from fastapi import APIRouter, HTTPException
from typing import Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import median
import datetime
import math
import re
import time

import pandas as pd
import yfinance as yf

from ticker_map import yf_symbol
import market_data
import shibui_client
import alphavantage_client
from cache import ttl_cache

router = APIRouter(prefix="/market", tags=["market"])

# How long each yfinance-backed response is cached in-process. The frontend
# auto-loader prefetches every holding's fundamentals on load, so without these
# every page reload would re-hit Yahoo. Fundamentals change at most quarterly;
# quotes / FX are kept short so live prices stay reasonably fresh.
_FUNDAMENTALS_TTL = 3600     # 1 hour
_HISTORY_TTL = 1800          # 30 minutes
_SEARCH_TTL = 1800           # 30 minutes
_QUOTE_TTL = 120             # 2 minutes
_FX_TTL = 600                # 10 minutes

# Guards every f-string-interpolated ticker sent to Shibui's stock_data_query
# (that server takes a finished SQL string, not parametrized queries).
_SHIBUI_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


# ---------------------------------------------------------------------------
# Fundamentals helpers
# ---------------------------------------------------------------------------

# Representative large-cap constituents per Yahoo GICS sector. We compute a
# median of each ratio across this basket to serve as the "sector average"
# the per-stock view compares against. Using a stable hand-picked list
# (rather than scraping an index) keeps results consistent across reloads.
SECTOR_CONSTITUENTS = {
    "Technology": ["AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CRM", "AMD", "ADBE", "CSCO", "ACN"],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS", "VZ", "CMCSA", "T", "TMUS", "EA", "WBD"],
    "Consumer Cyclical": ["AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "TJX", "BKNG", "SBUX", "ABNB"],
    "Consumer Defensive": ["WMT", "PG", "COST", "KO", "PEP", "PM", "MDLZ", "MO", "CL", "TGT"],
    "Energy": ["XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "WMB", "OKE", "VLO"],
    "Financial Services": ["JPM", "V", "MA", "BAC", "WFC", "MS", "GS", "BLK", "SCHW", "AXP"],
    "Healthcare": ["LLY", "JNJ", "UNH", "ABBV", "MRK", "TMO", "ABT", "DHR", "PFE", "AMGN"],
    "Industrials": ["GE", "RTX", "CAT", "BA", "UNP", "HON", "UPS", "LMT", "DE", "ETN"],
    "Basic Materials": ["LIN", "SHW", "APD", "ECL", "FCX", "NEM", "DOW", "NUE", "DD", "VMC"],
    "Real Estate": ["AMT", "PLD", "EQIX", "WELL", "SPG", "PSA", "CCI", "O", "VICI", "DLR"],
    "Utilities": ["NEE", "SO", "DUK", "CEG", "AEP", "SRE", "VST", "D", "PCG", "EXC"],
}

# Each sector's medians are computed lazily on first request and cached for
# the process lifetime. Restarting the backend re-fetches.
_SECTOR_CACHE: dict[str, dict[str, Any]] = {}

# Full fundamentals payloads are expensive (~15 serial yfinance calls each), so
# we cache the assembled result per symbol for a few minutes. Keyed by the
# broker symbol; value is (built_at, payload).
_FUND_CACHE: dict[str, tuple[float, dict]] = {}
_FUND_TTL = 300.0

# Sanity bounds: yfinance occasionally returns garbage outliers (negative P/E
# on a money-losing company, P/S in the thousands, etc) that would skew even
# a median. We drop values outside these bands before computing the median.
_RATIO_BOUNDS = {
    "pe": (0, 200),
    "forward_pe": (0, 200),
    "ps": (0, 50),
    "pb": (0, 50),
    "pfcf": (0, 200),
    "peg": (0, 10),
    "ev_ebitda": (0, 200),
    "ev_revenue": (0, 50),
    "de": (0, 20),
    "current_ratio": (0, 20),
    "quick_ratio": (0, 20),
    "roe": (-200, 500),
    "roa": (-100, 100),
    "roic": (-100, 200),
    "gross_margin": (-100, 100),
    "operating_margin": (-100, 100),
    "net_margin": (-100, 100),
    "div_yield": (0, 30),
    "payout_ratio": (0, 200),
}


def _f(x) -> Optional[float]:
    """Coerce yfinance values into a JSON-friendly float (or None)."""
    try:
        if x is None:
            return None
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    except (TypeError, ValueError):
        return None


def _row(df: pd.DataFrame, *names: str) -> Optional[pd.Series]:
    if df is None or getattr(df, "empty", True):
        return None
    for n in names:
        if n in df.index:
            return df.loc[n]
    return None


def _series_periods(
    s: Optional[pd.Series], freq: str = "Y", n: int = 20
) -> tuple[list[str], list[float]]:
    """yfinance returns columns sorted newest→oldest. Flip to oldest→newest,
    drop periods where the metric is missing, and trim to the last n. Period
    labels are years for annual (freq="Y") or "Qx 'YY" for quarterly
    (freq="Q")."""
    if s is None:
        return [], []
    s = s.iloc[::-1]
    periods: list[str] = []
    values: list[float] = []
    for idx, raw in zip(s.index, s.values):
        v = _f(raw)
        if v is None:
            continue
        if freq == "Q" and hasattr(idx, "month") and hasattr(idx, "year"):
            q = (idx.month - 1) // 3 + 1
            label = f"Q{q} '{idx.year % 100:02d}"
        elif hasattr(idx, "year"):
            label = str(idx.year)
        else:
            label = str(idx)
        periods.append(label)
        values.append(v)
    if len(periods) > n:
        periods = periods[-n:]
        values = values[-n:]
    return periods, values


def _yoy(values: list[float], lag: int = 1) -> list[Optional[float]]:
    """Period-over-period change with a configurable lag. For annual data
    lag=1 (vs prior year); for quarterly lag=4 (vs same quarter last year).
    When the prior value is zero or both are negative we report None rather
    than a misleading huge percentage."""
    out: list[Optional[float]] = [None] * len(values)
    for i in range(lag, len(values)):
        prev, curr = values[i - lag], values[i]
        if prev == 0 or (prev < 0 and curr < 0):
            out[i] = None
        else:
            out[i] = round((curr - prev) / abs(prev) * 100, 2)
    return out


def _cagr(values: list[float], periods_per_year: int = 1) -> Optional[float]:
    """Annualised compound growth rate. Only well-defined when start and end
    are both positive. periods_per_year=4 for quarterly data so the rate is
    still expressed per-year."""
    if not values or len(values) < 2:
        return None
    start, end = values[0], values[-1]
    if start <= 0 or end <= 0:
        return None
    n = len(values) - 1
    try:
        return round((((end / start) ** (periods_per_year / n)) - 1) * 100, 2)
    except (ValueError, OverflowError, ZeroDivisionError):
        return None


def _metric_block(name: str, raw: Optional[pd.Series], freq: str = "Y") -> dict:
    periods, values = _series_periods(raw, freq=freq, n=40 if freq == "Q" else 20)
    if freq == "Q":
        yoy = _yoy(values, lag=4)
        cagr = _cagr(values, periods_per_year=4)
    else:
        yoy = _yoy(values, lag=1)
        cagr = _cagr(values, periods_per_year=1)
    return {
        "name": name,
        "years": periods,
        "values": values,
        "yoy": yoy,
        "cagr": cagr,
    }


def _shibui_metric_block(name: str, periods: list[str], values: list[float], freq: str = "Y") -> dict:
    """Same output shape as _metric_block, built from already-extracted
    (period_label, value) pairs -- oldest to newest -- instead of a yfinance
    statement Series. Used for Shibui-sourced financials."""
    if freq == "Q":
        yoy = _yoy(values, lag=4)
        cagr = _cagr(values, periods_per_year=4)
    else:
        yoy = _yoy(values, lag=1)
        cagr = _cagr(values, periods_per_year=1)
    return {
        "name": name,
        "years": periods,
        "values": values,
        "yoy": yoy,
        "cagr": cagr,
    }


def _to_pct(v: Optional[float]) -> Optional[float]:
    """Decimal fraction (0.45) → percent (45.0). yfinance returns margins,
    ROE, ROA, payout ratio as decimals."""
    return None if v is None else round(v * 100, 2)


def _normalize_div_yield(v: Optional[float]) -> Optional[float]:
    """yfinance ≥0.2.44 returns dividendYield already as a percent (0.55 for
    AAPL's ~0.55% yield), so we just round it. Pre-0.2.44 was decimal."""
    return None if v is None else round(v, 2)


def _ratios_from_info(info: dict) -> dict[str, Optional[float]]:
    """Pull all the ratios we care about out of a yfinance .info dict and
    normalise their units (percent vs decimal, ratio vs %). The same shape
    is used for the focal stock and for each sector constituent."""
    market_cap = _f(info.get("marketCap"))
    fcf = _f(info.get("freeCashflow"))
    pfcf = None
    if market_cap is not None and fcf is not None and fcf > 0:
        pfcf = round(market_cap / fcf, 2)
    de = _f(info.get("debtToEquity"))
    if de is not None and de > 10:  # yahoo reports as percent (145.6 = 1.456)
        de = round(de / 100, 2)
    # ROIC ≈ NOPAT / invested capital, approximated from summary fields (there
    # is no direct yfinance field) so it can be computed uniformly for the focal
    # stock and every sector peer. EBIT ≈ operating margin × revenue; equity is
    # the book value implied by P/B; a flat 21% tax stands in for NOPAT. The
    # focal stock is refined with a statement-based figure downstream.
    roic = None
    _op_margin = _f(info.get("operatingMargins"))
    _revenue = _f(info.get("totalRevenue"))
    _pb = _f(info.get("priceToBook"))
    _equity_bv = (market_cap / _pb) if (market_cap is not None and _pb and _pb > 0) else None
    if _op_margin is not None and _revenue and _equity_bv is not None:
        _invested = (_f(info.get("totalDebt")) or 0.0) + _equity_bv - (_f(info.get("totalCash")) or 0.0)
        if _invested > 0:
            roic = round(_op_margin * _revenue * (1 - 0.21) / _invested * 100, 2)
    return {
        "pe": _f(info.get("trailingPE")),
        "forward_pe": _f(info.get("forwardPE")),
        "ps": _f(info.get("priceToSalesTrailing12Months")),
        "pb": _f(info.get("priceToBook")),
        "pfcf": pfcf,
        "peg": _f(info.get("trailingPegRatio") or info.get("pegRatio")),
        "ev_ebitda": _f(info.get("enterpriseToEbitda")),
        "ev_revenue": _f(info.get("enterpriseToRevenue")),
        "de": de,
        "current_ratio": _f(info.get("currentRatio")),
        "quick_ratio": _f(info.get("quickRatio")),
        "roe": _to_pct(_f(info.get("returnOnEquity"))),
        "roa": _to_pct(_f(info.get("returnOnAssets"))),
        "roic": roic,
        "gross_margin": _to_pct(_f(info.get("grossMargins"))),
        "operating_margin": _to_pct(_f(info.get("operatingMargins"))),
        "net_margin": _to_pct(_f(info.get("profitMargins"))),
        "div_yield": _normalize_div_yield(_f(info.get("dividendYield"))),
        "payout_ratio": _to_pct(_f(info.get("payoutRatio"))),
    }


def _safe_info(symbol: str) -> dict:
    try:
        return yf.Ticker(symbol).info or {}
    except Exception:
        return {}


def _median_in_bounds(values: list[float], key: str) -> Optional[float]:
    lo, hi = _RATIO_BOUNDS.get(key, (-math.inf, math.inf))
    filtered = [v for v in values if v is not None and lo <= v <= hi]
    if not filtered:
        return None
    return round(median(filtered), 2)


def _sector_avg(sector: Optional[str]) -> dict[str, Any]:
    """Compute median ratios across a basket of representative constituents
    for the given sector. First call per sector hits Yahoo for each
    constituent in parallel (~1-2s); subsequent calls return the cached
    dict instantly."""
    if not sector:
        return {}
    if sector in _SECTOR_CACHE:
        return _SECTOR_CACHE[sector]
    constituents = SECTOR_CONSTITUENTS.get(sector)
    if not constituents:
        _SECTOR_CACHE[sector] = {}
        return {}

    with ThreadPoolExecutor(max_workers=8) as ex:
        infos = list(ex.map(_safe_info, constituents))

    samples = [_ratios_from_info(info) for info in infos]

    keys = [
        "pe", "forward_pe", "ps", "pb", "pfcf", "peg", "ev_ebitda", "ev_revenue",
        "de", "current_ratio", "quick_ratio",
        "roe", "roa", "roic", "gross_margin", "operating_margin", "net_margin",
        "div_yield", "payout_ratio",
    ]
    result: dict[str, Any] = {
        "method": "median",
        "sample_size": sum(1 for info in infos if info),
        "constituents": constituents,
    }
    for k in keys:
        result[k] = _median_in_bounds([s.get(k) for s in samples], k)
    _SECTOR_CACHE[sector] = result
    return result


# ---------------------------------------------------------------------------
# Valuation models (multiples + 2-stage DCF with sensitivity)
# ---------------------------------------------------------------------------

def _two_stage_dcf_ev(
    fcf0: float, growth_pct: float, wacc: float, terminal_g: float, years: int
) -> Optional[float]:
    """Enterprise value from a 2-stage DCF: `years` of `growth_pct` growth,
    then a Gordon-growth terminal value at `terminal_g`. Returns None when
    inputs are degenerate (negative FCF, WACC ≤ terminal growth, etc.).
    Growth is clamped to a sane band so wildly extrapolated CAGRs from a
    short series don't blow up the model."""
    if fcf0 is None or fcf0 <= 0 or wacc <= terminal_g or years <= 0:
        return None
    g = max(min(growth_pct / 100.0, 0.25), -0.10)
    pv = 0.0
    fcf = fcf0
    for t in range(1, years + 1):
        fcf = fcf * (1 + g)
        pv += fcf / (1 + wacc) ** t
    terminal = fcf * (1 + terminal_g) / (wacc - terminal_g)
    pv += terminal / (1 + wacc) ** years
    return pv


def _build_valuation(
    info: dict,
    financials: dict,
    ratios: dict,
    sector_avg: dict,
    fwd_eps_rows: Optional[list[dict]] = None,
) -> dict:
    """Multiple-based and DCF fair-value estimates plus a DCF sensitivity
    grid. Each method ships as a row with fair_value, % upside vs. current
    price, and the inputs that produced it (so the UI can label the
    assumptions). Missing inputs → method is silently dropped."""
    price = _f(info.get("currentPrice") or info.get("regularMarketPrice"))
    shares = _f(info.get("sharesOutstanding"))
    total_debt = _f(info.get("totalDebt")) or 0.0
    cash = _f(info.get("totalCash")) or 0.0
    ebitda = _f(info.get("ebitda"))
    forward_eps = _f(info.get("forwardEps"))
    trailing_eps = _f(info.get("trailingEps"))
    net_debt = total_debt - cash

    def _upside(fv: Optional[float]) -> Optional[float]:
        if fv is None or price is None or price <= 0:
            return None
        return round((fv / price - 1) * 100, 2)

    methods: list[dict] = []

    # --- P/E multiple --------------------------------------------------------
    # We project one fair value per (EPS basis × multiple) combination so the
    # user sees how the implied price moves as growth comes in. EPS bases:
    # next FY (FY+1) and the one after that (FY+2), pulled from analyst
    # estimates. Multiple options: the stock's own trailing P/E and the
    # sector median.
    pe_curr = ratios.get("pe")
    pe_sect = sector_avg.get("pe")

    eps_bases: list[tuple[str, float, Optional[int]]] = []
    rows = fwd_eps_rows or []
    if rows:
        for idx, r in enumerate(rows[:2]):
            eps = r.get("avg")
            yr = r.get("year")
            if eps and eps > 0:
                label = f"FY{yr}E" if yr is not None else ("next FY" if idx == 0 else "FY after next")
                eps_bases.append((label, eps, yr))
    # Fallback when estimates are unavailable: use yfinance's headline EPS.
    if not eps_bases:
        eps_fallback = forward_eps if (forward_eps and forward_eps > 0) else trailing_eps
        if eps_fallback and eps_fallback > 0:
            label = "forward (yf)" if (forward_eps and forward_eps > 0) else "trailing"
            eps_bases.append((label, eps_fallback, None))

    multiples = []
    if pe_curr and pe_curr > 0:
        multiples.append(("current multiple", pe_curr, "current"))
    if pe_sect and pe_sect > 0:
        multiples.append(("sector median", pe_sect, "sector median"))

    for mult_tag, mult_val, mult_src in multiples:
        for eps_label, eps_val, eps_year in eps_bases:
            fv = eps_val * mult_val
            year_tag = f" {eps_year}" if eps_year is not None else ""
            methods.append({
                "method": f"P/E{year_tag} ({mult_tag})",
                "fair_value": round(fv, 2),
                "upside": _upside(fv),
                "inputs": {
                    "eps": round(eps_val, 2),
                    "eps_basis": eps_label,
                    "multiple": round(mult_val, 2),
                    "multiple_source": mult_src,
                },
            })

    # --- EV/EBITDA multiple --------------------------------------------------
    eve_curr = ratios.get("ev_ebitda")
    eve_sect = sector_avg.get("ev_ebitda")
    if ebitda and ebitda > 0 and shares and shares > 0:
        if eve_curr and eve_curr > 0:
            ev = ebitda * eve_curr
            fv = (ev - net_debt) / shares
            methods.append({
                "method": "EV/EBITDA (current multiple)",
                "fair_value": round(fv, 2),
                "upside": _upside(fv),
                "inputs": {
                    "ebitda": round(ebitda, 2),
                    "multiple": round(eve_curr, 2),
                    "multiple_source": "current",
                    "net_debt": round(net_debt, 2),
                },
            })
        if eve_sect and eve_sect > 0:
            ev = ebitda * eve_sect
            fv = (ev - net_debt) / shares
            methods.append({
                "method": "EV/EBITDA (sector median)",
                "fair_value": round(fv, 2),
                "upside": _upside(fv),
                "inputs": {
                    "ebitda": round(ebitda, 2),
                    "multiple": round(eve_sect, 2),
                    "multiple_source": "sector median",
                    "net_debt": round(net_debt, 2),
                },
            })

    # --- 2-stage FCF DCF + sensitivity --------------------------------------
    fcf_block = financials.get("fcf") or {}
    fcf_values = fcf_block.get("values") or []
    fcf_cagr = fcf_block.get("cagr")  # already in percent
    last_fcf = fcf_values[-1] if fcf_values else _f(info.get("freeCashflow"))

    wacc_default = 0.09
    terminal_g_default = 0.025
    years_default = 5

    # Anchor growth on historic FCF CAGR if available, else fall back to a
    # conservative 5%. Clamp to keep the base-case sensible (the per-year
    # clamp inside the DCF still handles extremes).
    if fcf_cagr is not None:
        growth_assumed = max(min(fcf_cagr, 20.0), -5.0)
    else:
        growth_assumed = 5.0

    sensitivity = None
    if last_fcf and last_fcf > 0 and shares and shares > 0:
        ev_base = _two_stage_dcf_ev(
            last_fcf, growth_assumed, wacc_default, terminal_g_default, years_default
        )
        if ev_base is not None:
            fv_base = (ev_base - net_debt) / shares
            methods.append({
                "method": "2-stage FCF DCF",
                "fair_value": round(fv_base, 2),
                "upside": _upside(fv_base),
                "inputs": {
                    "fcf0": round(last_fcf, 2),
                    "growth_pct": round(growth_assumed, 2),
                    "terminal_growth_pct": round(terminal_g_default * 100, 2),
                    "wacc_pct": round(wacc_default * 100, 2),
                    "years": years_default,
                    "net_debt": round(net_debt, 2),
                    "growth_source": "FCF CAGR" if fcf_cagr is not None else "default 5%",
                },
            })

            wacc_axis = [0.06, 0.075, 0.09, 0.105, 0.12]
            term_axis = [0.01, 0.02, 0.025, 0.03, 0.04]
            grid: list[list[Optional[float]]] = []
            for w in wacc_axis:
                row: list[Optional[float]] = []
                for tg in term_axis:
                    ev = _two_stage_dcf_ev(
                        last_fcf, growth_assumed, w, tg, years_default
                    )
                    if ev is None:
                        row.append(None)
                    else:
                        row.append(round((ev - net_debt) / shares, 2))
                grid.append(row)
            sensitivity = {
                "wacc_pct": [round(w * 100, 1) for w in wacc_axis],
                "terminal_growth_pct": [round(t * 100, 1) for t in term_axis],
                "grid": grid,
                "growth_pct": round(growth_assumed, 2),
                "years": years_default,
                "base_wacc_pct": round(wacc_default * 100, 1),
                "base_terminal_pct": round(terminal_g_default * 100, 1),
            }

    return {
        "methods": methods,
        "sensitivity": sensitivity,
        "price": price,
    }


def _fmt_date(v: Any) -> Optional[str]:
    """Coerce assorted date-like values from yfinance into ISO YYYY-MM-DD."""
    if v is None:
        return None
    try:
        if isinstance(v, str):
            return v[:10] if len(v) >= 10 else v
        if hasattr(v, "strftime"):
            return v.strftime("%Y-%m-%d")
        if isinstance(v, (int, float)):
            return datetime.datetime.fromtimestamp(float(v)).strftime("%Y-%m-%d")
    except Exception:
        return None
    return None


def _shibui_ownership_stats(sym: str) -> dict:
    """Best-effort row from Shibui's ownership_stats (insider %, institutional
    %, short interest). Returns {} on any failure (bad ticker, Shibui down,
    no row for this symbol) rather than raising -- supplementary/preferred
    data only, the fundamentals endpoint must keep working without it."""
    if not _SHIBUI_TICKER_RE.match(sym):
        return {}
    sql = (
        "SELECT percent_insiders, percent_institutions, short_percent_float, shares_float"
        " FROM shibui.ownership_stats"
        f" WHERE ticker = '{sym}' LIMIT 1"
    )
    try:
        rows = shibui_client.query(sql, f"Ownership stats for {sym}")
    except shibui_client.ShibuiError:
        return {}
    return rows[0] if rows else {}


def _build_ownership(stock: yf.Ticker, info: dict, sym: str) -> dict:
    """Institutional / insider ownership breakdown.

    Returns headline percentages (insider %, institutional %) plus the top
    institutional holders table. Each holder includes the dollar value, share
    count, and % of shares outstanding so the UI can render a hover-tooltip
    pie chart. Insider/institutional % and short interest (yfinance doesn't
    have the latter at all) prefer Shibui's ownership_stats, falling back to
    yfinance's `info` when Shibui has no row for this ticker."""
    stats = _shibui_ownership_stats(sym)
    # Shibui's percent_insiders/percent_institutions are already percentages
    # (50.0 = 50%); yfinance's info fields are fractions (0.5 = 50%).
    insider_pct = _f(stats.get("percent_insiders"))
    if insider_pct is None:
        insider_pct = _to_pct(_f(info.get("heldPercentInsiders")))
    inst_pct = _f(stats.get("percent_institutions"))
    if inst_pct is None:
        inst_pct = _to_pct(_f(info.get("heldPercentInstitutions")))
    institutions_count = None
    short_percent_float = _f(stats.get("short_percent_float"))
    short_shares_float = _f(stats.get("shares_float"))

    holders: list[dict] = []
    try:
        df = stock.institutional_holders
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                name = row.get("Holder") if hasattr(row, "get") else None
                if not name:
                    continue
                shares = _f(row.get("Shares"))
                value = _f(row.get("Value"))
                pct_out = _f(row.get("pctHeld") if "pctHeld" in row.index else row.get("% Out"))
                # pctHeld arrives as a fraction (0.05); % Out as a percent.
                if pct_out is not None and pct_out <= 1:
                    pct_out = pct_out * 100
                holders.append({
                    "name": str(name),
                    "shares": shares,
                    "value": value,
                    "pct_out": pct_out,
                    "date_reported": _fmt_date(row.get("Date Reported")),
                })
            institutions_count = len(holders)
    except Exception:
        pass

    return {
        "insider_pct": insider_pct,
        "institutional_pct": inst_pct,
        "institutions_count": institutions_count,
        "short_percent_float": short_percent_float,
        "short_shares_float": short_shares_float,
        "top_institutional_holders": holders,
    }


def _shibui_financials_from_rows(rows: list[dict], freq: str) -> dict:
    """Build the same metric-block dict shape _build_financials produces
    (revenue/net_income/eps/fcf/debt/cash/shares_outstanding, plus bonus
    cost_of_revenue/gross_profit/operating_income/ebitda), from Shibui
    fundamentals_yearly/fundamentals_quarterly rows. `rows` need not be
    sorted; this sorts oldest-to-newest itself."""
    ordered = sorted(rows, key=lambda r: (r["year"], r.get("quarter") or 0))

    def _label(r: dict) -> str:
        if freq == "Q":
            return f"Q{r['quarter']} '{r['year'] % 100:02d}"
        return str(r["year"])

    def _block(col: str, name: str, fallback_col: Optional[str] = None) -> dict:
        periods, values = [], []
        for r in ordered:
            v = _f(r.get(col))
            if v is None and fallback_col:
                v = _f(r.get(fallback_col))
            if v is None:
                continue
            periods.append(_label(r))
            values.append(v)
        return _shibui_metric_block(name, periods, values, freq=freq)

    return {
        "revenue": _block("revenue", "Revenue"),
        "cost_of_revenue": _block("cost_of_revenue", "Cost of Revenue"),
        "gross_profit": _block("gross_profit", "Gross Profit"),
        "operating_income": _block("operating_income", "Operating Income"),
        "ebitda": _block("ebitda", "EBITDA"),
        "net_income": _block("net_income", "Net Income"),
        "eps": _block("eps_diluted", "Diluted EPS", fallback_col="eps"),
        "fcf": _block("free_cash_flow", "Free Cash Flow"),
        "debt": _block("debt", "Total Debt"),
        "cash": _block("cash_and_equivalents", "Cash & Equivalents"),
        "shares_outstanding": _block("shares_outstanding", "Shares Outstanding"),
    }


_SHIBUI_STATEMENT_COLUMNS = (
    "revenue, cost_of_revenue, gross_profit, operating_income, ebitda, "
    "net_income, eps, eps_diluted, free_cash_flow, debt, cash_and_equivalents, shares_outstanding"
)
_SHIBUI_ANNUAL_FIELDS = f"year, {_SHIBUI_STATEMENT_COLUMNS}"
_SHIBUI_QUARTERLY_FIELDS = (
    f"year, quarter, {_SHIBUI_STATEMENT_COLUMNS}, "
    "current_ratio, profit_margin, piotroski_f_score, current_assets, inventory, current_liabilities"
)


def _shibui_fundamentals(sym: str) -> Optional[dict]:
    """Best-effort annual/quarterly financials + latest-ratio snapshot from
    Shibui, for get_fundamentals to prefer over yfinance's statement-scraping
    (PLAN.md follow-up: Shibui as primary source, not just a fallback).

    Shibui only covers NYSE/NASDAQ common stock, so this returns None
    (triggering the existing yfinance-only path, unchanged) for anything it
    doesn't have -- foreign listings, delisted tickers, thinly-covered names.
    Presence is gated on the annual query alone: if that's empty, the ticker
    isn't Shibui-covered and we don't bother with the other two calls."""
    if not _SHIBUI_TICKER_RE.match(sym):
        return None

    annual_sql = (
        f"SELECT {_SHIBUI_ANNUAL_FIELDS} FROM shibui.fundamentals_yearly "
        f"WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 5"
    )
    try:
        annual_rows = shibui_client.query(annual_sql, f"Annual financial statements for {sym}")
    except shibui_client.ShibuiError:
        return None
    if not annual_rows:
        return None

    quarterly_sql = (
        f"SELECT {_SHIBUI_QUARTERLY_FIELDS} FROM shibui.fundamentals_quarterly "
        f"WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 8"
    )
    try:
        quarterly_rows = shibui_client.query(quarterly_sql, f"Quarterly financial statements for {sym}")
    except shibui_client.ShibuiError:
        quarterly_rows = []

    ratios_sql = (
        "SELECT"
        f" (SELECT market_cap FROM shibui.valuation WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 1) AS market_cap,"
        f" (SELECT enterprise_value FROM shibui.valuation WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 1) AS enterprise_value,"
        f" (SELECT price_to_book FROM shibui.valuation WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 1) AS price_to_book,"
        f" (SELECT trailing_pe FROM shibui.fundamentals_derived_daily WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 1) AS trailing_pe,"
        f" (SELECT price_to_sales FROM shibui.fundamentals_derived_daily WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 1) AS price_to_sales,"
        f" (SELECT price_to_cash_flow FROM shibui.fundamentals_derived_daily WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 1) AS price_to_cash_flow,"
        f" (SELECT ev_ebitda FROM shibui.fundamentals_derived_daily WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 1) AS ev_ebitda,"
        f" (SELECT dividend_yield FROM shibui.fundamentals_derived_daily WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 1) AS dividend_yield,"
        f" (SELECT payout_ratio FROM shibui.fundamentals_derived_daily WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 1) AS payout_ratio,"
        f" (SELECT return_on_equity_ttm FROM shibui.fundamentals_derived_quarterly WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 1) AS return_on_equity_ttm,"
        f" (SELECT return_on_assets FROM shibui.fundamentals_derived_quarterly WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 1) AS return_on_assets,"
        f" (SELECT return_on_invested_capital FROM shibui.fundamentals_derived_quarterly WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 1) AS return_on_invested_capital,"
        f" (SELECT debt_to_equity FROM shibui.fundamentals_derived_quarterly WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 1) AS debt_to_equity,"
        f" (SELECT gross_margin FROM shibui.fundamentals_derived_quarterly WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 1) AS gross_margin,"
        f" (SELECT operating_margin FROM shibui.fundamentals_derived_quarterly WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 1) AS operating_margin,"
        f" (SELECT profit_margin_ttm FROM shibui.fundamentals_derived_quarterly WHERE ticker = '{sym}' ORDER BY date DESC LIMIT 1) AS profit_margin_ttm"
        " LIMIT 1"
    )
    try:
        ratio_rows = shibui_client.query(ratios_sql, f"Valuation ratio snapshot for {sym}")
    except shibui_client.ShibuiError:
        ratio_rows = []
    ratio_row = ratio_rows[0] if ratio_rows else {}

    current_ratio = quick_ratio = piotroski = None
    if quarterly_rows:
        latest_q = quarterly_rows[0]  # ORDER BY date DESC -> most recent quarter first
        current_ratio = _f(latest_q.get("current_ratio"))
        piotroski = _f(latest_q.get("piotroski_f_score"))
        ca, inventory, cl = (
            _f(latest_q.get("current_assets")),
            _f(latest_q.get("inventory")) or 0.0,
            _f(latest_q.get("current_liabilities")),
        )
        if ca is not None and cl:
            quick_ratio = round((ca - inventory) / cl, 2)

    ratios = {
        "pe": _f(ratio_row.get("trailing_pe")),
        "ps": _f(ratio_row.get("price_to_sales")),
        "pb": _f(ratio_row.get("price_to_book")),
        "pfcf": _f(ratio_row.get("price_to_cash_flow")),
        "ev_ebitda": _f(ratio_row.get("ev_ebitda")),
        "de": _f(ratio_row.get("debt_to_equity")),
        "current_ratio": current_ratio,
        "quick_ratio": quick_ratio,
        "roe": _to_pct(_f(ratio_row.get("return_on_equity_ttm"))),
        "roa": _to_pct(_f(ratio_row.get("return_on_assets"))),
        "roic": _to_pct(_f(ratio_row.get("return_on_invested_capital"))),
        "gross_margin": _to_pct(_f(ratio_row.get("gross_margin"))),
        "operating_margin": _to_pct(_f(ratio_row.get("operating_margin"))),
        "net_margin": _to_pct(_f(ratio_row.get("profit_margin_ttm"))),
        "div_yield": _to_pct(_f(ratio_row.get("dividend_yield"))),
        "payout_ratio": _to_pct(_f(ratio_row.get("payout_ratio"))),
        "piotroski_f_score": piotroski,
    }

    return {
        "annual": _shibui_financials_from_rows(annual_rows, "Y"),
        "quarterly": _shibui_financials_from_rows(quarterly_rows, "Q") if quarterly_rows else {},
        "ratios": ratios,
        "market_cap": _f(ratio_row.get("market_cap")),
        "enterprise_value": _f(ratio_row.get("enterprise_value")),
    }


def _classify_insider_side(transaction: Any, text: Any) -> str:
    """Map yfinance's `Transaction`/`Text` strings to buy/sell/other.

    yfinance returns whatever Yahoo scraped — sometimes a phrase ("Sale at
    price 123"), sometimes the bare Form-4 code ("S", "P"), sometimes a
    description that lives only in `Text` while `Transaction` is empty.
    Check both fields with word-boundary matches so "saletype" doesn't
    falsely register as a sale, and special-case the single-letter codes."""
    import re

    blob = " ".join(str(x) for x in (transaction, text) if x).strip().lower()
    if not blob:
        return "other"

    raw = (str(transaction) or "").strip()
    # Form-4 single-letter codes (case-sensitive on Yahoo's side).
    if raw in ("P", "P-Purchase"):
        return "buy"
    if raw in ("S", "S-Sale"):
        return "sell"

    # Word-boundary matches so "sales-restricted" doesn't trip "sale", but
    # "Sale at price 123" or "Open Market Purchase" both classify correctly.
    if re.search(r"\b(purchase|bought|buy|acqui[rs])", blob):
        return "buy"
    if re.search(r"\b(sale|sold|sell|disposition|dispose)", blob):
        return "sell"
    return "other"


def _build_insider_transactions(stock: yf.Ticker, limit: int = 200) -> list[dict]:
    """Latest insider buys/sells from yfinance. Sorted newest first, capped
    so the UI doesn't have to scroll through years of grants. Best-effort:
    yfinance returns empty for many tickers."""
    out: list[dict] = []
    try:
        df = stock.insider_transactions
    except Exception:
        df = None
    if df is None or getattr(df, "empty", True):
        return out

    try:
        df = df.copy()
        if "Start Date" in df.columns:
            df["__sort"] = pd.to_datetime(df["Start Date"], errors="coerce")
            df = df.sort_values("__sort", ascending=False)
        for _, row in df.head(limit).iterrows():
            shares = _f(row.get("Shares"))
            value = _f(row.get("Value"))
            text = row.get("Text") or row.get("Transaction")
            transaction = row.get("Transaction") or ""
            side = _classify_insider_side(transaction, text)
            out.append({
                "insider": str(row.get("Insider") or "").strip() or None,
                "position": str(row.get("Position") or "").strip() or None,
                "transaction": str(transaction).strip() or None,
                "text": str(text).strip() if text else None,
                "side": side,
                "shares": shares,
                "value": value,
                "ownership": str(row.get("Ownership") or "").strip() or None,
                "date": _fmt_date(row.get("Start Date")),
                "url": row.get("URL") if "URL" in df.columns else None,
            })
    except Exception:
        pass
    return out


# Autocomplete results are cached briefly: users backspace and retype, so the
# same query repeats constantly within a few seconds.
_SEARCH_CACHE: dict[tuple[str, int], tuple[float, list]] = {}
_SEARCH_TTL = 120.0


def _yahoo_search(q: str, safe_limit: int) -> list[dict]:
    """Blocking call into Yahoo's autocomplete; run via market_data.run_bounded."""
    search = getattr(yf, "Search", None)
    if search is not None:
        res = search(q, max_results=safe_limit)
        return list(getattr(res, "quotes", []) or [])
    quotes: list[dict] = []
    lookup = yf.Lookup(q)
    df = getattr(lookup, "all", None)
    if df is not None and not df.empty:
        for sym, row in df.head(safe_limit).iterrows():
            quotes.append({
                "symbol": sym,
                "shortname": row.get("shortName"),
                "longname": row.get("longName"),
                "exchange": row.get("exchange"),
                "quoteType": row.get("quoteType"),
            })
    return quotes


@router.get("/search")
@ttl_cache(_SEARCH_TTL)
def search_tickers(q: str, limit: int = 10):
    """Search for stocks/ETFs by name or symbol. Backed by yfinance's lookup
    API (Yahoo's autocomplete service). Returns up to `limit` matches with
    enough metadata to render a search dropdown."""
    q = (q or "").strip()
    if len(q) < 1:
        return {"query": q, "results": []}
    safe_limit = max(1, min(int(limit or 10), 25))

    cache_key = (q.lower(), safe_limit)
    cached = _SEARCH_CACHE.get(cache_key)
    if cached and time.time() - cached[0] < _SEARCH_TTL:
        quotes = cached[1]
    else:
        # Bound the live Yahoo call so a slow/hung autocomplete can't tie up a
        # worker on every keystroke. Failures (None) are not cached, so the next
        # keystroke retries rather than serving a stale "no matches".
        quotes = market_data.run_bounded(_yahoo_search, q, safe_limit, timeout=5.0, default=None)
        if quotes is None:
            quotes = []
        else:
            _SEARCH_CACHE[cache_key] = (time.time(), quotes)

    results = []
    for r in quotes[:safe_limit]:
        symbol = r.get("symbol") or r.get("ticker")
        if not symbol:
            continue
        results.append({
            "symbol": symbol,
            "name": r.get("longname") or r.get("shortname") or symbol,
            "exchange": r.get("exchDisp") or r.get("exchange"),
            "type": r.get("quoteType") or r.get("typeDisp"),
            "sector": r.get("sectorDisp") or r.get("sector"),
            "industry": r.get("industryDisp") or r.get("industry"),
        })
    return {"query": q, "results": results}


@router.get("/fx/{pair}")
@ttl_cache(_FX_TTL)
def get_fx_rate(pair: str):
    """Return the current exchange rate for a currency pair, e.g. USDCZK."""
    ticker = f"{pair.upper()}=X"
    try:
        info = yf.Ticker(ticker).info
        rate = info.get("regularMarketPrice") or info.get("currentPrice")
        if not rate:
            raise ValueError("No rate in response")
        return {
            "pair": pair.upper(),
            "rate": round(float(rate), 4),
            "base": pair[:3].upper(),
            "quote": pair[3:].upper(),
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"FX rate unavailable for {pair}: {e}")


@router.get("/quote/{ticker}")
@ttl_cache(_QUOTE_TTL)
def get_quote(ticker: str):
    try:
        stock = yf.Ticker(ticker.upper())
        info = stock.info
        price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        if not price:
            raise ValueError("No price data")
        return {
            "ticker": ticker.upper(),
            "name": info.get("shortName", ticker.upper()),
            "price": round(price, 2),
            "change": round(info.get("regularMarketChange", 0), 2),
            "change_percent": round(info.get("regularMarketChangePercent", 0), 2),
            "market_cap": info.get("marketCap"),
            "pe_ratio": info.get("trailingPE"),
            "sector": info.get("sector"),
            "currency": info.get("currency", "USD"),
            "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Could not fetch data for {ticker}: {str(e)}")


@router.get("/history/{ticker}")
@ttl_cache(_HISTORY_TTL)
def get_history(ticker: str, period: str = "1y"):
    try:
        stock = yf.Ticker(ticker.upper())
        hist = stock.history(period=period)
        if hist.empty:
            raise ValueError("No historical data")
        return {
            "ticker": ticker.upper(),
            "data": [
                {"date": str(idx.date()), "close": round(float(row["Close"]), 2)}
                for idx, row in hist.iterrows()
            ],
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/fundamentals/{ticker}")
@ttl_cache(_FUNDAMENTALS_TTL)
def get_fundamentals(ticker: str):
    """Comprehensive fundamentals for the stock-detail modal.

    Returns 5y of revenue / EPS / net income / FCF / debt / cash plus YoY and
    CAGR, valuation & quality ratios, sector-average ratios, and consensus
    analyst data. Each field is best-effort: missing data comes back as null
    so the frontend can render an em-dash."""
    sym = ticker.upper()
    yf_sym = yf_symbol(sym)

    cached = _FUND_CACHE.get(sym)
    if cached and time.time() - cached[0] < _FUND_TTL:
        return cached[1]

    stock = yf.Ticker(yf_sym)
    # Bounded .info (fail-fast gate + hard timeout) so a junk/delisted ticker
    # can't hang the stock-detail request for minutes.
    info = market_data.get_info(sym) or {}

    if not info.get("symbol") and not info.get("shortName") and not info.get("longName"):
        raise HTTPException(status_code=404, detail=f"Unknown ticker {ticker}")

    # ---- Annual statements ------------------------------------------------
    try:
        income = stock.income_stmt
    except Exception:
        income = pd.DataFrame()
    try:
        balance = stock.balance_sheet
    except Exception:
        balance = pd.DataFrame()
    try:
        cashflow = stock.cashflow
    except Exception:
        cashflow = pd.DataFrame()

    # ---- Quarterly statements --------------------------------------------
    try:
        q_income = stock.quarterly_income_stmt
    except Exception:
        q_income = pd.DataFrame()
    try:
        q_balance = stock.quarterly_balance_sheet
    except Exception:
        q_balance = pd.DataFrame()
    try:
        q_cashflow = stock.quarterly_cashflow
    except Exception:
        q_cashflow = pd.DataFrame()

    def _build_fcf_row(cf_df: pd.DataFrame) -> Optional[pd.Series]:
        row = _row(cf_df, "Free Cash Flow")
        if row is not None:
            return row
        ocf = _row(cf_df, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
        capex = _row(cf_df, "Capital Expenditure", "Capital Expenditure Reported")
        if ocf is not None and capex is not None:
            try:
                return ocf.add(capex, fill_value=0)  # capex is reported negative
            except Exception:
                return None
        return None

    def _build_financials(inc_df, bal_df, cf_df, freq: str) -> dict:
        return {
            "revenue": _metric_block("Revenue", _row(inc_df, "Total Revenue", "Operating Revenue"), freq=freq),
            "net_income": _metric_block("Net Income", _row(inc_df, "Net Income", "Net Income Common Stockholders", "Net Income Continuous Operations"), freq=freq),
            "eps": _metric_block("Diluted EPS", _row(inc_df, "Diluted EPS", "Basic EPS"), freq=freq),
            "fcf": _metric_block("Free Cash Flow", _build_fcf_row(cf_df), freq=freq),
            "debt": _metric_block("Total Debt", _row(bal_df, "Total Debt", "Long Term Debt And Capital Lease Obligation", "Long Term Debt"), freq=freq),
            "cash": _metric_block("Cash & Equivalents", _row(
                bal_df,
                "Cash Cash Equivalents And Short Term Investments",
                "Cash And Cash Equivalents",
                "Cash Financial",
            ), freq=freq),
            "shares_outstanding": _metric_block(
                "Shares Outstanding",
                _row(bal_df, "Ordinary Shares Number", "Share Issued", "Common Stock Shares Outstanding"),
                freq=freq,
            ),
        }

    # Prefer Shibui's structured statement data over yfinance's row-name
    # guessing wherever Shibui covers this ticker (NYSE/NASDAQ common stock);
    # `shibui_data` is None for anything it doesn't cover (foreign listings,
    # delisted tickers, etc.), in which case every block below behaves
    # exactly as before. income/balance/cashflow are still fetched above
    # regardless -- they remain the fallback for whatever Shibui doesn't
    # have below (ROIC, quick ratio inputs, margins), and the sole source
    # when shibui_data is None.
    shibui_data = _shibui_fundamentals(sym)
    financials = shibui_data["annual"] if shibui_data else _build_financials(income, balance, cashflow, freq="Y")
    financials_quarterly = (
        shibui_data["quarterly"] if shibui_data and shibui_data.get("quarterly")
        else _build_financials(q_income, q_balance, q_cashflow, freq="Q")
    )

    # ---- TTM (trailing twelve months) for flow metrics -------------------
    # Sum the last four reported quarters so each TTM figure is computed the
    # SAME way as the quarterly/annual bars it sits next to in the chart. Only
    # fall back to yfinance's headline TTM field when we lack four quarters.
    def _ttm_from_quarters(metric_key: str) -> Optional[float]:
        vals = (financials_quarterly.get(metric_key) or {}).get("values") or []
        return round(sum(vals[-4:]), 4) if len(vals) >= 4 else None

    def _ttm_value(metric_key: str, info_key: Optional[str] = None) -> Optional[float]:
        s = _ttm_from_quarters(metric_key)
        if s is not None:
            return s
        return _f(info.get(info_key)) if info_key else None

    ttm = {
        "revenue": _ttm_value("revenue", "totalRevenue"),
        "net_income": _ttm_value("net_income", "netIncomeToCommon"),
        "eps": _ttm_value("eps", "trailingEps"),
        # No info fallback for FCF: yfinance's info.freeCashflow is computed on a
        # different basis than our Operating CF - CapEx bars, so it would not
        # match the chart (e.g. AAPL: 101B from info vs 129B summed from the
        # four quarterly bars actually shown).
        "fcf": _ttm_value("fcf"),
    }

    # ---- Live snapshot ----------------------------------------------------
    price = _f(info.get("currentPrice") or info.get("regularMarketPrice"))
    market_cap = _f(info.get("marketCap"))

    ratios = _ratios_from_info(info)
    if shibui_data:
        # Shibui's own precomputed ratios win over yfinance's `info` fields
        # wherever it has a value; anything it lacks (peg, forward_pe,
        # ev_revenue -- see _shibui_fundamentals) keeps falling through the
        # existing info/statement-based fallback chain below unchanged.
        ratios.update({k: v for k, v in shibui_data["ratios"].items() if v is not None})

    # ---- Fill any missing ratios from the underlying statements ----------
    # yfinance's .info dict can be patchy for smaller-cap or foreign listings;
    # the financial statements we already loaded above are a reliable
    # fallback. These are FY-approximations (not TTM) but better than blank.
    def _last(metric_key):
        m = financials.get(metric_key) or {}
        vals = m.get("values") or []
        return vals[-1] if vals else None

    last_revenue = _last("revenue")
    last_ni = _last("net_income")
    last_eps = _last("eps")
    last_fcf = _last("fcf")
    last_debt = _last("debt")

    if ratios.get("pe") is None and price is not None and last_eps and last_eps > 0:
        ratios["pe"] = round(price / last_eps, 2)
    if ratios.get("ps") is None and market_cap is not None and last_revenue and last_revenue > 0:
        ratios["ps"] = round(market_cap / last_revenue, 2)
    if ratios.get("pfcf") is None and market_cap is not None and last_fcf and last_fcf > 0:
        ratios["pfcf"] = round(market_cap / last_fcf, 2)
    if ratios.get("net_margin") is None and last_revenue and last_ni is not None and last_revenue > 0:
        ratios["net_margin"] = round(last_ni / last_revenue * 100, 2)

    # Balance-sheet derived fallbacks (D/E, ROE, ROA, current/quick ratios).
    try:
        equity_row = _row(balance, "Stockholders Equity", "Total Equity Gross Minority Interest", "Common Stock Equity")
        assets_row = _row(balance, "Total Assets")
        cur_assets_row = _row(balance, "Current Assets", "Total Current Assets")
        cur_liab_row = _row(balance, "Current Liabilities", "Total Current Liabilities")
        inventory_row = _row(balance, "Inventory")

        def _bs_latest(s):
            if s is None or s.empty:
                return None
            for v in s.values:  # newest first
                fv = _f(v)
                if fv is not None:
                    return fv
            return None

        equity = _bs_latest(equity_row)
        assets = _bs_latest(assets_row)
        cur_assets = _bs_latest(cur_assets_row)
        cur_liab = _bs_latest(cur_liab_row)
        inventory = _bs_latest(inventory_row) or 0.0

        if ratios.get("de") is None and last_debt is not None and equity and equity > 0:
            ratios["de"] = round(last_debt / equity, 2)
        if ratios.get("roe") is None and last_ni is not None and equity and equity > 0:
            ratios["roe"] = round(last_ni / equity * 100, 2)
        if ratios.get("roa") is None and last_ni is not None and assets and assets > 0:
            ratios["roa"] = round(last_ni / assets * 100, 2)
        if ratios.get("current_ratio") is None and cur_assets is not None and cur_liab and cur_liab > 0:
            ratios["current_ratio"] = round(cur_assets / cur_liab, 2)
        if ratios.get("quick_ratio") is None and cur_assets is not None and cur_liab and cur_liab > 0:
            ratios["quick_ratio"] = round((cur_assets - inventory) / cur_liab, 2)

        # ROIC = NOPAT / invested capital. Statement-based and more accurate
        # than the P/B-implied approximation in _ratios_from_info, so it
        # overrides that for the focal stock when the inputs are available --
        # but only when Shibui hasn't already supplied a (preferred) value.
        # NOPAT = operating income (EBIT) × (1 − effective tax rate);
        # invested capital = total debt + equity − cash.
        op_row_roic = _row(income, "Operating Income", "Total Operating Income As Reported")
        ebit = _f(op_row_roic.iloc[0]) if op_row_roic is not None and not op_row_roic.empty else None
        tax_row = _row(income, "Tax Provision", "Income Tax Expense")
        pretax_row = _row(income, "Pretax Income", "Income Before Tax")
        tax_rate = 0.21
        if tax_row is not None and not tax_row.empty and pretax_row is not None and not pretax_row.empty:
            tp, pt = _f(tax_row.iloc[0]), _f(pretax_row.iloc[0])
            if tp is not None and pt and pt > 0:
                tax_rate = min(max(tp / pt, 0.0), 0.5)
        invested_cap = (last_debt or 0.0) + (equity or 0.0) - (_f(info.get("totalCash")) or 0.0)
        if ratios.get("roic") is None and ebit is not None and invested_cap > 0:
            ratios["roic"] = round(ebit * (1 - tax_rate) / invested_cap * 100, 2)
    except Exception:
        pass

    # Income statement derived margin fallbacks.
    try:
        gross_row = _row(income, "Gross Profit")
        op_row = _row(income, "Operating Income", "Total Operating Income As Reported")
        # Use the same most-recent year as last_revenue.
        if last_revenue and last_revenue > 0:
            if ratios.get("gross_margin") is None and gross_row is not None:
                gp = _f(gross_row.iloc[0])
                if gp is not None:
                    ratios["gross_margin"] = round(gp / last_revenue * 100, 2)
            if ratios.get("operating_margin") is None and op_row is not None:
                opi = _f(op_row.iloc[0])
                if opi is not None:
                    ratios["operating_margin"] = round(opi / last_revenue * 100, 2)
    except Exception:
        pass

    # EV/EBITDA fallback from enterprise value + EBITDA. Prefer Shibui's own
    # enterprise_value (feeds the ev_revenue fallback below too) when covered.
    ev = None
    if shibui_data:
        ev = shibui_data.get("enterprise_value")
    if ev is None:
        ev = _f(info.get("enterpriseValue"))
    ebitda = _f(info.get("ebitda"))
    if ratios.get("ev_ebitda") is None and ev is not None and ebitda and ebitda > 0:
        ratios["ev_ebitda"] = round(ev / ebitda, 2)
    if ratios.get("ev_revenue") is None and ev is not None and last_revenue and last_revenue > 0:
        ratios["ev_revenue"] = round(ev / last_revenue, 2)

    # ---- Analyst consensus -----------------------------------------------
    analyst: dict[str, Any] = {
        "strong_buy": 0,
        "buy": 0,
        "hold": 0,
        "sell": 0,
        "strong_sell": 0,
        "total": 0,
    }
    try:
        rs = stock.recommendations_summary
        if rs is not None and not rs.empty:
            row = rs.iloc[0]  # most-recent period bucket
            analyst.update({
                "strong_buy": int(row.get("strongBuy", 0) or 0),
                "buy": int(row.get("buy", 0) or 0),
                "hold": int(row.get("hold", 0) or 0),
                "sell": int(row.get("sell", 0) or 0),
                "strong_sell": int(row.get("strongSell", 0) or 0),
            })
            analyst["total"] = (
                analyst["strong_buy"] + analyst["buy"] + analyst["hold"]
                + analyst["sell"] + analyst["strong_sell"]
            )
    except Exception:
        pass

    target_mean = _f(info.get("targetMeanPrice"))
    target_high = _f(info.get("targetHighPrice"))
    target_low = _f(info.get("targetLowPrice"))
    target_median = _f(info.get("targetMedianPrice"))
    upside = None
    if target_mean and price:
        upside = round((target_mean / price - 1) * 100, 2)

    analyst.update({
        "target_mean": target_mean,
        "target_high": target_high,
        "target_low": target_low,
        "target_median": target_median,
        "rating": info.get("recommendationKey"),
        "score": _f(info.get("recommendationMean")),
        "upside": upside,
        "analyst_count": int(info.get("numberOfAnalystOpinions") or 0),
    })

    # ---- Forward estimates (revenue & EPS) -------------------------------
    # yfinance exposes per-period estimates indexed by symbolic period keys:
    # "-1q", "0q", "+1q", "+5q", "0y", "+1y" (sometimes "+2y", "+3y"). We
    # extract just the yearly buckets here so we can plot a forward curve
    # alongside the historical statement bars.
    last_fy_ts = info.get("lastFiscalYearEnd")
    last_fy_year: Optional[int] = None
    if last_fy_ts:
        try:
            last_fy_year = datetime.datetime.fromtimestamp(int(last_fy_ts)).year
        except Exception:
            last_fy_year = None
    if last_fy_year is None:
        # Best-effort fallback: use the latest year from the income statement.
        rev_years = (financials.get("revenue") or {}).get("years") or []
        if rev_years:
            try:
                last_fy_year = int(rev_years[-1])
            except (TypeError, ValueError):
                last_fy_year = None
    if last_fy_year is None:
        last_fy_year = datetime.datetime.now().year - 1

    # Anchor for quarterly periods is the most-recently reported quarter.
    last_q_year: Optional[int] = None
    last_q_quarter: Optional[int] = None
    mrq_ts = info.get("mostRecentQuarter")
    if mrq_ts:
        try:
            dt = datetime.datetime.fromtimestamp(int(mrq_ts))
            last_q_year = dt.year
            last_q_quarter = (dt.month - 1) // 3 + 1
        except Exception:
            pass
    if last_q_year is None:
        # Fallback to the latest label from quarterly financials, e.g. "Q1 '24".
        q_periods = (financials_quarterly.get("revenue") or {}).get("years") or []
        if q_periods:
            try:
                m = q_periods[-1]
                q = int(m[1])
                yy = int(m.split("'")[-1])
                year = 2000 + yy if yy < 70 else 1900 + yy
                last_q_year, last_q_quarter = year, q
            except Exception:
                pass

    def _period_to_year(period: str) -> Optional[int]:
        """Anchor yfinance's symbolic period keys on the last reported FY."""
        if not isinstance(period, str) or not period.endswith("y"):
            return None
        stem = period[:-1]
        try:
            if stem == "0":
                offset = 0
            elif stem.startswith("+"):
                offset = int(stem[1:])
            elif stem.startswith("-"):
                offset = -int(stem[1:])
            else:
                return None
        except ValueError:
            return None
        # "-1y" = last reported FY (matches the last bar in annual financials),
        # "0y" = current FY in progress, "+1y" = next FY, etc.
        return last_fy_year + 1 + offset

    def _period_to_quarter(period: str) -> tuple[Optional[int], Optional[int]]:
        """Map yfinance's quarterly period keys to absolute (year, quarter).
        "-1q" = last reported quarter (matches the last quarterly financials
        bar), "0q" = current quarter in progress, "+1q" = next quarter."""
        if not isinstance(period, str) or not period.endswith("q"):
            return None, None
        if last_q_year is None or last_q_quarter is None:
            return None, None
        stem = period[:-1]
        try:
            if stem == "0":
                offset = 0
            elif stem.startswith("+"):
                offset = int(stem[1:])
            elif stem.startswith("-"):
                offset = -int(stem[1:])
            else:
                return None, None
        except ValueError:
            return None, None
        # offset = -1 → same as last reported (no shift). 0 → next quarter, etc.
        shift = offset + 1
        total = last_q_year * 4 + (last_q_quarter - 1) + shift
        return total // 4, (total % 4) + 1

    def _estimates_block(df: Optional[pd.DataFrame], value_col_year_ago: str) -> list[dict]:
        if df is None or getattr(df, "empty", True):
            return []
        order = ["-1y", "0y", "+1y", "+2y", "+3y", "+4y", "+5y"]
        seen: set[str] = set()
        rows: list[dict] = []

        def _emit(period: str):
            seen.add(period)
            row = df.loc[period]
            rows.append({
                "period": period,
                "year": _period_to_year(period),
                "avg": _f(row.get("avg")),
                "low": _f(row.get("low")),
                "high": _f(row.get("high")),
                "analysts": int(_f(row.get("numberOfAnalysts")) or 0),
                "year_ago": _f(row.get(value_col_year_ago)),
                "growth": _to_pct(_f(row.get("growth"))),
            })

        for period in order:
            if period in df.index and period not in seen:
                _emit(period)
        # Forward-compatible: pick up any other yearly rows yfinance adds.
        for period in df.index:
            if isinstance(period, str) and period.endswith("y") and period not in seen:
                _emit(period)
        return rows

    def _estimates_block_q(df: Optional[pd.DataFrame], value_col_year_ago: str) -> list[dict]:
        if df is None or getattr(df, "empty", True):
            return []
        order = ["-1q", "0q", "+1q", "+2q", "+3q", "+4q", "+5q", "+6q", "+7q", "+8q"]
        seen: set[str] = set()
        rows: list[dict] = []

        def _emit(period: str):
            seen.add(period)
            row = df.loc[period]
            y, q = _period_to_quarter(period)
            rows.append({
                "period": period,
                "year": y,
                "quarter": q,
                "avg": _f(row.get("avg")),
                "low": _f(row.get("low")),
                "high": _f(row.get("high")),
                "analysts": int(_f(row.get("numberOfAnalysts")) or 0),
                "year_ago": _f(row.get(value_col_year_ago)),
                "growth": _to_pct(_f(row.get("growth"))),
            })

        for period in order:
            if period in df.index and period not in seen:
                _emit(period)
        for period in df.index:
            if isinstance(period, str) and period.endswith("q") and period not in seen:
                _emit(period)
        return rows

    try:
        earnings_est_df = stock.earnings_estimate
    except Exception:
        earnings_est_df = None
    try:
        revenue_est_df = stock.revenue_estimate
    except Exception:
        revenue_est_df = None

    analyst_estimates = {
        "eps": _estimates_block(earnings_est_df, "yearAgoEps"),
        "revenue": _estimates_block(revenue_est_df, "yearAgoRevenue"),
    }
    analyst_estimates_quarterly = {
        "eps": _estimates_block_q(earnings_est_df, "yearAgoEps"),
        "revenue": _estimates_block_q(revenue_est_df, "yearAgoRevenue"),
    }

    # ---- Forward P/E split into FY+1 and FY+2 ----------------------------
    # yfinance's `forwardPE` is one number (price / next-FY consensus EPS).
    # We expose both the next FY and the one after so the user can see how
    # the multiple compresses as growth comes in. Pulled from the same
    # `analyst_estimates.eps` list to stay consistent with the forecast bars.
    fwd_eps_rows = sorted(
        [r for r in (analyst_estimates.get("eps") or [])
         if r.get("year") is not None and r["year"] > last_fy_year and r.get("avg") is not None],
        key=lambda r: r["year"],
    )
    fwd_pe_1y = None
    fwd_pe_2y = None
    if price is not None and fwd_eps_rows:
        eps1 = fwd_eps_rows[0]["avg"]
        if eps1 and eps1 > 0:
            fwd_pe_1y = round(price / eps1, 2)
        if len(fwd_eps_rows) >= 2:
            eps2 = fwd_eps_rows[1]["avg"]
            if eps2 and eps2 > 0:
                fwd_pe_2y = round(price / eps2, 2)
    # Prefer the analyst-derived next-FY value; fall back to yfinance's
    # `forwardPE` (already in ratios["forward_pe"]) if estimates are missing.
    if fwd_pe_1y is not None:
        ratios["forward_pe"] = fwd_pe_1y
    ratios["forward_pe_2y"] = fwd_pe_2y
    ratios["forward_pe_fy1_year"] = fwd_eps_rows[0]["year"] if fwd_eps_rows else None
    ratios["forward_pe_fy2_year"] = fwd_eps_rows[1]["year"] if len(fwd_eps_rows) >= 2 else None

    sector = info.get("sector")
    sector_avg = _sector_avg(sector)
    valuation = _build_valuation(info, financials, ratios, sector_avg, fwd_eps_rows)
    ownership = _build_ownership(stock, info, sym)
    insider_transactions = _build_insider_transactions(stock)

    payload = {
        "ticker": sym,
        "name": info.get("longName") or info.get("shortName") or sym,
        "sector": sector,
        "industry": info.get("industry"),
        "country": info.get("country"),
        "currency": info.get("currency", "USD"),
        "exchange": info.get("exchange"),
        "quote_type": info.get("quoteType"),
        "price": price,
        "change": _f(info.get("regularMarketChange")),
        "change_percent": _f(info.get("regularMarketChangePercent")),
        "market_cap": market_cap,
        "enterprise_value": _f(info.get("enterpriseValue")),
        "fifty_two_week_high": _f(info.get("fiftyTwoWeekHigh")),
        "fifty_two_week_low": _f(info.get("fiftyTwoWeekLow")),
        "fifty_day_avg": _f(info.get("fiftyDayAverage")),
        "two_hundred_day_avg": _f(info.get("twoHundredDayAverage")),
        "beta": _f(info.get("beta")),
        "shares_outstanding": _f(info.get("sharesOutstanding")),
        "float_shares": _f(info.get("floatShares")),
        "short_ratio": _f(info.get("shortRatio")),
        "short_pct_float": _to_pct(_f(info.get("shortPercentOfFloat"))),
        "description": info.get("longBusinessSummary"),
        "website": info.get("website"),
        "employees": _f(info.get("fullTimeEmployees")),
        "financials": financials,
        "financials_quarterly": financials_quarterly,
        "ttm": ttm,
        "ratios": ratios,
        "sector_avg": sector_avg,
        "valuation": valuation,
        "analyst": analyst,
        "analyst_estimates": analyst_estimates,
        "analyst_estimates_quarterly": analyst_estimates_quarterly,
        "ownership": ownership,
        "insider_transactions": insider_transactions,
        "fundamentals_source": "shibui" if shibui_data else "yfinance",
    }
    _FUND_CACHE[sym] = (time.time(), payload)
    return payload


_SHIBUI_FINANCIALS_TTL = 3600  # Shibui's fundamentals update only as filings arrive


@router.get("/shibui/financials/{ticker}")
@ttl_cache(_SHIBUI_FINANCIALS_TTL)
def get_shibui_financials(ticker: str, years: int = 5):
    """Annual revenue/earnings/cash-flow trend for `ticker`, sourced from Shibui
    Finance (NYSE/NASDAQ, SEC-filing-derived) via its public MCP server. An
    independent data source alongside the yfinance-backed /fundamentals/{ticker}
    above -- useful when yfinance is missing or disagrees on a name."""
    sym = ticker.upper()
    if not _SHIBUI_TICKER_RE.match(sym):
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {ticker}")
    safe_years = max(1, min(int(years or 5), 20))

    sql = (
        "SELECT date, revenue, cost_of_revenue, gross_profit, operating_income, "
        "ebitda, net_income, free_cash_flow, "
        "ROUND(profit_margin * 100, 2) AS net_margin_pct "
        "FROM shibui.fundamentals_yearly "
        f"WHERE ticker = '{sym}' AND date >= CURRENT_DATE - INTERVAL '{safe_years} years' "
        f"ORDER BY date DESC LIMIT {safe_years}"
    )
    try:
        rows = shibui_client.query(sql, f"Annual revenue and financials trend for {sym}")
    except shibui_client.ShibuiError as e:
        raise HTTPException(status_code=502, detail=f"Shibui query failed for {ticker}: {e}")
    if not rows:
        raise HTTPException(status_code=404, detail=f"No Shibui financials for {ticker}")

    return {"ticker": sym, "source": "shibui", "annual": list(reversed(rows))}


# ---------------------------------------------------------------------------
# Shibui: SEC filings, insider transactions, beneficial ownership (PLAN.md
# phase 1). All of these go through shibui_client.query(), which f-string
# interpolates the ticker/params straight into SQL -- every one MUST run the
# ticker through _SHIBUI_TICKER_RE first.
# ---------------------------------------------------------------------------

_SHIBUI_FILINGS_TTL = 3600 * 3  # new filings land at most a few times/week
_SHIBUI_INSIDERS_TTL = 3600     # Form 4/5 filings arrive within days of the trade
_SHIBUI_OWNERSHIP_TTL = 3600 * 6  # 13D/13G filings are rare, changes are slow

# Curated subset of the ~250 EDGAR form_type codes Shibui tracks -- the rest
# (fund N-1A/N-2 registration forms, exchange-listing admin forms, etc.) don't
# apply to the NYSE/NASDAQ operating companies this app covers. Confirmed
# live against shibui.sec_filings (2026-08-25). Amendments are represented via
# the separate `is_amendment` flag, not a distinct "/A"-suffixed form_type.
_SHIBUI_FORM_TYPES = {
    "10-K", "10-Q", "20-F", "6-K", "8-K", "11-K", "40-F",
    "3", "4", "5",
    "DEF 14A", "DEF 14C", "DEFA14A", "DEFA14C", "DEFM14A", "DEFM14C", "DFAN14A",
    "SC 13G", "SC 13D",
    "424A", "424B1", "424B2", "424B3", "424B4", "424B5", "424B7", "424B8", "425",
    "FWP", "S-1", "S-3", "S-8", "F-1", "F-3", "F-4", "F-6",
    "13F-HR", "13F-NT", "13F-E", "13FCONP",
    "ARS", "D", "CB",
}
_SHIBUI_DEFAULT_FORM_TYPES = "10-K,10-Q,8-K,DEF 14A"


@router.get("/shibui/filings/{ticker}")
@ttl_cache(_SHIBUI_FILINGS_TTL)
def get_shibui_filings(ticker: str, form_types: str = _SHIBUI_DEFAULT_FORM_TYPES, years: int = 2):
    """Recent SEC filings for `ticker` (up to 20 per requested form type),
    sourced from Shibui's EDGAR filing-metadata table. `form_types` is a
    comma-separated list checked against a whitelist -- never forwarded
    to SQL raw."""
    sym = ticker.upper()
    if not _SHIBUI_TICKER_RE.match(sym):
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {ticker}")
    safe_years = max(1, min(int(years or 2), 20))

    requested = [t.strip().upper() for t in (form_types or "").split(",") if t.strip()]
    valid_types = [t for t in requested if t in _SHIBUI_FORM_TYPES]
    if not valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"No valid form_types given. Allowed: {sorted(_SHIBUI_FORM_TYPES)}",
        )
    form_types_sql = ", ".join(f"'{t}'" for t in valid_types)

    sql = (
        "WITH recent AS ("
        "  SELECT sf.filing_date, sf.acceptance_datetime, sf.form_type, sf.raw_form_type,"
        "         sf.is_amendment, sf.report_date, sf.filing_url, sf.items,"
        "         ROW_NUMBER() OVER (PARTITION BY sf.form_type ORDER BY sf.filing_date DESC) AS rn"
        "  FROM shibui.sec_filings sf"
        f"  WHERE sf.cik = (SELECT g.cik FROM shibui.general_info g WHERE g.ticker = '{sym}')"
        f"    AND sf.filing_date >= CURRENT_DATE - INTERVAL '{safe_years} years'"
        f"    AND sf.form_type IN ({form_types_sql})"
        ") "
        "SELECT filing_date, acceptance_datetime, form_type, raw_form_type, is_amendment,"
        "  report_date, items, filing_url "
        "FROM recent WHERE rn <= 20 "
        "ORDER BY form_type, filing_date DESC "
        "LIMIT 200"
    )
    try:
        rows = shibui_client.query(sql, f"Recent SEC filings for {sym}")
    except shibui_client.ShibuiError as e:
        raise HTTPException(status_code=502, detail=f"Shibui query failed for {ticker}: {e}")
    if not rows:
        raise HTTPException(status_code=404, detail=f"No Shibui filings for {ticker}")

    return {"ticker": sym, "source": "shibui", "form_types": valid_types, "years": safe_years, "filings": rows}


_CLUSTER_WINDOW_DAYS = 30
_CLUSTER_MIN_OWNERS = 3


def _is_cluster_candidate(row: dict) -> bool:
    """Open-market common-stock buys only -- excludes 10b5-1 auto-plans,
    estate transfers, and derivative (option/RSU) transactions, which don't
    reflect a discretionary "I think this is cheap" decision."""
    return (
        row.get("tx_code") == "P"
        and not row.get("is_derivative")
        and not row.get("is_auto_plan")
        and not row.get("is_estate")
        and row.get("price_per_share") is not None
        and "common" in (row.get("security_title") or "").lower()
    )


def _detect_cluster_buys(rows: list[dict]) -> list[dict]:
    """Sliding 30-day window over qualifying buys (see _is_cluster_candidate);
    flags stretches where >= 3 distinct insiders (by CIK) bought within the
    same window -- a conviction signal no single transaction shows on its
    own. Adjacent qualifying windows are merged into one cluster event."""
    candidates = sorted(
        (r for r in rows if _is_cluster_candidate(r)),
        key=lambda r: r["tx_date"],
    )
    clusters: list[dict] = []
    active: Optional[dict] = None
    for i, tx in enumerate(candidates):
        tx_date = datetime.date.fromisoformat(str(tx["tx_date"])[:10])
        window = [
            c for c in candidates[: i + 1]
            if (tx_date - datetime.date.fromisoformat(str(c["tx_date"])[:10])).days <= _CLUSTER_WINDOW_DAYS
        ]
        if len({c.get("owner_cik") for c in window}) < _CLUSTER_MIN_OWNERS:
            continue
        buyers = sorted({c.get("owner_canonical_name") for c in window if c.get("owner_canonical_name")})
        if active is not None and (tx_date - active["_last_date"]).days <= _CLUSTER_WINDOW_DAYS:
            active["end"] = tx["tx_date"]
            active["_last_date"] = tx_date
            active["buyers"] = sorted(set(active["buyers"]) | set(buyers))
        else:
            if active is not None:
                active.pop("_last_date")
                clusters.append(active)
            active = {"start": window[0]["tx_date"], "end": tx["tx_date"], "buyers": buyers, "_last_date": tx_date}
    if active is not None:
        active.pop("_last_date")
        clusters.append(active)
    return clusters


@router.get("/shibui/insiders/{ticker}")
@ttl_cache(_SHIBUI_INSIDERS_TTL)
def get_shibui_insiders(ticker: str, months: int = 12):
    """Structured Form 4/5 insider transactions for `ticker` from Shibui --
    replaces the yfinance-scraped, regex-classified insider table
    (_build_insider_transactions below) with the SEC's own transaction codes
    plus noise flags (10b5-1 plans, tax withholding, gifts, estates, average
    pricing). Also flags open-market buy clusters (see _detect_cluster_buys)."""
    sym = ticker.upper()
    if not _SHIBUI_TICKER_RE.match(sym):
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {ticker}")
    safe_months = max(1, min(int(months or 12), 60))

    sql = (
        "SELECT t.tx_date, t.owner_cik, t.owner_canonical_name, t.officer_title, t.tx_code,"
        "  CASE WHEN t.acquired_or_disposed = 'A' THEN 'buy' ELSE 'sell' END AS direction,"
        "  t.shares, t.price_per_share, ROUND(t.shares * t.price_per_share, 0) AS value,"
        "  t.shares_after_tx, t.is_10b5_1, t.is_tax_withholding, t.is_gift, t.is_estate,"
        "  t.is_auto_plan, t.is_avg_price, t.is_derivative, t.security_title,"
        "  t.is_director, t.is_officer, t.is_ten_pct_owner"
        " FROM shibui.insider_transactions t"
        " WHERE NOT t.is_superseded"
        f"  AND t.issuer_ticker = '{sym}'"
        f"  AND t.tx_date >= CURRENT_DATE - INTERVAL '{safe_months} months'"
        " ORDER BY t.tx_date DESC"
        " LIMIT 100"
    )
    try:
        rows = shibui_client.query(sql, f"Insider Form 4/5 transactions for {sym}")
    except shibui_client.ShibuiError as e:
        raise HTTPException(status_code=502, detail=f"Shibui query failed for {ticker}: {e}")
    if not rows:
        raise HTTPException(status_code=404, detail=f"No Shibui insider transactions for {ticker}")

    return {
        "ticker": sym,
        "source": "shibui",
        "months": safe_months,
        "transactions": rows,
        "cluster_buys": _detect_cluster_buys(rows),
    }


@router.get("/shibui/activist-stakes/{ticker}")
@ttl_cache(_SHIBUI_OWNERSHIP_TTL)
def get_shibui_activist_stakes(ticker: str):
    """SC 13D/13G beneficial-ownership filings against `ticker`. 13D signals
    an active/activist stake, 13G a passive position (>5% of float)."""
    sym = ticker.upper()
    if not _SHIBUI_TICKER_RE.match(sym):
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {ticker}")

    sql = (
        "SELECT filer_name, filer_canonical_name, filer_entity_type,"
        "  filer_is_activist, filer_activist_group, schedule_type, filing_date"
        " FROM shibui.beneficial_ownership"
        f" WHERE subject_ticker = '{sym}' AND NOT is_superseded"
        " ORDER BY filing_date DESC"
        " LIMIT 50"
    )
    try:
        rows = shibui_client.query(sql, f"Activist/beneficial ownership stakes in {sym}")
    except shibui_client.ShibuiError as e:
        raise HTTPException(status_code=502, detail=f"Shibui query failed for {ticker}: {e}")
    if not rows:
        raise HTTPException(status_code=404, detail=f"No Shibui beneficial ownership filings for {ticker}")

    return {"ticker": sym, "source": "shibui", "stakes": rows}


@router.get("/shibui/strategic-investors/{ticker}")
@ttl_cache(_SHIBUI_OWNERSHIP_TTL)
def get_shibui_strategic_investors(ticker: str):
    """Beneficial-ownership filers against `ticker` that are themselves a
    publicly traded company (direct corporate stakes, e.g. NVIDIA's 13G in
    CoreWeave) -- a join of beneficial_ownership.filer_cik to general_info.

    Misses stakes routed through a private venture arm (e.g. Alphabet's
    CapitalG holding in Freshworks isn't filed under Alphabet's own CIK) --
    see PLAN.md phase 1e for the verified example and the proposed
    known-VC-arm mapping follow-up. Empty results are the common case (most
    tickers have no such investor), so this returns 200 with an empty list
    rather than 404."""
    sym = ticker.upper()
    if not _SHIBUI_TICKER_RE.match(sym):
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {ticker}")

    sql = (
        "SELECT bo.filer_name, g2.ticker AS filer_ticker, bo.schedule_type, bo.filing_date"
        " FROM shibui.beneficial_ownership bo"
        " INNER JOIN shibui.general_info g2 ON g2.cik = bo.filer_cik"
        f" WHERE bo.subject_ticker = '{sym}' AND NOT bo.is_superseded"
        " ORDER BY bo.filing_date DESC"
        " LIMIT 50"
    )
    try:
        rows = shibui_client.query(sql, f"Corporate strategic investors in {sym}")
    except shibui_client.ShibuiError as e:
        raise HTTPException(status_code=502, detail=f"Shibui query failed for {ticker}: {e}")

    return {"ticker": sym, "source": "shibui", "investors": rows}


# ---------------------------------------------------------------------------
# Alpha Vantage: congressional (STOCK Act) trades (PLAN.md phase 1g). A
# different data source from Shibui -- plain REST, not MCP -- and gated
# behind an optional API key. The frontend must only call this on explicit
# user action (a button), never auto-prefetch: see PLAN.md 1g-i for why
# (25 req/day free-tier quota).
# ---------------------------------------------------------------------------

_POLITICIAN_TRADES_TTL = 3600 * 24


@router.get("/politician-trades/{ticker}")
@ttl_cache(_POLITICIAN_TRADES_TTL)
async def get_politician_trades(ticker: str):
    """Disclosed congressional trades referencing `ticker`, via Alpha
    Vantage's free CONGRESS_TRADES endpoint. 503s with a clear message if
    ALPHA_VANTAGE_API_KEY isn't configured, rather than failing generically.

    Adds a best-effort `is_likely_option` flag per trade -- Alpha Vantage's
    `asset_type_code` alone doesn't reliably distinguish options from stock
    (see PLAN.md 1g-iii); strike/expiry aren't available from this source at
    all, so no "deep ITM" detection is attempted."""
    sym = ticker.upper()
    if not _SHIBUI_TICKER_RE.match(sym):
        raise HTTPException(status_code=400, detail=f"Invalid ticker: {ticker}")
    if not alphavantage_client.ALPHA_VANTAGE_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="ALPHA_VANTAGE_API_KEY is not configured. Get a free key at alphavantage.co "
                   "and set it as an environment variable to enable political trades data.",
        )

    try:
        data = await alphavantage_client.congress_trades(sym)
    except alphavantage_client.AlphaVantageError as e:
        raise HTTPException(status_code=502, detail=f"Alpha Vantage query failed for {ticker}: {e}")

    trades = data.get("trades") or []
    for t in trades:
        t["is_likely_option"] = (
            t.get("asset_type_code") == "OP" and "option" in (t.get("asset_name") or "").lower()
        )

    return {
        "ticker": sym,
        "source": "alpha_vantage",
        "trades": trades,
        "total_count": data.get("trades_total_count", len(trades)),
        "truncated": bool(data.get("trades_truncated", False)),
    }


@router.get("/dividend-growth/{ticker}")
def stock_dividend_growth(ticker: str):
    """Full dividend-growth payload for one ticker (annual series + per-payment
    history for the chart, plus streak/CAGR/YoY/payout)."""
    from dividend_growth import compute_dividend_growth
    return compute_dividend_growth(ticker)


# ---------------------------------------------------------------------------
# Stock screener: filter a list of tickers by fundamental criteria
# ---------------------------------------------------------------------------

from universes import SP500, NASDAQ100, DIVIDEND_ARISTOCRATS, TECH_LARGE

_PRESET_UNIVERSES = {
    "sp500": SP500,
    "nasdaq100": NASDAQ100,
    "dividend_aristocrats": DIVIDEND_ARISTOCRATS,
    "tech_large": TECH_LARGE,
}

# Screener rows change slowly (valuation ratios, not tick prices), so cache them
# for an hour. This is what makes the full-index universes usable: the first
# scan of ~500 names pays the yfinance cost once, then filtering/sorting/
# re-screening is instant until the TTL lapses.
_SCREENER_ROW_TTL = 3600.0
_SCREENER_ROW_CACHE: dict[str, tuple[float, dict]] = {}


def _ticker_screener_row(sym: str) -> dict[str, Any]:
    """One row for the screener: lightweight fundamentals (no statements, no DCF)."""
    cached = _SCREENER_ROW_CACHE.get(sym)
    if cached and time.time() - cached[0] < _SCREENER_ROW_TTL:
        return cached[1]
    # Bounded + cached via market_data (which maps broker symbols itself): a
    # raw yf.Ticker(...).info can hang ~10 minutes on one thin/delisted name,
    # and with full-index universes a single such ticker stalled the whole
    # screener request until every worker finished.
    info = market_data.get_info(sym)
    if not info:
        return {"ticker": sym, "error": "unavailable"}

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    ratios = _ratios_from_info(info)
    sector = _sector_avg(info.get("sector"))

    row = {
        "ticker": sym,
        "name": info.get("shortName") or info.get("longName") or sym,
        "price": _f(price),
        "market_cap": _f(info.get("marketCap")),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "exchange": info.get("exchange"),
        "quote_type": info.get("quoteType"),
        "pe": ratios.get("pe"),
        "forward_pe": ratios.get("forward_pe"),
        "ps": ratios.get("ps"),
        "pb": ratios.get("pb"),
        "pfcf": ratios.get("pfcf"),
        "ev_ebitda": ratios.get("ev_ebitda"),
        "de": ratios.get("de"),
        "current_ratio": ratios.get("current_ratio"),
        "roe": ratios.get("roe"),
        "roa": ratios.get("roa"),
        "gross_margin": ratios.get("gross_margin"),
        "operating_margin": ratios.get("operating_margin"),
        "net_margin": ratios.get("net_margin"),
        "div_yield": ratios.get("div_yield"),
        "payout_ratio": ratios.get("payout_ratio"),
        "beta": _f(info.get("beta")),
        "dividend_rate": _f(info.get("dividendRate")),
        "target_mean": _f(info.get("targetMeanPrice")),
        "rating": info.get("recommendationKey"),
        "analyst_count": _f(info.get("numberOfAnalystOpinions")),
        "fifty_two_week_high": _f(info.get("fiftyTwoWeekHigh")),
        "fifty_two_week_low": _f(info.get("fiftyTwoWeekLow")),
    }
    # Only cache rows that actually resolved a price; an empty info dict is a
    # transient yfinance miss and should be retried on the next scan.
    if row["price"] is not None:
        _SCREENER_ROW_CACHE[sym] = (time.time(), row)
    return row


def _in_range(val: float | None, lo: float | None, hi: float | None) -> bool:
    """Check if val is within [lo, hi] (inclusive). None bounds are ignored."""
    if val is None:
        return False
    if lo is not None and val < lo:
        return False
    if hi is not None and val > hi:
        return False
    return True


@router.get("/screener")
def stock_screener(
    universe: str = "sp500",
    tickers: str = "",
    sector: str = "",
    min_pe: float = None,
    max_pe: float = None,
    min_forward_pe: float = None,
    max_forward_pe: float = None,
    min_pb: float = None,
    max_pb: float = None,
    min_div_yield: float = None,
    max_div_yield: float = None,
    min_market_cap: float = None,
    max_market_cap: float = None,
    min_roe: float = None,
    max_roe: float = None,
    min_net_margin: float = None,
    max_net_margin: float = None,
    min_ps: float = None,
    max_ps: float = None,
    sort_by: str = "market_cap",
    sort_desc: bool = True,
    limit: int = 50,
):
    """Stock screener: filter a universe of tickers by valuation/fundamental criteria.

    Universes (full constituent lists, see universes.py):
      - `sp500`                → S&P 500 (~500 names)
      - `nasdaq100`            → NASDAQ-100 (~100 names)
      - `dividend_aristocrats` → S&P 500 Dividend Aristocrats (~65 names)
      - `tech_large`           → 10 tech megacaps (also the fallback universe)
      - Custom via `tickers` parameter (comma-separated symbols)

    The first scan of a full index is slow (one yfinance lookup per name);
    rows are then cached for an hour so re-filtering is instant.

    Filters: min_pe, max_pe, min_forward_pe, max_forward_pe, min_pb, max_pb,
    min_div_yield, max_div_yield (percent), min_market_cap, max_market_cap,
    min_roe, max_roe (percent), min_net_margin, max_net_margin (percent),
    min_ps, max_ps, sector.

    Results sorted by `sort_by` field, capped at `limit`.
    """
    safe_limit = max(1, min(int(limit or 50), 200))
    tickers_list: list[str] = []

    if tickers:
        tickers_list = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    elif universe in _PRESET_UNIVERSES:
        tickers_list = _PRESET_UNIVERSES[universe]
    else:
        # Fallback to the smallest preset
        tickers_list = _PRESET_UNIVERSES["tech_large"]

    if not tickers_list:
        return {"universe": universe, "results": [], "total": 0, "filters_applied": True}

    tickers_list = list(dict.fromkeys(tickers_list))  # dedupe, keep order

    # Fetch data in parallel
    rows: list[dict] = []
    with ThreadPoolExecutor(max_workers=min(12, len(tickers_list))) as ex:
        futures = {ex.submit(_ticker_screener_row, sym): sym for sym in tickers_list}
        for f in as_completed(futures):
            try:
                row = f.result()
                if "error" not in row:
                    rows.append(row)
            except Exception:
                pass

    # Apply filters
    filtered = []
    for r in rows:
        if sector and (r.get("sector") or "").lower() != sector.lower():
            continue
        if not _in_range(r.get("pe"), min_pe, max_pe):
            continue
        if not _in_range(r.get("forward_pe"), min_forward_pe, max_forward_pe):
            continue
        if not _in_range(r.get("pb"), min_pb, max_pb):
            continue
        if not _in_range(r.get("div_yield"), min_div_yield, max_div_yield):
            continue
        if not _in_range(r.get("market_cap"), min_market_cap, max_market_cap):
            continue
        if not _in_range(r.get("roe"), min_roe, max_roe):
            continue
        if not _in_range(r.get("net_margin"), min_net_margin, max_net_margin):
            continue
        if not _in_range(r.get("ps"), min_ps, max_ps):
            continue
        filtered.append(r)

    # Sort
    reverse = sort_desc
    valid_sort_keys = {
        "ticker", "name", "price", "market_cap", "pe", "forward_pe", "ps", "pb",
        "pfcf", "div_yield", "roe", "net_margin", "beta",
    }
    sort_key = sort_by if sort_by in valid_sort_keys else "market_cap"
    filtered.sort(key=lambda r: (r.get(sort_key) or 0) if isinstance(r.get(sort_key), (int, float)) else str(r.get(sort_key, "")), reverse=reverse)

    results = filtered[:safe_limit]
    return {
        "universe": universe if not tickers else "custom",
        "results": results,
        "total": len(filtered),
        "filters_applied": bool(sector or min_pe is not None or max_pe is not None),
    }
