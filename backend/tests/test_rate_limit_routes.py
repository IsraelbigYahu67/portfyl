"""The five targeted rate_limit(...) route dependencies: proves each route
is actually gated by hitting it enough times to trip a deliberately tiny
limit, using minimal mini-apps in the same style as
tests/test_hosted_assistant.py."""
from __future__ import annotations

from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import rate_limit
from database import get_db
from edition import Edition
from entitlements import EntitlementDenied, entitlement_denied_handler
from firebase_identity import IdentityVerificationError
from rate_limit import (
    InvalidClientIp,
    RateLimitExceeded,
    RateLimitRule,
    RateLimitUnavailable,
    invalid_client_ip_handler,
    rate_limit_exceeded_handler,
    rate_limit_unavailable_handler,
)
from routers.portfolios import require_portfolio
from tenancy import get_request_context, require_csrf


def _rate_limited_app(*, cloud: bool) -> FastAPI:
    app = FastAPI()
    app.state.portfyl_edition = Edition.CLOUD if cloud else Edition.LOCAL
    app.add_exception_handler(EntitlementDenied, entitlement_denied_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_exception_handler(RateLimitUnavailable, rate_limit_unavailable_handler)
    app.add_exception_handler(InvalidClientIp, invalid_client_ip_handler)
    return app


def _shared_limiter_session(db_session):
    """consume_rate_limit owns its session and closes it -- in production
    that is an independent SessionLocal(), never the route's own session
    (see the spec's transaction-boundary rules). These tests only have one
    in-memory database, so the limiter must share it *without* closing it:
    a real close() would expunge the route's own ORM instances (the
    RequestContext's Workspace among them) and detach them mid-request.
    Everything else is delegated so commit/rollback semantics are real."""

    class _SharedSession:
        def __getattr__(self, name):
            return getattr(db_session, name)

        def close(self) -> None:
            pass

    return _SharedSession()


class _FailingVerifier:
    """Deterministically fails like a real Firebase call would with a bad
    token, without needing Firebase Admin configured in tests. get_identity_verifier
    is used via Depends(...), so it must be swapped with
    app.dependency_overrides -- monkeypatching the module attribute would
    not change what FastAPI already captured at route-decoration time."""

    def verify_id_token(self, token: str):
        raise IdentityVerificationError("no real Firebase call in this test")


class TestAuthSessionRateLimit:
    def _app(self, db_session) -> FastAPI:
        from routers import auth as auth_router

        app = _rate_limited_app(cloud=True)
        app.add_exception_handler(auth_router.AuthAPIError, auth_router.auth_api_error_handler)
        app.include_router(auth_router.router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[auth_router.get_identity_verifier] = lambda: _FailingVerifier()
        return app

    def test_second_call_from_the_same_ip_is_429(self, monkeypatch, db_session):
        monkeypatch.setattr(
            rate_limit, "RATE_LIMIT_RULES",
            {"auth_session": RateLimitRule(name="auth_session", limit=1, window_seconds=60)},
        )
        monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
        monkeypatch.setattr(rate_limit, "SessionLocal", lambda: db_session)

        client = TestClient(self._app(db_session))
        headers = {"CF-Connecting-IP": "203.0.113.9"}
        first = client.post("/api/auth/session", json={"id_token": "x"}, headers=headers)
        second = client.post("/api/auth/session", json={"id_token": "x"}, headers=headers)

        assert first.status_code == 401  # IdentityVerificationError -- past the limiter
        assert first.json() == {"code": "authentication_required"}
        assert second.status_code == 429
        assert second.json() == {"code": "rate_limit_exceeded", "rule": "auth_session"}

    def test_noops_in_local_edition(self, monkeypatch, db_session):
        monkeypatch.setattr(
            rate_limit, "RATE_LIMIT_RULES",
            {"auth_session": RateLimitRule(name="auth_session", limit=1, window_seconds=60)},
        )
        monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
        monkeypatch.setattr(rate_limit, "SessionLocal", lambda: db_session)

        app = self._app(db_session)
        app.state.portfyl_edition = Edition.LOCAL
        client = TestClient(app)
        headers = {"CF-Connecting-IP": "203.0.113.9"}
        for _ in range(5):
            response = client.post("/api/auth/session", json={"id_token": "x"}, headers=headers)
            assert response.status_code == 401


class TestBrokerSyncRateLimit:
    """All three sync routes 404 immediately with no seeded BrokerConnection
    row -- so hitting them with none seeded proves the limiter runs (and
    commits) even though the route itself never gets past its own
    "not connected" check, exactly matching the spec's "the request counts
    even if the downstream provider fails" requirement.

    Every cloud workspace currently resolves to the FREE plan (no billing
    runtime -- see CLAUDE.md), and broker_sync requires PlanTier.INVESTOR
    (plans.py's MINIMUM_PLAN), so require_capability("broker_sync") would
    otherwise 403 before the limiter ever runs on every one of these routes.
    Bypass it the same way Task 10 does, by no-opping
    entitlements.ensure_capability."""

    def _app(self, router_module, prefix: str, db_session, request_context) -> FastAPI:
        app = _rate_limited_app(cloud=True)
        app.include_router(router_module.router, prefix=prefix)
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[get_request_context] = lambda: request_context
        app.dependency_overrides[require_csrf] = lambda: request_context
        return app

    def _assert_second_call_is_429(self, app, path, monkeypatch, db_session):
        import entitlements

        monkeypatch.setattr(entitlements, "ensure_capability", lambda *a, **k: None)
        monkeypatch.setattr(
            rate_limit, "RATE_LIMIT_RULES",
            {"broker_sync": RateLimitRule(name="broker_sync", limit=1, window_seconds=60)},
        )
        monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
        monkeypatch.setattr(rate_limit, "SessionLocal", lambda: _shared_limiter_session(db_session))

        with TestClient(app) as client:
            first = client.post(path)
            second = client.post(path)

        assert first.status_code == 404  # "not connected" -- past the limiter
        assert second.status_code == 429
        assert second.json() == {"code": "rate_limit_exceeded", "rule": "broker_sync"}

    def test_trading212_sync_second_call_is_429(self, monkeypatch, db_session, request_context, default_portfolio):
        from routers import broker

        app = self._app(broker, "/api", db_session, request_context)
        self._assert_second_call_is_429(app, "/api/broker/trading212/sync", monkeypatch, db_session)

    def test_ibkr_sync_second_call_is_429(self, monkeypatch, db_session, request_context, default_portfolio):
        from routers import ibkr

        app = self._app(ibkr, "/api", db_session, request_context)
        self._assert_second_call_is_429(app, "/api/broker/ibkr/sync", monkeypatch, db_session)

    def test_polymarket_sync_second_call_is_429(self, monkeypatch, db_session, request_context, default_portfolio):
        from routers import polymarket

        app = self._app(polymarket, "/api", db_session, request_context)
        self._assert_second_call_is_429(app, "/api/broker/polymarket/sync", monkeypatch, db_session)

    def test_trading212_and_ibkr_share_one_workspace_bucket(self, monkeypatch, db_session, request_context, default_portfolio):
        from routers import broker, ibkr
        import entitlements

        monkeypatch.setattr(entitlements, "ensure_capability", lambda *a, **k: None)
        monkeypatch.setattr(
            rate_limit, "RATE_LIMIT_RULES",
            {"broker_sync": RateLimitRule(name="broker_sync", limit=1, window_seconds=60)},
        )
        monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
        monkeypatch.setattr(rate_limit, "SessionLocal", lambda: _shared_limiter_session(db_session))

        app = _rate_limited_app(cloud=True)
        app.include_router(broker.router, prefix="/api")
        app.include_router(ibkr.router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[get_request_context] = lambda: request_context
        app.dependency_overrides[require_csrf] = lambda: request_context

        with TestClient(app) as client:
            first = client.post("/api/broker/trading212/sync")
            second = client.post("/api/broker/ibkr/sync")

        assert first.status_code == 404
        assert second.status_code == 429  # same broker_sync bucket, intentionally shared


class TestAssistantChatRateLimit:
    def test_second_call_from_the_same_workspace_is_429(
        self, monkeypatch, db_session, request_context, default_portfolio
    ):
        from routers import assistant
        import entitlements

        monkeypatch.setattr(entitlements, "ensure_capability", lambda *a, **k: None)
        monkeypatch.setattr(
            rate_limit, "RATE_LIMIT_RULES",
            {"assistant_chat": RateLimitRule(name="assistant_chat", limit=1, window_seconds=60)},
        )
        monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
        monkeypatch.setattr(rate_limit, "SessionLocal", lambda: _shared_limiter_session(db_session))

        app = _rate_limited_app(cloud=True)
        app.include_router(assistant.router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[get_request_context] = lambda: request_context
        app.dependency_overrides[require_csrf] = lambda: request_context
        app.dependency_overrides[require_portfolio] = lambda: default_portfolio

        provider = Mock(return_value=("answer", {"total_tokens": 4}))
        payload = {"messages": [{"role": "user", "content": "hi"}]}
        with patch("routers.assistant._call_deepseek", provider), TestClient(app) as client:
            first = client.post(
                "/api/assistant/chat", json=payload, headers={"Idempotency-Key": "req-1"}
            )
            second = client.post(
                "/api/assistant/chat", json=payload, headers={"Idempotency-Key": "req-2"}
            )

        assert first.status_code != 429  # capability check bypassed; limiter let it through
        assert second.status_code == 429
        assert second.json() == {"code": "rate_limit_exceeded", "rule": "assistant_chat"}
