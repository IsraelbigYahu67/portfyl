"""Per-transaction FX snapshots: rate from txn currency to CZK on txn date.

Used so portfolio cost basis in CZK reflects what the user actually paid,
not today's rate applied retroactively.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

import pandas as pd
import yfinance as yf


_DAILY_CACHE: dict[str, pd.Series] = {}


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
    if key in _DAILY_CACHE:
        return _DAILY_CACHE[key]
    try:
        raw = yf.download(
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
