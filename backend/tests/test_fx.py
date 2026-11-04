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

    def test_pence_history_is_the_pound_series_divided_by_100(self, monkeypatch):
        """GBX (pence) trades must snapshot GBP→CZK / 100. Yahoo's GBXCZK=X
        is the per-pound rate, which made pence cost bases 100x too large."""
        import fx

        monkeypatch.setattr(fx, "_DAILY_CACHE", {})
        requested: list[str] = []

        def download(pair, **_):
            requested.append(pair)
            idx = pd.to_datetime(["2025-01-09", "2025-01-10"])
            return pd.DataFrame({"Close": [29.0, 30.0]}, index=idx)

        monkeypatch.setattr(fx.market_data, "download", download)

        assert fx.fetch_fx_to_czk("GBX", date(2025, 1, 10)) == pytest.approx(0.30)
        assert fx.bulk_fetch_fx([("GBX", date(2025, 1, 9))]) == {
            ("GBX", date(2025, 1, 9)): pytest.approx(0.29)}
        # The pound series itself (same cached download) stays per pound.
        assert fx.fetch_fx_to_czk("GBP", date(2025, 1, 10)) == pytest.approx(30.0)
        assert set(requested) == {"GBPCZK=X"}

    def test_normalize_currency_keeps_pence_distinct_from_pounds(self):
        """'GBp' (pence) must never upper-case into 'GBP' (pounds): that is a
        silent 100x error for every pence-priced LSE trade."""
        from fx import normalize_currency, subunit

        assert normalize_currency("GBp") == "GBX"
        assert normalize_currency(" gbx ") == "GBX"
        assert normalize_currency("GBP") == "GBP"
        assert normalize_currency(" usd ") == "USD"
        assert normalize_currency(None) == "USD"
        assert normalize_currency("", default="CZK") == "CZK"
        assert subunit("GBp") == ("GBP", 100.0)
        assert subunit("GBP") == ("GBP", 1.0)

    def test_none_currency_is_usd(self):
        """None/empty currency is treated as not-CZK but will need yfinance call."""
        # This will hit the network, but we just test it doesn't crash and returns
        # either a number or None.
        result = fetch_fx_to_czk(None, date.today())
        assert result is None or isinstance(result, float)
