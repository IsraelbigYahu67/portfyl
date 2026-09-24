"""Tests for analytics: tax report, FIFO lot matching, capital gains, Czech exemptions."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

from tests.helpers import make_txn
from routers.analytics import (
    LOT_EPSILON,
    _compute_capital_gains,
    _compute_czech_tax_by_year,
    _compute_unrealized_gains,
    _consume_fifo,
    tax_report,
)


class TestCapitalGains:
    """FIFO lot matching for capital gains."""

    def test_no_sells(self, db_session, pid):
        txns = [make_txn("AAPL", "buy", 10, 150.0, date=date(2024, 1, 1), portfolio_id=pid)]
        for t in txns:
            db_session.add(t)
        db_session.commit()
        gains = _compute_capital_gains(txns)
        assert gains == []

    def test_same_day_sell_cannot_match_a_later_timestamped_buy(self, pid):
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

        assert _compute_capital_gains([buy, sell]) == []

    def test_simple_gain(self, db_session, pid):
        """Buy 10 @ $150, sell all @ $200 → gain $500."""
        txns = [
            make_txn("AAPL", "buy", 10, 150.0, date=date(2024, 1, 1), portfolio_id=pid),
            make_txn("AAPL", "sell", 10, 200.0, date=date(2024, 6, 1), portfolio_id=pid),
        ]
        for t in txns:
            db_session.add(t)
        db_session.commit()
        gains = _compute_capital_gains(txns)
        assert len(gains) == 1
        assert gains[0]["gain"] == pytest.approx(500.0)
        assert gains[0]["term"] == "short"
        assert gains[0]["holding_days"] == 152  # approx

    def test_long_term_threshold(self, db_session, pid):
        """Held > 365 days → 'long' term."""
        txns = [
            make_txn("AAPL", "buy", 10, 150.0, date=date(2020, 1, 1), portfolio_id=pid),
            make_txn("AAPL", "sell", 10, 200.0, date=date(2024, 6, 1), portfolio_id=pid),
        ]
        for t in txns:
            db_session.add(t)
        db_session.commit()
        gains = _compute_capital_gains(txns)
        assert gains[0]["term"] == "long"
        assert gains[0]["holding_days"] > 365

    def test_fifo_multi_lot(self, db_session, pid):
        """FIFO: sell 15 from lot1 (100 @ $10) and lot2 (50 @ $15)."""
        txns = [
            make_txn("AAPL", "buy", 100, 10.0, date=date(2024, 1, 1), portfolio_id=pid),
            make_txn("AAPL", "buy", 50, 15.0, date=date(2024, 2, 1), portfolio_id=pid),
            make_txn("AAPL", "sell", 120, 20.0, date=date(2024, 3, 1), portfolio_id=pid),
        ]
        for t in txns:
            db_session.add(t)
        db_session.commit()
        gains = _compute_capital_gains(txns)
        # Lot1: all 100 sold → gain = 100*(20-10)=1000
        # Lot2: 20 of 50 sold → gain = 20*(20-15)=100
        assert len(gains) == 2
        assert gains[0]["gain"] == pytest.approx(1000.0)
        assert gains[1]["gain"] == pytest.approx(100.0)

    def test_loss(self, db_session, pid):
        """Sell at a loss → negative gain."""
        txns = [
            make_txn("AAPL", "buy", 10, 200.0, date=date(2024, 1, 1), portfolio_id=pid),
            make_txn("AAPL", "sell", 10, 150.0, date=date(2024, 6, 1), portfolio_id=pid),
        ]
        for t in txns:
            db_session.add(t)
        db_session.commit()
        gains = _compute_capital_gains(txns)
        assert gains[0]["gain"] == pytest.approx(-500.0)

    def test_cz_time_test_exemption(self, db_session, pid):
        """Czech §4: held > 3 years → cz_exempt_time_test = True."""
        txns = [
            make_txn("AAPL", "buy", 10, 100.0, date=date(2020, 1, 1), portfolio_id=pid),
            make_txn("AAPL", "sell", 10, 200.0, date=date(2024, 6, 1), portfolio_id=pid),
        ]
        for t in txns:
            db_session.add(t)
        db_session.commit()
        gains = _compute_capital_gains(txns)
        assert gains[0]["cz_exempt_time_test"] is True

    def test_cz_time_test_no_exemption(self, db_session, pid):
        """Held < 3 years → not exempt."""
        txns = [
            make_txn("AAPL", "buy", 10, 100.0, date=date(2024, 1, 1), portfolio_id=pid),
            make_txn("AAPL", "sell", 10, 200.0, date=date(2024, 6, 1), portfolio_id=pid),
        ]
        for t in txns:
            db_session.add(t)
        db_session.commit()
        gains = _compute_capital_gains(txns)
        assert gains[0]["cz_exempt_time_test"] is False

    def test_filter_by_tax_year(self, db_session, pid):
        """Only sell transactions in the given year are returned."""
        txns = [
            make_txn("AAPL", "buy", 10, 100.0, date=date(2023, 6, 1), portfolio_id=pid),
            make_txn("AAPL", "sell", 5, 150.0, date=date(2024, 3, 1), portfolio_id=pid),
            make_txn("AAPL", "sell", 5, 200.0, date=date(2025, 3, 1), portfolio_id=pid),
        ]
        for t in txns:
            db_session.add(t)
        db_session.commit()
        gains_2024 = _compute_capital_gains(txns, tax_year=2024)
        assert len(gains_2024) == 1
        gains_2025 = _compute_capital_gains(txns, tax_year=2025)
        assert len(gains_2025) == 1
        gains_all = _compute_capital_gains(txns)
        assert len(gains_all) == 2


def test_consume_fifo_clamps_residuals_at_epsilon():
    lots = [{"remaining": 1.0, "shares": 1.0, "price": 10.0}]
    matched = _consume_fifo(lots, 1.0 - LOT_EPSILON / 2)
    assert lots[0]["remaining"] == 0.0
    assert matched[0][1] == pytest.approx(1.0 - LOT_EPSILON / 2)


def test_consume_fifo_does_not_emit_dust_match():
    lots = [{"remaining": LOT_EPSILON / 2, "shares": 1.0, "price": 10.0}]
    assert _consume_fifo(lots, 1) == []


def test_realized_row_precision_and_tiny_basis_percentage():
    txns = [
        make_txn("DUST", "buy", 0.00000002, 100, date=date(2024, 1, 1), fx_to_czk=20),
        make_txn("DUST", "sell", 0.00000002, 200, date=date(2024, 2, 1), fx_to_czk=20),
    ]
    row = _compute_capital_gains(txns)[0]
    assert row["shares"] == 0.00000002
    assert row["cost_basis"] == 0.000002
    assert row["proceeds"] == 0.000004
    assert row["gain"] == 0.000002
    assert row["gain_pct"] is None


def test_split_adjusted_multi_lot_rows_reconcile_with_summary(
    db_session, pid, default_portfolio
):
    txns = [
        make_txn("SPLT", "buy", 1, 10.123456, date=date(2024, 1, 1), fx_to_czk=20, portfolio_id=pid),
        make_txn("SPLT", "buy", 2, 20.654321, date=date(2024, 2, 1), fx_to_czk=21, portfolio_id=pid),
        make_txn("SPLT", "split_close", 3, 1, date=date(2024, 3, 1), fx_to_czk=1, portfolio_id=pid),
        make_txn("SPLT", "split_open", 6, 1, date=date(2024, 3, 1), fx_to_czk=1, portfolio_id=pid),
        make_txn("SPLT", "sell", 6, 15.987654, date=date(2024, 4, 1), fx_to_czk=22, portfolio_id=pid),
    ]
    db_session.add_all(txns)
    db_session.commit()

    report = tax_report(year=2024, db=db_session, portfolio=default_portfolio)

    assert len(report["gains"]) == 2
    assert round(sum(item["gain"] for item in report["gains"]), 2) == report["summary"]["total_realized"]
    assert round(sum(item["gain_czk"] for item in report["gains"]), 2) == report["summary"]["total_realized_czk"]


def test_missing_trade_fx_remains_explicitly_incomplete(
    db_session, pid, default_portfolio
):
    db_session.add_all([
        make_txn("NOFX", "buy", 1, 10, date=date(2024, 1, 1), fx_to_czk=None, portfolio_id=pid),
        make_txn("NOFX", "sell", 1, 20, date=date(2024, 2, 1), fx_to_czk=22, portfolio_id=pid),
    ])
    db_session.commit()

    report = tax_report(year=2024, db=db_session, portfolio=default_portfolio)

    assert report["gains"][0]["cost_basis_czk"] is None
    assert report["gains"][0]["gain_czk"] is None
    assert report["summary"]["fx_complete"] is False


def test_tax_dividend_income_uses_paid_cash_and_historical_fx(db_session, pid, default_portfolio):
    dividend = make_txn("AAPL", "dividend", 10, 1.0, date=date(2024, 6, 1),
                        fx_to_czk=20, portfolio_id=pid)
    dividend.cash_amount = 170.0
    dividend.cash_currency = "CZK"
    db_session.add(dividend)
    db_session.commit()

    report = tax_report(year=2024, db=db_session, portfolio=default_portfolio)

    assert report["dividend_income"][0]["amount"] == pytest.approx(8.5)
    assert report["dividend_income"][0]["amount_czk"] == pytest.approx(170.0)
    assert report["summary"]["total_dividends"] == pytest.approx(8.5)
    assert report["summary"]["total_dividends_czk"] == pytest.approx(170.0)


class TestCzechTax:
    """Czech §4 exemption summary (value test, time test, 40M cap)."""

    def test_value_test_passed(self):
        """Gross proceeds <= 100k CZK → everything exempt."""
        gains = [
            {
                "sell_date": "2024-06-01",
                "gain_czk": 50_000.0,
                "proceeds_czk": 30_000.0,
                "cz_exempt_time_test": False,
            },
        ]
        years = _compute_czech_tax_by_year(gains)
        assert len(years) == 1
        assert years[0]["value_test_passed"] is True
        assert years[0]["taxable_total_czk"] == 0.0
        assert years[0]["exempt_total_czk"] == 50_000.0

    def test_value_test_failed_taxable(self):
        """Proceeds > 100k → non-exempt gains are taxable."""
        gains = [
            {
                "sell_date": "2024-06-01",
                "gain_czk": 200_000.0,
                "proceeds_czk": 500_000.0,
                "cz_exempt_time_test": False,
            },
        ]
        years = _compute_czech_tax_by_year(gains)
        assert years[0]["value_test_passed"] is False
        assert years[0]["taxable_total_czk"] == 200_000.0

    def test_time_test_exempt(self):
        """Time-test exempt gains are excluded from taxable."""
        gains = [
            {
                "sell_date": "2024-06-01",
                "gain_czk": 100_000.0,
                "proceeds_czk": 300_000.0,
                "cz_exempt_time_test": True,
            },
            {
                "sell_date": "2024-07-01",
                "gain_czk": 50_000.0,
                "proceeds_czk": 200_000.0,
                "cz_exempt_time_test": False,
            },
        ]
        years = _compute_czech_tax_by_year(gains)
        assert years[0]["value_test_passed"] is False
        assert years[0]["exempt_total_czk"] == 100_000.0  # time-test exempt
        assert years[0]["taxable_total_czk"] == 50_000.0

    def test_40m_cap_excess(self):
        """Time-test exemption capped at 40M CZK from 2024."""
        gains = [
            {
                "sell_date": "2024-06-01",
                "gain_czk": 50_000_000.0,
                "proceeds_czk": 200_000_000.0,
                "cz_exempt_time_test": True,
            },
        ]
        years = _compute_czech_tax_by_year(gains)
        assert years[0]["value_test_passed"] is False
        # Time-test exempt capped at 40M → 10M excess is taxable
        assert years[0]["exempt_total_czk"] == pytest.approx(40_000_000.0)
        assert years[0]["taxable_total_czk"] == pytest.approx(10_000_000.0)

    def test_multi_year_aggregation(self):
        """Gains across different years are grouped separately."""
        gains = [
            {
                "sell_date": "2023-06-01",
                "gain_czk": 10_000.0,
                "proceeds_czk": 50_000.0,
                "cz_exempt_time_test": True,
            },
            {
                "sell_date": "2024-06-01",
                "gain_czk": 200_000.0,
                "proceeds_czk": 500_000.0,
                "cz_exempt_time_test": False,
            },
        ]
        years = _compute_czech_tax_by_year(gains)
        assert len(years) == 2
        assert years[0]["tax_year"] == 2023
        assert years[1]["tax_year"] == 2024


def test_allocation_totals_returns_raw_values(db_session, pid, default_portfolio):
    # market_data.get_infos is patched directly (matching the pattern already used
    # by sector_breakdown's own holdings tests in test_currency_and_history.py) --
    # the shared `mock_yfinance` MockTicker has no .history(), which market_data's
    # _raw_info requires before trusting .info, so it can't be used for this.
    from unittest.mock import patch
    from routers.analytics import _allocation_totals
    from tests.helpers import make_txn

    db_session.add(make_txn("AAPL", "buy", 10, 150.0, portfolio_id=pid))
    db_session.commit()

    with patch("market_data.get_infos", return_value={
        "AAPL": {"currentPrice": 180.0, "currency": "USD", "sector": "Technology", "quoteType": "EQUITY"},
    }):
        raw = _allocation_totals(db_session, default_portfolio, "USD")
    # raw values are un-weighted market values (mock price 180 * 10 = 1800), not percentages
    assert raw["total_value"] > 0
    assert sum(raw["sectors"].values()) == pytest.approx(raw["total_value"], rel=0.01)
    # Technology sector from the mock info
    assert "Technology" in raw["sectors"]


def test_weighted_is_module_level_and_percentizes():
    from routers.analytics import _weighted
    out = _weighted({"A": 30.0, "B": 10.0})
    by_name = {r["name"]: r for r in out}
    assert by_name["A"]["weight"] == 75.0
    assert by_name["B"]["weight"] == 25.0
    assert out[0]["name"] == "A"  # sorted desc by value


@pytest.mark.parametrize(
    ("old_shares", "new_shares", "buy_price", "sell_price"),
    [
        (10, 5, 100.0, 220.0),   # 1-for-2 reverse split
        (5, 10, 200.0, 110.0),   # 2-for-1 forward split
    ],
)
def test_fifo_capital_gain_preserves_basis_across_stock_split(
    old_shares, new_shares, buy_price, sell_price
):
    txns = [
        make_txn("SPLT", "buy", old_shares, buy_price,
                 date=date(2024, 1, 1), fx_to_czk=1),
        make_txn("SPLT", "split_close", old_shares, buy_price,
                 date=date(2024, 6, 1), fx_to_czk=1),
        make_txn("SPLT", "split_open", new_shares,
                 buy_price * old_shares / new_shares,
                 date=date(2024, 6, 1), fx_to_czk=1),
        make_txn("SPLT", "sell", new_shares, sell_price,
                 date=date(2024, 7, 1), fx_to_czk=1),
    ]

    gains = _compute_capital_gains(txns)

    assert len(gains) == 1
    assert gains[0]["shares"] == pytest.approx(new_shares)
    assert gains[0]["cost_basis"] == pytest.approx(1000)
    assert gains[0]["proceeds"] == pytest.approx(1100)
    assert gains[0]["gain"] == pytest.approx(100)


def test_unrealized_lot_quantity_and_basis_follow_reverse_split():
    txns = [
        make_txn("SPLT", "buy", 10, 100, date=date(2024, 1, 1)),
        make_txn("SPLT", "split_close", 10, 100, date=date(2024, 6, 1)),
        make_txn("SPLT", "split_open", 5, 200, date=date(2024, 6, 1)),
    ]

    with patch("routers.analytics.market_data.get_infos", return_value={
        "SPLT": {"currentPrice": 220.0, "currency": "USD"},
    }):
        unrealized = _compute_unrealized_gains(txns)

    assert len(unrealized) == 1
    assert unrealized[0]["shares"] == pytest.approx(5)
    assert unrealized[0]["cost_basis"] == pytest.approx(1000)
    assert unrealized[0]["market_value"] == pytest.approx(1100)


def test_allocation_uses_post_split_share_count(db_session, pid, default_portfolio):
    from routers.analytics import _allocation_totals

    db_session.add_all([
        make_txn("SPLT", "buy", 10, 100, date=date(2024, 1, 1), portfolio_id=pid),
        make_txn("SPLT", "split_close", 10, 100, date=date(2024, 6, 1), portfolio_id=pid),
        make_txn("SPLT", "split_open", 5, 200, date=date(2024, 6, 1), portfolio_id=pid),
    ])
    db_session.commit()

    with patch("market_data.get_infos", return_value={
        "SPLT": {
            "currentPrice": 200.0,
            "currency": "USD",
            "sector": "Technology",
            "quoteType": "EQUITY",
        },
    }):
        raw = _allocation_totals(db_session, default_portfolio, "USD")

    assert raw["total_value"] == pytest.approx(1000)
    assert raw["sectors"]["Technology"] == pytest.approx(1000)
