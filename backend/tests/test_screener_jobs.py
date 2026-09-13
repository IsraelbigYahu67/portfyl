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
