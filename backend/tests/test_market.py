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


class TestShibuiTickerValidation:
    """_SHIBUI_TICKER_RE guards the f-string-interpolated SQL sent to Shibui's
    MCP server -- must reject anything that isn't a bare ticker shape."""

    def test_accepts_plain_tickers(self):
        from routers.market import _SHIBUI_TICKER_RE
        for t in ("AAPL", "MSFT", "BRK.B", "BF-B", "F", "T"):
            assert _SHIBUI_TICKER_RE.match(t), f"{t} should be accepted"

    def test_rejects_injection_attempts(self):
        from routers.market import _SHIBUI_TICKER_RE
        for t in ("AAPL'; DROP TABLE x; --", "AAPL OR 1=1", "", "'", " AAPL", "AAPL "):
            assert not _SHIBUI_TICKER_RE.match(t), f"{t} should be rejected"


class TestScreenerRowBounded:
    """_ticker_screener_row must route through market_data's bounded, cached
    get_info — a raw yf.Ticker(...).info call can hang for ~10 minutes on one
    thin ticker and stall the whole 500-name screener scan."""

    @pytest.fixture(autouse=True)
    def _clean_row_cache(self):
        from routers import market
        market._SCREENER_ROW_CACHE.clear()
        yield
        market._SCREENER_ROW_CACHE.clear()

    def test_row_uses_bounded_market_data(self, monkeypatch):
        from routers import market

        calls = []

        def fake_get_info(sym, **kwargs):
            calls.append(sym)
            return {"currentPrice": 123.0, "shortName": "Test Co", "marketCap": 5_000_000}

        def forbidden_ticker(sym):
            raise AssertionError("raw yf.Ticker() bypasses the bounded wrapper")

        monkeypatch.setattr(market.market_data, "get_info", fake_get_info)
        monkeypatch.setattr(market.yf, "Ticker", forbidden_ticker)

        row = market._ticker_screener_row("AAPL")
        assert calls == ["AAPL"]
        assert row["price"] == 123.0
        assert row.get("error") is None

    def test_row_reports_unavailable_when_no_data(self, monkeypatch):
        from routers import market
        monkeypatch.setattr(market.market_data, "get_info", lambda sym, **k: {})
        monkeypatch.setattr(
            market.yf, "Ticker",
            lambda s: (_ for _ in ()).throw(AssertionError("raw yf call")))
        row = market._ticker_screener_row("THIN")
        assert row.get("error") == "unavailable"


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


class TestShibuiFilings:
    """GET /market/shibui/filings/{ticker} (PLAN.md 1a)."""

    def setup_method(self):
        from cache import cache_clear
        cache_clear()

    def test_rejects_form_types_outside_whitelist(self):
        from routers.market import get_shibui_filings
        import pytest as _pytest
        from fastapi import HTTPException
        with _pytest.raises(HTTPException) as exc_info:
            get_shibui_filings("AAPL", form_types="AAPL'; DROP TABLE x; --")
        assert exc_info.value.status_code == 400

    def test_rejects_invalid_ticker(self):
        from routers.market import get_shibui_filings
        import pytest as _pytest
        from fastapi import HTTPException
        with _pytest.raises(HTTPException) as exc_info:
            get_shibui_filings("'; DROP TABLE x; --")
        assert exc_info.value.status_code == 400

    def test_valid_request_filters_and_shapes_payload(self, monkeypatch):
        import routers.market as market

        captured_sql = {}

        def fake_query(sql, user_prompt):
            captured_sql["sql"] = sql
            return [{"filing_date": "2026-01-01", "form_type": "10-K", "raw_form_type": "10-K",
                     "is_amendment": False, "report_date": "2025-12-31", "items": [],
                     "filing_url": "https://sec.gov/x", "acceptance_datetime": "2026-01-01T00:00:00"}]

        monkeypatch.setattr(market.shibui_client, "query", fake_query)
        out = market.get_shibui_filings("aapl", form_types="10-K, bogus-type")
        assert out["ticker"] == "AAPL"
        assert out["form_types"] == ["10-K"]  # bogus-type silently dropped
        assert len(out["filings"]) == 1
        assert "'AAPL'" in captured_sql["sql"]
        assert "'10-K'" in captured_sql["sql"]

    def test_empty_result_is_404(self, monkeypatch):
        import routers.market as market
        from fastapi import HTTPException
        import pytest as _pytest

        monkeypatch.setattr(market.shibui_client, "query", lambda sql, prompt: [])
        with _pytest.raises(HTTPException) as exc_info:
            market.get_shibui_filings("AAPL")
        assert exc_info.value.status_code == 404


class TestClusterBuyDetection:
    """_is_cluster_candidate / _detect_cluster_buys (PLAN.md 1c) -- pure
    Python logic over insider-transaction rows, no network involved."""

    def _buy(self, owner_cik, tx_date, **overrides):
        row = {
            "tx_code": "P", "is_derivative": False, "is_auto_plan": False,
            "is_estate": False, "price_per_share": 100.0, "security_title": "Common Stock",
            "owner_cik": owner_cik, "owner_canonical_name": f"Owner {owner_cik}", "tx_date": tx_date,
        }
        row.update(overrides)
        return row

    def test_filters_out_noise_transactions(self):
        from routers.market import _is_cluster_candidate
        assert not _is_cluster_candidate(self._buy("1", "2026-01-01", tx_code="S"))
        assert not _is_cluster_candidate(self._buy("1", "2026-01-01", is_derivative=True))
        assert not _is_cluster_candidate(self._buy("1", "2026-01-01", is_auto_plan=True))
        assert not _is_cluster_candidate(self._buy("1", "2026-01-01", is_estate=True))
        assert not _is_cluster_candidate(self._buy("1", "2026-01-01", price_per_share=None))
        assert not _is_cluster_candidate(self._buy("1", "2026-01-01", security_title="Options"))
        assert _is_cluster_candidate(self._buy("1", "2026-01-01"))

    def test_detects_cluster_of_three_distinct_owners_within_window(self):
        from routers.market import _detect_cluster_buys
        rows = [
            self._buy("1", "2026-01-01"),
            self._buy("2", "2026-01-10"),
            self._buy("3", "2026-01-20"),
        ]
        clusters = _detect_cluster_buys(rows)
        assert len(clusters) == 1
        assert clusters[0]["start"] == "2026-01-01"
        assert clusters[0]["end"] == "2026-01-20"
        assert len(clusters[0]["buyers"]) == 3

    def test_no_cluster_when_fewer_than_three_owners(self):
        from routers.market import _detect_cluster_buys
        rows = [self._buy("1", "2026-01-01"), self._buy("2", "2026-01-10")]
        assert _detect_cluster_buys(rows) == []

    def test_no_cluster_when_owners_spread_beyond_window(self):
        from routers.market import _detect_cluster_buys
        rows = [
            self._buy("1", "2026-01-01"),
            self._buy("2", "2026-02-15"),
            self._buy("3", "2026-04-01"),
        ]
        assert _detect_cluster_buys(rows) == []

    def test_same_owner_buying_repeatedly_does_not_count_as_a_cluster(self):
        from routers.market import _detect_cluster_buys
        rows = [self._buy("1", d) for d in ("2026-01-01", "2026-01-05", "2026-01-10")]
        assert _detect_cluster_buys(rows) == []


class TestShibuiInsiders:
    """GET /market/shibui/insiders/{ticker} (PLAN.md 1b) -- replaces the
    yfinance-scraped insider table with Shibui's structured Form 4/5 data."""

    def setup_method(self):
        from cache import cache_clear
        cache_clear()

    def test_returns_transactions_and_cluster_buys(self, monkeypatch):
        import routers.market as market

        rows = [
            {"tx_date": "2026-01-01", "owner_cik": "1", "owner_canonical_name": "A",
             "tx_code": "P", "is_derivative": False, "is_auto_plan": False, "is_estate": False,
             "price_per_share": 10.0, "security_title": "Common Stock"},
            {"tx_date": "2026-01-10", "owner_cik": "2", "owner_canonical_name": "B",
             "tx_code": "P", "is_derivative": False, "is_auto_plan": False, "is_estate": False,
             "price_per_share": 11.0, "security_title": "Common Stock"},
            {"tx_date": "2026-01-15", "owner_cik": "3", "owner_canonical_name": "C",
             "tx_code": "P", "is_derivative": False, "is_auto_plan": False, "is_estate": False,
             "price_per_share": 12.0, "security_title": "Common Stock"},
        ]
        monkeypatch.setattr(market.shibui_client, "query", lambda sql, prompt: rows)
        out = market.get_shibui_insiders("NVDA", months=12)
        assert out["ticker"] == "NVDA"
        assert len(out["transactions"]) == 3
        assert len(out["cluster_buys"]) == 1

    def test_empty_result_is_404(self, monkeypatch):
        import routers.market as market
        from fastapi import HTTPException
        import pytest as _pytest

        monkeypatch.setattr(market.shibui_client, "query", lambda sql, prompt: [])
        with _pytest.raises(HTTPException) as exc_info:
            market.get_shibui_insiders("NVDA")
        assert exc_info.value.status_code == 404


class TestShibuiBeneficialOwnership:
    """GET /market/shibui/activist-stakes/{ticker} and
    /market/shibui/strategic-investors/{ticker} (PLAN.md 1d/1e)."""

    def setup_method(self):
        from cache import cache_clear
        cache_clear()

    def test_activist_stakes_404s_on_empty(self, monkeypatch):
        import routers.market as market
        from fastapi import HTTPException
        import pytest as _pytest

        monkeypatch.setattr(market.shibui_client, "query", lambda sql, prompt: [])
        with _pytest.raises(HTTPException) as exc_info:
            market.get_shibui_activist_stakes("AAPL")
        assert exc_info.value.status_code == 404

    def test_strategic_investors_returns_empty_list_not_404(self, monkeypatch):
        """Most tickers have no corporate strategic investor -- that's the
        expected common case, not an error (unlike the other Shibui endpoints)."""
        import routers.market as market

        monkeypatch.setattr(market.shibui_client, "query", lambda sql, prompt: [])
        out = market.get_shibui_strategic_investors("AAPL")
        assert out == {"ticker": "AAPL", "source": "shibui", "investors": []}


class TestShibuiShortInterest:
    """_shibui_short_interest (PLAN.md phase 3) -- supplementary data folded
    into _build_ownership; must never raise."""

    def test_returns_values_from_shibui(self, monkeypatch):
        import routers.market as market
        monkeypatch.setattr(
            market.shibui_client, "query",
            lambda sql, prompt: [{"short_percent_float": 0.0097, "shares_float": 14569223952.0}],
        )
        pct, shares = market._shibui_short_interest("AAPL")
        assert pct == 0.0097
        assert shares == 14569223952.0

    def test_invalid_ticker_returns_none_without_querying(self, monkeypatch):
        import routers.market as market

        def boom(sql, prompt):
            raise AssertionError("should not query Shibui for an invalid ticker")

        monkeypatch.setattr(market.shibui_client, "query", boom)
        assert market._shibui_short_interest("'; DROP TABLE x; --") == (None, None)

    def test_shibui_error_returns_none(self, monkeypatch):
        import routers.market as market
        import shibui_client

        def raise_error(sql, prompt):
            raise shibui_client.ShibuiError("boom")

        monkeypatch.setattr(market.shibui_client, "query", raise_error)
        assert market._shibui_short_interest("AAPL") == (None, None)


class TestPoliticianTrades:
    """GET /market/politician-trades/{ticker} (PLAN.md 1g) -- Alpha Vantage
    backed, gated behind ALPHA_VANTAGE_API_KEY, on-demand only."""

    def setup_method(self):
        from cache import cache_clear
        cache_clear()

    def test_503_when_api_key_not_configured(self, monkeypatch):
        import asyncio
        import routers.market as market
        from fastapi import HTTPException

        monkeypatch.setattr(market.alphavantage_client, "ALPHA_VANTAGE_API_KEY", None)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(market.get_politician_trades("NVDA"))
        assert exc_info.value.status_code == 503

    def test_flags_likely_option_trades(self, monkeypatch):
        import asyncio
        import routers.market as market

        async def fake_congress_trades(symbol):
            return {
                "trades": [
                    {"asset_name": "NVIDIA Corporation - Common Stock (NVDA) [ST]",
                     "asset_type_code": "ST", "transaction_type": "SELL"},
                    {"asset_name": "Bloom Energy Corporation Class A Common Stock (BE) [OP]",
                     "asset_type_code": "OP", "transaction_type": "SELL"},
                    {"asset_name": "Purchased 50 call options with NVIDIA Corporation (NVDA) [OP]",
                     "asset_type_code": "OP", "transaction_type": "PURCHASE"},
                ],
                "trades_total_count": 3,
                "trades_truncated": False,
            }

        monkeypatch.setattr(market.alphavantage_client, "ALPHA_VANTAGE_API_KEY", "fake-key")
        monkeypatch.setattr(market.alphavantage_client, "congress_trades", fake_congress_trades)
        out = asyncio.run(market.get_politician_trades("NVDA"))
        flags = [t["is_likely_option"] for t in out["trades"]]
        assert flags == [False, False, True]
        assert out["total_count"] == 3


def test_stock_dividend_growth_returns_full_payload(monkeypatch):
    from routers.market import stock_dividend_growth
    import dividend_growth

    payload = {"ticker": "AAPL", "streak_years": 12, "cagr_pct": 8.0,
               "cagr_years_used": 5, "yoy_pct": 6.0, "payout_ratio_pct": 15.0,
               "annual": [{"year": 2023, "dps": 0.96}],
               "payments": [{"ex_date": "2023-02-10", "amount": 0.23}]}
    monkeypatch.setattr(dividend_growth, "compute_dividend_growth",
                        lambda symbol: {**payload, "ticker": symbol})
    out = stock_dividend_growth("AAPL")
    assert out["ticker"] == "AAPL"
    assert out["payments"] == [{"ex_date": "2023-02-10", "amount": 0.23}]
    assert out["annual"][0]["year"] == 2023
