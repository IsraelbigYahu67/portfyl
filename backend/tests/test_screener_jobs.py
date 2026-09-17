"""Tests for screener jobs and their shared filtering semantics."""

import time
import threading
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from routers.market import (
    _in_range,
    create_screener_job,
    get_screener_job,
    cancel_screener_job,
    ScreenerJobRequest,
)
from services import screener_jobs as sj
from tenancy import RequestContext


def _reset_registry():
    with sj._REGISTRY_LOCK:
        sj._JOBS.clear()


def test_in_range_no_bounds_and_no_value_is_true():
    """An unfiltered missing metric must not exclude a provider row."""
    assert _in_range(None, None, None) is True


def test_in_range_missing_value_with_a_bound_is_false():
    """A missing metric cannot satisfy an explicit lower or upper bound."""
    assert _in_range(None, 10, None) is False
    assert _in_range(None, None, 10) is False
    assert _in_range(None, 5, 10) is False


def test_in_range_present_value_still_respects_bounds():
    """The missing-value fix must preserve inclusive range filtering."""
    assert _in_range(5, 10, None) is False
    assert _in_range(15, 10, None) is True
    assert _in_range(15, None, 10) is False
    assert _in_range(5, None, 10) is True


def test_fingerprint_is_stable_for_same_user_and_request():
    """Equivalent request mappings must deduplicate for one user."""
    request = {"universe": "sp500", "sort_by": "market_cap", "sort_desc": True}
    assert sj._fingerprint("user-1", request) == sj._fingerprint("user-1", dict(request))


def test_fingerprint_differs_by_user_or_request():
    """A fingerprint must not reuse jobs across users or scan inputs."""
    request = {"universe": "sp500"}
    assert sj._fingerprint("user-1", request) != sj._fingerprint("user-2", request)
    assert sj._fingerprint("user-1", request) != sj._fingerprint(
        "user-1", {"universe": "nasdaq100"}
    )


def test_prune_removes_expired_jobs():
    """Terminal jobs cease to be addressable once their TTL elapses."""
    _reset_registry()
    job = sj.ScreenerJob(
        job_id="j1",
        user_id="user-1",
        fingerprint="fp1",
        status="completed",
        request={},
        created_at=sj._now() - 3600,
        expires_at=sj._now() - 1,
        scan_total=1,
        completed_count=1,
        result_items=[],
        unavailable_count=0,
        error=None,
        cancel_requested=False,
    )
    with sj._REGISTRY_LOCK:
        sj._JOBS["j1"] = job

    sj._prune_expired_and_over_capacity()

    with sj._REGISTRY_LOCK:
        assert "j1" not in sj._JOBS


def test_prune_enforces_max_retained_jobs():
    """Capacity cleanup evicts oldest retained jobs before newer ones."""
    _reset_registry()
    now = time.time()
    with sj._REGISTRY_LOCK:
        for index in range(25):
            job_id = f"j{index}"
            sj._JOBS[job_id] = sj.ScreenerJob(
                job_id=job_id,
                user_id="user-1",
                fingerprint=f"fp{index}",
                status="completed",
                request={},
                created_at=now - index,
                expires_at=now + 1800,
                scan_total=1,
                completed_count=1,
                result_items=[],
                unavailable_count=0,
                error=None,
                cancel_requested=False,
            )

    sj._prune_expired_and_over_capacity()

    with sj._REGISTRY_LOCK:
        assert len(sj._JOBS) == sj.MAX_RETAINED_JOBS
        assert "j0" in sj._JOBS
        assert "j24" not in sj._JOBS


def test_job_response_serializes_timestamps_as_utc_iso8601():
    """The API contract must not expose internal unix timestamps."""
    job = sj.ScreenerJob(
        job_id="j1",
        user_id="user-1",
        fingerprint="fp1",
        status="completed",
        request={},
        created_at=0,
        expires_at=1800,
        scan_total=1,
        completed_count=1,
        result_items=[],
        unavailable_count=0,
        error=None,
        cancel_requested=False,
    )

    response = job.to_response(offset=0, limit=50)

    assert response["created_at"] == "1970-01-01T00:00:00Z"
    assert response["expires_at"] == "1970-01-01T00:30:00Z"


def _fake_row(symbol, price=100.0, pe=15.0):
    return {
        "ticker": symbol,
        "name": symbol,
        "price": price,
        "market_cap": 1e9,
        "pe": pe,
        "sector": "Technology",
    }


def _wait_for_status(job_id, user_id, statuses, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = sj.get_job(user_id, job_id)
        if job and job.status in statuses:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not reach {statuses} in time")


def test_submit_job_deduplicates_identical_active_request_for_same_user():
    """Repeated clicks must not enqueue duplicate scans for one user/request."""
    _reset_registry()
    gate = threading.Event()

    def slow_row(symbol):
        gate.wait(timeout=2)
        return _fake_row(symbol)

    request = {"universe": "tech_large", "sort_by": "market_cap", "sort_desc": True}
    with patch("services.screener_jobs._ticker_row", side_effect=slow_row):
        first = sj.submit_job("user-1", request)
        second = sj.submit_job("user-1", dict(request))
        assert first.job_id == second.job_id
        gate.set()
        _wait_for_status(first.job_id, "user-1", {"completed", "failed", "cancelled"})


def test_submit_job_does_not_deduplicate_across_users():
    """The same filters from another identity must create a separate job."""
    _reset_registry()
    request = {"universe": "tech_large", "sort_by": "market_cap", "sort_desc": True}
    with patch("services.screener_jobs._ticker_row", side_effect=lambda symbol: _fake_row(symbol)):
        first = sj.submit_job("user-1", request)
        second = sj.submit_job("user-2", dict(request))
        assert first.job_id != second.job_id
        _wait_for_status(first.job_id, "user-1", {"completed", "failed", "cancelled"})
        _wait_for_status(second.job_id, "user-2", {"completed", "failed", "cancelled"})


def test_immediate_retry_does_not_reuse_a_cancelling_worker():
    _reset_registry()
    gate = threading.Event()
    started = threading.Event()

    def slow_row(symbol):
        started.set()
        gate.wait(timeout=3)
        return _fake_row(symbol)

    request = {"tickers": "AAA,BBB", "sort_by": "market_cap"}
    with patch("services.screener_jobs._ticker_row", side_effect=slow_row):
        first = sj.submit_job("user-1", request)
        try:
            assert started.wait(timeout=2)
            assert sj.cancel_job("user-1", first.job_id)
            second = sj.submit_job("user-1", request)
            assert second.job_id != first.job_id
        finally:
            gate.set()
            _wait_for_status(first.job_id, "user-1", {"cancelled"})
        done = _wait_for_status(second.job_id, "user-1", {"completed"})
        assert len(done.result_items) == 2


def test_job_completes_and_progress_reaches_total():
    """Every settled ticker future increments progress exactly once."""
    _reset_registry()
    tickers = ["AAA", "BBB", "CCC"]
    with (
        patch("services.screener_jobs._universe_tickers", return_value=tickers),
        patch("services.screener_jobs._ticker_row", side_effect=lambda symbol: _fake_row(symbol)),
    ):
        job = sj.submit_job(
            "user-1",
            {"universe": "tech_large", "sort_by": "market_cap", "sort_desc": True},
        )
        done = _wait_for_status(job.job_id, "user-1", {"completed"})

    assert done.completed_count == done.scan_total == 3
    assert len(done.result_items) == 3


def test_job_cancellation_stops_scheduling_further_batches():
    """Cancellation may finish current calls but must not launch another batch."""
    _reset_registry()
    tickers = [f"T{index}" for index in range(40)]
    started = threading.Event()
    release = threading.Event()

    def slow_row(symbol):
        started.set()
        release.wait(timeout=2)
        return _fake_row(symbol)

    with (
        patch("services.screener_jobs._universe_tickers", return_value=tickers),
        patch("services.screener_jobs._ticker_row", side_effect=slow_row),
    ):
        job = sj.submit_job(
            "user-1",
            {"universe": "tech_large", "sort_by": "market_cap", "sort_desc": True},
        )
        assert started.wait(timeout=2)
        assert sj.cancel_job("user-1", job.job_id) is True
        release.set()
        done = _wait_for_status(job.job_id, "user-1", {"cancelled"})

    assert done.completed_count < len(tickers)


def test_get_job_hides_wrong_user_and_missing_ids():
    """Job lookup must not disclose another user's in-memory job."""
    _reset_registry()
    with patch("services.screener_jobs._ticker_row", side_effect=lambda symbol: _fake_row(symbol)):
        job = sj.submit_job("user-1", {"universe": "tech_large"})
        _wait_for_status(job.job_id, "user-1", {"completed", "failed", "cancelled"})

    assert sj.get_job("user-2", job.job_id) is None
    assert sj.get_job("user-1", "not-a-real-id") is None


def test_cancel_job_hides_wrong_user_and_missing_ids():
    """Cancellation must not reveal or mutate jobs outside the caller identity."""
    _reset_registry()
    gate = threading.Event()

    def slow_row(symbol):
        gate.wait(timeout=2)
        return _fake_row(symbol)

    with patch("services.screener_jobs._ticker_row", side_effect=slow_row):
        job = sj.submit_job("user-1", {"universe": "tech_large"})
        assert sj.cancel_job("user-2", job.job_id) is False
        assert sj.cancel_job("user-1", "not-a-real-id") is False
        gate.set()
        _wait_for_status(job.job_id, "user-1", {"completed", "failed", "cancelled"})


class _FakeUser:
    def __init__(self, id):
        self.id = id


def _ctx(user_id: str) -> RequestContext:
    # RequestContext only needs `.user.id` for this endpoint; the other fields
    # are left None, matching how other fast-suite tests exercise router
    # functions directly without a full authenticated HTTP request.
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
