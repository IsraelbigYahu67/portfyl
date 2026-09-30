"""Trading 212 corporate-action normalization (plan 2026-09-24 Track B).

The leg encoding is defined by docs/research/t212-corporate-action-encoding.md
(gate G1, signed off 2026-09-30). Only _leg_of and collapse_split_pairs know
that encoding.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from fractions import Fraction

from models import BrokerSyncEvent
from t212_sync import _parse_t212_datetime

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
