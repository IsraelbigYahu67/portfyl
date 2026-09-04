"""Workspace-scoped settings. Currently just the broker auto-sync schedule;
frontend note: '/settings' must stay listed in PORTFOLIO_AGNOSTIC_PREFIXES
in frontend/src/api.js."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app_settings import set_workspace_setting
from database import get_db
from jobs import (SYNC_DAILY_TIME_KEY, SYNC_INTERVAL_HOURS_KEY, SYNC_MODE_KEY,
                  load_sync_schedule, next_sync_run, sync_timezone)
from models import AuditLog
from tenancy import RequestContext, get_request_context

router = APIRouter(prefix="/settings", tags=["settings"])


class SyncSchedule(BaseModel):
    mode: Literal["daily", "interval"]
    daily_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    interval_hours: int = Field(ge=1, le=168)


@router.get("/sync-schedule")
def get_sync_schedule(
    db: Session = Depends(get_db),
    context: RequestContext = Depends(get_request_context),
):
    s = load_sync_schedule(db, context.workspace.id)
    tz = sync_timezone()
    nxt = next_sync_run(datetime.now(timezone.utc), s["mode"], s["daily_time"],
                        s["interval_hours"], s["last_run"], tz)
    return {
        "mode": s["mode"],
        "daily_time": s["daily_time"],
        "interval_hours": s["interval_hours"],
        "timezone": tz.key,
        "last_run": s["last_run"].isoformat() if s["last_run"] else None,
        "next_run": nxt.isoformat() if nxt else None,
    }


@router.put("/sync-schedule")
def put_sync_schedule(
    payload: SyncSchedule,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(get_request_context),
):
    set_workspace_setting(db, context.workspace.id, SYNC_MODE_KEY, payload.mode)
    set_workspace_setting(db, context.workspace.id, SYNC_DAILY_TIME_KEY, payload.daily_time)
    set_workspace_setting(db, context.workspace.id, SYNC_INTERVAL_HOURS_KEY, str(payload.interval_hours))
    db.commit()
    return get_sync_schedule(db, context)


@router.get("/audit-log")
def get_audit_log(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    context: RequestContext = Depends(get_request_context),
):
    """Return workspace events plus the caller's personal security events.

    The explicit predicate is required even though PostgreSQL applies the same
    rule through forced RLS; the fast SQLite suite and defense in depth both
    rely on application-level scoping.
    """
    visible = or_(
        AuditLog.workspace_id == context.workspace.id,
        (
            AuditLog.workspace_id.is_(None)
            & (AuditLog.actor_user_id == context.user.id)
        ),
    )
    total = db.scalar(select(func.count()).select_from(AuditLog).where(visible)) or 0
    rows = db.scalars(
        select(AuditLog)
        .where(visible)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return {
        "items": [
            {
                "id": str(row.public_id),
                "workspace_id": str(row.workspace_id) if row.workspace_id else None,
                "actor_user_id": str(row.actor_user_id),
                "action": row.action,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "metadata": row.event_metadata or {},
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
        "page": page,
        "page_size": page_size,
        "total": total,
    }
