"""Cash ledger: pure balance/interest math + the trade/cash type discriminator.

Cash flows share the Transaction table (discriminated by `type`). These frozensets
are the single source of truth used everywhere to keep cash rows out of holdings /
returns math.
"""
from __future__ import annotations

from datetime import date, timedelta

TRADE_TYPES = frozenset({"buy", "sell", "dividend"})
# Corporate-action rows change the position quantity but never move cash.
POSITION_TYPES = TRADE_TYPES | frozenset({"split_open", "split_close"})
# card_debit / cashback: T212 card spending and its cashback. fx_in / fx_out: the two
# legs of a currency conversion (internal transfer between currency piles).
CASH_TYPES = frozenset({"deposit", "withdrawal", "fee", "interest",
                        "card_debit", "cashback", "fx_in", "fx_out"})
# Money entering/leaving the portfolio from outside — gates the cash-aware returns
# path and feeds the external-cashflow series C. fee/interest/fx_* are cash-only
# internal events; buys/sells are internal reallocation.
EXTERNAL_FLOW_TYPES = frozenset({"deposit", "withdrawal", "card_debit", "cashback"})

_CASH_IN = frozenset({"deposit", "interest", "cashback", "fx_in"})
_CASH_OUT = frozenset({"withdrawal", "fee", "card_debit", "fx_out"})


def signed_cash(txn) -> tuple[str, float]:
    """(currency, signed native amount) for one row.

    Cash rows use `amount` with direction from `type`. Trades/dividends settle in
    `cash_currency` for the exact `cash_amount` when present (T212 `Total`, FX fees
    included) — buys pull from the pile, sells/dividends push in. Legacy trade rows
    without a settlement snapshot fall back to shares*price in the trade currency.
    """
    t = txn.type
    if t in _CASH_IN:
        return (txn.currency or "USD").upper(), float(txn.amount or 0.0)
    if t in _CASH_OUT:
        return (txn.currency or "USD").upper(), -float(txn.amount or 0.0)
    if t in TRADE_TYPES:
        if getattr(txn, "cash_amount", None):
            ccy = (txn.cash_currency or "CZK").upper()
            value = float(txn.cash_amount)
        else:
            ccy = (txn.currency or "USD").upper()
            value = float(txn.shares or 0.0) * float(txn.price or 0.0)
        return ccy, -value if t == "buy" else value
    return (txn.currency or "USD").upper(), 0.0


def has_external_cashflows(transactions) -> bool:
    """True if any row moves money in/out of the portfolio from outside
    (EXTERNAL_FLOW_TYPES). Gates the cash-aware returns path in analytics.py;
    portfolios with none of these take the untouched original trade-only path."""
    return any(t.type in EXTERNAL_FLOW_TYPES for t in transactions)


def cash_balance_by_currency(transactions) -> dict[str, float]:
    """Per-currency net cash (native). Negative balances are allowed (tolerant)."""
    out: dict[str, float] = {}
    for txn in transactions:
        ccy, amt = signed_cash(txn)
        out[ccy] = out.get(ccy, 0.0) + amt
    return out


def last_interest_date_by_currency(transactions) -> dict[str, date]:
    """Latest actual `interest` row per currency — real (imported) interest covers
    accrual up to and including that day, so lazy accrual starts the day after."""
    out: dict[str, date] = {}
    for txn in transactions:
        if txn.type == "interest":
            ccy = (txn.currency or "USD").upper()
            if ccy not in out or txn.date > out[ccy]:
                out[ccy] = txn.date
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
    over each segment where balance > 0, from the accrual start to as_of.
    Accrual starts at the later of cfg.start_date and the day AFTER the last real
    `interest` row (imported interest already covers up to that day). Only
    currencies with an enabled rate accrue."""
    as_of = as_of or date.today()
    last_real = last_interest_date_by_currency(transactions)
    out: dict[str, float] = {}
    for ccy, cfg in rates.items():
        if not cfg.get("enabled") or not cfg.get("annual_rate"):
            continue
        rate = float(cfg["annual_rate"])
        timeline = _balance_timeline(transactions, ccy)
        if not timeline:
            continue
        start = cfg.get("start_date") or timeline[0][0]
        if ccy in last_real:
            start = max(start, last_real[ccy] + timedelta(days=1))
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
