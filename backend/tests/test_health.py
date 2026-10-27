from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jobs import mark_job_succeeded
from main import health


def test_health_is_ok_when_database_and_all_job_passes_are_fresh(db_session):
    now = datetime.now(timezone.utc)
    for name in ("alerts", "autosync", "dividends", "broker_backfill"):
        mark_job_succeeded(db_session, name, now)
    db_session.commit()

    result = health(db_session)

    assert result["status"] == "ok"
    assert result["checks"]["database"]["status"] == "ok"
    assert result["checks"]["scheduler"]["status"] == "ok"


def test_health_names_a_stale_job(db_session):
    now = datetime.now(timezone.utc)
    mark_job_succeeded(db_session, "alerts", now - timedelta(hours=1))
    mark_job_succeeded(db_session, "autosync", now)
    mark_job_succeeded(db_session, "dividends", now)
    db_session.commit()

    result = health(db_session)

    assert result["status"] == "degraded"
    assert result["checks"]["scheduler"]["jobs"]["alerts"]["status"] == "stale"


def test_livez_takes_no_dependencies_so_it_never_touches_the_database():
    import inspect

    from main import livez

    assert inspect.signature(livez).parameters == {}
    assert livez() == {"status": "ok"}


def test_livez_is_served_as_json_not_swallowed_by_the_spa_fallback():
    from fastapi.testclient import TestClient

    from main import app

    response = TestClient(app).get("/livez")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"status": "ok"}


def test_health_names_database_failure_without_leaking_exception_text():
    class BrokenSession:
        def execute(self, _statement):
            raise RuntimeError("postgres://user:secret@host/database")

    result = health(BrokenSession())

    assert result == {
        "status": "degraded",
        "checks": {
            "database": {"status": "error", "error_type": "RuntimeError"},
            "scheduler": {"status": "unavailable"},
        },
    }
    assert "secret" not in str(result)
