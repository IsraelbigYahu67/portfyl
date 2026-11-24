"""XIRR must say "cannot compute" (None) instead of a fake 0 %."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from routers.analytics import _lifetime_money_weighted
from routers.portfolio import _xirr
from tests.helpers import make_txn


class _FrozenDate(date):
    @classmethod
    def today(cls):
        return date(2024, 2, 1)


def test_xirr_normal_flows_return_a_number():
    rate = _xirr([(date(2023, 1, 1), -1000.0), (date(2024, 1, 1), 1100.0)])
    assert rate == pytest.approx(0.10, abs=0.005)


def test_xirr_all_positive_flows_is_none():
    assert _xirr([(date(2023, 1, 1), 100.0), (date(2024, 1, 1), 110.0)]) is None


def test_xirr_all_negative_flows_is_none():
    assert _xirr([(date(2023, 1, 1), -100.0), (date(2024, 1, 1), -110.0)]) is None


def test_xirr_single_flow_is_none():
    assert _xirr([(date(2023, 1, 1), -100.0)]) is None


def test_xirr_empty_is_none():
    assert _xirr([]) is None


def test_xirr_no_root_in_search_range_is_none():
    # Sign change exists, but the rate is far above the 1000 % search ceiling,
    # so neither Newton nor bisection can find a root.
    flows = [(date(2024, 1, 1), -1.0), (date(2024, 1, 2), 1e9)]
    assert _xirr(flows) is None


def test_lifetime_xirr_is_none_when_it_cannot_be_computed(pid):
    # One buy and a zero ending value: a single flow, so no IRR exists.
    buy = make_txn("AAPL", "buy", 1, 100.0, currency="USD",
                   date=date(2024, 1, 1), portfolio_id=pid)
    with patch("routers.analytics.date", _FrozenDate):
        lifetime = _lifetime_money_weighted([buy], pd.Series([0.0]))
    assert lifetime["xirr"] is None
    # Other fields still serialise normally.
    assert lifetime["simple_roi"] == pytest.approx(-100.0)


def test_lifetime_xirr_is_a_number_for_normal_flows(pid):
    buy = make_txn("AAPL", "buy", 1, 100.0, currency="USD",
                   date=date(2023, 2, 1), portfolio_id=pid)
    with patch("routers.analytics.date", _FrozenDate):
        lifetime = _lifetime_money_weighted([buy], pd.Series([110.0]))
    assert isinstance(lifetime["xirr"], float)
    assert lifetime["xirr"] > 0
