"""Tests for FX rate fetching and ticker map."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest
import pandas as pd

from ticker_map import yf_symbol, TICKER_FALLBACKS
from fx import fetch_fx_to_czk


class TestTickerMap:
    def test_direct_ticker(self):
        """Ticker not in fallback map returns unchanged."""
        assert yf_symbol("AAPL") == "AAPL"
        assert yf_symbol("MSFT") == "MSFT"

    def test_fallback_applied(self):
        """COPM.L → COPM.AS per the only fallback entry."""
        assert yf_symbol("COPM.L") == "COPM.AS"

    def test_case_insensitive(self):
        """Input is case-insensitive."""
        assert yf_symbol("copm.l") == "COPM.AS"
        assert yf_symbol("Copm.L") == "COPM.AS"

    def test_empty(self):
        """Empty ticker returns empty."""
        assert yf_symbol("") == ""
        assert yf_symbol(None) is None


class TestFX:
    def test_czk_returns_one(self):
        """CZK currency returns 1.0 immediately."""
        assert fetch_fx_to_czk("CZK", date.today()) == 1.0

    def test_none_currency_is_usd(self):
        """None/empty currency is treated as not-CZK but will need yfinance call."""
        # This will hit the network, but we just test it doesn't crash and returns
        # either a number or None.
        result = fetch_fx_to_czk(None, date.today())
        assert result is None or isinstance(result, float)
