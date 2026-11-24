"""Portfolio and benchmark returns must be measured in the same currency.

A benchmark quoted in EUR compared with a portfolio expressed in USD (or CZK)
used to mix currency drift into the active return. These tests use synthetic
series: an EUR asset and a flat EUR benchmark while EUR moves against USD/CZK.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from routers.analytics import (
    BASIS_NATIVE,
    _benchmark_compare_metrics,
    _benchmark_daily_returns,
    _build_value_cashflow_series,
    _modified_dietz_daily_returns,
    _usd_series_to_display,
)
from tests.helpers import make_txn

IDX = pd.bdate_range("2024-01-01", periods=60)
EURUSD = pd.Series(1.05 + 0.002 * np.arange(len(IDX)) + 0.01 * np.sin(np.arange(len(IDX))), index=IDX)
CZKUSD = pd.Series(0.043 - 0.0001 * np.arange(len(IDX)), index=IDX)
CURRENCY = {"EUA": "EUR", "^STOXX50E": "EUR", "SPY": "USD"}


class _Market:
    """Yahoo stand-in. Everything priced in EUR is flat at 100; FX moves."""

    def __init__(self, fx_available=("EURUSD=X", "CZKUSD=X")):
        self.fx_available = set(fx_available)

    def download(self, tickers, **_kw):
        fx = {"EURUSD=X": EURUSD, "CZKUSD=X": CZKUSD}
        if isinstance(tickers, list):
            return pd.DataFrame({"Close": 100.0, "Stock Splits": 0.0}, index=IDX).rename_axis("Date")
        if tickers in fx:
            if tickers not in self.fx_available:
                return pd.DataFrame()
            return pd.DataFrame({"Close": fx[tickers]})
        return pd.DataFrame({"Close": 100.0}, index=IDX)

    def infos(self, tickers):
        return {t: {"currency": CURRENCY[t]} for t in tickers if t in CURRENCY}


def _portfolio_and_benchmark(display, market=None):
    market = market or _Market()
    txns = [make_txn("EUA", "buy", 10, 100, currency="EUR", date=IDX[0].date())]
    bench = SimpleNamespace(kind="ticker", ticker="^STOXX50E", workspace_id=None, id=1)
    with patch("routers.analytics.market_data.download", side_effect=market.download), \
         patch("routers.analytics.market_data.get_infos", side_effect=market.infos):
        V, C, idx = _build_value_cashflow_series(txns, date(2024, 1, 1))
        V, C = _usd_series_to_display(V, C, date(2024, 1, 1), display)
        port = _modified_dietz_daily_returns(V, C, date(2024, 1, 1))
        bench_converted = _benchmark_daily_returns(None, bench, date(2024, 1, 1), idx, display)
        bench_native = _benchmark_daily_returns(None, bench, date(2024, 1, 1), idx)
    return port, bench_converted, bench_native


@pytest.mark.parametrize("display", ["USD", "CZK"])
def test_flat_foreign_benchmark_has_zero_active_return_after_conversion(display):
    port, bench, native = _portfolio_and_benchmark(display)

    # Sanity: the EUR asset really moves in the display currency ...
    assert abs((1 + port).prod() - 1) > 0.05
    # ... a flat EUR benchmark in its own currency does not (the old mismatch) ...
    assert native.dropna().abs().max() == pytest.approx(0.0)
    # (so the old, unconverted comparison showed a large fake active return) ...
    old = pd.DataFrame({"p": port, "b": native}).dropna()
    assert abs((1 + old["p"]).prod() - (1 + old["b"]).prod()) > 0.05
    # ... and once converted it tracks the portfolio.
    aligned = pd.DataFrame({"p": port, "b": bench}).dropna()
    active_cum = (1 + aligned["p"]).prod() - (1 + aligned["b"]).prod()
    assert active_cum == pytest.approx(0.0, abs=1e-9)
    assert bench.attrs["currency_basis"] == display
    assert native.attrs["currency_basis"] == BASIS_NATIVE
    metrics = _benchmark_compare_metrics(aligned["p"], aligned["b"])
    assert metrics["tracking_error"] == pytest.approx(0.0, abs=1e-6)


def test_missing_fx_history_falls_back_to_native_and_says_so():
    market = _Market(fx_available=())
    bench = SimpleNamespace(kind="ticker", ticker="^STOXX50E", workspace_id=None, id=1)
    with patch("routers.analytics.market_data.download", side_effect=market.download), \
         patch("routers.analytics.market_data.get_infos", side_effect=market.infos):
        out = _benchmark_daily_returns(None, bench, date(2024, 1, 1), IDX, "USD")
    assert out.attrs["currency_basis"] == BASIS_NATIVE
    assert out.dropna().abs().max() == pytest.approx(0.0)


def test_usd_benchmark_in_usd_is_unchanged():
    market = _Market()
    bench = SimpleNamespace(kind="ticker", ticker="SPY", workspace_id=None, id=1)
    with patch("routers.analytics.market_data.download", side_effect=market.download), \
         patch("routers.analytics.market_data.get_infos", side_effect=market.infos):
        out = _benchmark_daily_returns(None, bench, date(2024, 1, 1), IDX, "USD")
        native = _benchmark_daily_returns(None, bench, date(2024, 1, 1), IDX)
    pd.testing.assert_series_equal(out, native)
    assert out.attrs["currency_basis"] == "USD"
