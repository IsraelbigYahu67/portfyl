"""In-process, in-memory job registry for the yfinance universe screener.

No queue library and no database table: one process-wide worker runs at
most one scan at a time (see _run_job in this module for the worker), while
this module owns the shared job state, fingerprint-based deduplication, and
expiry/retention bookkeeping. Every public function acquires _REGISTRY_LOCK
around its read-modify-write of _JOBS so a request thread reading job status
never races the worker thread updating progress.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

JOB_TTL_SECONDS = 1800  # 30 minutes, spec §9.3
MAX_RETAINED_JOBS = 20  # spec §9.3

_REGISTRY_LOCK = threading.Lock()
_JOBS: dict[str, "ScreenerJob"] = {}


def _now() -> float:
    return time.time()


@dataclass
class ScreenerJob:
    job_id: str
    user_id: str
    fingerprint: str
    status: str  # queued | running | completed | failed | cancelled
    request: dict[str, Any]
    created_at: float
    expires_at: float | None
    scan_total: int
    completed_count: int
    result_items: list[dict]
    unavailable_count: int
    error: str | None
    cancel_requested: bool

    def to_response(self, offset: int, limit: int) -> dict:
        percent = (
            round(100 * self.completed_count / self.scan_total)
            if self.scan_total else 0
        )
        result = None
        if self.status == "completed":
            page = self.result_items[offset:offset + limit]
            result = {
                "items": page,
                "total": len(self.result_items),
                "offset": offset,
                "limit": limit,
            }
        return {
            "job_id": self.job_id,
            "status": self.status,
            "progress": {
                "completed": self.completed_count,
                "total": self.scan_total,
                "percent": percent,
            },
            "result": result,
            "unavailable_count": self.unavailable_count,
            "error": self.error,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


def _fingerprint(user_id: str, request: dict[str, Any]) -> str:
    normalized = json.dumps({"user_id": user_id, **request}, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _prune_expired_and_over_capacity() -> None:
    now = _now()
    with _REGISTRY_LOCK:
        for job_id in [
            jid for jid, job in _JOBS.items()
            if job.expires_at is not None and job.expires_at <= now
        ]:
            del _JOBS[job_id]

        if len(_JOBS) > MAX_RETAINED_JOBS:
            ordered = sorted(_JOBS.values(), key=lambda j: j.created_at, reverse=True)
            keep_ids = {j.job_id for j in ordered[:MAX_RETAINED_JOBS]}
            for job_id in list(_JOBS):
                if job_id not in keep_ids:
                    del _JOBS[job_id]


def _find_reusable_job(user_id: str, fingerprint: str) -> "ScreenerJob | None":
    now = _now()
    with _REGISTRY_LOCK:
        for job in _JOBS.values():
            if job.user_id != user_id or job.fingerprint != fingerprint:
                continue
            if job.status in ("queued", "running"):
                return job
            if job.status == "completed" and job.expires_at and job.expires_at > now:
                return job
    return None
