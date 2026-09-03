"""Postgres tests for job_runs claim/finish idempotency and dead-lettering
(backend/jobs.py's _claim_job_run/_finish_job_run) -- see
docs/superpowers/specs/2026-09-03-portfyl-job-triggering-design.md.

Reuses the seeding/session fixtures from test_job_workspace_isolation.py
rather than duplicating them -- see that module's docstring for why
runtime_job_session (real commits) is required here, not runtime_session
(savepoint-based, would give a false pass on the claim's own db.commit())."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from jobs import (
    JOB_RUN_STALE_AFTER,
    MAX_JOB_ATTEMPTS_PER_PERIOD,
    _claim_job_run,
    _finish_job_run,
    _set_job_workspace_context,
)
from tests.postgres.test_job_workspace_isolation import (
    _owner_session,
    runtime_job_session,
    single_workspace,
)


NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def test_second_claim_in_same_period_is_rejected(single_workspace, runtime_job_session: Session):
    ws, _ = single_workspace
    _set_job_workspace_context(runtime_job_session, ws.id)
    first = _claim_job_run(runtime_job_session, "autosync", ws.id, NOW)
    _set_job_workspace_context(runtime_job_session, ws.id)
    second = _claim_job_run(runtime_job_session, "autosync", ws.id, NOW)

    assert first is not None
    assert second is None


def test_new_period_allows_a_fresh_claim(single_workspace, runtime_job_session: Session):
    ws, _ = single_workspace
    _set_job_workspace_context(runtime_job_session, ws.id)
    first = _claim_job_run(runtime_job_session, "autosync", ws.id, NOW)
    later = NOW + timedelta(minutes=5)  # default autosync bucket is 300s
    _set_job_workspace_context(runtime_job_session, ws.id)
    second = _claim_job_run(runtime_job_session, "autosync", ws.id, later)

    assert first is not None and second is not None
    assert second[0] != first[0]


def test_finish_succeeded_persists_status(
    postgres_engine, single_workspace, runtime_job_session: Session,
):
    ws, _ = single_workspace
    _set_job_workspace_context(runtime_job_session, ws.id)
    run_id, _ = _claim_job_run(runtime_job_session, "autosync", ws.id, NOW)
    _set_job_workspace_context(runtime_job_session, ws.id)
    _finish_job_run(runtime_job_session, run_id, "succeeded")

    with _owner_session(postgres_engine) as db:
        row = db.execute(
            text("SELECT status, finished_at FROM job_runs WHERE id = :id"), {"id": run_id}
        ).one()
        assert row.status == "succeeded"
        assert row.finished_at is not None


def test_repeated_failures_reach_dead_letter_within_one_period(
    single_workspace, runtime_job_session: Session,
):
    ws, _ = single_workspace
    last_status = None
    for _ in range(MAX_JOB_ATTEMPTS_PER_PERIOD):
        _set_job_workspace_context(runtime_job_session, ws.id)
        claim = _claim_job_run(runtime_job_session, "autosync", ws.id, NOW)
        assert claim is not None
        run_id, attempt = claim
        _set_job_workspace_context(runtime_job_session, ws.id)
        last_status = "dead_letter" if attempt >= MAX_JOB_ATTEMPTS_PER_PERIOD else "failed"
        _finish_job_run(runtime_job_session, run_id, last_status, error="boom")

    assert last_status == "dead_letter"
    _set_job_workspace_context(runtime_job_session, ws.id)
    assert _claim_job_run(runtime_job_session, "autosync", ws.id, NOW) is None


def test_stale_running_row_can_be_reclaimed(
    postgres_engine, single_workspace, runtime_job_session: Session,
):
    ws, _ = single_workspace
    _set_job_workspace_context(runtime_job_session, ws.id)
    claim = _claim_job_run(runtime_job_session, "autosync", ws.id, NOW)
    assert claim is not None
    run_id, attempt = claim

    # Simulate a crashed worker: back-date started_at past the staleness
    # window without ever calling _finish_job_run.
    with _owner_session(postgres_engine) as db:
        db.execute(
            text("UPDATE job_runs SET started_at = :ts WHERE id = :id"),
            {"ts": NOW - JOB_RUN_STALE_AFTER - timedelta(minutes=1), "id": run_id},
        )
        db.commit()

    _set_job_workspace_context(runtime_job_session, ws.id)
    reclaimed = _claim_job_run(runtime_job_session, "autosync", ws.id, NOW)
    assert reclaimed is not None
    assert reclaimed == (run_id, attempt + 1)


from unittest.mock import AsyncMock, patch

from jobs import alert_check_all_workspaces


async def _run_twice(coro_fn, *args, **kwargs):
    first = await coro_fn(*args, **kwargs)
    second = await coro_fn(*args, **kwargs)
    return first, second


def test_alert_check_all_workspaces_skips_a_second_call_in_the_same_period(
    single_workspace, runtime_job_session: Session,
):
    # alert_check_all_workspaces does `from routers.alerts import run_check`
    # as a fresh local import on every call (see its lazy-import comment in
    # jobs.py) -- patch it at its origin, routers.alerts.run_check, not on
    # the jobs module, or the patch never takes effect.
    import asyncio
    ws, _ = single_workspace
    fake_run_check = AsyncMock(return_value=[{"ticker": "AAPL"}])
    with patch("routers.alerts.run_check", fake_run_check):
        first, second = asyncio.run(_run_twice(
            alert_check_all_workspaces, runtime_job_session, now=NOW))

    assert first == [{"ticker": "AAPL"}]
    assert second == []  # second call's claim for the same period is rejected
    assert fake_run_check.await_count == 1
