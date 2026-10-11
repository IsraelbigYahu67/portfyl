"""Shared, short-lived caching of Yahoo downloads and per-ticker lookups.

One dashboard load fired ~11 requests that each fetched their own copy of the
same Yahoo data: three identical 2-day closes downloads for all holdings
(summary, heatmap, movers), the same price history twice (performance, risk
metrics), and per-ticker dividend history / calendar / earnings dates one
ticker after another, never cached. Measured with 22 holdings that cost
4-10s per endpoint on every load.
"""

from __future__ import annotations

import threading
import time

import pandas as pd
import pytest
import yfinance as yf

import market_data


def _frame():
    return pd.DataFrame({"Close": [1.0, 2.0]})


def test_identical_downloads_share_one_yahoo_call(monkeypatch):
    calls = []
    monkeypatch.setattr(yf, "download", lambda *a, **k: calls.append((a, k)) or _frame())

    first = market_data.download(["AAPL", "MSFT"], period="2d", auto_adjust=True, progress=False)
    second = market_data.download(["AAPL", "MSFT"], period="2d", auto_adjust=True, progress=False)

    assert len(calls) == 1
    assert first.equals(second)


def test_cached_download_is_a_private_copy(monkeypatch):
    monkeypatch.setattr(yf, "download", lambda *a, **k: _frame())

    first = market_data.download("AAPL", period="2d")
    first.loc[0, "Close"] = 999.0

    assert market_data.download("AAPL", period="2d").loc[0, "Close"] == 1.0


def test_different_arguments_are_different_downloads(monkeypatch):
    calls = []
    monkeypatch.setattr(yf, "download", lambda *a, **k: calls.append((a, k)) or _frame())

    market_data.download(["AAPL"], period="2d", auto_adjust=True)
    market_data.download(["AAPL"], period="5d", auto_adjust=True)
    market_data.download(["AAPL"], period="2d", auto_adjust=False)
    market_data.download(["AAPL", "MSFT"], period="2d", auto_adjust=True)

    assert len(calls) == 4


def test_concurrent_identical_downloads_wait_for_one_call(monkeypatch):
    calls = []
    release = threading.Event()

    def slow_download(*a, **k):
        calls.append(1)
        release.wait(5)
        return _frame()

    monkeypatch.setattr(yf, "download", slow_download)
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(market_data.download("AAPL", period="2d")))
        for _ in range(4)
    ]
    for t in threads:
        t.start()
    time.sleep(0.2)
    release.set()
    for t in threads:
        t.join(5)

    assert len(calls) == 1
    assert len(results) == 4


def test_a_failed_download_is_not_cached(monkeypatch):
    attempts = []

    def flaky(*a, **k):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("Yahoo hiccup")
        return _frame()

    monkeypatch.setattr(yf, "download", flaky)

    with pytest.raises(RuntimeError):
        market_data.download("AAPL", period="2d")
    assert not market_data.download("AAPL", period="2d").empty
    assert len(attempts) == 2


def test_download_expires_after_its_ttl(monkeypatch):
    calls = []
    monkeypatch.setattr(yf, "download", lambda *a, **k: calls.append(1) or _frame())
    now = [1000.0]
    monkeypatch.setattr(market_data.time, "monotonic", lambda: now[0])

    market_data.download("AAPL", period="2d")
    now[0] += market_data.DOWNLOAD_TTL + 1
    market_data.download("AAPL", period="2d")

    assert len(calls) == 2


class _Ticker:
    created = []
    lock = threading.Lock()

    def __init__(self, symbol):
        self.ticker = symbol
        with self.lock:
            self.created.append(symbol)

    @property
    def dividends(self):
        time.sleep(0.2)
        return pd.Series([0.5], index=pd.to_datetime(["2026-01-15"]))


def test_ticker_attrs_fetch_in_parallel_and_cache(monkeypatch):
    _Ticker.created = []
    monkeypatch.setattr(yf, "Ticker", _Ticker)
    symbols = [f"T{i}" for i in range(8)]

    t0 = time.monotonic()
    first = market_data.ticker_attrs(symbols, "dividends")
    elapsed = time.monotonic() - t0
    second = market_data.ticker_attrs(symbols, "dividends")

    assert elapsed < 0.2 * len(symbols) / 2  # not one after another
    assert set(first) == set(symbols)
    assert all(float(series.iloc[0]) == 0.5 for series in first.values())
    assert sorted(_Ticker.created) == sorted(symbols)  # second call: no Yahoo
    assert second.keys() == first.keys()


def test_ticker_attrs_turn_a_failure_into_none(monkeypatch):
    class Broken:
        def __init__(self, symbol):
            self.ticker = symbol

        @property
        def calendar(self):
            raise RuntimeError("no data")

    monkeypatch.setattr(yf, "Ticker", Broken)

    assert market_data.ticker_attrs(["X"], "calendar") == {"X": None}
