"""eToro connection via the Public API with the user's personal (Read) key.

Portfyl's own app key comes from `PORTFYL_ETORO_APP_KEY`; without it the
integration reports itself as not configured. Every handler is a plain def:
EtoroClient is a blocking httpx client, and the sync runs it on the request's
worker thread (or the job's thread), never on the event loop.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import os
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from audit import record_audit_event
from database import get_db, release_connection, release_request_connections
from entitlements import (
    enforce_broker_capacity_locked,
    require_broker_capacity,
    require_capability,
    require_writable_broker,
)
from etoro_client import EtoroAuthError, EtoroClient, EtoroRateLimited, field
from etoro_mapper import SOURCE, map_account
from importers.base import validate_rows
from ledger_import import MAX_SYNC_ERRORS, insert_new_provider_rows, ledger_result
from models import BrokerConnection, Portfolio
from rate_limit import rate_limit
from tenancy import RequestContext, require_csrf, require_portfolio

router = APIRouter(prefix="/broker/etoro", tags=["etoro"])

BROKER = "etoro"
APP_KEY_ENV = "PORTFYL_ETORO_APP_KEY"
# eToro was founded in 2007: the first sync reads the whole history.
HISTORY_START = date(2007, 1, 1)
# Later syncs re-read a month back so late-settling closes are not missed;
# event ids make the overlap free.
SYNC_OVERLAP = timedelta(days=30)
KEY_HELP = ("eToro rejected the key. In eToro open Settings → Trading → API Key Management, "
            "create a key with Read permission for the Real environment and paste it here.")


class ConnectBody(BaseModel):
    user_key: str = Field(min_length=1, max_length=512)


class AutoSyncBody(BaseModel):
    enabled: bool


def _app_key() -> str | None:
    return (os.environ.get(APP_KEY_ENV) or "").strip() or None


def _require_app_key() -> str:
    key = _app_key()
    if not key:
        raise HTTPException(status_code=503, detail="eToro integration is not configured")
    return key


def _get_connection(db: Session, portfolio: Portfolio) -> BrokerConnection | None:
    return (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.workspace_id == portfolio.workspace_id,
            BrokerConnection.broker == BROKER,
            BrokerConnection.portfolio_id == portfolio.id,
        )
        .first()
    )


def _rate_limited(exc: EtoroRateLimited) -> HTTPException:
    return HTTPException(status_code=429, detail=str(exc),
                         headers={"Retry-After": f"{exc.retry_after:.0f}"})


@router.post(
    "/connect",
    dependencies=[Depends(require_capability("broker_sync")), Depends(require_broker_capacity(BROKER))],
)
def connect(
    body: ConnectBody,
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    _context: RequestContext = Depends(require_csrf),
):
    app_key = _require_app_key()
    user_key = body.user_key.strip()
    if not user_key:
        raise HTTPException(status_code=400, detail="user_key is required")

    # Validate with one read before the workspace lock and without a held
    # connection.
    release_connection(db)
    try:
        EtoroClient(app_key, user_key).positions()
    except EtoroAuthError:
        raise HTTPException(status_code=400, detail=KEY_HELP)
    except EtoroRateLimited as exc:
        raise _rate_limited(exc)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach eToro: {exc}")

    enforce_broker_capacity_locked(db, portfolio.workspace_id, None, BROKER, portfolio)
    # Re-read under the lock: another connect or a disconnect may have won.
    connection = (
        db.query(BrokerConnection)
        .populate_existing()
        .filter(
            BrokerConnection.workspace_id == portfolio.workspace_id,
            BrokerConnection.broker == BROKER,
            BrokerConnection.portfolio_id == portfolio.id,
        )
        .first()
    )
    action = "broker.connection.rotated" if connection else "broker.connection.created"
    if connection:
        connection.api_key = user_key
        connection.last_synced_at = None
        # Fresh credentials deserve a fresh start on the dead-letter state.
        connection.consecutive_failures = 0
        connection.needs_attention = False
        connection.last_error = None
    else:
        connection = BrokerConnection(
            workspace_id=portfolio.workspace_id,
            portfolio_id=portfolio.id,
            broker=BROKER,
            api_key=user_key,
            environment="live",
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
            metadata={"broker": BROKER, "portfolio_id": str(portfolio.public_id)},
        )
    result = {
        "connected": True,
        "id": str(connection.public_id),
        "portfolio_id": str(portfolio.public_id),
        "message": "Connected to eToro",
    }
    db.commit()
    return result


@router.get("/status")
def get_status(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
):
    configured = _app_key() is not None
    conn = _get_connection(db, portfolio)
    if not conn:
        return {"connected": False, "configured": configured, "portfolio_id": str(portfolio.public_id)}
    return {
        "connected": True,
        "configured": configured,
        "id": str(conn.public_id),
        "portfolio_id": str(portfolio.public_id),
        "auto_sync": conn.auto_sync,
        "last_synced_at": conn.last_synced_at.isoformat() if conn.last_synced_at else None,
        "connected_at": conn.created_at.isoformat() if conn.created_at else None,
        "needs_attention": conn.needs_attention,
        "last_error": conn.last_error if conn.needs_attention else None,
    }


@router.post(
    "/auto-sync",
    dependencies=[Depends(require_capability("broker_sync")), Depends(require_writable_broker(BROKER))],
)
def set_auto_sync(
    body: AutoSyncBody,
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    _context: RequestContext = Depends(require_csrf),
):
    conn = _get_connection(db, portfolio)
    if not conn:
        raise HTTPException(status_code=404, detail="eToro is not connected")
    conn.auto_sync = body.enabled
    if conn.auto_sync:
        conn.consecutive_failures = 0
        conn.needs_attention = False
        conn.last_error = None
    db.commit()
    return {"ok": True, "auto_sync": conn.auto_sync}


@router.delete("/connect")
def disconnect(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    _context: RequestContext = Depends(require_csrf),
):
    conn = _get_connection(db, portfolio)
    if not conn:
        raise HTTPException(status_code=404, detail="No eToro connection found")
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
            metadata={"broker": BROKER, "portfolio_id": str(portfolio.public_id)},
        )
    db.commit()
    return {"ok": True, "message": "Disconnected from eToro"}


def _flag(db: Session, conn: BrokerConnection, message: str) -> None:
    conn.needs_attention = True
    conn.last_error = message[:500]
    db.commit()


def etoro_sync(db: Session, workspace_id: UUID, portfolio_id: int) -> dict:
    """Import new eToro positions into one explicitly scoped portfolio.

    Returns {status: "imported" | "needs_review", imported, already_present,
    errors, skipped_reasons}. Commits. Raises HTTPException for an unknown
    connection (404), missing configuration (503), a rejected key (400, also
    flags the connection), eToro's rate limit (429) and network failures (502).
    """
    portfolio = db.query(Portfolio).filter(
        Portfolio.workspace_id == workspace_id,
        Portfolio.id == portfolio_id,
    ).first()
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    conn = _get_connection(db, portfolio)
    if not conn:
        raise HTTPException(status_code=404, detail="eToro is not connected")
    app_key = _require_app_key()
    user_key = conn.api_key
    min_date = (conn.last_synced_at.date() - SYNC_OVERLAP) if conn.last_synced_at else HISTORY_START

    # A request session must not hold a pooled connection through the eToro
    # round trips (rate-limited to ~1 call/s). Job sessions are left alone.
    release_request_connections()
    client = EtoroClient(app_key, user_key)
    try:
        positions = client.positions()
        history = client.trade_history(min_date)
        ids = {field(item, "instrumentId", "instrumentID") for item in [*positions, *history]}
        instruments = client.instruments(int(i) for i in ids if i is not None)
    except EtoroAuthError as exc:
        _flag(db, conn, str(exc))
        raise HTTPException(status_code=400, detail=KEY_HELP)
    except EtoroRateLimited as exc:
        raise _rate_limited(exc)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"eToro request failed: {exc}")

    # Cash stays empty: the documented cash endpoint is eToro Money, not the
    # trading account (etoro_mapper.CASH_MAPPED), so it is never fetched.
    parsed = map_account(history, positions, [], instruments)
    errors = [*parsed.errors, *validate_rows(parsed.rows)]
    if errors:
        ledger = ledger_result("needs_review", errors=errors[:MAX_SYNC_ERRORS])
    else:
        ledger = insert_new_provider_rows(db, portfolio, parsed.rows, source=SOURCE)

    if ledger["status"] == "needs_review":
        # Nothing was written; keep last_synced_at so the next sync re-reads
        # the same window once the problem is fixed.
        _flag(db, conn, ledger["errors"][0])
    else:
        if conn.needs_attention and not conn.consecutive_failures:
            # Only a review sets attention without failures (the dead-letter
            # path counts them); this sync imported cleanly.
            conn.needs_attention = False
            conn.last_error = None
        conn.last_synced_at = datetime.now(timezone.utc)
        db.commit()
    return {**ledger, "skipped_reasons": dict(parsed.skipped_reasons)}


@router.post(
    "/sync",
    dependencies=[
        Depends(require_capability("broker_sync")),
        Depends(require_writable_broker(BROKER)),
        Depends(rate_limit("broker_sync", by="workspace")),
    ],
)
def sync(
    db: Session = Depends(get_db),
    portfolio: Portfolio = Depends(require_portfolio),
    _context: RequestContext = Depends(require_csrf),
):
    """User-facing eToro sync for the authorized portfolio."""
    return etoro_sync(db, portfolio.workspace_id, portfolio.id)
