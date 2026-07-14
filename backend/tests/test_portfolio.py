"""Tests for portfolio holdings, FIFO P&L, and summary logic."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from models import Transaction
from schemas import TransactionCreate
from routers.portfolio import _build_holdings, create_transaction, get_summary, get_holdings


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


class TestHoldingsCurrency:
    """/holdings splits currencies by field: per-share prices (avg_cost,
    current_price, live_price) stay in the stock's *native* currency, while
    portfolio-level values (market_value, cost_basis, pnl, dividends) convert
    to the display currency. A $200 US stock must never render as "200 Kč"."""

    # display currency CZK; USD settles at 20 Kč / $1, GBP at 29 Kč / £1.
    _FX = {"USD": 20.0, "CZK": 1.0, "GBP": 29.0}

    def _patches(self, live_price, ccy="USD"):
        from tests.helpers import make_txn  # noqa: F401 (import kept local for clarity)
        return (
            patch("routers.portfolio._fetch_price_and_info",
                  return_value=(live_price, "Mock Co.", ccy)),
            patch("routers.portfolio._live_fx_to_czk",
                  side_effect=lambda c, cache: self._FX.get((c or "USD").upper(), 1.0)),
            patch("routers.portfolio.market_data.get_infos", return_value={}),
        )

    def test_open_position_per_share_native_value_display(self, db_session, pid):
        """Open US holding, CZK display: avg_cost/current_price in USD;
        market_value/cost_basis/pnl in CZK."""
        db_session.add(make_txn("AAPL", "buy", 10, 150.0, currency="USD",
                                date=date(2024, 1, 1), portfolio_id=pid))
        db_session.commit()

        p1, p2, p3 = self._patches(live_price=200.0)
        with p1, p2, p3:
            rows = get_holdings(currency="CZK", db=db_session, pid=pid)

        h = next(r for r in rows if r["ticker"] == "AAPL")
        assert h["currency"] == "USD"
        # Per-share prices: native USD, NOT multiplied by the 20x FX rate.
        assert h["avg_cost"] == pytest.approx(150.0)
        assert h["current_price"] == pytest.approx(200.0)
        # Portfolio-level: converted to CZK (20x).
        assert h["market_value"] == pytest.approx(10 * 200.0 * 20.0)  # 40,000 Kč
        assert h["cost_basis"] == pytest.approx(10 * 150.0 * 20.0)    # 30,000 Kč
        assert h["pnl"] == pytest.approx(10000.0)                     # 40k - 30k

    def test_lse_pence_quote_valued_in_pounds(self, db_session, pid):
        """LSE stock quoted in pence (GBp): per-share prices stay in pence, but
        market_value must convert pence → pounds before applying the per-pound
        GBP rate — multiplying the raw pence price by it is a 100x error."""
        db_session.add(make_txn("SGRO.L", "buy", 100, 7000.0, currency="GBX",
                                fx_to_czk=0.29, date=date(2024, 1, 1), portfolio_id=pid))
        db_session.commit()

        p1, p2, p3 = self._patches(live_price=7150.0, ccy="GBp")
        with p1, p2, p3:
            rows = get_holdings(currency="CZK", db=db_session, pid=pid)

        h = next(r for r in rows if r["ticker"] == "SGRO.L")
        assert h["currency"] == "GBp"
        assert h["current_price"] == pytest.approx(7150.0)  # pence, native
        assert h["avg_cost"] == pytest.approx(7000.0)       # pence, native
        # 100 sh × £71.50 × 29 Kč/£ — NOT 100 × 7150 × 29.
        assert h["market_value"] == pytest.approx(100 * 71.50 * 29.0)
        # Cost basis converts via the txn's own pence→CZK snapshot rate.
        assert h["cost_basis"] == pytest.approx(100 * 7000.0 * 0.29)

    def test_closed_position_per_share_native_value_display(self, db_session, pid):
        """Closed US holding, CZK display: avg buy/sell and the live price are
        native USD; realized P&L is CZK."""
        for t in (
            make_txn("TSLA", "buy", 10, 200.0, currency="USD",
                     date=date(2024, 1, 1), portfolio_id=pid),
            make_txn("TSLA", "sell", 10, 250.0, currency="USD",
                     date=date(2024, 6, 1), portfolio_id=pid),
        ):
            db_session.add(t)
        db_session.commit()

        p1, p2, p3 = self._patches(live_price=300.0)
        with p1, p2, p3:
            rows = get_holdings(include_closed=True, currency="CZK", db=db_session, pid=pid)

        h = next(r for r in rows if r["ticker"] == "TSLA")
        assert h["closed"] is True
        assert h["currency"] == "USD"
        assert h["avg_cost"] == pytest.approx(200.0)       # native avg buy
        assert h["current_price"] == pytest.approx(250.0)  # native avg sell
        assert h["live_price"] == pytest.approx(300.0)     # native live price today
        assert h["pnl"] == pytest.approx(10000.0)          # 10*(250-200)*20 Kč


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


class TestCreateTransaction:
    """Tests for POST /portfolio/transactions (create_transaction)."""

    def test_creates_transaction_with_resolved_fields(self, db_session, pid):
        """Valid input creates a row: ticker upper-cased, name/fx resolved, portfolio_id set.

        Regression test: create_transaction used to crash with
        `TypeError: models.Transaction() got multiple values for keyword
        argument 'ticker'` because txn.model_dump() already carries 'ticker'
        and the constructor call passed ticker= again.
        """
        txn_in = TransactionCreate(
            ticker="aapl",
            type="buy",
            shares=10,
            price=150.0,
            currency="USD",
            date=date(2024, 1, 15),
        )

        with (
            patch("routers.portfolio.market_data.get_info", return_value={"shortName": "Apple Inc."}),
            patch("routers.portfolio.fetch_fx_to_czk", return_value=22.5),
        ):
            result = create_transaction(txn_in, db=db_session, pid=pid)

        assert result.id is not None
        assert result.ticker == "AAPL"
        assert result.name == "Apple Inc."
        assert result.fx_to_czk == 22.5
        assert result.portfolio_id == pid

        stored = db_session.query(Transaction).filter(Transaction.id == result.id).first()
        assert stored.ticker == "AAPL"
        assert stored.shares == 10


from tests.helpers import make_txn


class TestLiveFxFallback:
    """_live_fx_to_czk must never silently turn a quote hiccup into rate 1.0 —
    that once rendered every USD position at ≈ -95% in CZK display."""

    @pytest.fixture(autouse=True)
    def _clean_last_good(self):
        import routers.portfolio as rp
        rp._LAST_GOOD_FX.clear()
        yield
        rp._LAST_GOOD_FX.clear()

    def test_success_remembers_last_good_rate(self):
        import routers.portfolio as rp
        with patch("routers.portfolio.market_data.get_info",
                   return_value={"regularMarketPrice": 22.0}):
            assert rp._live_fx_to_czk("USD", {}) == 22.0
        assert rp._LAST_GOOD_FX["USD"] == 22.0

    def test_falls_back_to_daily_close_series(self):
        import routers.portfolio as rp
        with (
            patch("routers.portfolio.market_data.get_info", return_value={}),
            patch("routers.portfolio.fetch_fx_to_czk", return_value=21.5),
        ):
            assert rp._live_fx_to_czk("USD", {}) == 21.5

    def test_falls_back_to_last_good_rate(self):
        import routers.portfolio as rp
        rp._LAST_GOOD_FX["USD"] = 20.5
        with (
            patch("routers.portfolio.market_data.get_info", return_value={}),
            patch("routers.portfolio.fetch_fx_to_czk", return_value=None),
        ):
            assert rp._live_fx_to_czk("USD", {}) == 20.5

    def test_total_failure_returns_1_without_caching(self):
        import routers.portfolio as rp
        cache = {}
        with (
            patch("routers.portfolio.market_data.get_info", return_value={}),
            patch("routers.portfolio.fetch_fx_to_czk", return_value=None),
        ):
            assert rp._live_fx_to_czk("USD", cache) == 1.0
        # The made-up 1.0 must not stick for the rest of the request.
        assert "USD" not in cache

    def test_holdings_warms_fx_pairs_with_tickers(self, db_session, pid):
        """The FX pair joins the quote warm-up batch instead of queueing
        behind it (the queue-starvation that caused the 1.0 fallback)."""
        db_session.add(make_txn("AAPL", "buy", 10, 150.0, currency="USD",
                                date=date(2024, 1, 1), fx_to_czk=20.0,
                                portfolio_id=pid))
        db_session.commit()

        warmed = []
        with (
            patch("routers.portfolio.market_data.get_infos",
                  side_effect=lambda ts, **kw: warmed.extend(ts) or {}),
            patch("routers.portfolio._fetch_price_and_info",
                  return_value=(200.0, "Mock", "USD")),
            patch("routers.portfolio._live_fx_to_czk",
                  side_effect=lambda c, cache: 1.0 if (c or "USD").upper() == "CZK" else 20.0),
        ):
            get_holdings(currency="CZK", db=db_session, pid=pid)

        assert "AAPL" in warmed
        assert "USDCZK=X" in warmed
