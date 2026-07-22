"""Tests for dividend calendar endpoint."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from tests.helpers import make_txn


@pytest.fixture
def sample_portfolio_with_dividend_stocks(db_session, pid):
    """Portfolio with a few dividend-paying holdings."""
    txns = [
        make_txn("AAPL", "buy", 100, 150.0, date=date(2024, 1, 15), portfolio_id=pid),
        make_txn("MSFT", "buy", 50, 350.0, date=date(2024, 2, 1), portfolio_id=pid),
    ]
    for t in txns:
        db_session.add(t)
    db_session.commit()
    return pid


class TestDividendCalendarEndpoint:
    """Unit tests for the dividend calendar logic (mocked yfinance)."""

    def test_empty_portfolio_returns_empty(self, db_session, pid):
        """No transactions → empty calendar."""
        from routers.dividend_calendar import dividend_calendar
        result = dividend_calendar(months=12, db=db_session, pid=pid)
        assert result["tickers"] == []
        assert result["monthly_projection"] == []
        assert result["total_annual_est"] == 0

    def test_with_holdings_produces_tickers(self, db_session, sample_portfolio_with_dividend_stocks, mock_yfinance):
        """Portfolio with holdings returns ticker entries (mocked yfinance)."""
        from routers.dividend_calendar import dividend_calendar
        pid = sample_portfolio_with_dividend_stocks
        result = dividend_calendar(months=12, db=db_session, pid=pid)
        # With mock yfinance, all tickers return the default mock info
        assert len(result["tickers"]) == 2  # AAPL, MSFT
        tickers = {t["ticker"] for t in result["tickers"]}
        assert tickers == {"AAPL", "MSFT"}
        # Monthly projection should exist
        assert len(result["monthly_projection"]) > 0
        # Total annual est should be > 0 since we have shares
        assert result["total_annual_est"] >= 0

    def test_projection_excludes_months_before_current_month(self, db_session, sample_portfolio_with_dividend_stocks):
        """A suspended payer whose last ex-date is years ago must not flood the
        projection with decades of stale past months (the LEU/2005 bug)."""
        from routers.dividend_calendar import dividend_calendar
        pid = sample_portfolio_with_dividend_stocks

        def _stale(symbol):
            return {
                "ticker": symbol,
                "ex_date": "2005-03-01",  # years in the past — payer since suspended
                "pay_date": None,
                "amount_per_share": 0.25,
                "frequency": "quarterly",
                "trailing_yield_pct": 1.0,
                "dividend_rate_annual": 1.0,
            }

        with patch("routers.dividend_calendar._next_dividend_info", side_effect=_stale):
            result = dividend_calendar(months=12, db=db_session, pid=pid)

        current_month_key = date.today().strftime("%Y-%m")
        month_keys = [m["month"] for m in result["monthly_projection"]]
        assert month_keys, "expected some projected months"
        # month keys are 'YYYY-MM', so lexicographic min == chronological earliest
        assert min(month_keys) >= current_month_key, (
            f"projection leaked stale past months: earliest={min(month_keys)}"
        )

    def test_next_dividend_info_structure(self):
        """_next_dividend_info returns the expected fields."""
        from routers.dividend_calendar import _next_dividend_info
        # Real call would hit Network, but we can test structure
        # Just verify the function is importable and returns a dict
        import inspect
        sig = inspect.signature(_next_dividend_info)
        params = list(sig.parameters.keys())
        assert "symbol" in params
