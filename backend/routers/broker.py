from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import httpx
import base64
import yfinance as yf

from database import get_db
from models import BrokerConnection, Transaction
from routers.portfolios import require_portfolio
from auth import get_current_user

router = APIRouter(prefix="/broker", tags=["broker"])

T212_BASES = {
    "live": "https://live.trading212.com/api/v0",
    "demo": "https://demo.trading212.com/api/v0",
}


def _t212_base(environment: str) -> str:
    return T212_BASES.get(environment, T212_BASES["live"])


def _t212_headers(api_key: str, api_secret: str = "") -> dict:
    if api_secret:
        credentials = base64.b64encode(f"{api_key}:{api_secret}".encode()).decode()
        return {"Authorization": f"Basic {credentials}"}
    return {"Authorization": api_key}


_T212_TICKER_RENAMES = {
    "AGC": "GRAB",
    "IPOE": "SOFI",
    "IVAN": "SES",
    "IPXX": "USAR",
    "RSTN": "GIFT",
    "OAC": "HIMS",
    "LION": "SMX",
    # SPAC tickers that already de-SPAC'd into the named operating company
    "SNII": "RGTI",
    # Renamed US listings that T212 still reports under the old ticker
    "FB": "META",
    "PCLN": "BKNG",
    # Class shares — Yahoo uses dash, T212 uses underscore
    "BRK_B": "BRK-B",
    "BRK_A": "BRK-A",
    # LSE-listed UCITS ETFs whose base ticker doesn't carry a T212 exchange suffix
    "CSPX": "CSPX.L",
    "CNDX": "CNDX.L",
    "IITU": "IITU.L",
}

# T212 appends a single lowercase letter to denote the listing exchange / currency
# variant (e.g. NVDd = Nvidia on Xetra). Map each to its Yahoo Finance suffix.
_T212_EXCHANGE_SUFFIX = {
    "l": ".L",   # London (GBX)
    "p": ".L",   # London (GBP)
    "s": ".L",   # London (USD)
    "d": ".DE",  # Xetra / Frankfurt
    "a": ".AS",  # Euronext Amsterdam
    "m": ".MI",  # Borsa Italiana / Milan
}


def _normalize_t212_ticker(t212_ticker: str) -> str:
    ticker = t212_ticker.strip()
    for suffix in ("_US_EQ", "_EQ"):
        if ticker.endswith(suffix):
            ticker = ticker[:-len(suffix)]
            break
    if ticker in _T212_TICKER_RENAMES:
        return _T212_TICKER_RENAMES[ticker]
    # Lowercase trailing letter on an otherwise upper-case ticker = T212 exchange tag.
    if len(ticker) >= 2 and ticker[-1].islower() and ticker[:-1].isupper():
        yahoo_suffix = _T212_EXCHANGE_SUFFIX.get(ticker[-1])
        if yahoo_suffix:
            return ticker[:-1] + yahoo_suffix
    return ticker


import re as _re
_CANONICAL_TICKER = _re.compile(r"^[A-Z0-9]+([.\-][A-Z0-9]+)?$")


def _split_adjust(txns_by_ticker: dict) -> int:
    """Rewrite buy/sell rows that were booked at pre-split prices.

    T212 reports historical orders at the price/quantity at the time of the trade and
    does NOT split-adjust them. For each yfinance-known split (ex-date D, ratio R) we
    rewrite shares*=R, price/=R for any txn where BOTH hold:
      - txn.date <= D (so it's not already a post-split trade)
      - txn.price / current_price ≈ R (price is on the pre-split scale)

    The price-ratio check protects against fuzzy yfinance matches: e.g. T212's "NVDd"
    (German Nvidia) gets matched by yfinance to the unrelated "NVDD" inverse ETF, and
    without this guard we'd apply that ETF's splits to Nvidia trades. We also skip
    any ticker that doesn't look canonical (upper-case + optional .X or -X suffix).
    """
    adjusted = 0
    for ticker, txns in txns_by_ticker.items():
        if not txns or not _CANONICAL_TICKER.match(ticker):
            continue
        try:
            yft = yf.Ticker(ticker)
            splits = yft.splits
            if splits is None or len(splits) == 0:
                continue
            try:
                ref_price = float(yft.fast_info["last_price"] or 0)
            except Exception:
                ref_price = 0.0
            if ref_price <= 0:
                continue
            for split_dt, ratio in splits.items():
                ex_date = split_dt.date()
                ratio = float(ratio)
                if ratio <= 0:
                    continue
                lo, hi = 0.5 * ratio, 2.0 * ratio
                for t in txns:
                    if t.date > ex_date:
                        continue
                    rel = t.price / ref_price
                    if lo <= rel <= hi:
                        t.shares *= ratio
                        t.price /= ratio
                        adjusted += 1
        except Exception:
            continue
    return adjusted


def _drop_corporate_action_pairs(db: Session, txns_by_ticker: dict) -> int:
    """Delete buy+sell pairs created by broker share give-backs on stock-split days.

    After a split, T212 records a sell of the pre-split position and a buy of the
    post-split equivalent on the ex-date — purely a broker adjustment, not user
    trading. We only remove a pair when (a) shares & price are identical, AND
    (b) the date matches a known yfinance split ex-date for that ticker. Without
    the split-date guard we'd also delete legitimate same-day round-trips at the
    same price (rare but they happen with zero-spread small caps).
    """
    removed = 0
    for ticker, txns in txns_by_ticker.items():
        if not txns or not _CANONICAL_TICKER.match(ticker):
            continue
        try:
            splits = yf.Ticker(ticker).splits
        except Exception:
            continue
        if splits is None or len(splits) == 0:
            continue
        split_dates = {dt.date() for dt in splits.index}
        by_date: dict = {}
        for t in txns:
            if t.date in split_dates:
                by_date.setdefault(t.date, []).append(t)
        for group in by_date.values():
            buys = [t for t in group if t.type == "buy"]
            sells = [t for t in group if t.type == "sell"]
            for b in buys:
                match = None
                for s in sells:
                    if abs(b.shares - s.shares) < 1e-9 and abs(b.price - s.price) < 1e-6:
                        match = s
                        break
                if match is not None:
                    sells.remove(match)
                    db.delete(b)
                    db.delete(match)
                    removed += 2
    return removed


def _get_connection(db: Session, pid: int) -> BrokerConnection | None:
    return (
        db.query(BrokerConnection)
        .filter(BrokerConnection.broker == "trading212", BrokerConnection.portfolio_id == pid)
        .first()
    )


@router.get("/trading212/status")
def get_status(db: Session = Depends(get_db), pid: int = Depends(require_portfolio)):
    conn = _get_connection(db, pid)
    if not conn:
        return {"connected": False, "portfolio_id": pid}
    return {
        "connected": True,
        "portfolio_id": pid,
        "auto_sync": conn.auto_sync,
        "environment": conn.environment or "live",
        "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
        "connected_at": conn.created_at.isoformat() if conn.created_at else None,
        "api_key_preview": conn.api_key[:6] + "..." + conn.api_key[-4:] if len(conn.api_key) > 10 else "***",
    }


@router.post("/trading212/connect")
def connect(payload: dict, db: Session = Depends(get_db), pid: int = Depends(require_portfolio), owner: str = Depends(get_current_user)):
    api_key = payload.get("api_key", "").strip()
    api_secret = payload.get("api_secret", "").strip()
    environment = payload.get("environment", "live").strip().lower()
    if environment not in T212_BASES:
        environment = "live"
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")

    # Reject reusing the same API key on a different portfolio — mixing two portfolios
    # backed by the same upstream account is exactly what this feature is meant to prevent.
    clash = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.broker == "trading212",
            BrokerConnection.api_key == api_key,
            BrokerConnection.portfolio_id != pid,
        )
        .first()
    )
    if clash:
        raise HTTPException(
            status_code=409,
            detail="This API key is already connected to a different portfolio. "
                   "Each portfolio must use its own Trading 212 API key.",
        )

    base = _t212_base(environment)
    try:
        resp = httpx.get(f"{base}/equity/account/info", headers=_t212_headers(api_key, api_secret), timeout=10)
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="Invalid API key")
        if resp.status_code == 403:
            raise HTTPException(status_code=403, detail="API key does not have the required permissions")
        if resp.status_code == 429:
            raise HTTPException(status_code=429, detail="Too many requests — Trading 212 rate limit hit. Try again in a minute.")
        resp.raise_for_status()
    except HTTPException:
        raise
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Trading 212 returned an error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Trading 212: {e}")

    # Wipe only THIS portfolio's transactions, never others.
    db.query(Transaction).filter(Transaction.portfolio_id == pid).delete(synchronize_session=False)

    existing = _get_connection(db, pid)
    if existing:
        existing.api_key = api_key
        existing.api_secret = api_secret
        existing.environment = environment
        existing.created_at = datetime.utcnow()
        existing.last_synced_at = None
    else:
        db.add(BrokerConnection(
            broker="trading212",
            api_key=api_key,
            api_secret=api_secret,
            environment=environment,
            portfolio_id=pid,
            owner_id=owner,
        ))
    db.commit()
    return {"ok": True, "message": "Connected to Trading 212"}


@router.delete("/trading212/connect")
def disconnect(db: Session = Depends(get_db), pid: int = Depends(require_portfolio)):
    conn = _get_connection(db, pid)
    if not conn:
        raise HTTPException(status_code=404, detail="No Trading 212 connection found")
    db.delete(conn)
    db.commit()
    return {"ok": True, "message": "Disconnected from Trading 212"}


@router.post("/trading212/sync")
def sync_transactions(db: Session = Depends(get_db), pid: int = Depends(require_portfolio), owner: str = Depends(get_current_user)):
    # owner is resolved through the single identity source for consistency with the
    # other broker endpoints; T212 sync writes only portfolio-scoped Transaction rows
    # (no owner_id of their own) so there is nothing to stamp here.
    conn = _get_connection(db, pid)
    if not conn:
        raise HTTPException(status_code=404, detail="Trading 212 is not connected")

    base = _t212_base(conn.environment or "live")
    headers = _t212_headers(conn.api_key, conn.api_secret or "")
    imported = 0
    errors = []

    try:
        orders = _fetch_all_orders(base, headers)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch orders: {e}")

    existing_sources = set()
    new_orders_by_ticker: dict[str, list[Transaction]] = {}
    # Dedup only within THIS portfolio — another portfolio holding the same ticker
    # at the same date/price is not a duplicate, it's separate data.
    t212_txns = (
        db.query(Transaction)
        .filter(Transaction.source == "t212_api", Transaction.portfolio_id == pid)
        .all()
    )
    for t in t212_txns:
        existing_sources.add(f"{t.ticker}_{t.date}_{t.type}_{t.shares}_{t.price}")
        if t.type == "dividend":
            existing_sources.add(f"{t.ticker}_{t.date}_dividend_{round(t.shares * t.price, 6)}")

    for item in orders:
        try:
            order_data = item.get("order", {})
            fill_data = item.get("fill", {})

            status = order_data.get("status", "").upper()
            if status != "FILLED":
                continue

            raw_ticker = order_data.get("ticker", "").strip()
            if not raw_ticker:
                continue
            ticker = _normalize_t212_ticker(raw_ticker)

            side = order_data.get("side", "").upper()
            if side == "BUY":
                txn_type = "buy"
            elif side == "SELL":
                txn_type = "sell"
            else:
                continue

            filled_qty = abs(fill_data.get("quantity") or order_data.get("filledQuantity", 0))
            filled_price = fill_data.get("price", 0)
            if not filled_qty or not filled_price:
                continue

            instrument = order_data.get("instrument", {})
            currency = instrument.get("currency", "USD").upper()

            date_str = fill_data.get("filledAt") or order_data.get("createdAt", "")
            try:
                txn_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
            except Exception:
                continue

            name = instrument.get("name", ticker)

            dedup_key = f"{ticker}_{txn_date}_{txn_type}_{filled_qty}_{filled_price}"
            if dedup_key in existing_sources:
                continue

            new_txn = Transaction(
                portfolio_id=pid,
                ticker=ticker,
                name=name,
                type=txn_type,
                shares=float(filled_qty),
                price=float(filled_price),
                currency=currency,
                date=txn_date,
                notes=f"T212 Order #{order_data.get('id', '')}",
                source="t212_api",
            )
            db.add(new_txn)
            new_orders_by_ticker.setdefault(ticker, []).append(new_txn)
            existing_sources.add(dedup_key)
            imported += 1
        except Exception as e:
            errors.append(str(e))

    dividends_imported = 0
    try:
        dividends = _fetch_all_dividends(base, headers)
        for div in dividends:
            try:
                raw_ticker = div.get("ticker", "").strip()
                if not raw_ticker:
                    continue
                ticker = _normalize_t212_ticker(raw_ticker)
                gross_per_share = div.get("grossAmountPerShare", 0)
                quantity = div.get("quantity", 0)
                if not gross_per_share or not quantity:
                    continue
                total_amount = round(float(gross_per_share) * float(quantity) * 0.85, 6)
                instrument = div.get("instrument", {})
                div_currency = instrument.get("currency", "USD").upper()

                date_str = div.get("paidOn") or div.get("reference", "")
                try:
                    txn_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).date()
                except Exception:
                    continue

                dedup_key = f"{ticker}_{txn_date}_dividend_{total_amount}"
                if dedup_key in existing_sources:
                    continue

                db.add(Transaction(
                    portfolio_id=pid,
                    ticker=ticker,
                    name=ticker,
                    type="dividend",
                    shares=1.0,
                    price=total_amount,
                    currency=div_currency,
                    date=txn_date,
                    notes="T212 Dividend",
                    source="t212_api",
                ))
                existing_sources.add(dedup_key)
                dividends_imported += 1
            except Exception as e:
                errors.append(str(e))
    except Exception as e:
        errors.append(f"Dividend fetch failed: {e}")

    _split_adjust(new_orders_by_ticker)
    _drop_corporate_action_pairs(db, new_orders_by_ticker)

    conn.last_synced_at = datetime.utcnow()
    db.commit()

    return {
        "imported_orders": imported,
        "imported_dividends": dividends_imported,
        "total_imported": imported + dividends_imported,
        "errors": errors,
    }


def _extract_cursor(next_page_path: str) -> str | None:
    if not next_page_path:
        return None
    parsed = urlparse(next_page_path)
    params = parse_qs(parsed.query)
    cursors = params.get("cursor")
    return cursors[0] if cursors else None


def _fetch_all_orders(base: str, headers: dict) -> list:
    all_orders = []
    cursor = None
    while True:
        params = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        resp = httpx.get(f"{base}/equity/history/orders", headers=headers, params=params, timeout=15)
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="API key is invalid or expired")
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        all_orders.extend(items)
        next_path = data.get("nextPagePath")
        if not next_path or not items:
            break
        cursor = _extract_cursor(next_path)
        if not cursor:
            break
    return all_orders


def _fetch_all_dividends(base: str, headers: dict) -> list:
    all_divs = []
    cursor = None
    while True:
        params = {"limit": 50}
        if cursor:
            params["cursor"] = cursor
        resp = httpx.get(f"{base}/equity/history/dividends", headers=headers, params=params, timeout=15)
        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="API key is invalid or expired")
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items", [])
        all_divs.extend(items)
        next_path = data.get("nextPagePath")
        if not next_path or not items:
            break
        cursor = _extract_cursor(next_path)
        if not cursor:
            break
    return all_divs
