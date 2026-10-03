"""Pure mapping of Trading 212 `/equity/history/transactions` events.

The encoding was proven from a real capture and signed off in
docs/research/t212-cash-transaction-encoding.md; every rule below is that
record's Decision. This module has no database or network dependency so
t212_sync can import it freely. Anything the record does not prove is returned
as `UnsupportedCash`, never guessed: the caller sends the run to `needs_review`.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timezone

# type -> (ledger type, the sign the provider is proven to use for it).
# TRANSFER has no fixed sign: its sign is its direction (proven 4/4).
_FIXED_TYPES: dict[str, tuple[str, int]] = {
    "DEPOSIT": ("deposit", 1),
    "WITHDRAW": ("withdrawal", -1),
    "FEE": ("fee", -1),
    "INTEREST_ON_FREE_CASH": ("interest", 1),
    "LENDING_INTEREST": ("interest", 1),
}


@dataclass(frozen=True)
class CashRow:
    type: str
    amount: float
    currency: str
    executed_at: datetime
    date: date
    notes: str
    event_id: str


@dataclass(frozen=True)
class UnsupportedCash:
    reason: str
    source_type: str | None = None


def _parse_time(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def cash_event_time(item: dict) -> datetime | None:
    return _parse_time(item.get("dateTime"))


def cash_event_id(item: dict) -> str:
    reference = item.get("reference")
    if reference:
        return f"cash:{reference}"
    blob = json.dumps(item, sort_keys=True, default=str)
    return f"cash-fp:{hashlib.sha256(blob.encode()).hexdigest()[:32]}"


def map_cash_event(item: dict) -> CashRow | UnsupportedCash:
    source_type = item.get("type")
    kind = str(source_type).upper() if source_type else None

    when = cash_event_time(item)
    if when is None:
        return UnsupportedCash("missing or invalid dateTime", kind)
    currency = str(item.get("currency") or "").strip().upper()
    if not currency:
        return UnsupportedCash("missing currency", kind)
    try:
        amount = float(item.get("amount"))
    except (TypeError, ValueError):
        return UnsupportedCash("amount is not a number", kind)
    if not math.isfinite(amount) or amount == 0:
        return UnsupportedCash("amount is zero or not finite", kind)

    if kind == "TRANSFER":
        ledger_type = "deposit" if amount > 0 else "withdrawal"
    elif kind in _FIXED_TYPES:
        ledger_type, proven_sign = _FIXED_TYPES[kind]
        if (amount > 0) != (proven_sign > 0):
            return UnsupportedCash("sign contradicts the proven direction", kind)
    else:
        return UnsupportedCash("unmapped cash transaction type", kind)

    utc = when.astimezone(timezone.utc)
    return CashRow(
        type=ledger_type,
        amount=round(abs(amount), 6),
        currency=currency,
        executed_at=utc,
        date=utc.date(),
        notes=f"T212 {kind}",
        event_id=cash_event_id(item),
    )
