"""Workspace-scoped settings. Currently just the broker auto-sync schedule;
frontend note: '/settings' must stay listed in PORTFOLIO_AGNOSTIC_PREFIXES
in frontend/src/api.js."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app_settings import set_workspace_setting
from database import get_db
from jobs import (SYNC_DAILY_TIME_KEY, SYNC_INTERVAL_HOURS_KEY, SYNC_MODE_KEY,
                  load_sync_schedule, next_sync_run, sync_timezone)
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
