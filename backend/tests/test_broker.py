"""Tests for broker integration: ticker normalization, split adjustment, corporate actions."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from models import (
    BrokerBalance, BrokerConnection, BrokerPosition, BrokerSyncRun, Portfolio, Transaction,
)
from routers.broker import (
    _normalize_t212_ticker,
    _CANONICAL_TICKER as _canonical_ticker,
    _fetch_account_summary,
    connect,
    disconnect,
    get_history_status,
    get_positions,
    get_status,
    sync_transactions,
)
from tests.fixtures.t212 import t212_position
from tests.helpers import make_txn


def test_fetch_account_summary_calls_expected_t212_endpoint():
    response = MagicMock(status_code=200)
    response.json.return_value = {"currency": "CZK", "cash": {"availableToTrade": 1}}

    with patch("routers.broker.httpx.get", return_value=response) as get:
        result = _fetch_account_summary("https://live.trading212.com/api/v0", {"Authorization": "x"})

    get.assert_called_once_with(
        "https://live.trading212.com/api/v0/equity/account/summary",
        headers={"Authorization": "x"},
        timeout=15,
    )
    response.raise_for_status.assert_called_once_with()
    assert result["currency"] == "CZK"


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


def _run_sync(
    db_session, portfolio, orders, dividends=None, fx_map=None, summary=None,
    summary_error=None, positions=None, positions_error=None,
):
    """Call sync_transactions with the network + yfinance bits patched out.

    `sync_transactions` is a route handler: `portfolio` is the authorized
    Portfolio the require_portfolio dependency would have resolved, and
    `_context` is only the CSRF gate, which does not apply to a direct call."""
    account_summary = summary or {
        "cash": {"availableToTrade": 0, "inPies": 0, "reservedForOrders": 0},
        "currency": "CZK",
        "id": 1,
        "investments": {
            "currentValue": 0,
            "realizedProfitLoss": 0,
            "totalCost": 0,
            "unrealizedProfitLoss": 0,
        },
        "totalValue": 0,
    }
    summary_patch = patch(
        "routers.broker._fetch_account_summary",
        return_value=account_summary,
        side_effect=summary_error,
    )
    positions_patch = patch(
        "t212_sync._fetch_positions",
        return_value=positions if positions is not None else [],
        side_effect=positions_error,
    )
    with summary_patch, positions_patch, \
         patch("routers.broker._fetch_all_orders", return_value=orders), \
         patch("routers.broker._fetch_all_dividends", return_value=dividends or []), \
         patch("routers.broker._split_adjust", return_value=0), \
         patch("routers.broker._drop_corporate_action_pairs", return_value=0), \
         patch("routers.broker.bulk_fetch_fx", return_value=fx_map or {}):
        return sync_transactions(db=db_session, portfolio=portfolio, _context=None)


def test_sync_persists_current_cash_snapshot_without_cash_transactions(
    db_session, default_portfolio
):
    conn = BrokerConnection(
        workspace_id=default_portfolio.workspace_id,
        portfolio_id=default_portfolio.id,
        broker="trading212",
        api_key="k" * 20,
    )
    db_session.add(conn)
    db_session.commit()

    result = _run_sync(
        db_session,
        default_portfolio,
        [],
        summary={
            "cash": {
                "availableToTrade": 1000.0,
                "inPies": 300.0,
                "reservedForOrders": 82.17,
            },
            "currency": "CZK",
            "id": 123456,
            "investments": {
                "currentValue": 60000.0,
                "realizedProfitLoss": 500.0,
                "totalCost": 55000.0,
                "unrealizedProfitLoss": 4500.0,
            },
            "totalValue": 61382.17,
        },
    )

    balance = db_session.query(BrokerBalance).one()
    assert balance.workspace_id == default_portfolio.workspace_id
    assert balance.portfolio_id == default_portfolio.id
    assert balance.broker == "trading212"
    assert balance.base_currency == "CZK"
    assert balance.cash == pytest.approx(1382.17)
    assert balance.stock == pytest.approx(60000.0)
    assert balance.net_liquidation == pytest.approx(61382.17)
    assert result["cash_updated"] is True
    assert db_session.query(Transaction).count() == 0


def test_sync_keeps_last_cash_snapshot_when_summary_fetch_fails(
    db_session, default_portfolio
):
    db_session.add_all([
        BrokerConnection(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212",
            api_key="k" * 20,
        ),
        BrokerBalance(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212",
            base_currency="CZK",
            cash=777.0,
            cash_by_currency='{"CZK": 777.0}',
            as_of=date(2026, 9, 19),
        ),
    ])
    db_session.commit()

    result = _run_sync(
        db_session,
        default_portfolio,
        [],
        summary_error=RuntimeError("temporary upstream error"),
    )

    balance = db_session.query(BrokerBalance).one()
    assert balance.cash == pytest.approx(777.0)
    assert balance.as_of == date(2026, 9, 19)
    assert result["cash_updated"] is False
    assert result["cash_error"] == "Cash summary fetch failed: temporary upstream error"


def test_disconnect_removes_current_cash_snapshot(db_session, default_portfolio):
    db_session.add_all([
        BrokerConnection(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212",
            api_key="k" * 20,
        ),
        BrokerBalance(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212",
            base_currency="CZK",
            cash=777.0,
        ),
    ])
    db_session.commit()

    disconnect(db=db_session, portfolio=default_portfolio, _context=None)

    assert db_session.query(BrokerConnection).count() == 0
    assert db_session.query(BrokerBalance).count() == 0


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


class TestStatusDecryptFailure:
    """Regression: a stored connection whose secret can't be decrypted (e.g. a
    misconfigured/missing PORTFYL_LOCAL_SECRET_KEY, or a wrong-key mismatch)
    must degrade to a 'needs attention' status, not crash the whole
    /trading212/status call -- a raised exception here has no exception
    handler, so it 500s with no JSON `detail`, and the Settings > Connections
    page renders nothing but a generic 'We couldn't load this data.' with no
    way to reach the Disconnect button and recover."""

    @pytest.fixture
    def connection(self, db_session, default_portfolio):
        conn = BrokerConnection(workspace_id=default_portfolio.workspace_id,
                                portfolio_id=default_portfolio.id,
                                broker="trading212", api_key="k" * 20)
        db_session.add(conn)
        db_session.commit()
        return conn

    def test_status_degrades_instead_of_raising(self, db_session, default_portfolio, connection):
        with patch("models.get_secret_cipher", side_effect=RuntimeError("PORTFYL_LOCAL_SECRET_KEY is required")):
            result = get_status(db=db_session, portfolio=default_portfolio)

        assert result["connected"] is True
        assert result["needs_attention"] is True
        assert result["api_key_preview"] is None
        assert result["last_error"]


class TestSyncPersistsPositionsSnapshot:
    """T212 snapshot-first sync plan (2026-09-20), Task 2: sync fetches
    positions alongside the account summary, independently of order/dividend
    history import."""

    @pytest.fixture
    def connection(self, db_session, default_portfolio):
        conn = BrokerConnection(workspace_id=default_portfolio.workspace_id,
                                portfolio_id=default_portfolio.id,
                                broker="trading212", api_key="k" * 20)
        db_session.add(conn)
        db_session.commit()
        return conn

    def test_sync_persists_positions_and_reports_updated(
        self, db_session, default_portfolio, connection
    ):
        result = _run_sync(
            db_session, default_portfolio, [],
            positions=[t212_position(ticker="AAPL_US_EQ", quantity=10.0, averagePrice=150.0)],
        )
        assert result["positions_updated"] is True
        assert result["positions_error"] is None
        row = db_session.query(BrokerPosition).one()
        assert row.ticker == "AAPL"
        assert row.quantity == 10.0

    def test_positions_failure_does_not_block_summary_or_orders(
        self, db_session, default_portfolio, connection
    ):
        result = _run_sync(
            db_session, default_portfolio,
            [_order("MSFT", "BUY", 5, 300.0, "2024-06-02")],
            positions_error=RuntimeError("positions endpoint down"),
        )
        assert result["positions_updated"] is False
        assert result["positions_error"] == "Positions fetch failed: positions endpoint down"
        assert result["cash_updated"] is True
        assert result["imported_orders"] == 1
        assert db_session.query(BrokerPosition).count() == 0

    def test_summary_failure_does_not_block_positions(
        self, db_session, default_portfolio, connection
    ):
        result = _run_sync(
            db_session, default_portfolio, [],
            positions=[t212_position(ticker="AAPL_US_EQ")],
            summary_error=RuntimeError("summary down"),
        )
        assert result["cash_updated"] is False
        assert result["positions_updated"] is True
        assert db_session.query(BrokerPosition).count() == 1

    def test_sync_replaces_stale_positions(self, db_session, default_portfolio, connection):
        _run_sync(db_session, default_portfolio, [],
                  positions=[t212_position(ticker="AAPL_US_EQ")])
        _run_sync(db_session, default_portfolio, [],
                  positions=[t212_position(ticker="MSFT_US_EQ")])
        tickers = {r.ticker for r in db_session.query(BrokerPosition).all()}
        assert tickers == {"MSFT"}

    def test_sync_persists_expanded_balance_components(
        self, db_session, default_portfolio, connection
    ):
        result = _run_sync(
            db_session, default_portfolio, [],
            summary={
                "cash": {"availableToTrade": 1000.0, "inPies": 300.0, "reservedForOrders": 82.17},
                "currency": "CZK",
                "investments": {
                    "currentValue": 60000.0,
                    "totalCost": 55000.0,
                    "unrealizedProfitLoss": 4500.0,
                    "realizedProfitLoss": 500.0,
                },
                "totalValue": 61382.17,
            },
        )
        assert result["cash_updated"] is True
        balance = db_session.query(BrokerBalance).one()
        assert balance.cash_available == 1000.0
        assert balance.cash_in_pies == 300.0
        assert balance.cash_reserved == pytest.approx(82.17)
        assert balance.stock_total_cost == 55000.0
        assert balance.stock_unrealized_pnl == 4500.0
        assert balance.broker_realized_pnl == 500.0


class TestDisconnectAndReconnectClearPositions:
    def test_disconnect_removes_positions_snapshot(self, db_session, default_portfolio):
        db_session.add_all([
            BrokerConnection(workspace_id=default_portfolio.workspace_id,
                              portfolio_id=default_portfolio.id,
                              broker="trading212", api_key="k" * 20),
            BrokerPosition(
                workspace_id=default_portfolio.workspace_id,
                portfolio_id=default_portfolio.id,
                broker="trading212",
                provider_ticker="AAPL_US_EQ",
                ticker="AAPL",
                quantity=1.0,
                avg_price=100.0,
                as_of=datetime.now(timezone.utc),
            ),
        ])
        db_session.commit()

        disconnect(db=db_session, portfolio=default_portfolio, _context=None)

        assert db_session.query(BrokerPosition).count() == 0

    def test_reconnect_clears_previous_positions(self, db_session, default_portfolio):
        db_session.add(BrokerPosition(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212",
            provider_ticker="AAPL_US_EQ",
            ticker="AAPL",
            quantity=1.0,
            avg_price=100.0,
            as_of=datetime.now(timezone.utc),
        ))
        db_session.commit()

        info_response = MagicMock(status_code=200)
        with patch("routers.broker.httpx.get", return_value=info_response):
            connect(
                payload={"api_key": "new-key-value-1234567890"},
                db=db_session,
                portfolio=default_portfolio,
                _context=None,
            )

        assert db_session.query(BrokerPosition).count() == 0


class TestGetPositionsEndpoint:
    @pytest.fixture
    def connection(self, db_session, default_portfolio):
        conn = BrokerConnection(workspace_id=default_portfolio.workspace_id,
                                portfolio_id=default_portfolio.id,
                                broker="trading212", api_key="k" * 20)
        db_session.add(conn)
        db_session.commit()
        return conn

    def test_not_connected_is_unavailable(self, db_session, default_portfolio):
        result = get_positions(db=db_session, portfolio=default_portfolio)
        assert result == {"connected": False, "status": "unavailable", "as_of": None, "positions": []}

    def test_connected_but_never_synced_is_unavailable(self, db_session, default_portfolio, connection):
        result = get_positions(db=db_session, portfolio=default_portfolio)
        assert result["connected"] is True
        assert result["status"] == "unavailable"
        assert result["positions"] == []

    def test_fresh_snapshot_returns_positions_with_native_values(
        self, db_session, default_portfolio, connection
    ):
        db_session.add(BrokerPosition(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212",
            provider_ticker="AAPL_US_EQ",
            ticker="AAPL",
            quantity=10.0,
            avg_price=150.0,
            current_price=175.0,
            ppl=250.0,
            as_of=datetime.now(timezone.utc),
        ))
        db_session.commit()

        result = get_positions(currency="USD", db=db_session, portfolio=default_portfolio)

        assert result["connected"] is True
        assert result["status"] == "fresh"
        assert len(result["positions"]) == 1
        pos = result["positions"][0]
        assert pos["ticker"] == "AAPL"
        # No ledger row for AAPL exists, so currency is unknown and values
        # are reported unconverted (native face value).
        assert pos["currency"] is None
        assert pos["market_value"] == pytest.approx(1750.0)
        assert pos["cost_basis"] == pytest.approx(1500.0)
        assert pos["pnl"] == pytest.approx(250.0)

    def test_stale_snapshot_reported_as_stale(self, db_session, default_portfolio, connection):
        db_session.add(BrokerPosition(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212",
            provider_ticker="AAPL_US_EQ",
            ticker="AAPL",
            quantity=10.0,
            avg_price=150.0,
            as_of=datetime.now(timezone.utc) - timedelta(hours=26),
        ))
        db_session.commit()

        result = get_positions(db=db_session, portfolio=default_portfolio)
        assert result["status"] == "stale"
        assert len(result["positions"]) == 1

    def test_derives_currency_from_latest_ledger_row(self, db_session, default_portfolio, pid, connection):
        db_session.add(make_txn("AAPL", "buy", 5, 140.0, date=date(2024, 1, 1),
                                currency="USD", portfolio_id=pid))
        db_session.add(BrokerPosition(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212",
            provider_ticker="AAPL_US_EQ",
            ticker="AAPL",
            quantity=10.0,
            avg_price=150.0,
            current_price=175.0,
            as_of=datetime.now(timezone.utc),
        ))
        db_session.commit()

        result = get_positions(currency="USD", db=db_session, portfolio=default_portfolio)
        assert result["positions"][0]["currency"] == "USD"
        # Same currency in and out: no FX distortion.
        assert result["positions"][0]["market_value"] == pytest.approx(1750.0)


class TestSyncStartsHistoryRun:
    """T212 snapshot-first sync plan (2026-09-20), Task 3: sync_transactions
    starts (or returns the already-active) resumable history run alongside
    its existing full fetch-and-import behavior."""

    @pytest.fixture
    def connection(self, db_session, default_portfolio):
        conn = BrokerConnection(workspace_id=default_portfolio.workspace_id,
                                portfolio_id=default_portfolio.id,
                                broker="trading212", api_key="k" * 20)
        db_session.add(conn)
        db_session.commit()
        return conn

    def test_sync_creates_a_run_and_reports_it(self, db_session, default_portfolio, connection):
        result = _run_sync(db_session, default_portfolio, [])
        assert result["history_status"] == "pending"
        run = db_session.query(BrokerSyncRun).one()
        assert result["history_run_id"] == str(run.public_id)
        assert run.connection_id == connection.id
        assert run.credential_generation == connection.credential_generation

    def test_repeated_sync_returns_the_same_run(self, db_session, default_portfolio, connection):
        first = _run_sync(db_session, default_portfolio, [])
        second = _run_sync(db_session, default_portfolio, [])
        assert first["history_run_id"] == second["history_run_id"]
        assert db_session.query(BrokerSyncRun).count() == 1


class TestConnectFencesActiveRuns:
    def test_rotating_credentials_increments_generation_and_cancels_active_run(
        self, db_session, default_portfolio
    ):
        conn = BrokerConnection(workspace_id=default_portfolio.workspace_id,
                                portfolio_id=default_portfolio.id,
                                broker="trading212", api_key="old-key" * 3)
        db_session.add(conn)
        db_session.commit()
        db_session.refresh(conn)
        original_generation = conn.credential_generation
        run = BrokerSyncRun(
            workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
            connection_id=conn.id, broker="trading212",
            credential_generation=original_generation, mode="incremental", state="fetching",
        )
        db_session.add(run)
        db_session.commit()

        info_response = MagicMock(status_code=200)
        with patch("routers.broker.httpx.get", return_value=info_response):
            connect(
                payload={"api_key": "new-key-value-1234567890"},
                db=db_session, portfolio=default_portfolio, _context=None,
            )

        db_session.refresh(conn)
        db_session.refresh(run)
        assert conn.credential_generation == original_generation + 1
        assert run.state == "cancelled"

    def test_fresh_connect_starts_at_generation_one(self, db_session, default_portfolio):
        info_response = MagicMock(status_code=200)
        with patch("routers.broker.httpx.get", return_value=info_response):
            connect(
                payload={"api_key": "brand-new-key-1234567890"},
                db=db_session, portfolio=default_portfolio, _context=None,
            )
        conn = db_session.query(BrokerConnection).one()
        assert conn.credential_generation == 1

    def test_completed_run_is_not_cancelled_by_rotation(self, db_session, default_portfolio):
        conn = BrokerConnection(workspace_id=default_portfolio.workspace_id,
                                portfolio_id=default_portfolio.id,
                                broker="trading212", api_key="old-key" * 3)
        db_session.add(conn)
        db_session.commit()
        db_session.refresh(conn)
        run = BrokerSyncRun(
            workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
            connection_id=conn.id, broker="trading212",
            credential_generation=conn.credential_generation, mode="incremental", state="completed",
        )
        db_session.add(run)
        db_session.commit()

        info_response = MagicMock(status_code=200)
        with patch("routers.broker.httpx.get", return_value=info_response):
            connect(
                payload={"api_key": "new-key-value-1234567890"},
                db=db_session, portfolio=default_portfolio, _context=None,
            )

        db_session.refresh(run)
        assert run.state == "completed"


class TestGetHistoryStatusEndpoint:
    def test_not_connected(self, db_session, default_portfolio):
        result = get_history_status(db=db_session, portfolio=default_portfolio)
        assert result == {"connected": False, "run": None}

    def test_connected_no_run_yet(self, db_session, default_portfolio):
        db_session.add(BrokerConnection(workspace_id=default_portfolio.workspace_id,
                                        portfolio_id=default_portfolio.id,
                                        broker="trading212", api_key="k" * 20))
        db_session.commit()
        result = get_history_status(db=db_session, portfolio=default_portfolio)
        assert result == {"connected": True, "run": None}

    def test_reports_the_most_recent_run(self, db_session, default_portfolio):
        conn = BrokerConnection(workspace_id=default_portfolio.workspace_id,
                                portfolio_id=default_portfolio.id,
                                broker="trading212", api_key="k" * 20)
        db_session.add(conn)
        db_session.commit()
        db_session.refresh(conn)
        run = BrokerSyncRun(
            workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
            connection_id=conn.id, broker="trading212",
            credential_generation=conn.credential_generation, mode="incremental",
            state="fetching", orders_loaded=5, dividends_loaded=2, dividends_complete=True,
        )
        db_session.add(run)
        db_session.commit()

        result = get_history_status(db=db_session, portfolio=default_portfolio)
        assert result["connected"] is True
        assert result["run"]["id"] == str(run.public_id)
        assert result["run"]["state"] == "fetching"
        assert result["run"]["complete"] is False
        assert result["run"]["orders_loaded"] == 5
        assert result["run"]["dividends_complete"] is True
