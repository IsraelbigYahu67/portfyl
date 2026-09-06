"""main.py: the cloud-only rate-limit gate's registration position relative
to CORSMiddleware, its exception handlers, and the cloud-only
rate_limit_cleanup entry in _JOB_MAX_AGES."""
from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

import edge_trust
import rate_limit
from database import get_db
from rate_limit import RateLimitRule


def _reload_main(monkeypatch, edition: str):
    monkeypatch.setenv("PORTFYL_EDITION", edition)
    import main

    return importlib.reload(main)


def test_local_edition_never_registers_the_gate_middleware(monkeypatch):
    try:
        main = _reload_main(monkeypatch, "local")
        middleware_classes = {m.cls for m in main.app.user_middleware}
        from cloud_gate import CloudApiGateMiddleware

        assert CloudApiGateMiddleware not in middleware_classes
    finally:
        _reload_main(monkeypatch, "local")


def test_cloud_edition_registers_the_gate_more_inner_than_cors(monkeypatch):
    try:
        main = _reload_main(monkeypatch, "cloud")
        from cloud_gate import CloudApiGateMiddleware
        from fastapi.middleware.cors import CORSMiddleware

        classes = [m.cls for m in main.app.user_middleware]
        # user_middleware is listed outermost-first; the gate must appear
        # AFTER CORSMiddleware in this list (i.e. it is more inner / closer
        # to routing), so CORS still wraps the gate's direct error responses.
        assert classes.index(CORSMiddleware) < classes.index(CloudApiGateMiddleware)
    finally:
        _reload_main(monkeypatch, "local")


def test_cloud_health_thresholds_include_rate_limit_cleanup(monkeypatch):
    try:
        main = _reload_main(monkeypatch, "cloud")
        assert "rate_limit_cleanup" in main._JOB_MAX_AGES
    finally:
        _reload_main(monkeypatch, "local")


def test_local_health_thresholds_never_include_rate_limit_cleanup(monkeypatch):
    try:
        main = _reload_main(monkeypatch, "local")
        assert "rate_limit_cleanup" not in main._JOB_MAX_AGES
    finally:
        _reload_main(monkeypatch, "local")


def test_full_app_gate_wraps_routing_and_cors_survives_a_429(monkeypatch, db_session):
    try:
        main = _reload_main(monkeypatch, "cloud")
        main.app.dependency_overrides[get_db] = lambda: db_session
        monkeypatch.setattr(edge_trust, "EDGE_TOKEN", "test-edge-token")
        monkeypatch.setattr(
            rate_limit,
            "RATE_LIMIT_RULES",
            {"global": RateLimitRule(name="global", limit=1, window_seconds=60)},
        )
        monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
        monkeypatch.setattr(rate_limit, "SessionLocal", lambda: db_session)

        # main.py's startup hook (pre-existing, from the completed secrets/jobs
        # workstream) unconditionally asserts the DB's alembic_version via its
        # own SessionLocal -- the process-global engine, not the db_session
        # fixture's own throwaway schema. Nothing else in the fast unit suite
        # runs main.app's real lifespan, so that global engine is otherwise
        # never migrated/stamped, and (being SingletonThreadPool-backed) a
        # stamp made from this thread wouldn't even be visible to the
        # TestClient's worker thread. Route main's SessionLocal to the same
        # db_session used above and stamp alembic_version on it instead, so
        # entering the TestClient context below (which fires that startup
        # hook for real) succeeds; this is orthogonal to the rate-limit
        # behavior under test.
        from database import EXPECTED_ALEMBIC_HEAD
        from sqlalchemy import text as _text

        monkeypatch.setattr(main, "SessionLocal", lambda: db_session)
        db_session.execute(_text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
        db_session.execute(_text("DELETE FROM alembic_version"))
        db_session.execute(
            _text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
            {"v": EXPECTED_ALEMBIC_HEAD},
        )
        db_session.commit()

        headers = {
            "X-Portfyl-Edge-Token": "test-edge-token",
            "CF-Connecting-IP": "203.0.113.9",
            "Origin": "http://localhost:5173",
        }
        with TestClient(main.app) as client:
            first = client.get("/api/portfolios", headers=headers)
            second = client.get("/api/portfolios", headers=headers)

        assert first.status_code == 401  # past the gate, into real (unauthenticated) routing
        assert second.status_code == 429
        assert second.json() == {"code": "rate_limit_exceeded", "rule": "global"}
        assert second.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert second.headers["cache-control"] == "no-store"
    finally:
        main.app.dependency_overrides.clear()
        _reload_main(monkeypatch, "local")
