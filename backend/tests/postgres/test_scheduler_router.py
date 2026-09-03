"""Postgres tests for POST /api/jobs/run (backend/routers/scheduler.py)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from database import get_db
from routers import scheduler


@pytest.fixture
def scheduler_client(postgres_engine) -> TestClient:
    app = FastAPI()
    app.include_router(scheduler.router, prefix="/api")

    def override_get_db():
        with Session(postgres_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client


def test_missing_token_is_rejected(scheduler_client):
    with patch("routers.scheduler.check_scheduler_token", return_value=False):
        response = scheduler_client.post("/api/jobs/run", params={"job": "alert_check"})
    assert response.status_code == 403


def test_valid_token_but_unknown_job_is_rejected(scheduler_client):
    with patch("routers.scheduler.check_scheduler_token", return_value=True):
        response = scheduler_client.post("/api/jobs/run", params={"job": "not_a_real_job"})
    assert response.status_code == 400


def test_valid_token_and_job_dispatches_and_returns_200(scheduler_client):
    fake = AsyncMock(return_value=[{"ticker": "AAPL"}])
    with patch("routers.scheduler.check_scheduler_token", return_value=True), \
         patch.dict(scheduler.JOB_REGISTRY, {"alert_check": fake}):
        response = scheduler_client.post(
            "/api/jobs/run",
            params={"job": "alert_check"},
            headers={"X-Scheduler-Token": "irrelevant-because-mocked"},
        )
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok", "job": "alert_check", "events": 1, "results": [{"ticker": "AAPL"}],
    }
    fake.assert_awaited_once()


def test_ibkr_scheduler_sync_route_no_longer_exists(postgres_engine):
    from routers import ibkr

    app = FastAPI()
    app.include_router(ibkr.router, prefix="/api")

    def override_get_db():
        with Session(postgres_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        response = client.post("/api/broker/ibkr/scheduler-sync")
    assert response.status_code == 404
