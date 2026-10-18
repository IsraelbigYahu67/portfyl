"""Shared chronological ordering key for transactions.

T212 snapshot-first sync plan (docs/superpowers/plans/2026-09-20-t212-snapshot-first-sync.md),
§4.5: adding `Transaction.executed_at` alone is insufficient because
legacy consumers ordered by `date` plus a fixed type-order fallback for
same-day rows. This module is the single shared key used by holdings/FIFO,
realized P/L, performance, and analytics so those
accounting paths cannot drift apart.
"""

from __future__ import annotations

from datetime import datetime, timezone

# Date-only CSV/manual rows keep the legacy deterministic fallback.
TXN_TYPE_ORDER = {"buy": 0, "split_close": 1, "split_open": 2, "dividend": 3, "sell": 4}


def chronological_key(txn) -> tuple:
    """Sort key for one transaction: aware `executed_at` when present,
    otherwise `date` plus the existing type-order fallback. The two shapes
    interleave deterministically across the same calendar day (an
    `executed_at`-bearing row's second component is a sub-day offset,
    a date-only row's is a small type-order integer, and the third
    component breaks the tie) -- this is stable and reproducible, not a
    claim that a date-only row's true intraday time is known."""
    executed_at = getattr(txn, "executed_at", None)
    if executed_at is not None:
        if executed_at.tzinfo is None:
            executed_at = executed_at.replace(tzinfo=timezone.utc)
        return (executed_at.date(), _fine_order(executed_at), 0)
    return (txn.date, TXN_TYPE_ORDER.get(txn.type, 1), 1)


def _fine_order(executed_at: datetime) -> float:
    """Sub-day ordering component for an executed_at-bearing row: seconds
    since midnight UTC on its own date, so two such rows on the same day
    order by real time instead of collapsing to the type-order tiebreak."""
    midnight = executed_at.replace(hour=0, minute=0, second=0, microsecond=0)
    return (executed_at - midnight).total_seconds()
