from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
import yfinance as yf
import pandas as pd
import pytz
import io
import logging
from datetime import datetime

from database import get_db
from models import Transaction
from cash_ledger import TRADE_TYPES, POSITION_TYPES
from schemas import TransactionCreate, TransactionResponse
from fx import fetch_fx_to_czk, bulk_fetch_fx
from routers.portfolios import require_portfolio
from ticker_map import yf_symbol
import market_data

router = APIRouter(prefix="/portfolio", tags=["portfolio"])

# ---------------------------------------------------------------------------
# Trading 212 CSV normalisation
# ---------------------------------------------------------------------------

_T212_SIGNATURE = {"action", "no. of shares", "price / share", "ticker"}

_T212_BUY_ACTIONS = {
    "market buy", "limit buy", "stop buy", "buy"
}
_T212_SELL_ACTIONS = {
    "market sell", "limit sell", "stop sell", "sell"
}
# Cash movements mapped 1:1 onto ledger types (amount = |Total|, direction from type).
_T212_CASH_ACTIONS = {
    "deposit": "deposit",
    "withdrawal": "withdrawal",
    "interest on cash": "interest",
    "lending interest": "interest",
    "card debit": "card_debit",
    "spending cashback": "cashback",
}
_T212_SKIP_ACTIONS = {
    "cash in", "cash out", "result from positions",
}


def _is_t212(cols: set) -> bool:
    return _T212_SIGNATURE.issubset(cols) and bool({"time", "time (utc)"} & cols)


def _t212_action_to_type(action: str) -> str | None:
    a = action.strip().lower()
    if a in _T212_BUY_ACTIONS:
        return "buy"
    if a in _T212_SELL_ACTIONS:
        return "sell"
    if "dividend" in a:
        return "dividend"
    if a in _T212_CASH_ACTIONS:
        return _T212_CASH_ACTIONS[a]
    return None  # lending interest / unknown → skip


def _t212_num(row, col) -> float | None:
    v = row.get(col)
    if v is None or pd.isna(v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _t212_str(row, col, default="") -> str:
    v = row.get(col)
    if v is None or pd.isna(v):
        return default
    s = str(v).strip()
    return s if s and s.upper() != "NAN" else default


def _normalize_t212(df: pd.DataFrame) -> tuple[list[dict], int]:
    """Convert a T212 DataFrame into a list of normalised row dicts.

    Everything in a T212 export settles in the account currency: the `Total`
    column is the exact cash impact (buy totals include the FX fee, sell totals
    are net of it), stored as cash_amount/cash_currency so trades move the cash
    pile. Deposits, withdrawals, interest, card debits and cashback become cash
    rows; a currency conversion becomes fx_out + fx_in (+ fee) legs.

    Returns (rows, skipped_count).
    """
    rows, skipped = [], 0
    for _, row in df.iterrows():
        raw_action = str(row.get("action", "")).strip()
        try:
            raw_time = row.get("time (utc)")
            if raw_time is None or pd.isna(raw_time):
                raw_time = row.get("time")
            txn_date = pd.to_datetime(str(raw_time), utc=True).date()
        except Exception:
            skipped += 1
            continue

        total = _t212_num(row, "total")
        total_ccy = _t212_str(row, "currency (total)", "CZK").upper()
        action_lc = raw_action.lower()

        if action_lc == "adr fee":
            shares = _t212_num(row, "no. of shares") or 0.0
            price = _t212_num(row, "price / share") or 0.0
            amount = abs(total) if total else abs(shares * price)
            currency = total_ccy if total and total_ccy else \
                _t212_str(row, "currency (price / share)", "USD").upper()
            if amount <= 0:
                skipped += 1
                continue
            ticker = _t212_str(row, "ticker").upper()
            rows.append({"ticker": None, "name": None, "type": "fee",
                         "shares": 0.0, "price": 0.0, "amount": amount,
                         "currency": currency, "date": txn_date,
                         "notes": f"T212: ADR fee{f' ({ticker})' if ticker else ''}"})
            continue

        if action_lc in {"stock split open", "stock split close"}:
            ticker = _t212_str(row, "ticker").upper()
            shares = _t212_num(row, "no. of shares")
            price = _t212_num(row, "price / share")
            if not ticker or shares is None or price is None:
                skipped += 1
                continue
            currency = _t212_str(row, "currency (price / share)", "USD").upper()
            rate = _t212_num(row, "exchange rate")
            fx_to_czk = 1.0 if currency == "CZK" else (1.0 / rate if rate else None)
            rows.append({
                "ticker": ticker,
                "name": _t212_str(row, "name", ticker),
                "type": "split_open" if action_lc.endswith("open") else "split_close",
                "shares": abs(shares),
                "price": abs(price),
                "currency": currency,
                "date": txn_date,
                "notes": f"T212: {raw_action}",
                "fx_to_czk": fx_to_czk,
                "cash_amount": None,
                "cash_currency": None,
            })
            continue

        if action_lc == "currency conversion":
            from_amt = _t212_num(row, "currency conversion from amount")
            from_ccy = _t212_str(row, "currency (currency conversion from amount)").upper()
            to_amt = _t212_num(row, "currency conversion to amount")
            to_ccy = _t212_str(row, "currency (currency conversion to amount)").upper()
            note = _t212_str(row, "notes", raw_action)
            if from_amt and from_ccy:
                rows.append({"ticker": None, "name": None, "type": "fx_out",
                             "shares": 0.0, "price": 0.0, "amount": abs(from_amt),
                             "currency": from_ccy, "date": txn_date, "notes": f"T212: {note}"})
            if to_amt and to_ccy:
                rows.append({"ticker": None, "name": None, "type": "fx_in",
                             "shares": 0.0, "price": 0.0, "amount": abs(to_amt),
                             "currency": to_ccy, "date": txn_date, "notes": f"T212: {note}"})
            if total:
                rows.append({"ticker": None, "name": None, "type": "fee",
                             "shares": 0.0, "price": 0.0, "amount": abs(total),
                             "currency": total_ccy, "date": txn_date,
                             "notes": "T212: Currency conversion fee"})
            continue

        txn_type = _t212_action_to_type(raw_action)
        if txn_type is None:
            skipped += 1
            continue

        if txn_type in _T212_CASH_ACTIONS.values():
            if not total:
                skipped += 1
                continue
            if txn_type == "card_debit":
                merchant = _t212_str(row, "merchant name")
                category = _t212_str(row, "merchant category")
                note = f"Card: {merchant}" + (f" ({category})" if category else "") \
                    if merchant else "T212: Card debit"
            else:
                note = f"T212: {_t212_str(row, 'notes', raw_action)}"
            rows.append({"ticker": None, "name": None, "type": txn_type,
                         "shares": 0.0, "price": 0.0, "amount": abs(total),
                         "currency": total_ccy, "date": txn_date, "notes": note})
            continue

        # Trade / dividend rows
        ticker = _t212_str(row, "ticker").upper()
        shares = _t212_num(row, "no. of shares")
        price = _t212_num(row, "price / share")
        if not ticker or shares is None or price is None:
            skipped += 1
            continue

        currency = _t212_str(row, "currency (price / share)", "USD").upper()
        rate = _t212_num(row, "exchange rate")

        # fx_to_czk: exact from the export rather than a yfinance lookup.
        # Trades quote `Exchange rate` as price-ccy per 1 CZK (~0.048 for USD);
        # dividends quote it inverted, CZK per 1 price-ccy (~21) -- for those,
        # Total / (shares*price) reproduces it exactly, fees don't apply.
        fx_to_czk = None
        if currency == "CZK" or total_ccy != "CZK":
            fx_to_czk = 1.0 if currency == "CZK" else None
        elif txn_type == "dividend":
            if total and shares and price:
                fx_to_czk = abs(total) / (shares * price)
            elif rate:
                fx_to_czk = rate
        elif rate:
            fx_to_czk = 1.0 / rate

        rows.append({
            "ticker": ticker,
            "name": _t212_str(row, "name", ticker),
            "type": txn_type,
            "shares": shares,
            "price": price,
            "currency": currency,
            "date": txn_date,
            "notes": f"T212: {raw_action}",
            "fx_to_czk": fx_to_czk,
            "cash_amount": abs(total) if total else None,
            "cash_currency": total_ccy if total else None,
        })

    return rows, skipped


def _fetch_price_and_info(ticker: str) -> tuple[float, str, str]:
    # Bounded + cached: see market_data. A delisted/thin ticker can no longer
    # hang the whole request, and repeat lookups (e.g. /summary right after
    # /holdings) hit the TTL cache instead of re-querying Yahoo.
    return market_data.quote(market_data.get_info(ticker), ticker)


def _pence_to_pounds(price: float, ccy: str) -> tuple[float, str]:
    """LSE quotes arrive in pence ('GBp'/'GBX') while FX rates are per pound:
    valuation must convert pence → pounds before applying the GBP rate, or the
    position is overstated 100x. Per-share *display* prices stay in pence (the
    frontend renders them with a 'p' suffix, matching the txn history)."""
    if (ccy or "") in ("GBp", "GBX"):
        return price / 100.0, "GBP"
    return price, ccy


_TXN_TYPE_ORDER = {"buy": 0, "split_close": 1, "split_open": 2, "dividend": 3, "sell": 4}


def _portfolio_txns(db: Session, pid: int):
    return db.query(Transaction).filter(Transaction.portfolio_id == pid)


def _build_holdings(transactions: list, include_closed: bool = False,
                    display_ccy: str | None = None) -> dict:
    """Aggregate per-ticker shares, cost, dividends and realized P&L.

    display_ccy=None leaves money values in each txn's native currency (fine for
    the many callers that only read `shares`). Passing a currency converts every
    value native -> CZK (historical per-txn snapshot) -> display (live rate)."""
    fx_fallback: dict[str, float] = {}
    disp_rate = _live_fx_to_czk(display_ccy, fx_fallback) if display_ccy else None
    holdings: dict[str, dict] = {}
    for txn in sorted(transactions, key=lambda t: (t.date, _TXN_TYPE_ORDER.get(t.type, 1))):
        if txn.type not in POSITION_TYPES or not txn.ticker:
            continue  # cash rows (deposit/withdrawal/fee/interest/...) never affect holdings
        t = txn.ticker
        if disp_rate:
            fx = (txn.fx_to_czk or _live_fx_to_czk(txn.currency, fx_fallback)) / disp_rate
        else:
            fx = 1.0
        if t not in holdings:
            # cost = cost basis in display currency (FX-applied). cost_native =
            # the same running total but FX-free, in the ticker's own currency,
            # so per-share prices (avg cost) can be shown natively (a US stock's
            # $150 avg stays $150, never converted to Kč).
            holdings[t] = {"shares": 0.0, "cost": 0.0, "cost_native": 0.0,
                           "dividends": 0.0, "realized_pnl": 0.0, "currency": txn.currency}
        if txn.type == "buy":
            holdings[t]["shares"] += txn.shares
            holdings[t]["cost"] += txn.shares * txn.price * fx
            holdings[t]["cost_native"] += txn.shares * txn.price
        elif txn.type == "sell":
            if holdings[t]["shares"] > 0:
                avg = holdings[t]["cost"] / holdings[t]["shares"]
                avg_native = holdings[t]["cost_native"] / holdings[t]["shares"]
                sold_shares = min(txn.shares, holdings[t]["shares"])
                holdings[t]["realized_pnl"] += sold_shares * (txn.price * fx - avg)
                holdings[t]["shares"] -= sold_shares
                holdings[t]["cost"] -= sold_shares * avg
                holdings[t]["cost_native"] -= sold_shares * avg_native
                holdings[t]["shares"] = max(0.0, holdings[t]["shares"])
                holdings[t]["cost"] = max(0.0, holdings[t]["cost"])
                holdings[t]["cost_native"] = max(0.0, holdings[t]["cost_native"])
        elif txn.type == "split_close":
            holdings[t]["shares"] = max(0.0, holdings[t]["shares"] - txn.shares)
        elif txn.type == "split_open":
            holdings[t]["shares"] += txn.shares
        elif txn.type == "dividend":
            holdings[t]["dividends"] += txn.shares * txn.price * fx
    if include_closed:
        return holdings
    return {k: v for k, v in holdings.items() if v["shares"] > 0.0001}


# Last successful live rate per currency, process-wide. A quote hiccup must not
# silently become "1 Kč per USD" — that once rendered every position at ≈ -95%.
_LAST_GOOD_FX: dict[str, float] = {}


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
        rate = fetch_fx_to_czk(c, datetime.now().date()) or _LAST_GOOD_FX.get(c) or 0.0
        if rate <= 0:
            # Truly cold start with no rate source at all. Don't cache or
            # remember the made-up 1.0 so the next lookup retries.
            logging.getLogger("portfyl.fx").warning(
                "No %s→CZK rate available (live quote, daily close and "
                "last-known-good all missing); falling back to 1.0", c)
            return 1.0
    _LAST_GOOD_FX[c] = rate
    cache[c] = rate
    return rate


@router.get("/transactions", response_model=List[TransactionResponse])
def get_transactions(db: Session = Depends(get_db), pid: int = Depends(require_portfolio)):
    # Trade rows only -- cash rows (deposit/withdrawal/fee/interest, ticker=None)
    # belong to the Cash ledger, not the Transactions page. Un-filtered, they leaked
    # in as blank rows and crashed the page's ticker-filter (`t.ticker.toLowerCase()`
    # on null).
    return (
        _portfolio_txns(db, pid)
        .filter(Transaction.type.in_(TRADE_TYPES))
        .order_by(Transaction.date.desc())
        .all()
    )


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
        # Manual trades settle from the CZK cash pile like imported ones; without
        # a rate we leave settlement unset and signed_cash falls back to native.
        cash_amount=round(txn.shares * txn.price * fx, 2) if fx else None,
        cash_currency="CZK" if fx else None,
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
        # A T212 export is the broker's full history: importing one always
        # replaces the portfolio's data (user-chosen overwrite semantics) so the
        # cash ledger reconciles with the broker instead of double-counting.
        replace = True

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
    # Backfill FX only where the normaliser couldn't derive an exact rate from
    # the file itself (T212 rows carry their own; CZK rows are 1.0).
    fx_needed = {(r["currency"], r["date"]) for r in new_rows if not r.get("fx_to_czk")}
    fx_map = bulk_fetch_fx(fx_needed)
    prepared: list[Transaction] = []
    for r in new_rows:
        try:
            if not r.get("fx_to_czk"):
                ccy = r["currency"].upper()
                r["fx_to_czk"] = 1.0 if ccy == "CZK" else fx_map.get((ccy, r["date"]))
            r["source"] = "csv"
            prepared.append(Transaction(**r, portfolio_id=pid))
        except Exception as e:
            errors.append(str(e))

    if errors:
        db.rollback()
        raise HTTPException(status_code=400, detail={"message": "CSV validation failed", "errors": errors})

    try:
        if replace:
            _portfolio_txns(db, pid).delete(synchronize_session=False)
        db.add_all(prepared)
        db.flush()
        imported = len(prepared)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Import rolled back: {e}")

    return {"imported": imported, "skipped": skipped, "errors": errors, "format": fmt,
            "replaced": replace, "events": len(df), "processed_events": len(df) - skipped}


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

    display_ccy = currency.upper()
    all_data = _build_holdings(transactions, include_closed=True, display_ccy=display_ccy)
    active = {k: v for k, v in all_data.items() if v["shares"] > 0.0001}
    # Warm the quote cache for every ticker in one concurrent, deadline-bounded
    # batch so the per-ticker _fetch_price_and_info calls below all hit the
    # cache instead of fanning out serial Yahoo requests. FX pairs ride in the
    # same batch: submitted separately they queue behind leftover warm-up work,
    # miss their own deadline, and the display converts at a bogus rate.
    fx_ccys = {display_ccy} | {(t.currency or "USD").upper() for t in transactions}
    market_data.get_infos(
        list(all_data.keys()) + [f"{c}CZK=X" for c in fx_ccys if c != "CZK"])
    result = []
    total_value = 0.0
    fx_cache: dict[str, float] = {}
    disp_rate = _live_fx_to_czk(display_ccy, fx_cache)

    for ticker, data in active.items():
        price, name, ticker_ccy = _fetch_price_and_info(ticker)
        value_price, fx_ccy = _pence_to_pounds(price, ticker_ccy)
        live_fx = _live_fx_to_czk(fx_ccy, fx_cache) / disp_rate
        market_value = data["shares"] * value_price * live_fx
        cost_basis = data["cost"]
        pnl = market_value - cost_basis
        pnl_pct = (pnl / cost_basis * 100) if cost_basis > 0 else 0
        # avg_cost is a per-share price → native currency (matches current_price,
        # which is also native), so it never gets an incorrect Kč label.
        avg_cost = data["cost_native"] / data["shares"] if data["shares"] > 0 else 0
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
                t = txn_totals.setdefault(txn.ticker, {
                    "bought_val": 0.0, "sold_val": 0.0,
                    "bought_val_native": 0.0, "sold_val_native": 0.0,
                    "bought_sh": 0.0, "sold_sh": 0.0})
                fx = (txn.fx_to_czk or _live_fx_to_czk(txn.currency, fx_cache)) / disp_rate
                if txn.type == "buy":
                    t["bought_val"] += txn.shares * txn.price * fx
                    t["bought_val_native"] += txn.shares * txn.price
                    t["bought_sh"] += txn.shares
                elif txn.type == "sell":
                    t["sold_val"] += txn.shares * txn.price * fx
                    t["sold_val_native"] += txn.shares * txn.price
                    t["sold_sh"] += txn.shares

        for ticker, data in closed.items():
            totals = txn_totals.get(ticker, {})
            cost = totals.get("bought_val", 0)
            realized = data["realized_pnl"]
            pnl_pct = (realized / cost * 100) if cost > 0 else 0
            bought_sh = totals.get("bought_sh", 0)
            # Per-share buy/sell prices → native currency (like open holdings),
            # so a sold US position doesn't render its prices as Kč.
            avg_buy = totals.get("bought_val_native", 0) / bought_sh if bought_sh else 0
            avg_sell = totals["sold_val_native"] / totals["sold_sh"] if totals.get("sold_sh") else 0

            # Hypothetical P&L if the position had been held to today instead
            # of sold. Uses live price * live FX (so it tracks the user's
            # currency view), against the buy cost expressed in that currency.
            live_price, _, live_ccy = _fetch_price_and_info(ticker)
            value_live, fx_ccy = _pence_to_pounds(live_price, live_ccy)
            live_fx = _live_fx_to_czk(fx_ccy, fx_cache) / disp_rate
            if bought_sh and live_price > 0:
                hypothetical_value = bought_sh * value_live * live_fx
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
                # live_price shown natively (USD), alongside the native avg buy/sell.
                "live_price": round(live_price, 2) if live_price else None,
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
    display_ccy = currency.upper()
    total_value = sum(h["market_value"] for h in holdings)
    total_invested = sum(h["cost_basis"] for h in holdings)
    unrealized_pnl = total_value - total_invested

    transactions = _portfolio_txns(db, pid).all()
    fx_fallback: dict[str, float] = {}
    disp_rate = _live_fx_to_czk(display_ccy, fx_fallback)

    def _txn_fx(t):
        return (t.fx_to_czk or _live_fx_to_czk(t.currency, fx_fallback)) / disp_rate

    total_dividends = sum(
        t.shares * t.price * _txn_fx(t) for t in transactions if t.type == "dividend"
    )
    total_interest = sum(
        (t.amount or 0.0) * _txn_fx(t) for t in transactions if t.type == "interest"
    )
    total_fees = sum(
        (t.amount or 0.0) * _txn_fx(t) for t in transactions if t.type == "fee"
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
        elif txn.type == "split_close":
            shares_open[txn.ticker] = max(
                0.0, shares_open.get(txn.ticker, 0.0) - txn.shares
            )
        elif txn.type == "split_open":
            shares_open[txn.ticker] = shares_open.get(txn.ticker, 0.0) + txn.shares

    total_pnl = unrealized_pnl + realized_pnl + total_dividends + total_interest - total_fees
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

    # Cash: guarded on external cashflows (deposit/withdrawal rows). A portfolio
    # with none (trades-only) does not surface cash at all -- net_worth ==
    # total_value -- avoiding a confusing negative/phantom cash figure for the
    # app's real trades-but-no-deposits user. When gated on, the displayed
    # "Cash" figure is FOLDED (balance + accrued interest) into one number so it
    # reconciles with net_worth; accrued is NOT added again below (no double-count).
    from cash_ledger import accrued_interest, has_external_cashflows
    from models import CashInterestRate
    from fx import cash_amount_to_display, folded_cash_display
    _rates = {r.currency: {"annual_rate": r.annual_rate, "enabled": r.enabled, "start_date": r.start_date}
              for r in db.query(CashInterestRate).filter(CashInterestRate.portfolio_id == pid).all()}
    if has_external_cashflows(transactions):
        cash_total = folded_cash_display(transactions, _rates, currency)  # balance + accrued, folded
        _accrued = accrued_interest(transactions, _rates)
        accrued_total = sum(cash_amount_to_display(v, ccy, currency) for ccy, v in _accrued.items())
    else:
        cash_total = 0.0
        accrued_total = 0.0
    # cash_total already includes accrued interest -- do NOT add accrued_total again.
    net_worth = total_value + cash_total

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
        "net_worth": round(net_worth, 2),
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


@router.get("/dividends/growth")
def get_dividend_growth(
    db: Session = Depends(get_db),
    pid: int = Depends(require_portfolio),
):
    """Per-holding dividend-growth stats (streak / CAGR / YoY / payout) for the
    active portfolio. Only dividend-paying holdings are returned."""
    from dividend_growth import compute_dividend_growth

    transactions = (
        db.query(Transaction)
        .filter(Transaction.portfolio_id == pid)
        .order_by(Transaction.date)
        .all()
    )
    if not transactions:
        return []

    active = _build_holdings(transactions)
    # First-wins: earliest non-null name per ticker (buy rows carry real names;
    # later dividend rows from API syncs carry name=ticker and must not overwrite).
    names: dict[str, str] = {}
    for t in transactions:
        if t.ticker and t.ticker not in names and t.name:
            names[t.ticker] = t.name

    rows = []
    for ticker in sorted(active.keys()):
        g = compute_dividend_growth(ticker)
        if not g.get("annual"):
            continue  # not a dividend payer — skip
        rows.append({
            "ticker": ticker,
            "name": names.get(ticker, ticker),
            "streak_years": g["streak_years"],
            "cagr_pct": g["cagr_pct"],
            "cagr_years_used": g["cagr_years_used"],
            "yoy_pct": g["yoy_pct"],
            "payout_ratio_pct": g["payout_ratio_pct"],
        })
    return rows


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
    # Imported full-history portfolios contain their actual cash ledger. Reuse
    # the analytics engine so this chart and risk metrics share one definition:
    # V = positions + cash in every currency; C = external flows only.
    from routers.analytics import (
        _build_value_cashflow_series,
        _modified_dietz_daily_returns,
        _resolve_window,
    )

    start_date, window_start = _resolve_window(transactions, period)
    V, C, _ = _build_value_cashflow_series(
        transactions, start_date, display_currency=currency
    )
    if V is None or V.empty:
        return []

    mask = V.index >= pd.Timestamp(window_start)
    window_values = V.loc[mask]
    if window_values.empty:
        return []
    window_flows = C.reindex(window_values.index).fillna(0.0)
    daily_returns = _modified_dietz_daily_returns(V, C, window_start)

    baseline = float(window_values.iloc[0])
    cumulative_external = 0.0
    cumulative_twr = 1.0
    result: list[dict] = []
    for i, (date_idx, value) in enumerate(window_values.items()):
        if i > 0:
            cumulative_external += float(window_flows.loc[date_idx])
            if date_idx in daily_returns.index:
                cumulative_twr *= 1.0 + float(daily_returns.loc[date_idx])
        pnl = float(value) - baseline - cumulative_external
        pnl_pct = (cumulative_twr - 1.0) * 100.0
        invested = baseline + cumulative_external
        result.append({
            "date": str(date_idx.date()),
            "value": round(float(value), 2),
            "invested": round(invested, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "total_pnl": round(pnl, 2),
            "total_pnl_pct": round(pnl_pct, 2),
        })

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
            ticker_ccy = info.get("currency", "USD")
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
                    # Insider filings are in the stock's native currency (USD for
                    # US listings), so the frontend must not stamp them with Kč.
                    "currency": ticker_ccy,
                })
        except Exception:
            continue

    results.sort(key=lambda r: r["date"] or "", reverse=True)
    _insider_buys_cache[pid] = (now, results)
    return results
