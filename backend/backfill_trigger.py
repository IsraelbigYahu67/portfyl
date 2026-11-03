"""Wake the cloud broker_backfill job now instead of at its next hourly tick.

Cloud Scheduler runs /internal/jobs/broker_backfill only hourly: a minutely
schedule kept the Neon database awake around the clock and exhausted its
compute quota (2026-10-19). A Trading 212 history import, though, needs a
pass roughly every minute -- each pass downloads pages until Trading 212's
rate limit stops it, and the limit resets about a minute later.

So the work wakes the job itself, through a Cloud Tasks queue:

* sync_transactions / retry_history enqueue an immediate task right after
  they create a history run, so the first pages arrive within seconds;
* every cloud pass that leaves a run unfinished enqueues one continuation at
  the moment that run is due again (rate-limit reset or retry backoff).

The chain stops by itself once no run is open, and the database is woken only
while there is history to fetch. The hourly scheduler job stays as the safety
net for a lost task. The task calls the same endpoint with the same OIDC
identity Cloud Scheduler uses, so verify_scheduler_token needs no change; the
advisory lock in internal_jobs makes an overlapping task a no-op.

Configured by PORTFYL_BACKFILL_TASKS_QUEUE (the full queue resource name)
plus the PORTFYL_SERVICE_URL / PORTFYL_SCHEDULER_SERVICE_ACCOUNT pair the
job endpoints already need. Unset (local edition, tests) it is a no-op. A
failure is logged and swallowed: the hourly job still picks the run up.
"""
from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone

import httpx

log = logging.getLogger("portfyl.backfill_trigger")

CLOUD_TASKS_API = "https://cloudtasks.googleapis.com/v2"
# Continuations are named by schedule-time bucket, so two passes asking for
# about the same moment create one task (Cloud Tasks answers 409 for the
# second). Immediate wake-ups are unnamed: a user's sync must never be
# swallowed by an earlier task that has already run.
CONTINUATION_BUCKET_SECONDS = 30
# Floor between a pass and its continuation, so a run that is due "now"
# (lease held elsewhere, finalize pending) cannot spin the queue.
MIN_CONTINUATION_SECONDS = 20
# Work due later than this is left to the hourly scheduler job.
MAX_CONTINUATION_SECONDS = 3600

_credentials = None
_credentials_lock = threading.Lock()


def enabled() -> bool:
    return bool(os.environ.get("PORTFYL_BACKFILL_TASKS_QUEUE", "").strip())


def _access_token() -> str:
    """OAuth token of the runtime service account (metadata server on Cloud
    Run), cached and refreshed by google-auth."""
    global _credentials
    import google.auth
    from google.auth.transport.requests import Request

    with _credentials_lock:
        if _credentials is None:
            _credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
        if not _credentials.valid:
            _credentials.refresh(Request())
        return _credentials.token


def request_backfill(*, at: datetime | None = None) -> bool:
    """Enqueue a broker_backfill run: now, or as a continuation at `at`.

    Returns True when a task is queued (or the same continuation already
    was), False when not configured or the enqueue failed. Never raises.
    Makes an outbound HTTPS call: call it with no database connection held.
    """
    queue = os.environ.get("PORTFYL_BACKFILL_TASKS_QUEUE", "").strip()
    if not queue:
        return False
    service_url = os.environ.get("PORTFYL_SERVICE_URL", "").strip().rstrip("/")
    caller = os.environ.get("PORTFYL_SCHEDULER_SERVICE_ACCOUNT", "").strip()
    if not service_url or not caller:
        log.warning("backfill trigger: queue set but scheduler identity is not configured")
        return False

    task: dict = {
        "httpRequest": {
            "httpMethod": "POST",
            "url": f"{service_url}/internal/jobs/broker_backfill",
            "oidcToken": {"serviceAccountEmail": caller, "audience": service_url},
        },
    }
    if at is not None:
        at = at.astimezone(timezone.utc)
        bucket = int(at.timestamp()) // CONTINUATION_BUCKET_SECONDS
        task["name"] = f"{queue}/tasks/backfill-{bucket}"
        task["scheduleTime"] = at.strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        resp = httpx.post(
            f"{CLOUD_TASKS_API}/{queue}/tasks",
            json={"task": task},
            headers={"Authorization": f"Bearer {_access_token()}"},
            timeout=10,
        )
    except Exception as exc:
        log.warning("backfill trigger: enqueue failed (%s)", type(exc).__name__)
        return False
    if resp.status_code == 409 and at is not None:
        return True  # this continuation is already queued
    if resp.status_code >= 400:
        log.warning("backfill trigger: Cloud Tasks returned %s", resp.status_code)
        return False
    return True
