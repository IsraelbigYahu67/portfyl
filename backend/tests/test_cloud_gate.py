"""backend/cloud_gate.py: the combined edge-trust + global rate-limit HTTP
gate, exercised against a minimal Starlette app so each check is isolated.
test_main_rate_limit_wiring.py separately proves this middleware is wired
into the real app in the correct position relative to CORSMiddleware."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

import edge_trust
import rate_limit
from cloud_gate import CloudApiGateMiddleware
from rate_limit import RateLimitRule

VALID_HEADERS = {
    "X-Portfyl-Edge-Token": "test-edge-token",
    "CF-Connecting-IP": "203.0.113.9",
    "Origin": "http://localhost:5173",
}


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CloudApiGateMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/ping")
    def ping():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


@pytest.fixture(autouse=True)
def _rate_limit_env(monkeypatch, db_session):
    monkeypatch.setattr(edge_trust, "EDGE_TOKEN", "test-edge-token")
    monkeypatch.setattr(
        rate_limit,
        "RATE_LIMIT_RULES",
        {"global": RateLimitRule(name="global", limit=2, window_seconds=60)},
    )
    monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
    monkeypatch.setattr(rate_limit, "SessionLocal", lambda: db_session)


def test_non_api_path_bypasses_the_gate():
    client = TestClient(_make_app())
    assert client.get("/health").status_code == 200


def test_options_request_is_never_counted():
    client = TestClient(_make_app())
    for _ in range(5):
        client.options(
            "/api/ping",
            headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
        )
    assert client.get("/api/ping", headers=VALID_HEADERS).status_code == 200
    assert client.get("/api/ping", headers=VALID_HEADERS).status_code == 200


def test_missing_edge_token_is_403_with_cors_and_no_store(db_session):
    from models import RateLimitBucket

    client = TestClient(_make_app())
    response = client.get(
        "/api/ping",
        headers={"CF-Connecting-IP": "203.0.113.9", "Origin": "http://localhost:5173"},
    )
    assert response.status_code == 403
    assert response.json() == {"code": "untrusted_edge"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert db_session.query(RateLimitBucket).count() == 0  # untrusted request creates no bucket


def test_wrong_edge_token_is_403():
    client = TestClient(_make_app())
    headers = {**VALID_HEADERS, "X-Portfyl-Edge-Token": "wrong"}
    assert client.get("/api/ping", headers=headers).status_code == 403


def test_malformed_client_ip_is_400():
    client = TestClient(_make_app())
    headers = {**VALID_HEADERS, "CF-Connecting-IP": "not-an-ip"}
    response = client.get("/api/ping", headers=headers)
    assert response.status_code == 400
    assert response.json() == {"code": "invalid_client_ip"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_nth_request_succeeds_and_n_plus_1_is_429_with_cors():
    client = TestClient(_make_app())
    assert client.get("/api/ping", headers=VALID_HEADERS).status_code == 200
    assert client.get("/api/ping", headers=VALID_HEADERS).status_code == 200
    third = client.get("/api/ping", headers=VALID_HEADERS)
    assert third.status_code == 429
    assert third.json() == {"code": "rate_limit_exceeded", "rule": "global"}
    assert int(third.headers["retry-after"]) >= 1
    assert third.headers["cache-control"] == "no-store"
    assert third.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unknown_api_path_is_still_counted():
    # No route is registered for this path -- it would 404 downstream, but
    # the gate runs before routing and must count it anyway.
    client = TestClient(_make_app())
    headers = {**VALID_HEADERS}
    assert client.get("/api/does-not-exist", headers=headers).status_code == 404
    assert client.get("/api/does-not-exist", headers=headers).status_code == 404
    third = client.get("/api/does-not-exist", headers=headers)
    assert third.status_code == 429


def test_distinct_ips_get_distinct_buckets():
    client = TestClient(_make_app())
    headers_a = {**VALID_HEADERS, "CF-Connecting-IP": "203.0.113.9"}
    headers_b = {**VALID_HEADERS, "CF-Connecting-IP": "198.51.100.4"}
    assert client.get("/api/ping", headers=headers_a).status_code == 200
    assert client.get("/api/ping", headers=headers_a).status_code == 200
    assert client.get("/api/ping", headers=headers_a).status_code == 429
    assert client.get("/api/ping", headers=headers_b).status_code == 200


def test_rate_limiter_db_error_is_503(monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    class _BrokenSession:
        def execute(self, *args, **kwargs):
            raise SQLAlchemyError("boom")

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(rate_limit, "SessionLocal", lambda: _BrokenSession())
    client = TestClient(_make_app())
    response = client.get("/api/ping", headers=VALID_HEADERS)
    assert response.status_code == 503
    assert response.json() == {"code": "rate_limiter_unavailable"}
    assert response.headers["retry-after"] == "1"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
