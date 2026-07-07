"""Cash ledger: pure balance/interest math + the trade/cash type discriminator.

Cash flows share the Transaction table (discriminated by `type`). These frozensets
are the single source of truth used everywhere to keep cash rows out of holdings /
returns math.
"""
from __future__ import annotations

from datetime import date

TRADE_TYPES = frozenset({"buy", "sell", "dividend"})
CASH_TYPES = frozenset({"deposit", "withdrawal", "fee", "interest"})


def signed_cash(txn) -> tuple[str, float]:
    """(currency, signed native amount) for one row. Cash rows use `amount`;
    trades use shares*price. Direction by type."""
    ccy = (txn.currency or "USD").upper()
    t = txn.type
    if t == "deposit" or t == "interest":
        return ccy, float(txn.amount or 0.0)
    if t == "withdrawal" or t == "fee":
        return ccy, -float(txn.amount or 0.0)
    value = float(txn.shares or 0.0) * float(txn.price or 0.0)
    if t == "buy":
        return ccy, -value
    if t == "sell" or t == "dividend":
        return ccy, value
    return ccy, 0.0


def has_external_cashflows(transactions) -> bool:
    """True if any row is a deposit or withdrawal -- external capital movement
    (money entering/leaving the portfolio from outside), as opposed to
    buys/sells (internal reallocation) or fee/interest (cash-only, not an
    external capital contribution). Gates the cash-aware returns path in
    analytics.py; portfolios with none of these take the untouched original
    trade-only path."""
    return any(t.type in ("deposit", "withdrawal") for t in transactions)


def cash_balance_by_currency(transactions) -> dict[str, float]:
    """Per-currency net cash (native). Negative balances are allowed (tolerant)."""
    out: dict[str, float] = {}
    for txn in transactions:
        ccy, amt = signed_cash(txn)
        out[ccy] = out.get(ccy, 0.0) + amt
    return out


def _balance_timeline(transactions, currency):
    """Sorted [(date, running_balance)] for `currency`, one point per event date."""
    events = []
    for txn in transactions:
        ccy, amt = signed_cash(txn)
        if ccy == currency and amt:
            events.append((txn.date, amt))
    events.sort(key=lambda e: e[0])
    timeline, running = [], 0.0
    for d, amt in events:
        running += amt
        if timeline and timeline[-1][0] == d:
            timeline[-1] = (d, running)
        else:
            timeline.append((d, running))
    return timeline


def accrued_interest(transactions, rates, as_of=None):
    """Lazy straight-line interest per currency: sum(balance * rate * days/365)
    over each segment where balance > 0, from max(start_date, first event) to as_of.
    Only currencies with an enabled rate accrue."""
    as_of = as_of or date.today()
    out: dict[str, float] = {}
    for ccy, cfg in rates.items():
        if not cfg.get("enabled") or not cfg.get("annual_rate"):
            continue
        rate = float(cfg["annual_rate"])
        timeline = _balance_timeline(transactions, ccy)
        if not timeline:
            continue
        start = cfg.get("start_date") or timeline[0][0]
        total = 0.0
        for i, (seg_start, bal) in enumerate(timeline):
            seg_end = timeline[i + 1][0] if i + 1 < len(timeline) else as_of
            seg_end = min(seg_end, as_of)  # never accrue past the requested as_of
            lo = max(seg_start, start)
            if seg_end <= lo or bal <= 0:
                continue
            days = (seg_end - lo).days
            total += bal * rate * days / 365.0
        rounded = round(total, 2)
        if rounded:
            out[ccy] = rounded
    return out
