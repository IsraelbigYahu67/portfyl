from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import date, datetime, timezone
import httpx
import json

import t212_sync
from account_identity import account_fingerprint
from audit import record_audit_event
from broker_reconciliation import reconcile_positions
from database import get_db
from entitlements import require_broker_capacity, require_capability, require_writable_broker
from rate_limit import rate_limit
from fx import convert_amount
from models import BrokerBalance, BrokerConnection, BrokerPosition, BrokerSyncRun, Portfolio, Transaction
from tenancy import RequestContext, require_csrf, require_portfolio
from t212_sync import (
    T212_BASES,
    _t212_base,
    _t212_headers,
)

router = APIRouter(prefix="/broker", tags=["broker"])


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


def _summary_account_fingerprint(summary: dict, environment: str) -> str:
    try:
        return account_fingerprint(
            broker="trading212",
            environment=environment,
            provider_account_id=summary.get("id"),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Trading 212 did not return a usable account identity",
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="Trading 212 account identity verification is not configured",
        ) from exc


def _reject_account_replacement() -> None:
    raise HTTPException(
        status_code=409,
        detail=(
            "This portfolio is already bound to a different Trading 212 account. "
            "Create a new portfolio for the other account."
        ),
    )


def _ensure_unique_account_binding(
    db: Session,
    portfolio: Portfolio,
    fingerprint: str,
) -> None:
    clash = db.query(Portfolio.id).filter(
        Portfolio.workspace_id == portfolio.workspace_id,
        Portfolio.id != portfolio.id,
        Portfolio.t212_account_fingerprint == fingerprint,
    ).first()
    if clash is not None:
        raise HTTPException(
            status_code=409,
            detail="This Trading 212 account is already bound to another portfolio.",
        )


def _bind_verified_account(
    db: Session,
    portfolio: Portfolio,
    connection: BrokerConnection | None,
    fingerprint: str,
) -> None:
    if portfolio.t212_account_fingerprint not in (None, fingerprint):
        _reject_account_replacement()
    if connection is not None and connection.account_fingerprint not in (None, fingerprint):
        _reject_account_replacement()
    _ensure_unique_account_binding(db, portfolio, fingerprint)
    portfolio.t212_account_fingerprint = fingerprint
    if connection is not None:
        connection.account_fingerprint = fingerprint


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
        "account_bound": bool(
            conn.account_fingerprint
            and conn.account_fingerprint == portfolio.t212_account_fingerprint
        ),
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
        as_of = conn.positions_snapshot_at
        return {
            "connected": True,
            "status": ("fresh" if t212_sync.is_snapshot_fresh(as_of) else "stale") if as_of else "unavailable",
            "as_of": as_of.isoformat() if as_of else None,
            "currency": currency,
            "positions": [],
        }

    as_of = max(r.as_of for r in rows)
    status = "fresh" if t212_sync.is_snapshot_fresh(as_of) else "stale"

    # /equity/positions carries no instrument currency; best-effort derive it
    # from the most recent ledger row for the same normalized ticker. Until
    # that currency is known, monetary values cannot be labeled with the
    # requested display currency.
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
            if t.currency:
                currency_by_ticker.setdefault(t.ticker, t.currency.upper())

    positions = []
    for r in rows:
        native_ccy = r.currency or currency_by_ticker.get(r.ticker)
        market_value = cost_basis = pnl = None
        if native_ccy and r.current_price is not None:
            native_market_value = r.quantity * r.current_price
            market_value = convert_amount(native_market_value, native_ccy, currency)
        if native_ccy:
            native_cost_basis = r.quantity * r.avg_price
            cost_basis = convert_amount(native_cost_basis, native_ccy, currency)
        if market_value is not None and cost_basis is not None:
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


def _reconcile_history(
    db: Session, portfolio: Portfolio, conn: BrokerConnection, run: BrokerSyncRun,
) -> dict:
    """Ledger-vs-snapshot reconciliation (plan §6.3). The ledger is only
    authoritative once the latest run completed, so the transaction load is
    skipped until then and whenever no positions snapshot exists."""
    if run.state != "completed":
        return reconcile_positions(
            ledger_shares={}, positions=[], snapshot_available=False, history_complete=False,
        )
    positions = (
        db.query(BrokerPosition)
        .filter(
            BrokerPosition.workspace_id == portfolio.workspace_id,
            BrokerPosition.portfolio_id == portfolio.id,
            BrokerPosition.broker == "trading212",
        )
        .all()
    )
    as_of = max((p.as_of for p in positions), default=None) or conn.positions_snapshot_at
    ledger_shares: dict[str, float] = {}
    if as_of is not None:
        # Local import: the portfolio router pulls in market-data modules that
        # the rest of this router does not need (same pattern as jobs.py).
        from routers.portfolio import _build_holdings, _portfolio_txns

        holdings = _build_holdings(_portfolio_txns(db, portfolio).all())
        ledger_shares = {ticker: data["shares"] for ticker, data in holdings.items()}
    return reconcile_positions(
        ledger_shares=ledger_shares,
        positions=positions,
        snapshot_available=as_of is not None,
        history_complete=True,
        snapshot_stale=as_of is not None and not t212_sync.is_snapshot_fresh(as_of),
    )


def _reconciliation_mismatch(db: Session, portfolio: Portfolio, conn: BrokerConnection) -> bool:
    """True when the ledger, as of the latest completed history run, disagrees
    with the positions snapshot this sync just refreshed -- the trigger for an
    immediate audit (parent plan §7), since only a full re-read can reveal old
    events the incremental stop rule skipped. Not asked again while a full
    read is younger than t212_sync.RECONCILIATION_AUDIT_COOLDOWN: it already
    saw everything the provider has, so a lingering mismatch has another cause."""
    last_read = t212_sync.last_full_read_at(conn)
    if (
        last_read is not None
        and datetime.now(timezone.utc) - last_read < t212_sync.RECONCILIATION_AUDIT_COOLDOWN
    ):
        return False
    latest_completed = (
        db.query(BrokerSyncRun)
        .filter(
            BrokerSyncRun.workspace_id == portfolio.workspace_id,
            BrokerSyncRun.connection_id == conn.id,
            BrokerSyncRun.state == "completed",
        )
        .order_by(BrokerSyncRun.created_at.desc(), BrokerSyncRun.id.desc())
        .first()
    )
    # Only an incremental run can have skipped provider events. When the latest
    # completed run already read the whole history (initial/audit), another
    # full read cannot explain a mismatch that survived it.
    if latest_completed is None or latest_completed.mode != "incremental":
        return False
    # Sessions run with autoflush off: make the just-replaced snapshot visible.
    db.flush()
    return _reconcile_history(db, portfolio, conn, latest_completed)["status"] == "different"


@router.get("/trading212/history-status")
def get_history_status(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    """Progress of this connection's resumable history backfill.

    Cursors and raw exception strings are operational secrets and never cross
    this API boundary. ``download_complete`` reports staged provider pages;
    ``complete`` becomes true only after atomic ledger finalization.
    """
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

    reset_candidates = [
        value for value in (
            run.orders_rate_limit_reset_at,
            run.dividends_rate_limit_reset_at,
            run.cash_rate_limit_reset_at,
        )
        if value is not None
    ]
    resume_at = max(reset_candidates) if reset_candidates else None
    if resume_at is not None and resume_at.tzinfo is None:
        resume_at = resume_at.replace(tzinfo=timezone.utc)
    if run.state == "needs_review":
        public_error = (
            run.last_error
            if run.last_error in {
                t212_sync.HISTORY_SPLIT_UNVERIFIED_ERROR,
                t212_sync.HISTORY_CASH_UNSUPPORTED_ERROR,
            }
            else t212_sync.HISTORY_NEEDS_REVIEW_ERROR
        )
    elif run.last_error:
        if run.state == "failed" and run.last_error == t212_sync.HISTORY_PAGINATION_ERROR:
            public_error = t212_sync.HISTORY_PAGINATION_ERROR
        elif run.state == "failed":
            public_error = "Trading 212 history sync failed. Start a new sync to retry."
        else:
            public_error = t212_sync.HISTORY_RETRY_ERROR
    else:
        public_error = None

    return {
        "connected": True,
        "run": {
            "id": str(run.public_id),
            "mode": run.mode,
            "state": run.state,
            "complete": run.state == "completed",
            "download_complete": bool(
                run.orders_complete and run.dividends_complete and run.cash_complete
            ),
            "orders_loaded": run.orders_loaded,
            "orders_complete": run.orders_complete,
            "dividends_loaded": run.dividends_loaded,
            "dividends_complete": run.dividends_complete,
            "cash_loaded": run.cash_loaded,
            "cash_complete": run.cash_complete,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "last_progress_at": run.last_progress_at.isoformat() if run.last_progress_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "resume_at": resume_at.isoformat() if resume_at else None,
            "last_error": public_error,
            "review": (
                {"items": run.review_details or [],
                 **t212_sync.review_resolution(run, conn, portfolio)}
                if run.state == "needs_review" else None
            ),
        },
        "reconciliation": _reconcile_history(db, portfolio, conn, run),
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

    connection = _get_connection(db, portfolio)
    try:
        candidate_summary = _fetch_account_summary(
            base, _t212_headers(api_key, api_secret),
        )
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Trading 212 returned an error: {exc.response.status_code}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not verify the Trading 212 account: {exc}",
        ) from exc
    candidate_fingerprint = _summary_account_fingerprint(candidate_summary, environment)

    if connection and connection.account_fingerprint is None:
        # A legacy connection can be bound only after independently validating
        # its stored credentials. New credentials are not proof that the old
        # ledger belongs to the same upstream account.
        try:
            same_credentials = (
                (connection.environment or "live") == environment
                and connection.api_key == api_key
                and (connection.api_secret or "") == api_secret
            )
            if same_credentials:
                existing_fingerprint = candidate_fingerprint
            else:
                old_environment = connection.environment or "live"
                old_summary = _fetch_account_summary(
                    _t212_base(old_environment),
                    _t212_headers(connection.api_key, connection.api_secret or ""),
                )
                existing_fingerprint = _summary_account_fingerprint(
                    old_summary, old_environment,
                )
        except Exception as exc:
            raise HTTPException(
                status_code=409,
                detail=(
                    "The existing Trading 212 account identity could not be verified. "
                    "This portfolio was left unchanged; connect the new account to a new portfolio."
                ),
            ) from exc
        if existing_fingerprint != candidate_fingerprint:
            _reject_account_replacement()

    _bind_verified_account(db, portfolio, connection, candidate_fingerprint)
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
        ).update(
            {"state": "cancelled", "lease_token": None, "lease_expires_at": None},
            synchronize_session=False,
        )
        connection.credential_generation = (connection.credential_generation or 1) + 1
        connection.api_key = api_key
        connection.api_secret = api_secret
        connection.environment = environment
        connection.account_fingerprint = candidate_fingerprint
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
            account_fingerprint=candidate_fingerprint,
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


@router.post(
    "/trading212/sync",
    status_code=202,
    dependencies=[
        Depends(require_capability("broker_sync")),
        Depends(require_writable_broker("trading212")),
        Depends(rate_limit("broker_sync", by="workspace")),
    ],
)
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
    cash_updated = False
    cash_error = None
    positions_updated = False
    positions_error = None

    # Summary and positions are the fast current-state snapshot (T212
    # snapshot-first sync plan, 2026-09-20, §5.2): fetched concurrently and
    # persisted independently, so one endpoint failing never blocks or
    # discards the other's result.
    snapshot = t212_sync.fetch_snapshot(base, headers, fetch_summary=_fetch_account_summary)
    if snapshot.summary is not None:
        fingerprint = _summary_account_fingerprint(
            snapshot.summary, conn.environment or "live",
        )
        _bind_verified_account(db, portfolio, conn, fingerprint)
        _upsert_t212_balance(db, portfolio, snapshot.summary)
        cash_updated = True
    else:
        if (
            not conn.account_fingerprint
            or not portfolio.t212_account_fingerprint
            or conn.account_fingerprint != portfolio.t212_account_fingerprint
        ):
            raise HTTPException(
                status_code=502,
                detail="Trading 212 account identity could not be verified",
            )
        cash_error = "Trading 212 account summary could not be refreshed."

    if snapshot.positions is not None:
        t212_sync.replace_positions(db, portfolio, snapshot.positions)
        positions_updated = True
    else:
        positions_error = "Trading 212 positions could not be refreshed."

    # Create the history run only after account identity has been verified,
    # and never while the latest run is an unresolved needs_review: that would
    # re-stage the whole history into the same dead end.
    decision = t212_sync.history_run_decision(
        db, conn, portfolio,
        reconciliation_mismatch=positions_updated and _reconciliation_mismatch(db, portfolio, conn),
    )
    if decision.action == "blocked":
        history_run, blocked = decision.run, True
    else:
        history_run, blocked = t212_sync.claim_or_create_run(
            db, conn, portfolio, mode=decision.mode,
        ), False

    # Manual sync is snapshot-first: persist the independently successful
    # current-state components and hand history work to broker_backfill.  A
    # foreground request must never walk the provider's full history or mark
    # the ledger as synchronized.
    db.commit()
    snapshot_status = (
        "ready" if cash_updated and positions_updated
        else "partial" if cash_updated or positions_updated
        else "unavailable"
    )
    return {
        "snapshot": {
            "status": snapshot_status,
            "cash_updated": cash_updated,
            "cash_error": cash_error,
            "positions_updated": positions_updated,
            "positions_error": positions_error,
            "positions": len(snapshot.positions) if snapshot.positions is not None else None,
        },
        "history": {
            "run_id": str(history_run.public_id),
            "status": history_run.state,
            "complete": False,
            "blocked": blocked,
        },
    }


@router.post(
    "/trading212/history/retry",
    dependencies=[
        Depends(require_capability("broker_sync")),
        Depends(require_writable_broker("trading212")),
        Depends(rate_limit("broker_sync", by="workspace")),
    ],
)
def retry_history(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    _context: RequestContext = Depends(require_csrf),
):
    """Explicit user retry of the history import after a needs_review run:
    always starts a fresh run (or returns the one already active)."""
    conn = _get_connection(db, portfolio)
    if not conn:
        raise HTTPException(status_code=404, detail="Trading 212 is not connected")
    decision = t212_sync.history_run_decision(db, conn, portfolio, force=True)
    run = (
        decision.run if decision.action == "reuse"
        else t212_sync.claim_or_create_run(db, conn, portfolio, mode=decision.mode)
    )
    db.commit()
    return {"run_id": str(run.public_id), "status": run.state, "complete": False, "blocked": False}


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


