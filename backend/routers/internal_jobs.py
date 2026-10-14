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
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from database import DatabaseSettings, SessionLocal, build_engine
from logging_setup import correlation_id_var
from private_loop import run_on_private_loop

router = APIRouter(prefix="/internal/jobs", tags=["internal-jobs"], include_in_schema=False)
log = logging.getLogger("portfyl.internal_jobs")

_google_auth_request = google_auth_requests.Request()
_job_session_factory = None
_lock_engine: Engine | None = None


def _job_database_settings(env: Mapping[str, str]) -> DatabaseSettings:
    """Settings for the direct, non-pooled PostgreSQL URL the jobs run on.

    Neon pooled endpoints use PgBouncer transaction pooling, which cannot
    preserve this router's session-level advisory lock for the duration of a
    job pass. Failing closed prevents silently ineffective cloud locking.
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
    return settings


def build_job_session_factory(env: Mapping[str, str]):
    """Build scheduler sessions from a direct, non-pooled PostgreSQL URL."""
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=build_engine(_job_database_settings(env)),
    )


def build_job_lock_engine(env: Mapping[str, str]) -> Engine:
    """Engine used only to hold a job's advisory lock.

    NullPool is the point: a connection checked out from it is really closed
    on release, so a lock can never survive on a connection parked in a pool.
    The job Session keeps its own pooled engine and returns its connections
    to that pool on every commit, which is exactly why the lock cannot live
    on it.
    """
    return create_engine(_job_database_settings(env).url, poolclass=NullPool)


def _job_lock_engine() -> Engine | None:
    """The engine for with_job_lock, or None where the lock is a no-op (the
    fast suite's SQLite fixture, same switch as _new_job_session)."""
    if os.environ.get("PORTFYL_TESTING") == "1":
        return None
    global _lock_engine
    if _lock_engine is None:
        _lock_engine = build_job_lock_engine(os.environ)
    return _lock_engine


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
def with_job_lock(job_name: str, engine: Engine | None = None) -> Iterator[bool]:
    """Non-blocking Postgres SESSION-level advisory lock held on a dedicated
    connection for the whole pass -- deliberately not pg_try_advisory_XACT_lock,
    which auto-releases at the pass's first internal COMMIT (jobs.py's passes
    commit more than once per run).

    The lock must NOT live on the job Session's connection. That Session is
    bound to a pooled engine and hands its connection back to the pool on
    every commit, so the rest of the pass runs on some other connection and
    the unlock can land on one that does not hold the lock. The lock would
    then sit on a pooled connection until pool_recycle, making the next
    invocation skip as "already running", or be re-entrant on the same
    connection and let two passes run at once. Here the lock owns a
    connection from a NullPool engine that nothing else uses, so it stays
    put until the `finally` below, and closing it really closes the socket
    (which also releases the lock if the process dies mid-pass).

    Yields True if this call acquired the lock (safe to run the pass), False
    if another invocation already holds it (the caller must skip, never
    queue or retry inline -- Cloud Scheduler's own retry policy is the retry
    mechanism).

    pg_try_advisory_lock only exists under PostgreSQL -- this router is only
    ever mounted (and only ever meaningfully concurrent) in the cloud
    edition, which is fail-closed to PostgreSQL (see database.py), but the
    fast unit suite still exercises these endpoints end-to-end against its
    SQLite fixture. There, every call trivially "acquires" the lock, the
    same no-op pattern jobs.py's _rls_enforced already uses for RLS context.
    `engine` is for tests; production resolves it from JOB_DATABASE_URL."""
    if engine is None:
        engine = _job_lock_engine()
    if engine is None or engine.dialect.name != "postgresql":
        yield True
        return

    key = _lock_key(job_name)
    with engine.connect() as lock_conn:
        acquired = bool(
            lock_conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar_one()
        )
        # End the implicit transaction so the lock connection does not sit
        # "idle in transaction" for the whole pass; the session-level lock
        # does not depend on it.
        lock_conn.commit()
        try:
            yield acquired
        finally:
            if acquired:
                try:
                    released = lock_conn.execute(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": key}
                    ).scalar_one()
                    lock_conn.commit()
                except Exception:
                    log.warning("%s: advisory unlock failed; dropping the lock connection", job_name)
                    lock_conn.invalidate()
                else:
                    if not released:
                        log.warning("%s: advisory lock was not held at unlock; dropping the lock connection", job_name)
                        lock_conn.invalidate()


def _run_job(job_name: str, pass_fn: Callable[[Session], Awaitable[list]]) -> dict:
    """Run one pass with its own session. Called from the plain-def job
    endpoints below, so it runs in the threadpool: the token check (which may
    fetch Google's certificates), the advisory lock, and the pass's sync
    database work between its awaits never touch the server's event loop."""
    token = correlation_id_var.set(f"job-{job_name}-{uuid.uuid4().hex[:8]}")
    try:
        with with_job_lock(job_name) as acquired:
            if not acquired:
                log.info("%s: skipped, already running", job_name)
                return {"job": job_name, "skipped": "already running"}
            # The pass runs on its own pooled Session; the lock is held on a
            # separate connection, so the pass's commits cannot disturb it.
            db = _new_job_session()
            try:
                happened = run_on_private_loop(pass_fn, db)
                from jobs import mark_job_succeeded

                mark_job_succeeded(db, job_name)
                db.commit()
            finally:
                db.close()
            if happened:
                log.info("%s pass: %d event(s)", job_name, len(happened))
            return {"job": job_name, "events": len(happened)}
    finally:
        correlation_id_var.reset(token)


@router.post("/alerts")
def run_alerts_job(authorization: str | None = Header(default=None)) -> dict:
    verify_scheduler_token(authorization)
    from jobs import alert_check_all_workspaces

    return _run_job("alerts", alert_check_all_workspaces)


@router.post("/autosync")
def run_autosync_job(authorization: str | None = Header(default=None)) -> dict:
    verify_scheduler_token(authorization)
    from jobs import autosync_all_workspaces

    return _run_job("autosync", autosync_all_workspaces)


@router.post("/dividends")
def run_dividends_job(authorization: str | None = Header(default=None)) -> dict:
    verify_scheduler_token(authorization)
    from jobs import dividend_notify_all_workspaces

    return _run_job("dividends", dividend_notify_all_workspaces)


@router.post("/broker_backfill")
def run_broker_backfill_job(authorization: str | None = Header(default=None)) -> dict:
    verify_scheduler_token(authorization)
    from jobs import broker_backfill_all_workspaces

    return _run_job("broker_backfill", broker_backfill_all_workspaces)


@router.post("/rate_limit_cleanup")
def run_rate_limit_cleanup_job(authorization: str | None = Header(default=None)) -> dict:
    verify_scheduler_token(authorization)
    from jobs import rate_limit_cleanup_pass

    return _run_job("rate_limit_cleanup", rate_limit_cleanup_pass)


@router.post("/account_deletion_cleanup")
def run_account_deletion_cleanup_job(
    authorization: str | None = Header(default=None),
) -> dict:
    verify_scheduler_token(authorization)
    from jobs import account_deletion_cleanup_pass

    return _run_job("account_deletion_cleanup", account_deletion_cleanup_pass)
