"""Tests for compute_dividend_growth (yfinance mocked, cache cleared per test)."""

from __future__ import annotations

import pandas as pd
import pytest

from cache import cache_clear
import dividend_growth


@pytest.fixture(autouse=True)
def _clear_cache():
    cache_clear()
    yield
    cache_clear()


def _patch_ticker(monkeypatch, series: pd.Series, info: dict | None = None):
    class _Tk:
        def __init__(self, symbol):
            self.symbol = symbol
        @property
        def dividends(self):
            return series
        @property
        def info(self):
            return info or {}
    monkeypatch.setattr(dividend_growth.yf, "Ticker", _Tk)


def _series(pairs):
    idx = pd.to_datetime([d for d, _ in pairs])
    return pd.Series([a for _, a in pairs], index=idx)


def test_rising_series_streak_cagr_yoy(monkeypatch):
    # 2019..2023, strictly rising annual DPS -> 4 consecutive increases.
    s = _series([("2019-06-01", 1.0), ("2020-06-01", 1.1), ("2021-06-01", 1.2),
                 ("2022-06-01", 1.3), ("2023-06-01", 1.4)])
    _patch_ticker(monkeypatch, s, {"payoutRatio": 0.42})
    # current year is well past 2023 in this project's timeline
    g = dividend_growth.compute_dividend_growth("RISE", _current_year=2026)
    assert g["streak_years"] == 4
    assert g["cagr_years_used"] == 4
    assert g["cagr_pct"] == pytest.approx(8.78, abs=0.05)   # (1.4/1.0)**(1/4)-1
    assert g["yoy_pct"] == pytest.approx(7.69, abs=0.05)    # 1.4/1.3-1
    assert g["payout_ratio_pct"] == 42.0
    assert [a["year"] for a in g["annual"]] == [2019, 2020, 2021, 2022, 2023]
    assert len(g["payments"]) == 5


def test_cut_breaks_streak(monkeypatch):
    s = _series([("2019-06-01", 1.0), ("2020-06-01", 1.1), ("2021-06-01", 1.2),
                 ("2022-06-01", 1.1), ("2023-06-01", 1.3)])
    _patch_ticker(monkeypatch, s, {})
    g = dividend_growth.compute_dividend_growth("CUT", _current_year=2026)
    # From 2023 back: 2023>2022 (+1), 2022<2021 -> stop.
    assert g["streak_years"] == 1


def test_short_history_reports_years_used(monkeypatch):
    s = _series([("2022-06-01", 1.0), ("2023-06-01", 1.1)])
    _patch_ticker(monkeypatch, s, {})
    g = dividend_growth.compute_dividend_growth("SHORT", _current_year=2026)
    assert g["cagr_years_used"] == 1
    assert g["cagr_pct"] == pytest.approx(10.0, abs=0.01)


def test_quarterly_payments_aggregate_by_year(monkeypatch):
    s = _series([("2022-03-01", 0.25), ("2022-06-01", 0.25), ("2022-09-01", 0.25),
                 ("2022-12-01", 0.25), ("2023-03-01", 0.30), ("2023-06-01", 0.30),
                 ("2023-09-01", 0.30), ("2023-12-01", 0.30)])
    _patch_ticker(monkeypatch, s, {})
    g = dividend_growth.compute_dividend_growth("QTR", _current_year=2026)
    annual = {a["year"]: a["dps"] for a in g["annual"]}
    assert annual[2022] == pytest.approx(1.0)
    assert annual[2023] == pytest.approx(1.2)
    assert g["yoy_pct"] == pytest.approx(20.0, abs=0.01)


def test_empty_history_is_wellformed(monkeypatch):
    _patch_ticker(monkeypatch, pd.Series(dtype=float), {})
    g = dividend_growth.compute_dividend_growth("NONE", _current_year=2026)
    assert g["annual"] == []
    assert g["payments"] == []
    assert g["streak_years"] == 0
    assert g["cagr_pct"] is None
    assert g["yoy_pct"] is None


def test_yfinance_exception_is_swallowed(monkeypatch):
    class _Boom:
        def __init__(self, symbol): raise RuntimeError("delisted")
    monkeypatch.setattr(dividend_growth.yf, "Ticker", _Boom)
    g = dividend_growth.compute_dividend_growth("BOOM", _current_year=2026)
    assert g["annual"] == [] and g["streak_years"] == 0
