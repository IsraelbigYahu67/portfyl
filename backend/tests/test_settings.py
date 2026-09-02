"""Tests for the workspace-scoped settings router (sync schedule)."""

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from jobs import mark_sync_ran
from routers.settings import SyncSchedule, get_sync_schedule, put_sync_schedule


def test_get_returns_defaults_on_fresh_db(db_session, request_context, monkeypatch):
    monkeypatch.delenv("BROKER_SYNC_TIMEZONE", raising=False)
    out = get_sync_schedule(db_session, request_context)
    assert out == {"mode": "daily", "daily_time": "02:00", "interval_hours": 6,
                   "timezone": "Europe/Prague", "last_run": None,
                   "next_run": None}  # never ran -> due now -> next_run null


def test_get_computes_next_run_after_a_sync(db_session, request_context):
    mark_sync_ran(db_session, request_context.workspace.id, datetime.now(timezone.utc))
    out = get_sync_schedule(db_session, request_context)
    assert out["last_run"] is not None
    assert out["next_run"] is not None  # just ran -> not due -> concrete next time


def test_put_persists_and_echoes(db_session, request_context):
    out = put_sync_schedule(
        SyncSchedule(mode="interval", daily_time="04:30", interval_hours=12),
        db_session, request_context)
    assert (out["mode"], out["daily_time"], out["interval_hours"]) == ("interval", "04:30", 12)
    # survives a fresh read
    again = get_sync_schedule(db_session, request_context)
    assert (again["mode"], again["daily_time"], again["interval_hours"]) == ("interval", "04:30", 12)


def test_schedule_is_isolated_per_workspace(db_session, request_context):
    from uuid import uuid4
    from models import Workspace
    from tenancy import RequestContext

    other_workspace = Workspace(id=uuid4(), name="Other workspace")
    db_session.add(other_workspace)
    db_session.flush()
    other_context = RequestContext(
        user=request_context.user,
        workspace=other_workspace,
        membership=request_context.membership,
        session=request_context.session,
    )

    put_sync_schedule(
        SyncSchedule(mode="interval", daily_time="04:30", interval_hours=12),
        db_session, request_context)

    default_for_other = get_sync_schedule(db_session, other_context)
    assert (default_for_other["mode"], default_for_other["daily_time"],
            default_for_other["interval_hours"]) == ("daily", "02:00", 6)


@pytest.mark.parametrize("bad", [
    {"mode": "weekly", "daily_time": "02:00", "interval_hours": 6},
    {"mode": "daily", "daily_time": "25:00", "interval_hours": 6},
    {"mode": "daily", "daily_time": "2am", "interval_hours": 6},
    {"mode": "daily", "daily_time": "02:00", "interval_hours": 0},
    {"mode": "daily", "daily_time": "02:00", "interval_hours": 200},
])
def test_put_payload_validation(bad):
    with pytest.raises(ValidationError):
        SyncSchedule(**bad)
