"""Tests for the screener job service (backend/services/screener_jobs.py)
and the _in_range missing-value fix it depends on."""

from routers.market import _in_range
from services import screener_jobs as sj


def _reset_registry():
    with sj._REGISTRY_LOCK:
        sj._JOBS.clear()



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
