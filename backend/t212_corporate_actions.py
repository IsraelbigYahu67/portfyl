"""Trading 212 corporate-action normalization (plan 2026-09-24 Track B).

The leg encoding is defined by docs/research/t212-corporate-action-encoding.md
(gate G1, signed off 2026-09-30). Only _leg_of and collapse_split_pairs know
that encoding.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timezone
from decimal import Decimal, InvalidOperation
from fractions import Fraction

from sqlalchemy.orm import Session

from models import (
    BrokerCorporateAction,
    BrokerCorporateActionApplication,
    BrokerSyncEvent,
    BrokerSyncRun,
    Portfolio,
    Transaction,
)
from t212_sync import _normalize_t212_ticker, _parse_t212_datetime

# G1 decision 1: walletImpact is informational on split legs, but both legs must
# carry the same value (a real cash component would make them differ). Rounding
# to whole minor units can differ by a cent between legs.
_WALLET_TOLERANCE = Decimal("0.01")
# Rounded share quantities and prices can disagree slightly; a real mismatch
# (value not conserved) is far larger than 1%.
_PRICE_RATIO_TOLERANCE = Fraction(1, 100)


class UnpairedSplitLeg(Exception):
    """A STOCK_SPLIT leg without exactly one counterpart in the staged set."""


class InvalidSplitPair(UnpairedSplitLeg):
    """A close/open pair that does not look like a pure split (G1): values differ
    between legs, or the price ratio disagrees with the share ratio."""


@dataclass(frozen=True)
class SplitEvidence:
    provider_instrument_id: str
    effective_at: datetime
    provider_event_key: str
    old_shares: Decimal
    new_shares: Decimal
    event_ids: tuple[str, ...]

    @property
    def ratio(self) -> Fraction:
        return Fraction(self.new_shares / self.old_shares).limit_denominator(1000)


def _leg_of(event: BrokerSyncEvent) -> str:
    # G1: SELL = close leg (old shares, negative quantity), BUY = open leg (new shares).
    side = (((event.raw_payload or {}).get("order") or {}).get("side") or "").upper()
    if side == "SELL":
        return "close"
    if side == "BUY":
        return "open"
    raise UnpairedSplitLeg(f"split leg {event.provider_event_id} has unknown side {side!r}")


def _decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _wallet_net_value(event: BrokerSyncEvent) -> Decimal | None:
    impact = ((event.raw_payload or {}).get("fill") or {}).get("walletImpact")
    return _decimal(impact.get("netValue")) if isinstance(impact, dict) else None


def _validate_pair(label: str, close: BrokerSyncEvent, open_: BrokerSyncEvent,
                   old: Decimal, new: Decimal) -> None:
    close_value, open_value = _wallet_net_value(close), _wallet_net_value(open_)
    if (close_value is None) != (open_value is None) or (
        close_value is not None and abs(abs(close_value) - abs(open_value)) > _WALLET_TOLERANCE
    ):
        raise InvalidSplitPair(f"{label}: split legs carry different wallet values")

    close_price = _decimal(close.raw_payload["fill"].get("price"))
    open_price = _decimal(open_.raw_payload["fill"].get("price"))
    if not close_price or not open_price or close_price <= 0 or open_price <= 0:
        raise InvalidSplitPair(f"{label}: split legs lack prices to verify the ratio")
    by_shares = Fraction(new / old)
    by_price = Fraction(close_price / open_price)
    if abs(by_shares - by_price) > _PRICE_RATIO_TOLERANCE * by_shares:
        raise InvalidSplitPair(f"{label}: price ratio disagrees with the share ratio")


def collapse_split_pairs(events: list[BrokerSyncEvent]) -> list[SplitEvidence]:
    groups: dict[tuple[str, datetime], dict[str, list[BrokerSyncEvent]]] = defaultdict(
        lambda: {"open": [], "close": []}
    )
    for event in events:
        payload = event.raw_payload or {}
        fill = payload.get("fill") or {}
        if (fill.get("type") or "").upper() != "STOCK_SPLIT":
            continue
        instrument = ((payload.get("order") or {}).get("ticker") or "").strip()
        at = _parse_t212_datetime(fill.get("filledAt"))
        if not instrument or at is None:
            raise UnpairedSplitLeg(f"split leg {event.provider_event_id} lacks instrument or time")
        groups[(instrument, at)][_leg_of(event)].append(event)

    out: list[SplitEvidence] = []
    for (instrument, at), legs in sorted(groups.items()):
        label = f"{instrument} at {at.isoformat()}"
        if len(legs["open"]) != 1 or len(legs["close"]) != 1:
            raise UnpairedSplitLeg(
                f"{label}: {len(legs['close'])} close / {len(legs['open'])} open legs"
            )
        close, open_ = legs["close"][0], legs["open"][0]
        old = abs(_decimal(close.raw_payload["fill"].get("quantity")) or Decimal(0))
        new = abs(_decimal(open_.raw_payload["fill"].get("quantity")) or Decimal(0))
        if old <= 0 or new <= 0:
            raise InvalidSplitPair(f"{label}: non-positive leg quantity")
        _validate_pair(label, close, open_, old, new)
        ids = tuple(sorted((close.provider_event_id, open_.provider_event_id)))
        out.append(SplitEvidence(instrument, at, "|".join(ids), old, new, ids))
    return out


@dataclass(frozen=True)
class ApplySummary:
    actions_created: int
    applications_created: int
    csv_represented: int


def _is_t212_origin(t: Transaction) -> bool:
    if t.source in {"t212_api", "t212_csv"}:
        return True
    return not t.source and (t.notes or "").startswith("T212")


def _row_time(t: Transaction) -> datetime:
    if t.executed_at is not None:
        return t.executed_at if t.executed_at.tzinfo else t.executed_at.replace(tzinfo=timezone.utc)
    return datetime.combine(t.date, time.max, tzinfo=timezone.utc)


def _action_ratio(action: BrokerCorporateAction) -> Fraction:
    return Fraction(Decimal(action.ratio_numerator)) / Fraction(Decimal(action.ratio_denominator))


def apply_splits(db: Session, *, run: BrokerSyncRun, portfolio: Portfolio,
                 evidence: list[SplitEvidence], pending: list[Transaction]) -> ApplySummary:
    """Record each split once and adjust the T212-origin buy/sell rows that
    predate it, exactly once per (action, transaction). Runs inside the ledger
    lock finalize_run already holds. A split whose two legs the CSV importer
    already stored as split_open/split_close rows is recorded as "csv_rows" and
    changes nothing: one provider action has exactly one quantity-changing form."""
    created = applied = csv_rep = 0
    for ev in sorted(evidence, key=lambda e: e.effective_at):
        ticker = _normalize_t212_ticker(ev.provider_instrument_id)
        rows = db.query(Transaction).filter(
            Transaction.workspace_id == portfolio.workspace_id,
            Transaction.portfolio_id == portfolio.id,
            Transaction.ticker == ticker,
        ).all()
        action = db.query(BrokerCorporateAction).filter_by(
            workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id,
            account_fingerprint=run.account_fingerprint,
            provider_instrument_id=ev.provider_instrument_id, action_type="STOCK_SPLIT",
            effective_at=ev.effective_at, provider_event_key=ev.provider_event_key,
        ).first()
        if action is None:
            csv_legs = {t.type for t in rows
                        if t.type in {"split_open", "split_close"} and t.date == ev.effective_at.date()}
            action = BrokerCorporateAction(
                workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id,
                broker="trading212", account_fingerprint=run.account_fingerprint,
                provider_instrument_id=ev.provider_instrument_id, ticker=ticker,
                action_type="STOCK_SPLIT", effective_at=ev.effective_at,
                provider_event_key=ev.provider_event_key,
                ratio_numerator=ev.ratio.numerator, ratio_denominator=ev.ratio.denominator,
                representation="csv_rows" if csv_legs == {"split_open", "split_close"} else "api_normalized",
                run_id=run.id,
            )
            db.add(action)
            db.flush()
            created += 1
        if action.representation == "csv_rows":
            csv_rep += 1
            continue
        already = {
            a.transaction_id for a in db.query(BrokerCorporateActionApplication).filter_by(
                workspace_id=portfolio.workspace_id, action_id=action.id,
            )
        }
        ratio = _action_ratio(action)
        candidates = rows + [p for p in pending if p.ticker == ticker and p not in rows]
        for t in candidates:
            if t.type not in {"buy", "sell"} or not _is_t212_origin(t):
                continue
            if _row_time(t) >= ev.effective_at:
                continue
            if t.id is None:
                db.add(t)
                db.flush()
            if t.id in already:
                continue
            before_shares, before_price = t.shares, t.price
            t.shares = float(Fraction(str(t.shares)) * ratio)
            t.price = float(Fraction(str(t.price)) / ratio)
            db.add(BrokerCorporateActionApplication(
                workspace_id=portfolio.workspace_id, action_id=action.id, transaction_id=t.id,
                shares_before=before_shares, price_before=before_price,
                shares_after=t.shares, price_after=t.price, applied_by_run_id=run.id,
            ))
            already.add(t.id)
            applied += 1
    return ApplySummary(created, applied, csv_rep)


def reapply_recorded_splits(db: Session, *, workspace_id, rows: list[Transaction]) -> None:
    """After an audit run overwrote rows with the provider's raw values, put
    back every recorded split adjustment, oldest first, and refresh the
    application markers. Without this a provider correction would silently
    undo the split and leave pre-split share counts in the ledger."""
    by_id = {t.id: t for t in rows if t.id is not None}
    if not by_id:
        return
    applications = (
        db.query(BrokerCorporateActionApplication, BrokerCorporateAction)
        .join(BrokerCorporateAction, (BrokerCorporateAction.workspace_id
                                      == BrokerCorporateActionApplication.workspace_id)
              & (BrokerCorporateAction.id == BrokerCorporateActionApplication.action_id))
        .filter(
            BrokerCorporateActionApplication.workspace_id == workspace_id,
            BrokerCorporateActionApplication.transaction_id.in_(list(by_id)),
        )
        .order_by(BrokerCorporateAction.effective_at, BrokerCorporateAction.id)
        .all()
    )
    for application, action in applications:
        t = by_id[application.transaction_id]
        application.shares_before, application.price_before = t.shares, t.price
        ratio = _action_ratio(action)
        t.shares = float(Fraction(str(t.shares)) * ratio)
        t.price = float(Fraction(str(t.price)) / ratio)
        application.shares_after, application.price_after = t.shares, t.price
