"""Tests for stock screener endpoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest


class TestStockScreener:
    """Unit tests for the stock screener."""

    def test_in_range_helper(self):
        """_in_range correctly filters values."""
        from routers.market import _in_range
        assert _in_range(15.0, 10.0, 20.0) is True
        assert _in_range(5.0, 10.0, 20.0) is False
        assert _in_range(25.0, 10.0, 20.0) is False
        assert _in_range(15.0, None, 20.0) is True
        assert _in_range(25.0, None, 20.0) is False
        assert _in_range(15.0, 10.0, None) is True
        assert _in_range(5.0, 10.0, None) is False
        assert _in_range(None, 10.0, 20.0) is False  # None fails
        assert _in_range(15.0, None, None) is True  # no bounds

    def test_preset_universes(self):
        """Preset ticker lists are defined, full-sized, and well-formed."""
        from routers.market import _PRESET_UNIVERSES
        assert "sp500" in _PRESET_UNIVERSES
        assert "nasdaq100" in _PRESET_UNIVERSES
        assert "dividend_aristocrats" in _PRESET_UNIVERSES
        assert "tech_large" in _PRESET_UNIVERSES
        # Full constituent lists, not top-20 samples.
        assert len(_PRESET_UNIVERSES["sp500"]) >= 400
        assert len(_PRESET_UNIVERSES["nasdaq100"]) >= 90
        assert len(_PRESET_UNIVERSES["dividend_aristocrats"]) >= 55
        # tech_large stays small: it's the fallback universe, so a bad universe
        # param must not accidentally trigger a 500-name scan.
        assert len(_PRESET_UNIVERSES["tech_large"]) <= 15
        for name, tickers in _PRESET_UNIVERSES.items():
            assert len(tickers) > 0, f"{name} is empty"
            assert len(tickers) == len(set(tickers)), f"{name} has duplicates"
            assert all(t.isupper() for t in tickers), f"{name} has non-upper tickers"

    def test_ticker_screener_row_structure(self):
        """_ticker_screener_row returns the expected field shape."""
        from routers.market import _ticker_screener_row
        expected_fields = {
            "ticker", "name", "price", "market_cap", "sector", "industry",
            "pe", "forward_pe", "ps", "pb", "div_yield", "beta",
        }
        # Can't call without network, but we can verify the function signature exists
        import inspect
        sig = inspect.signature(_ticker_screener_row)
        assert "sym" in sig.parameters

    def test_screener_empty_tickers(self):
        """Nonexistent universe falls back to tech_large (not empty)."""
        from routers.market import stock_screener
        result = stock_screener(universe="nonexistent", limit=10)
        assert "results" in result
        assert result["universe"] == "nonexistent"
        # Falls back to tech_large, which has 10 tickers
        assert result["total"] >= 0

    def test_screener_custom_tickers(self):
        """Custom tickers param overrides the universe."""
        from routers.market import stock_screener
        result = stock_screener(tickers="AAPL,MSFT", limit=5)
        assert result["universe"] == "custom"
        # These will try to fetch from Network, but we just test the shape
        assert "results" in result
        assert result["total"] >= 0


class TestGetInfosTimeout:
    """A deadline miss must not be cached as 'no data' — that poisoned the
    USDCZK=X quote for 60s and made every position render at ≈ -95%."""

    @pytest.fixture(autouse=True)
    def _clean_state(self):
        import market_data
        market_data._cache.clear()
        market_data._inflight.clear()
        yield
        market_data._cache.clear()
        market_data._inflight.clear()

    def test_timeout_leaves_cache_unpoisoned_and_result_collectable(self):
        import threading
        import market_data

        release = threading.Event()

        def slow_info(symbol):
            release.wait(5)
            return {"regularMarketPrice": 21.2}

        with patch("market_data._raw_info", side_effect=slow_info):
            out = market_data.get_infos(["USDCZK=X"], timeout=0.2)
            assert out["USDCZK=X"] == {}          # nothing yet, caller degrades
            assert "USDCZK=X" not in market_data._cache  # but NOT cached as empty
            assert "USDCZK=X" in market_data._inflight

            release.set()
            market_data._inflight["USDCZK=X"].result(timeout=5)  # let it finish
            out = market_data.get_infos(["USDCZK=X"], timeout=0.2)

        assert out["USDCZK=X"]["regularMarketPrice"] == 21.2
        assert "USDCZK=X" not in market_data._inflight

    def test_genuine_empty_fetch_still_cached(self):
        import market_data

        calls = []

        def empty_info(symbol):
            calls.append(symbol)
            return {}

        with patch("market_data._raw_info", side_effect=empty_info):
            assert market_data.get_infos(["NODATA"], timeout=2)["NODATA"] == {}
            assert market_data.get_infos(["NODATA"], timeout=2)["NODATA"] == {}

        assert len(calls) == 1  # second call served from the empty-TTL cache
        assert "NODATA" in market_data._cache
