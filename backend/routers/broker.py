from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime, timezone
from urllib.parse import urlparse, parse_qs
import httpx
import base64
import os
import yfinance as yf

from audit import record_audit_event
from database import get_db
from entitlements import require_broker_capacity, require_capability, require_writable_broker
from rate_limit import rate_limit
from fx import bulk_fetch_fx
from models import BrokerConnection, Portfolio, Transaction
from tenancy import RequestContext, require_csrf, require_portfolio
from cash_ledger import CASH_TYPES

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


def _dedup_keys(ticker: str, *parts) -> set[str]:
    """Dedup keys under the row's ticker AND its exchange-suffix-stripped base
    ('COPM.L' → 'COPM'), so API-normalized tickers match the raw tickers the
    CSV import stores. Class-share dashes (BRK-B) are left alone."""
    tail = "_".join(str(p) for p in parts)
    keys = {f"{ticker}_{tail}"}
    base = (ticker or "").split(".")[0]
    if base != ticker:
        keys.add(f"{base}_{tail}")
    return keys


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


def _get_connection(db: Session, portfolio: Portfolio) -> BrokerConnection | None:
    return (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.workspace_id == portfolio.workspace_id,
            BrokerConnection.broker == "trading212",
            BrokerConnection.portfolio_id == portfolio.id,
        )
        .first()
    )


@router.get("/trading212/status")
def get_status(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    conn = _get_connection(db, portfolio)
    if not conn:
        return {"connected": False, "portfolio_id": str(portfolio.public_id)}
    return {
        "connected": True,
        "id": str(conn.public_id),
        "portfolio_id": str(portfolio.public_id),
        "auto_sync": conn.auto_sync,
        "environment": conn.environment or "live",
        "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
        "connected_at": conn.created_at.isoformat() if conn.created_at else None,
        "api_key_preview": conn.api_key[:6] + "..." + conn.api_key[-4:] if len(conn.api_key) > 10 else "***",
        "needs_attention": conn.needs_attention,
        "last_error": conn.last_error if conn.needs_attention else None,
    }


@router.post(
    "/trading212/connect",
    dependencies=[Depends(require_capability("broker_sync")), Depends(require_broker_capacity("trading212"))],
)
def connect(
    payload: dict,
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    _context: RequestContext = Depends(require_csrf),
):
    api_key = payload.get("api_key", "").strip()
    api_secret = payload.get("api_secret", "").strip()
    environment = payload.get("environment", "live").strip().lower()
    if environment not in T212_BASES:
        environment = "live"
    if not api_key:
        raise HTTPException(status_code=400, detail="API key is required")

    # One upstream account may be connected only once inside a workspace. The
    # same credential value in another tenant is unrelated customer data.
    # api_key is stored as ciphertext (see models.BrokerConnection), so this
    # can't be a SQL-level equality filter -- two encryptions of the same
    # plaintext never produce the same bytes. A workspace has few broker
    # connections, so decrypting each candidate here is cheap.
    other_connections = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.workspace_id == portfolio.workspace_id,
            BrokerConnection.broker == "trading212",
            BrokerConnection.portfolio_id != portfolio.id,
        )
        .all()
    )
    clash = next((c for c in other_connections if c.api_key == api_key), None)
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

    db.query(Transaction).filter(
        Transaction.workspace_id == portfolio.workspace_id,
        Transaction.portfolio_id == portfolio.id,
    ).delete(synchronize_session=False)

    connection = _get_connection(db, portfolio)
    action = "broker.connection.rotated" if connection else "broker.connection.created"
    if connection:
        connection.api_key = api_key
        connection.api_secret = api_secret
        connection.environment = environment
        connection.created_at = datetime.utcnow()
        connection.last_synced_at = None
        # Fresh credentials deserve a fresh start on the dead-letter state.
        connection.consecutive_failures = 0
        connection.needs_attention = False
        connection.last_error = None
    else:
        connection = BrokerConnection(
            workspace_id=portfolio.workspace_id,
            portfolio_id=portfolio.id,
            broker="trading212",
            api_key=api_key,
            api_secret=api_secret,
            environment=environment,
        )
        db.add(connection)
    db.flush()
    if _context is not None:
        record_audit_event(
            db,
            actor_user_id=_context.user.id,
            workspace_id=portfolio.workspace_id,
            action=action,
            target_type="broker_connection",
            target_id=str(connection.public_id),
            metadata={"broker": "trading212", "portfolio_id": str(portfolio.public_id)},
        )
    result = {
        "ok": True,
        "id": str(connection.public_id),
        "portfolio_id": str(portfolio.public_id),
        "message": "Connected to Trading 212",
    }
    db.commit()
    return result


@router.post("/trading212/auto-sync", dependencies=[Depends(require_capability("broker_sync")), Depends(require_writable_broker("trading212"))])
def set_auto_sync(
    payload: dict,
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    _context: RequestContext = Depends(require_csrf),
):
    """Toggle background auto-sync for this portfolio's T212 connection."""
    conn = _get_connection(db, portfolio)
    if not conn:
        raise HTTPException(status_code=404, detail="Trading 212 is not connected")
    conn.auto_sync = bool(payload.get("enabled"))
    if conn.auto_sync:
        # The user is explicitly re-enabling it -- give the dead-letter
        # state a fresh start rather than counting it as still failing.
        conn.consecutive_failures = 0
        conn.needs_attention = False
        conn.last_error = None
    db.commit()
    return {"ok": True, "auto_sync": conn.auto_sync}


@router.delete("/trading212/connect")
def disconnect(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    _context: RequestContext = Depends(require_csrf),
):
    conn = _get_connection(db, portfolio)
    if not conn:
        raise HTTPException(status_code=404, detail="No Trading 212 connection found")
    target_id = str(conn.public_id)
    db.delete(conn)
    if _context is not None:
        record_audit_event(
            db,
            actor_user_id=_context.user.id,
            workspace_id=portfolio.workspace_id,
            action="broker.connection.deleted",
            target_type="broker_connection",
            target_id=target_id,
            metadata={"broker": "trading212", "portfolio_id": str(portfolio.public_id)},
        )
    db.commit()
    return {"ok": True, "message": "Disconnected from Trading 212"}


@router.post("/trading212/sync", dependencies=[Depends(require_capability("broker_sync")), Depends(require_writable_broker("trading212")), Depends(rate_limit("broker_sync", by="workspace"))])
def sync_transactions(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    _context: RequestContext = Depends(require_csrf),
):
    conn = _get_connection(db, portfolio)
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
    new_txns: list[Transaction] = []
    # Dedup only within THIS portfolio — another portfolio holding the same ticker
    # at the same date/price is not a duplicate, it's separate data. But within the
    # portfolio, dedupe against EVERY trade row regardless of origin: CSV-imported
    # rows carry source=NULL, and matching only source='t212_api' once re-imported
    # the entire order history on top of a CSV import, doubling every position.
    existing_txns = (
        db.query(Transaction)
        .filter(
            Transaction.workspace_id == portfolio.workspace_id,
            Transaction.portfolio_id == portfolio.id,
            Transaction.ticker.isnot(None),
        )
        .all()
    )
    # A replace-imported T212 export is an account-wide history snapshot. Its
    # newest date therefore covers even instruments absent from the export;
    # without this global cutoff, a later API sync resurrects old API-only rows
    # for unseen tickers and breaks the replacement guarantee. Orders after the
    # snapshot date remain eligible for normal incremental sync.
    snapshot_rows = db.query(
        Transaction.date, Transaction.type, Transaction.source, Transaction.notes
    ).filter(
        Transaction.workspace_id == portfolio.workspace_id,
        Transaction.portfolio_id == portfolio.id,
        Transaction.source.in_(("csv", "t212_csv")),
    ).all()
    t212_csv_dates = [row.date for row in snapshot_rows if row.source == "t212_csv"]
    legacy_csv_rows = [row for row in snapshot_rows if row.source == "csv"]
    legacy_is_t212 = any(
        row.type in CASH_TYPES or (row.notes or "").startswith("T212:")
        for row in legacy_csv_rows
    )
    fallback_dates = t212_csv_dates + (
        [row.date for row in legacy_csv_rows] if legacy_is_t212 else []
    )
    portfolio_history_cutoff = portfolio.t212_csv_covered_through
    precise_history_cutoff = portfolio_history_cutoff or conn.t212_csv_covered_through
    if precise_history_cutoff is not None:
        if precise_history_cutoff.tzinfo is None:
            precise_history_cutoff = precise_history_cutoff.replace(tzinfo=timezone.utc)
        else:
            precise_history_cutoff = precise_history_cutoff.astimezone(timezone.utc)
    t212_history_date_cutoff = (
        max(fallback_dates) if fallback_dates and precise_history_cutoff is None else None
    )
    for t in existing_txns:
        existing_sources |= _dedup_keys(t.ticker, t.date, t.type, t.shares, t.price)
        if t.type == "dividend":
            existing_sources |= _dedup_keys(
                t.ticker, t.date, "dividend", round(t.shares * t.price, 6))
    # History cutoff, per instrument: orders older than a ticker's own newest
    # known transaction are history the portfolio already has for that ticker
    # (CSV exports and older syncs cover it); representations drift across
    # sources (split-adjusted prices, per-share vs total dividends), so key
    # matching alone can't be trusted for the past. A ticker with no history at
    # all has nothing covering it — its full history must import. Keyed by the
    # suffix-stripped base (like _dedup_keys) so COPM and COPM.L are one
    # instrument. Same-day overlap still goes through the key dedupe above.
    latest_by_base: dict[str, date] = {}
    for t in existing_txns:
        base_ticker = (t.ticker or "").split(".")[0]
        if base_ticker and (base_ticker not in latest_by_base
                            or t.date > latest_by_base[base_ticker]):
            latest_by_base[base_ticker] = t.date

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

            filled_qty = float(abs(fill_data.get("quantity") or order_data.get("filledQuantity", 0)))
            filled_price = float(fill_data.get("price", 0) or 0)
            if not filled_qty or not filled_price:
                continue

            instrument = order_data.get("instrument", {})
            currency = instrument.get("currency", "USD").upper()

            date_str = fill_data.get("filledAt") or order_data.get("createdAt", "")
            try:
                event_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                if event_time.tzinfo is None:
                    event_time = event_time.replace(tzinfo=timezone.utc)
                else:
                    event_time = event_time.astimezone(timezone.utc)
                txn_date = event_time.date()
            except Exception:
                continue

            if precise_history_cutoff and event_time <= precise_history_cutoff:
                continue
            if t212_history_date_cutoff and txn_date <= t212_history_date_cutoff:
                continue

            cutoff = latest_by_base.get(ticker.split(".")[0])
            if cutoff and txn_date < cutoff:
                continue

            name = instrument.get("name", ticker)

            keys = _dedup_keys(ticker, txn_date, txn_type, filled_qty, filled_price)
            if keys & existing_sources:
                continue

            new_txn = Transaction(
                workspace_id=portfolio.workspace_id,
                portfolio_id=portfolio.id,
                ticker=ticker,
                name=name,
                type=txn_type,
                shares=filled_qty,
                price=filled_price,
                currency=currency,
                date=txn_date,
                notes=f"T212 Order #{order_data.get('id', '')}",
                source="t212_api",
            )
            db.add(new_txn)
            new_orders_by_ticker.setdefault(ticker, []).append(new_txn)
            new_txns.append(new_txn)
            existing_sources |= keys
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
                    event_time = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    if event_time.tzinfo is None:
                        event_time = event_time.replace(tzinfo=timezone.utc)
                    else:
                        event_time = event_time.astimezone(timezone.utc)
                    txn_date = event_time.date()
                except Exception:
                    continue

                if precise_history_cutoff and event_time <= precise_history_cutoff:
                    continue
                if t212_history_date_cutoff and txn_date <= t212_history_date_cutoff:
                    continue

                cutoff = latest_by_base.get(ticker.split(".")[0])
                if cutoff and txn_date < cutoff:
                    continue

                keys = _dedup_keys(ticker, txn_date, "dividend", total_amount)
                if keys & existing_sources:
                    continue

                new_div = Transaction(
                    workspace_id=portfolio.workspace_id,
                    portfolio_id=portfolio.id,
                    ticker=ticker,
                    name=ticker,
                    type="dividend",
                    shares=1.0,
                    price=total_amount,
                    currency=div_currency,
                    date=txn_date,
                    notes="T212 Dividend",
                    source="t212_api",
                )
                db.add(new_div)
                new_txns.append(new_div)
                existing_sources |= keys
                dividends_imported += 1
            except Exception as e:
                errors.append(str(e))
    except Exception as e:
        errors.append(f"Dividend fetch failed: {e}")

    # Everything in a T212 account settles in the account currency (CZK here):
    # snapshot the trade-date fx and store the CZK cash impact, like the CSV
    # import does. Without it, cash model v2 falls back to shares*price in the
    # trade currency and a synced buy drains a USD pile that doesn't exist.
    # (Approximation — no FX-fee detail; the next CSV replace-import corrects it.)
    fx_needed = {((t.currency or "USD").upper(), t.date) for t in new_txns
                 if (t.currency or "USD").upper() != "CZK"}
    fx_map = bulk_fetch_fx(fx_needed)
    for t in new_txns:
        ccy = (t.currency or "USD").upper()
        fx = 1.0 if ccy == "CZK" else fx_map.get((ccy, t.date))
        if fx:
            t.fx_to_czk = fx
            t.cash_amount = round(float(t.shares) * float(t.price) * fx, 2)
            t.cash_currency = "CZK"

    # Split-adjust rewrites shares*=R, price/=R — the product (and therefore the
    # CZK settlement above) is unchanged.
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
