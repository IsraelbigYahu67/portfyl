"""BrokerConnection credentials are stored only as ciphertext; the api_key/
api_secret properties transparently encrypt on write and decrypt on read."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from models import BrokerConnection
from routers.broker import connect as t212_connect


def _make_connection(db_session, workspace_id, portfolio_id, broker="trading212",
                      api_key="k" * 20, api_secret=""):
    conn = BrokerConnection(
        workspace_id=workspace_id, portfolio_id=portfolio_id, broker=broker,
        api_key=api_key, api_secret=api_secret, environment="live",
    )
    db_session.add(conn)
    db_session.commit()
    db_session.refresh(conn)
    return conn


class TestAtRestEncryption:
    def test_no_plaintext_survives_on_the_row(self, db_session, default_portfolio):
        conn = _make_connection(
            db_session, default_portfolio.workspace_id, default_portfolio.id,
            api_key="sk_live_abcdef1234567890", api_secret="super-secret-value",
        )
        assert conn.api_key_ciphertext is not None
        assert b"sk_live_abcdef1234567890" not in conn.api_key_ciphertext
        assert conn.api_secret_ciphertext is not None
        assert b"super-secret-value" not in conn.api_secret_ciphertext
        # The ORM no longer maps any plaintext column at all -- there is
        # nothing named api_key/api_secret in __table__.columns.
        column_names = {c.name for c in BrokerConnection.__table__.columns}
        assert "api_key" not in column_names
        assert "api_secret" not in column_names

    def test_round_trips_through_the_property(self, db_session, default_portfolio):
        conn = _make_connection(
            db_session, default_portfolio.workspace_id, default_portfolio.id,
            api_key="my-api-key", api_secret="my-api-secret",
        )
        db_session.expire_all()
        reloaded = db_session.get(BrokerConnection, conn.id)
        assert reloaded.api_key == "my-api-key"
        assert reloaded.api_secret == "my-api-secret"

    def test_blank_api_secret_stays_none(self, db_session, default_portfolio):
        conn = _make_connection(
            db_session, default_portfolio.workspace_id, default_portfolio.id,
            api_key="only-a-key", api_secret="",
        )
        assert conn.api_secret_ciphertext is None
        assert conn.api_secret is None

    def test_two_connections_with_the_same_key_have_different_ciphertext(
        self, db_session, default_portfolio,
    ):
        # Fernet ciphertext is never byte-identical across two encryptions,
        # even of the same plaintext -- confirms api_key isn't accidentally
        # falling back to a deterministic/plaintext encoding.
        first = _make_connection(
            db_session, default_portfolio.workspace_id, default_portfolio.id,
            broker="trading212", api_key="shared-key",
        )
        second_ws_conn = BrokerConnection(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id, broker="ibkr",
            api_key="shared-key",
        )
        assert first.api_key_ciphertext != second_ws_conn.api_key_ciphertext
        assert first.api_key == second_ws_conn.api_key == "shared-key"


class TestClashDetectionWithoutSqlFilterOnCiphertext:
    def test_connecting_the_same_key_to_a_second_portfolio_is_rejected(
        self, db_session, test_workspace,
    ):
        from models import Portfolio

        p1 = Portfolio(workspace_id=test_workspace.id, name="P1", is_default=True)
        p2 = Portfolio(workspace_id=test_workspace.id, name="P2")
        db_session.add_all([p1, p2])
        db_session.commit()

        _make_connection(db_session, test_workspace.id, p1.id, api_key="dupe-key" * 3)

        with pytest.raises(HTTPException) as exc_info:
            t212_connect(
                payload={"api_key": "dupe-key" * 3},
                db=db_session,
                portfolio=p2,
                _context=None,
            )
        assert exc_info.value.status_code == 409

    def test_connecting_a_different_key_to_a_second_portfolio_succeeds(
        self, db_session, test_workspace, monkeypatch,
    ):
        from models import Portfolio
        import routers.broker as broker_module

        p1 = Portfolio(workspace_id=test_workspace.id, name="P1", is_default=True)
        p2 = Portfolio(workspace_id=test_workspace.id, name="P2")
        db_session.add_all([p1, p2])
        db_session.commit()

        _make_connection(db_session, test_workspace.id, p1.id, api_key="key-one" * 3)

        class _FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

        monkeypatch.setattr(broker_module.httpx, "get", lambda *a, **k: _FakeResponse())

        result = t212_connect(
            payload={"api_key": "key-two" * 3},
            db=db_session,
            portfolio=p2,
            _context=None,
        )
        assert result["ok"] is True


class TestSyncDecryptsStoredCredentials:
    def test_t212_sync_uses_decrypted_credentials(self, db_session, default_portfolio, pid):
        import routers.broker as broker_module

        conn = _make_connection(
            db_session, default_portfolio.workspace_id, default_portfolio.id,
            api_key="real-t212-key", api_secret="",
        )
        seen_headers = {}

        def _fake_fetch_orders(base, headers):
            seen_headers.update(headers)
            return []

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(broker_module, "_fetch_all_orders", _fake_fetch_orders)
            mp.setattr(broker_module, "_fetch_account_summary", lambda base, headers: {
                "cash": {"availableToTrade": 0},
                "currency": "USD",
                "investments": {},
                "totalValue": 0,
            })
            mp.setattr(broker_module, "_fetch_all_dividends", lambda base, headers: [])
            broker_module.sync_transactions(db=db_session, portfolio=default_portfolio, _context=None)

        assert seen_headers.get("Authorization") == "real-t212-key"
