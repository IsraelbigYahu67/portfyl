"""Tests for jobs.broker_backfill_pass (T212 snapshot-first sync, Task 3).

Network (t212_sync.advance_run's httpx calls) is always patched -- this file
tests the job's orchestration (which runs get claimed/skipped/cancelled),
not the page-fetching mechanics already covered by test_t212_sync_runs.py.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import t212_sync
from jobs import broker_backfill_pass
from models import BrokerConnection, BrokerSyncRun, Portfolio
from tests.helpers import TEST_WORKSPACE_ID


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def connection(db_session, default_portfolio):
    conn = BrokerConnection(
        workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
        broker="trading212", api_key="k" * 20,
    )
    db_session.add(conn)
    db_session.commit()
    db_session.refresh(conn)
    return conn


def _run_row(db, connection, portfolio, *, state="pending", **overrides):
    row = BrokerSyncRun(
        workspace_id=connection.workspace_id,
        portfolio_id=portfolio.id,
        connection_id=connection.id,
        broker="trading212",
        credential_generation=connection.credential_generation,
        mode="incremental",
        state=state,
        **overrides,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class TestBrokerBackfillPass:
    def test_no_due_runs_is_a_noop(self, db_session, default_portfolio, connection):
        results = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))
        assert results == []

    def test_advances_a_due_run(self, db_session, default_portfolio, connection):
        run = _run_row(db_session, connection, default_portfolio, state="pending")
        fake_result = t212_sync.RunAdvanceResult(
            state="completed", orders_staged=2, dividends_staged=1, rate_limited_streams=()
        )
        with patch("t212_sync.advance_run", return_value=fake_result) as advance:
            results = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))

        advance.assert_called_once()
        assert len(results) == 1
        assert results[0]["run_id"] == str(run.public_id)
        assert results[0]["state"] == "completed"
        assert results[0]["orders_staged"] == 2

    def test_ignores_terminal_runs(self, db_session, default_portfolio, connection):
        _run_row(db_session, connection, default_portfolio, state="completed")
        _run_row(db_session, connection, default_portfolio, state="failed")
        _run_row(db_session, connection, default_portfolio, state="cancelled")
        _run_row(db_session, connection, default_portfolio, state="needs_review")

        with patch("t212_sync.advance_run") as advance:
            results = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))

        assert results == []
        advance.assert_not_called()

    def test_skips_a_run_whose_lease_is_still_held(self, db_session, default_portfolio, connection):
        run = _run_row(db_session, connection, default_portfolio, state="fetching")
        run.lease_token = t212_sync.uuid.uuid4()
        run.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=60)
        db_session.commit()

        with patch("t212_sync.advance_run") as advance:
            results = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))

        assert results == []
        advance.assert_not_called()

    def test_waiting_rate_limit_not_yet_due_is_skipped(self, db_session, default_portfolio, connection):
        _run_row(
            db_session, connection, default_portfolio, state="waiting_rate_limit",
            orders_rate_limit_reset_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        with patch("t212_sync.advance_run") as advance:
            results = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))
        assert results == []
        advance.assert_not_called()

    def test_waiting_rate_limit_past_reset_is_advanced(self, db_session, default_portfolio, connection):
        _run_row(
            db_session, connection, default_portfolio, state="waiting_rate_limit",
            orders_rate_limit_reset_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        fake_result = t212_sync.RunAdvanceResult(
            state="fetching", orders_staged=0, dividends_staged=0, rate_limited_streams=()
        )
        with patch("t212_sync.advance_run", return_value=fake_result) as advance:
            results = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))
        advance.assert_called_once()
        assert len(results) == 1

    def test_credential_rotation_cancels_a_stale_generation_run(
        self, db_session, default_portfolio, connection
    ):
        run = _run_row(db_session, connection, default_portfolio, state="fetching")
        connection.credential_generation = run.credential_generation + 1
        db_session.commit()

        with patch("t212_sync.advance_run") as advance:
            results = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))

        advance.assert_not_called()
        assert results == [{"run_id": str(run.public_id), "state": "cancelled"}]
        db_session.refresh(run)
        assert run.state == "cancelled"

    def test_deleted_connection_cancels_the_run(self, db_session, default_portfolio, connection):
        run = _run_row(db_session, connection, default_portfolio, state="fetching")
        db_session.delete(connection)
        db_session.commit()

        results = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))

        assert results == [{"run_id": str(run.public_id), "state": "cancelled"}]

    def test_exception_records_retry_and_error_without_crashing(
        self, db_session, default_portfolio, connection
    ):
        run = _run_row(db_session, connection, default_portfolio, state="pending")

        with patch("t212_sync.advance_run", side_effect=RuntimeError("boom")):
            results = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))

        assert len(results) == 1
        assert results[0]["error"] == "boom"
        db_session.refresh(run)
        assert run.retry_count == 1
        assert run.last_error == "boom"

    def test_respects_max_runs_budget(self, db_session, default_portfolio, connection):
        # Only the connection's one-active-run application logic normally
        # prevents piling up pending runs; simulate two due runs across
        # distinct connections instead, to exercise the max_runs cap in
        # isolation from that logic.
        other_portfolio = Portfolio(workspace_id=default_portfolio.workspace_id, name="Other 2")
        db_session.add(other_portfolio)
        db_session.commit()
        db_session.refresh(other_portfolio)
        other_conn = BrokerConnection(
            workspace_id=default_portfolio.workspace_id, portfolio_id=other_portfolio.id,
            broker="trading212", api_key="k" * 20,
        )
        db_session.add(other_conn)
        db_session.commit()
        db_session.refresh(other_conn)
        _run_row(db_session, connection, default_portfolio, state="pending")
        _run_row(db_session, other_conn, other_portfolio, state="pending")

        fake_result = t212_sync.RunAdvanceResult(
            state="fetching", orders_staged=0, dividends_staged=0, rate_limited_streams=()
        )
        with patch("t212_sync.advance_run", return_value=fake_result):
            results = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID, max_runs=1))

        assert len(results) == 1
