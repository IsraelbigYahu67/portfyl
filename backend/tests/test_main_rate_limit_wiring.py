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
        # The `with TestClient(...)` below runs main's startup hook, whose
        # assert_alembic_head() can't be satisfied by the fast suite's
        # in-memory SQLite. Neutralize it the same way test_internal_jobs.py
        # already does -- this test is about middleware order, not schema.
        monkeypatch.setattr(main, "assert_alembic_head", lambda db: None)
        main.app.dependency_overrides[get_db] = lambda: db_session
        monkeypatch.setattr(edge_trust, "EDGE_TOKEN", "test-edge-token")
        monkeypatch.setattr(
            rate_limit,
            "RATE_LIMIT_RULES",
            {"global": RateLimitRule(name="global", limit=1, window_seconds=60)},
        )
        monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
        monkeypatch.setattr(rate_limit, "SessionLocal", lambda: db_session)

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
