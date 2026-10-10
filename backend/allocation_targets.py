"""Per-portfolio target allocation: validation and drift.

Snowball-gap spec 2026-09-20 §4.2; plan 2026-10-10. Pure functions -- no
database, no network. Drift is computed from `/portfolio/holdings` rows, so the
current-weight denominator is the market value of active holdings in the
display currency (cash excluded), exactly like that endpoint's `weight`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

TARGET_SUM_TOLERANCE = Decimal("0.01")
HUNDRED = Decimal("100")
MAX_TARGETS = 200
MAX_GROUP_LENGTH = 40
_CENT = Decimal("0.01")
_TICKER_RE = re.compile(r"[A-Z0-9^][A-Z0-9.\-=_^]{0,31}")


class TargetSetError(ValueError):
    """A target set that must not be saved. The message is shown to the user."""


@dataclass(frozen=True)
class TargetSpec:
    ticker: str
    target_pct: Decimal
    group: str | None = None


def normalize_ticker(raw: str) -> str:
    ticker = (raw or "").strip().upper()
    if not _TICKER_RE.fullmatch(ticker):
        raise TargetSetError(f"'{(raw or '').strip()}' is not a valid ticker.")
    return ticker


def normalize_group(raw: str | None) -> str | None:
    group = (raw or "").strip()
    if not group:
        return None
    if len(group) > MAX_GROUP_LENGTH:
        raise TargetSetError(f"Group names can be at most {MAX_GROUP_LENGTH} characters.")
    return group


def target_total(targets: Iterable[TargetSpec]) -> Decimal:
    return sum((t.target_pct for t in targets), Decimal("0"))


def is_complete(total: Decimal) -> bool:
    return abs(total - HUNDRED) <= TARGET_SUM_TOLERANCE


def validate_target_set(targets: list[TargetSpec]) -> Decimal:
    """Reject a set that must not be stored; return its total otherwise.

    A partial set (total below 100%) is allowed -- the user may save while
    still deciding. Only a total above 100% (plus tolerance) is an error.
    """
    if len(targets) > MAX_TARGETS:
        raise TargetSetError(f"A portfolio can have at most {MAX_TARGETS} targets.")
    seen: set[str] = set()
    for target in targets:
        if target.ticker in seen:
            raise TargetSetError(f"{target.ticker} has more than one target.")
        seen.add(target.ticker)
        if target.target_pct < 0 or target.target_pct > HUNDRED:
            raise TargetSetError(f"The target for {target.ticker} must be between 0 and 100%.")
        if target.target_pct != target.target_pct.quantize(_CENT):
            raise TargetSetError(
                f"The target for {target.ticker} can have at most two decimal places."
            )
    total = target_total(targets)
    if total > HUNDRED + TARGET_SUM_TOLERANCE:
        raise TargetSetError(f"Targets add up to {total}%, more than 100%.")
    return total


def compute_drift(holdings: list[dict], targets: list[TargetSpec]) -> dict:
    active = [h for h in holdings if not h.get("closed")]
    by_ticker = {str(h["ticker"]).strip().upper(): h for h in active}
    total_value = sum(float(h.get("market_value") or 0) for h in active)

    def weight(value: float) -> float:
        return value / total_value * 100 if total_value > 0 else 0.0

    rows: list[dict] = []
    group_totals: dict[str, list[float]] = {}
    targeted: set[str] = set()
    for target in targets:
        held = by_ticker.get(target.ticker)
        value = float(held.get("market_value") or 0) if held else 0.0
        target_pct = float(target.target_pct)
        current = weight(value)
        rows.append({
            "ticker": target.ticker,
            "name": held.get("name") if held else None,
            "group": target.group,
            "held": held is not None,
            "target_pct": target_pct,
            "current_pct": round(current, 2),
            "drift_pct": round(current - target_pct, 2),
            "market_value": round(value, 2),
            "value_to_target": (
                round(total_value * target_pct / 100 - value, 2) if total_value > 0 else None
            ),
        })
        targeted.add(target.ticker)
        if target.group is not None:
            sums = group_totals.setdefault(target.group, [0.0, 0.0])
            sums[0] += target_pct
            sums[1] += current

    unassigned = sorted(
        (h for ticker, h in by_ticker.items() if ticker not in targeted),
        key=lambda h: -float(h.get("market_value") or 0),
    )
    unassigned_pct = 0.0
    for held in unassigned:
        value = float(held.get("market_value") or 0)
        unassigned_pct += weight(value)
        rows.append({
            "ticker": str(held["ticker"]).strip().upper(),
            "name": held.get("name"),
            "group": None,
            "held": True,
            "target_pct": None,
            "current_pct": round(weight(value), 2),
            "drift_pct": None,
            "market_value": round(value, 2),
            "value_to_target": None,
        })

    total = target_total(targets)
    complete = is_complete(total)
    missing = sorted(t for t, h in by_ticker.items() if h.get("price_status") == "missing")
    warnings = []
    if not complete:
        warnings.append("targets_incomplete")
    if missing:
        warnings.append("missing_prices")
    return {
        "total_value": round(total_value, 2),
        "target_total_pct": float(total),
        "is_complete": complete,
        "unassigned_pct": round(unassigned_pct, 2),
        "rows": rows,
        "groups": [
            {
                "group": name,
                "target_pct": round(target_sum, 2),
                "current_pct": round(current_sum, 2),
                "drift_pct": round(current_sum - target_sum, 2),
            }
            for name, (target_sum, current_sum) in group_totals.items()
        ],
        "missing_price_tickers": missing,
        "warnings": warnings,
    }
