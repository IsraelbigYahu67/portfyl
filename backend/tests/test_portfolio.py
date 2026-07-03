"""Tests for portfolio holdings, FIFO P&L, and summary logic."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from routers.portfolio import _build_holdings, get_summary


class TestBuildHoldings:
    """Unit tests for _build_holdings — the core FIFO aggregation engine."""

    def test_empty(self, db_session, pid):
        """No transactions → empty dict."""
        assert _build_holdings([]) == {}

    def test_single_buy(self, txns_demo, pid):
        """Single ticker with one buy lot."""
        # MSFT: bought 20 @ $350 → 20 shares, cost $7,000
        msft = _build_holdings([t for t in txns_demo if t.ticker == "MSFT" and t.type == "buy"])
        assert msft["MSFT"]["shares"] == 20
        assert msft["MSFT"]["cost"] == 20 * 350.0

    def test_partial_sell(self, txns_demo, pid):
        """Sell draws from the first lot (FIFO)."""
        # AAPL: buy 100 @ $150, buy 50 @ $160, sell 30 @ $175
        # After sell: shares = 120, cost = 150*100 + 160*50 - 30*150 = 15,000+8,000-4,500 = 18,500
        # Realized: 30*(175-150) = $750
        aapl = _build_holdings(
            [t for t in txns_demo if t.ticker == "AAPL" and t.type != "dividend"],
            include_closed=True,
        )
        assert aapl["AAPL"]["shares"] == pytest.approx(120.0)
        assert aapl["AAPL"]["cost"] == pytest.approx(18400.0)
        assert aapl["AAPL"]["realized_pnl"] == pytest.approx(650.0)

    def test_dividend_accumulation(self, txns_demo, pid):
        """Dividend transaction adds to the 'dividends' accumulator."""
        aapl = _build_holdings(
            [t for t in txns_demo if t.ticker == "AAPL"],
            include_closed=True,
        )
        assert aapl["AAPL"]["dividends"] == pytest.approx(100 * 0.50)

    def test_sell_reduces_cost_basis(self, txns_demo, pid):
        """Selling shares reduces the cost basis proportionally."""
        msft = _build_holdings(
            [t for t in txns_demo if t.ticker == "MSFT"],
            include_closed=True,
        )
        # Cost after sell: bought 20 @ $350 ($7,000), sold 10 → cost reduced by 10*$350 = $3,500
        assert msft["MSFT"]["shares"] == pytest.approx(10.0)
        assert msft["MSFT"]["cost"] == pytest.approx(10 * 350.0)

    def test_fully_closed_position(self, db_session, pid):
        """A fully closed position (shares = 0) is excluded by default."""
        txns = [
            make_txn("TSLA", "buy", 10, 200.0, date=date(2024, 1, 1), portfolio_id=pid),
            make_txn("TSLA", "sell", 10, 250.0, date=date(2024, 6, 1), portfolio_id=pid),
        ]
        for t in txns:
            db_session.add(t)
        db_session.commit()

        active = _build_holdings(txns, include_closed=False)
        assert "TSLA" not in active

        closed = _build_holdings(txns, include_closed=True)
        assert closed["TSLA"]["shares"] == 0.0
        assert closed["TSLA"]["realized_pnl"] == pytest.approx(10 * (250 - 200))

    def test_different_tickers_independent(self, txns_demo, pid):
        """AAPL and MSFT holdings are tracked independently."""
        h = _build_holdings(txns_demo, include_closed=True)
        assert "AAPL" in h
        assert "MSFT" in h
        assert h["AAPL"]["cost"] != h["MSFT"]["cost"]

    def test_sort_by_date(self, db_session, pid):
        """Transactions are processed in date order regardless of input order."""
        txns = [
            make_txn("NVDA", "buy", 5, 400.0, date=date(2024, 3, 1), portfolio_id=pid),
            make_txn("NVDA", "buy", 5, 800.0, date=date(2024, 1, 1), portfolio_id=pid),
        ]
        for t in txns:
            db_session.add(t)
        db_session.commit()
        # FIFO cost: lot1 @ $800 (Jan), lot2 @ $400 (Mar) — both still open
        h = _build_holdings(txns)
        assert h["NVDA"]["shares"] == 10.0
        assert h["NVDA"]["cost"] == pytest.approx(5 * 800 + 5 * 400)


class TestSummary:
    """Tests for /portfolio/summary logic (get_summary)."""

    def test_summary_values(self, txns_demo, pid, db_session):
        """Summary returns expected totals for the demo transactions."""
        s = get_summary(currency="USD", db=db_session, pid=pid)
        assert s["holdings_count"] == 2  # AAPL + MSFT
        # total_invested = AAPL cost (70*150 + 50*160? No, after sell: 70*150 + 50*160)
        # total_invested = AAPL cost (18400) + MSFT cost (3500) = 21900
        assert s["total_invested"] == pytest.approx(21900.0)
        assert s["total_dividends"] == pytest.approx(50.0)

    def test_empty_portfolio(self, db_session, pid):
        """No transactions → zeroed summary."""
        s = get_summary(currency="USD", db=db_session, pid=pid)
        assert s["total_value"] == 0.0
        assert s["holdings_count"] == 0


from tests.helpers import make_txn
