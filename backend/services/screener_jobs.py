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
from concurrent.futures import ThreadPoolExecutor, as_completed
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


_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="screener-job")
_TICKER_BATCH_SIZE = 12  # matches the existing per-ticker fetch concurrency in market.py


def _universe_tickers(request: dict[str, Any]) -> list[str]:
    from routers.market import _PRESET_UNIVERSES

    tickers = request.get("tickers") or ""
    if tickers:
        return list(dict.fromkeys(t.strip().upper() for t in tickers.split(",") if t.strip()))
    universe = request.get("universe") or "sp500"
    return _PRESET_UNIVERSES.get(universe, _PRESET_UNIVERSES["tech_large"])


def _ticker_row(sym: str) -> dict[str, Any]:
    from routers.market import _ticker_screener_row

    return _ticker_screener_row(sym)


def _passes_filters(row: dict[str, Any], request: dict[str, Any]) -> bool:
    from routers.market import _in_range

    sector = request.get("sector")
    if sector and (row.get("sector") or "").lower() != sector.lower():
        return False
    checks = [
        ("pe", "min_pe", "max_pe"), ("forward_pe", "min_forward_pe", "max_forward_pe"),
        ("pb", "min_pb", "max_pb"), ("div_yield", "min_div_yield", "max_div_yield"),
        ("market_cap", "min_market_cap", "max_market_cap"), ("roe", "min_roe", "max_roe"),
        ("net_margin", "min_net_margin", "max_net_margin"), ("ps", "min_ps", "max_ps"),
    ]
    for field_name, lo_key, hi_key in checks:
        if not _in_range(row.get(field_name), request.get(lo_key), request.get(hi_key)):
            return False
    return True


def submit_job(user_id: str, request: dict[str, Any]) -> ScreenerJob:
    _prune_expired_and_over_capacity()
    fingerprint = _fingerprint(user_id, request)

    reusable = _find_reusable_job(user_id, fingerprint)
    if reusable is not None:
        return reusable

    job = ScreenerJob(
        job_id=str(uuid.uuid4()),
        user_id=user_id,
        fingerprint=fingerprint,
        status="queued",
        request=request,
        created_at=_now(),
        expires_at=None,
        scan_total=0,
        completed_count=0,
        result_items=[],
        unavailable_count=0,
        error=None,
        cancel_requested=False,
    )
    with _REGISTRY_LOCK:
        _JOBS[job.job_id] = job

    _EXECUTOR.submit(_run_job, job.job_id)
    return job


def get_job(user_id: str, job_id: str) -> ScreenerJob | None:
    _prune_expired_and_over_capacity()
    with _REGISTRY_LOCK:
        job = _JOBS.get(job_id)
        if job is None or job.user_id != user_id:
            return None
        return job


def cancel_job(user_id: str, job_id: str) -> bool:
    with _REGISTRY_LOCK:
        job = _JOBS.get(job_id)
        if job is None or job.user_id != user_id:
            return False
        if job.status not in ("queued", "running"):
            return False
        job.cancel_requested = True
        return True


def _run_job(job_id: str) -> None:
    with _REGISTRY_LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return
        job.status = "running"
        request = job.request

    try:
        tickers = _universe_tickers(request)
        with _REGISTRY_LOCK:
            job.scan_total = len(tickers)

        rows: list[dict] = []
        unavailable = 0
        for start in range(0, len(tickers), _TICKER_BATCH_SIZE):
            with _REGISTRY_LOCK:
                if job.cancel_requested:
                    job.status = "cancelled"
                    job.expires_at = _now() + JOB_TTL_SECONDS
                    return
            batch = tickers[start:start + _TICKER_BATCH_SIZE]
            with ThreadPoolExecutor(max_workers=len(batch)) as ex:
                futures = {ex.submit(_ticker_row, sym): sym for sym in batch}
                for future in as_completed(futures):
                    try:
                        row = future.result()
                    except Exception:
                        row = {"error": "unavailable"}
                    with _REGISTRY_LOCK:
                        job.completed_count += 1
                        if "error" in row:
                            unavailable += 1
                        elif _passes_filters(row, request):
                            rows.append(row)

        sort_by = request.get("sort_by") or "market_cap"
        sort_desc = bool(request.get("sort_desc", True))
        rows.sort(
            key=lambda r: (r.get(sort_by) or 0) if isinstance(r.get(sort_by), (int, float)) else str(r.get(sort_by, "")),
            reverse=sort_desc,
        )

        with _REGISTRY_LOCK:
            job.result_items = rows
            job.unavailable_count = unavailable
            job.status = "completed"
            job.expires_at = _now() + JOB_TTL_SECONDS
    except Exception:  # pragma: no cover - defensive: job must never hang "running" forever
        with _REGISTRY_LOCK:
            job.status = "failed"
            job.error = "The screener scan failed. Please try again."
            job.expires_at = _now() + JOB_TTL_SECONDS
