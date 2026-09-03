"""Tests for broker integration: ticker normalization, split adjustment, corporate actions."""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from models import BrokerConnection, Portfolio, Transaction
from routers.broker import (
    _normalize_t212_ticker,
    _CANONICAL_TICKER as _canonical_ticker,
    sync_transactions,
)
from tests.helpers import make_txn


class TestTickerNormalization:
    """Trading 212 → Yahoo Finance ticker mapping."""

    def test_us_stock_unchanged(self):
        """Plain US tickers pass through."""
        assert _normalize_t212_ticker("AAPL") == "AAPL"
        assert _normalize_t212_ticker("MSFT") == "MSFT"
        assert _normalize_t212_ticker("TSLA") == "TSLA"

    def test_suffix_stripped(self):
        """_US_EQ and _EQ suffixes are removed."""
        assert _normalize_t212_ticker("AAPL_US_EQ") == "AAPL"
        assert _normalize_t212_ticker("VWCE_EQ") == "VWCE"

    def test_exchange_suffix_lowercase(self):
        """Lowercase trailing letter → exchange suffix."""
        assert _normalize_t212_ticker("NVDd") == "NVD.DE"  # Xetra
        assert _normalize_t212_ticker("CSPXl") == "CSPX.L"  # London
        assert _normalize_t212_ticker("IWDAa") == "IWDA.AS"  # Amsterdam

    def test_ticker_rename(self):
        """Old/de-SPAC'd tickers are remapped."""
        assert _normalize_t212_ticker("FB") == "META"
        assert _normalize_t212_ticker("IPOE") == "SOFI"
        assert _normalize_t212_ticker("AGC") == "GRAB"

    def test_brk_special(self):
        """BRK_A → BRK-A (dash instead of underscore)."""
        assert _normalize_t212_ticker("BRK_A") == "BRK-A"
        assert _normalize_t212_ticker("BRK_B") == "BRK-B"

    def test_lse_ucits_etf(self):
        """Known LSE-listed UCITS ETFs map to .L suffix."""
        assert _normalize_t212_ticker("CSPX") == "CSPX.L"
        assert _normalize_t212_ticker("CNDX") == "CNDX.L"
        assert _normalize_t212_ticker("IITU") == "IITU.L"

    def test_empty_ticker(self):
        """Empty string returns empty."""
        assert _normalize_t212_ticker("") == ""

    def test_whitespace_stripped(self):
        """Leading/trailing whitespace is stripped."""
        assert _normalize_t212_ticker("  AAPL  ") == "AAPL"


class TestCanonicalTicker:
    """Regex check for canonical ticker shape."""

    def test_valid_tickers(self):
        assert bool(_canonical_ticker.match("AAPL"))
        assert bool(_canonical_ticker.match("BRK-B"))
        assert bool(_canonical_ticker.match("CSPX.L"))
        assert bool(_canonical_ticker.match("NVDA.DE"))

    def test_invalid_tickers(self):
        assert not _canonical_ticker.match("")
        assert not _canonical_ticker.match("abc")  # lowercase
        assert not _canonical_ticker.match("aAPL")  # mixed case wrong direction


def _order(ticker, side, qty, price, day, currency="USD", order_id="1"):
    """Minimal T212 order-history item as _fetch_all_orders returns it."""
    return {
        "order": {
            "id": order_id,
            "status": "FILLED",
            "ticker": ticker,
            "side": side,
            "filledQuantity": qty,
            "createdAt": f"{day}T10:00:00Z",
            "instrument": {"currency": currency, "name": ticker},
        },
        "fill": {"quantity": qty, "price": price, "filledAt": f"{day}T10:00:00Z"},
    }


def _run_sync(db_session, portfolio, orders, dividends=None, fx_map=None):
    """Call sync_transactions with the network + yfinance bits patched out.

    `sync_transactions` is a route handler: `portfolio` is the authorized
    Portfolio the require_portfolio dependency would have resolved, and
    `_context` is only the CSRF gate, which does not apply to a direct call."""
    with patch("routers.broker._fetch_all_orders", return_value=orders), \
         patch("routers.broker._fetch_all_dividends", return_value=dividends or []), \
         patch("routers.broker._split_adjust", return_value=0), \
         patch("routers.broker._drop_corporate_action_pairs", return_value=0), \
         patch("routers.broker.bulk_fetch_fx", return_value=fx_map or {}):
        return sync_transactions(db=db_session, portfolio=portfolio, _context=None)


class TestSyncDedupe:
    """Sync must never re-import history that arrived via CSV import.

    Regression tests for the 2026-07 incident: the dedupe only looked at rows
    with source='t212_api', so syncing after a CSV import re-inserted the whole
    order history and doubled every position.
    """

    @pytest.fixture
    def connection(self, db_session, default_portfolio):
        conn = BrokerConnection(workspace_id=default_portfolio.workspace_id,
                                portfolio_id=default_portfolio.id,
                                broker="trading212", api_key="k" * 20)
        db_session.add(conn)
        db_session.commit()
        return conn

    def _txn_count(self, db_session, pid):
        return db_session.query(Transaction).filter(Transaction.portfolio_id == pid).count()

    def test_skips_orders_matching_csv_rows(self, db_session, default_portfolio, pid, connection):
        db_session.add(make_txn("AAPL", "buy", 10, 150.0, date=date(2024, 6, 1),
                                source=None, portfolio_id=pid))
        db_session.commit()
        res = _run_sync(db_session, default_portfolio, [_order("AAPL", "BUY", 10, 150.0, "2024-06-01")])
        assert res["imported_orders"] == 0
        assert self._txn_count(db_session, pid) == 1

    def test_skips_orders_matching_csv_rows_by_base_ticker(self, db_session, default_portfolio, pid, connection):
        # CSV stores the raw export ticker (COPM); the API normalizes to COPM.L.
        db_session.add(make_txn("COPM", "sell", 3, 9.91, date=date(2024, 6, 1),
                                source=None, portfolio_id=pid))
        db_session.commit()
        res = _run_sync(db_session, default_portfolio, [_order("COPMl", "SELL", 3, 9.91, "2024-06-01")])
        assert res["imported_orders"] == 0
        assert self._txn_count(db_session, pid) == 1

    def test_date_cutoff_is_per_ticker_not_portfolio_wide(self, db_session, default_portfolio, pid, connection):
        # AAPL history exists through 2024-06-01: an old AAPL order that doesn't
        # key-match (representation drift after splits) is still skipped. MSFT
        # has no history at all — its old orders are genuinely new and must
        # import, not be dropped because *another* ticker has newer trades.
        db_session.add(make_txn("AAPL", "buy", 10, 150.0, date=date(2024, 6, 1),
                                source=None, portfolio_id=pid))
        db_session.commit()
        res = _run_sync(db_session, default_portfolio, [
            _order("AAPL", "BUY", 40, 37.5, "2024-01-05"),   # pre-split repr → skip
            _order("MSFT", "BUY", 5, 300.0, "2024-01-05"),   # never-seen ticker → import
            _order("NVDA", "BUY", 2, 120.0, "2024-06-02"),   # after cutoff → import
        ])
        assert res["imported_orders"] == 2
        tickers = {t.ticker for t in db_session.query(Transaction).all()}
        assert tickers == {"AAPL", "MSFT", "NVDA"}

    def test_date_cutoff_matches_base_ticker(self, db_session, default_portfolio, pid, connection):
        # CSV stores the raw export ticker (COPM); the API normalizes to COPM.L —
        # the per-ticker cutoff must treat them as the same instrument.
        db_session.add(make_txn("COPM", "buy", 3, 9.91, date=date(2024, 6, 1),
                                source=None, portfolio_id=pid))
        db_session.commit()
        res = _run_sync(db_session, default_portfolio, [
            _order("COPMl", "BUY", 7, 4.25, "2024-02-01"),   # old, drifted repr → skip
        ])
        assert res["imported_orders"] == 0
        assert self._txn_count(db_session, pid) == 1

    def test_dividend_cutoff_is_per_ticker(self, db_session, default_portfolio, pid, connection):
        # KO was never imported: its old dividends must come in even though
        # AAPL has newer trades in the same portfolio.
        db_session.add(make_txn("AAPL", "buy", 10, 150.0, date=date(2024, 6, 1),
                                source=None, portfolio_id=pid))
        db_session.commit()
        res = _run_sync(db_session, default_portfolio, [], dividends=[{
            "ticker": "KO",
            "grossAmountPerShare": 0.485,
            "quantity": 10,
            "paidOn": "2024-03-15T00:00:00Z",
            "instrument": {"currency": "USD"},
        }])
        assert res["imported_dividends"] == 1

    def test_first_sync_imports_full_history(self, db_session, default_portfolio, pid, connection):
        res = _run_sync(db_session, default_portfolio, [
            _order("MSFT", "BUY", 5, 300.0, "2024-01-05"),
            _order("AAPL", "BUY", 10, 150.0, "2024-06-01"),
        ])
        assert res["imported_orders"] == 2

    def test_full_t212_csv_blocks_covered_history_for_unseen_tickers(
        self, db_session, default_portfolio, pid, connection
    ):
        # A T212 replacement export is authoritative for the whole account,
        # not only for tickers present in it. A later manual API sync must not
        # resurrect older API-only history or same-day rows behind its cutoff.
        db_session.add(make_txn("AAPL", "buy", 10, 150.0, date=date(2024, 6, 1),
                                source="t212_csv", portfolio_id=pid))
        db_session.commit()

        res = _run_sync(db_session, default_portfolio, [
            _order("MSFT", "BUY", 5, 300.0, "2024-01-05"),
            _order("AVGO", "BUY", 1, 1400.0, "2024-06-01"),
        ])

        assert res["imported_orders"] == 0
        assert self._txn_count(db_session, pid) == 1

    def test_full_t212_csv_allows_orders_after_its_coverage_date(
        self, db_session, default_portfolio, pid, connection
    ):
        db_session.add(make_txn("AAPL", "buy", 10, 150.0, date=date(2024, 6, 1),
                                source="t212_csv", portfolio_id=pid))
        db_session.commit()

        res = _run_sync(db_session, default_portfolio, [
            _order("MSFT", "BUY", 5, 300.0, "2024-06-02"),
        ])

        assert res["imported_orders"] == 1
        assert self._txn_count(db_session, pid) == 2

    def test_precise_snapshot_timestamp_allows_later_same_day_order(
        self, db_session, default_portfolio, pid, connection
    ):
        portfolio = db_session.query(Portfolio).filter(Portfolio.id == pid).one()
        portfolio.t212_csv_covered_through = datetime(
            2024, 6, 1, 8, 0, tzinfo=timezone.utc
        )
        db_session.add(make_txn("AAPL", "buy", 10, 150.0, date=date(2024, 6, 1),
                                source="t212_csv", portfolio_id=pid))
        db_session.commit()

        res = _run_sync(db_session, default_portfolio, [
            _order("MSFT", "BUY", 5, 300.0, "2024-06-01"),
        ])

        assert res["imported_orders"] == 1
        assert self._txn_count(db_session, pid) == 2

    def test_skips_dividends_matching_csv_rows(self, db_session, default_portfolio, pid, connection):
        # CSV dividend: 0.4 shares @ 0.374/share = 0.1496 total. The API reports
        # gross 0.44/share × 0.4 qty × 0.85 net = the same 0.1496 total.
        db_session.add(make_txn("CRM", "dividend", 0.4, 0.374, date=date(2024, 6, 1),
                                source=None, portfolio_id=pid))
        db_session.commit()
        res = _run_sync(db_session, default_portfolio, [], dividends=[{
            "ticker": "CRM",
            "grossAmountPerShare": 0.44,
            "quantity": 0.4,
            "paidOn": "2024-06-01T00:00:00Z",
            "instrument": {"currency": "USD"},
        }])
        assert res["imported_dividends"] == 0
        assert self._txn_count(db_session, pid) == 1

    def test_new_trades_settle_in_czk(self, db_session, default_portfolio, pid, connection):
        fx_map = {("USD", date(2024, 6, 2)): 25.0}
        res = _run_sync(db_session, default_portfolio,
                        [_order("AAPL", "BUY", 2, 100.0, "2024-06-02")], fx_map=fx_map)
        assert res["imported_orders"] == 1
        t = db_session.query(Transaction).one()
        assert t.fx_to_czk == 25.0
        assert t.cash_amount == 5000.0
        assert t.cash_currency == "CZK"
