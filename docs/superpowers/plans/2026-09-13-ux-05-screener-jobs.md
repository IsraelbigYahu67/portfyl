# Non-Blocking Screener Jobs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the synchronous, blocking yfinance-universe screener request with an authenticated, in-process background job (create → poll → cancel/retry), fix the `_in_range` missing-value bug, and keep the Shibui whole-market path synchronous exactly as today.

**Architecture:** A new `backend/services/screener_jobs.py` module owns an in-memory job registry (dict + lock) and a single-worker `ThreadPoolExecutor` that runs at most one yfinance universe scan at a time process-wide, reusing the existing per-ticker `ThreadPoolExecutor(max_workers=12)` fetch pattern from `backend/routers/market.py` in small batches so cancellation can actually stop scheduling further batches. Three new FastAPI routes (`POST/GET/DELETE /api/market/screener/jobs...`) are registered the same way the existing synchronous `/market/screener` route is registered today — through `backend/routers/local_features.py`, so the feature stays local-edition-only with zero new capability wiring. The frontend gets a small `useScreenerJob` hook that creates a job, polls it every second (paused while the tab is hidden), and persists the job ID in `sessionStorage` so navigating away and back within the TTL reconnects instead of losing progress. `Screener.jsx` is rewired onto this hook and the Plan 4 `Pagination` component for its results.

**Tech Stack:** FastAPI (sync `def` route handlers, run in FastAPI's default threadpool), Python `threading`/`concurrent.futures.ThreadPoolExecutor` (no new dependency — no Celery/Redis/queue library exists in `requirements.txt` today and none is added), React 18 + `@tanstack/react-query` (existing `fetchScreener`-style axios client in `frontend/src/editions/localApi.js`), Vitest + React Testing Library with fake timers for the polling/visibility behavior.

**Spec:** docs/superpowers/specs/2026-09-13-portfyl-ux-product-coherence-design.md (§9.3 Screener jobs is this plan's primary source; §7.3 Pagination and §7.2 Async states are consumed, not built, here)

**Branch:** `codex/ux-05-screener-jobs`
**Depends on:** Plan 4 (`codex/ux-04-scalable-collections`) merged into `codex/portfyl-ux-overhaul`. This plan assumes, and must not reimplement:
- `frontend/src/components/ui/Pagination.jsx` with the exact contract `<Pagination offset={offset} limit={limit} total={total} onOffsetChange={setOffset} ariaLabel="..." />`, page sizes 25/50/100, default 50.
- `frontend/src/lib/apiError.js`'s `getApiErrorMessage(error, fallback)` and `frontend/src/components/ui/AsyncSection.jsx` (Plan 2).
- `frontend/src/components/layout/AppShell.jsx` / `navigation.js` (Plan 3) — this plan does not touch navigation or shell layout.
**Merges into:** `codex/portfyl-ux-overhaul` (never `main`).

Before editing, create a dedicated worktree from the current integration-branch HEAD and run this guard:

```powershell
$branch = (git branch --show-current).Trim()
if ($branch -eq 'main') { throw 'Refusing to work on main' }
git status --short
```

Stop if the worktree contains unexplained changes that overlap this plan. Never discard, reset, or stage another person's work. Commit small coherent steps using only the exact files named per task — never `git add -A`. Push the task branch and open a PR targeting `codex/portfyl-ux-overhaul`, not `main`.

## Global Constraints

- Trust before polish; errors are not empty states; progressive disclosure; one source of truth; responsive not reduced; reversible delivery; no speculative infrastructure — **no queue service (Celery/Redis/etc.) and no new database table are introduced for jobs; the registry is in-process memory** (spec §5, §7 design principle 7, §9.3, §19).
- Job statuses are exactly `queued`, `running`, `completed`, `failed`, `cancelled` — no others (spec §9.3).
- Job JSON contract is exactly:
  ```json
  {
    "job_id": "uuid",
    "status": "running",
    "progress": {"completed": 143, "total": 503, "percent": 28},
    "result": {"items": [], "total": 0, "offset": 0, "limit": 50},
    "unavailable_count": 4,
    "error": null,
    "created_at": "2026-09-13T10:00:00Z",
    "expires_at": "2026-09-13T10:30:00Z"
  }
  ```
  `result` is `null` before completion; `error` is a safe user-facing message only for a failed job (spec §9.3).
- Endpoints: `POST /api/market/screener/jobs` (body: universe/filters/sort, returns HTTP 202); `GET /api/market/screener/jobs/{job_id}?offset=0&limit=50`; `DELETE /api/market/screener/jobs/{job_id}` to request cancellation (spec §9.3).
- Jobs are bound to the authenticated user identity on the server, never to a client-supplied owner ID. Unknown, expired, or other-user job IDs return 404 (spec §9.3).
- One active yfinance scan process-wide; later distinct requests queue. An identical request fingerprint from the same user reuses its active or unexpired completed job. Each future completion increments progress under a lock. Cancellation stops scheduling/collecting additional work where possible; it does not claim an already-running external call was killed (spec §9.3).
- Completed/failed/cancelled jobs expire after 30 minutes; registry cleanup also enforces a maximum of 20 retained jobs (spec §9.3).
- `_in_range(None, None, None)` must return `True`; a missing value fails only when at least one bound for that metric is present (spec §9.3, §2 item 8).
- The synchronous legacy yfinance GET (`GET /api/market/screener` with `source="yfinance"`, the default) remains temporarily available and deprecated, but the SPA stops calling it for the yfinance path. The Shibui path (`source="shibui"`) stays synchronous exactly as today — it is one bounded DB query, not a per-ticker scan (spec §9.3).
- Screener stays local-edition-only; no new capability wiring beyond the existing `local_features.py` mounting pattern (spec §3, CLAUDE.md edition boundary).
- Polling is 1 second while queued/running, paused when the tab is hidden and resumed on visibility. Navigating away does not cancel the job automatically; returning within the TTL reconnects to the job ID stored in session storage (spec §9.3).
- No `git add -A`; PRs target `codex/portfyl-ux-overhaul`.

---

## Task 1: Fix `_in_range` missing-value semantics

**Files:**
- Modify: `backend/routers/market.py` (the `_in_range` function, currently around line 2255)
- Test: `backend/tests/test_analytics.py` or a new `backend/tests/test_screener_jobs.py` (this task creates that new test file since Task 2 will keep using it)

**Interfaces:**
- Produces: `_in_range(val: float | None, lo: float | None, hi: float | None) -> bool` — unchanged signature, corrected semantics. Used by both the existing synchronous `stock_screener` filter loop and the new job's filter loop in Task 3.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_screener_jobs.py`:

```python
"""Tests for the screener job service (backend/services/screener_jobs.py)
and the _in_range missing-value fix it depends on."""

from routers.market import _in_range


def test_in_range_no_bounds_and_no_value_is_true():
    # A metric nobody filtered on must never exclude a row just because the
    # provider didn't return that field.
    assert _in_range(None, None, None) is True


def test_in_range_missing_value_with_a_bound_is_false():
    assert _in_range(None, 10, None) is False
    assert _in_range(None, None, 10) is False
    assert _in_range(None, 5, 10) is False


def test_in_range_present_value_still_respects_bounds():
    assert _in_range(5, 10, None) is False
    assert _in_range(15, 10, None) is True
    assert _in_range(15, None, 10) is False
    assert _in_range(7, 5, 10) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_screener_jobs.py -v`
Expected: `test_in_range_no_bounds_and_no_value_is_true` FAILS (current code returns `False` for `val=None` unconditionally); the other two tests PASS already.

- [ ] **Step 3: Fix `_in_range`**

In `backend/routers/market.py`, replace the current implementation:

```python
def _in_range(val: float | None, lo: float | None, hi: float | None) -> bool:
    """Check if val is within [lo, hi] (inclusive). A missing value only
    fails the filter when at least one bound for that metric was actually
    set; if the caller left the metric unfiltered, a provider that simply
    didn't return the field must not silently exclude the row."""
    if val is None:
        return lo is None and hi is None
    if lo is not None and val < lo:
        return False
    if hi is not None and val > hi:
        return False
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_screener_jobs.py -v`
Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/market.py backend/tests/test_screener_jobs.py
git commit -m "fix: _in_range no longer excludes rows on unset filters"
```

---

## Task 2: Job registry — data model, fingerprinting, TTL/retention

**Files:**
- Create: `backend/services/__init__.py` (empty — the `backend/services/` package does not exist yet)
- Create: `backend/services/screener_jobs.py`
- Test: `backend/tests/test_screener_jobs.py` (extends Task 1's file)

**Interfaces:**
- Consumes: nothing new from other tasks.
- Produces (used by Task 3 and Task 4):
  - `class ScreenerJob` — dataclass with fields `job_id: str`, `user_id: str`, `fingerprint: str`, `status: str`, `request: dict`, `created_at: float`, `expires_at: float | None`, `scan_total: int`, `completed_count: int`, `result_items: list[dict]`, `unavailable_count: int`, `error: str | None`, `cancel_requested: bool`.
  - `def _fingerprint(user_id: str, request: dict) -> str` — deterministic hash of user + normalized request.
  - `def _now() -> float` — thin wrapper over `time.time()` so tests can monkeypatch it.
  - `def _prune_expired_and_over_capacity() -> None` — internal cleanup, called from every public entry point.
  - `_JOBS: dict[str, ScreenerJob]` and `_REGISTRY_LOCK: threading.Lock` module-level state.
  - `JOB_TTL_SECONDS = 1800` and `MAX_RETAINED_JOBS = 20` module constants.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_screener_jobs.py`:

```python
import time

from services import screener_jobs as sj


def _reset_registry():
    with sj._REGISTRY_LOCK:
        sj._JOBS.clear()


def test_fingerprint_is_stable_for_same_user_and_request():
    req = {"universe": "sp500", "sort_by": "market_cap", "sort_desc": True}
    assert sj._fingerprint("user-1", req) == sj._fingerprint("user-1", dict(req))


def test_fingerprint_differs_by_user_or_request():
    req = {"universe": "sp500"}
    assert sj._fingerprint("user-1", req) != sj._fingerprint("user-2", req)
    assert sj._fingerprint("user-1", req) != sj._fingerprint("user-1", {"universe": "nasdaq100"})


def test_prune_removes_expired_jobs():
    _reset_registry()
    job = sj.ScreenerJob(
        job_id="j1", user_id="user-1", fingerprint="fp1", status="completed",
        request={}, created_at=sj._now() - 3600, expires_at=sj._now() - 1,
        scan_total=1, completed_count=1, result_items=[], unavailable_count=0,
        error=None, cancel_requested=False,
    )
    with sj._REGISTRY_LOCK:
        sj._JOBS["j1"] = job
    sj._prune_expired_and_over_capacity()
    with sj._REGISTRY_LOCK:
        assert "j1" not in sj._JOBS


def test_prune_enforces_max_retained_jobs():
    _reset_registry()
    now = sj._now()
    with sj._REGISTRY_LOCK:
        for i in range(25):
            sj._JOBS[f"j{i}"] = sj.ScreenerJob(
                job_id=f"j{i}", user_id="user-1", fingerprint=f"fp{i}", status="completed",
                request={}, created_at=now - i, expires_at=now + 1800,
                scan_total=1, completed_count=1, result_items=[], unavailable_count=0,
                error=None, cancel_requested=False,
            )
    sj._prune_expired_and_over_capacity()
    with sj._REGISTRY_LOCK:
        assert len(sj._JOBS) == sj.MAX_RETAINED_JOBS
        # Oldest jobs (highest i, since created_at = now - i means larger i is older) are evicted first.
        assert "j0" in sj._JOBS
        assert "j24" not in sj._JOBS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_screener_jobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'services'`.

- [ ] **Step 3: Create the package and the registry module**

Create `backend/services/__init__.py` (empty file).

Create `backend/services/screener_jobs.py`:

```python
"""In-process, in-memory job registry for the yfinance universe screener.

No queue library and no database table: one process-wide worker runs at
most one scan at a time (see run_job in this module for the worker), while
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
from dataclasses import dataclass, field
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_screener_jobs.py -v`
Expected: all tests PASS (7 total so far).

- [ ] **Step 5: Commit**

```bash
git add backend/services/__init__.py backend/services/screener_jobs.py backend/tests/test_screener_jobs.py
git commit -m "feat: in-memory screener job registry with fingerprint dedup and TTL/retention"
```

---

## Task 3: Job execution — background worker, progress, cancellation

**Files:**
- Modify: `backend/services/screener_jobs.py`
- Test: `backend/tests/test_screener_jobs.py`

**Interfaces:**
- Consumes: `backend.routers.market._ticker_screener_row`, `backend.routers.market._in_range`, `backend.routers.market._PRESET_UNIVERSES` (imported lazily inside `screener_jobs.py` functions to avoid a circular import, since `market.py` will import this module's public functions in Task 4).
- Produces (used by Task 4):
  - `def submit_job(user_id: str, request: dict) -> ScreenerJob` — creates or reuses a job per the fingerprint rule, enqueues it on the shared single-worker executor, returns immediately.
  - `def get_job(user_id: str, job_id: str) -> ScreenerJob | None` — `None` if missing, expired, or owned by a different user.
  - `def cancel_job(user_id: str, job_id: str) -> bool` — `True` if a cancellable job was found and flagged, `False` otherwise (including wrong user / not found).
  - `_EXECUTOR: concurrent.futures.ThreadPoolExecutor` (module-level, `max_workers=1`) — enforces "one active scan process-wide"; later distinct submissions queue in this executor's own FIFO queue, so no separate queueing logic is needed.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_screener_jobs.py`:

```python
import threading
from unittest.mock import patch


def _fake_row(sym, price=100.0, pe=15.0):
    return {"ticker": sym, "name": sym, "price": price, "market_cap": 1e9, "pe": pe, "sector": "Technology"}


def test_submit_job_dedups_identical_request_from_same_user():
    _reset_registry()
    gate = threading.Event()

    def slow_row(sym):
        gate.wait(timeout=2)
        return _fake_row(sym)

    with patch("services.screener_jobs._ticker_row", side_effect=slow_row):
        req = {"universe": "tech_large", "tickers": "", "sort_by": "market_cap", "sort_desc": True, "limit": 50}
        job1 = sj.submit_job("user-1", req)
        job2 = sj.submit_job("user-1", dict(req))
        assert job1.job_id == job2.job_id
        gate.set()
        _wait_for_status(job1.job_id, "user-1", {"completed", "failed", "cancelled"})


def test_submit_job_does_not_dedup_across_users():
    _reset_registry()
    with patch("services.screener_jobs._ticker_row", side_effect=lambda sym: _fake_row(sym)):
        req = {"universe": "tech_large", "tickers": "", "sort_by": "market_cap", "sort_desc": True, "limit": 50}
        job1 = sj.submit_job("user-1", req)
        job2 = sj.submit_job("user-2", dict(req))
        assert job1.job_id != job2.job_id
        _wait_for_status(job1.job_id, "user-1", {"completed", "failed", "cancelled"})
        _wait_for_status(job2.job_id, "user-2", {"completed", "failed", "cancelled"})


def _wait_for_status(job_id, user_id, statuses, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = sj.get_job(user_id, job_id)
        if job is not None and job.status in statuses:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not reach {statuses} in time")


def test_job_completes_and_progress_reaches_total():
    _reset_registry()
    tickers = ["AAA", "BBB", "CCC"]
    with patch("services.screener_jobs._universe_tickers", return_value=tickers), \
         patch("services.screener_jobs._ticker_row", side_effect=lambda sym: _fake_row(sym)):
        job = sj.submit_job("user-1", {"universe": "tech_large", "tickers": "", "sort_by": "market_cap", "sort_desc": True, "limit": 50})
        done = _wait_for_status(job.job_id, "user-1", {"completed"})
        assert done.completed_count == done.scan_total == len(tickers)
        assert done.result_items and len(done.result_items) == len(tickers)


def test_job_cancellation_stops_scheduling_further_batches():
    _reset_registry()
    tickers = [f"T{i}" for i in range(40)]
    started = threading.Event()
    release = threading.Event()

    def slow_row(sym):
        started.set()
        release.wait(timeout=2)
        return _fake_row(sym)

    with patch("services.screener_jobs._universe_tickers", return_value=tickers), \
         patch("services.screener_jobs._ticker_row", side_effect=slow_row):
        job = sj.submit_job("user-1", {"universe": "tech_large", "tickers": "", "sort_by": "market_cap", "sort_desc": True, "limit": 50})
        assert started.wait(timeout=2)
        assert sj.cancel_job("user-1", job.job_id) is True
        release.set()
        done = _wait_for_status(job.job_id, "user-1", {"cancelled"})
        # Cancellation must stop scheduling further batches; it must not have
        # processed every one of the 40 tickers (batch size is 12 per Step 3).
        assert done.completed_count < len(tickers)


def test_get_job_returns_none_for_wrong_user_or_missing():
    _reset_registry()
    with patch("services.screener_jobs._ticker_row", side_effect=lambda sym: _fake_row(sym)):
        job = sj.submit_job("user-1", {"universe": "tech_large", "tickers": "", "sort_by": "market_cap", "sort_desc": True, "limit": 50})
        _wait_for_status(job.job_id, "user-1", {"completed", "failed", "cancelled"})
        assert sj.get_job("user-2", job.job_id) is None
        assert sj.get_job("user-1", "not-a-real-id") is None


def test_cancel_job_returns_false_for_wrong_user_or_missing():
    _reset_registry()
    with patch("services.screener_jobs._ticker_row", side_effect=lambda sym: _fake_row(sym)):
        job = sj.submit_job("user-1", {"universe": "tech_large", "tickers": "", "sort_by": "market_cap", "sort_desc": True, "limit": 50})
        assert sj.cancel_job("user-2", job.job_id) is False
        assert sj.cancel_job("user-1", "not-a-real-id") is False
        _wait_for_status(job.job_id, "user-1", {"completed", "failed", "cancelled"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_screener_jobs.py -v`
Expected: FAIL — `submit_job`, `get_job`, `cancel_job`, `_ticker_row`, `_universe_tickers` don't exist yet.

- [ ] **Step 3: Implement the worker and public API**

Append to `backend/services/screener_jobs.py`:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

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
    except Exception as exc:  # pragma: no cover - defensive: job must never hang "running" forever
        with _REGISTRY_LOCK:
            job.status = "failed"
            job.error = "The screener scan failed. Please try again."
            job.expires_at = _now() + JOB_TTL_SECONDS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_screener_jobs.py -v`
Expected: all tests PASS (13 total so far). If the dedup or cancellation tests are flaky under CI timing, increase the `timeout=` values in `_wait_for_status` rather than removing the assertions.

- [ ] **Step 5: Commit**

```bash
git add backend/services/screener_jobs.py backend/tests/test_screener_jobs.py
git commit -m "feat: run screener scans as a single-worker background job with batch cancellation"
```

---

## Task 4: FastAPI endpoints, wired into the local edition

**Files:**
- Modify: `backend/routers/market.py` (add the three endpoint functions near the existing `stock_screener`)
- Modify: `backend/routers/local_features.py` (register the three new routes)
- Test: `backend/tests/test_screener_jobs.py`

**Interfaces:**
- Consumes: `services.screener_jobs.submit_job/get_job/cancel_job`, `tenancy.RequestContext`/`get_request_context` (existing pattern used by every authenticated router, e.g. `backend/routers/watchlists.py`).
- Produces (used by Task 5/6 on the frontend): the three HTTP endpoints below, matching the spec's job JSON contract exactly.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_screener_jobs.py`:

```python
import pytest
from fastapi import HTTPException

from routers.market import create_screener_job, get_screener_job, cancel_screener_job, ScreenerJobRequest
from tenancy import RequestContext


class _FakeUser:
    def __init__(self, id):
        self.id = id


def _ctx(user_id: str) -> RequestContext:
    # RequestContext is a frozen dataclass with user/workspace/membership/session;
    # only `.user.id` is read by the new endpoints, so the other fields are
    # left as None -- this matches how other fast-suite tests exercise router
    # functions directly without building a full authenticated HTTP request.
    return RequestContext(user=_FakeUser(user_id), workspace=None, membership=None, session=None)


def test_create_screener_job_endpoint_returns_202_shaped_payload():
    _reset_registry()
    with patch("services.screener_jobs._ticker_row", side_effect=lambda sym: _fake_row(sym)):
        body = ScreenerJobRequest(universe="tech_large")
        job = create_screener_job(body, ctx=_ctx("user-1"))
        assert job["status"] in ("queued", "running")
        assert job["job_id"]
        assert job["result"] is None
        _wait_for_status(job["job_id"], "user-1", {"completed", "failed", "cancelled"})


def test_get_screener_job_endpoint_404s_for_wrong_user():
    _reset_registry()
    with patch("services.screener_jobs._ticker_row", side_effect=lambda sym: _fake_row(sym)):
        body = ScreenerJobRequest(universe="tech_large")
        job = create_screener_job(body, ctx=_ctx("user-1"))
        _wait_for_status(job["job_id"], "user-1", {"completed", "failed", "cancelled"})
        with pytest.raises(HTTPException) as exc_info:
            get_screener_job(job["job_id"], offset=0, limit=50, ctx=_ctx("user-2"))
        assert exc_info.value.status_code == 404


def test_cancel_screener_job_endpoint_404s_when_not_cancellable():
    _reset_registry()
    with patch("services.screener_jobs._ticker_row", side_effect=lambda sym: _fake_row(sym)):
        body = ScreenerJobRequest(universe="tech_large")
        job = create_screener_job(body, ctx=_ctx("user-1"))
        _wait_for_status(job["job_id"], "user-1", {"completed", "failed", "cancelled"})
        with pytest.raises(HTTPException) as exc_info:
            cancel_screener_job(job["job_id"], ctx=_ctx("user-1"))
        assert exc_info.value.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_screener_jobs.py -v`
Expected: FAIL — `create_screener_job`, `get_screener_job`, `cancel_screener_job`, `ScreenerJobRequest` don't exist yet.

- [ ] **Step 3: Add the endpoint functions**

In `backend/routers/market.py`, add near `stock_screener` (after it, using the same `_f`/typing imports already present in the file):

```python
from pydantic import BaseModel
from fastapi import HTTPException
from tenancy import RequestContext, get_request_context
from services import screener_jobs


class ScreenerJobRequest(BaseModel):
    universe: str = "sp500"
    tickers: str = ""
    sector: str = ""
    min_pe: float | None = None
    max_pe: float | None = None
    min_forward_pe: float | None = None
    max_forward_pe: float | None = None
    min_pb: float | None = None
    max_pb: float | None = None
    min_div_yield: float | None = None
    max_div_yield: float | None = None
    min_market_cap: float | None = None
    max_market_cap: float | None = None
    min_roe: float | None = None
    max_roe: float | None = None
    min_net_margin: float | None = None
    max_net_margin: float | None = None
    min_ps: float | None = None
    max_ps: float | None = None
    sort_by: str = "market_cap"
    sort_desc: bool = True


def create_screener_job(body: ScreenerJobRequest, ctx: RequestContext = Depends(get_request_context)):
    job = screener_jobs.submit_job(str(ctx.user.id), body.model_dump())
    return job.to_response(offset=0, limit=50)


def get_screener_job(
    job_id: str,
    offset: int = 0,
    limit: int = 50,
    ctx: RequestContext = Depends(get_request_context),
):
    job = screener_jobs.get_job(str(ctx.user.id), job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Screener job not found or expired")
    safe_limit = limit if limit in (25, 50, 100) else 50
    return job.to_response(offset=max(0, offset), limit=safe_limit)


def cancel_screener_job(job_id: str, ctx: RequestContext = Depends(get_request_context)):
    cancelled = screener_jobs.cancel_job(str(ctx.user.id), job_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail="Screener job not found or already finished")
    return {"job_id": job_id, "status": "cancelled"}
```

Confirm `Depends` is already imported in `market.py` (it is, for other routes in the file); add it to the existing `from fastapi import ...` line if it is not.

In `backend/routers/local_features.py`, register the three routes the same way `stock_screener` is registered:

```python
from routers.market import stock_screener, create_screener_job, get_screener_job, cancel_screener_job

# ... existing router.add_api_route("/market/screener", stock_screener, ...) stays as-is ...

router.add_api_route(
    "/market/screener/jobs",
    create_screener_job,
    methods=["POST"],
    tags=["market"],
    status_code=202,
)
router.add_api_route(
    "/market/screener/jobs/{job_id}",
    get_screener_job,
    methods=["GET"],
    tags=["market"],
)
router.add_api_route(
    "/market/screener/jobs/{job_id}",
    cancel_screener_job,
    methods=["DELETE"],
    tags=["market"],
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_screener_jobs.py -v`
Expected: all tests PASS (16 total).

- [ ] **Step 5: Run the full fast backend suite**

Run: `cd backend && python -m pytest tests/ -v --ignore=tests/postgres`
Expected: PASS, no regressions in unrelated suites (baseline was 584 passed before this plan per spec §16.1; this plan adds tests and touches no existing endpoint's response shape, so the count should only grow).

- [ ] **Step 6: Commit**

```bash
git add backend/routers/market.py backend/routers/local_features.py backend/tests/test_screener_jobs.py
git commit -m "feat: expose screener job create/status/cancel endpoints in the local edition"
```

---

## Task 5: Frontend `useScreenerJob` hook

**Files:**
- Create: `frontend/src/hooks/useScreenerJob.js`
- Modify: `frontend/src/editions/localApi.js` (add job API calls next to `fetchScreener`)
- Test: `frontend/src/hooks/useScreenerJob.test.js`

**Interfaces:**
- Consumes: the axios `api` client already used by `fetchScreener` in `frontend/src/editions/localApi.js`.
- Produces (used by Task 6): `useScreenerJob()` returning `{ job, isPolling, createJob(params), cancel(), retry() }`, where `job` is the raw job-status JSON from the backend or `null` before the first creation/reconnect.

- [ ] **Step 1: Add the job API calls**

In `frontend/src/editions/localApi.js`, add next to the existing `fetchScreener`:

```js
export const createScreenerJob = (body = {}) =>
  api.post("/market/screener/jobs", body).then((r) => r.data);

export const fetchScreenerJob = (jobId, { offset = 0, limit = 50 } = {}) =>
  api.get(`/market/screener/jobs/${jobId}`, { params: { offset, limit } }).then((r) => r.data);

export const cancelScreenerJob = (jobId) =>
  api.delete(`/market/screener/jobs/${jobId}`).then((r) => r.data);
```

- [ ] **Step 2: Write the failing hook test**

Create `frontend/src/hooks/useScreenerJob.test.js`:

```js
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useScreenerJob } from "./useScreenerJob";
import * as localApi from "../editions/localApi";

const SESSION_KEY = "sb_screener_job_id";

describe("useScreenerJob", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    sessionStorage.clear();
    vi.spyOn(localApi, "createScreenerJob");
    vi.spyOn(localApi, "fetchScreenerJob");
    vi.spyOn(localApi, "cancelScreenerJob");
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("creates a job, stores its id in sessionStorage, and polls every second", async () => {
    localApi.createScreenerJob.mockResolvedValue({ job_id: "j1", status: "queued", progress: { completed: 0, total: 0, percent: 0 }, result: null, error: null });
    localApi.fetchScreenerJob.mockResolvedValue({ job_id: "j1", status: "running", progress: { completed: 5, total: 10, percent: 50 }, result: null, error: null });

    const { result } = renderHook(() => useScreenerJob());

    await act(async () => {
      await result.current.createJob({ universe: "sp500" });
    });

    expect(sessionStorage.getItem(SESSION_KEY)).toBe("j1");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(localApi.fetchScreenerJob).toHaveBeenCalledWith("j1", expect.any(Object));
  });

  it("pauses polling while the tab is hidden and resumes on visibility", async () => {
    localApi.createScreenerJob.mockResolvedValue({ job_id: "j2", status: "queued", progress: { completed: 0, total: 0, percent: 0 }, result: null, error: null });
    localApi.fetchScreenerJob.mockResolvedValue({ job_id: "j2", status: "running", progress: { completed: 1, total: 10, percent: 10 }, result: null, error: null });

    const { result } = renderHook(() => useScreenerJob());
    await act(async () => {
      await result.current.createJob({ universe: "sp500" });
    });

    Object.defineProperty(document, "hidden", { value: true, configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));

    const callsWhileHidden = localApi.fetchScreenerJob.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(localApi.fetchScreenerJob.mock.calls.length).toBe(callsWhileHidden);

    Object.defineProperty(document, "hidden", { value: false, configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(localApi.fetchScreenerJob.mock.calls.length).toBeGreaterThan(callsWhileHidden);
  });

  it("reconnects to a job id already in sessionStorage on mount", async () => {
    sessionStorage.setItem(SESSION_KEY, "j3");
    localApi.fetchScreenerJob.mockResolvedValue({ job_id: "j3", status: "completed", progress: { completed: 10, total: 10, percent: 100 }, result: { items: [], total: 0, offset: 0, limit: 50 }, error: null });

    const { result } = renderHook(() => useScreenerJob());
    await waitFor(() => expect(result.current.job?.job_id).toBe("j3"));
    expect(localApi.createScreenerJob).not.toHaveBeenCalled();
  });

  it("clears sessionStorage and stops polling once status is a terminal state", async () => {
    localApi.createScreenerJob.mockResolvedValue({ job_id: "j4", status: "queued", progress: { completed: 0, total: 0, percent: 0 }, result: null, error: null });
    localApi.fetchScreenerJob.mockResolvedValue({ job_id: "j4", status: "completed", progress: { completed: 5, total: 5, percent: 100 }, result: { items: [], total: 0, offset: 0, limit: 50 }, error: null });

    const { result } = renderHook(() => useScreenerJob());
    await act(async () => {
      await result.current.createJob({ universe: "sp500" });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.job.status).toBe("completed");

    const callsAfterCompletion = localApi.fetchScreenerJob.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(localApi.fetchScreenerJob.mock.calls.length).toBe(callsAfterCompletion);
  });

  it("cancel() calls the cancel endpoint with the current job id", async () => {
    localApi.createScreenerJob.mockResolvedValue({ job_id: "j5", status: "running", progress: { completed: 1, total: 10, percent: 10 }, result: null, error: null });
    localApi.cancelScreenerJob.mockResolvedValue({ job_id: "j5", status: "cancelled" });

    const { result } = renderHook(() => useScreenerJob());
    await act(async () => {
      await result.current.createJob({ universe: "sp500" });
    });
    await act(async () => {
      await result.current.cancel();
    });
    expect(localApi.cancelScreenerJob).toHaveBeenCalledWith("j5");
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npm test -- src/hooks/useScreenerJob.test.js`
Expected: FAIL — `./useScreenerJob` does not exist.

- [ ] **Step 4: Implement the hook**

Create `frontend/src/hooks/useScreenerJob.js`:

```js
import { useCallback, useEffect, useRef, useState } from "react";
import { createScreenerJob, fetchScreenerJob, cancelScreenerJob } from "../editions/localApi";

const SESSION_KEY = "sb_screener_job_id";
const POLL_MS = 1000;
const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

export function useScreenerJob() {
  const [job, setJob] = useState(null);
  const [isPolling, setIsPolling] = useState(false);
  const lastRequestRef = useRef(null);
  const intervalRef = useRef(null);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    setIsPolling(false);
  }, []);

  const pollOnce = useCallback(async (jobId) => {
    try {
      const data = await fetchScreenerJob(jobId, { offset: 0, limit: 50 });
      setJob(data);
      if (TERMINAL_STATUSES.has(data.status)) {
        stopPolling();
        sessionStorage.removeItem(SESSION_KEY);
      }
      return data;
    } catch {
      // A 404 means the job expired or is gone; stop polling and let the
      // caller decide to retry via createJob again.
      stopPolling();
      sessionStorage.removeItem(SESSION_KEY);
      return null;
    }
  }, [stopPolling]);

  const startPolling = useCallback((jobId) => {
    stopPolling();
    setIsPolling(true);
    intervalRef.current = setInterval(() => {
      if (document.hidden) return;
      pollOnce(jobId);
    }, POLL_MS);
  }, [pollOnce, stopPolling]);

  const createJob = useCallback(async (params) => {
    lastRequestRef.current = params;
    const data = await createScreenerJob(params);
    setJob(data);
    sessionStorage.setItem(SESSION_KEY, data.job_id);
    if (!TERMINAL_STATUSES.has(data.status)) {
      startPolling(data.job_id);
    }
    return data;
  }, [startPolling]);

  const retry = useCallback(async () => {
    if (!lastRequestRef.current) return null;
    return createJob(lastRequestRef.current);
  }, [createJob]);

  const cancel = useCallback(async () => {
    if (!job?.job_id) return;
    await cancelScreenerJob(job.job_id);
    stopPolling();
    sessionStorage.removeItem(SESSION_KEY);
    setJob((prev) => (prev ? { ...prev, status: "cancelled" } : prev));
  }, [job, stopPolling]);

  useEffect(() => {
    const storedId = sessionStorage.getItem(SESSION_KEY);
    if (storedId) {
      pollOnce(storedId).then((data) => {
        if (data && !TERMINAL_STATUSES.has(data.status)) {
          startPolling(storedId);
        }
      });
    }
    // Intentionally runs once on mount only, to reconnect to a job created
    // before a navigation away and back within the TTL.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onVisibility = () => {
      if (!document.hidden && job && !TERMINAL_STATUSES.has(job.status)) {
        pollOnce(job.job_id);
      }
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [job, pollOnce]);

  useEffect(() => stopPolling, [stopPolling]);

  return { job, isPolling, createJob, cancel, retry };
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npm test -- src/hooks/useScreenerJob.test.js`
Expected: all 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useScreenerJob.js frontend/src/hooks/useScreenerJob.test.js frontend/src/editions/localApi.js
git commit -m "feat: add useScreenerJob hook with visibility-aware polling and session reconnect"
```

---

## Task 6: Rewire `Screener.jsx` onto jobs + shared Pagination

**Files:**
- Modify: `frontend/src/pages/Screener.jsx`
- Test: `frontend/src/pages/Screener.test.jsx` (new — no test file exists for this page today)

**Interfaces:**
- Consumes: `useScreenerJob` (Task 5), `frontend/src/components/ui/Pagination.jsx` (Plan 4, contract: `offset, limit, total, onOffsetChange, ariaLabel`), `frontend/src/components/ui/AsyncSection.jsx` and `frontend/src/lib/apiError.js`'s `getApiErrorMessage` (Plan 2).

- [ ] **Step 1: Write the failing test**

Create `frontend/src/pages/Screener.test.jsx`:

```jsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import Screener from "./Screener";
import * as localApi from "../editions/localApi";

vi.mock("../components/StockDetail", () => ({
  useStockDetail: () => ({ openStock: vi.fn() }),
}));

describe("Screener page (job-based)", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("creates a job on Run Scan and shows queued/running progress, then results via Pagination", async () => {
    vi.spyOn(localApi, "createScreenerJob").mockResolvedValue({
      job_id: "jx", status: "queued", progress: { completed: 0, total: 0, percent: 0 }, result: null, error: null,
    });
    vi.spyOn(localApi, "fetchScreenerJob").mockResolvedValue({
      job_id: "jx", status: "completed",
      progress: { completed: 3, total: 3, percent: 100 },
      result: { items: [{ ticker: "AAA", name: "Aaa Inc", price: 10, market_cap: 1e9 }], total: 1, offset: 0, limit: 50 },
      error: null,
    });

    render(<Screener />);
    fireEvent.click(screen.getByRole("button", { name: /run scan/i }));

    await waitFor(() => expect(screen.getByText("AAA")).toBeInTheDocument());
    expect(localApi.createScreenerJob).toHaveBeenCalled();
  });

  it("shows a Cancel button while running and a Retry button after failure", async () => {
    vi.spyOn(localApi, "createScreenerJob").mockResolvedValue({
      job_id: "jy", status: "running", progress: { completed: 1, total: 10, percent: 10 }, result: null, error: null,
    });
    vi.spyOn(localApi, "cancelScreenerJob").mockResolvedValue({ job_id: "jy", status: "cancelled" });

    render(<Screener />);
    fireEvent.click(screen.getByRole("button", { name: /run scan/i }));

    const cancelButton = await screen.findByRole("button", { name: /cancel/i });
    fireEvent.click(cancelButton);
    await waitFor(() => expect(localApi.cancelScreenerJob).toHaveBeenCalledWith("jy"));
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm test -- src/pages/Screener.test.jsx`
Expected: FAIL — no "Run Scan" button exists yet (current page auto-fetches via `useQuery`/`fetchScreener` with no explicit trigger, and has no Cancel button).

- [ ] **Step 3: Rewire the page**

Replace the data-fetching and results portions of `frontend/src/pages/Screener.jsx`. Keep the existing filter-input JSX from lines 1-53 and the filter form markup (universe/sector/PE/etc. inputs), but:

1. Replace the `import { useQuery } from "@tanstack/react-query";` and `fetchScreener` import with:
   ```js
   import { useScreenerJob } from "../hooks/useScreenerJob";
   import Pagination from "../components/ui/Pagination";
   import AsyncSection from "../components/ui/AsyncSection";
   import { getApiErrorMessage } from "../lib/apiError";
   ```
2. Replace the `useQuery` call with:
   ```js
   const { job, isPolling, createJob, cancel, retry } = useScreenerJob();
   const [offset, setOffset] = useState(0);

   const runScan = useCallback(() => {
     setOffset(0);
     createJob(buildParams());
   }, [buildParams, createJob]);

   const isRunning = job && (job.status === "queued" || job.status === "running");
   const isFailed = job?.status === "failed";
   const results = job?.status === "completed" ? job.result.items : [];
   const total = job?.status === "completed" ? job.result.total : 0;
   ```
   Note the Shibui path (`source: "shibui"`) is unaffected by this plan and keeps calling the existing synchronous `fetchScreener` — branch on `isShibui` to call the old path directly (`useQuery` with `fetchScreener`) when `isShibui` is true, and the job hook otherwise. Keep both code paths clearly separated in the component rather than interleaving conditionals inside one query.
3. Replace the "Refresh" button with a "Run Scan" button calling `runScan`, and add a "Cancel" button (visible when `isRunning`) calling `cancel`, and a "Retry" button (visible when `isFailed`) calling `retry`.
4. Add a progress indicator while `isRunning`: `{job.progress.completed} / {job.progress.total} ({job.progress.percent}%)`.
5. Wrap the results table in `<AsyncSection isLoading={isRunning} error={isFailed ? new Error(job.error || "Scan failed") : null} onRetry={retry} isEmpty={!isRunning && !isFailed && results.length === 0} empty={<div className="text-center py-20 text-muted">No stocks match your criteria. Try expanding the filters.</div>}>` around the existing `<table>` markup (for the yfinance-job path only; the Shibui path keeps its existing loading/empty handling since it is unchanged).
6. Replace the "showing up to 50" static text with a `<Pagination offset={offset} limit={50} total={total} onOffsetChange={setOffset} ariaLabel="Screener results pages" />` below the table, and slice `results` by `offset`/`limit=50` for display (the job endpoint already returns a paginated `result.items` window per the `offset`/`limit` query params, so re-fetch the job's current page when `offset` changes via `fetchScreenerJob(job.job_id, { offset, limit: 50 })` — add a small effect in the page, or extend `useScreenerJob` with a `setPage(offset)` helper if that reads more cleanly; either is acceptable, but the offset change must trigger a real re-fetch of that page's items, not a client-side slice of only the first 50 returned.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm test -- src/pages/Screener.test.jsx`
Expected: both tests PASS.

- [ ] **Step 5: Run the full frontend suite for both editions**

Run:
```
cd frontend
npm test
npm run test:cloud
npm run build
npm run build:cloud
```
Expected: all PASS. Confirm the cloud build still excludes the screener route/code (local-only) — check the cloud build output does not reference `Screener` (e.g. `grep -r "Screener" dist-cloud/assets/*.js` should have no matches, or use whatever the existing convention is for verifying edition exclusion in this repo — check how Tax Report's exclusion is verified today, e.g. `frontend/src/App.routing.test.jsx` or `test:cloud`, and mirror that check for Screener if it isn't already covered).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Screener.jsx frontend/src/pages/Screener.test.jsx
git commit -m "feat: rewire Screener page onto background jobs with progress, cancel/retry, and pagination"
```

---

## Task 7: Phase verification and browser matrix

**Files:**
- Create: `docs/superpowers/plans/ux-05-screener-jobs-verification.md` (phase acceptance report, per spec §16.3's requirement that each phase's report lists commands/exit codes/warnings/deferrals)

**Interfaces:** none (documentation/verification only).

- [ ] **Step 1: Run full backend and frontend verification**

```powershell
cd backend
python -m pytest tests/ -v --ignore=tests/postgres

cd ..\frontend
npm test
npm run test:cloud
npm run build
npm run build:cloud
```

Record the exit code of each command in the verification report.

- [ ] **Step 2: Run the PostgreSQL suite if this plan touched owner/workspace scoping**

This plan's new endpoints read `ctx.user.id` from the existing `get_request_context` dependency and store jobs in memory only — no new SQL query, migration, or RLS-relevant table access is introduced. State this explicitly in the verification report so the PostgreSQL suite is understood as CI-only for this phase, per spec §16.2's last sentence. If, during implementation, a task ends up touching portfolio-scoped SQL (it should not), add `cd backend && python -m pytest tests/postgres/ -v` here instead.

- [ ] **Step 3: Manual browser-matrix walkthrough**

At each of 390×844, 768×1024, 1024×768, and 1440×900, using the worktree's own dev servers (not the main checkout's `:5173` tab, per spec §12.3/§16.3) with `VITE_API_PROXY_TARGET` pointed at this worktree's backend port:

- Creating a screener job returns within ~2 seconds (job created, status `queued`/`running` returned immediately — the scan itself continues in the background).
- Progress (`completed`/`total`/`percent`) updates while polling.
- Switching to another browser tab pauses polling (no new network requests in devtools); switching back resumes it.
- Cancel stops the job and the UI reflects `cancelled` without further progress updates.
- Retry re-submits the same last filter set as a new (or deduplicated, if within TTL) job.
- Navigating away from Screener and back within 30 minutes reconnects to the same job via `sessionStorage` instead of starting over.
- Results paginate via the shared `Pagination` component (25/50/100 page sizes, Previous/Next, numbered pages).
- The Shibui ("Whole Market") universe option still works exactly as before (synchronous, unaffected by this plan).
- Screener is reachable only in the local edition (confirm via the cloud build's excluded route/asset check from Task 6 Step 5, and/or by running the cloud build locally with `PORTFYL_EDITION=cloud` if the repo supports a local cloud-edition run).
- No unexpected console errors or failed network requests during the whole flow.

- [ ] **Step 4: Write the verification report**

Create `docs/superpowers/plans/ux-05-screener-jobs-verification.md` containing: the exact commands run, their exit codes, the browser-matrix checklist above with pass/fail per viewport, any unresolved warnings (e.g. pre-existing large-chunk build warning from spec §16.1, which is a known baseline condition, not a regression introduced here), and any intentional deferrals (e.g. "Screener's own money/percent formatting was left as local `fmtMoney`/`fmtPct` helpers rather than migrated to Plan 1's `frontend/src/lib/format.js`, since this plan's scope is jobs/pagination, not formatting centralization — flagged for a later cleanup pass, not a spec gap since §7.4 only mandates centralization for *new* formatting, and no new money/date formatting was introduced here").

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/ux-05-screener-jobs-verification.md
git commit -m "docs: record phase 5 (screener jobs) verification results"
```
