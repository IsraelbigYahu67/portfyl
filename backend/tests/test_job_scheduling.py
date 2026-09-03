"""Fast, DB-free tests for jobs.py's period-bucketing math."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime, timezone

from jobs import JOB_PERIOD_SECONDS, _period_start


def test_period_start_floors_to_the_bucket_boundary(monkeypatch):
    monkeypatch.delenv("AUTOSYNC_TRIGGER_INTERVAL_SECONDS", raising=False)
    now = datetime(2026, 1, 1, 12, 7, 30, tzinfo=timezone.utc)  # 300s bucket -> :05:00
    assert _period_start(now, "autosync") == datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc)


def test_period_start_respects_env_override(monkeypatch):
    monkeypatch.setenv("AUTOSYNC_TRIGGER_INTERVAL_SECONDS", "60")
    now = datetime(2026, 1, 1, 12, 7, 30, tzinfo=timezone.utc)
    assert _period_start(now, "autosync") == datetime(2026, 1, 1, 12, 7, 0, tzinfo=timezone.utc)


def test_job_period_seconds_has_exactly_the_three_job_types():
    assert set(JOB_PERIOD_SECONDS) == {"alert_check", "autosync", "dividend_notify"}
