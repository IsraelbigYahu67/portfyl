"""Tests for the screener job service (backend/services/screener_jobs.py)
and the _in_range missing-value fix it depends on."""

import threading
import time
from unittest.mock import patch

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


def _fake_row(sym, price=100.0, pe=15.0):
    return {"ticker": sym, "name": sym, "price": price, "market_cap": 1e9, "pe": pe, "sector": "Technology"}


def _wait_for_status(job_id, user_id, statuses, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = sj.get_job(user_id, job_id)
        if job is not None and job.status in statuses:
            return job
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not reach {statuses} in time")


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
        # processed every one of the 40 tickers (batch size is 12).
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
