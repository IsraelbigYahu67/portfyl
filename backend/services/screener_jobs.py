"""Thread-safe in-process state for local-edition screener jobs."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

JOB_TTL_SECONDS = 1800
MAX_RETAINED_JOBS = 20

_REGISTRY_LOCK = threading.Lock()
_JOBS: dict[str, "ScreenerJob"] = {}


def _now() -> float:
    return time.time()


def _iso_datetime(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class ScreenerJob:
    job_id: str
    user_id: str
    fingerprint: str
    status: str
    request: dict[str, Any]
    created_at: float
    expires_at: float | None
    scan_total: int
    completed_count: int
    result_items: list[dict]
    unavailable_count: int
    error: str | None
    cancel_requested: bool

    def to_response(self, offset: int, limit: int) -> dict[str, Any]:
        percent = round(100 * self.completed_count / self.scan_total) if self.scan_total else 0
        result = None
        if self.status == "completed":
            result = {
                "items": self.result_items[offset : offset + limit],
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
            "created_at": _iso_datetime(self.created_at),
            "expires_at": _iso_datetime(self.expires_at),
        }


def _fingerprint(user_id: str, request: dict[str, Any]) -> str:
    normalized = json.dumps(
        {"user_id": user_id, "request": request},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _prune_expired_and_over_capacity() -> None:
    now = _now()
    with _REGISTRY_LOCK:
        expired_ids = [
            job_id
            for job_id, job in _JOBS.items()
            if job.expires_at is not None and job.expires_at <= now
        ]
        for job_id in expired_ids:
            del _JOBS[job_id]

        if len(_JOBS) > MAX_RETAINED_JOBS:
            newest = sorted(_JOBS.values(), key=lambda job: job.created_at, reverse=True)
            keep_ids = {job.job_id for job in newest[:MAX_RETAINED_JOBS]}
            for job_id in list(_JOBS):
                if job_id not in keep_ids:
                    del _JOBS[job_id]


def _find_reusable_job(user_id: str, fingerprint: str) -> ScreenerJob | None:
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
