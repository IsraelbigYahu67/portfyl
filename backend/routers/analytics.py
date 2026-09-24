from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import date, timedelta
from collections import defaultdict
from uuid import UUID
import yfinance as yf
import pandas as pd
import numpy as np

from database import get_db
from entitlements import require_capability
from models import Portfolio, Transaction, Benchmark, BenchmarkComponent
from cash_ledger import (TRADE_TYPES, POSITION_TYPES, EXTERNAL_FLOW_TYPES,
                         has_external_cashflows, cash_balance_by_currency, signed_cash)
from routers.portfolios import require_portfolio
from ticker_map import yf_symbol
from transaction_ordering import chronological_key
from routers.portfolio import _xirr, _live_to_usd, _received_dividend_in_currency
import market_data

router = APIRouter(prefix="/analytics", tags=["analytics"])

RISK_FREE_RATE = 0.05
TRADING_DAYS = 252


def _load_close_panel(yf_tickers: list[str], start: date) -> pd.DataFrame:
    """Download as-traded close prices for the given Yahoo symbols. Returns a
    DataFrame indexed by trading day, columns = yf_tickers (or fewer if Yahoo
    has no data for some). Dividends are represented by cash transactions, so
    dividend-adjusted closes would double-count them. Yahoo's Close still
    adjusts for splits with auto_adjust=False; undo that adjustment because
    broker transactions hold the share count applicable on each historical day.
    Empty DataFrame on failure."""
    if not yf_tickers:
        return pd.DataFrame()
    try:
        raw = yf.download(
            yf_tickers,
            start=start.isoformat(),
            auto_adjust=False,
            actions=True,
            progress=False,
        )
    except Exception:
        return pd.DataFrame()
    if raw is None or raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        closes = raw["Close"] if "Close" in raw.columns.get_level_values(0) else pd.DataFrame()
        splits = raw["Stock Splits"] if "Stock Splits" in raw.columns.get_level_values(0) else pd.DataFrame()
        if isinstance(closes, pd.Series):
            closes = closes.to_frame(name=yf_tickers[0])
    elif len(yf_tickers) == 1:
        closes = raw[["Close"]].rename(columns={"Close": yf_tickers[0]}) if "Close" in raw.columns else pd.DataFrame()
        splits = raw[["Stock Splits"]].rename(columns={"Stock Splits": yf_tickers[0]}) if "Stock Splits" in raw.columns else pd.DataFrame()
    else:
        closes = raw["Close"] if "Close" in raw.columns else raw
        splits = pd.DataFrame()
    if closes is None or closes.empty:
        return pd.DataFrame()
    closes = closes.copy()
    for ticker in closes.columns:
        if ticker not in splits:
            continue
        ratios = splits[ticker].reindex(closes.index).fillna(0.0).replace(0.0, 1.0)
        # A split changes the units from its effective date onwards. Only
        # later splits must be undone for a particular historical close.
        future_factor = ratios.iloc[::-1].cumprod().iloc[::-1].shift(-1, fill_value=1.0)
        closes[ticker] = closes[ticker] * future_factor
    return closes.ffill().dropna(how="all")


def _ticker_currencies(originals: list[str]) -> dict[str, str]:
    """Resolve each broker ticker to its listing currency via yfinance. Falls
    back to 'USD'. Notably, LSE tickers may report 'GBp' (pence) — we keep that
    distinction so prices can be divided by 100 later."""
    out: dict[str, str] = {}
    infos = market_data.get_infos(originals)  # one bounded, concurrent batch
    for orig in originals:
        ccy = (infos.get(orig, {}).get("currency") or "USD").strip()
        out[orig] = ccy if ccy else "USD"
    return out


def _ccy_to_usd(ccy: str) -> float:
    """Live conversion factor from a listing currency to USD, applying the
    pence→pound divisor for LSE 'GBp' quotes. Returns 1.0 for USD/unknown."""
    if ccy == "GBp":
        return _live_to_usd("GBP") / 100.0
    return _live_to_usd(ccy or "USD")


def _fx_to_usd_series(currencies: set[str], start: date, index: pd.Index) -> dict[str, pd.Series]:
    """Return a per-currency FX series reindexed onto `index`. GBp shares the
    GBP series (with a pence-to-pound divisor applied later at the price-use
    site, not here)."""
    out: dict[str, pd.Series] = {}
    for ccy in currencies:
        c = "GBP" if ccy == "GBp" else ccy.upper()
        if c == "USD":
            continue
        try:
            raw = yf.download(f"{c}USD=X", start=start.isoformat(), auto_adjust=True, progress=False)
            if raw is None or raw.empty:
                continue
            col = raw["Close"]
            if isinstance(col, pd.DataFrame):
                col = col.squeeze()
            out[ccy] = col.reindex(index, method="ffill").ffill()
        except Exception:
            pass
    return out


def _price_to_usd(price: float, ccy: str, fx_series: dict[str, pd.Series], idx) -> float:
    """Convert one close price to USD using the given FX series at idx. Returns
    NaN if the FX is missing for a non-USD ccy (caller should skip)."""
    if not pd.notna(price):
        return float("nan")
    divisor = 100.0 if ccy == "GBp" else 1.0
    if ccy == "USD" or ccy == "":
        return float(price) / divisor
    s = fx_series.get(ccy)
    if s is None:
        return float("nan")
    try:
        rate = float(s.loc[idx])
    except Exception:
        return float("nan")
    if not pd.notna(rate) or rate <= 0:
        return float("nan")
    return (float(price) / divisor) * rate


def _usd_series_to_display(
    V: pd.Series,
    C: pd.Series,
    start_date: date,
    display_currency: str,
) -> tuple[pd.Series, pd.Series]:
    """Convert aligned USD value/flow series to the dashboard display currency."""
    if display_currency.upper() != "CZK":
        return V, C
    czk_usd = _fx_to_usd_series({"CZK"}, start_date, V.index).get("CZK")
    if czk_usd is None:
        fallback = _ccy_to_usd("CZK")
        if fallback <= 0:
            return V, C
        factor = pd.Series(1.0 / fallback, index=V.index)
    else:
        factor = 1.0 / czk_usd.replace(0, np.nan)
    factor = factor.reindex(V.index, method="ffill").ffill().bfill()
    return V * factor, C * factor


def _get_transactions(db: Session, portfolio: Portfolio):
    rows = (
        db.query(Transaction)
        .filter(
            Transaction.portfolio_id == portfolio.id,
            Transaction.workspace_id == portfolio.workspace_id,
        )
        .order_by(Transaction.date)
        .all()
    )
    # Single choke point for position analytics: cash-only rows never reach
    # holdings/tax math, while corporate actions must remain present so share
    # counts and FIFO cost bases survive stock splits.
    return [t for t in rows if t.type in POSITION_TYPES and t.ticker]


# Czech Income Tax Act §4: capital gain on a security is exempt if the holding
# period exceeds 3 years (1095 days). Cap of CZK 40,000,000/year on the time
# test introduced 2024-01-01. Separately, the "value test" exempts gains for any
# tax year where total gross sale proceeds ≤ CZK 100,000.
CZ_TIME_TEST_DAYS = 365 * 3 + 1
CZ_VALUE_TEST_LIMIT_CZK = 100_000
CZ_TIME_TEST_CAP_CZK = 40_000_000
CZ_TIME_TEST_CAP_FROM_YEAR = 2024
LOT_EPSILON = 1e-8


def _position_events(transactions: list) -> list:
    """Stable accounting order, including paired split legs on the same date."""
    return [
        txn for _, txn in sorted(
            enumerate(transactions),
            key=lambda pair: (*chronological_key(pair[1]), pair[0]),
        )
    ]


def _split_ratios(transactions: list) -> dict[tuple, float]:
    """Return new/old share ratios for complete T212 split pairs."""
    legs: dict[tuple, dict[str, float]] = defaultdict(lambda: {"open": 0.0, "close": 0.0})
    for txn in transactions:
        if txn.type not in {"split_open", "split_close"} or not txn.ticker:
            continue
        key = (txn.ticker, txn.date)
        leg = "open" if txn.type == "split_open" else "close"
        legs[key][leg] += abs(float(txn.shares or 0.0))
    return {
        key: values["open"] / values["close"]
        for key, values in legs.items()
        if values["open"] > 0 and values["close"] > 0
    }


def _apply_split_to_lots(ticker_lots: list[dict], ratio: float) -> None:
    """Change lot quantity/per-share basis while preserving total cost basis."""
    if ratio <= 0:
        return
    for lot in ticker_lots:
        lot["shares"] *= ratio
        lot["remaining"] *= ratio
        lot["price"] /= ratio


def _consume_fifo(ticker_lots: list[dict], shares: float) -> list[tuple[dict, float]]:
    matched: list[tuple[dict, float]] = []
    remaining = float(shares or 0.0)
    if abs(remaining) <= LOT_EPSILON:
        return matched
    for lot in ticker_lots:
        if remaining <= LOT_EPSILON:
            break
        if lot["remaining"] <= LOT_EPSILON:
            lot["remaining"] = 0.0
            continue
        sold = min(remaining, lot["remaining"])
        if sold <= LOT_EPSILON:
            continue
        lot["remaining"] -= sold
        remaining -= sold
        if abs(lot["remaining"]) <= LOT_EPSILON:
            lot["remaining"] = 0.0
        if abs(remaining) <= LOT_EPSILON:
            remaining = 0.0
        matched.append((lot, sold))
    return matched


def _new_lot(txn) -> dict:
    return {
        "date": txn.date,
        "shares": float(txn.shares or 0.0),
        "price": float(txn.price or 0.0),
        "remaining": float(txn.shares or 0.0),
        "fx_to_czk": txn.fx_to_czk,  # FX captured at acquisition
        "currency": txn.currency,    # native currency of the buy price
    }


def _build_lot_queue(transactions: list) -> dict[str, list[dict]]:
    """Build final open FIFO lots after buys, sells and stock splits."""
    lots: dict[str, list[dict]] = defaultdict(list)
    ratios = _split_ratios(transactions)
    applied_splits: set[tuple] = set()
    for txn in _position_events(transactions):
        if txn.type == "buy":
            lots[txn.ticker].append(_new_lot(txn))
        elif txn.type == "split_open":
            key = (txn.ticker, txn.date)
            if key in ratios and key not in applied_splits:
                _apply_split_to_lots(lots[txn.ticker], ratios[key])
                applied_splits.add(key)
        elif txn.type == "sell":
            _consume_fifo(lots.get(txn.ticker, []), txn.shares)
    return lots


def _to_czk(amount: float, fx: float | None) -> float | None:
    """Return the amount in CZK, or None if FX is unknown so callers can flag
    the data gap rather than silently emitting wrong totals."""
    if fx is None:
        return None
    return amount * fx


def _add_years(d: date, years: int) -> date:
    """Add `years` calendar years to d. Handles Feb 29 by falling to Feb 28."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def _compute_capital_gains(transactions: list, tax_year: int | None = None):
    lots: dict[str, list[dict]] = defaultdict(list)
    ratios = _split_ratios(transactions)
    applied_splits: set[tuple] = set()
    gains = []

    for txn in _position_events(transactions):
        if txn.type == "buy":
            lots[txn.ticker].append(_new_lot(txn))
            continue
        if txn.type == "split_open":
            key = (txn.ticker, txn.date)
            if key in ratios and key not in applied_splits:
                _apply_split_to_lots(lots[txn.ticker], ratios[key])
                applied_splits.add(key)
            continue
        if txn.type != "sell":
            continue
        sell_fx = txn.fx_to_czk  # may be None

        # Always consume historical sells so a year-filtered report starts from
        # the right remaining lots; only emission is scoped to the selected year.
        matched = _consume_fifo(lots.get(txn.ticker, []), txn.shares)
        if tax_year and txn.date.year != tax_year:
            continue

        for lot, sold_from_lot in matched:

            cost_basis = sold_from_lot * lot["price"]
            proceeds = sold_from_lot * txn.price
            gain = proceeds - cost_basis
            holding_days = (txn.date - lot["date"]).days
            is_long_term = holding_days > 365
            cz_exempt_time_test = holding_days > CZ_TIME_TEST_DAYS

            buy_fx = lot.get("fx_to_czk")
            cost_basis_czk = _to_czk(cost_basis, buy_fx)
            proceeds_czk = _to_czk(proceeds, sell_fx)
            gain_czk = (
                proceeds_czk - cost_basis_czk
                if (proceeds_czk is not None and cost_basis_czk is not None)
                else None
            )

            gains.append({
                "ticker": txn.ticker,
                "sell_date": txn.date.isoformat(),
                "buy_date": lot["date"].isoformat(),
                "shares": round(sold_from_lot, 8),
                "cost_basis": round(cost_basis, 6),
                "proceeds": round(proceeds, 6),
                "gain": round(gain, 6),
                "gain_pct": None if abs(cost_basis) < 0.005 else round(gain / cost_basis * 100, 2),
                "holding_days": holding_days,
                "term": "long" if is_long_term else "short",
                # Czech tax fields — booleans are unconditional; CZK amounts may
                # be None if any FX rate is missing.
                "cz_exempt_time_test": cz_exempt_time_test,
                "cz_exempt_date": _add_years(lot["date"], 3).isoformat(),
                "cost_basis_czk": round(cost_basis_czk, 6) if cost_basis_czk is not None else None,
                "proceeds_czk": round(proceeds_czk, 6) if proceeds_czk is not None else None,
                "gain_czk": round(gain_czk, 6) if gain_czk is not None else None,
                "_gain_raw": gain,
                "_cost_basis_czk_raw": cost_basis_czk,
                "_proceeds_czk_raw": proceeds_czk,
                "_gain_czk_raw": gain_czk,
            })

    return gains


def _compute_czech_tax_by_year(gains: list) -> list[dict]:
    """Per-tax-year Czech exemption summary (value test, time test, 40M cap).
    Operates on the already-filtered `gains` produced by _compute_capital_gains
    so the same FIFO match feeds both views."""
    by_year: dict[int, list[dict]] = defaultdict(list)
    for g in gains:
        by_year[int(g["sell_date"][:4])].append(g)

    out: list[dict] = []
    for yr in sorted(by_year):
        ygains = by_year[yr]
        proceeds_czk_vals = [
            g.get("_proceeds_czk_raw", g["proceeds_czk"])
            for g in ygains
            if g["proceeds_czk"] is not None
        ]
        gain_czk_vals = [
            g.get("_gain_czk_raw", g["gain_czk"])
            for g in ygains
            if g["gain_czk"] is not None
        ]
        incomplete = (
            len(proceeds_czk_vals) != len(ygains) or len(gain_czk_vals) != len(ygains)
        )

        gross_proceeds_czk = sum(proceeds_czk_vals)
        value_test_passed = gross_proceeds_czk <= CZ_VALUE_TEST_LIMIT_CZK and not incomplete

        time_test_exempt_gain_czk = sum(
            g.get("_gain_czk_raw", g["gain_czk"]) for g in ygains
            if g["cz_exempt_time_test"] and g["gain_czk"] is not None
        )
        taxable_gain_czk_pre_cap = sum(
            g.get("_gain_czk_raw", g["gain_czk"]) for g in ygains
            if not g["cz_exempt_time_test"] and g["gain_czk"] is not None
        )

        cap_active = yr >= CZ_TIME_TEST_CAP_FROM_YEAR
        cap_excess = (
            max(0.0, time_test_exempt_gain_czk - CZ_TIME_TEST_CAP_CZK)
            if cap_active else 0.0
        )
        exempt_via_time_test = time_test_exempt_gain_czk - cap_excess

        if value_test_passed:
            # Below the value-test threshold: everything is exempt, time test
            # and the 40M cap don't enter into it.
            exempt_total = time_test_exempt_gain_czk + max(0.0, taxable_gain_czk_pre_cap)
            taxable_total = 0.0
        else:
            exempt_total = exempt_via_time_test
            taxable_total = taxable_gain_czk_pre_cap + cap_excess

        out.append({
            "tax_year": yr,
            "gross_proceeds_czk": round(gross_proceeds_czk, 2),
            "value_test_threshold_czk": CZ_VALUE_TEST_LIMIT_CZK,
            "value_test_passed": value_test_passed,
            "time_test_exempt_gain_czk": round(time_test_exempt_gain_czk, 2),
            "time_test_cap_active": cap_active,
            "time_test_cap_czk": CZ_TIME_TEST_CAP_CZK if cap_active else None,
            "time_test_cap_excess_czk": round(cap_excess, 2),
            "taxable_gain_czk_pre_cap": round(taxable_gain_czk_pre_cap, 2),
            "exempt_total_czk": round(exempt_total, 2),
            "taxable_total_czk": round(taxable_total, 2),
            "incomplete_fx": incomplete,
            "trades": len(ygains),
        })
    return out


def tax_report(
    year: int | None = None,
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    transactions = _get_transactions(db, portfolio)
    if not transactions:
        return {"gains": [], "summary": {}, "dividend_income": [], "available_years": []}

    all_years = sorted({t.date.year for t in transactions})
    gains = _compute_capital_gains(transactions, year)

    short_gains = [g for g in gains if g["term"] == "short"]
    long_gains = [g for g in gains if g["term"] == "long"]

    total_short = sum(g.get("_gain_raw", g["gain"]) for g in short_gains)
    total_long = sum(g.get("_gain_raw", g["gain"]) for g in long_gains)

    # CZK totals from the per-transaction FX captured at trade time (not today's
    # live rate). None when any contributing leg is missing its FX snapshot.
    short_gain_czk = [
        g.get("_gain_czk_raw", g["gain_czk"])
        for g in short_gains
        if g["gain_czk"] is not None
    ]
    long_gain_czk = [
        g.get("_gain_czk_raw", g["gain_czk"])
        for g in long_gains
        if g["gain_czk"] is not None
    ]
    total_short_czk = sum(short_gain_czk)
    total_long_czk = sum(long_gain_czk)
    realized_fx_complete = (
        len(short_gain_czk) == len(short_gains) and len(long_gain_czk) == len(long_gains)
    )

    dividend_txns = [t for t in transactions if t.type == "dividend"]
    if year:
        dividend_txns = [t for t in dividend_txns if t.date.year == year]

    div_by_ticker: dict[str, float] = defaultdict(float)
    div_czk_by_ticker: dict[str, float] = defaultdict(float)
    div_fx_complete = True
    for t in dividend_txns:
        paid_ccy, paid_amount = signed_cash(t)
        div_by_ticker[t.ticker] += _received_dividend_in_currency(t, None, {})
        if paid_ccy == "CZK":
            div_czk_by_ticker[t.ticker] += paid_amount
        elif paid_ccy == (t.currency or "USD").upper() and t.fx_to_czk is not None:
            div_czk_by_ticker[t.ticker] += paid_amount * t.fx_to_czk
        else:
            div_fx_complete = False

    dividend_income = [
        {
            "ticker": ticker,
            "amount": round(amount, 2),
            "amount_czk": round(div_czk_by_ticker[ticker], 2) if ticker in div_czk_by_ticker else None,
        }
        for ticker, amount in sorted(div_by_ticker.items(), key=lambda x: -x[1])
    ]
    total_dividends = sum(d["amount"] for d in dividend_income)
    total_dividends_czk = sum(div_czk_by_ticker.values())

    unrealized = _compute_unrealized_gains(transactions)

    # Czech §4 exemption summary. When a specific year is requested we scope to
    # that year; for "all years" we return a per-year breakdown.
    czech_tax = _compute_czech_tax_by_year(gains)

    response_gains = [
        {key: value for key, value in gain.items() if not key.startswith("_")}
        for gain in gains
    ]

    return {
        "year": year or "all",
        "available_years": all_years,
        "gains": response_gains,
        "summary": {
            "total_realized": round(total_short + total_long, 2),
            "short_term_gains": round(total_short, 2),
            "long_term_gains": round(total_long, 2),
            "short_term_count": len(short_gains),
            "long_term_count": len(long_gains),
            "total_trades": len(gains),
            "total_dividends": round(total_dividends, 2),
            # CZK figures use trade-time FX; prefer these for Czech filing.
            "total_realized_czk": round(total_short_czk + total_long_czk, 2),
            "short_term_gains_czk": round(total_short_czk, 2),
            "long_term_gains_czk": round(total_long_czk, 2),
            "total_dividends_czk": round(total_dividends_czk, 2),
            "fx_complete": realized_fx_complete and div_fx_complete,
        },
        "dividend_income": dividend_income,
        "unrealized": unrealized,
        "czech_tax": czech_tax,
    }


def _compute_unrealized_gains(transactions: list):
    lots = _build_lot_queue(transactions)

    unrealized = []
    tickers_with_lots = {
        ticker: ticker_lots
        for ticker, ticker_lots in lots.items()
        if any(lot["remaining"] > LOT_EPSILON for lot in ticker_lots)
    }
    infos = market_data.get_infos(list(tickers_with_lots.keys()))  # bounded batch

    for ticker, ticker_lots in tickers_with_lots.items():
        info = infos.get(ticker, {})
        current_price, _, listing_ccy = market_data.quote(info, ticker)
        price_to_usd = _ccy_to_usd(listing_ccy)

        for lot in ticker_lots:
            if lot["remaining"] <= LOT_EPSILON:
                continue
            # Normalize both legs to USD so a non-USD listing (incl. GBp pence)
            # can't mix native cost basis with a differently-denominated market
            # price and produce nonsensical unrealized gains.
            cost_basis = lot["remaining"] * lot["price"] * _ccy_to_usd(lot.get("currency") or "USD")
            market_value = lot["remaining"] * current_price * price_to_usd
            gain = market_value - cost_basis
            holding_days = (date.today() - lot["date"]).days

            exempt_date = _add_years(lot["date"], 3)
            days_to_exemption = (exempt_date - date.today()).days
            unrealized.append({
                "ticker": ticker,
                "buy_date": lot["date"].isoformat(),
                "shares": round(lot["remaining"], 8),
                "cost_basis": round(cost_basis, 6),
                "market_value": round(market_value, 6),
                "unrealized_gain": round(gain, 6),
                "gain_pct": None if abs(cost_basis) < 0.005 else round(gain / cost_basis * 100, 2),
                "holding_days": holding_days,
                "term": "long" if holding_days > 365 else "short",
                "cz_exempt_date": exempt_date.isoformat(),
                "cz_days_to_exemption": max(0, days_to_exemption),
                "cz_exempt_time_test": days_to_exemption <= 0,
            })

    # Sort by closest-to-exemption first so the user sees what's about to flip
    # tax-free at the top. Already-exempt lots fall to the bottom.
    unrealized.sort(key=lambda u: (
        0 if not u["cz_exempt_time_test"] else 1,
        u["cz_days_to_exemption"] if not u["cz_exempt_time_test"] else 0,
    ))
    return unrealized


PERIOD_DAYS = {"7d": 7, "1m": 30, "3m": 90, "6m": 180, "1y": 365, "2y": 730}


def _resolve_window(transactions: list, period: str) -> tuple[date, date] | None:
    """Returns (start_date_for_data_pull, window_start_for_trimming) or None."""
    first_txn_date = min(t.date for t in transactions)
    key = period.lower()
    if key == "all":
        window_start = first_txn_date
    elif key == "mtd":
        window_start = date.today().replace(day=1)
    elif key == "ytd":
        window_start = date.today().replace(month=1, day=1)
    else:
        window_start = date.today() - timedelta(days=PERIOD_DAYS.get(key, 365))
    # Pull a couple extra days so we have a valid V_{t-1} baseline for the
    # first transaction inside the requested window.
    start_date = max(first_txn_date - timedelta(days=5), window_start - timedelta(days=5))
    return start_date, window_start


def _build_value_cashflow_series(
    transactions: list,
    start_date: date,
    display_currency: str = "USD",
):
    """Construct V (net worth) and C (external cashflow) series
    over every trading day on/after start_date. Returns (V, C, closes_index)
    or (None, None, None) if there's no usable price data.

    V uses actual closes and the cash ledger, so dividends, interest and lending
    income raise net worth while fees reduce it. None of those events enter C.

    When the portfolio has deposit/withdrawal rows (has_external_cashflows),
    C switches to deposit(+)/withdrawal(-) and V additionally folds in the
    running cash balance, so V represents whole-portfolio net worth rather
    than holdings-only -- buys/sells become internal reallocation between
    cash and positions instead of external cashflow. Portfolios with zero
    deposit/withdrawal rows take the untouched original path (else branch)."""
    transactions = sorted(transactions, key=chronological_key)
    held_tickers = sorted({t.ticker for t in transactions if t.type in POSITION_TYPES and t.ticker})
    if not held_tickers:
        return None, None, None

    yf_to_orig: dict[str, str] = {}
    for t in held_tickers:
        yf_to_orig.setdefault(yf_symbol(t), t)
    yf_tickers = list(yf_to_orig.keys())

    closes = _load_close_panel(yf_tickers, start_date)
    if closes.empty:
        return None, None, None
    closes = closes.rename(columns=yf_to_orig)

    ticker_ccy = _ticker_currencies(held_tickers)
    fx_series = _fx_to_usd_series(set(ticker_ccy.values()), start_date, closes.index)

    txns_by_date: dict[date, list] = defaultdict(list)
    for t in transactions:
        txns_by_date[t.date].append(t)

    # Pre-seed holdings from txns strictly before the first trading day so day-1
    # has a real V_0 baseline (not cashflow that zeroes out the denominator).
    first_trading_day = closes.index[0].date()
    holdings: dict[str, float] = {}
    for d_key in [d for d in list(txns_by_date.keys()) if d < first_trading_day]:
        for txn in txns_by_date.pop(d_key):
            if txn.type == "buy":
                holdings[txn.ticker] = holdings.get(txn.ticker, 0) + txn.shares
            elif txn.type == "sell":
                prev = holdings.get(txn.ticker, 0)
                holdings[txn.ticker] = max(0.0, prev - min(txn.shares, prev))
            elif txn.type == "split_close":
                holdings[txn.ticker] = max(0.0, holdings.get(txn.ticker, 0) - txn.shares)
            elif txn.type == "split_open":
                holdings[txn.ticker] = holdings.get(txn.ticker, 0) + txn.shares

    if has_external_cashflows(transactions):
        # Cash-aware path: deposits(+)/withdrawals(-) are the external
        # cashflow; buys/sells are internal reallocation (cash <-> positions)
        # so they no longer feed C. V additionally folds in the running cash
        # balance (from cash_balance_by_currency, walked forward over the
        # date index) so it reflects whole-portfolio net worth. Actual closes
        # are used, therefore dividend settlement belongs in cash and is not
        # double-counted in the position price.
        # Settlement currencies: signed_cash routes trades through their
        # cash_currency (CZK for T212), so build the FX set from it, not from
        # the trade's price currency.
        cash_ccys = {signed_cash(t)[0] for t in transactions}
        extra_ccys = cash_ccys - set(fx_series.keys()) - {"USD"}
        cash_fx_series = _fx_to_usd_series(extra_ccys, start_date, closes.index) if extra_ccys else {}
        combined_fx = {**fx_series, **cash_fx_series}

        pre_window_cash = [t for t in transactions if t.date < first_trading_day]
        cash_txns_to_date: list = list(pre_window_cash)

        values: list[float] = []
        cashflows: list[float] = []
        for date_idx in closes.index:
            curr_date = date_idx.date()
            cf_today = 0.0
            for d_key in [d for d in list(txns_by_date.keys()) if d <= curr_date]:
                for txn in txns_by_date.pop(d_key):
                    if txn.type == "buy":
                        holdings[txn.ticker] = holdings.get(txn.ticker, 0) + txn.shares
                    elif txn.type == "sell":
                        prev = holdings.get(txn.ticker, 0)
                        sold = min(txn.shares, prev)
                        holdings[txn.ticker] = max(0.0, prev - sold)
                    elif txn.type == "split_close":
                        holdings[txn.ticker] = max(
                            0.0, holdings.get(txn.ticker, 0) - txn.shares
                        )
                    elif txn.type == "split_open":
                        holdings[txn.ticker] = holdings.get(txn.ticker, 0) + txn.shares

                    if txn.type in EXTERNAL_FLOW_TYPES:
                        # deposit/cashback add external money; withdrawal/card
                        # debit remove it.
                        amt_usd = _price_to_usd(txn.amount, (txn.currency or "USD").upper(), combined_fx, date_idx)
                        if pd.notna(amt_usd):
                            cf_today += amt_usd if txn.type in ("deposit", "cashback") else -amt_usd
                    # Every transaction participates in the cash ledger. Split
                    # rows contribute zero; income/fees/dividends move V but not C.
                    cash_txns_to_date.append(txn)

            v = 0.0
            for tk, sh in holdings.items():
                if sh <= 0 or tk not in closes.columns:
                    continue
                try:
                    p = float(closes.loc[date_idx, tk])
                except Exception:
                    continue
                p_usd = _price_to_usd(p, ticker_ccy.get(tk, "USD"), fx_series, date_idx)
                if pd.notna(p_usd):
                    v += sh * p_usd

            balances = cash_balance_by_currency(cash_txns_to_date)
            for ccy, bal in balances.items():
                bal_usd = _price_to_usd(bal, ccy, combined_fx, date_idx)
                if pd.notna(bal_usd):
                    v += bal_usd

            values.append(v)
            cashflows.append(cf_today)

        V = pd.Series(values, index=closes.index)
        C = pd.Series(cashflows, index=closes.index)
        V, C = _usd_series_to_display(V, C, start_date, display_currency)
        return V, C, closes.index
    else:
        values: list[float] = []
        cashflows: list[float] = []
        for date_idx in closes.index:
            curr_date = date_idx.date()
            cf_today = 0.0
            for d_key in [d for d in list(txns_by_date.keys()) if d <= curr_date]:
                for txn in txns_by_date.pop(d_key):
                    ccy = ticker_ccy.get(txn.ticker, "USD")
                    if txn.type == "buy":
                        holdings[txn.ticker] = holdings.get(txn.ticker, 0) + txn.shares
                        px_usd = _price_to_usd(txn.price, ccy, fx_series, date_idx)
                        if pd.notna(px_usd):
                            cf_today += txn.shares * px_usd
                    elif txn.type == "sell":
                        prev = holdings.get(txn.ticker, 0)
                        sold = min(txn.shares, prev)
                        holdings[txn.ticker] = max(0.0, prev - sold)
                        px_usd = _price_to_usd(txn.price, ccy, fx_series, date_idx)
                        if pd.notna(px_usd):
                            cf_today -= sold * px_usd

            v = 0.0
            for tk, sh in holdings.items():
                if sh <= 0 or tk not in closes.columns:
                    continue
                try:
                    p = float(closes.loc[date_idx, tk])
                except Exception:
                    continue
                p_usd = _price_to_usd(p, ticker_ccy.get(tk, "USD"), fx_series, date_idx)
                if pd.notna(p_usd):
                    v += sh * p_usd

            values.append(v)
            cashflows.append(cf_today)

        V = pd.Series(values, index=closes.index)
        C = pd.Series(cashflows, index=closes.index)
        V, C = _usd_series_to_display(V, C, start_date, display_currency)
        return V, C, closes.index


def _modified_dietz_daily_returns(V: pd.Series, C: pd.Series, window_start: date) -> pd.Series:
    """Trim V/C to the requested window and compute daily Modified-Dietz returns.
    r_t = (V_t - V_{t-1} - C_t) / (V_{t-1} + 0.5*C_t)
    Returns an empty Series if there's not enough data."""
    first_held = V[V > 0].first_valid_index()
    if first_held is None:
        return pd.Series(dtype=float)
    effective_start = max(first_held, pd.Timestamp(window_start))
    if effective_start not in V.index:
        idx_after = V.index[V.index >= effective_start]
        if len(idx_after) == 0:
            return pd.Series(dtype=float)
        effective_start = idx_after[0]

    V = V.loc[effective_start:]
    C = C.loc[effective_start:]
    if len(V) < 2:
        return pd.Series(dtype=float)

    out_vals: list[float] = []
    out_idx: list = []
    for i in range(1, len(V)):
        prev = V.iloc[i - 1]
        curr = V.iloc[i]
        cf = C.iloc[i]
        denom = prev + 0.5 * cf
        if denom <= 0:
            continue
        r = (curr - prev - cf) / denom
        if not np.isfinite(r):
            continue
        out_vals.append(r)
        out_idx.append(V.index[i])

    return pd.Series(out_vals, index=out_idx)


def _ticker_daily_returns(ticker: str, start_date: date, target_index) -> pd.Series:
    """Daily simple returns for a single yfinance symbol, reindexed onto target_index."""
    try:
        raw = yf.download(ticker, start=start_date.isoformat(), auto_adjust=True, progress=False)
    except Exception:
        return pd.Series(dtype=float)
    if raw is None or raw.empty or "Close" not in raw.columns:
        return pd.Series(dtype=float)
    c = raw["Close"]
    if isinstance(c, pd.DataFrame):
        c = c.squeeze()
    c = c.reindex(target_index, method="ffill").ffill()
    return c.pct_change()


def _basket_daily_returns(components: list[dict], start_date: date, target_index) -> pd.Series:
    """Weighted daily returns of a basket. Components: [{ticker, weight}].
    Missing tickers are dropped and remaining weights renormalised so a partial
    failure produces a best-effort series rather than zeroing out the metric."""
    if not components:
        return pd.Series(dtype=float)
    yf_to_orig: dict[str, str] = {}
    for c in components:
        yf_to_orig.setdefault(yf_symbol(c["ticker"]), c["ticker"])
    closes = _load_close_panel(list(yf_to_orig.keys()), start_date)
    if closes.empty:
        return pd.Series(dtype=float)
    closes = closes.rename(columns=yf_to_orig)
    closes = closes.reindex(target_index, method="ffill").ffill()
    returns = closes.pct_change()
    weights = {c["ticker"]: float(c["weight"]) for c in components}
    available = [t for t in returns.columns if t in weights]
    if not available:
        return pd.Series(dtype=float)
    w = pd.Series({t: weights[t] for t in available})
    if w.sum() <= 0:
        return pd.Series(dtype=float)
    w = w / w.sum()
    return returns[available].mul(w, axis=1).sum(axis=1, min_count=1)


def _benchmark_daily_returns(db: Session, bench: Benchmark | None, start_date: date, target_index) -> pd.Series:
    """Dispatch on benchmark.kind. Empty series if bench is None."""
    if bench is None:
        return pd.Series(dtype=float)
    if bench.kind == "ticker" and bench.ticker:
        return _ticker_daily_returns(bench.ticker, start_date, target_index)
    if bench.kind == "basket":
        # `workspace_id IS NULL` (shared presets) can't be matched with `== None`
        # in SQL, so branch on it explicitly rather than risk silently returning
        # zero rows for a preset basket.
        workspace_filter = (
            BenchmarkComponent.workspace_id.is_(None)
            if bench.workspace_id is None
            else BenchmarkComponent.workspace_id == bench.workspace_id
        )
        rows = db.query(BenchmarkComponent).filter(
            BenchmarkComponent.benchmark_id == bench.id,
            workspace_filter,
        ).all()
        components = [{"ticker": r.ticker, "weight": r.weight} for r in rows]
        return _basket_daily_returns(components, start_date, target_index)
    return pd.Series(dtype=float)


def resolve_benchmark(db: Session, portfolio: Portfolio, benchmark_id: UUID | None) -> Benchmark | None:
    """Pick the benchmark to use: explicit public id (own workspace+portfolio,
    or a shared preset) → portfolio default → S&P preset → None.

    A benchmark_id that doesn't resolve inside this call's own tenant falls
    through to the default lookup exactly like an unknown id always has --
    it is never treated as a hard 404, just ignored."""
    if benchmark_id is not None:
        b = db.query(Benchmark).filter(Benchmark.public_id == benchmark_id).first()
        if b and (
            b.is_preset
            or (b.workspace_id == portfolio.workspace_id and b.portfolio_id == portfolio.id)
        ):
            return b
    b = (
        db.query(Benchmark)
        .filter(
            Benchmark.workspace_id == portfolio.workspace_id,
            Benchmark.portfolio_id == portfolio.id,
            Benchmark.is_default.is_(True),
        )
        .first()
    )
    if b:
        return b
    return (
        db.query(Benchmark)
        .filter(Benchmark.is_preset.is_(True), Benchmark.ticker == "^GSPC")
        .first()
    )


def _benchmark_compare_metrics(port: pd.Series, bench: pd.Series) -> dict:
    """Active-return / capture / beta / alpha metrics for two aligned daily-return series."""
    aligned = pd.DataFrame({"p": port, "b": bench}).dropna()
    if len(aligned) < 10:
        return {}
    active = aligned["p"] - aligned["b"]
    te = float(active.std(ddof=1) * np.sqrt(TRADING_DAYS))
    info_ratio = float((active.mean() * TRADING_DAYS) / te) if te > 0 else 0.0

    var_b = aligned["b"].var()
    beta = float(aligned["p"].cov(aligned["b"]) / var_b) if var_b > 0 else None
    p_ann = float(aligned["p"].mean() * TRADING_DAYS)
    b_ann = float(aligned["b"].mean() * TRADING_DAYS)
    alpha = (p_ann - (RISK_FREE_RATE + beta * (b_ann - RISK_FREE_RATE))) if beta is not None else None
    corr = float(aligned["p"].corr(aligned["b"]))

    up = aligned[aligned["b"] > 0]
    dn = aligned[aligned["b"] < 0]
    up_capture = float(up["p"].mean() / up["b"].mean()) if len(up) > 0 and up["b"].mean() != 0 else None
    down_capture = float(dn["p"].mean() / dn["b"].mean()) if len(dn) > 0 and dn["b"].mean() != 0 else None

    return {
        "tracking_error": round(te * 100, 2),
        "information_ratio": round(info_ratio, 3),
        "beta": round(beta, 3) if beta is not None else None,
        "alpha": round(alpha * 100, 2) if alpha is not None else None,
        "correlation": round(corr, 3) if np.isfinite(corr) else None,
        "up_capture": round(up_capture, 3) if up_capture is not None else None,
        "down_capture": round(down_capture, 3) if down_capture is not None else None,
        "observations": len(aligned),
    }


@router.get("/risk-metrics", dependencies=[Depends(require_capability("portfolio_analytics"))])
def risk_metrics(
    period: str = "1y",
    benchmark_id: UUID | None = None,
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    """Time-weighted return based risk metrics, plus benchmark-relative metrics
    against the chosen (or portfolio-default) benchmark."""
    transactions = (
        db.query(Transaction)
        .filter(
            Transaction.portfolio_id == portfolio.id,
            Transaction.workspace_id == portfolio.workspace_id,
        )
        .order_by(Transaction.date)
        .all()
    )
    if not transactions:
        return {}

    window = _resolve_window(transactions, period)
    if window is None:
        return {}
    start_date, window_start = window

    V, C, closes_index = _build_value_cashflow_series(transactions, start_date)
    if V is None:
        return {}

    bench = resolve_benchmark(db, portfolio, benchmark_id)
    bench_daily_full = _benchmark_daily_returns(db, bench, start_date, closes_index)

    daily_returns = _modified_dietz_daily_returns(V, C, window_start)
    if len(daily_returns) < 2:
        return {}

    daily_rf = RISK_FREE_RATE / TRADING_DAYS

    ann_return = float(daily_returns.mean() * TRADING_DAYS)
    ann_vol = float(daily_returns.std(ddof=1) * np.sqrt(TRADING_DAYS))
    sharpe = float((ann_return - RISK_FREE_RATE) / ann_vol) if ann_vol > 0 else 0

    downside = daily_returns[daily_returns < daily_rf]
    downside_std = float(downside.std(ddof=1) * np.sqrt(TRADING_DAYS)) if len(downside) > 1 else 0
    sortino = float((ann_return - RISK_FREE_RATE) / downside_std) if downside_std > 0 else 0

    cumulative = (1 + daily_returns).cumprod()
    rolling_max = cumulative.cummax()
    drawdowns = (cumulative - rolling_max) / rolling_max
    max_dd = float(drawdowns.min()) if len(drawdowns) else 0.0
    if max_dd < 0:
        max_dd_end_idx = drawdowns.idxmin()
        max_dd_start_idx = cumulative.loc[:max_dd_end_idx].idxmax()
        recovery = cumulative.loc[max_dd_end_idx:]
        recovery = recovery[recovery >= cumulative.loc[max_dd_start_idx]]
        max_dd_recovery = str(recovery.index[0].date()) if len(recovery) > 0 else None
        max_dd_start_str = str(max_dd_start_idx.date())
        max_dd_end_str = str(max_dd_end_idx.date())
    else:
        max_dd = 0.0
        max_dd_start_str = None
        max_dd_end_str = None
        max_dd_recovery = None

    current_dd = float(drawdowns.iloc[-1]) if len(drawdowns) else 0.0
    positive_days = int((daily_returns > 0).sum())
    negative_days = int((daily_returns < 0).sum())
    best_day = float(daily_returns.max())
    worst_day = float(daily_returns.min())
    total_return = float(cumulative.iloc[-1] - 1)

    span_days = (daily_returns.index[-1] - daily_returns.index[0]).days
    years = max(span_days / 365.25, 1e-9)
    cagr = ((cumulative.iloc[-1]) ** (1 / years) - 1) if cumulative.iloc[-1] > 0 else -1.0

    bench_metrics = _benchmark_compare_metrics(daily_returns, bench_daily_full) if not bench_daily_full.empty else {}

    lifetime = _lifetime_money_weighted(transactions, V)

    return {
        "period": period,
        "trading_days": len(daily_returns),
        "total_return": round(total_return * 100, 2),
        "annualized_return": round(ann_return * 100, 2),
        "cagr": round(cagr * 100, 2),
        "annualized_volatility": round(ann_vol * 100, 2),
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "max_drawdown": round(max_dd * 100, 2),
        "max_drawdown_start": max_dd_start_str,
        "max_drawdown_end": max_dd_end_str,
        "max_drawdown_recovery": max_dd_recovery,
        "current_drawdown": round(current_dd * 100, 2),
        "beta": bench_metrics.get("beta"),
        "alpha": bench_metrics.get("alpha"),
        "tracking_error": bench_metrics.get("tracking_error"),
        "information_ratio": bench_metrics.get("information_ratio"),
        "up_capture": bench_metrics.get("up_capture"),
        "down_capture": bench_metrics.get("down_capture"),
        "benchmark": {"id": str(bench.public_id), "name": bench.name, "kind": bench.kind} if bench else None,
        "positive_days": positive_days,
        "negative_days": negative_days,
        "win_rate": round(positive_days / (positive_days + negative_days) * 100, 1) if (positive_days + negative_days) > 0 else 0,
        "best_day": round(best_day * 100, 2),
        "worst_day": round(worst_day * 100, 2),
        "risk_free_rate": RISK_FREE_RATE,
        "method": "modified-dietz-twr",
        "lifetime": lifetime,
    }


def _lifetime_money_weighted(transactions, V_usd: pd.Series) -> dict:
    """Lifetime money-weighted metrics in USD: simple ROI (matches dashboard
    semantics) and annualized XIRR. Uses live FX for converting historical
    transactions to USD — acceptable for the per-position % since amounts
    cancel; for portfolios where this is mostly USD already, it's exact.

    When the portfolio has deposit/withdrawal rows (has_external_cashflows),
    xirr_flows are built from deposits(-)/withdrawals(+) instead of buys/
    sells/dividends — buys/sells become internal reallocation (mirrors
    _build_value_cashflow_series) — and the XIRR terminal flow uses ending
    NET WORTH (V_usd already folds in the cash balance in this case).
    Portfolios with zero deposit/withdrawal rows take the untouched original
    path (else branch)."""
    shares_open: dict[str, float] = {}
    cost_open: dict[str, float] = {}
    cum_buys_cost_usd = 0.0
    realized_pnl_usd = 0.0
    dividends_usd = 0.0
    xirr_flows: list[tuple] = []

    if has_external_cashflows(transactions):
        for txn in sorted(transactions, key=chronological_key):
            if txn.type in EXTERNAL_FLOW_TYPES:
                ccy = (txn.currency or "USD").upper()
                rate = _live_to_usd("GBP" if ccy == "GBp" else ccy)
                amt_usd = float(txn.amount or 0.0) * rate
                # Money entering the portfolio (deposit/cashback) is a negative
                # XIRR flow; money leaving (withdrawal/card debit) positive.
                if txn.type in ("deposit", "cashback"):
                    xirr_flows.append((txn.date, -amt_usd))
                else:
                    xirr_flows.append((txn.date, +amt_usd))
                continue
            if txn.shares is None or txn.shares <= 0:
                continue
            ccy = (txn.currency or "USD").upper()
            rate = _live_to_usd("GBP" if ccy in ("GBP", "GBP") or ccy == "GBp" else ccy)
            price_usd = txn.price * rate
            amt_usd = txn.shares * price_usd
            if txn.type == "buy":
                shares_open[txn.ticker] = shares_open.get(txn.ticker, 0.0) + txn.shares
                cost_open[txn.ticker] = cost_open.get(txn.ticker, 0.0) + amt_usd
                cum_buys_cost_usd += amt_usd
                # NOTE: buys no longer feed xirr_flows here -- internal
                # reallocation (cash -> position), not an external cashflow.
            elif txn.type == "sell":
                prev = shares_open.get(txn.ticker, 0.0)
                sold = min(txn.shares, prev)
                if sold > 0:
                    avg = cost_open[txn.ticker] / prev
                    proceeds_matched = sold * price_usd
                    realized_pnl_usd += proceeds_matched - sold * avg
                    shares_open[txn.ticker] = prev - sold
                    cost_open[txn.ticker] = max(0.0, cost_open[txn.ticker] - sold * avg)
                    # NOTE: sells no longer feed xirr_flows here either --
                    # internal reallocation (position -> cash).
            elif txn.type == "dividend":
                paid_ccy, paid_amount = signed_cash(txn)
                dividends_usd += paid_amount * _live_to_usd("GBP" if paid_ccy == "GBp" else paid_ccy)
                # NOTE: excluded from xirr_flows -- auto_adjust already prices
                # the dividend into V_usd, so adding the cash again here would
                # double-count it (same reasoning as _build_value_cashflow_series).
    else:
        for txn in sorted(transactions, key=chronological_key):
            ccy = (txn.currency or "USD").upper()
            rate = _live_to_usd("GBP" if ccy in ("GBP", "GBP") or ccy == "GBp" else ccy)
            if txn.shares <= 0:
                continue
            price_usd = txn.price * rate
            amt_usd = txn.shares * price_usd
            if txn.type == "buy":
                shares_open[txn.ticker] = shares_open.get(txn.ticker, 0.0) + txn.shares
                cost_open[txn.ticker] = cost_open.get(txn.ticker, 0.0) + amt_usd
                cum_buys_cost_usd += amt_usd
                xirr_flows.append((txn.date, -amt_usd))
            elif txn.type == "sell":
                prev = shares_open.get(txn.ticker, 0.0)
                # Match only against shares we know the cost basis for. Unmatched
                # portions (sells without a prior buy in this DB) are skipped from
                # every lifetime metric — we don't know their cost basis, so
                # counting them as profit would inflate both Simple ROI and XIRR.
                sold = min(txn.shares, prev)
                if sold > 0:
                    avg = cost_open[txn.ticker] / prev
                    proceeds_matched = sold * price_usd
                    realized_pnl_usd += proceeds_matched - sold * avg
                    shares_open[txn.ticker] = prev - sold
                    cost_open[txn.ticker] = max(0.0, cost_open[txn.ticker] - sold * avg)
                    xirr_flows.append((txn.date, +proceeds_matched))
            elif txn.type == "dividend":
                paid_ccy, paid_amount = signed_cash(txn)
                received_usd = paid_amount * _live_to_usd("GBP" if paid_ccy == "GBp" else paid_ccy)
                dividends_usd += received_usd
                xirr_flows.append((txn.date, +received_usd))

    net_worth_usd = float(V_usd.iloc[-1]) if len(V_usd) else 0.0
    if has_external_cashflows(transactions):
        # current_value/unrealized_pnl/simple_roi stay positions-only (matches
        # get_summary's total_value-vs-net_worth split) -- back the still-idle
        # cash balance out of V_usd's net worth so it isn't double counted as
        # "profit". The XIRR terminal flow below uses the full net worth,
        # since deposits/withdrawals are flows against the WHOLE portfolio.
        cash_bal_native = cash_balance_by_currency([t for t in transactions if t.type != "dividend"])
        cash_usd = 0.0
        for ccy, bal in cash_bal_native.items():
            c = (ccy or "USD").upper()
            cash_usd += bal * _live_to_usd("GBP" if c == "GBp" else c)
        current_value_usd = net_worth_usd - cash_usd
    else:
        current_value_usd = net_worth_usd

    total_invested_usd = sum(cost_open.values())
    unrealized_pnl_usd = current_value_usd - total_invested_usd
    net_profit_usd = unrealized_pnl_usd + realized_pnl_usd + dividends_usd
    simple_roi = (net_profit_usd / cum_buys_cost_usd) if cum_buys_cost_usd > 0 else 0.0

    xirr_ending_value = net_worth_usd if has_external_cashflows(transactions) else current_value_usd
    if xirr_ending_value > 0:
        xirr_flows.append((date.today(), xirr_ending_value))
    xirr_rate = _xirr(xirr_flows) if len(xirr_flows) >= 2 else 0.0

    return {
        "currency": "USD",
        "current_value": round(current_value_usd, 2),
        "total_invested": round(total_invested_usd, 2),
        "cum_buys_cost": round(cum_buys_cost_usd, 2),
        "realized_pnl": round(realized_pnl_usd, 2),
        "dividends": round(dividends_usd, 2),
        "unrealized_pnl": round(unrealized_pnl_usd, 2),
        "net_profit": round(net_profit_usd, 2),
        "simple_roi": round(simple_roi * 100, 2),
        "xirr": round(xirr_rate * 100, 2),
    }


_QUOTE_TYPE_LABEL = {
    "EQUITY": "Stocks",
    "ETF": "ETFs",
    "MUTUALFUND": "Funds",
    "INDEX": "Indices",
    "CRYPTOCURRENCY": "Crypto",
    "CURRENCY": "FX",
    "BOND": "Bonds",
}


def _classify_sector(info: dict) -> str:
    """yfinance only fills `sector` for individual stocks. For ETFs/funds we
    fall back to the fund category (e.g. 'Large Growth', 'Technology') so the
    pie chart doesn't bucket every ETF into 'Unknown'."""
    sector = info.get("sector")
    if sector:
        return sector
    quote_type = (info.get("quoteType") or "").upper()
    if quote_type in ("ETF", "MUTUALFUND"):
        category = info.get("category") or info.get("legalType")
        if category:
            return category
        return "Diversified ETF"
    if quote_type == "CRYPTOCURRENCY":
        return "Crypto"
    return "Other"


def _classify_country(info: dict) -> str:
    country = info.get("country")
    if country:
        return country
    # ETFs often expose region/domicile rather than country.
    region = info.get("region") or info.get("market")
    if region:
        return region
    return "Other"


def _weighted(totals: dict) -> list:
    """[{name, value, weight%}] sorted desc; weight base is the dict's own sum."""
    denom = sum(totals.values())
    return [
        {"name": name, "value": round(value, 2),
         "weight": round(value / denom * 100, 2) if denom > 0 else 0}
        for name, value in sorted(totals.items(), key=lambda x: -x[1])
    ]


def _allocation_totals(db: Session, portfolio: Portfolio, display_ccy: str) -> dict:
    """Raw (un-weighted) per-dimension market-value totals for one portfolio,
    in `display_ccy` ('CZK' or 'USD'). Cash is folded into sectors/asset_types/
    currencies (never countries), matching get_summary's Cash figure. This is the
    shared core behind both /sector-breakdown and the cross-portfolio Overview."""
    from fx import folded_cash_display
    from models import CashInterestRate

    pid = portfolio.id
    workspace_id = portfolio.workspace_id

    in_czk = display_ccy.upper() == "CZK"
    display_ccy = "CZK" if in_czk else "USD"

    transactions = _get_transactions(db, portfolio)

    # Cash bucket: guarded on external cashflows (deposit/withdrawal rows), same
    # semantic as get_summary -- a portfolio with none does not get a Cash bucket
    # at all (holdings-only breakdown, weights sum to 100 as before the cash
    # model). When gated on, the value is FOLDED (balance + accrued interest),
    # matching get_summary's "Cash" figure so the allocation bucket and the
    # dashboard headline agree. Sourced from the FULL transaction list (all
    # types) -- _get_transactions above is trade-guarded (TRADE_TYPES + ticker)
    # and excludes cash rows entirely, so it cannot be reused for this.
    txns = db.query(Transaction).filter(
        Transaction.portfolio_id == pid, Transaction.workspace_id == workspace_id,
    ).all()
    # Per-currency cash (native ccy -> display value) feeds the FX-exposure
    # ("currencies") dimension. Same external-cashflow gate as the folded Cash
    # bucket; the sum of these equals cash_total so the dimensions reconcile.
    cash_by_ccy_display: dict[str, float] = {}
    from broker_cash import current_t212_cash
    broker_cash = current_t212_cash(db, portfolio, display_ccy)
    if broker_cash is not None:
        cash_total = broker_cash.amount
        has_cash = abs(cash_total) > 0.005
        if has_cash:
            cash_by_ccy_display[broker_cash.currency] = cash_total
    elif has_external_cashflows(txns):
        from cash_ledger import cash_balance_by_currency, accrued_interest
        from fx import cash_amount_to_display

        rates = {r.currency: {"annual_rate": r.annual_rate, "enabled": r.enabled, "start_date": r.start_date}
                  for r in db.query(CashInterestRate).filter(
                      CashInterestRate.portfolio_id == pid,
                      CashInterestRate.workspace_id == workspace_id,
                  ).all()}
        cash_total = folded_cash_display(txns, rates, display_ccy)
        has_cash = abs(cash_total) > 0.005
        balances = cash_balance_by_currency(txns)
        accrued = accrued_interest(txns, rates)
        for ccy in set(balances) | set(accrued):
            v = cash_amount_to_display(balances.get(ccy, 0.0) + accrued.get(ccy, 0.0), ccy, display_ccy)
            if abs(v) > 0.005:
                cash_by_ccy_display[ccy] = v
    else:
        cash_total = 0.0
        has_cash = False

    if not transactions:
        # Cash-only portfolio (no trades yet): still surface the Cash slice —
        # it's 100% of the (non-holdings) allocation -- but only when the guard
        # above found an actual deposit/withdrawal (has_cash already reflects it).
        # Countries stays empty: cash has no country, so it's excluded from that
        # dimension entirely (holdings-only pie).
        sectors = {"Cash": round(cash_total, 2)} if has_cash else {}
        return {"sectors": sectors, "countries": {}, "asset_types": dict(sectors),
                "currencies": dict(cash_by_ccy_display) if has_cash else {},
                "total_value": 0.0}

    from routers.portfolio import _build_holdings, _live_fx_to_czk, _live_to_usd

    active = _build_holdings(transactions)  # shares only; values converted live below

    sector_totals: dict[str, float] = defaultdict(float)
    country_totals: dict[str, float] = defaultdict(float)
    type_totals: dict[str, float] = defaultdict(float)
    currency_totals: dict[str, float] = defaultdict(float)  # native trading ccy -> display value
    total_value = 0.0
    fx_cache: dict[str, float] = {}
    infos = market_data.get_infos(list(active.keys()))  # one bounded, concurrent batch

    for ticker, data in active.items():
        try:
            info = infos.get(ticker, {})
            price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
            ticker_ccy = (info.get("currency") or "USD")
            # Normalize pence-denominated LSE quotes to GBP, then apply FX.
            divisor = 100.0 if ticker_ccy == "GBp" else 1.0
            native_value = data["shares"] * float(price) / divisor
            if in_czk:
                live_fx = _live_fx_to_czk("GBP" if ticker_ccy == "GBp" else ticker_ccy, fx_cache)
            else:
                live_fx = _live_to_usd("GBP" if ticker_ccy == "GBp" else ticker_ccy)
            market_value = native_value * live_fx

            sector = _classify_sector(info)
            country = _classify_country(info)
            quote_type = (info.get("quoteType") or "EQUITY").upper()
            type_label = _QUOTE_TYPE_LABEL.get(quote_type, quote_type.title() if quote_type else "Other")
            # FX exposure groups by the security's native trading currency
            # (pence-quoted LSE names normalized to GBP, matching the value calc).
            trade_ccy = "GBP" if ticker_ccy == "GBp" else (ticker_ccy or "USD").upper()

            sector_totals[sector] += market_value
            country_totals[country] += market_value
            type_totals[type_label] += market_value
            currency_totals[trade_ccy] += market_value
            total_value += market_value
        except Exception:
            continue

    if has_cash:
        # Append Cash to sector/asset-type — it has no dimension of its own.
        # Country deliberately gets NO Cash slice (cash has no country); its
        # weights renormalize over holdings alone. For currencies, cash is
        # folded into its actual native currency (real FX exposure).
        sector_totals["Cash"] = cash_total
        type_totals["Cash"] = cash_total
        for ccy, v in cash_by_ccy_display.items():
            currency_totals[ccy] += v

    return {
        "sectors": dict(sector_totals),
        "countries": dict(country_totals),
        "asset_types": dict(type_totals),
        "currencies": dict(currency_totals),
        "total_value": total_value,
    }


@router.get("/sector-breakdown", dependencies=[Depends(require_capability("portfolio_analytics"))])
def sector_breakdown(
    currency: str = "USD",
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    display_ccy = "CZK" if currency.upper() == "CZK" else "USD"
    raw = _allocation_totals(db, portfolio, display_ccy)
    return {
        "currency": display_ccy,
        "sectors": _weighted(raw["sectors"]),
        "countries": _weighted(raw["countries"]),
        "asset_types": _weighted(raw["asset_types"]),
        "currencies": _weighted(raw["currencies"]),
        "total_value": round(raw["total_value"], 2),
    }


@router.get("/correlation", dependencies=[Depends(require_capability("portfolio_analytics"))])
def correlation_matrix(
    period: str = "1y",
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    transactions = _get_transactions(db, portfolio)
    if not transactions:
        return {"tickers": [], "matrix": []}

    from routers.portfolio import _build_holdings
    active = _build_holdings(transactions)
    tickers = list(active.keys())
    if len(tickers) < 2:
        return {"tickers": tickers, "matrix": [[1.0]] if tickers else []}

    period_map = {"3m": 90, "6m": 180, "1y": 365, "2y": 730}
    days = period_map.get(period, 365)
    start_date = date.today() - timedelta(days=days)

    yf_to_orig: dict[str, str] = {}
    for t in tickers:
        yf_to_orig.setdefault(yf_symbol(t), t)
    yf_tickers = list(yf_to_orig.keys())

    closes = _load_close_panel(yf_tickers, start_date)
    if closes.empty:
        return {"tickers": [], "matrix": []}
    closes = closes.rename(columns=yf_to_orig)

    returns = closes.pct_change().dropna(how="all")

    # Drop columns with too few observations to produce a stable correlation.
    min_obs = max(20, len(returns) // 4)
    available = [t for t in tickers if t in returns.columns and returns[t].count() >= min_obs]
    if len(available) < 2:
        return {"tickers": available, "matrix": [[1.0]] if available else []}

    corr = returns[available].corr(min_periods=min_obs)
    matrix = []
    for a in available:
        row = []
        for b in available:
            v = corr.loc[a, b]
            row.append(round(float(v), 3) if pd.notna(v) else 0.0)
        matrix.append(row)

    return {
        "tickers": available,
        "matrix": matrix,
        "observations": len(returns),
    }
