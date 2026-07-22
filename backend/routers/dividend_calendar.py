"""Forward dividend calendar: upcoming dividends for every holding in a portfolio.

For each held ticker, pulls the next ex-date, pay date, and estimated per-share
amount from yfinance. Aggregates by month so the UI can render a 12-month
forward-looking dividend forecast.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Optional

import pandas as pd
import yfinance as yf
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from cache import ttl_cache
from database import get_db
from models import Transaction
from routers.portfolios import require_portfolio
from ticker_map import yf_symbol

router = APIRouter(prefix="/analytics/dividend-calendar", tags=["dividend-calendar"])

_DIVIDEND_TTL = 3600  # 1 hour — dividend schedules change slowly


def _next_dividend_info(symbol: str) -> dict[str, Any]:
    """Best-effort fetch of next dividend for a single ticker.

    Returns:
        ex_date:   expected next ex-dividend date (or last known)
        pay_date:  expected next pay date (or None)
        amount:    latest dividend per share
        frequency: 'monthly', 'quarterly', 'semi-annual', 'annual', or 'unknown'
        yield_pct: trailing dividend yield percent
    """
    try:
        stock = yf.Ticker(yf_symbol(symbol))
        info = stock.info or {}
    except Exception:
        return {"ticker": symbol, "ex_date": None, "amount": None, "error": "yfinance unavailable"}

    # yfinance dividend yield — >=0.2.44 returns percent directly
    div_yield = info.get("dividendYield")
    if div_yield is not None:
        try:
            div_yield = round(float(div_yield), 2)
        except (TypeError, ValueError):
            div_yield = None

    # Trailing annual dividend rate
    div_rate = info.get("dividendRate")
    if div_rate is not None:
        try:
            div_rate = round(float(div_rate), 2)
        except (TypeError, ValueError):
            div_rate = None

    # Pull the dividend history to find the most recent dividend and estimate
    # ex-date / pay-date for the next one.
    ex_date: date | None = None
    pay_date_val: date | None = None
    amount: float | None = None
    frequency = "unknown"

    try:
        hist = stock.dividends
        if hist is not None and not hist.empty:
            # hist index is the ex-date
            last_ex = hist.index[-1]
            amount = float(hist.iloc[-1])

            if hasattr(last_ex, "date"):
                ex_date = last_ex.date()
            elif hasattr(last_ex, "strftime"):
                ex_date = pd.Timestamp(last_ex).date()

            # Estimate frequency from the gap between the last two dividends
            if len(hist) >= 2:
                gap = (hist.index[-1] - hist.index[-2]).days
                if gap < 50:
                    frequency = "monthly"
                elif gap < 100:
                    frequency = "quarterly"
                elif gap < 250:
                    frequency = "semi-annual"
                else:
                    frequency = "annual"
            elif div_rate and amount and amount > 0:
                implied_payments = round(div_rate / amount)
                if implied_payments >= 10:
                    frequency = "monthly"
                elif implied_payments >= 3:
                    frequency = "quarterly"
                elif implied_payments >= 1:
                    frequency = "annual"

            # Estimate next ex-date: last ex-date + gap days
            if ex_date and len(hist) >= 2:
                gap = (hist.index[-1] - hist.index[-2]).days
                next_ex_est = ex_date + timedelta(days=gap)
                # Only show dates in the forward-looking window
                if next_ex_est > date.today():
                    ex_date = next_ex_est

            # Estimate pay date from calendar if available
            try:
                cal = stock.calendar
                if cal is not None:
                    if isinstance(cal, dict):
                        raw_pay = cal.get("Dividend Date")
                    elif isinstance(cal, pd.DataFrame) and not cal.empty:
                        cal_dict = cal.to_dict()
                        raw_pay = None
                        for key, col in cal_dict.items():
                            val = list(col.values())
                            if val and isinstance(val[0], (pd.Timestamp, pd.datetime)):
                                raw_pay = val[0]
                                break
                            elif val:
                                raw_pay = val[0]
                    else:
                        raw_pay = None
                    if raw_pay is not None:
                        pay_date_val = pd.Timestamp(raw_pay).date()
            except Exception:
                pass
    except Exception:
        pass

    # Fallback amount from yfinance rate if history is empty
    if amount is None and div_rate is not None:
        amount = round(div_rate / 4, 4) if frequency == "quarterly" else round(div_rate, 4)

    return {
        "ticker": symbol,
        "ex_date": ex_date.isoformat() if ex_date else None,
        "pay_date": pay_date_val.isoformat() if pay_date_val else None,
        "amount_per_share": round(amount, 4) if amount is not None else None,
        "frequency": frequency,
        "trailing_yield_pct": div_yield,
        "dividend_rate_annual": div_rate,
    }


@router.get("")
def dividend_calendar(
    months: int = 12,
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    """Forward dividend calendar for the current portfolio.

    For each held ticker (open positions only), fetches the next dividend
    info and projects income over the next N months. Returns:
      - tickers with upcoming dividend data
      - monthly aggregated projections
      - total projected income per month
    """
    transactions = (
        db.query(Transaction)
        .filter(Transaction.portfolio_id == pid)
        .order_by(Transaction.date)
        .all()
    )
    if not transactions:
        return {"months": months, "tickers": [], "monthly_projection": [], "total_annual_est": 0}

    # Build active holdings (open positions only)
    from routers.portfolio import _build_holdings
    active = _build_holdings(transactions)

    # Fetch next dividend info for each held ticker
    results = []
    for ticker in sorted(active.keys()):
        shares = active[ticker]["shares"]
        info = _next_dividend_info(ticker)
        info["held_shares"] = round(shares, 4)
        if info["amount_per_share"] is not None:
            info["est_next_payment"] = round(shares * info["amount_per_share"], 2)
        else:
            info["est_next_payment"] = None
        results.append(info)

    # Build forward monthly projection
    projection_end = date.today() + timedelta(days=months * 30)
    monthly: dict[str, dict] = {}
    total_annual_est = 0.0

    for r in results:
        if r["amount_per_share"] is None or r["held_shares"] is None:
            continue
        shares = r["held_shares"]
        amt = r["amount_per_share"]
        freq = r["frequency"]
        ex = r["ex_date"]

        payments_per_year = {
            "monthly": 12, "quarterly": 4, "semi-annual": 2, "annual": 1, "unknown": 4,
        }.get(freq, 4)

        # Estimate: project payments at regular intervals starting from ex_date
        annual_est = round(shares * amt * payments_per_year, 2)
        total_annual_est += annual_est

        if ex:
            try:
                base_date = date.fromisoformat(ex)
            except (TypeError, ValueError):
                base_date = date.today()
        else:
            base_date = date.today()

        gap_days = 365 // payments_per_year if payments_per_year > 0 else 90

        # Don't project payments in the past. A suspended/delisted payer whose
        # last ex-date is years old (e.g. LEU, last ex-date 2005) would otherwise
        # flood monthly_projection with decades of stale months and inflate the
        # "next 30 days" stat. Fast-forward the cadence to the current month,
        # preserving the real payment phase (step size stays gap_days).
        current_month_start = date.today().replace(day=1)
        projection = base_date
        while gap_days > 0 and projection < current_month_start:
            projection += timedelta(days=gap_days)

        while projection <= projection_end:
            month_key = projection.strftime("%Y-%m")
            month_label = projection.strftime("%b %Y")
            if month_key not in monthly:
                monthly[month_key] = {"month": month_key, "label": month_label, "total": 0.0, "items": []}

            payment = round(shares * amt, 2)
            monthly[month_key]["total"] += payment
            monthly[month_key]["items"].append({
                "ticker": r["ticker"],
                "ex_date": projection.isoformat(),
                "est_payment": payment,
                "amount_per_share": amt,
                "frequency": freq,
            })
            projection += timedelta(days=gap_days)

    month_list = sorted(monthly.values(), key=lambda m: m["month"])
    return {
        "months": months,
        "tickers": results,
        "monthly_projection": month_list,
        "total_annual_est": round(total_annual_est, 2),
    }
