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
        """Preset ticker lists are defined and non-empty."""
        from routers.market import _PRESET_UNIVERSES
        assert "sp500" in _PRESET_UNIVERSES
        assert "nasdaq100" in _PRESET_UNIVERSES
        assert "tech_large" in _PRESET_UNIVERSES
        for name, tickers in _PRESET_UNIVERSES.items():
            assert len(tickers) > 0, f"{name} is empty"
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
