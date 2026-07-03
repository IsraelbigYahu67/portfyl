"""Tests for analytics: tax report, FIFO lot matching, capital gains, Czech exemptions."""

from __future__ import annotations

from datetime import date

import pytest

from tests.helpers import make_txn
from routers.analytics import _compute_capital_gains, _compute_czech_tax_by_year


class TestCapitalGains:
    """FIFO lot matching for capital gains."""

    def test_no_sells(self, db_session, pid):
        txns = [make_txn("AAPL", "buy", 10, 150.0, date=date(2024, 1, 1), portfolio_id=pid)]
        for t in txns:
            db_session.add(t)
        db_session.commit()
        gains = _compute_capital_gains(txns)
        assert gains == []

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
