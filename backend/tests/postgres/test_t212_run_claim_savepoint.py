"""claim_or_create_run's insert runs in a SAVEPOINT (review 2026-10-14, N11).

Two workers can both pass the "no active run" lookup and then insert; the second
insert hits the partial unique index from migration 0015
(uq_broker_sync_run_one_active_per_connection). It used to call db.rollback(),
which threw away everything the caller had already written in the same
transaction (sync_transactions' balance/positions snapshot) and, for a job
session, the transaction-local RLS context set by set_config -- so the re-query
found nothing under forced RLS and the sync failed.

The collision here is real: the second insert blocks on the first worker's
uncommitted row, then fails once that worker commits. The second worker runs as
the NOBYPASSRLS `portfyl_runtime` role, like a production job session.
"""

from __future__ import annotations

import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import Engine, delete, text
from sqlalchemy.orm import Session, sessionmaker

import jobs
import t212_sync
from models import (
    BrokerConnection, BrokerSyncEvent, BrokerSyncRun, Portfolio, Transaction, Workspace,
)

FINGERPRINT = "savepoint-account-fingerprint"


@pytest.fixture
def seeded(postgres_engine: Engine):
    with Session(postgres_engine, expire_on_commit=False) as db:
        workspace = Workspace(name=f"claim-savepoint-{uuid4().hex}")
        db.add(workspace)
        db.flush()
        portfolio = Portfolio(
            workspace_id=workspace.id, name="Default", is_default=True,
            t212_account_fingerprint=FINGERPRINT,
        )
        db.add(portfolio)
        db.flush()
        connection = BrokerConnection(
            workspace_id=workspace.id, portfolio_id=portfolio.id, broker="trading212",
            api_key="k" * 20, api_secret="", environment="live",
            account_fingerprint=FINGERPRINT,
        )
        db.add(connection)
        db.commit()
        ids = (workspace.id, portfolio.id, connection.id)
    try:
        yield ids
    finally:
        with Session(postgres_engine) as db:
            db.execute(delete(Workspace).where(Workspace.id == ids[0]))
            db.commit()


def _wait_until_a_session_waits_on_a_lock(postgres_engine: Engine, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    with postgres_engine.connect() as probe:
        while time.monotonic() < deadline:
            waiting = probe.execute(text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = current_database() AND wait_event_type = 'Lock'"
            )).scalar()
            probe.rollback()
            if waiting:
                return
            time.sleep(0.05)
    raise AssertionError("the second insert never blocked on the first worker's run")


def _job_session(postgres_engine: Engine):
    """A production-like job session: portfyl_runtime, real commits."""
    connection = postgres_engine.connect()
    connection.execute(text("SET ROLE portfyl_runtime"))
    connection.commit()
    return connection, sessionmaker(autocommit=False, autoflush=False, bind=connection)()


def _add_run(postgres_engine: Engine, ids, **overrides) -> int:
    workspace_id, portfolio_id, connection_id = ids
    with Session(postgres_engine) as db:
        connection = db.get(BrokerConnection, connection_id)
        run = BrokerSyncRun(
            workspace_id=workspace_id, portfolio_id=portfolio_id,
            connection_id=connection_id, broker="trading212",
            account_fingerprint=FINGERPRINT,
            credential_generation=connection.credential_generation,
            mode="incremental", **{"state": "pending", **overrides},
        )
        db.add(run)
        db.commit()
        return run.id


def _run_pass(postgres_engine: Engine, workspace_id):
    raw, db = _job_session(postgres_engine)
    try:
        return asyncio.run(jobs.broker_backfill_pass(db, workspace_id))
    finally:
        db.close()
        try:
            raw.execute(text("RESET ROLE"))
            raw.commit()
        finally:
            raw.close()


def _http_401():
    return HTTPException(status_code=401, detail="API key is invalid or expired")


class TestBackfillFailureStatesUnderForcedRls:
    """The new terminal/backoff writes happen right after a rollback, which
    drops the transaction-local RLS context: they must reassert it."""

    def test_rejected_credentials_fail_the_run_and_flag_the_connection(
        self, postgres_engine: Engine, seeded,
    ):
        workspace_id, _, connection_id = seeded
        run_id = _add_run(postgres_engine, seeded)

        with patch("t212_sync.advance_run", side_effect=_http_401()):
            results = _run_pass(postgres_engine, workspace_id)

        assert results[0]["error"] == t212_sync.HISTORY_CREDENTIALS_ERROR
        with Session(postgres_engine) as check:
            run = check.get(BrokerSyncRun, run_id)
            connection = check.get(BrokerConnection, connection_id)
            assert run.state == "failed"
            assert run.last_error == t212_sync.HISTORY_CREDENTIALS_ERROR
            assert connection.needs_attention is True
            assert connection.last_error == t212_sync.CONNECTION_CREDENTIALS_ERROR
        with patch("t212_sync.advance_run") as advance:
            assert _run_pass(postgres_engine, workspace_id) == []
        advance.assert_not_called()

    def test_finalize_value_error_parks_the_run_in_needs_review(
        self, postgres_engine: Engine, seeded,
    ):
        workspace_id, portfolio_id, _ = seeded
        run_id = _add_run(
            postgres_engine, seeded, state="finalizing",
            orders_complete=True, dividends_complete=True, cash_complete=True,
        )
        with Session(postgres_engine) as db:
            run = db.get(BrokerSyncRun, run_id)
            db.add(BrokerSyncEvent(
                workspace_id=workspace_id, portfolio_id=portfolio_id, run_id=run_id,
                broker="trading212", account_fingerprint=FINGERPRINT,
                stream="dividends", provider_event_id="dividend:no-amount",
                raw_payload={
                    "ticker": "AAPL_US_EQ", "grossAmountPerShare": 0.25, "quantity": 10,
                    "currency": "EUR", "paidOn": "2024-03-15T00:00:00Z",
                },
            ))
            db.commit()

        results = _run_pass(postgres_engine, workspace_id)

        assert results[0]["state"] == "needs_review"
        with Session(postgres_engine) as check:
            run = check.get(BrokerSyncRun, run_id)
            assert run.state == "needs_review"
            assert run.last_error == t212_sync.HISTORY_DATA_ERROR
            assert run.review_details[0]["date"] == "2024-03-15"
            assert run.review_details[0]["stream"] == "dividends"
            assert check.query(Transaction).filter(
                Transaction.workspace_id == workspace_id,
            ).count() == 0

    def test_transient_failures_back_off_then_stop(self, postgres_engine: Engine, seeded):
        workspace_id, _, _ = seeded
        run_id = _add_run(postgres_engine, seeded)

        with patch("t212_sync.advance_run", side_effect=RuntimeError("boom")) as advance:
            _run_pass(postgres_engine, workspace_id)
            _run_pass(postgres_engine, workspace_id)  # inside the 1 minute backoff

        assert advance.call_count == 1
        with Session(postgres_engine) as db:
            run = db.get(BrokerSyncRun, run_id)
            assert run.retry_count == 1
            assert run.last_error == t212_sync.HISTORY_RETRY_ERROR
            run.retry_count = jobs.BROKER_BACKFILL_MAX_RETRIES - 1
            run.updated_at = datetime.now(timezone.utc) - timedelta(hours=2)
            db.commit()

        with patch("t212_sync.advance_run", side_effect=RuntimeError("boom")):
            _run_pass(postgres_engine, workspace_id)

        with Session(postgres_engine) as check:
            run = check.get(BrokerSyncRun, run_id)
            assert run.state == "failed"
            assert run.last_error == t212_sync.HISTORY_RETRY_EXHAUSTED_ERROR

    def test_a_successful_step_resets_the_retry_count(self, postgres_engine: Engine, seeded):
        workspace_id, _, _ = seeded
        run_id = _add_run(postgres_engine, seeded, retry_count=3)
        with Session(postgres_engine) as db:
            db.get(BrokerSyncRun, run_id).updated_at = (
                datetime.now(timezone.utc) - timedelta(hours=2)
            )
            db.commit()

        step = t212_sync.RunAdvanceResult(
            state="fetching", orders_staged=5, dividends_staged=0, rate_limited_streams=(),
        )
        with patch("t212_sync.advance_run", return_value=step):
            _run_pass(postgres_engine, workspace_id)

        with Session(postgres_engine) as check:
            assert check.get(BrokerSyncRun, run_id).retry_count == 0


@pytest.mark.parametrize("job_context", [False, True], ids=["plain", "job-rls-context"])
def test_collision_keeps_the_snapshot_and_returns_the_winning_run(
    postgres_engine: Engine, seeded, job_context: bool,
):
    workspace_id, portfolio_id, connection_id = seeded
    outcome: dict = {}
    snapshot = "snapshot written before the collision"

    def second_worker() -> None:
        raw, db = _job_session(postgres_engine)
        try:
            jobs._set_job_workspace_context(db, workspace_id)
            connection = db.get(BrokerConnection, connection_id)
            portfolio = db.get(Portfolio, portfolio_id)
            # The caller's earlier write in this transaction (the snapshot).
            connection.last_error = snapshot
            db.flush()
            run = t212_sync.claim_or_create_run(db, connection, portfolio)
            outcome["run_id"] = run.id
            outcome["state"] = run.state
            outcome["context"] = db.execute(
                text("SELECT current_setting('portfyl.workspace_id', true)")
            ).scalar()
            if job_context:
                # The job path keeps querying tenant tables with the context
                # it set before the savepoint.
                outcome["visible_runs"] = db.query(BrokerSyncRun).filter(
                    BrokerSyncRun.workspace_id == workspace_id,
                ).count()
            db.commit()
        except BaseException as exc:  # surfaced in the main thread
            outcome["error"] = exc
        finally:
            db.close()
            try:
                raw.execute(text("RESET ROLE"))
                raw.commit()
            finally:
                raw.close()

    with Session(postgres_engine) as first:
        connection = first.get(BrokerConnection, connection_id)
        portfolio = first.get(Portfolio, portfolio_id)
        winner = t212_sync.claim_or_create_run(first, connection, portfolio)
        winner_id = winner.id  # flushed, not committed: the second insert will block

        thread = threading.Thread(target=second_worker)
        thread.start()
        _wait_until_a_session_waits_on_a_lock(postgres_engine)
        first.commit()
        thread.join(timeout=30)

    assert not thread.is_alive()
    assert "error" not in outcome, outcome.get("error")
    assert outcome["run_id"] == winner_id
    assert outcome["state"] == "pending"
    assert outcome["context"] == str(workspace_id)
    if job_context:
        assert outcome["visible_runs"] == 1

    with Session(postgres_engine) as check:
        assert check.get(BrokerConnection, connection_id).last_error == snapshot
        runs = check.query(BrokerSyncRun).filter(BrokerSyncRun.workspace_id == workspace_id).all()
        assert [r.id for r in runs] == [winner_id]
