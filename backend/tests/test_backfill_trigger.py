"""Tests for backfill_trigger: the Cloud Tasks wake-up that starts the cloud
broker_backfill job right after a sync instead of at the next hourly tick."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import httpx
import pytest

import backfill_trigger
import jobs as jobs_module
from models import BrokerConnection, BrokerSyncRun
from tests.helpers import TEST_WORKSPACE_ID

QUEUE = "projects/p/locations/europe-west1/queues/portfyl-backfill"
SERVICE = "https://portfyl.example.run.app"
CALLER = "portfyl-scheduler@p.iam.gserviceaccount.com"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("PORTFYL_BACKFILL_TASKS_QUEUE", QUEUE)
    monkeypatch.setenv("PORTFYL_SERVICE_URL", SERVICE)
    monkeypatch.setenv("PORTFYL_SCHEDULER_SERVICE_ACCOUNT", CALLER)
    monkeypatch.setattr(backfill_trigger, "_access_token", lambda: "token")


def _response(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "https://cloudtasks.googleapis.com"))


def test_noop_without_queue(monkeypatch):
    monkeypatch.delenv("PORTFYL_BACKFILL_TASKS_QUEUE", raising=False)
    with patch.object(backfill_trigger.httpx, "post") as post:
        assert backfill_trigger.request_backfill() is False
    post.assert_not_called()


def test_immediate_task_calls_the_job_with_scheduler_identity(configured):
    with patch.object(backfill_trigger.httpx, "post", return_value=_response(200)) as post:
        assert backfill_trigger.request_backfill() is True
    url = post.call_args.args[0]
    body = post.call_args.kwargs["json"]["task"]
    assert url == f"https://cloudtasks.googleapis.com/v2/{QUEUE}/tasks"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer token"
    assert body["httpRequest"] == {
        "httpMethod": "POST",
        "url": f"{SERVICE}/internal/jobs/broker_backfill",
        "oidcToken": {"serviceAccountEmail": CALLER, "audience": SERVICE},
    }
    # An immediate wake-up is never deduplicated away by a task name.
    assert "name" not in body
    assert "scheduleTime" not in body


def test_continuation_is_named_per_time_bucket(configured):
    at = datetime(2026, 11, 3, 19, 0, 40, tzinfo=timezone.utc)
    with patch.object(backfill_trigger.httpx, "post", return_value=_response(200)) as post:
        assert backfill_trigger.request_backfill(at=at) is True
    body = post.call_args.kwargs["json"]["task"]
    bucket = int(at.timestamp()) // backfill_trigger.CONTINUATION_BUCKET_SECONDS
    assert body["name"] == f"{QUEUE}/tasks/backfill-{bucket}"
    assert body["scheduleTime"] == "2026-11-03T19:00:40Z"


def test_already_queued_continuation_counts_as_success(configured):
    at = datetime.now(timezone.utc) + timedelta(minutes=1)
    with patch.object(backfill_trigger.httpx, "post", return_value=_response(409)):
        assert backfill_trigger.request_backfill(at=at) is True


@pytest.mark.parametrize("failure", [_response(500), httpx.ConnectError("down")])
def test_failure_never_raises(configured, failure):
    kwargs = {"side_effect": failure} if isinstance(failure, Exception) else {"return_value": failure}
    with patch.object(backfill_trigger.httpx, "post", **kwargs):
        assert backfill_trigger.request_backfill() is False


# --- continuation after a cloud pass --------------------------------------


@pytest.fixture
def connection(db_session, default_portfolio):
    default_portfolio.t212_account_fingerprint = "fp"
    conn = BrokerConnection(
        workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
        broker="trading212", api_key="k" * 20, account_fingerprint="fp",
    )
    db_session.add(conn)
    db_session.commit()
    db_session.refresh(conn)
    return conn


def _run_row(db, connection, portfolio, *, state, **overrides):
    row = BrokerSyncRun(
        workspace_id=connection.workspace_id, portfolio_id=portfolio.id,
        connection_id=connection.id, broker="trading212",
        account_fingerprint=connection.account_fingerprint,
        credential_generation=connection.credential_generation,
        mode="incremental", state=state, **overrides,
    )
    db.add(row)
    db.commit()
    return row


async def _no_events(*_args, **_kwargs):
    return []


def _cloud_pass(db):
    with patch.object(jobs_module, "broker_backfill_pass", new=_no_events), \
            patch.object(jobs_module, "_active_workspace_ids", return_value=[TEST_WORKSPACE_ID]), \
            patch("backfill_trigger.request_backfill") as request:
        asyncio.run(jobs_module.broker_backfill_all_workspaces(db))
    return request


def test_next_due_is_none_without_open_runs(db_session, connection, default_portfolio):
    _run_row(db_session, connection, default_portfolio, state="completed")
    assert jobs_module.broker_backfill_next_due(db_session, TEST_WORKSPACE_ID) is None


def test_next_due_waits_for_the_rate_limit_reset(db_session, connection, default_portfolio):
    now = datetime(2026, 11, 3, 19, 0, tzinfo=timezone.utc)
    reset = now + timedelta(seconds=55)
    _run_row(
        db_session, connection, default_portfolio, state="waiting_rate_limit",
        orders_rate_limit_reset_at=now + timedelta(seconds=10),
        cash_rate_limit_reset_at=reset,
    )
    assert jobs_module.broker_backfill_next_due(db_session, TEST_WORKSPACE_ID, now=now) == reset


def test_next_due_is_now_for_a_runnable_run(db_session, connection, default_portfolio):
    now = datetime(2026, 11, 3, 19, 0, tzinfo=timezone.utc)
    _run_row(db_session, connection, default_portfolio, state="fetching")
    assert jobs_module.broker_backfill_next_due(db_session, TEST_WORKSPACE_ID, now=now) == now


def test_next_due_respects_retry_backoff(db_session, connection, default_portfolio):
    now = datetime(2026, 11, 3, 19, 0, tzinfo=timezone.utc)
    _run_row(
        db_session, connection, default_portfolio, state="fetching",
        retry_count=2, updated_at=now.replace(tzinfo=None),
    )
    due = jobs_module.broker_backfill_next_due(db_session, TEST_WORKSPACE_ID, now=now)
    assert due == now + timedelta(seconds=jobs_module.backfill_backoff_seconds(2))


def test_cloud_pass_schedules_a_continuation(configured, db_session, connection, default_portfolio):
    _run_row(db_session, connection, default_portfolio, state="waiting_rate_limit",
             cash_rate_limit_reset_at=datetime.now(timezone.utc) + timedelta(seconds=40))
    request = _cloud_pass(db_session)
    request.assert_called_once()
    at = request.call_args.kwargs["at"]
    now = datetime.now(timezone.utc)
    # Never sooner than the minimum gap, never later than the reset needs.
    assert now + timedelta(seconds=backfill_trigger.MIN_CONTINUATION_SECONDS - 2) <= at
    assert at <= now + timedelta(seconds=45)


def test_cloud_pass_does_not_reschedule_when_done(configured, db_session, connection, default_portfolio):
    _run_row(db_session, connection, default_portfolio, state="completed")
    _cloud_pass(db_session).assert_not_called()


def test_far_future_work_is_left_to_the_hourly_job(configured, db_session, connection, default_portfolio):
    _run_row(db_session, connection, default_portfolio, state="waiting_rate_limit",
             cash_rate_limit_reset_at=datetime.now(timezone.utc) + timedelta(hours=3))
    _cloud_pass(db_session).assert_not_called()
