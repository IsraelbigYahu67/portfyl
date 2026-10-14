"""Per-transaction FX snapshots: rate from txn currency to CZK on txn date.

Used so portfolio cost basis in CZK reflects what the user actually paid,
not today's rate applied retroactively.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

import pandas as pd
import yfinance as yf

import market_data
from cache import BoundedTTLCache


# Keys embed the requested date window, which varies per transaction date, so
# this must be bounded. Windows ending today keep moving, hence the TTL.
_DAILY_CACHE: BoundedTTLCache = BoundedTTLCache(512, ttl=6 * 3600.0)


def _pair(currency: str) -> str | None:
    c = (currency or "USD").upper()
    if c == "CZK":
        return None
    return f"{c}CZK=X"


def _load_series(currency: str, start: date, end: date) -> pd.Series | None:
    pair = _pair(currency)
    if pair is None:
        return None
    key = f"{pair}:{start}:{end}"
    cached = _DAILY_CACHE.get(key)
    if cached is not None:
        return cached
    try:
        raw = market_data.download(
            pair,
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=2)).strftime("%Y-%m-%d"),
            auto_adjust=True,
            progress=False,
        )
        if raw.empty:
            return None
        col = raw["Close"]
        if hasattr(col, "squeeze"):
            col = col.squeeze()
        series = col.dropna()
        _DAILY_CACHE[key] = series
        return series
    except Exception:
        return None


def fetch_fx_to_czk(currency: str, txn_date: date) -> float | None:
    """Return rate from `currency` to CZK on `txn_date` (daily close).

    Forward-fills over weekends/holidays. Returns 1.0 if currency is CZK.
    Returns None if the rate is unavailable.
    """
    if not currency or currency.upper() == "CZK":
        return 1.0
    # Pull a ~10-day window around the date so we can ffill weekends/holidays.
    series = _load_series(currency, txn_date - timedelta(days=10), txn_date + timedelta(days=2))
    if series is None or series.empty:
        return None
    try:
        ts = pd.Timestamp(txn_date)
        earlier = series[series.index <= ts]
        if earlier.empty:
            # txn predates available data; fall back to earliest known
            v = float(series.iloc[0])
        else:
            v = float(earlier.iloc[-1])
        return v if v > 0 else None
    except Exception:
        return None


def convert_amount(amount_native: float, from_ccy: str, to_ccy: str,
                   on_date: date | None = None) -> float:
    """Convert `amount_native` from `from_ccy` to `to_ccy` (display currency).

    Mirrors how `get_summary` maps native figures to the display currency —
    money is pivoted through CZK using the same `{ccy}CZK=X` rate source
    (`fetch_fx_to_czk`): native -> CZK, then CZK -> display. Same-currency
    conversions are a no-op, and a missing/zero rate degrades gracefully to the
    input amount (matching `get_summary`, which never crashes on absent FX).
    """
    src = (from_ccy or "USD").upper()
    dst = (to_ccy or "USD").upper()
    if src == dst:
        return amount_native
    on_date = on_date or date.today()
    r_from = fetch_fx_to_czk(src, on_date)   # native -> CZK
    r_to = fetch_fx_to_czk(dst, on_date)     # display -> CZK
    if not r_from or not r_to:
        return amount_native  # no rate available: leave amount unconverted
    return amount_native * r_from / r_to


def cash_amount_to_display(amount_native: float, native_ccy: str, display_ccy: str) -> float:
    """Blended cash total helper: real conversion into the display currency
    (native -> CZK -> display). get_summary/holdings convert on the same
    CZK-pivot basis, so net_worth = total_value + cash stays consistent."""
    return convert_amount(amount_native, native_ccy, display_ccy)


def cash_total_from_transactions(transactions, display_ccy: str) -> float:
    """Blended cash BALANCE total in display currency.
    Sums cash_balance_by_currency (native, per currency) via cash_amount_to_display."""
    from cash_ledger import cash_balance_by_currency
    balances = cash_balance_by_currency(transactions)
    return sum(cash_amount_to_display(v, ccy, display_ccy) for ccy, v in balances.items())


def folded_cash_display(transactions, rates, display_ccy):
    """Blended cash BALANCE + accrued interest in display currency.
    The single 'Cash' figure used by the dashboard summary and the allocation bucket,
    so both reconcile with net_worth. Callers gate on has_external_cashflows first."""
    from cash_ledger import cash_balance_by_currency, accrued_interest
    balances = cash_balance_by_currency(transactions)
    accrued = accrued_interest(transactions, rates)
    total = sum(cash_amount_to_display(v, ccy, display_ccy) for ccy, v in balances.items())
    total += sum(cash_amount_to_display(v, ccy, display_ccy) for ccy, v in accrued.items())
    return total


def bulk_fetch_fx(pairs: Iterable[tuple[str, date]]) -> dict[tuple[str, date], float]:
    """Batch-resolve (currency, date) → rate. Groups by currency and downloads
    one history window per currency to minimize yfinance calls."""
    pairs = list(pairs)
    if not pairs:
        return {}

    by_ccy: dict[str, list[date]] = {}
    for ccy, d in pairs:
        by_ccy.setdefault((ccy or "USD").upper(), []).append(d)

    out: dict[tuple[str, date], float] = {}
    for ccy, dates in by_ccy.items():
        if ccy == "CZK":
            for d in dates:
                out[(ccy, d)] = 1.0
            continue
        lo, hi = min(dates), max(dates)
        series = _load_series(ccy, lo - timedelta(days=10), hi + timedelta(days=2))
        if series is None or series.empty:
            continue
        for d in dates:
            try:
                ts = pd.Timestamp(d)
                earlier = series[series.index <= ts]
                v = float(earlier.iloc[-1]) if not earlier.empty else float(series.iloc[0])
                if v > 0:
                    out[(ccy, d)] = v
            except Exception:
                pass
    return out
