"""Per-ticker dividend-growth analytics: annual DPS series, growth streak,
CAGR, YoY, and payout ratio. Pure function of a ticker's yfinance dividend
history; cached in-process. Leaf module — must not import from routers.*."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Optional

import pandas as pd
import yfinance as yf

from cache import ttl_cache
from ticker_map import yf_symbol

_GROWTH_TTL = 3600  # 1h — dividend schedules change slowly


def _to_pct(v: Optional[float]) -> Optional[float]:
    """Decimal fraction (0.42) -> percent (42.0)."""
    return None if v is None else round(v * 100, 2)


def _annual_dps(dividends: pd.Series) -> list[dict]:
    """Sum per-share payments into calendar-year totals, ascending by year."""
    totals: dict[int, float] = defaultdict(float)
    for ts, amt in dividends.items():
        try:
            year = pd.Timestamp(ts).year
            totals[year] += float(amt)
        except (TypeError, ValueError):
            continue
    return [{"year": y, "dps": round(totals[y], 4)} for y in sorted(totals)]


def _closed(annual: list[dict], current_year: int) -> list[dict]:
    """Only fully-elapsed years — the in-progress year has partial data."""
    return [a for a in annual if a["year"] < current_year]


def _streak(annual: list[dict], current_year: int) -> int:
    """Consecutive most-recent closed years with a strictly higher DPS than
    the prior year (dividend-aristocrat style count of consecutive raises)."""
    closed = _closed(annual, current_year)
    streak = 0
    for i in range(len(closed) - 1, 0, -1):
        if closed[i]["dps"] > closed[i - 1]["dps"] and closed[i]["year"] == closed[i - 1]["year"] + 1:
            streak += 1
        else:
            break
    return streak


def _cagr(annual: list[dict], current_year: int, max_years: int = 5) -> tuple[Optional[float], int]:
    """CAGR of annual DPS over up to the last `max_years` closed years.
    Returns (cagr_pct, years_spanned). None cagr if start<=0 or <2 points."""
    closed = _closed(annual, current_year)
    if len(closed) < 2:
        return None, 0
    window = closed[-(max_years + 1):]
    start = window[0]["dps"]
    end = window[-1]["dps"]
    years = window[-1]["year"] - window[0]["year"]
    if start <= 0 or years <= 0:
        return None, max(years, 0)
    cagr = (end / start) ** (1.0 / years) - 1.0
    return round(cagr * 100, 2), years


def _yoy(annual: list[dict], current_year: int) -> Optional[float]:
    """Last closed year vs. the year before it, in percent."""
    closed = _closed(annual, current_year)
    if len(closed) < 2:
        return None
    prev, last = closed[-2]["dps"], closed[-1]["dps"]
    if prev <= 0:
        return None
    return round((last / prev - 1.0) * 100, 2)


@ttl_cache(_GROWTH_TTL)
def compute_dividend_growth(symbol: str, _current_year: int | None = None) -> dict:
    """Growth stats for one ticker. Best-effort; never raises on bad data.

    `_current_year` is injectable for tests; defaults to today's year.
    """
    current_year = _current_year if _current_year is not None else date.today().year
    empty = {
        "ticker": symbol, "streak_years": 0, "cagr_pct": None,
        "cagr_years_used": 0, "yoy_pct": None, "payout_ratio_pct": None,
        "annual": [], "payments": [],
    }
    try:
        tk = yf.Ticker(yf_symbol(symbol))
        div = tk.dividends
    except Exception:
        return empty

    # Payout ratio from .info (best-effort, independent of history).
    payout = None
    try:
        info = tk.info or {}
        pr = info.get("payoutRatio")
        payout = _to_pct(float(pr)) if pr is not None else None
    except Exception:
        payout = None

    if div is None or getattr(div, "empty", True):
        return {**empty, "payout_ratio_pct": payout}

    try:
        annual = _annual_dps(div)
        payments = sorted(
            (
                {"ex_date": pd.Timestamp(ts).date().isoformat(), "amount": round(float(a), 4)}
                for ts, a in div.items()
            ),
            key=lambda p: p["ex_date"],
        )
    except Exception:
        return {**empty, "payout_ratio_pct": payout}

    cagr_pct, years_used = _cagr(annual, current_year)
    return {
        "ticker": symbol,
        "streak_years": _streak(annual, current_year),
        "cagr_pct": cagr_pct,
        "cagr_years_used": years_used,
        "yoy_pct": _yoy(annual, current_year),
        "payout_ratio_pct": payout,
        "annual": annual,
        "payments": payments,
    }
