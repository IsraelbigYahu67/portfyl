"""Tests for screener jobs and their shared filtering semantics."""

import time

from routers.market import _in_range
from services import screener_jobs as sj


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
    assert _in_range(7, 5, 10) is True


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
