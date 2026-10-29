"""Tests for broker integration: ticker normalization, split adjustment, corporate actions."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
import t212_sync

from account_identity import account_fingerprint
from models import (
    AuditLog, BrokerBalance, BrokerConnection, BrokerPosition, BrokerSyncRun,
    OptionsTrade, Portfolio, Transaction, Workspace,
)
from routers.broker import (
    _fetch_account_summary,
    connect,
    disconnect,
    get_history_status,
    get_positions,
    get_status,
    retry_history,
    sync_transactions,
)
from tests.fixtures.t212 import t212_position
from tests.helpers import make_txn

_normalize_t212_ticker = t212_sync._normalize_t212_ticker
_canonical_ticker = t212_sync._CANONICAL_TICKER


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


def _account_response(account_id=1, status_code=200):
    response = MagicMock(status_code=status_code)
    response.json.return_value = {"id": account_id}
    return response


def _run_sync(
    db_session, portfolio, _orders=None, summary=None,
    summary_error=None, positions=None, positions_error=None,
):
    """Call the snapshot-first sync route with provider requests patched out.

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
    account_summary.setdefault("id", 1)
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
    with summary_patch, positions_patch:
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
    assert result["snapshot"]["cash_updated"] is True
    assert db_session.query(Transaction).count() == 0


def test_sync_keeps_last_cash_snapshot_when_summary_fetch_fails(
    db_session, default_portfolio
):
    fingerprint = account_fingerprint(
        broker="trading212", environment="live", provider_account_id=1,
    )
    default_portfolio.t212_account_fingerprint = fingerprint
    db_session.add_all([
        BrokerConnection(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212",
            api_key="k" * 20,
            account_fingerprint=fingerprint,
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
    assert result["snapshot"]["cash_updated"] is False
    assert result["snapshot"]["cash_error"] == "Trading 212 account summary could not be refreshed."


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
        fingerprint = account_fingerprint(
            broker="trading212", environment="live", provider_account_id=1,
        )
        default_portfolio.t212_account_fingerprint = fingerprint
        conn = BrokerConnection(workspace_id=default_portfolio.workspace_id,
                                portfolio_id=default_portfolio.id,
                                broker="trading212", api_key="k" * 20,
                                account_fingerprint=fingerprint)
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
        assert result["snapshot"]["positions_updated"] is True
        assert result["snapshot"]["positions_error"] is None
        row = db_session.query(BrokerPosition).one()
        assert row.ticker == "AAPL"
        assert row.quantity == 10.0

    def test_positions_failure_does_not_block_summary_or_orders(
        self, db_session, default_portfolio, connection
    ):
        result = _run_sync(
            db_session, default_portfolio, [],
            positions_error=RuntimeError("positions endpoint down"),
        )
        assert result["snapshot"]["positions_updated"] is False
        assert result["snapshot"]["positions_error"] == "Trading 212 positions could not be refreshed."
        assert result["snapshot"]["cash_updated"] is True
        assert result["history"]["status"] == "pending"
        assert db_session.query(BrokerPosition).count() == 0

    def test_summary_failure_does_not_block_positions(
        self, db_session, default_portfolio, connection
    ):
        result = _run_sync(
            db_session, default_portfolio, [],
            positions=[t212_position(ticker="AAPL_US_EQ")],
            summary_error=RuntimeError("summary down"),
        )
        assert result["snapshot"]["cash_updated"] is False
        assert result["snapshot"]["positions_updated"] is True
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
        assert result["snapshot"]["cash_updated"] is True
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

    def test_same_account_reconnect_preserves_positions_and_ledger(
        self, db_session, default_portfolio
    ):
        fingerprint = account_fingerprint(
            broker="trading212", environment="live", provider_account_id=1,
        )
        default_portfolio.t212_account_fingerprint = fingerprint
        snapshot_at = datetime.now(timezone.utc)
        connection = BrokerConnection(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212",
            api_key="old-key-value-1234567890",
            environment="live",
            account_fingerprint=fingerprint,
            positions_snapshot_at=snapshot_at,
        )
        db_session.add_all([
            connection,
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
            make_txn(
                ticker="AAPL", date=date(2024, 1, 1),
                portfolio_id=default_portfolio.id,
            ),
        ])
        db_session.commit()

        with patch("routers.broker.httpx.get", return_value=_account_response(1)):
            connect(
                payload={"api_key": "new-key-value-1234567890"},
                db=db_session,
                portfolio=default_portfolio,
                _context=None,
            )

        assert db_session.query(BrokerPosition).count() == 1
        assert db_session.query(Transaction).count() == 1
        db_session.refresh(connection)
        assert connection.positions_snapshot_at == snapshot_at.replace(tzinfo=None)


class TestDemoCleanupOnConnect:
    @staticmethod
    def _connect(db_session, portfolio):
        with patch("routers.broker.httpx.get", return_value=_account_response(101)):
            connect(
                payload={"api_key": "new-key-value-1234567890"},
                db=db_session, portfolio=portfolio, _context=None,
            )

    def test_removes_demo_rows_but_keeps_real_ones_and_renames(
        self, db_session, default_portfolio
    ):
        default_portfolio.name = "Portfyl demo"
        db_session.add_all([
            make_txn(ticker="AAPL", date=date(2025, 1, 2),
                     portfolio_id=default_portfolio.id, source="demo"),
            make_txn(ticker="MSFT", date=date(2025, 2, 3),
                     portfolio_id=default_portfolio.id, source="demo"),
            make_txn(ticker="VWCE", date=date(2026, 1, 19),
                     portfolio_id=default_portfolio.id, source="t212_api"),
            make_txn(ticker="CEZ", date=date(2026, 1, 20),
                     portfolio_id=default_portfolio.id, source="manual"),
        ])
        db_session.commit()

        self._connect(db_session, default_portfolio)

        remaining = {t.ticker for t in db_session.query(Transaction).all()}
        assert remaining == {"VWCE", "CEZ"}
        db_session.refresh(default_portfolio)
        assert default_portfolio.name == "Trading 212"
        assert db_session.query(BrokerConnection).count() == 1

    def test_keeps_custom_portfolio_name(self, db_session, default_portfolio):
        db_session.add(make_txn(
            ticker="AAPL", date=date(2025, 1, 2),
            portfolio_id=default_portfolio.id, source="demo",
        ))
        db_session.commit()

        self._connect(db_session, default_portfolio)

        db_session.refresh(default_portfolio)
        assert default_portfolio.name == "Default"
        assert db_session.query(Transaction).count() == 0

    def test_removes_separate_pristine_demo_portfolio(
        self, db_session, default_portfolio, test_workspace
    ):
        demo = Portfolio(
            workspace_id=test_workspace.id, name="Portfyl demo", is_default=True,
        )
        default_portfolio.is_default = False
        db_session.add(demo)
        db_session.commit()
        db_session.add(make_txn(
            ticker="AAPL", date=date(2025, 1, 2), portfolio_id=demo.id, source="demo",
        ))
        db_session.commit()

        self._connect(db_session, default_portfolio)

        names = [p.name for p in db_session.query(Portfolio).all()]
        assert names == ["Default"]
        db_session.refresh(default_portfolio)
        assert default_portfolio.is_default is True
        assert db_session.query(Transaction).count() == 0

    def test_keeps_demo_named_portfolio_that_holds_real_data(
        self, db_session, default_portfolio, test_workspace
    ):
        other = Portfolio(workspace_id=test_workspace.id, name="Portfyl demo")
        db_session.add(other)
        db_session.commit()
        db_session.add_all([
            make_txn(ticker="AAPL", date=date(2025, 1, 2),
                     portfolio_id=other.id, source="demo"),
            make_txn(ticker="MSFT", date=date(2025, 1, 3),
                     portfolio_id=other.id, source="manual"),
        ])
        db_session.commit()

        self._connect(db_session, default_portfolio)

        assert db_session.query(Portfolio).count() == 2
        assert db_session.query(Transaction).count() == 2

    def test_keeps_demo_portfolio_with_other_user_data(
        self, db_session, default_portfolio, test_workspace
    ):
        demo = Portfolio(workspace_id=test_workspace.id, name="Portfyl demo")
        db_session.add(demo)
        db_session.commit()
        db_session.add_all([
            make_txn(ticker="AAPL", date=date(2025, 1, 2),
                     portfolio_id=demo.id, source="demo"),
            OptionsTrade(
                workspace_id=test_workspace.id, portfolio_id=demo.id,
                underlying="AAPL", strike=200.0, expiry=date(2026, 12, 18),
                put_call="P", quantity=1, open_price=3.5,
                open_date=date(2026, 9, 1), status="open",
            ),
        ])
        db_session.commit()

        self._connect(db_session, default_portfolio)

        assert db_session.query(Portfolio).count() == 2
        assert db_session.query(OptionsTrade).count() == 1

    def test_leaves_other_workspaces_untouched(
        self, db_session, default_portfolio, test_workspace
    ):
        other_ws = Workspace(name="Someone else")
        db_session.add(other_ws)
        db_session.flush()
        foreign_demo = Portfolio(workspace_id=other_ws.id, name="Portfyl demo")
        db_session.add(foreign_demo)
        db_session.flush()
        db_session.add_all([
            make_txn(ticker="AAPL", date=date(2025, 1, 2), source="demo",
                     portfolio_id=foreign_demo.id, workspace_id=other_ws.id),
            make_txn(ticker="MSFT", date=date(2025, 1, 2), source="demo",
                     portfolio_id=default_portfolio.id),
        ])
        db_session.commit()

        self._connect(db_session, default_portfolio)

        foreign = db_session.query(Transaction).filter(
            Transaction.workspace_id == other_ws.id
        ).all()
        assert [t.ticker for t in foreign] == ["AAPL"]
        assert db_session.get(Portfolio, foreign_demo.id) is not None
        assert db_session.query(Transaction).filter(
            Transaction.workspace_id == test_workspace.id
        ).count() == 0

    def test_failed_connect_rolls_back_purge(self, db_session, default_portfolio):
        default_portfolio.name = "Portfyl demo"
        db_session.add(make_txn(
            ticker="AAPL", date=date(2025, 1, 2),
            portfolio_id=default_portfolio.id, source="demo",
        ))
        db_session.commit()

        with patch("routers.broker.record_audit_event", side_effect=RuntimeError("boom")), \
                patch("routers.broker.httpx.get", return_value=_account_response(101)), \
                pytest.raises(RuntimeError):
            connect(
                payload={"api_key": "new-key-value-1234567890"},
                db=db_session, portfolio=default_portfolio, _context=MagicMock(),
            )
        db_session.rollback()

        assert db_session.query(Transaction).count() == 1
        assert db_session.query(BrokerConnection).count() == 0
        db_session.refresh(default_portfolio)
        assert default_portfolio.name == "Portfyl demo"

    def test_records_audit_event_only_when_demo_removed(
        self, db_session, default_portfolio, request_context
    ):
        db_session.add(make_txn(
            ticker="AAPL", date=date(2025, 1, 2),
            portfolio_id=default_portfolio.id, source="demo",
        ))
        db_session.commit()

        with patch("routers.broker.httpx.get", return_value=_account_response(101)):
            connect(
                payload={"api_key": "new-key-value-1234567890"},
                db=db_session, portfolio=default_portfolio, _context=request_context,
            )
            connect(
                payload={"api_key": "new-key-value-1234567890"},
                db=db_session, portfolio=default_portfolio, _context=request_context,
            )

        removed = db_session.query(AuditLog).filter(
            AuditLog.action == "onboarding.demo.removed"
        ).all()
        assert len(removed) == 1
        assert removed[0].event_metadata == {
            "transactions": 1, "portfolios": 0, "renamed": False,
        }


class TestAccountBinding:
    def test_fresh_connect_binds_account_without_deleting_existing_ledger(
        self, db_session, default_portfolio
    ):
        db_session.add(make_txn(
            ticker="AAPL", date=date(2024, 1, 1), portfolio_id=default_portfolio.id,
        ))
        db_session.commit()

        with patch("routers.broker.httpx.get", return_value=_account_response(101)):
            connect(
                payload={"api_key": "new-key-value-1234567890"},
                db=db_session, portfolio=default_portfolio, _context=None,
            )

        connection = db_session.query(BrokerConnection).one()
        assert db_session.query(Transaction).count() == 1
        assert connection.account_fingerprint
        assert connection.account_fingerprint == default_portfolio.t212_account_fingerprint

    def test_different_account_is_rejected_before_mutating_credentials_or_ledger(
        self, db_session, default_portfolio
    ):
        old_fingerprint = account_fingerprint(
            broker="trading212", environment="live", provider_account_id=101,
        )
        default_portfolio.t212_account_fingerprint = old_fingerprint
        connection = BrokerConnection(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212",
            api_key="old-key-value-1234567890",
            account_fingerprint=old_fingerprint,
        )
        db_session.add_all([
            connection,
            make_txn(ticker="AAPL", date=date(2024, 1, 1), portfolio_id=default_portfolio.id),
        ])
        db_session.commit()

        with patch("routers.broker.httpx.get", return_value=_account_response(202)):
            with pytest.raises(Exception) as exc_info:
                connect(
                    payload={"api_key": "other-key-value-1234567890"},
                    db=db_session, portfolio=default_portfolio, _context=None,
                )

        assert exc_info.value.status_code == 409
        db_session.refresh(connection)
        assert connection.api_key == "old-key-value-1234567890"
        assert connection.account_fingerprint == old_fingerprint
        assert db_session.query(Transaction).count() == 1

    def test_disconnect_retains_portfolio_account_binding(
        self, db_session, default_portfolio
    ):
        fingerprint = account_fingerprint(
            broker="trading212", environment="live", provider_account_id=101,
        )
        default_portfolio.t212_account_fingerprint = fingerprint
        db_session.add(BrokerConnection(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212",
            api_key="old-key-value-1234567890",
            account_fingerprint=fingerprint,
        ))
        db_session.commit()

        disconnect(db=db_session, portfolio=default_portfolio, _context=None)

        db_session.refresh(default_portfolio)
        assert default_portfolio.t212_account_fingerprint == fingerprint

    def test_disconnected_portfolio_rejects_a_different_account(
        self, db_session, default_portfolio
    ):
        default_portfolio.t212_account_fingerprint = account_fingerprint(
            broker="trading212", environment="live", provider_account_id=101,
        )
        db_session.commit()

        with patch("routers.broker.httpx.get", return_value=_account_response(202)):
            with pytest.raises(Exception) as exc_info:
                connect(
                    payload={"api_key": "other-key-value-1234567890"},
                    db=db_session, portfolio=default_portfolio, _context=None,
                )

        assert exc_info.value.status_code == 409
        assert db_session.query(BrokerConnection).count() == 0

    def test_unverifiable_legacy_connection_fails_closed(
        self, db_session, default_portfolio
    ):
        connection = BrokerConnection(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212",
            api_key="old-key-value-1234567890",
        )
        db_session.add_all([
            connection,
            make_txn(ticker="AAPL", date=date(2024, 1, 1), portfolio_id=default_portfolio.id),
        ])
        db_session.commit()

        with patch("routers.broker.httpx.get", side_effect=[
            _account_response(202),
            _account_response(202),
            _account_response(status_code=401),
        ]):
            with pytest.raises(Exception) as exc_info:
                connect(
                    payload={"api_key": "new-key-value-1234567890"},
                    db=db_session, portfolio=default_portfolio, _context=None,
                )

        assert exc_info.value.status_code == 409
        db_session.refresh(connection)
        assert connection.api_key == "old-key-value-1234567890"
        assert connection.account_fingerprint is None
        assert default_portfolio.t212_account_fingerprint is None
        assert db_session.query(Transaction).count() == 1


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

    def test_successful_empty_snapshot_is_fresh_and_distinct_from_never_synced(
        self, db_session, default_portfolio, connection
    ):
        t212_sync.replace_positions(db_session, default_portfolio, [])
        db_session.commit()

        result = get_positions(db=db_session, portfolio=default_portfolio)
        assert result["connected"] is True
        assert result["status"] == "fresh"
        assert result["as_of"] is not None
        assert result["positions"] == []

    def test_fresh_snapshot_does_not_label_unknown_native_values_as_display_currency(
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
        # No ledger row for AAPL exists, so currency is unknown. The provider
        # price must not be presented as an amount in the requested currency.
        assert pos["currency"] is None
        assert pos["market_value"] is None
        assert pos["cost_basis"] is None
        assert pos["pnl"] is None

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

    def test_missing_ledger_currency_does_not_default_snapshot_value_to_usd(
        self, db_session, default_portfolio, pid, connection
    ):
        txn = make_txn("AAPL", "buy", 5, 140.0, date=date(2024, 1, 1), portfolio_id=pid)
        db_session.add(txn)
        db_session.add(BrokerPosition(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212", provider_ticker="AAPL_US_EQ", ticker="AAPL",
            quantity=10.0, avg_price=150.0, current_price=175.0,
            as_of=datetime.now(timezone.utc),
        ))
        db_session.flush()
        # Transaction's ORM insert default is USD, so clear it after insertion
        # to represent a legacy row with genuinely unknown currency.
        txn.currency = None
        db_session.commit()

        position = get_positions(currency="USD", db=db_session, portfolio=default_portfolio)["positions"][0]

        assert position["currency"] is None
        assert position["market_value"] is None


class TestSyncStartsHistoryRun:
    """T212 snapshot-first sync plan (2026-09-20), Task 3: sync_transactions
    starts (or returns the already-active) resumable history run without
    downloading history in the request."""

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
        assert result["snapshot"]["status"] == "ready"
        assert result["history"]["status"] == "pending"
        run = db_session.query(BrokerSyncRun).one()
        assert result["history"]["run_id"] == str(run.public_id)
        assert "total_imported" not in result
        assert run.connection_id == connection.id
        assert run.credential_generation == connection.credential_generation

    def test_manual_sync_does_not_fetch_full_history_in_the_request(
        self, db_session, default_portfolio, connection
    ):
        snapshot = t212_sync.SnapshotResult(
            summary={
                "id": 1,
                "cash": {"availableToTrade": 0, "inPies": 0, "reservedForOrders": 0},
                "currency": "CZK",
                "investments": {},
                "totalValue": 0,
            },
            summary_error=None,
            positions=[],
            positions_error=None,
        )
        with patch("t212_sync.fetch_snapshot", return_value=snapshot), \
             patch("routers.broker._fetch_all_orders", return_value=[], create=True) as fetch_orders, \
             patch("routers.broker._fetch_all_dividends", return_value=[], create=True) as fetch_dividends:
            result = sync_transactions(
                db=db_session, portfolio=default_portfolio, _context=None,
            )

        assert result["history"]["status"] == "pending"
        fetch_orders.assert_not_called()
        fetch_dividends.assert_not_called()

    def test_repeated_sync_returns_the_same_run(self, db_session, default_portfolio, connection):
        first = _run_sync(db_session, default_portfolio, [])
        second = _run_sync(db_session, default_portfolio, [])
        assert first["history"]["run_id"] == second["history"]["run_id"]
        assert db_session.query(BrokerSyncRun).count() == 1

    def test_manual_sync_does_not_acquire_the_ledger_writer_lock(
        self, db_session, default_portfolio, connection
    ):
        with patch("routers.broker.acquire_workspace_ledger_lock", create=True) as acquire_lock:
            _run_sync(db_session, default_portfolio, [])

        acquire_lock.assert_not_called()


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
        info_response.json.return_value = {"id": 1}
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
        info_response.json.return_value = {"id": 1}
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
        info_response.json.return_value = {"id": 1}
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

    def test_cash_progress_is_reported_and_gates_download_complete(
        self, db_session, default_portfolio
    ):
        conn = BrokerConnection(workspace_id=default_portfolio.workspace_id,
                                portfolio_id=default_portfolio.id,
                                broker="trading212", api_key="k" * 20)
        db_session.add(conn)
        db_session.flush()
        reset = datetime(2030, 1, 1, tzinfo=timezone.utc)
        db_session.add(BrokerSyncRun(
            workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
            connection_id=conn.id, broker="trading212",
            credential_generation=conn.credential_generation, mode="incremental",
            state="waiting_rate_limit", orders_complete=True, dividends_complete=True,
            cash_loaded=7, cash_complete=False, cash_rate_limit_reset_at=reset,
        ))
        db_session.commit()

        run = get_history_status(db=db_session, portfolio=default_portfolio)["run"]

        assert run["cash_loaded"] == 7
        assert run["cash_complete"] is False
        assert run["download_complete"] is False
        assert run["resume_at"].startswith("2030-01-01")

    def test_needs_review_run_is_not_reported_as_retrying(
        self, db_session, default_portfolio
    ):
        conn = BrokerConnection(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212",
            api_key="k" * 20,
        )
        db_session.add(conn)
        db_session.flush()
        db_session.add(BrokerSyncRun(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            connection_id=conn.id,
            broker="trading212",
            credential_generation=conn.credential_generation,
            mode="incremental",
            state="needs_review",
            orders_complete=True,
            dividends_complete=True,
            last_error=t212_sync.HISTORY_NEEDS_REVIEW_ERROR,
        ))
        db_session.commit()

        result = get_history_status(db=db_session, portfolio=default_portfolio)

        assert result["run"]["state"] == "needs_review"
        assert result["run"]["complete"] is False
        assert result["run"]["last_error"] == t212_sync.HISTORY_NEEDS_REVIEW_ERROR
        assert "retry" not in result["run"]["last_error"].lower()

    def test_history_status_shows_the_pagination_error(self, db_session, default_portfolio):
        conn = BrokerConnection(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212",
            api_key="k" * 20,
        )
        db_session.add(conn)
        db_session.flush()
        db_session.add(BrokerSyncRun(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            connection_id=conn.id,
            broker="trading212",
            credential_generation=conn.credential_generation,
            mode="incremental",
            state="failed",
            last_error=t212_sync.HISTORY_PAGINATION_ERROR,
        ))
        db_session.commit()

        result = get_history_status(db=db_session, portfolio=default_portfolio)

        assert result["run"]["state"] == "failed"
        assert result["run"]["last_error"] == t212_sync.HISTORY_PAGINATION_ERROR

    def test_a_cash_review_reports_its_own_reason_not_the_split_message(
        self, db_session, default_portfolio
    ):
        conn = BrokerConnection(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212", api_key="k" * 20,
        )
        db_session.add(conn)
        db_session.flush()
        db_session.add(BrokerSyncRun(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            connection_id=conn.id, broker="trading212",
            credential_generation=conn.credential_generation,
            mode="incremental", state="needs_review",
            orders_complete=True, dividends_complete=True, cash_complete=True,
            last_error=t212_sync.HISTORY_CASH_UNSUPPORTED_ERROR,
            review_details=[{"fill_type": None, "ticker": None,
                             "date": "2026-03-01", "cash_type": "MYSTERY"}],
        ))
        db_session.commit()

        run = get_history_status(db=db_session, portfolio=default_portfolio)["run"]

        assert run["last_error"] == t212_sync.HISTORY_CASH_UNSUPPORTED_ERROR
        assert run["review"]["items"][0]["cash_type"] == "MYSTERY"
        assert run["review"]["mapper_supports_all"] is False

    def test_waiting_status_exposes_reset_time_without_raw_url_or_cursor(
        self, db_session, default_portfolio
    ):
        conn = BrokerConnection(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            broker="trading212",
            api_key="k" * 20,
        )
        db_session.add(conn)
        db_session.flush()
        reset_at = datetime.now(timezone.utc) + timedelta(minutes=1)
        db_session.add(BrokerSyncRun(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            connection_id=conn.id,
            broker="trading212",
            credential_generation=conn.credential_generation,
            mode="incremental",
            state="waiting_rate_limit",
            orders_next_page_path="/equity/history/orders?cursor=secret-cursor&limit=50",
            orders_rate_limit_reset_at=reset_at,
            last_error=(
                "429 Too Many Requests for url "
                "https://live.trading212.com/api/v0/equity/history/orders?cursor=secret-cursor"
            ),
        ))
        db_session.commit()

        result = get_history_status(db=db_session, portfolio=default_portfolio)
        rendered = str(result)

        assert result["run"]["resume_at"] == reset_at.isoformat()
        assert result["run"]["last_error"] == "Trading 212 history sync will retry automatically."
        assert "https://" not in rendered
        assert "secret-cursor" not in rendered


class TestHistoryStatusReconciliation:
    """`GET /trading212/history-status` reports whether the finalized ledger's
    open quantities agree with the current broker snapshot (plan §6.3). It is
    strictly read-only: a mismatch never creates an adjustment row."""

    @staticmethod
    def _setup(db, portfolio, *, run_state="completed", snapshot_at=True,
               positions=(), ledger=(), position_age=timedelta(0)):
        conn = BrokerConnection(
            workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id,
            broker="trading212", api_key="k" * 20,
            positions_snapshot_at=(
                datetime.now(timezone.utc) - position_age if snapshot_at else None
            ),
        )
        db.add(conn)
        db.flush()
        db.add(BrokerSyncRun(
            workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id,
            connection_id=conn.id, broker="trading212",
            credential_generation=conn.credential_generation, mode="incremental",
            state=run_state,
        ))
        for ticker, quantity in positions:
            db.add(BrokerPosition(
                workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id,
                broker="trading212", provider_ticker=f"{ticker}_US_EQ", ticker=ticker,
                quantity=quantity, avg_price=100.0,
                as_of=datetime.now(timezone.utc) - position_age,
            ))
        for ticker, shares in ledger:
            db.add(make_txn(
                ticker=ticker, type="buy", shares=shares, price=100.0,
                date=date(2024, 1, 2), portfolio_id=portfolio.id,
                workspace_id=portfolio.workspace_id,
            ))
        db.commit()

    def test_completed_history_matching_the_snapshot_reports_matched(
        self, db_session, default_portfolio
    ):
        self._setup(db_session, default_portfolio,
                    positions=[("AAPL", 10.0)], ledger=[("AAPL", 10.0)])

        result = get_history_status(db=db_session, portfolio=default_portfolio)

        assert result["reconciliation"]["status"] == "matched"
        assert result["reconciliation"]["matched_count"] == 1

    def test_mismatch_is_reported_without_creating_adjustment_rows(
        self, db_session, default_portfolio
    ):
        self._setup(db_session, default_portfolio,
                    positions=[("NVDA", 100.0)], ledger=[("NVDA", 10.0)])

        result = get_history_status(db=db_session, portfolio=default_portfolio)

        reconciliation = result["reconciliation"]
        assert reconciliation["status"] == "different"
        (item,) = reconciliation["different"]
        assert item["ticker"] == "NVDA"
        assert item["direction"] == "ledger_lower"
        assert db_session.query(Transaction).count() == 1

    def test_stale_snapshot_mismatch_names_staleness_as_a_cause(
        self, db_session, default_portfolio
    ):
        self._setup(db_session, default_portfolio, position_age=timedelta(days=3),
                    positions=[("NVDA", 100.0)], ledger=[("NVDA", 10.0)])

        result = get_history_status(db=db_session, portfolio=default_portfolio)

        (item,) = result["reconciliation"]["different"]
        assert "snapshot_stale" in item["likely_causes"]

    def test_successful_empty_snapshot_with_an_empty_ledger_matches(
        self, db_session, default_portfolio
    ):
        self._setup(db_session, default_portfolio)

        result = get_history_status(db=db_session, portfolio=default_portfolio)

        assert result["reconciliation"]["status"] == "matched"

    @pytest.mark.parametrize("run_state", ["pending", "fetching", "finalizing", "needs_review", "failed"])
    def test_unavailable_until_the_latest_run_completed(
        self, db_session, default_portfolio, run_state
    ):
        self._setup(db_session, default_portfolio, run_state=run_state,
                    positions=[("AAPL", 10.0)], ledger=[("AAPL", 10.0)])

        result = get_history_status(db=db_session, portfolio=default_portfolio)

        assert result["reconciliation"]["status"] == "unavailable"
        assert result["reconciliation"]["reason"] == "history_incomplete"

    def test_unavailable_when_no_positions_snapshot_was_ever_fetched(
        self, db_session, default_portfolio
    ):
        self._setup(db_session, default_portfolio, snapshot_at=False,
                    ledger=[("AAPL", 10.0)])

        result = get_history_status(db=db_session, portfolio=default_portfolio)

        assert result["reconciliation"]["status"] == "unavailable"
        assert result["reconciliation"]["reason"] == "no_snapshot"

    def test_no_run_yet_has_no_reconciliation_field(self, db_session, default_portfolio):
        db_session.add(BrokerConnection(
            workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
            broker="trading212", api_key="k" * 20,
        ))
        db_session.commit()

        result = get_history_status(db=db_session, portfolio=default_portfolio)

        assert result == {"connected": True, "run": None}


# ---------------------------------------------------------------------------
# needs_review re-download loop breaker (plan 2026-09-24, Task A4)
# ---------------------------------------------------------------------------

_SPLIT_REVIEW = [{"fill_type": "STOCK_DISTRIBUTION", "ticker": "NVDA", "date": "2024-06-10"}]


class TestNeedsReviewLoopBreaker:
    @pytest.fixture
    def connection(self, db_session, default_portfolio):
        conn = BrokerConnection(workspace_id=default_portfolio.workspace_id,
                                portfolio_id=default_portfolio.id,
                                broker="trading212", api_key="k" * 20)
        db_session.add(conn)
        db_session.commit()
        return conn

    @pytest.fixture
    def review_run(self, db_session, default_portfolio, connection):
        run = BrokerSyncRun(
            workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
            connection_id=connection.id, broker="trading212",
            credential_generation=connection.credential_generation, mode="incremental",
            state="needs_review", orders_complete=True, dividends_complete=True,
            last_error=t212_sync.HISTORY_NEEDS_REVIEW_ERROR, review_details=_SPLIT_REVIEW,
        )
        db_session.add(run)
        db_session.commit()
        return run

    def test_sync_refreshes_snapshot_but_creates_no_run_when_blocked(
        self, db_session, default_portfolio, connection, review_run
    ):
        result = _run_sync(db_session, default_portfolio, [])

        assert result["snapshot"]["status"] == "ready"
        assert result["history"]["status"] == "needs_review"
        assert result["history"]["run_id"] == str(review_run.public_id)
        assert result["history"]["blocked"] is True
        assert result["history"]["complete"] is False
        assert db_session.query(BrokerSyncRun).count() == 1

    def test_sync_without_a_review_run_is_not_blocked(
        self, db_session, default_portfolio, connection
    ):
        result = _run_sync(db_session, default_portfolio, [])
        assert result["history"]["blocked"] is False
        assert result["history"]["status"] == "pending"

    def test_retry_route_creates_new_run(
        self, db_session, default_portfolio, connection, review_run
    ):
        result = retry_history(db=db_session, portfolio=default_portfolio, _context=None)

        assert result["status"] == "pending"
        assert result["blocked"] is False
        assert result["complete"] is False
        assert result["run_id"] != str(review_run.public_id)
        assert db_session.query(BrokerSyncRun).count() == 2

    def test_retry_route_reuses_an_already_active_run(
        self, db_session, default_portfolio, connection, review_run
    ):
        first = retry_history(db=db_session, portfolio=default_portfolio, _context=None)
        second = retry_history(db=db_session, portfolio=default_portfolio, _context=None)

        assert first["run_id"] == second["run_id"]
        assert db_session.query(BrokerSyncRun).count() == 2

    def test_retry_route_requires_a_connection(self, db_session, default_portfolio):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            retry_history(db=db_session, portfolio=default_portfolio, _context=None)
        assert exc.value.status_code == 404

    def test_history_status_exposes_review_block_without_payloads(
        self, db_session, default_portfolio, connection, review_run
    ):
        result = get_history_status(db=db_session, portfolio=default_portfolio)

        assert result["run"]["review"] == {
            "items": _SPLIT_REVIEW,
            "csv_covers_all": False,
            "csv_needed_through": "2024-06-10",
            "mapper_supports_all": False,
        }

    def test_history_status_review_is_none_for_other_states(
        self, db_session, default_portfolio, connection, review_run
    ):
        review_run.state = "completed"
        db_session.commit()

        result = get_history_status(db=db_session, portfolio=default_portfolio)

        assert result["run"]["review"] is None


class TestSyncRunMode:
    """Plan 2026-09-24 Task C1: the routes create runs in the decided mode."""

    @pytest.fixture
    def connection(self, db_session, default_portfolio):
        conn = BrokerConnection(workspace_id=default_portfolio.workspace_id,
                                portfolio_id=default_portfolio.id,
                                broker="trading212", api_key="k" * 20)
        db_session.add(conn)
        db_session.commit()
        return conn

    def test_first_sync_creates_an_initial_run(self, db_session, default_portfolio, connection):
        _run_sync(db_session, default_portfolio, [])
        assert db_session.query(BrokerSyncRun).one().mode == "initial"

    def test_sync_after_history_completed_creates_an_incremental_run(
        self, db_session, default_portfolio, connection
    ):
        connection.history_complete_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
        connection.last_full_audit_at = datetime.now(timezone.utc)
        db_session.commit()

        _run_sync(db_session, default_portfolio, [])

        assert db_session.query(BrokerSyncRun).one().mode == "incremental"

    def test_retry_creates_a_run_in_the_decided_mode(
        self, db_session, default_portfolio, connection
    ):
        retry_history(db=db_session, portfolio=default_portfolio, _context=None)
        assert db_session.query(BrokerSyncRun).one().mode == "initial"


class TestSyncAuditMode:
    """Plan 2026-09-24 Task C3: sync_transactions turns the next run into an
    audit when the last full read is 30 days old or reconciliation disagrees."""

    @pytest.fixture
    def connection(self, db_session, default_portfolio):
        conn = BrokerConnection(workspace_id=default_portfolio.workspace_id,
                                portfolio_id=default_portfolio.id,
                                broker="trading212", api_key="k" * 20)
        db_session.add(conn)
        db_session.commit()
        return conn

    @staticmethod
    def _completed_history(db, portfolio, conn, *, last_read_age, ledger_shares=10.0,
                           latest_mode="incremental"):
        read_at = datetime.now(timezone.utc) - last_read_age
        conn.history_complete_at = read_at
        conn.last_full_audit_at = read_at
        db.add(BrokerSyncRun(
            workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id,
            connection_id=conn.id, broker="trading212",
            credential_generation=conn.credential_generation, mode=latest_mode,
            state="completed", completed_at=read_at,
        ))
        db.add(make_txn(
            "AAPL", "buy", ledger_shares, 100.0, date=date(2024, 1, 2),
            portfolio_id=portfolio.id, workspace_id=portfolio.workspace_id,
        ))
        db.commit()

    @staticmethod
    def _new_run(db):
        return db.query(BrokerSyncRun).filter(BrokerSyncRun.state == "pending").one()

    def test_manual_sync_after_30_days_creates_an_audit_run(
        self, db_session, default_portfolio, connection
    ):
        self._completed_history(
            db_session, default_portfolio, connection, last_read_age=timedelta(days=31),
        )

        _run_sync(db_session, default_portfolio, [], positions=[t212_position(quantity=10.0)])

        assert self._new_run(db_session).mode == "audit"

    def test_reconciliation_mismatch_creates_an_audit_run(
        self, db_session, default_portfolio, connection
    ):
        self._completed_history(
            db_session, default_portfolio, connection, last_read_age=timedelta(days=8),
        )

        _run_sync(db_session, default_portfolio, [], positions=[t212_position(quantity=12.0)])

        assert self._new_run(db_session).mode == "audit"

    @pytest.mark.parametrize("latest_mode", ["initial", "audit"])
    def test_mismatch_after_a_full_read_run_does_not_audit_again(
        self, db_session, default_portfolio, connection, latest_mode
    ):
        # The latest completed run already read the whole history, so another
        # full read cannot explain a mismatch that is still there.
        self._completed_history(
            db_session, default_portfolio, connection, last_read_age=timedelta(days=8),
            latest_mode=latest_mode,
        )

        _run_sync(db_session, default_portfolio, [], positions=[t212_position(quantity=12.0)])

        assert self._new_run(db_session).mode == "incremental"

    def test_persistent_mismatch_audits_at_most_once_per_cooldown(
        self, db_session, default_portfolio, connection
    ):
        # A permanent cause (ticker mapping, unsupported action) must not turn
        # every daily incremental sync into a full re-download.
        self._completed_history(
            db_session, default_portfolio, connection, last_read_age=timedelta(days=3),
        )

        _run_sync(db_session, default_portfolio, [], positions=[t212_position(quantity=12.0)])

        assert self._new_run(db_session).mode == "incremental"

    def test_matching_positions_keep_the_sync_incremental(
        self, db_session, default_portfolio, connection
    ):
        self._completed_history(
            db_session, default_portfolio, connection, last_read_age=timedelta(days=2),
        )

        _run_sync(db_session, default_portfolio, [], positions=[t212_position(quantity=10.0)])

        assert self._new_run(db_session).mode == "incremental"

    def test_mismatch_right_after_a_full_read_does_not_repeat_the_audit(
        self, db_session, default_portfolio, connection
    ):
        # A full read within the last day already saw everything the provider
        # has; auditing again on every sync would only re-download it.
        self._completed_history(
            db_session, default_portfolio, connection, last_read_age=timedelta(hours=1),
        )

        _run_sync(db_session, default_portfolio, [], positions=[t212_position(quantity=12.0)])

        assert self._new_run(db_session).mode == "incremental"

    def test_failed_positions_refresh_never_triggers_a_mismatch_audit(
        self, db_session, default_portfolio, connection
    ):
        self._completed_history(
            db_session, default_portfolio, connection, last_read_age=timedelta(days=2),
        )
        db_session.add(BrokerPosition(
            workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
            broker="trading212", provider_ticker="AAPL_US_EQ", ticker="AAPL",
            quantity=99.0, avg_price=100.0, as_of=datetime.now(timezone.utc),
        ))
        db_session.commit()

        _run_sync(db_session, default_portfolio, [], positions_error=RuntimeError("boom"))

        assert self._new_run(db_session).mode == "incremental"
