"""Tests for broker integration: ticker normalization, split adjustment, corporate actions."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from models import BrokerConnection, Transaction
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


def _run_sync(db_session, pid, orders, dividends=None, fx_map=None):
    """Call sync_transactions with the network + yfinance bits patched out."""
    with patch("routers.broker._fetch_all_orders", return_value=orders), \
         patch("routers.broker._fetch_all_dividends", return_value=dividends or []), \
         patch("routers.broker._split_adjust", return_value=0), \
         patch("routers.broker._drop_corporate_action_pairs", return_value=0), \
         patch("routers.broker.bulk_fetch_fx", return_value=fx_map or {}):
        return sync_transactions(db=db_session, pid=pid, owner="default")


class TestSyncDedupe:
    """Sync must never re-import history that arrived via CSV import.

    Regression tests for the 2026-07 incident: the dedupe only looked at rows
    with source='t212_api', so syncing after a CSV import re-inserted the whole
    order history and doubled every position.
    """

    @pytest.fixture
    def connection(self, db_session, pid):
        conn = BrokerConnection(portfolio_id=pid, broker="trading212", api_key="k" * 20)
        db_session.add(conn)
        db_session.commit()
        return conn

    def _txn_count(self, db_session, pid):
        return db_session.query(Transaction).filter(Transaction.portfolio_id == pid).count()

    def test_skips_orders_matching_csv_rows(self, db_session, pid, connection):
        db_session.add(make_txn("AAPL", "buy", 10, 150.0, date=date(2024, 6, 1),
                                source=None, portfolio_id=pid))
        db_session.commit()
        res = _run_sync(db_session, pid, [_order("AAPL", "BUY", 10, 150.0, "2024-06-01")])
        assert res["imported_orders"] == 0
        assert self._txn_count(db_session, pid) == 1

    def test_skips_orders_matching_csv_rows_by_base_ticker(self, db_session, pid, connection):
        # CSV stores the raw export ticker (COPM); the API normalizes to COPM.L.
        db_session.add(make_txn("COPM", "sell", 3, 9.91, date=date(2024, 6, 1),
                                source=None, portfolio_id=pid))
        db_session.commit()
        res = _run_sync(db_session, pid, [_order("COPMl", "SELL", 3, 9.91, "2024-06-01")])
        assert res["imported_orders"] == 0
        assert self._txn_count(db_session, pid) == 1

    def test_skips_orders_older_than_latest_existing_trade(self, db_session, pid, connection):
        # An old order that doesn't key-match anything (different representation
        # after splits etc.) must still be skipped: history is already imported.
        db_session.add(make_txn("AAPL", "buy", 10, 150.0, date=date(2024, 6, 1),
                                source=None, portfolio_id=pid))
        db_session.commit()
        res = _run_sync(db_session, pid, [
            _order("MSFT", "BUY", 5, 300.0, "2024-01-05"),   # before latest → skip
            _order("NVDA", "BUY", 2, 120.0, "2024-06-02"),   # after latest → import
        ])
        assert res["imported_orders"] == 1
        tickers = {t.ticker for t in db_session.query(Transaction).all()}
        assert tickers == {"AAPL", "NVDA"}

    def test_first_sync_imports_full_history(self, db_session, pid, connection):
        res = _run_sync(db_session, pid, [
            _order("MSFT", "BUY", 5, 300.0, "2024-01-05"),
            _order("AAPL", "BUY", 10, 150.0, "2024-06-01"),
        ])
        assert res["imported_orders"] == 2

    def test_skips_dividends_matching_csv_rows(self, db_session, pid, connection):
        # CSV dividend: 0.4 shares @ 0.374/share = 0.1496 total. The API reports
        # gross 0.44/share × 0.4 qty × 0.85 net = the same 0.1496 total.
        db_session.add(make_txn("CRM", "dividend", 0.4, 0.374, date=date(2024, 6, 1),
                                source=None, portfolio_id=pid))
        db_session.commit()
        res = _run_sync(db_session, pid, [], dividends=[{
            "ticker": "CRM",
            "grossAmountPerShare": 0.44,
            "quantity": 0.4,
            "paidOn": "2024-06-01T00:00:00Z",
            "instrument": {"currency": "USD"},
        }])
        assert res["imported_dividends"] == 0
        assert self._txn_count(db_session, pid) == 1

    def test_new_trades_settle_in_czk(self, db_session, pid, connection):
        fx_map = {("USD", date(2024, 6, 2)): 25.0}
        res = _run_sync(db_session, pid,
                        [_order("AAPL", "BUY", 2, 100.0, "2024-06-02")], fx_map=fx_map)
        assert res["imported_orders"] == 1
        t = db_session.query(Transaction).one()
        assert t.fx_to_czk == 25.0
        assert t.cash_amount == 5000.0
        assert t.cash_currency == "CZK"
