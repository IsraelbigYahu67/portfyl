"""Auth: the signed session and the two ways a request can carry it.

Browsers send the session as the httponly `sb_session` cookie; the native app
(Capacitor, cross-origin) can't rely on that lax cookie, so it sends the same
signed token as `Authorization: Bearer <token>`. Both must authenticate; both
must respect the signature and the 30-day age.

These call auth directly (no live server, no DB) — the security logic lives in
auth.py so it stays testable without importing main.
"""

from __future__ import annotations

import time

import pytest
from starlette.requests import Request

import auth


@pytest.fixture(autouse=True)
def _fixed_secrets(monkeypatch):
    """Pin the password and signing secret so tests don't depend on the shell env."""
    monkeypatch.setattr(auth, "APP_PASSWORD", "test-password")
    monkeypatch.setattr(auth, "SESSION_SECRET", "test-signing-secret")


def _request(*, authorization: str | None = None, cookie_token: str | None = None) -> Request:
    """Minimal ASGI request carrying an optional Authorization header / session cookie."""
    headers: list[tuple[bytes, bytes]] = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    if cookie_token is not None:
        headers.append((b"cookie", f"{auth.SESSION_COOKIE}={cookie_token}".encode()))
    scope = {"type": "http", "method": "GET", "path": "/api/anything", "headers": headers}
    return Request(scope)


# --- login_token: JSON-login building block -----------------------------------

def test_login_token_issues_verifiable_token_for_correct_password():
    token = auth.login_token("test-password")
    assert token is not None
    assert auth.verify_session(token) == auth.DEFAULT_OWNER_ID


def test_login_token_returns_none_for_wrong_password():
    assert auth.login_token("wrong") is None


# --- is_authenticated: cookie path (existing behavior preserved) --------------

def test_valid_cookie_authenticates():
    token = auth.issue_session()
    assert auth.is_authenticated(_request(cookie_token=token)) is True


# --- is_authenticated: bearer path (new) --------------------------------------

def test_valid_bearer_token_authenticates():
    token = auth.issue_session()
    assert auth.is_authenticated(_request(authorization=f"Bearer {token}")) is True


def test_bearer_scheme_is_case_insensitive():
    token = auth.issue_session()
    assert auth.is_authenticated(_request(authorization=f"bearer {token}")) is True


def test_no_credentials_not_authenticated():
    assert auth.is_authenticated(_request()) is False


def test_tampered_bearer_token_not_authenticated():
    assert auth.is_authenticated(_request(authorization="Bearer not-a-real-token")) is False


def test_wrong_scheme_not_authenticated():
    token = auth.issue_session()
    assert auth.is_authenticated(_request(authorization=f"Basic {token}")) is False


def test_expired_bearer_token_not_authenticated():
    old_ts = int(time.time()) - auth.SESSION_MAX_AGE - 100
    payload = auth._b64encode(f"{auth.DEFAULT_OWNER_ID}:{old_ts}".encode())
    stale = f"{payload}.{auth._sign(payload)}"
    assert auth.is_authenticated(_request(authorization=f"Bearer {stale}")) is False


# --- _bearer_token extraction --------------------------------------------------

def test_bearer_token_extracts_value():
    assert auth._bearer_token(_request(authorization="Bearer abc.def")) == "abc.def"


def test_bearer_token_none_when_header_absent():
    assert auth._bearer_token(_request()) is None
