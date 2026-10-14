"""Cloud Scheduler-triggered internal job endpoints: OIDC auth and
edition-conditional mounting. Advisory-lock behavior needs real PostgreSQL
(pg_try_advisory_lock doesn't exist in the fast suite's SQLite fixture) --
see tests/postgres/test_job_advisory_lock.py."""
from __future__ import annotations

import asyncio
import importlib
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import NullPool

import routers.internal_jobs as internal_jobs


class TestVerifySchedulerToken:
    def test_missing_header_is_401(self):
        with pytest.raises(HTTPException) as exc_info:
            internal_jobs.verify_scheduler_token(None)
        assert exc_info.value.status_code == 401

    def test_non_bearer_header_is_401(self):
        with pytest.raises(HTTPException) as exc_info:
            internal_jobs.verify_scheduler_token("Basic dXNlcjpwYXNz")
        assert exc_info.value.status_code == 401

    def test_missing_configuration_is_403(self, monkeypatch):
        monkeypatch.delenv("PORTFYL_SERVICE_URL", raising=False)
        monkeypatch.delenv("PORTFYL_SCHEDULER_SERVICE_ACCOUNT", raising=False)
        with pytest.raises(HTTPException) as exc_info:
            internal_jobs.verify_scheduler_token("Bearer sometoken")
        assert exc_info.value.status_code == 403

    def test_token_that_fails_google_verification_is_403(self, monkeypatch):
        monkeypatch.setenv("PORTFYL_SERVICE_URL", "https://portfyl-abc.run.app")
        monkeypatch.setenv("PORTFYL_SCHEDULER_SERVICE_ACCOUNT", "portfyl-scheduler@p.iam.gserviceaccount.com")
        with patch.object(internal_jobs.google_id_token, "verify_oauth2_token", side_effect=ValueError("bad token")):
            with pytest.raises(HTTPException) as exc_info:
                internal_jobs.verify_scheduler_token("Bearer garbage")
        assert exc_info.value.status_code == 403

    def test_token_for_the_wrong_identity_is_403(self, monkeypatch):
        monkeypatch.setenv("PORTFYL_SERVICE_URL", "https://portfyl-abc.run.app")
        monkeypatch.setenv("PORTFYL_SCHEDULER_SERVICE_ACCOUNT", "portfyl-scheduler@p.iam.gserviceaccount.com")
        claims = {"email": "someone-else@p.iam.gserviceaccount.com", "email_verified": True}
        with patch.object(internal_jobs.google_id_token, "verify_oauth2_token", return_value=claims):
            with pytest.raises(HTTPException) as exc_info:
                internal_jobs.verify_scheduler_token("Bearer validlyformattedtoken")
        assert exc_info.value.status_code == 403

    def test_valid_token_for_the_expected_identity_passes(self, monkeypatch):
        monkeypatch.setenv("PORTFYL_SERVICE_URL", "https://portfyl-abc.run.app")
        monkeypatch.setenv("PORTFYL_SCHEDULER_SERVICE_ACCOUNT", "portfyl-scheduler@p.iam.gserviceaccount.com")
        claims = {"email": "portfyl-scheduler@p.iam.gserviceaccount.com", "email_verified": True}
        with patch.object(internal_jobs.google_id_token, "verify_oauth2_token", return_value=claims):
            internal_jobs.verify_scheduler_token("Bearer validlyformattedtoken")  # does not raise


class TestJobDatabaseConfiguration:
    def test_missing_direct_job_database_url_fails_closed(self):
        with pytest.raises(RuntimeError, match="JOB_DATABASE_URL is required"):
            internal_jobs.build_job_session_factory({"PORTFYL_EDITION": "cloud"})

    def test_neon_pooler_url_is_rejected(self):
        with pytest.raises(RuntimeError, match="direct Neon hostname"):
            internal_jobs.build_job_session_factory({
                "PORTFYL_EDITION": "cloud",
                "JOB_DATABASE_URL": (
                    "postgresql://user:pass@ep-example-pooler.eu-central-1.aws.neon.tech/db"
                ),
            })


class TestJobLockEngine:
    def test_lock_engine_uses_a_null_pool(self):
        engine = internal_jobs.build_job_lock_engine({
            "PORTFYL_EDITION": "cloud",
            "JOB_DATABASE_URL": "postgresql://user:pass@db.example.com/portfyl",
        })
        try:
            assert isinstance(engine.pool, NullPool)
            assert engine.dialect.name == "postgresql"
        finally:
            engine.dispose()

    def test_lock_engine_applies_the_same_fail_closed_checks(self):
        with pytest.raises(RuntimeError, match="JOB_DATABASE_URL is required"):
            internal_jobs.build_job_lock_engine({"PORTFYL_EDITION": "cloud"})
        with pytest.raises(RuntimeError, match="direct Neon hostname"):
            internal_jobs.build_job_lock_engine({
                "PORTFYL_EDITION": "cloud",
                "JOB_DATABASE_URL": "postgresql://u:p@ep-example-pooler.eu.aws.neon.tech/db",
            })

    def test_lock_is_a_no_op_without_a_postgres_engine(self):
        # PORTFYL_TESTING=1 (set by conftest) resolves no lock engine at all,
        # so the fast suite's SQLite fixture trivially "acquires" the lock.
        with internal_jobs.with_job_lock("alerts") as acquired:
            assert acquired is True
        with internal_jobs.with_job_lock("alerts") as nested:
            assert nested is True  # nothing is actually held

    def test_lock_is_a_no_op_for_a_non_postgres_engine(self, db_session):
        with internal_jobs.with_job_lock("alerts", db_session.get_bind()) as acquired:
            assert acquired is True


class TestJobEndpointsRunExactlyOnePass:
    @pytest.fixture(autouse=True)
    def _job_session(self, monkeypatch, db_session):
        # Task 7 persists a JobRun heartbeat after each successful pass.  The
        # endpoint must use this test's migrated metadata-backed session rather
        # than database.SessionLocal's otherwise-empty in-memory connection.
        monkeypatch.setattr(internal_jobs, "SessionLocal", lambda: db_session)

    def test_alerts_endpoint_runs_the_pass_and_returns_a_summary(self, monkeypatch):
        monkeypatch.setattr(internal_jobs, "verify_scheduler_token", lambda auth: None)
        pass_fn = AsyncMock(return_value=[{"triggered": 1}])
        with patch("jobs.alert_check_all_workspaces", pass_fn):
            result = internal_jobs.run_alerts_job(authorization="Bearer x")
        pass_fn.assert_awaited_once()
        assert result == {"job": "alerts", "events": 1}

    def test_autosync_endpoint_runs_the_pass(self, monkeypatch):
        monkeypatch.setattr(internal_jobs, "verify_scheduler_token", lambda auth: None)
        pass_fn = AsyncMock(return_value=[])
        with patch("jobs.autosync_all_workspaces", pass_fn):
            result = internal_jobs.run_autosync_job(authorization="Bearer x")
        pass_fn.assert_awaited_once()
        assert result == {"job": "autosync", "events": 0}

    def test_dividends_endpoint_runs_the_pass(self, monkeypatch):
        monkeypatch.setattr(internal_jobs, "verify_scheduler_token", lambda auth: None)
        pass_fn = AsyncMock(return_value=[])
        with patch("jobs.dividend_notify_all_workspaces", pass_fn):
            result = internal_jobs.run_dividends_job(authorization="Bearer x")
        pass_fn.assert_awaited_once()
        assert result == {"job": "dividends", "events": 0}

    def test_rate_limit_cleanup_endpoint_runs_the_pass(self, monkeypatch):
        monkeypatch.setattr(internal_jobs, "verify_scheduler_token", lambda auth: None)
        pass_fn = AsyncMock(return_value=[{"deleted": 42}])
        with patch("jobs.rate_limit_cleanup_pass", pass_fn):
            result = internal_jobs.run_rate_limit_cleanup_job(authorization="Bearer x")
        pass_fn.assert_awaited_once()
        assert result == {"job": "rate_limit_cleanup", "events": 1}

    def test_account_deletion_cleanup_endpoint_runs_the_pass(self, monkeypatch):
        monkeypatch.setattr(internal_jobs, "verify_scheduler_token", lambda auth: None)
        pass_fn = AsyncMock(return_value=[])
        with patch("jobs.account_deletion_cleanup_pass", pass_fn):
            result = internal_jobs.run_account_deletion_cleanup_job(
                authorization="Bearer x"
            )
        pass_fn.assert_awaited_once()
        assert result == {"job": "account_deletion_cleanup", "events": 0}

    def test_heartbeat_is_recorded_only_after_a_successful_pass(self, monkeypatch):
        monkeypatch.setattr(internal_jobs, "verify_scheduler_token", lambda auth: None)
        calls = []
        pass_fn = AsyncMock(side_effect=lambda db: calls.append("pass") or [])
        mark = lambda db, name: calls.append(f"mark:{name}")  # noqa: E731
        with patch("jobs.alert_check_all_workspaces", pass_fn), \
             patch("jobs.mark_job_succeeded", mark):
            internal_jobs.run_alerts_job(authorization="Bearer x")
        assert calls == ["pass", "mark:alerts"]

    def test_failed_pass_never_marks_the_job_succeeded(self, monkeypatch):
        monkeypatch.setattr(internal_jobs, "verify_scheduler_token", lambda auth: None)
        pass_fn = AsyncMock(side_effect=RuntimeError("pass failed"))
        mark = patch("jobs.mark_job_succeeded")
        with patch("jobs.alert_check_all_workspaces", pass_fn), mark as marked:
            with pytest.raises(RuntimeError, match="pass failed"):
                internal_jobs.run_alerts_job(authorization="Bearer x")
        marked.assert_not_called()

    def test_skipped_invocation_neither_runs_the_pass_nor_marks_success(self, monkeypatch):
        monkeypatch.setattr(internal_jobs, "verify_scheduler_token", lambda auth: None)

        @contextmanager
        def lock_held_elsewhere(job_name, engine=None):
            yield False

        monkeypatch.setattr(internal_jobs, "with_job_lock", lock_held_elsewhere)
        pass_fn = AsyncMock(return_value=[])
        with patch("jobs.alert_check_all_workspaces", pass_fn), \
             patch("jobs.mark_job_succeeded") as marked:
            result = internal_jobs.run_alerts_job(authorization="Bearer x")
        assert result == {"job": "alerts", "skipped": "already running"}
        pass_fn.assert_not_awaited()
        marked.assert_not_called()

    def test_job_session_is_closed_before_the_lock_is_released(self, monkeypatch, db_session):
        monkeypatch.setattr(internal_jobs, "verify_scheduler_token", lambda auth: None)
        events = []

        @contextmanager
        def recording_lock(job_name, engine=None):
            events.append("lock")
            try:
                yield True
            finally:
                events.append("unlock")

        monkeypatch.setattr(internal_jobs, "with_job_lock", recording_lock)
        monkeypatch.setattr(db_session, "close", lambda: events.append("session-close"))
        with patch("jobs.alert_check_all_workspaces", AsyncMock(return_value=[])):
            internal_jobs.run_alerts_job(authorization="Bearer x")
        assert events == ["lock", "session-close", "unlock"]

    def test_unverified_request_never_reaches_the_pass(self, monkeypatch):
        pass_fn = AsyncMock(return_value=[])
        with patch("jobs.alert_check_all_workspaces", pass_fn):
            with pytest.raises(HTTPException) as exc_info:
                internal_jobs.run_alerts_job(authorization=None)
        assert exc_info.value.status_code == 401
        pass_fn.assert_not_awaited()


def _reload_main(monkeypatch, edition: str):
    monkeypatch.setenv("PORTFYL_EDITION", edition)
    import main

    return importlib.reload(main)


class TestEditionConditionalMounting:
    def test_router_is_absent_in_the_local_edition(self, monkeypatch):
        try:
            main = _reload_main(monkeypatch, "local")
            from fastapi.testclient import TestClient

            client = TestClient(main.app)
            # 404 when frontend/dist isn't built; 405 when it is and the SPA
            # catch-all GET route matches the path but not POST -- either
            # way, internal_jobs.router never handled this request.
            assert client.post("/internal/jobs/alerts").status_code in (404, 405)
        finally:
            _reload_main(monkeypatch, "local")

    def test_router_is_present_but_requires_auth_in_the_cloud_edition(self, monkeypatch):
        try:
            main = _reload_main(monkeypatch, "cloud")
            from fastapi.testclient import TestClient

            client = TestClient(main.app)
            response = client.post("/internal/jobs/alerts")
            assert response.status_code == 401  # exists, but unauthenticated
            assert "/internal/jobs/billing" not in main.app.openapi()["paths"]
            assert client.post("/internal/jobs/billing").status_code in (404, 405)
        finally:
            _reload_main(monkeypatch, "local")

    def test_local_edition_registers_in_process_pollers(self, monkeypatch):
        try:
            main = _reload_main(monkeypatch, "local")
            monkeypatch.setattr(main, "assert_alembic_head", lambda db: None)
            asyncio.run(main._start_background_pollers())
            assert len(main._BG_TASKS) == 4
        finally:
            for task in main._BG_TASKS:
                task.cancel()
            main._BG_TASKS.clear()
            _reload_main(monkeypatch, "local")

    def test_cloud_edition_never_registers_in_process_pollers(self, monkeypatch):
        try:
            main = _reload_main(monkeypatch, "cloud")
            monkeypatch.setattr(main, "assert_alembic_head", lambda db: None)
            asyncio.run(main._start_background_pollers())
            assert main._BG_TASKS == []
        finally:
            _reload_main(monkeypatch, "local")
