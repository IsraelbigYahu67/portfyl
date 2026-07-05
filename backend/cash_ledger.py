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


def cash_balance_by_currency(transactions) -> dict[str, float]:
    """Per-currency net cash (native). Negative balances are allowed (tolerant)."""
    out: dict[str, float] = {}
    for txn in transactions:
        ccy, amt = signed_cash(txn)
        out[ccy] = out.get(ccy, 0.0) + amt
    return out
