"""Tests for jobs.broker_backfill_pass (T212 snapshot-first sync, Task 3).

Network (t212_sync.advance_run's httpx calls) is always patched -- this file
tests the job's orchestration (which runs get claimed/skipped/cancelled),
not the page-fetching mechanics already covered by test_t212_sync_runs.py.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

import t212_sync
from jobs import broker_backfill_pass
from models import BrokerConnection, BrokerSyncEvent, BrokerSyncRun, Portfolio, Transaction
from tests.helpers import TEST_WORKSPACE_ID


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def connection(db_session, default_portfolio):
    fingerprint = "account-fingerprint-1"
    default_portfolio.t212_account_fingerprint = fingerprint
    conn = BrokerConnection(
        workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
        broker="trading212", api_key="k" * 20, account_fingerprint=fingerprint,
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
        account_fingerprint=connection.account_fingerprint,
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

    def test_staged_run_is_finalized_once_before_last_synced_is_set(
        self, db_session, default_portfolio, connection
    ):
        run = _run_row(db_session, connection, default_portfolio, state="pending")

        def finish_staging(db, staged_run, *_args, **_kwargs):
            staged_run.orders_complete = True
            staged_run.dividends_complete = True
            staged_run.state = "finalizing"
            db.commit()
            return t212_sync.RunAdvanceResult(
                state="finalizing",
                orders_staged=0,
                dividends_staged=0,
                rate_limited_streams=(),
            )

        with patch("t212_sync.advance_run", side_effect=finish_staging), \
             patch("t212_sync.finalize_run", wraps=t212_sync.finalize_run) as finalize:
            first = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))
            second = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))

        finalize.assert_called_once()
        db_session.refresh(run)
        db_session.refresh(connection)
        assert first[0]["state"] == "completed"
        assert second == []
        assert run.state == "completed"
        assert run.completed_at is not None
        assert connection.last_synced_at == run.completed_at

    def test_finalizing_run_resumes_finalization_without_fetching_more_pages(
        self, db_session, default_portfolio, connection
    ):
        run = _run_row(
            db_session,
            connection,
            default_portfolio,
            state="finalizing",
            orders_complete=True,
            dividends_complete=True,
        )

        with patch("t212_sync.advance_run") as advance, \
             patch("t212_sync.finalize_run", wraps=t212_sync.finalize_run) as finalize:
            results = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))

        advance.assert_not_called()
        finalize.assert_called_once()
        db_session.refresh(run)
        assert results[0]["state"] == "completed"
        assert run.state == "completed"

    def test_corporate_action_run_ends_needs_review_not_completed(
        self, db_session, default_portfolio, connection
    ):
        run = _run_row(
            db_session, connection, default_portfolio, state="finalizing",
            orders_complete=True, dividends_complete=True,
        )
        db_session.add(BrokerSyncEvent(
            workspace_id=run.workspace_id, portfolio_id=run.portfolio_id, run_id=run.id,
            broker="trading212", account_fingerprint=run.account_fingerprint,
            stream="orders", provider_event_id="fill:split",
            raw_payload={
                "order": {"id": "o1", "status": "FILLED", "ticker": "NVDA_US_EQ",
                          "side": "BUY", "createdAt": "2024-06-10T10:00:00Z",
                          "instrument": {"currency": "USD"}},
                "fill": {"id": "split", "quantity": 90, "price": 0,
                         "filledAt": "2024-06-10T10:00:00Z", "type": "STOCK_SPLIT"},
            },
        ))
        db_session.commit()

        first = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))
        second = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))

        db_session.refresh(run)
        db_session.refresh(connection)
        assert first[0]["state"] == "needs_review"
        assert second == []
        assert run.state == "needs_review"
        assert run.completed_at is None
        assert connection.last_synced_at is None
        assert db_session.query(Transaction).count() == 0

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

    def test_after_reset_resumes_from_saved_next_page_without_dead_letter_failure(
        self, db_session, default_portfolio, connection
    ):
        checkpoint = "/equity/history/orders?cursor=resume-me&limit=50"
        run = _run_row(
            db_session,
            connection,
            default_portfolio,
            state="waiting_rate_limit",
            orders_next_page_path=checkpoint,
            orders_rate_limit_reset_at=datetime.now(timezone.utc) - timedelta(seconds=1),
            dividends_complete=True,
        )
        response = MagicMock(status_code=200, headers={})
        response.json.return_value = {"items": [], "nextPagePath": None}

        with patch("t212_sync.httpx.get", return_value=response) as fetch:
            results = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))

        fetch.assert_called_once_with(
            f"https://live.trading212.com/api/v0{checkpoint}",
            headers=t212_sync._t212_headers(connection.api_key, connection.api_secret or ""),
            timeout=15,
        )
        db_session.refresh(run)
        db_session.refresh(connection)
        assert results[0]["state"] == "completed"
        assert run.state == "completed"
        assert connection.consecutive_failures == 0
        assert connection.needs_attention is False

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

    def test_account_binding_mismatch_cancels_the_run(
        self, db_session, default_portfolio, connection
    ):
        run = _run_row(db_session, connection, default_portfolio, state="fetching")
        default_portfolio.t212_account_fingerprint = "different-account"
        db_session.commit()

        with patch("t212_sync.advance_run") as advance:
            results = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))

        advance.assert_not_called()
        assert results == [{"run_id": str(run.public_id), "state": "cancelled"}]

    def test_exception_records_retry_and_error_without_crashing(
        self, db_session, default_portfolio, connection
    ):
        run = _run_row(db_session, connection, default_portfolio, state="pending")

        with patch("t212_sync.advance_run", side_effect=RuntimeError("boom")):
            results = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))

        assert len(results) == 1
        assert results[0]["error"] == t212_sync.HISTORY_RETRY_ERROR
        db_session.refresh(run)
        assert run.retry_count == 1
        assert run.last_error == t212_sync.HISTORY_RETRY_ERROR

    def test_finalization_failure_stays_retryable_and_redacts_provider_url(
        self, db_session, default_portfolio, connection
    ):
        run = _run_row(
            db_session,
            connection,
            default_portfolio,
            state="finalizing",
            orders_complete=True,
            dividends_complete=True,
        )
        raw_error = (
            "500 for https://live.trading212.com/api/v0/equity/history/orders"
            "?cursor=private-cursor"
        )

        with patch("t212_sync.finalize_run", side_effect=RuntimeError(raw_error)):
            results = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))

        db_session.refresh(run)
        db_session.refresh(connection)
        assert run.state == "finalizing"
        assert run.retry_count == 1
        assert run.last_error == "Trading 212 history sync will retry automatically."
        assert results == [{
            "run_id": str(run.public_id),
            "error": "Trading 212 history sync will retry automatically.",
        }]
        assert connection.last_synced_at is None

    def test_respects_max_runs_budget(self, db_session, default_portfolio, connection):
        # Only the connection's one-active-run application logic normally
        # prevents piling up pending runs; simulate two due runs across
        # distinct connections instead, to exercise the max_runs cap in
        # isolation from that logic.
        other_portfolio = Portfolio(workspace_id=default_portfolio.workspace_id, name="Other 2")
        other_portfolio.t212_account_fingerprint = "account-fingerprint-2"
        db_session.add(other_portfolio)
        db_session.commit()
        db_session.refresh(other_portfolio)
        other_conn = BrokerConnection(
            workspace_id=default_portfolio.workspace_id, portfolio_id=other_portfolio.id,
            broker="trading212", api_key="k" * 20,
            account_fingerprint=other_portfolio.t212_account_fingerprint,
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


class TestBackfillNeverCreatesRuns:
    """Plan 2026-09-24 Task C3: only a sync (manual, or autosync for auto_sync
    connections) or an explicit retry creates runs, so a connection with
    auto-sync disabled never triggers unrequested broker access."""

    def test_backfill_never_creates_runs(self, db_session, default_portfolio, connection):
        assert connection.auto_sync in (None, False)

        results = _run(broker_backfill_pass(db_session, TEST_WORKSPACE_ID))

        assert results == []
        assert db_session.query(BrokerSyncRun).count() == 0
