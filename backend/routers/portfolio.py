from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
import yfinance as yf
import pandas as pd
import pytz
import io
from datetime import datetime

from database import get_db
from models import Transaction
from cash_ledger import TRADE_TYPES
from schemas import TransactionCreate, TransactionResponse
from fx import fetch_fx_to_czk, bulk_fetch_fx
from routers.portfolios import require_portfolio
from ticker_map import yf_symbol
import market_data

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

# ---------------------------------------------------------------------------
# Trading 212 CSV normalisation
# ---------------------------------------------------------------------------

_T212_SIGNATURE = {"action", "time", "no. of shares", "price / share", "ticker"}

_T212_BUY_ACTIONS = {
    "market buy", "limit buy", "stop buy", "buy"
}
_T212_SELL_ACTIONS = {
    "market sell", "limit sell", "stop sell", "sell"
}
# Non-trade rows we recognise and silently skip
_T212_SKIP_ACTIONS = {
    "interest on cash", "withdrawal", "deposit",
    "currency conversion", "cash in", "cash out",
    "spending cashback", "result from positions",
}


def _is_t212(cols: set) -> bool:
    return _T212_SIGNATURE.issubset(cols)


def _t212_action_to_type(action: str) -> str | None:
    a = action.strip().lower()
    if a in _T212_BUY_ACTIONS:
        return "buy"
    if a in _T212_SELL_ACTIONS:
        return "sell"
    if "dividend" in a:
        return "dividend"
    if a in _T212_SKIP_ACTIONS or not a:
        return None  # skip silently
    return None  # unknown → skip


def _normalize_t212(df: pd.DataFrame) -> tuple[list[dict], int]:
    """Convert a T212 DataFrame into a list of normalised row dicts.

    Returns (rows, skipped_count).
    """
    rows, skipped = [], 0
    for _, row in df.iterrows():
        raw_action = str(row.get("action", "")).strip()
        txn_type = _t212_action_to_type(raw_action)
        if txn_type is None:
            skipped += 1
            continue

        ticker = str(row.get("ticker", "")).strip().upper()
        if not ticker or ticker in ("NAN", ""):
            skipped += 1
            continue

        shares_raw = row.get("no. of shares")
        price_raw = row.get("price / share")
        if pd.isna(shares_raw) or pd.isna(price_raw):
            skipped += 1
            continue

        try:
            txn_date = pd.to_datetime(str(row["time"])).date()
        except Exception:
            skipped += 1
            continue

        currency = str(row.get("currency (price / share)", "USD")).strip().upper()
        if not currency or currency == "NAN":
            currency = "USD"

        rows.append({
            "ticker": ticker,
            "name": str(row.get("name", ticker)).strip(),
            "type": txn_type,
            "shares": float(shares_raw),
            "price": float(price_raw),
            "currency": currency,
            "date": txn_date,
            "notes": f"T212: {raw_action}",
        })

    return rows, skipped


def _fetch_price_and_info(ticker: str) -> tuple[float, str, str]:
    # Bounded + cached: see market_data. A delisted/thin ticker can no longer
    # hang the whole request, and repeat lookups (e.g. /summary right after
    # /holdings) hit the TTL cache instead of re-querying Yahoo.
    return market_data.quote(market_data.get_info(ticker), ticker)


_TXN_TYPE_ORDER = {"buy": 0, "dividend": 1, "sell": 2}


def _portfolio_txns(db: Session, pid: int):
    return db.query(Transaction).filter(Transaction.portfolio_id == pid)


def _build_holdings(transactions: list, include_closed: bool = False, in_czk: bool = False) -> dict:
    """Aggregate per-ticker shares, cost, dividends and realized P&L."""
    fx_fallback: dict[str, float] = {}
    holdings: dict[str, dict] = {}
    for txn in sorted(transactions, key=lambda t: (t.date, _TXN_TYPE_ORDER.get(t.type, 1))):
        if txn.type not in TRADE_TYPES or not txn.ticker:
            continue  # cash rows (deposit/withdrawal/fee/interest) never affect holdings
        t = txn.ticker
        if in_czk:
            fx = txn.fx_to_czk or _live_fx_to_czk(txn.currency, fx_fallback)
        else:
            fx = 1.0
        if t not in holdings:
            holdings[t] = {"shares": 0.0, "cost": 0.0, "dividends": 0.0, "realized_pnl": 0.0, "currency": txn.currency}
        if txn.type == "buy":
            holdings[t]["shares"] += txn.shares
            holdings[t]["cost"] += txn.shares * txn.price * fx
        elif txn.type == "sell":
            if holdings[t]["shares"] > 0:
                avg = holdings[t]["cost"] / holdings[t]["shares"]
                sold_shares = min(txn.shares, holdings[t]["shares"])
                holdings[t]["realized_pnl"] += sold_shares * (txn.price * fx - avg)
                holdings[t]["shares"] -= sold_shares
                holdings[t]["cost"] -= sold_shares * avg
                holdings[t]["shares"] = max(0.0, holdings[t]["shares"])
                holdings[t]["cost"] = max(0.0, holdings[t]["cost"])
        elif txn.type == "dividend":
            holdings[t]["dividends"] += txn.shares * txn.price * fx
    if include_closed:
        return holdings
    return {k: v for k, v in holdings.items() if v["shares"] > 0.0001}


def _live_fx_to_czk(currency: str, cache: dict) -> float:
    c = (currency or "USD").upper()
    if c == "CZK":
        return 1.0
    if c in cache:
        return cache[c]
    try:
        info = market_data.get_info(f"{c}CZK=X")
        rate = info.get("regularMarketPrice") or info.get("currentPrice") or 0
        rate = float(rate) if rate else 0.0
    except Exception:
        rate = 0.0
    if rate <= 0:
        rate = 1.0
    cache[c] = rate
    return rate


@router.get("/transactions", response_model=List[TransactionResponse])
def get_transactions(db: Session = Depends(get_db), pid: int = Depends(require_portfolio)):
    return _portfolio_txns(db, pid).order_by(Transaction.date.desc()).all()


@router.post("/transactions", response_model=TransactionResponse)
def create_transaction(
    txn: TransactionCreate,
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    # Bounded: a bad symbol used to be able to hang the POST for minutes.
    name = market_data.get_info(txn.ticker.upper()).get("shortName") or txn.ticker
    fx = fetch_fx_to_czk(txn.currency, txn.date)
    db_txn = Transaction(
        **txn.model_dump(exclude={"ticker"}),
        name=name,
        ticker=txn.ticker.upper(),
        fx_to_czk=fx,
        portfolio_id=pid,
    )
    db.add(db_txn)
    db.commit()
    db.refresh(db_txn)
    return db_txn


@router.delete("/transactions/{txn_id}")
def delete_transaction(
    txn_id: int,
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    txn = (
        db.query(Transaction)
        .filter(Transaction.id == txn_id, Transaction.portfolio_id == pid)
        .first()
    )
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(txn)
    db.commit()
    return {"ok": True}


@router.delete("/transactions")
def clear_all_transactions(
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    deleted = _portfolio_txns(db, pid).delete(synchronize_session=False)
    db.commit()
    return {"deleted": deleted}


@router.post("/import-csv")
async def import_csv(
    file: UploadFile = File(...),
    replace: bool = False,
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    content = await file.read()
    try:
        df = pd.read_csv(io.StringIO(content.decode("utf-8")))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse CSV: {e}")

    df.columns = df.columns.str.lower().str.strip()
    cols = set(df.columns)

    imported, skipped, errors = 0, 0, []

    new_rows: list[dict] = []

    if _is_t212(cols):
        fmt = "Trading 212"
        normalised, skipped = _normalize_t212(df)
        new_rows = normalised

    else:
        fmt = "Native"
        required = {"date", "ticker", "type", "shares", "price"}
        missing = required - cols
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Unrecognised CSV format. Missing columns: {', '.join(sorted(missing))}. "
                       f"Expected either the native format (date, ticker, type, shares, price) "
                       f"or a Trading 212 export.",
            )
        for i, row in df.iterrows():
            try:
                new_rows.append(dict(
                    ticker=str(row["ticker"]).upper().strip(),
                    type=str(row["type"]).lower().strip(),
                    shares=float(row["shares"]),
                    price=float(row["price"]),
                    currency=str(row.get("currency", "USD")).upper().strip()
                    if pd.notna(row.get("currency")) else "USD",
                    date=pd.to_datetime(row["date"]).date(),
                    notes=str(row["notes"])
                    if "notes" in row and pd.notna(row.get("notes")) else None,
                ))
            except Exception as e:
                errors.append(f"Row {i + 2}: {e}")

    # Only now that the CSV has parsed and validated do we touch the database.
    # `replace` deletes the existing rows in the SAME transaction as the insert
    # so a malformed upload can never wipe the portfolio and leave nothing
    # behind (previously the delete was committed up-front).
    if replace:
        _portfolio_txns(db, pid).delete(synchronize_session=False)

    fx_map = bulk_fetch_fx({(r["currency"], r["date"]) for r in new_rows})
    for r in new_rows:
        try:
            r["fx_to_czk"] = fx_map.get((r["currency"].upper(), r["date"]))
            db.add(Transaction(**r, portfolio_id=pid))
            imported += 1
        except Exception as e:
            errors.append(str(e))

    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors, "format": fmt}


@router.get("/holdings")
def get_holdings(
    include_closed: bool = False,
    currency: str = "USD",
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    transactions = _portfolio_txns(db, pid).all()
    if not transactions:
        return []

    in_czk = currency.upper() == "CZK"
    all_data = _build_holdings(transactions, include_closed=True, in_czk=in_czk)
    active = {k: v for k, v in all_data.items() if v["shares"] > 0.0001}
    # Warm the quote cache for every ticker in one concurrent, deadline-bounded
    # batch so the per-ticker _fetch_price_and_info calls below all hit the
    # cache instead of fanning out serial Yahoo requests.
    market_data.get_infos(list(all_data.keys()))
    result = []
    total_value = 0.0
    fx_cache: dict[str, float] = {}

    for ticker, data in active.items():
        price, name, ticker_ccy = _fetch_price_and_info(ticker)
        live_fx = _live_fx_to_czk(ticker_ccy, fx_cache) if in_czk else 1.0
        market_value = data["shares"] * price * live_fx
        cost_basis = data["cost"]
        pnl = market_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0
        avg_cost = cost_basis / data["shares"] if data["shares"] > 0 else 0
        result.append({
            "ticker": ticker,
            "name": name,
            "shares": round(data["shares"], 4),
            "avg_cost": round(avg_cost, 2),
            "current_price": round(price, 2),
            "market_value": round(market_value, 2),
            "cost_basis": round(cost_basis, 2),
            "pnl": round(pnl, 2),
            "pnl_percent": round(pnl_pct, 2),
            "weight": 0.0,
            "currency": ticker_ccy,
            "dividends": round(data["dividends"], 2),
            "closed": False,
        })
        total_value += market_value

    for h in result:
        h["weight"] = round((h["market_value"] / total_value * 100) if total_value > 0 else 0, 2)

    if include_closed:
        closed = {k: v for k, v in all_data.items() if v["shares"] <= 0.0001}
        txn_names = {}
        txn_totals: dict[str, dict] = {}
        for txn in transactions:
            if txn.ticker not in txn_names and txn.name:
                txn_names[txn.ticker] = txn.name
            if txn.ticker in closed:
                t = txn_totals.setdefault(txn.ticker, {"bought_val": 0.0, "sold_val": 0.0, "bought_sh": 0.0, "sold_sh": 0.0})
                fx = (txn.fx_to_czk or _live_fx_to_czk(txn.currency, fx_cache)) if in_czk else 1.0
                if txn.type == "buy":
                    t["bought_val"] += txn.shares * txn.price * fx
                    t["bought_sh"] += txn.shares
                elif txn.type == "sell":
                    t["sold_val"] += txn.shares * txn.price * fx
                    t["sold_sh"] += txn.shares

        for ticker, data in closed.items():
            totals = txn_totals.get(ticker, {})
            cost = totals.get("bought_val", 0)
            realized = data["realized_pnl"]
            pnl_pct = (realized / cost * 100) if cost > 0 else 0
            bought_sh = totals.get("bought_sh", 0)
            avg_buy = cost / bought_sh if bought_sh else 0
            avg_sell = totals["sold_val"] / totals["sold_sh"] if totals.get("sold_sh") else 0

            # Hypothetical P&L if the position had been held to today instead
            # of sold. Uses live price * live FX (so it tracks the user's
            # currency view), against the buy cost expressed in that currency.
            live_price, _, live_ccy = _fetch_price_and_info(ticker)
            live_fx = _live_fx_to_czk(live_ccy, fx_cache) if in_czk else 1.0
            if bought_sh and live_price > 0:
                hypothetical_value = bought_sh * live_price * live_fx
                pnl_if_held = hypothetical_value - cost
                pnl_if_held_pct = (pnl_if_held / cost * 100) if cost > 0 else 0
                # Delta vs. realized: positive means holding would have done better.
                pnl_if_held_delta = pnl_if_held - realized
            else:
                live_price = 0
                pnl_if_held = None
                pnl_if_held_pct = None
                pnl_if_held_delta = None

            result.append({
                "ticker": ticker,
                "name": txn_names.get(ticker, ticker),
                "shares": 0,
                "avg_cost": round(avg_buy, 2),
                "current_price": round(avg_sell, 2),
                "market_value": 0,
                "cost_basis": round(cost, 2),
                "pnl": round(realized, 2),
                "pnl_percent": round(pnl_pct, 2),
                "weight": 0.0,
                "currency": data.get("currency", "USD"),
                "dividends": round(data["dividends"], 2),
                "closed": True,
                "live_price": round(live_price * live_fx, 2) if live_price else None,
                "pnl_if_held": round(pnl_if_held, 2) if pnl_if_held is not None else None,
                "pnl_if_held_pct": round(pnl_if_held_pct, 2) if pnl_if_held_pct is not None else None,
                "pnl_if_held_delta": round(pnl_if_held_delta, 2) if pnl_if_held_delta is not None else None,
            })

    return sorted(result, key=lambda x: (x.get("closed", False), -x["market_value"]))


@router.get("/summary")
def get_summary(
    currency: str = "USD",
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    holdings = get_holdings(currency=currency, db=db, pid=pid)
    in_czk = currency.upper() == "CZK"
    total_value = sum(h["market_value"] for h in holdings)
    total_invested = sum(h["cost_basis"] for h in holdings)
    unrealized_pnl = total_value - total_invested

    transactions = _portfolio_txns(db, pid).all()
    fx_fallback: dict[str, float] = {}

    def _txn_fx(t):
        return (t.fx_to_czk or _live_fx_to_czk(t.currency, fx_fallback)) if in_czk else 1.0

    total_dividends = sum(
        t.shares * t.price * _txn_fx(t) for t in transactions if t.type == "dividend"
    )

    # Realized P&L from FIFO-style avg-cost matching, mirroring the per-date
    # logic in /performance so the metric card matches the chart's latest point.
    shares_open: dict[str, float] = {}
    cost_open: dict[str, float] = {}
    realized_pnl = 0.0
    cum_buys_cost = 0.0
    for txn in sorted(transactions, key=lambda t: (t.date, _TXN_TYPE_ORDER.get(t.type, 1))):
        fx = _txn_fx(txn)
        if txn.type == "buy":
            shares_open[txn.ticker] = shares_open.get(txn.ticker, 0.0) + txn.shares
            cost_open[txn.ticker] = cost_open.get(txn.ticker, 0.0) + txn.shares * txn.price * fx
            cum_buys_cost += txn.shares * txn.price * fx
        elif txn.type == "sell":
            prev = shares_open.get(txn.ticker, 0.0)
            if prev > 0:
                avg = cost_open.get(txn.ticker, 0.0) / prev
                sold = min(txn.shares, prev)
                realized_pnl += sold * (txn.price * fx - avg)
                shares_open[txn.ticker] = prev - sold
                cost_open[txn.ticker] = max(0.0, cost_open.get(txn.ticker, 0.0) - sold * avg)

    total_pnl = unrealized_pnl + realized_pnl + total_dividends
    total_pnl_pct = (total_pnl / cum_buys_cost * 100) if cum_buys_cost > 0 else 0

    # Day change — authoritative, reuses the movers 2-day-close logic across ALL
    # holdings. fx per holding is derived from the already-converted market_value
    # so it matches total_value exactly. Degrades to None on any data gap.
    day_change = None
    day_change_pct = None
    active_day = _build_holdings(transactions)
    closes_map = _two_day_closes(list(active_day.keys())) if active_day else {}
    if closes_map:
        rows = []
        mv_by_ticker = {h["ticker"]: h for h in holdings}
        for ticker, (start_px, end_px) in closes_map.items():
            shares = active_day[ticker]["shares"]
            h = mv_by_ticker.get(ticker)
            if not h or shares <= 0 or end_px <= 0:
                continue
            fx = h["market_value"] / (shares * end_px)  # native -> display currency
            rows.append({"shares": shares, "start": start_px, "end": end_px, "fx": fx})
        if rows:
            change, prev_value = aggregate_day_change(rows)
            day_change = round(change, 2)
            day_change_pct = round(change / prev_value * 100, 2) if prev_value > 0 else None

    # Cash + accrued interest, blended into net worth on the SAME basis as
    # total_value: cash_amount_to_display only converts native->CZK when the
    # display currency is CZK, otherwise it's a native sum (mirrors the
    # live_fx=1.0 branch above), so total_value + cash + accrued is always
    # consistent.
    from cash_ledger import cash_balance_by_currency, accrued_interest
    from models import CashInterestRate
    from fx import cash_amount_to_display
    _rates = {r.currency: {"annual_rate": r.annual_rate, "enabled": r.enabled, "start_date": r.start_date}
              for r in db.query(CashInterestRate).filter(CashInterestRate.portfolio_id == pid).all()}
    _balances = cash_balance_by_currency(transactions)
    _accrued = accrued_interest(transactions, _rates)
    cash_total = sum(cash_amount_to_display(v, ccy, currency) for ccy, v in _balances.items())
    accrued_total = sum(cash_amount_to_display(v, ccy, currency) for ccy, v in _accrued.items())

    return {
        "total_value": round(total_value, 2),
        "total_invested": round(total_invested, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_percent": round(total_pnl_pct, 2),
        "day_change": day_change,
        "day_change_percent": day_change_pct,
        "total_dividends": round(total_dividends, 2),
        "holdings_count": len(holdings),
        "last_updated": datetime.now().isoformat(),
        "cash": round(cash_total, 2),
        "accrued_interest": round(accrued_total, 2),
        "net_worth": round(total_value + cash_total + accrued_total, 2),
    }


def _ts_to_date_str(raw) -> str | None:
    """Normalize a yfinance date field (UNIX int or ISO/Timestamp) to YYYY-MM-DD."""
    if raw is None or raw == "":
        return None
    try:
        if isinstance(raw, (int, float)):
            return datetime.utcfromtimestamp(int(raw)).strftime("%Y-%m-%d")
    except Exception:
        pass
    try:
        return pd.Timestamp(raw).strftime("%Y-%m-%d")
    except Exception:
        return None


def _pay_date_from_calendar(yf_ticker) -> str | None:
    """Fallback: pull next dividend pay date from yfinance .calendar."""
    try:
        cal = yf_ticker.calendar
    except Exception:
        return None
    if cal is None:
        return None
    try:
        if isinstance(cal, dict):
            raw = cal.get("Dividend Date") or cal.get("Ex-Dividend Date")
            if raw:
                return pd.Timestamp(raw).strftime("%Y-%m-%d")
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            cal_dict = cal.to_dict()
            for key, col in cal_dict.items():
                val = list(col.values())
                if not val:
                    continue
                if not isinstance(val[0], (pd.Timestamp, datetime)):
                    continue
                key_l = str(key).lower()
                if "dividend" in key_l or "pay" in key_l:
                    return val[0].strftime("%Y-%m-%d")
    except Exception:
        return None
    return None


_USD_FX_CACHE: dict[str, float] = {}


def _live_to_usd(ccy: str) -> float:
    """Best-effort live conversion rate from `ccy` to USD. Returns 1.0 on failure."""
    c = (ccy or "USD").upper()
    if c == "USD":
        return 1.0
    if c in _USD_FX_CACHE:
        return _USD_FX_CACHE[c]
    try:
        info = market_data.get_info(f"{c}USD=X")
        rate = info.get("regularMarketPrice") or info.get("previousClose")
        if rate and rate > 0:
            _USD_FX_CACHE[c] = float(rate)
            return float(rate)
    except Exception:
        pass
    return 1.0


@router.get("/dividends")
def get_dividends(
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    transactions = _portfolio_txns(db, pid).all()
    if not transactions:
        return []

    active = _build_holdings(transactions)
    market_data.get_infos(list(active.keys()))  # warm cache concurrently/bounded
    result = []

    for ticker in active:
        try:
            info = market_data.get_info(ticker) or {}
            name = info.get("shortName") or info.get("longName") or ticker
            div_rate = info.get("dividendRate") or info.get("trailingAnnualDividendRate")
            div_yield = info.get("dividendYield")
            currency = info.get("currency", "USD")
            shares = active[ticker]["shares"]

            ex_date = _ts_to_date_str(info.get("exDividendDate"))
            pay_date = _ts_to_date_str(info.get("dividendDate"))
            if not pay_date:
                pay_date = _pay_date_from_calendar(yf.Ticker(yf_symbol(ticker)))

            if not div_rate and not div_yield:
                continue

            annual_income = (shares * float(div_rate)) if div_rate else None

            result.append({
                "ticker": ticker,
                "name": name,
                "ex_date": ex_date,
                "pay_date": pay_date,
                "dividend_rate": round(float(div_rate), 4) if div_rate else None,
                "dividend_yield": round(float(div_yield), 2) if div_yield else None,
                "annual_income": round(annual_income, 2) if annual_income is not None else None,
                "currency": currency,
                "shares": round(shares, 4),
            })
        except Exception:
            continue

    def sort_key(r):
        if r["pay_date"]:
            return (0, r["pay_date"])
        if r["ex_date"]:
            return (1, r["ex_date"])
        return (2, r["ticker"])

    return sorted(result, key=sort_key)


@router.get("/dividends/forecast")
def get_dividend_forecast(
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    """Monthly paid (actual) and estimated (projected) dividends for the current
    calendar year, summed across the active portfolio and converted to USD.

    Estimation: for each held ticker we look at its trailing ~13 months of
    dividend history from yfinance, take the average per-share payment for each
    calendar month it historically paid in, and project that into the same
    month-of-year going forward — scaled by the user's current share count.
    """
    transactions = _portfolio_txns(db, pid).all()
    year = datetime.now().year
    today = datetime.now().date()
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    if not transactions:
        return {
            "year": year,
            "currency": "USD",
            "months": [
                {"month": m, "paid": 0.0, "estimated": 0.0, "entries": []}
                for m in month_names
            ],
            "total_paid": 0.0,
            "total_estimated": 0.0,
        }

    paid_by_month = [0.0] * 12
    estimated_by_month = [0.0] * 12
    # entries_by_month[i] = list of {ticker, name, amount, status}
    entries_by_month: list[list[dict]] = [[] for _ in range(12)]

    # 1. Actual paid dividends (real transactions in current year), aggregated
    #    per (ticker, month) so multiple lots collapse into one entry.
    paid_keys: set[tuple[str, int]] = set()
    paid_agg: dict[tuple[str, int], float] = {}
    paid_names: dict[str, str] = {}
    for txn in transactions:
        if txn.type != "dividend" or not txn.date or txn.date.year != year:
            continue
        amt_usd = txn.shares * txn.price * _live_to_usd(txn.currency or "USD")
        m_idx = txn.date.month - 1
        paid_by_month[m_idx] += amt_usd
        key = (txn.ticker, txn.date.month)
        paid_keys.add(key)
        paid_agg[key] = paid_agg.get(key, 0.0) + amt_usd
        if txn.name and txn.ticker not in paid_names:
            paid_names[txn.ticker] = txn.name

    for (ticker, month), amount in paid_agg.items():
        entries_by_month[month - 1].append({
            "ticker": ticker,
            "name": paid_names.get(ticker, ticker),
            "amount": round(amount, 2),
            "status": "paid",
        })

    # 2. Estimated future dividends per held ticker, projected from yfinance
    #    history.
    active = _build_holdings(transactions)
    market_data.get_infos(list(active.keys()))  # warm cache concurrently/bounded
    for ticker, data in active.items():
        shares = data.get("shares", 0.0)
        if shares <= 0:
            continue
        try:
            info = market_data.get_info(ticker) or {}
            ccy = info.get("currency", "USD")
            display_name = info.get("shortName") or info.get("longName") or ticker

            div_history = yf.Ticker(yf_symbol(ticker)).dividends
            if div_history is None or div_history.empty:
                continue

            cutoff = pd.Timestamp(today) - pd.Timedelta(days=400)
            try:
                idx = div_history.index
                if getattr(idx, "tz", None) is not None:
                    div_history = div_history.copy()
                    div_history.index = idx.tz_localize(None)
            except Exception:
                pass
            recent = div_history[div_history.index >= cutoff]
            if recent.empty:
                continue

            by_month: dict[int, list[float]] = {}
            for ts, amount in recent.items():
                by_month.setdefault(ts.month, []).append(float(amount))

            usd_rate = _live_to_usd(ccy)
            for m in range(1, 13):
                if m < today.month:
                    continue
                if (ticker, m) in paid_keys:
                    continue
                payments = by_month.get(m)
                if not payments:
                    continue
                avg_per_share = sum(payments) / len(payments)
                est_usd = shares * avg_per_share * usd_rate
                if est_usd <= 0:
                    continue
                estimated_by_month[m - 1] += est_usd
                entries_by_month[m - 1].append({
                    "ticker": ticker,
                    "name": display_name,
                    "amount": round(est_usd, 2),
                    "status": "estimated",
                })
        except Exception:
            continue

    months = [
        {
            "month": month_names[i],
            "paid": round(paid_by_month[i], 2),
            "estimated": round(estimated_by_month[i], 2),
            "entries": sorted(entries_by_month[i], key=lambda e: -e["amount"]),
        }
        for i in range(12)
    ]

    return {
        "year": year,
        "currency": "USD",
        "months": months,
        "total_paid": round(sum(paid_by_month), 2),
        "total_estimated": round(sum(estimated_by_month), 2),
    }


def _xirr(flows: list[tuple], guess: float = 0.1) -> float:
    if not flows or len(flows) < 2:
        return 0.0
    flows = sorted(flows, key=lambda x: x[0])
    has_pos = any(a > 0 for _, a in flows)
    has_neg = any(a < 0 for _, a in flows)
    if not (has_pos and has_neg):
        return 0.0

    d0 = flows[0][0]
    times = [(d - d0).days / 365.0 for d, _ in flows]
    amounts = [float(a) for _, a in flows]

    def npv(r: float) -> float:
        return sum(a / (1 + r) ** t for a, t in zip(amounts, times))

    def dnpv(r: float) -> float:
        return sum(-a * t / (1 + r) ** (t + 1) for a, t in zip(amounts, times))

    r = guess
    for _ in range(60):
        try:
            f = npv(r)
            if abs(f) < 1e-9:
                return r
            df = dnpv(r)
            if df == 0:
                break
            r_new = r - f / df
            if r_new <= -0.999:
                r_new = -0.99
            if abs(r_new - r) < 1e-8:
                return r_new
            r = r_new
        except (ZeroDivisionError, OverflowError):
            break

    lo, hi = -0.999, 10.0
    try:
        f_lo = npv(lo)
        f_hi = npv(hi)
        if f_lo * f_hi > 0:
            return 0.0
        for _ in range(200):
            mid = (lo + hi) / 2
            f_mid = npv(mid)
            if abs(f_mid) < 1e-9:
                return mid
            if f_lo * f_mid < 0:
                hi = mid
                f_hi = f_mid
            else:
                lo = mid
                f_lo = f_mid
        return (lo + hi) / 2
    except Exception:
        return 0.0


def _resolve_start_date(period: str, first_txn_date) -> datetime:
    from datetime import date, timedelta
    today = date.today()
    mapping = {
        "7d": today - timedelta(days=7),
        "mtd": today.replace(day=1),
        "1m": today - timedelta(days=30),
        "3m": today - timedelta(days=90),
        "ytd": today.replace(month=1, day=1),
        "1y": today - timedelta(days=365),
        "all": first_txn_date,
    }
    calculated = mapping.get(period.lower(), first_txn_date)
    return max(calculated, first_txn_date)


@router.get("/performance")
def get_performance(
    currency: str = "USD",
    period: str = "all",
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    transactions = _portfolio_txns(db, pid).order_by(Transaction.date).all()
    if not transactions:
        return []

    tickers = list({t.ticker for t in transactions if t.type in ("buy", "sell")})
    if not tickers:
        return []

    # Map broker symbol -> Yahoo symbol; download under Yahoo's name, then
    # rename the result columns back so the rest of the loop matches by the
    # user's stored ticker.
    yf_to_orig: dict[str, str] = {}
    for t in tickers:
        yf_to_orig.setdefault(yf_symbol(t), t)
    yf_tickers = list(yf_to_orig.keys())

    start_date = _resolve_start_date(period, transactions[0].date)

    try:
        first_date = start_date.strftime("%Y-%m-%d")
        raw = yf.download(yf_tickers, start=first_date, auto_adjust=True, progress=False)
        if len(yf_tickers) == 1:
            closes = raw[["Close"]].rename(columns={"Close": yf_tickers[0]})
        else:
            closes = raw["Close"] if "Close" in raw.columns else raw
        closes = closes.rename(columns=yf_to_orig)
    except Exception:
        return []

    closes = closes.ffill().dropna(how="all")

    fx_rates: pd.Series | None = None
    if currency.upper() == "CZK":
        try:
            fx_raw = yf.download("USDCZK=X", start=first_date, auto_adjust=True, progress=False)
            if not fx_raw.empty:
                close_col = fx_raw["Close"]
                if hasattr(close_col, "squeeze"):
                    close_col = close_col.squeeze()
                fx_rates = close_col.reindex(closes.index, method="ffill").ffill()
        except Exception:
            fx_rates = None

    result = []

    for date_idx in closes.index:
        date_str = str(date_idx.date())
        curr_date = date_idx.date()
        holdings: dict[str, float] = {}
        cost_basis: dict[str, float] = {}
        realized_to_date = 0.0
        dividends_to_date = 0.0
        cum_buys_cost = 0.0

        for txn in transactions:
            if txn.date > curr_date:
                break
            if txn.type == "buy":
                holdings[txn.ticker] = holdings.get(txn.ticker, 0) + txn.shares
                cost_basis[txn.ticker] = cost_basis.get(txn.ticker, 0) + txn.shares * txn.price
                cum_buys_cost += txn.shares * txn.price
            elif txn.type == "sell":
                prev = holdings.get(txn.ticker, 0)
                if prev > 0:
                    avg = cost_basis.get(txn.ticker, 0) / prev
                    sold = min(txn.shares, prev)
                    realized_to_date += sold * (txn.price - avg)
                    holdings[txn.ticker] = prev - sold
                    cost_basis[txn.ticker] = max(0.0, cost_basis.get(txn.ticker, 0) - sold * avg)
            elif txn.type == "dividend":
                dividends_to_date += txn.shares * txn.price

        invested = sum(cost_basis.values())

        portfolio_value = 0.0
        for ticker, shares in holdings.items():
            if shares <= 0:
                continue
            try:
                price = float(closes.loc[date_idx, ticker]) if ticker in closes.columns else 0
                if pd.notna(price):
                    portfolio_value += shares * price
            except Exception:
                pass

        fx_rate = 1.0
        if fx_rates is not None:
            try:
                r = float(fx_rates.loc[date_idx])
                if pd.notna(r) and r > 0:
                    fx_rate = r
            except Exception:
                pass

        unrealized = portfolio_value - invested
        total_pnl_native = unrealized + realized_to_date + dividends_to_date
        total_pnl_pct = (total_pnl_native / cum_buys_cost * 100) if cum_buys_cost > 0 else 0.0

        result.append({
            "date": date_str,
            "value": round(portfolio_value * fx_rate, 2),
            "invested": round(invested * fx_rate, 2),
            "total_pnl": round(total_pnl_native * fx_rate, 2),
            "total_pnl_pct": round(total_pnl_pct, 2),
        })

    # Period-rebased metrics: pnl & pnl_pct reflect growth since the first day
    # of the selected timeframe, not lifetime. This keeps tooltip numbers
    # consistent across 7D/MTD/1M/3M/YTD/1Y/All and comparable to benchmarks.
    from bisect import bisect_left

    def _fx(d):
        if fx_rates is None:
            return 1.0
        try:
            idx = pd.Timestamp(d)
            earlier = fx_rates[fx_rates.index <= idx]
            if not earlier.empty:
                v = float(earlier.iloc[-1])
                return v if pd.notna(v) and v > 0 else 1.0
        except Exception:
            pass
        return 1.0

    result_dates = [
        datetime.strptime(r["date"], "%Y-%m-%d").date()
        if isinstance(r["date"], str) else r["date"]
        for r in result
    ]
    baseline_date = result_dates[0] if result_dates else None

    # Bucket each buy/sell as an external contribution into the result row on or
    # after the txn date, and dividends as portfolio return (cash that augments
    # value without changing capital base). Flows on the baseline day itself
    # are folded into V0 (the opening value) and excluded here.
    bucketed_contribs = [0.0] * len(result)
    bucketed_divs = [0.0] * len(result)
    for txn in transactions:
        if baseline_date is None or txn.date <= baseline_date:
            continue
        idx = bisect_left(result_dates, txn.date)
        if idx >= len(result_dates):
            continue
        fx = (txn.fx_to_czk or _fx(txn.date)) if currency.upper() == "CZK" else 1.0
        amt = txn.shares * txn.price * fx
        if txn.type == "buy":
            bucketed_contribs[idx] += amt
        elif txn.type == "sell":
            bucketed_contribs[idx] -= amt
        elif txn.type == "dividend":
            bucketed_divs[idx] += amt

    V0 = result[0]["value"] if result else 0.0
    cum_contrib = 0.0
    cum_div = 0.0
    prev_value = V0
    cum_twr = 1.0

    for i, r in enumerate(result):
        if i == 0:
            r["pnl"] = 0.0
            r["pnl_pct"] = 0.0
            prev_value = r["value"]
            continue
        today_contrib = bucketed_contribs[i]
        today_div = bucketed_divs[i]
        cum_contrib += today_contrib
        cum_div += today_div
        v = r["value"]
        base = prev_value + today_contrib
        if base > 0:
            cum_twr *= (1 + (v + today_div - base) / base)
        r["pnl"] = round(v - V0 - cum_contrib + cum_div, 2)
        r["pnl_pct"] = round((cum_twr - 1) * 100, 2)
        prev_value = v

    return result


@router.get("/earnings")
def get_earnings(
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    transactions = _portfolio_txns(db, pid).all()
    if not transactions:
        return []

    active = _build_holdings(transactions)
    if not active:
        return []

    cet = pytz.timezone("Europe/Prague")
    now_cet = pd.Timestamp.now(tz=cet)
    result = []

    for ticker in active:
        try:
            yf_ticker = yf.Ticker(yf_symbol(ticker))
            ed = yf_ticker.earnings_dates
            if ed is None or ed.empty:
                continue
            upcoming = ed[ed.index >= now_cet.tz_convert(ed.index.tz)]
            if upcoming.empty:
                continue
            next_dt = upcoming.index.min()
            cet_dt = next_dt.tz_convert(cet)

            name = market_data.get_info(ticker).get("shortName") or ticker

            eps_est = upcoming.loc[next_dt, "EPS Estimate"]
            result.append({
                "ticker": ticker,
                "name": name,
                "datetime_cet": cet_dt.isoformat(),
                "date": f"{cet_dt.day}.{cet_dt.month}.",
                "time": cet_dt.strftime("%H:%M"),
                "eps_estimate": round(float(eps_est), 2) if pd.notna(eps_est) else None,
            })
        except Exception:
            continue

    return sorted(result, key=lambda r: r["datetime_cet"])


def aggregate_day_change(rows):
    """Pure: sum per-holding day P&L and the prior day's value, both in the
    display currency (each row carries its own fx multiplier)."""
    change = 0.0
    prev_value = 0.0
    for r in rows:
        shares, start, end, fx = r["shares"], r["start"], r["end"], r["fx"]
        change += shares * (end - start) * fx
        prev_value += shares * start * fx
    return change, prev_value


def _two_day_closes(tickers):
    """{ticker: (start_close, end_close)} from a 2-day window. Never raises."""
    if not tickers:
        return {}
    try:
        raw = yf.download(tickers, period="2d", auto_adjust=True, progress=False)
        if raw is None or raw.empty:
            return {}
        if len(tickers) == 1:
            closes = raw[["Close"]].rename(columns={"Close": tickers[0]})
        else:
            closes = raw["Close"] if "Close" in raw.columns else raw
    except Exception:
        return {}
    closes = closes.ffill().dropna(how="all")
    out = {}
    for ticker in tickers:
        if ticker not in closes.columns:
            continue
        col = closes[ticker].dropna()
        if len(col) < 2:
            continue
        out[ticker] = (float(col.iloc[0]), float(col.iloc[-1]))
    return out


@router.get("/movers")
def get_movers(
    period: str = "1d",
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    transactions = _portfolio_txns(db, pid).all()
    if not transactions:
        return {"gainers": [], "losers": []}

    active = _build_holdings(transactions)
    if not active:
        return {"gainers": [], "losers": []}

    tickers = list(active.keys())

    if period.lower() == "1d":
        closes_map = _two_day_closes(tickers)
        if not closes_map:
            return {"gainers": [], "losers": []}
        results = []
        for ticker in tickers:
            if ticker not in closes_map:
                continue
            start_price, end_price = closes_map[ticker]
            if start_price <= 0:
                continue
            change_pct = round(((end_price - start_price) / start_price) * 100, 2)
            price, name, currency = _fetch_price_and_info(ticker)
            shares = active[ticker]["shares"]
            results.append({
                "ticker": ticker, "name": name,
                "current_price": round(end_price, 2),
                "change_pct": change_pct,
                "period_pnl": round(shares * (end_price - start_price), 2),
                "currency": currency,
            })
        results.sort(key=lambda x: x["change_pct"], reverse=True)
        return {
            "gainers": results[:5],
            "losers": list(reversed(results[-5:])) if len(results) >= 5 else list(reversed(results)),
        }

    period_map = {"1d": "2d", "1w": "7d", "1m": "1mo"}
    yf_period = period_map.get(period.lower(), "2d")

    try:
        raw = yf.download(tickers, period=yf_period, auto_adjust=True, progress=False)
        if raw.empty:
            return {"gainers": [], "losers": []}
        if len(tickers) == 1:
            closes = raw[["Close"]].rename(columns={"Close": tickers[0]})
        else:
            closes = raw["Close"] if "Close" in raw.columns else raw
    except Exception:
        return {"gainers": [], "losers": []}

    closes = closes.ffill().dropna(how="all")
    if len(closes) < 2:
        return {"gainers": [], "losers": []}

    results = []
    for ticker in tickers:
        if ticker not in closes.columns:
            continue
        col = closes[ticker].dropna()
        if len(col) < 2:
            continue
        start_price = float(col.iloc[0])
        end_price = float(col.iloc[-1])
        if start_price <= 0:
            continue
        change_pct = round(((end_price - start_price) / start_price) * 100, 2)
        price, name, currency = _fetch_price_and_info(ticker)
        shares = active[ticker]["shares"]
        period_pnl = round(shares * (end_price - start_price), 2)
        results.append({
            "ticker": ticker,
            "name": name,
            "current_price": round(end_price, 2),
            "change_pct": change_pct,
            "period_pnl": period_pnl,
            "currency": currency,
        })

    results.sort(key=lambda x: x["change_pct"], reverse=True)
    return {
        "gainers": results[:5],
        "losers": list(reversed(results[-5:])) if len(results) >= 5 else list(reversed(results)),
    }


@router.get("/heatmap")
def get_heatmap(
    period: str = "1d",
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    transactions = _portfolio_txns(db, pid).all()
    if not transactions:
        return []

    active = _build_holdings(transactions)
    if not active:
        return []

    tickers = list(active.keys())
    # Resolve broker symbols to Yahoo-recognised ones (same map the rest of the
    # app uses) so a held stock Yahoo only carries under an alternate listing
    # still shows up instead of being silently dropped below.
    yf_map = {t: yf_symbol(t) for t in tickers}
    yf_tickers = list(dict.fromkeys(yf_map.values()))
    p = period.lower()
    period_map = {
        "1d": "2d", "1w": "7d", "1m": "1mo",
        "3m": "3mo", "1y": "1y", "5y": "5y",
    }

    from datetime import date
    today = date.today()
    start_date = None
    if p == "mtd":
        start_date = today.replace(day=1)
    elif p == "ytd":
        start_date = today.replace(month=1, day=1)

    try:
        if start_date is not None:
            raw = yf.download(yf_tickers, start=start_date.strftime("%Y-%m-%d"),
                              auto_adjust=True, progress=False)
        else:
            yf_period = period_map.get(p, "2d")
            raw = yf.download(yf_tickers, period=yf_period,
                              auto_adjust=True, progress=False)
        if raw.empty:
            return []
        if len(yf_tickers) == 1:
            closes = raw[["Close"]].rename(columns={"Close": yf_tickers[0]})
        else:
            closes = raw["Close"] if "Close" in raw.columns else raw
    except Exception:
        return []

    closes = closes.ffill().dropna(how="all")
    if len(closes) < 2:
        return []

    total_value = 0.0
    holdings_data = []
    for ticker in tickers:
        ysym = yf_map[ticker]
        if ysym not in closes.columns:
            continue
        col = closes[ysym].dropna()
        if len(col) < 2:
            continue
        end_price = float(col.iloc[-1])
        start_price = float(col.iloc[0])
        shares = active[ticker]["shares"]
        value = shares * end_price
        change_pct = ((end_price - start_price) / start_price * 100) if start_price > 0 else 0
        total_value += value
        holdings_data.append({
            "ticker": ticker,
            "value": value,
            "change_pct": round(change_pct, 2),
        })

    for h in holdings_data:
        h["weight"] = round((h["value"] / total_value * 100) if total_value > 0 else 0, 2)
        del h["value"]

    return sorted(holdings_data, key=lambda x: -x["weight"])


BENCHMARK_TICKERS = {
    "sp500": "^GSPC",
    "nasdaq100": "^NDX",
    "dowjones": "^DJI",
    "stoxx50": "^STOXX50E",
    "bitcoin": "BTC-USD",
}


@router.get("/benchmarks")
def get_benchmarks(
    benchmarks: str = "",
    period: str = "all",
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    if not benchmarks:
        return {}

    keys = [b.strip().lower() for b in benchmarks.split(",") if b.strip().lower() in BENCHMARK_TICKERS]
    if not keys:
        return {}

    transactions = _portfolio_txns(db, pid).order_by(Transaction.date).all()
    first_txn_date = transactions[0].date if transactions else datetime.now().date()
    start_date = _resolve_start_date(period, first_txn_date)
    first_date = start_date.strftime("%Y-%m-%d")

    result = {}
    for key in keys:
        ticker = BENCHMARK_TICKERS[key]
        try:
            raw = yf.download(ticker, start=first_date, auto_adjust=True, progress=False)
            if raw.empty:
                continue
            close_col = raw["Close"]
            if hasattr(close_col, "squeeze"):
                close_col = close_col.squeeze()
            close_col = close_col.dropna()
            if close_col.empty:
                continue
            base = float(close_col.iloc[0])
            if base <= 0:
                continue
            data = []
            for idx, val in close_col.items():
                v = float(val)
                if pd.notna(v):
                    data.append({
                        "date": str(idx.date()) if hasattr(idx, "date") else str(idx),
                        "pct": round(((v - base) / base) * 100, 2),
                    })
            result[key] = data
        except Exception:
            continue

    return result


_insider_buys_cache: dict[int, tuple[float, list]] = {}
_INSIDER_BUYS_TTL = 1800  # 30 minutes


@router.get("/insider-buys")
def get_insider_buys(
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    """Insider buys in the last 12 months across all current holdings.
    Cached for 30 min to avoid hammering yfinance."""
    import time
    from datetime import timedelta
    from routers.market import _build_insider_transactions

    now = time.time()
    cached = _insider_buys_cache.get(pid)
    if cached and now - cached[0] < _INSIDER_BUYS_TTL:
        return cached[1]

    transactions = _portfolio_txns(db, pid).all()
    if not transactions:
        return []

    all_data = _build_holdings(transactions, include_closed=False)
    active_tickers = [t for t, d in all_data.items() if d["shares"] > 0.0001]

    cutoff = datetime.now() - timedelta(days=365)
    results = []
    prices: dict[str, float] = {}

    for ticker in active_tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info or {}
            current_price = info.get("currentPrice") or info.get("regularMarketPrice")
            if current_price is not None:
                prices[ticker] = float(current_price)

            insider_txns = _build_insider_transactions(stock, limit=200)
            for txn in insider_txns:
                if txn["side"] != "buy":
                    continue
                if not txn["date"]:
                    continue
                try:
                    txn_date = datetime.strptime(txn["date"], "%Y-%m-%d")
                except (ValueError, TypeError):
                    continue
                if txn_date < cutoff:
                    continue

                shares = txn["shares"]
                value = txn["value"]
                buy_price = None
                if shares and shares > 0 and value is not None:
                    buy_price = round(abs(value) / abs(shares), 2)

                pnl = None
                pnl_pct = None
                cp = prices.get(ticker)
                if buy_price and buy_price > 0 and cp is not None and shares:
                    pnl = round((cp - buy_price) * abs(shares), 2)
                    pnl_pct = round((cp / buy_price - 1) * 100, 2)

                results.append({
                    "ticker": ticker,
                    "insider": txn["insider"],
                    "position": txn["position"],
                    "shares": shares,
                    "value": value,
                    "buy_price": buy_price,
                    "current_price": cp,
                    "pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "date": txn["date"],
                })
        except Exception:
            continue

    results.sort(key=lambda r: r["date"] or "", reverse=True)
    _insider_buys_cache[pid] = (now, results)
    return results
