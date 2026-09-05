"""Cloud Scheduler-triggered job endpoints -- the cloud edition's
replacement for the in-process asyncio pollers main.py runs in the local
edition.

Cloud Run scales the web service to multiple instances; an in-process timer
in that world either fires redundantly on every instance (duplicate syncs,
duplicate Discord notifications, duplicate alert triggers) or needs its own
leader-election scheme neither this app nor its infra has. Cloud Scheduler
calling one of these endpoints on a cron schedule, guarded by a Postgres
advisory lock (see with_job_lock below), is simpler than either: exactly
one caller reaches the pass function at a time, and a second overlapping
invocation -- a slow first run plus an on-time second trigger, or Cloud
Scheduler's own retry after a transient failure -- is a safe no-op instead
of a double-run.

This router is mounted only in the cloud edition (see main.py) and is never
under `/api` -- it has its own authentication, not the cookie/CSRF session
model every `/api` route uses. Every request must carry a Google-signed
OIDC ID token for the dedicated `portfyl-scheduler` service account (see
deploy/cloudrun.md) in `Authorization: Bearer <token>`; there is no shared
static secret and no other accepted credential.
"""
from __future__ import annotations

import logging
import os
import uuid
import zlib
from contextlib import contextmanager
from typing import Awaitable, Callable, Iterator, Mapping

from fastapi import APIRouter, Header, HTTPException
from google.auth.transport import requests as google_auth_requests
from google.oauth2 import id_token as google_id_token
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from database import DatabaseSettings, SessionLocal, build_engine
from logging_setup import correlation_id_var

router = APIRouter(prefix="/internal/jobs", tags=["internal-jobs"], include_in_schema=False)
log = logging.getLogger("portfyl.internal_jobs")

_google_auth_request = google_auth_requests.Request()
_job_session_factory = None


def build_job_session_factory(env: Mapping[str, str]):
    """Build scheduler sessions from a direct, non-pooled PostgreSQL URL.

    Neon pooled endpoints use PgBouncer transaction pooling, which cannot
    preserve this router's session-level advisory lock across commits inside
    a job pass. Failing closed prevents silently ineffective cloud locking.
    """
    raw_url = env.get("JOB_DATABASE_URL", "").strip()
    if not raw_url:
        raise RuntimeError(
            "JOB_DATABASE_URL is required for cloud scheduler jobs and must "
            "be a direct PostgreSQL connection URL"
        )
    settings = DatabaseSettings.from_env({**env, "DATABASE_URL": raw_url})
    hostname = (make_url(settings.url).host or "").casefold()
    if "-pooler" in hostname:
        raise RuntimeError(
            "JOB_DATABASE_URL must use the direct Neon hostname, not a "
            "transaction-pooled -pooler endpoint"
        )
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=build_engine(settings),
    )


def _new_job_session() -> Session:
    # Fast tests intentionally use the shared SQLite fixture. Production cloud
    # invocations always take the fail-closed direct-Postgres branch below.
    if os.environ.get("PORTFYL_TESTING") == "1":
        return SessionLocal()
    global _job_session_factory
    if _job_session_factory is None:
        _job_session_factory = build_job_session_factory(os.environ)
    return _job_session_factory()


def verify_scheduler_token(authorization: str | None) -> None:
    """401 for a missing/malformed header; 403 for anything that doesn't
    verify as a Google-signed token for exactly the configured audience and
    service account. Never raises for any other reason -- a caller either
    proves it's Cloud Scheduler with the right identity, or it's rejected."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing scheduler credential")
    token = authorization.removeprefix("Bearer ").strip()

    audience = os.environ.get("PORTFYL_SERVICE_URL", "")
    expected_email = os.environ.get("PORTFYL_SCHEDULER_SERVICE_ACCOUNT", "")
    if not audience or not expected_email:
        raise HTTPException(status_code=403, detail="Scheduler auth is not configured")

    try:
        claims = google_id_token.verify_oauth2_token(token, _google_auth_request, audience=audience)
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Invalid scheduler credential") from exc

    if claims.get("email") != expected_email or not claims.get("email_verified"):
        raise HTTPException(status_code=403, detail="Unexpected scheduler identity")


def _lock_key(job_name: str) -> int:
    # pg_advisory_lock takes a bigint; deterministically fold the job name
    # into one so every instance/invocation contends on the same key.
    return zlib.crc32(job_name.encode("utf-8"))


@contextmanager
def with_job_lock(db: Session, job_name: str) -> Iterator[bool]:
    """Non-blocking Postgres SESSION-level advisory lock -- deliberately not
    pg_try_advisory_XACT_lock, which auto-releases at the pass's first
    internal COMMIT (jobs.py's passes commit more than once per run). A
    session-level lock stays held for this connection's lifetime regardless
    of how many times the pass commits, and is released explicitly in
    `finally` (or by the connection closing, if the process dies mid-pass).
    Yields True if this call acquired the lock (safe to run the pass), False
    if another invocation already holds it (the caller must skip, never
    queue or retry inline -- Cloud Scheduler's own retry policy is the retry
    mechanism).

    pg_try_advisory_lock only exists under PostgreSQL -- this router is only
    ever mounted (and only ever meaningfully concurrent) in the cloud
    edition, which is fail-closed to PostgreSQL (see database.py), but the
    fast unit suite still exercises these endpoints end-to-end against its
    SQLite fixture. There, every call trivially "acquires" the lock, the
    same no-op pattern jobs.py's _rls_enforced already uses for RLS context."""
    if db.get_bind().dialect.name != "postgresql":
        yield True
        return

    key = _lock_key(job_name)
    acquired = bool(db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar_one())
    try:
        yield acquired
    finally:
        if acquired:
            db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})


async def _run_job(job_name: str, pass_fn: Callable[[Session], Awaitable[list]]) -> dict:
    token = correlation_id_var.set(f"job-{job_name}-{uuid.uuid4().hex[:8]}")
    db = _new_job_session()
    try:
        with with_job_lock(db, job_name) as acquired:
            if not acquired:
                log.info("%s: skipped, already running", job_name)
                return {"job": job_name, "skipped": "already running"}
            happened = await pass_fn(db)
            from jobs import mark_job_succeeded

            mark_job_succeeded(db, job_name)
            db.commit()
            if happened:
                log.info("%s pass: %d event(s)", job_name, len(happened))
            return {"job": job_name, "events": len(happened)}
    finally:
        db.close()
        correlation_id_var.reset(token)


@router.post("/alerts")
async def run_alerts_job(authorization: str | None = Header(default=None)) -> dict:
    verify_scheduler_token(authorization)
    from jobs import alert_check_all_workspaces

    return await _run_job("alerts", alert_check_all_workspaces)


@router.post("/autosync")
async def run_autosync_job(authorization: str | None = Header(default=None)) -> dict:
    verify_scheduler_token(authorization)
    from jobs import autosync_all_workspaces

    return await _run_job("autosync", autosync_all_workspaces)


@router.post("/dividends")
async def run_dividends_job(authorization: str | None = Header(default=None)) -> dict:
    verify_scheduler_token(authorization)
    from jobs import dividend_notify_all_workspaces

    return await _run_job("dividends", dividend_notify_all_workspaces)
