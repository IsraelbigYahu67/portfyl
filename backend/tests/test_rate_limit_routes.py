"""The five targeted rate_limit(...) route dependencies: proves each route
is actually gated by hitting it enough times to trip a deliberately tiny
limit, using minimal mini-apps in the same style as
tests/test_hosted_assistant.py."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

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
