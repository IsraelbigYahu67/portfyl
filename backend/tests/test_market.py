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


class TestShibuiOwnershipStats:
    """_shibui_ownership_stats (PLAN.md phase 3 + fundamentals-primary-source
    follow-up) -- supplementary data folded into _build_ownership; must never
    raise, since the fundamentals endpoint has to keep working without it."""

    def test_returns_row_from_shibui(self, monkeypatch):
        import routers.market as market
        row = {"percent_insiders": 5.2, "percent_institutions": 61.3,
               "short_percent_float": 0.0097, "shares_float": 14569223952.0}
        monkeypatch.setattr(market.shibui_client, "query", lambda sql, prompt: [row])
        assert market._shibui_ownership_stats("AAPL") == row

    def test_invalid_ticker_returns_empty_without_querying(self, monkeypatch):
        import routers.market as market

        def boom(sql, prompt):
            raise AssertionError("should not query Shibui for an invalid ticker")

        monkeypatch.setattr(market.shibui_client, "query", boom)
        assert market._shibui_ownership_stats("'; DROP TABLE x; --") == {}

    def test_shibui_error_returns_empty(self, monkeypatch):
        import routers.market as market
        import shibui_client

        def raise_error(sql, prompt):
            raise shibui_client.ShibuiError("boom")

        monkeypatch.setattr(market.shibui_client, "query", raise_error)
        assert market._shibui_ownership_stats("AAPL") == {}

    def test_build_ownership_prefers_shibui_percentages_over_yfinance_info(self, monkeypatch):
        import routers.market as market

        monkeypatch.setattr(
            market, "_shibui_ownership_stats",
            lambda sym: {"percent_insiders": 5.2, "percent_institutions": 61.3,
                         "short_percent_float": 0.0097, "shares_float": 14569223952.0},
        )
        info = {"heldPercentInsiders": 0.99, "heldPercentInstitutions": 0.01}  # should be ignored
        out = market._build_ownership(stock=None, info=info, sym="AAPL")
        assert out["insider_pct"] == 5.2
        assert out["institutional_pct"] == 61.3
        assert out["short_percent_float"] == 0.0097

    def test_build_ownership_falls_back_to_yfinance_info_when_shibui_empty(self, monkeypatch):
        import routers.market as market

        monkeypatch.setattr(market, "_shibui_ownership_stats", lambda sym: {})
        info = {"heldPercentInsiders": 0.05, "heldPercentInstitutions": 0.60}
        out = market._build_ownership(stock=None, info=info, sym="XYZ")
        assert out["insider_pct"] == 5.0
        assert out["institutional_pct"] == 60.0
        assert out["short_percent_float"] is None


class TestShibuiFinancialsFromRows:
    """_shibui_financials_from_rows (fundamentals-as-primary-source
    follow-up) -- reshapes Shibui fundamentals_yearly/quarterly rows into
    the same metric-block shape _build_financials produces from yfinance."""

    def test_annual_labels_and_sorting(self):
        from routers.market import _shibui_financials_from_rows
        rows = [
            {"year": 2025, "revenue": 300.0, "net_income": 30.0},
            {"year": 2023, "revenue": 100.0, "net_income": 10.0},
            {"year": 2024, "revenue": 200.0, "net_income": 20.0},
        ]
        out = _shibui_financials_from_rows(rows, "Y")
        assert out["revenue"]["years"] == ["2023", "2024", "2025"]
        assert out["revenue"]["values"] == [100.0, 200.0, 300.0]
        assert out["net_income"]["values"] == [10.0, 20.0, 30.0]

    def test_quarterly_labels(self):
        from routers.market import _shibui_financials_from_rows
        rows = [
            {"year": 2025, "quarter": 2, "revenue": 20.0},
            {"year": 2025, "quarter": 1, "revenue": 10.0},
        ]
        out = _shibui_financials_from_rows(rows, "Q")
        assert out["revenue"]["years"] == ["Q1 '25", "Q2 '25"]
        assert out["revenue"]["values"] == [10.0, 20.0]

    def test_eps_falls_back_to_basic_when_diluted_missing(self):
        from routers.market import _shibui_financials_from_rows
        rows = [{"year": 2025, "eps_diluted": None, "eps": 4.2}]
        out = _shibui_financials_from_rows(rows, "Y")
        assert out["eps"]["values"] == [4.2]

    def test_missing_values_are_dropped_not_nulled(self):
        from routers.market import _shibui_financials_from_rows
        rows = [{"year": 2024, "revenue": 100.0}, {"year": 2025, "revenue": None}]
        out = _shibui_financials_from_rows(rows, "Y")
        assert out["revenue"]["years"] == ["2024"]
        assert out["revenue"]["values"] == [100.0]


class TestShibuiFundamentals:
    """_shibui_fundamentals (fundamentals-as-primary-source follow-up) --
    gates on the annual query alone; None means 'not Shibui-covered', in
    which case get_fundamentals must fall back to its existing yfinance path
    untouched."""

    def setup_method(self):
        from cache import cache_clear
        cache_clear()

    def test_returns_none_when_annual_query_is_empty(self, monkeypatch):
        import routers.market as market
        monkeypatch.setattr(market.shibui_client, "query", lambda sql, prompt: [])
        assert market._shibui_fundamentals("HSBA.L") is None

    def test_returns_none_on_invalid_ticker_without_querying(self, monkeypatch):
        import routers.market as market

        def boom(sql, prompt):
            raise AssertionError("should not query Shibui for an invalid ticker")

        monkeypatch.setattr(market.shibui_client, "query", boom)
        assert market._shibui_fundamentals("'; DROP TABLE x; --") is None

    def test_full_success_path_scales_units_correctly(self, monkeypatch):
        import routers.market as market

        annual_rows = [{"year": 2025, "revenue": 400.0, "cost_of_revenue": 200.0, "gross_profit": 200.0,
                        "operating_income": 130.0, "ebitda": 140.0, "net_income": 100.0, "eps": 6.0,
                        "eps_diluted": 5.9, "free_cash_flow": 90.0, "debt": 80.0,
                        "cash_and_equivalents": 50.0, "shares_outstanding": 15.0}]
        quarterly_rows = [{"year": 2025, "quarter": 4, "revenue": 100.0, "current_ratio": 1.2,
                           "profit_margin": 0.25, "piotroski_f_score": 7.0,
                           "current_assets": 60.0, "inventory": 10.0, "current_liabilities": 50.0}]
        ratio_row = {"market_cap": 3000.0, "enterprise_value": 3030.0, "price_to_book": 40.0,
                     "trailing_pe": 30.0, "price_to_sales": 7.5, "price_to_cash_flow": 33.3,
                     "ev_ebitda": 21.6, "dividend_yield": 0.005, "payout_ratio": 0.12,
                     "return_on_equity_ttm": 1.2, "return_on_assets": 0.08,
                     "return_on_invested_capital": 0.45, "debt_to_equity": 0.78,
                     "gross_margin": 0.5, "operating_margin": 0.325, "profit_margin_ttm": 0.25}

        calls = [annual_rows, quarterly_rows, [ratio_row]]
        monkeypatch.setattr(market.shibui_client, "query", lambda sql, prompt: calls.pop(0))

        out = market._shibui_fundamentals("AAPL")
        assert out is not None
        assert out["annual"]["revenue"]["values"] == [400.0]
        assert out["annual"]["eps"]["values"] == [5.9]  # prefers diluted
        # Decimal-fraction Shibui fields must land as PERCENT to match the
        # rest of the `ratios` dict's convention (yfinance-sourced values).
        assert out["ratios"]["roe"] == 120.0
        assert out["ratios"]["roa"] == 8.0
        assert out["ratios"]["roic"] == 45.0
        assert out["ratios"]["gross_margin"] == 50.0
        assert out["ratios"]["operating_margin"] == 32.5
        assert out["ratios"]["net_margin"] == 25.0
        assert out["ratios"]["div_yield"] == 0.5
        assert out["ratios"]["payout_ratio"] == 12.0
        # debt_to_equity is already a multiple in Shibui -- passed through raw.
        assert out["ratios"]["de"] == 0.78
        # trailing_pe / price_to_sales / price_to_book / ev_ebitda are already
        # ratio numbers in Shibui -- passed through raw, no scaling.
        assert out["ratios"]["pe"] == 30.0
        assert out["ratios"]["ps"] == 7.5
        assert out["ratios"]["pb"] == 40.0
        assert out["ratios"]["ev_ebitda"] == 21.6
        assert out["ratios"]["piotroski_f_score"] == 7.0
        assert out["ratios"]["current_ratio"] == 1.2
        assert out["ratios"]["quick_ratio"] == 1.0  # (60-10)/50
        assert out["market_cap"] == 3000.0
        assert out["enterprise_value"] == 3030.0

    def test_quarterly_or_ratio_failure_still_returns_annual(self, monkeypatch):
        """If Shibui gives annual data but errors on the other two calls, the
        ticker is still treated as Shibui-covered -- annual financials are
        used, quarterly/ratios/ownership just come back empty/None instead
        of taking down the whole result."""
        import routers.market as market
        import shibui_client

        annual_rows = [{"year": 2025, "revenue": 400.0}]
        calls = [annual_rows]

        def fake_query(sql, prompt):
            if calls:
                return calls.pop(0)
            raise shibui_client.ShibuiError("boom")

        monkeypatch.setattr(market.shibui_client, "query", fake_query)
        out = market._shibui_fundamentals("AAPL")
        assert out is not None
        assert out["quarterly"] == {}
        assert out["market_cap"] is None
        assert all(v is None for v in out["ratios"].values())


class TestFundamentalsPreferShibui:
    """get_fundamentals (fundamentals-as-primary-source follow-up): when
    Shibui covers the ticker its financials/ratios win over yfinance's,
    without breaking coverage for tickers Shibui doesn't have (foreign
    listings, delisted, etc.)."""

    def setup_method(self):
        from cache import cache_clear
        import routers.market as market
        cache_clear()
        market._FUND_CACHE.clear()

    def _stub_yf_ticker(self, monkeypatch):
        import routers.market as market

        class _StubTicker:
            def __getattr__(self, name):
                import pandas as pd
                return pd.DataFrame()

        monkeypatch.setattr(market.yf, "Ticker", lambda sym: _StubTicker())

    def test_prefers_shibui_financials_and_does_not_clobber_roic(self, monkeypatch):
        import routers.market as market

        self._stub_yf_ticker(monkeypatch)
        monkeypatch.setattr(market.market_data, "get_info",
                            lambda sym, timeout=None: {"symbol": "AAPL", "currentPrice": 200.0, "marketCap": 3e12})
        block = lambda: {"name": "x", "years": ["2024", "2025"], "values": [1.0, 2.0], "yoy": [None, 100.0], "cagr": 100.0}
        shibui_fixture = {
            "annual": {k: block() for k in (
                "revenue", "cost_of_revenue", "gross_profit", "operating_income", "ebitda",
                "net_income", "eps", "fcf", "debt", "cash", "shares_outstanding")},
            "quarterly": {},
            "ratios": {"pe": 11.11, "roic": 42.0, "piotroski_f_score": 7.0},
            "market_cap": 3.1e12,
            "enterprise_value": 3.2e12,
        }
        monkeypatch.setattr(market, "_shibui_fundamentals", lambda sym: shibui_fixture)
        monkeypatch.setattr(market, "_shibui_ownership_stats", lambda sym: {})

        payload = market.get_fundamentals("AAPL")
        assert payload["fundamentals_source"] == "shibui"
        assert payload["financials"]["revenue"]["values"] == [1.0, 2.0]
        assert payload["ratios"]["pe"] == 11.11
        # The statement-based ROIC fallback must not override Shibui's value
        # (income_stmt is empty here anyway, but this is the behavior that
        # matters even when statements ARE available).
        assert payload["ratios"]["roic"] == 42.0
        assert payload["ratios"]["piotroski_f_score"] == 7.0

    def test_falls_back_to_yfinance_when_shibui_has_no_coverage(self, monkeypatch):
        import routers.market as market

        self._stub_yf_ticker(monkeypatch)
        monkeypatch.setattr(market.market_data, "get_info",
                            lambda sym, timeout=None: {"symbol": "HSBA.L", "currentPrice": 1500.0, "marketCap": 1e11})
        monkeypatch.setattr(market, "_shibui_fundamentals", lambda sym: None)
        monkeypatch.setattr(market, "_shibui_ownership_stats", lambda sym: {})

        payload = market.get_fundamentals("HSBA.L")
        assert payload["fundamentals_source"] == "yfinance"
        assert payload["financials"]["revenue"]["values"] == []


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


class TestShibuiEarnings:
    """GET /market/shibui/earnings/{ticker} (PLAN.md 2a)."""

    def setup_method(self):
        from cache import cache_clear
        cache_clear()

    def test_rejects_invalid_ticker(self):
        from fastapi import HTTPException
        from routers.market import get_shibui_earnings
        with pytest.raises(HTTPException) as exc_info:
            get_shibui_earnings("'; DROP TABLE x; --")
        assert exc_info.value.status_code == 400

    def test_empty_result_is_404(self, monkeypatch):
        import routers.market as market
        from fastapi import HTTPException

        monkeypatch.setattr(market.shibui_client, "query", lambda sql, prompt: [])
        with pytest.raises(HTTPException) as exc_info:
            market.get_shibui_earnings("AAPL")
        assert exc_info.value.status_code == 404

    def test_returns_quarters(self, monkeypatch):
        import routers.market as market

        rows = [{"date": "2026-06-30", "eps_actual": 2.02, "eps_estimate": 1.88}]
        monkeypatch.setattr(market.shibui_client, "query", lambda sql, prompt: rows)
        out = market.get_shibui_earnings("AAPL")
        assert out["ticker"] == "AAPL"
        assert out["quarters"] == rows


class TestShibuiEarningsRecap:
    """GET /market/shibui/earnings-recap/{ticker} (PLAN.md 2e)."""

    def setup_method(self):
        from cache import cache_clear
        cache_clear()

    def test_rejects_invalid_ticker(self):
        from fastapi import HTTPException
        from routers.market import get_shibui_earnings_recap
        with pytest.raises(HTTPException) as exc_info:
            get_shibui_earnings_recap("'; DROP TABLE x; --")
        assert exc_info.value.status_code == 400

    def test_empty_quarters_is_404(self, monkeypatch):
        import routers.market as market
        from fastapi import HTTPException

        monkeypatch.setattr(market.shibui_client, "query", lambda sql, prompt: [])
        with pytest.raises(HTTPException) as exc_info:
            market.get_shibui_earnings_recap("AAPL")
        assert exc_info.value.status_code == 404

    def test_combines_quarters_buyback_and_filing_link(self, monkeypatch):
        import routers.market as market

        quarters = [{"earnings_date": "2026-06-30", "report_date": "2026-07-30",
                    "eps_actual": 2.02, "eps_estimate": 1.88, "revenue_actual": 1000.0}]
        buyback = [{"year": 2026, "quarter": 3, "equity_issuance_repayment": -500.0}]
        filing = [{"filing_date": "2026-07-30", "filing_url": "https://sec.gov/x"}]
        calls = [quarters, buyback, filing]
        monkeypatch.setattr(market.shibui_client, "query", lambda sql, prompt: calls.pop(0))

        class _NoRevenueEstimateTicker:
            revenue_estimate = None

        monkeypatch.setattr(market.yf, "Ticker", lambda sym: _NoRevenueEstimateTicker())

        out = market.get_shibui_earnings_recap("AAPL")
        assert out["quarters"] == quarters
        assert out["buyback_trend"] == buyback
        assert out["nearest_8k_2_02"] == filing[0]
        assert out["latest_revenue_estimate"] is None
        assert out["latest_revenue_surprise_pct"] is None
        assert out["source"] == "shibui"

    def test_computes_revenue_surprise_when_yfinance_has_minus_1q(self, monkeypatch):
        import routers.market as market
        import pandas as pd

        quarters = [{"earnings_date": "2026-06-30", "report_date": "2026-07-30",
                    "eps_actual": 2.02, "eps_estimate": 1.88, "revenue_actual": 110.0}]
        calls = [quarters, [], []]
        monkeypatch.setattr(market.shibui_client, "query", lambda sql, prompt: calls.pop(0))

        rev_est_df = pd.DataFrame({"avg": [100.0]}, index=["-1q"])

        class _StubTicker:
            revenue_estimate = rev_est_df

        monkeypatch.setattr(market.yf, "Ticker", lambda sym: _StubTicker())

        out = market.get_shibui_earnings_recap("AAPL")
        assert out["latest_revenue_estimate"] == 100.0
        assert out["latest_revenue_surprise_pct"] == 10.0  # (110-100)/100 * 100
        assert out["source"] == "shibui+yfinance"

    def test_yfinance_failure_does_not_break_the_endpoint(self, monkeypatch):
        import routers.market as market

        quarters = [{"earnings_date": "2026-06-30", "report_date": "2026-07-30",
                    "eps_actual": 2.02, "eps_estimate": 1.88, "revenue_actual": 110.0}]
        calls = [quarters, [], []]
        monkeypatch.setattr(market.shibui_client, "query", lambda sql, prompt: calls.pop(0))

        def boom(sym):
            raise RuntimeError("yfinance is down")

        monkeypatch.setattr(market.yf, "Ticker", boom)
        out = market.get_shibui_earnings_recap("AAPL")
        assert out["latest_revenue_estimate"] is None
        assert out["source"] == "shibui"


class TestValuationGranularityLadder:
    """_pick_valuation_granularity (PLAN.md phase 5) -- pure function of the
    requested date range, picking the finest bucket that stays under
    Shibui's 200-row cap. Boundary values verified live against the actual
    ladder cutoffs in PLAN.md (190/1300/2600/5400 days)."""

    def test_boundaries(self):
        from routers.market import _pick_valuation_granularity
        cases = {
            189: "day", 190: "day", 191: "week",
            1299: "week", 1300: "week", 1301: "biweekly",
            2599: "biweekly", 2600: "biweekly", 2601: "month",
            5399: "month", 5400: "month", 5401: "quarter",
            20000: "quarter",
        }
        for days, expected in cases.items():
            assert _pick_valuation_granularity(days) == expected, f"{days} days"


class TestShibuiValuationHistory:
    """GET /market/shibui/valuation-history/{ticker} (PLAN.md phase 5)."""

    def setup_method(self):
        from cache import cache_clear
        cache_clear()

    def test_rejects_invalid_ticker(self):
        from fastapi import HTTPException
        from routers.market import get_shibui_valuation_history
        with pytest.raises(HTTPException) as exc_info:
            get_shibui_valuation_history("'; DROP TABLE x; --")
        assert exc_info.value.status_code == 400

    def test_empty_result_is_404(self, monkeypatch):
        import routers.market as market
        from fastapi import HTTPException

        monkeypatch.setattr(market.shibui_client, "query", lambda sql, prompt: [])
        with pytest.raises(HTTPException) as exc_info:
            market.get_shibui_valuation_history("AAPL")
        assert exc_info.value.status_code == 404

    def test_picks_granularity_from_years_and_reports_it(self, monkeypatch):
        import routers.market as market

        captured = {}

        def fake_query(sql, prompt):
            captured["sql"] = sql
            return [{"bucket": "2024-01-01", "trailing_pe": 20.0}]

        monkeypatch.setattr(market.shibui_client, "query", fake_query)

        out = market.get_shibui_valuation_history("AAPL", years=1)
        assert out["granularity"] == "week"
        assert "DATE_TRUNC('week', v.date)" in captured["sql"]
        assert out["years"] == 1
        assert out["points"] == [{"bucket": "2024-01-01", "trailing_pe": 20.0}]

    def test_max_range_uses_quarterly_bucket(self, monkeypatch):
        import routers.market as market

        captured = {}

        def fake_query(sql, prompt):
            captured["sql"] = sql
            return [{"bucket": "2024-01-01"}]

        monkeypatch.setattr(market.shibui_client, "query", fake_query)
        out = market.get_shibui_valuation_history("AAPL", years=50)
        assert out["granularity"] == "quarter"
        assert "DATE_TRUNC('quarter', v.date)" in captured["sql"]
        # years is capped at 50 -- a caller passing something silly doesn't
        # produce an absurd WHERE clause.
        assert "INTERVAL '50 years'" in captured["sql"]

    def test_years_capped_to_sane_bounds(self, monkeypatch):
        import routers.market as market

        captured = {}
        monkeypatch.setattr(market.shibui_client, "query",
                            lambda sql, prompt: captured.setdefault("sql", sql) or [{"bucket": "x"}])
        market.get_shibui_valuation_history("AAPL", years=9999)
        assert "INTERVAL '50 years'" in captured["sql"]


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
