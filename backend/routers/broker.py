from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime, timezone
from urllib.parse import urlparse, parse_qs
import httpx
import json
import os
import yfinance as yf

import t212_sync
from audit import record_audit_event
from database import get_db
from entitlements import require_broker_capacity, require_capability, require_writable_broker
from rate_limit import rate_limit
from fx import bulk_fetch_fx, convert_amount
from models import BrokerBalance, BrokerConnection, BrokerPosition, BrokerSyncRun, Portfolio, Transaction
from tenancy import RequestContext, require_csrf, require_portfolio
from cash_ledger import CASH_TYPES
from t212_sync import (
    T212_BASES,
    _CANONICAL_TICKER,
    _dedup_keys,
    _normalize_t212_ticker,
    _t212_base,
    _t212_headers,
)

router = APIRouter(prefix="/broker", tags=["broker"])


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
    # Decrypting the stored key can fail on its own (missing/rotated secret
    # cipher config, KMS unreachable) independent of the connection's own
    # sync health. Without this guard that exception has no handler and 500s
    # the whole request, which the frontend can only show as a generic
    # "We couldn't load this data." -- with no connection info rendered at
    # all, there's no Disconnect button left to click to recover.
    try:
        api_key_preview = conn.api_key[:6] + "..." + conn.api_key[-4:] if len(conn.api_key) > 10 else "***"
        decrypt_error = None
    except Exception:
        api_key_preview = None
        decrypt_error = "Stored Trading 212 credentials could not be read. Disconnect and reconnect with your API key."
    return {
        "connected": True,
        "id": str(conn.public_id),
        "portfolio_id": str(portfolio.public_id),
        "auto_sync": conn.auto_sync,
        "environment": conn.environment or "live",
        "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
        "connected_at": conn.created_at.isoformat() if conn.created_at else None,
        "api_key_preview": api_key_preview,
        "needs_attention": conn.needs_attention or decrypt_error is not None,
        "last_error": decrypt_error or (conn.last_error if conn.needs_attention else None),
    }


@router.get("/trading212/positions")
def get_positions(
    currency: str = "USD",
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    """Current T212 position snapshot (fast path, T212 snapshot-first sync
    plan §2.1/§2.4) -- independent of and much faster than the full
    order/dividend history sync. `status` follows the 25-hour freshness
    rule: `fresh` inside the window, `stale` past it (still returned, since
    while history is incomplete a stale snapshot is the only current-state
    evidence), and `unavailable` when nothing has ever been fetched.

    Values are a current-value surface only -- they never substitute for the
    transaction ledger in historical performance, FIFO, or tax calculations.
    """
    conn = _get_connection(db, portfolio)
    if not conn:
        return {"connected": False, "status": "unavailable", "as_of": None, "positions": []}

    rows = (
        db.query(BrokerPosition)
        .filter(
            BrokerPosition.workspace_id == portfolio.workspace_id,
            BrokerPosition.portfolio_id == portfolio.id,
            BrokerPosition.broker == "trading212",
        )
        .order_by(BrokerPosition.ticker)
        .all()
    )
    if not rows:
        return {"connected": True, "status": "unavailable", "as_of": None, "positions": []}

    as_of = max(r.as_of for r in rows)
    status = "fresh" if t212_sync.is_snapshot_fresh(as_of) else "stale"

    # /equity/positions carries no instrument currency; best-effort derive it
    # from the most recent ledger row for the same normalized ticker (if the
    # account has no ledger history yet, values are reported unconverted in
    # their instrument-currency face value rather than guessed).
    tickers = {r.ticker for r in rows}
    currency_by_ticker: dict[str, str] = {}
    if tickers:
        latest_txns = (
            db.query(Transaction.ticker, Transaction.currency)
            .filter(
                Transaction.workspace_id == portfolio.workspace_id,
                Transaction.portfolio_id == portfolio.id,
                Transaction.ticker.in_(tickers),
            )
            .order_by(Transaction.date.desc())
            .all()
        )
        for t in latest_txns:
            currency_by_ticker.setdefault(t.ticker, (t.currency or "USD").upper())

    positions = []
    for r in rows:
        native_ccy = currency_by_ticker.get(r.ticker)
        market_value = cost_basis = pnl = None
        if r.current_price is not None:
            native_market_value = r.quantity * r.current_price
            market_value = convert_amount(native_market_value, native_ccy or "USD", currency) if native_ccy else native_market_value
        native_cost_basis = r.quantity * r.avg_price
        cost_basis = convert_amount(native_cost_basis, native_ccy or "USD", currency) if native_ccy else native_cost_basis
        if market_value is not None:
            pnl = market_value - cost_basis
        positions.append({
            "ticker": r.ticker,
            "provider_ticker": r.provider_ticker,
            "name": r.name or r.ticker,
            "currency": native_ccy,
            "quantity": r.quantity,
            "pie_quantity": r.pie_quantity,
            "avg_price": r.avg_price,
            "current_price": r.current_price,
            "market_value": market_value,
            "cost_basis": cost_basis,
            "pnl": pnl,
            "pnl_percent": (pnl / cost_basis) if pnl is not None and cost_basis else None,
            "broker_ppl": r.ppl,
            "broker_fx_ppl": r.fx_ppl,
        })

    return {
        "connected": True,
        "status": status,
        "as_of": as_of.isoformat(),
        "currency": currency,
        "positions": positions,
    }


@router.get("/trading212/history-status")
def get_history_status(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    """Progress of this connection's most recent resumable history backfill
    (T212 snapshot-first sync plan, Task 3). `jobs.broker_backfill_pass`
    advances an active run in the background; this is read-only and never
    triggers or advances one itself. `complete` mirrors §2.1/§2.2's
    'history complete' signal other current-value surfaces will eventually
    gate on -- it means every order/dividend page is staged, not that ledger
    Transaction rows reflect it yet (that finalization step doesn't exist in
    this increment)."""
    conn = _get_connection(db, portfolio)
    if not conn:
        return {"connected": False, "run": None}

    run = (
        db.query(BrokerSyncRun)
        .filter(
            BrokerSyncRun.workspace_id == portfolio.workspace_id,
            BrokerSyncRun.connection_id == conn.id,
        )
        .order_by(BrokerSyncRun.created_at.desc())
        .first()
    )
    if run is None:
        return {"connected": True, "run": None}

    return {
        "connected": True,
        "run": {
            "id": str(run.public_id),
            "mode": run.mode,
            "state": run.state,
            "complete": bool(run.orders_complete and run.dividends_complete),
            "orders_loaded": run.orders_loaded,
            "orders_complete": run.orders_complete,
            "dividends_loaded": run.dividends_loaded,
            "dividends_complete": run.dividends_complete,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "last_progress_at": run.last_progress_at.isoformat() if run.last_progress_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "last_error": run.last_error,
        },
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
    db.query(BrokerBalance).filter(
        BrokerBalance.workspace_id == portfolio.workspace_id,
        BrokerBalance.portfolio_id == portfolio.id,
        BrokerBalance.broker == "trading212",
    ).delete(synchronize_session=False)
    db.query(BrokerPosition).filter(
        BrokerPosition.workspace_id == portfolio.workspace_id,
        BrokerPosition.portfolio_id == portfolio.id,
        BrokerPosition.broker == "trading212",
    ).delete(synchronize_session=False)

    connection = _get_connection(db, portfolio)
    action = "broker.connection.rotated" if connection else "broker.connection.created"
    if connection:
        # Fence every in-flight history run before mutating credentials
        # (plan §5.1): an incomplete run must never be resumed under a new
        # credential generation. Bumping credential_generation here, before
        # any worker can re-read it, is what makes t212_sync.claim_lease's
        # generation check in jobs.broker_backfill_pass reliable.
        db.query(BrokerSyncRun).filter(
            BrokerSyncRun.workspace_id == portfolio.workspace_id,
            BrokerSyncRun.connection_id == connection.id,
            BrokerSyncRun.state.notin_(t212_sync.TERMINAL_RUN_STATES),
        ).update({"state": "cancelled"}, synchronize_session=False)
        connection.credential_generation = (connection.credential_generation or 1) + 1
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
    db.query(BrokerBalance).filter(
        BrokerBalance.workspace_id == portfolio.workspace_id,
        BrokerBalance.portfolio_id == portfolio.id,
        BrokerBalance.broker == "trading212",
    ).delete(synchronize_session=False)
    db.query(BrokerPosition).filter(
        BrokerPosition.workspace_id == portfolio.workspace_id,
        BrokerPosition.portfolio_id == portfolio.id,
        BrokerPosition.broker == "trading212",
    ).delete(synchronize_session=False)
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
    cash_updated = False
    cash_error = None
    positions_updated = False
    positions_error = None

    # Start (or return the already-active) resumable history run. This is
    # additive/parallel to the full fetch-and-import below, not a replacement
    # for it yet -- t212_sync.advance_run only stages raw pages into
    # BrokerSyncEvent; jobs.broker_backfill_pass, not this request, does the
    # actual paging (plan §5.4), so creating the run here is a single flush,
    # never an extra commit inside this request.
    history_run = t212_sync.claim_or_create_run(db, conn, portfolio)

    try:
        orders = _fetch_all_orders(base, headers)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch orders: {e}")

    # Summary and positions are the fast current-state snapshot (T212
    # snapshot-first sync plan, 2026-09-20, §5.2): fetched concurrently and
    # persisted independently, so one endpoint failing never blocks or
    # discards the other's result.
    snapshot = t212_sync.fetch_snapshot(base, headers, fetch_summary=_fetch_account_summary)
    if snapshot.summary is not None:
        _upsert_t212_balance(db, portfolio, snapshot.summary)
        cash_updated = True
    else:
        cash_error = f"Cash summary fetch failed: {snapshot.summary_error}"
        errors.append(cash_error)

    if snapshot.positions is not None:
        t212_sync.replace_positions(db, portfolio, snapshot.positions)
        positions_updated = True
    else:
        positions_error = f"Positions fetch failed: {snapshot.positions_error}"
        errors.append(positions_error)

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
        "cash_updated": cash_updated,
        "cash_error": cash_error,
        "positions_updated": positions_updated,
        "positions_error": positions_error,
        "history_run_id": str(history_run.public_id),
        "history_status": history_run.state,
    }


def _extract_cursor(next_page_path: str) -> str | None:
    if not next_page_path:
        return None
    parsed = urlparse(next_page_path)
    params = parse_qs(parsed.query)
    cursors = params.get("cursor")
    return cursors[0] if cursors else None


# NOTE: this endpoint and its response field names (cash.availableToTrade,
# cash.inPies, cash.reservedForOrders, investments.currentValue, totalValue,
# currency) are verified only against a hand-written test fixture, never
# against a live Trading 212 account. Confirm against the real API (or
# Trading 212's official docs) before relying on this in production.
def _fetch_account_summary(base: str, headers: dict) -> dict:
    resp = httpx.get(f"{base}/equity/account/summary", headers=headers, timeout=15)
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="API key is invalid or expired")
    if resp.status_code == 403:
        raise HTTPException(status_code=403, detail="API key cannot read the account summary")
    if resp.status_code == 429:
        raise HTTPException(status_code=429, detail="Trading 212 rate limit reached")
    resp.raise_for_status()
    return resp.json()


def _upsert_t212_balance(db: Session, portfolio: Portfolio, summary: dict) -> BrokerBalance:
    cash_data = summary.get("cash") or {}
    cash = sum(
        float(cash_data.get(field) or 0)
        for field in ("availableToTrade", "inPies", "reservedForOrders")
    )
    currency = str(summary.get("currency") or "").upper() or None
    investments = summary.get("investments") or {}

    balance = (
        db.query(BrokerBalance)
        .filter(
            BrokerBalance.workspace_id == portfolio.workspace_id,
            BrokerBalance.portfolio_id == portfolio.id,
            BrokerBalance.broker == "trading212",
        )
        .first()
    )
    if balance is None:
        balance = BrokerBalance(
            workspace_id=portfolio.workspace_id,
            portfolio_id=portfolio.id,
            broker="trading212",
        )
        db.add(balance)

    balance.base_currency = currency
    balance.cash = cash
    balance.stock = float(investments.get("currentValue") or 0)
    balance.options_value = None
    balance.net_liquidation = float(summary.get("totalValue") or 0)
    balance.cash_by_currency = json.dumps({currency: cash}) if currency else None
    # Persist the provider components behind the blended totals above
    # (T212 snapshot-first sync plan, 2026-09-20, §4.1) -- broker_realized_pnl
    # is reconciliation-only provenance, never a substitute for Portfyl's own
    # FIFO realized P/L.
    balance.cash_available = _optional_float(cash_data.get("availableToTrade"))
    balance.cash_in_pies = _optional_float(cash_data.get("inPies"))
    balance.cash_reserved = _optional_float(cash_data.get("reservedForOrders"))
    balance.stock_total_cost = _optional_float(investments.get("totalCost"))
    balance.stock_unrealized_pnl = _optional_float(investments.get("unrealizedProfitLoss"))
    balance.broker_realized_pnl = _optional_float(investments.get("realizedProfitLoss"))
    balance.as_of = date.today()
    return balance


def _optional_float(value) -> float | None:
    return None if value is None else float(value)


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
