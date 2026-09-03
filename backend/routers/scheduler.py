"""Machine entrypoint for external job triggering (Cloud Scheduler in the
cloud edition). Consolidates alert-check, broker-autosync, and
dividend-notify behind one SCHEDULER_TOKEN-authed endpoint; supersedes the
old IBKR-only /api/ibkr/scheduler-sync -- see
docs/superpowers/specs/2026-09-03-portfyl-job-triggering-design.md."""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from auth import check_scheduler_token
from database import get_db
from jobs import (
    alert_check_all_workspaces,
    autosync_all_workspaces,
    dividend_notify_all_workspaces,
)

router = APIRouter(prefix="/jobs", tags=["scheduler"])

JOB_REGISTRY: dict[str, Callable[[Session], Awaitable[list[dict]]]] = {
    "alert_check": alert_check_all_workspaces,
    "autosync": autosync_all_workspaces,
    "dividend_notify": dividend_notify_all_workspaces,
}


@router.post("/run", include_in_schema=False)
async def run_job(
    job: str = Query(...),
    db: Session = Depends(get_db),
    x_scheduler_token: str | None = Header(default=None),
    token: str | None = Query(default=None),
):
    """token (query param) exists only as a manual-testing fallback --
    Cloud Scheduler always sends X-Scheduler-Token as a header."""
    if not check_scheduler_token(x_scheduler_token or token or ""):
        raise HTTPException(status_code=403, detail="Invalid or missing scheduler token")
    fn = JOB_REGISTRY.get(job)
    if fn is None:
        raise HTTPException(status_code=400, detail=f"Unknown job: {job}")
    results = await fn(db)
    return {"status": "ok", "job": job, "events": len(results), "results": results}
