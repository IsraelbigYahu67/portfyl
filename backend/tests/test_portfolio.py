"""Tests for portfolio holdings, FIFO P&L, and summary logic."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

from models import BrokerConnection, BrokerSyncRun, Transaction
from schemas import TransactionCreate
from routers.portfolio import (
    _build_holdings,
    clear_all_transactions,
    create_transaction,
    delete_transaction,
    get_dividend_forecast,
    get_holdings,
    get_summary,
)
from tests.conftest import make_txn


class TestBuildHoldings:
    """Unit tests for _build_holdings — the core FIFO aggregation engine."""

    def test_empty(self, db_session, pid):
        """No transactions → empty dict."""
        assert _build_holdings([]) == {}

    def test_same_day_events_use_execution_time_before_type_fallback(self, pid):
        """A morning sell cannot consume shares bought later that afternoon."""
        sell = make_txn(
            "AAPL", "sell", 1, 110.0,
            date=date(2024, 1, 15), portfolio_id=pid,
        )
        sell.executed_at = datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc)
        buy = make_txn(
            "AAPL", "buy", 1, 100.0,
            date=date(2024, 1, 15), portfolio_id=pid,
        )
        buy.executed_at = datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc)

        holding = _build_holdings([buy, sell])["AAPL"]

        assert holding["shares"] == pytest.approx(1.0)
        assert holding["cost"] == pytest.approx(100.0)
        assert holding["realized_pnl"] == pytest.approx(0.0)

    def test_holding_received_dividends_use_paid_cash(self, pid):
        dividend = make_txn("AAPL", "dividend", 10, 1.0, currency="USD",
                            date=date(2024, 6, 1), portfolio_id=pid)
        dividend.cash_amount = 8.5
        dividend.cash_currency = "USD"

        with patch("routers.portfolio._live_fx_to_czk", return_value=1.0):
            holding = _build_holdings([dividend], include_closed=True, display_ccy="USD")["AAPL"]

        assert holding["dividends"] == pytest.approx(8.5)

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

    def test_open_position_per_share_native_value_display(self, db_session, pid, default_portfolio):
        """Open US holding, CZK display: avg_cost/current_price in USD;
        market_value/cost_basis/pnl in CZK."""
        db_session.add(make_txn("AAPL", "buy", 10, 150.0, currency="USD",
                                date=date(2024, 1, 1), portfolio_id=pid))
        db_session.commit()

        p1, p2, p3 = self._patches(live_price=200.0)
        with p1, p2, p3:
            rows = get_holdings(currency="CZK", db=db_session, portfolio=default_portfolio)

        h = next(r for r in rows if r["ticker"] == "AAPL")
        assert h["currency"] == "USD"
        # Per-share prices: native USD, NOT multiplied by the 20x FX rate.
        assert h["avg_cost"] == pytest.approx(150.0)
        assert h["current_price"] == pytest.approx(200.0)
        # Portfolio-level: converted to CZK (20x).
        assert h["market_value"] == pytest.approx(10 * 200.0 * 20.0)  # 40,000 Kč
        assert h["cost_basis"] == pytest.approx(10 * 150.0 * 20.0)    # 30,000 Kč
        assert h["pnl"] == pytest.approx(10000.0)                     # 40k - 30k

    def test_lse_pence_quote_valued_in_pounds(self, db_session, pid, default_portfolio):
        """LSE stock quoted in pence (GBp): per-share prices stay in pence, but
        market_value must convert pence → pounds before applying the per-pound
        GBP rate — multiplying the raw pence price by it is a 100x error."""
        db_session.add(make_txn("SGRO.L", "buy", 100, 7000.0, currency="GBX",
                                fx_to_czk=0.29, date=date(2024, 1, 1), portfolio_id=pid))
        db_session.commit()

        p1, p2, p3 = self._patches(live_price=7150.0, ccy="GBp")
        with p1, p2, p3:
            rows = get_holdings(currency="CZK", db=db_session, portfolio=default_portfolio)

        h = next(r for r in rows if r["ticker"] == "SGRO.L")
        assert h["currency"] == "GBp"
        assert h["current_price"] == pytest.approx(7150.0)  # pence, native
        assert h["avg_cost"] == pytest.approx(7000.0)       # pence, native
        # 100 sh × £71.50 × 29 Kč/£ — NOT 100 × 7150 × 29.
        assert h["market_value"] == pytest.approx(100 * 71.50 * 29.0)
        # Cost basis converts via the txn's own pence→CZK snapshot rate.
        assert h["cost_basis"] == pytest.approx(100 * 7000.0 * 0.29)

    def test_closed_position_per_share_native_value_display(self, db_session, pid, default_portfolio):
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
            rows = get_holdings(include_closed=True, currency="CZK", db=db_session, portfolio=default_portfolio)

        h = next(r for r in rows if r["ticker"] == "TSLA")
        assert h["closed"] is True
        assert h["currency"] == "USD"
        assert h["avg_cost"] == pytest.approx(200.0)       # native avg buy
        assert h["current_price"] == pytest.approx(250.0)  # native avg sell
        assert h["live_price"] == pytest.approx(300.0)     # native live price today
        assert h["pnl"] == pytest.approx(10000.0)          # 10*(250-200)*20 Kč


class TestSummary:
    """Tests for /portfolio/summary logic (get_summary)."""

    def test_summary_values(self, txns_demo, pid, db_session, default_portfolio):
        """Summary returns expected totals for the demo transactions."""
        s = get_summary(currency="USD", db=db_session, portfolio=default_portfolio)
        assert s["holdings_count"] == 2  # AAPL + MSFT
        # total_invested = AAPL cost (70*150 + 50*160? No, after sell: 70*150 + 50*160)
        # total_invested = AAPL cost (18400) + MSFT cost (3500) = 21900
        assert s["total_invested"] == pytest.approx(21900.0)
        assert s["total_dividends"] == pytest.approx(50.0)

    def test_summary_uses_received_dividend_cash_instead_of_gross(
        self, db_session, default_portfolio, pid
    ):
        dividend = make_txn("AAPL", "dividend", 10, 1.0, currency="USD",
                            date=date(2024, 6, 1), portfolio_id=pid)
        dividend.cash_amount = 8.5
        dividend.cash_currency = "USD"
        db_session.add(dividend)
        db_session.commit()

        with patch("routers.portfolio.get_holdings", return_value=[]), \
             patch("routers.portfolio._live_fx_to_czk", return_value=1.0):
            summary = get_summary(currency="USD", db=db_session, portfolio=default_portfolio)

        assert summary["total_dividends"] == pytest.approx(8.5)

    def test_empty_portfolio(self, db_session, pid, default_portfolio):
        """No transactions → zeroed summary."""
        s = get_summary(currency="USD", db=db_session, portfolio=default_portfolio)
        assert s["total_value"] == 0.0
        assert s["holdings_count"] == 0


def test_dividend_forecast_paid_total_uses_received_cash(db_session, default_portfolio, pid):
    today = datetime.now().date()
    dividend = make_txn("AAPL", "dividend", 10, 1.0, currency="USD",
                        date=today, portfolio_id=pid)
    dividend.cash_amount = 8.5
    dividend.cash_currency = "USD"
    db_session.add(dividend)
    db_session.commit()

    with patch("routers.portfolio._live_to_usd", return_value=1.0):
        forecast = get_dividend_forecast(db=db_session, portfolio=default_portfolio)

    assert forecast["total_paid"] == pytest.approx(8.5)


def test_delete_transaction_rejects_broker_managed_rows(
    db_session, default_portfolio, pid
):
    transaction = make_txn(
        "AAPL", "buy", 1, 100.0, date=date(2024, 1, 1),
        portfolio_id=pid, source="t212_api",
    )
    db_session.add(transaction)
    db_session.commit()

    with pytest.raises(Exception) as exc_info:
        delete_transaction(
            transaction.public_id, db=db_session, portfolio=default_portfolio,
        )

    assert exc_info.value.status_code == 409
    assert db_session.query(Transaction).filter_by(id=transaction.id).one()


def test_clear_all_transactions_invalidates_t212_history_state(
    db_session, default_portfolio, pid
):
    fingerprint = "f" * 64
    covered_at = datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)
    default_portfolio.t212_account_fingerprint = fingerprint
    default_portfolio.t212_csv_covered_through = covered_at
    connection = BrokerConnection(
        workspace_id=default_portfolio.workspace_id,
        portfolio_id=pid,
        broker="trading212",
        api_key="test-key-value-1234567890",
        account_fingerprint=fingerprint,
        last_synced_at=covered_at,
        t212_csv_covered_through=covered_at,
    )
    db_session.add(connection)
    db_session.flush()
    run = BrokerSyncRun(
        workspace_id=default_portfolio.workspace_id,
        portfolio_id=pid,
        connection_id=connection.id,
        broker="trading212",
        account_fingerprint=fingerprint,
        credential_generation=connection.credential_generation,
        mode="incremental",
        state="fetching",
    )
    completed_run = BrokerSyncRun(
        workspace_id=default_portfolio.workspace_id,
        portfolio_id=pid,
        connection_id=connection.id,
        broker="trading212",
        account_fingerprint=fingerprint,
        credential_generation=connection.credential_generation,
        mode="incremental",
        state="completed",
        completed_at=covered_at,
    )
    db_session.add_all([
        run,
        completed_run,
        make_txn(
            "AAPL", "buy", 1, 100.0, date=date(2024, 1, 1),
            portfolio_id=pid, source="t212_api",
        ),
    ])
    db_session.commit()

    result = clear_all_transactions(db=db_session, portfolio=default_portfolio)

    assert result == {"deleted": 1}
    assert db_session.query(Transaction).count() == 0
    db_session.refresh(run)
    db_session.refresh(completed_run)
    db_session.refresh(connection)
    db_session.refresh(default_portfolio)
    assert run.state == "cancelled"
    assert completed_run.state == "cancelled"
    assert connection.last_synced_at is None
    assert connection.t212_csv_covered_through is None
    assert default_portfolio.t212_csv_covered_through is None

def test_creates_transaction_with_resolved_fields(db_session, pid, default_portfolio):
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
        result = create_transaction(txn_in, db=db_session, portfolio=default_portfolio)

    assert result.id is not None
    assert result.ticker == "AAPL"
    assert result.name == "Apple Inc."
    assert result.fx_to_czk == 22.5
    assert result.portfolio_id == pid

    stored = db_session.query(Transaction).filter(Transaction.id == result.id).first()
    assert stored.ticker == "AAPL"
    assert stored.shares == 10


from tests.helpers import TEST_WORKSPACE_ID, make_txn


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

    def test_holdings_warms_fx_pairs_with_tickers(self, db_session, pid, default_portfolio):
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
            get_holdings(currency="CZK", db=db_session, portfolio=default_portfolio)

        assert "AAPL" in warmed
        assert "USDCZK=X" in warmed


def test_dividends_growth_lists_only_payers(db_session, pid, default_portfolio, monkeypatch):
    from routers.portfolio import get_dividend_growth
    from tests.helpers import make_txn
    import dividend_growth

    # Buy with real company name, then later dividend row with name=ticker.
    # Test ensures real name wins (first-wins logic), not the later bare-ticker name.
    db_session.add(make_txn("AAPL", "buy", 10, 150.0, name="Apple Inc.",
                            date=date(2024, 1, 2), portfolio_id=pid))
    db_session.add(make_txn("AAPL", "dividend", 10, 0.24, name="AAPL",
                            date=date(2024, 6, 1), portfolio_id=pid))
    db_session.add(make_txn("ZZZZ", "buy", 5, 20.0, portfolio_id=pid))
    db_session.commit()

    def fake_growth(symbol, _current_year=None):
        if symbol == "AAPL":
            return {"ticker": "AAPL", "streak_years": 3, "cagr_pct": 7.5,
                    "cagr_years_used": 5, "yoy_pct": 5.0, "payout_ratio_pct": 25.0,
                    "annual": [{"year": 2023, "dps": 0.9}], "payments": []}
        return {"ticker": symbol, "streak_years": 0, "cagr_pct": None,
                "cagr_years_used": 0, "yoy_pct": None, "payout_ratio_pct": None,
                "annual": [], "payments": []}

    monkeypatch.setattr(dividend_growth, "compute_dividend_growth", fake_growth)
    rows = get_dividend_growth(db=db_session, portfolio=default_portfolio)
    assert [r["ticker"] for r in rows] == ["AAPL"]      # ZZZZ (no history) filtered out
    assert rows[0]["name"] == "Apple Inc."              # first-wins real name, not later name=ticker dividend
    assert rows[0]["streak_years"] == 3
    assert "annual" not in rows[0] and "payments" not in rows[0]   # lightweight payload


def test_dividends_growth_empty_portfolio(db_session, pid, default_portfolio):
    from routers.portfolio import get_dividend_growth
    assert get_dividend_growth(db=db_session, portfolio=default_portfolio) == []


def test_portfolios_overview_sums_across_portfolios(
    db_session,
    monkeypatch,
    request_context,
):
    from unittest.mock import patch
    import pandas as pd
    import yfinance as yf
    from models import Portfolio
    from routers.portfolios import portfolios_overview
    from routers.portfolio import get_summary
    from tests.helpers import make_txn

    # Keep _two_day_closes (day-change calc) offline/deterministic too --
    # it calls yf.download() directly, outside the market_data.get_infos
    # patch below, and would otherwise hit the live network.
    monkeypatch.setattr(yf, "download", lambda *a, **kw: pd.DataFrame())

    p1 = Portfolio(
        workspace_id=TEST_WORKSPACE_ID,
        name="zubik",
        is_default=True,
    )
    p2 = Portfolio(workspace_id=TEST_WORKSPACE_ID, name="mama")
    db_session.add_all([p1, p2])
    db_session.commit()
    db_session.add(make_txn("AAPL", "buy", 10, 150.0, portfolio_id=p1.id))
    db_session.add(make_txn("MSFT", "buy", 5, 300.0, portfolio_id=p2.id))
    db_session.commit()

    def fake_infos(tickers, **kwargs):
        return {t: {"currentPrice": 200.0, "regularMarketPrice": 200.0,
                    "currency": "USD", "sector": "Technology",
                    "quoteType": "EQUITY"} for t in tickers}

    with patch("market_data.get_infos", side_effect=fake_infos):
        s1 = get_summary(currency="USD", db=db_session, portfolio=p1)
        s2 = get_summary(currency="USD", db=db_session, portfolio=p2)
        ov = portfolios_overview(
            currency="USD",
            context=request_context,
            db=db_session,
        )

    assert ov["portfolio_count"] == 2
    assert ov["total_net_worth"] == round(s1["net_worth"] + s2["net_worth"], 2)
    assert ov["currency"] == "USD"
    # both holdings are Technology in the mock -> one weighted sector at 100%
    assert ov["sectors"] and abs(sum(s["weight"] for s in ov["sectors"]) - 100.0) < 0.1


def test_portfolios_overview_empty_db(db_session, request_context):
    from routers.portfolios import portfolios_overview
    ov = portfolios_overview(
        currency="USD",
        context=request_context,
        db=db_session,
    )
    assert ov["portfolio_count"] == 0
    assert ov["total_net_worth"] == 0.0
    assert ov["sectors"] == []
    assert ov["total_day_change_percent"] is None
