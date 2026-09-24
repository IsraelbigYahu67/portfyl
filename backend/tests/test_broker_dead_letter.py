"""A broker connection that fails every auto-sync pass stops retrying
silently once it hits BROKER_AUTOSYNC_FAILURE_THRESHOLD consecutive
failures: auto_sync flips off, needs_attention flips on, and the flag
clears the moment the user re-enables it or reconnects."""
from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from jobs import BROKER_AUTOSYNC_FAILURE_THRESHOLD, broker_autosync_pass
from models import BrokerConnection
from routers.broker import connect as t212_connect, set_auto_sync as t212_set_auto_sync
from tests.helpers import TEST_WORKSPACE_ID


def _run(coro):
    return asyncio.run(coro)


def _connect(db, pid, workspace_id=TEST_WORKSPACE_ID):
    conn = BrokerConnection(
        workspace_id=workspace_id, portfolio_id=pid, broker="trading212",
        api_key="k" * 20, api_secret="", environment="live", auto_sync=True,
    )
    db.add(conn)
    db.commit()
    return conn


class TestFailureTracking:
    def test_repeated_failures_disable_auto_sync_and_flag_the_connection(
        self, db_session, default_portfolio, pid,
    ):
        conn = _connect(db_session, pid, default_portfolio.workspace_id)

        with patch("routers.broker.sync_transactions", side_effect=RuntimeError("T212 is down")):
            for _ in range(BROKER_AUTOSYNC_FAILURE_THRESHOLD):
                _run(broker_autosync_pass(db_session, default_portfolio.workspace_id))

        assert conn.consecutive_failures == BROKER_AUTOSYNC_FAILURE_THRESHOLD
        assert conn.needs_attention is True
        assert conn.auto_sync is False
        assert "T212 is down" in conn.last_error

    def test_a_pass_stops_being_retried_once_disabled(self, db_session, default_portfolio, pid):
        conn = _connect(db_session, pid, default_portfolio.workspace_id)

        with patch("routers.broker.sync_transactions", side_effect=RuntimeError("down")):
            for _ in range(BROKER_AUTOSYNC_FAILURE_THRESHOLD):
                _run(broker_autosync_pass(db_session, default_portfolio.workspace_id))

        assert conn.auto_sync is False

        # One more pass: the query already excludes auto_sync=False rows.
        sync = patch("routers.broker.sync_transactions", side_effect=RuntimeError("down"))
        with sync as mocked:
            results = _run(broker_autosync_pass(db_session, default_portfolio.workspace_id))
        mocked.assert_not_called()
        assert results == []

    def test_a_single_failure_below_threshold_keeps_auto_sync_on(
        self, db_session, default_portfolio, pid,
    ):
        conn = _connect(db_session, pid, default_portfolio.workspace_id)

        with patch("routers.broker.sync_transactions", side_effect=RuntimeError("blip")):
            _run(broker_autosync_pass(db_session, default_portfolio.workspace_id))

        assert conn.consecutive_failures == 1
        assert conn.needs_attention is False
        assert conn.auto_sync is True

    def test_a_success_after_failures_resets_the_counter(
        self, db_session, default_portfolio, pid,
    ):
        conn = _connect(db_session, pid, default_portfolio.workspace_id)

        with patch("routers.broker.sync_transactions", side_effect=RuntimeError("blip")):
            _run(broker_autosync_pass(db_session, default_portfolio.workspace_id))
        assert conn.consecutive_failures == 1

        ok_result = {"imported_orders": 0, "imported_dividends": 0, "total_imported": 0, "errors": []}
        with patch("routers.broker.sync_transactions", return_value=ok_result):
            _run(broker_autosync_pass(db_session, default_portfolio.workspace_id))

        assert conn.consecutive_failures == 0
        assert conn.needs_attention is False
        assert conn.last_error is None


class TestReenablingClearsDeadLetterState:
    def test_toggling_auto_sync_back_on_clears_the_flag(self, db_session, default_portfolio, pid):
        conn = _connect(db_session, pid, default_portfolio.workspace_id)
        conn.consecutive_failures = 5
        conn.needs_attention = True
        conn.last_error = "T212 is down"
        conn.auto_sync = False
        db_session.commit()

        t212_set_auto_sync(
            payload={"enabled": True}, db=db_session, portfolio=default_portfolio, _context=None,
        )

        assert conn.needs_attention is False
        assert conn.consecutive_failures == 0
        assert conn.last_error is None

    def test_reconnecting_clears_the_flag(self, db_session, default_portfolio, monkeypatch):
        import routers.broker as broker_module

        conn = _connect(db_session, default_portfolio.id, default_portfolio.workspace_id)
        conn.consecutive_failures = 5
        conn.needs_attention = True
        conn.last_error = "T212 is down"
        conn.auto_sync = False
        db_session.commit()

        class _FakeResponse:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"id": 1}

        monkeypatch.setattr(broker_module.httpx, "get", lambda *a, **k: _FakeResponse())

        t212_connect(
            payload={"api_key": "brand-new-key" * 2},
            db=db_session, portfolio=default_portfolio, _context=None,
        )

        assert conn.needs_attention is False
        assert conn.consecutive_failures == 0
