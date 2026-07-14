"""Tests for the global settings router (sync schedule)."""

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from jobs import mark_sync_ran
from routers.settings import SyncSchedule, get_sync_schedule, put_sync_schedule


def test_get_returns_defaults_on_fresh_db(db_session, monkeypatch):
    monkeypatch.delenv("BROKER_SYNC_TIMEZONE", raising=False)
    out = get_sync_schedule(db_session)
    assert out == {"mode": "daily", "daily_time": "02:00", "interval_hours": 6,
                   "timezone": "Europe/Prague", "last_run": None,
                   "next_run": None}  # never ran -> due now -> next_run null


def test_get_computes_next_run_after_a_sync(db_session):
    mark_sync_ran(db_session, datetime.now(timezone.utc))
    out = get_sync_schedule(db_session)
    assert out["last_run"] is not None
    assert out["next_run"] is not None  # just ran -> not due -> concrete next time


def test_put_persists_and_echoes(db_session):
    out = put_sync_schedule(
        SyncSchedule(mode="interval", daily_time="04:30", interval_hours=12), db_session)
    assert (out["mode"], out["daily_time"], out["interval_hours"]) == ("interval", "04:30", 12)
    # survives a fresh read
    again = get_sync_schedule(db_session)
    assert (again["mode"], again["daily_time"], again["interval_hours"]) == ("interval", "04:30", 12)


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
