"""Tests for compute_dividend_growth (yfinance mocked, cache cleared per test)."""

from __future__ import annotations

import pandas as pd
import pytest

from cache import cache_clear
import dividend_growth
import shibui_client


@pytest.fixture(autouse=True)
def _clear_cache():
    cache_clear()
    yield
    cache_clear()


@pytest.fixture(autouse=True)
def _no_shibui_by_default(monkeypatch):
    """Every pre-existing test in this file exercises the yfinance fallback
    path and mocks `dividend_growth.yf.Ticker` -- without this, the ticker
    regex would still let `compute_dividend_growth` fire a real query at the
    live Shibui MCP server for tickers like "RISE"/"CUT"/etc. Individual
    tests override this to exercise the Shibui-preferred path."""
    def _unavailable(sql, prompt):
        raise shibui_client.ShibuiError("Shibui not mocked in this test")
    monkeypatch.setattr(dividend_growth.shibui_client, "query", _unavailable)


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


def test_streak_breaks_on_gap_year(monkeypatch):
    # 2020 suspended entirely -> the pre-2020 raises must NOT count toward the streak.
    s = _series([("2018-06-01", 1.0), ("2019-06-01", 1.1), ("2021-06-01", 1.3),
                 ("2022-06-01", 1.4), ("2023-06-01", 1.5)])
    _patch_ticker(monkeypatch, s, {})
    g = dividend_growth.compute_dividend_growth("GAP", _current_year=2026)
    # From 2023 back: 2023>2022 (+1), 2022>2021 (+1), 2021 vs 2019 is a gap -> stop. Streak = 2.
    assert g["streak_years"] == 2


def test_empty_history_still_reports_payout(monkeypatch):
    _patch_ticker(monkeypatch, pd.Series(dtype=float), {"payoutRatio": 0.30})
    g = dividend_growth.compute_dividend_growth("EMPTYPAY", _current_year=2026)
    assert g["annual"] == [] and g["payments"] == []
    assert g["payout_ratio_pct"] == 30.0


def test_malformed_series_degrades_to_empty(monkeypatch):
    # Non-empty series whose amount can't be parsed: _annual_dps skips it per-item,
    # then the payments comprehension's float(...) raises — the post-fetch guard must
    # catch it and return the well-formed empty shape (never propagate), payout kept.
    bad = pd.Series(["not-a-number"], index=pd.to_datetime(["2023-06-01"]))
    _patch_ticker(monkeypatch, bad, {"payoutRatio": 0.20})
    g = dividend_growth.compute_dividend_growth("BAD", _current_year=2026)
    assert g["annual"] == [] and g["payments"] == []
    assert g["payout_ratio_pct"] == 20.0
    assert g["streak_years"] == 0 and g["cagr_pct"] is None


def _shibui_quarterly_rows(pairs):
    return [{"date": d, "dividends_per_share": a} for d, a in pairs]


def test_prefers_shibui_quarterly_dps_over_yfinance(monkeypatch):
    rows = _shibui_quarterly_rows([
        ("2022-03-31", 0.25), ("2022-06-30", 0.25), ("2022-09-30", 0.25), ("2022-12-31", 0.25),
        ("2023-03-31", 0.30), ("2023-06-30", 0.30), ("2023-09-30", 0.30), ("2023-12-31", 0.30),
    ])
    monkeypatch.setattr(dividend_growth.shibui_client, "query", lambda sql, prompt: rows)

    # yfinance is still used for the payout ratio but its .dividends history
    # must never be read once Shibui has covered this ticker.
    class _Tk:
        def __init__(self, symbol):
            pass
        @property
        def dividends(self):
            raise AssertionError("yfinance dividend history should not be read when Shibui has coverage")
        @property
        def info(self):
            return {"payoutRatio": 0.18}
    monkeypatch.setattr(dividend_growth.yf, "Ticker", _Tk)

    g = dividend_growth.compute_dividend_growth("AAPL", _current_year=2026)
    assert g["source"] == "shibui"
    assert len(g["payments"]) == 8
    assert g["payments"][0] == {"ex_date": "2022-03-31", "amount": 0.25}
    annual = {a["year"]: a["dps"] for a in g["annual"]}
    assert annual[2022] == pytest.approx(1.0)
    assert annual[2023] == pytest.approx(1.2)
    assert g["yoy_pct"] == pytest.approx(20.0, abs=0.01)
    assert g["payout_ratio_pct"] == 18.0


def test_falls_back_to_yfinance_when_shibui_has_no_rows(monkeypatch):
    monkeypatch.setattr(dividend_growth.shibui_client, "query", lambda sql, prompt: [])
    s = _series([("2022-06-01", 1.0), ("2023-06-01", 1.1)])
    _patch_ticker(monkeypatch, s, {})
    g = dividend_growth.compute_dividend_growth("THIN", _current_year=2026)
    assert g["source"] == "yfinance"
    assert len(g["payments"]) == 2


def test_invalid_ticker_never_queries_shibui(monkeypatch):
    def boom(sql, prompt):
        raise AssertionError("should not query Shibui for a non-Shibui-shaped ticker")
    monkeypatch.setattr(dividend_growth.shibui_client, "query", boom)
    s = _series([("2023-06-01", 1.0)])
    _patch_ticker(monkeypatch, s, {})
    g = dividend_growth.compute_dividend_growth("lowercase", _current_year=2026)
    assert g["source"] == "yfinance"


def test_malformed_shibui_rows_fall_back_to_yfinance(monkeypatch):
    monkeypatch.setattr(dividend_growth.shibui_client, "query",
                         lambda sql, prompt: [{"date": "2023-03-31"}])  # missing dividends_per_share
    s = _series([("2023-06-01", 1.0)])
    _patch_ticker(monkeypatch, s, {})
    g = dividend_growth.compute_dividend_growth("MALFORMED", _current_year=2026)
    assert g["source"] == "yfinance"
    assert len(g["payments"]) == 1
