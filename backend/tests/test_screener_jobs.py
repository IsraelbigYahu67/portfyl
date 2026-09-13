"""Tests for screener jobs and their shared filtering semantics."""

from routers.market import _in_range


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
