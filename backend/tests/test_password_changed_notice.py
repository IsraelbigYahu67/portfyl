"""The `password_changed` notice (own-emails wave 2, Task 4).

These run the real `/auth/session` exchange and the real `_on_password_changed`
hook against the in-memory SQLite session; only Firebase and the mailer are
faked. Detection itself (first sight, unchanged, revocation) is covered in
`test_password_change_detection.py`, which replaces the hook.
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from database import get_db
from edition import Edition
from emails import notify
from emails.catalog import EmailKind, locale_for
from emails.transport import EmailSendError
from models import AuditLog
from routers import auth as auth_router
from tests.test_password_change_detection import ADDRESS, T2, StubVerifier

APP_URL = "https://app.example.test"


def _subject(lang: str) -> str:
    return locale_for(lang).messages[EmailKind.PASSWORD_CHANGED].subject


class FakeTransport:
    def __init__(self, *, available=True, error=None):
        self._available, self._error = available, error
        self.sent = []

    def available(self):
        return self._available

    def send(self, *, to, email, tag):
        if self._error is not None:
            raise self._error
        self.sent.append((to, email, tag))
        return "msg-1"

    def probe(self):
        return None


class FakeMailer:
    def __init__(self, transport):
        self.transport = transport


@pytest.fixture(autouse=True)
def _mailer_env(monkeypatch):
    monkeypatch.setenv("PORTFYL_EMAIL_TRANSPORT", "console")
    monkeypatch.setenv("PORTFYL_EMAIL_APP_URL", APP_URL)
    monkeypatch.delenv("PORTFYL_BREVO_API_KEY", raising=False)
    notify.set_default_mailer(None)
    yield
    notify.set_default_mailer(None)


class Client:
    def __init__(self, db_session, monkeypatch):
        self.db = db_session
        self.verifier = StubVerifier()
        # SQLite has no set_config; the PostgreSQL suite covers the RLS side.
        monkeypatch.setattr(auth_router, "set_rls_context", lambda *a, **k: None)
        app = FastAPI()
        app.state.portfyl_edition = Edition.LOCAL
        app.add_exception_handler(auth_router.AuthAPIError, auth_router.auth_api_error_handler)
        app.include_router(auth_router.router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[auth_router.get_identity_verifier] = lambda: self.verifier
        self.http = TestClient(app)

    def sign_in(self, **body):
        return self.http.post("/api/auth/session", json={"id_token": "tok", **body})

    def password_changed(self, **body):
        """First sight at T1, then Firebase reports T2."""
        assert self.sign_in().status_code == 201
        self.verifier.password_time = T2
        return self.sign_in(**body)


@pytest.fixture
def client(db_session, monkeypatch):
    return Client(db_session, monkeypatch)


def _use(transport):
    notify.set_default_mailer(FakeMailer(transport))
    return transport


def test_notice_is_sent_once_when_the_password_changed(client):
    transport = _use(FakeTransport())

    response = client.password_changed()

    assert response.status_code == 201
    (to, email, tag), = transport.sent
    assert to == ADDRESS and tag == "password_changed"
    assert email.subject == _subject("en")
    # The fact row carries the time Firebase reports, not "now".
    assert "4 November 2026, 09:00 UTC" in email.text
    assert ADDRESS in email.text


def test_button_leads_to_forgot_password_on_the_configured_app_url(client):
    transport = _use(FakeTransport())

    client.password_changed()

    (_to, email, _tag), = transport.sent
    assert f"{APP_URL}/forgot-password" in email.text
    assert f'href="{APP_URL}/forgot-password"' in email.html


def test_notice_uses_the_language_from_the_request(client):
    transport = _use(FakeTransport())

    client.password_changed(lang="cs")

    (_to, email, _tag), = transport.sent
    assert email.subject == _subject("cs")
    assert email.subject != _subject("en")


def test_garbage_language_falls_back_to_english(client):
    transport = _use(FakeTransport())

    response = client.password_changed(lang={"x": 1})

    assert response.status_code == 201
    (_to, email, _tag), = transport.sent
    assert email.subject == _subject("en")


def test_no_notice_on_first_sight(client):
    transport = _use(FakeTransport())

    assert client.sign_in().status_code == 201

    assert transport.sent == []


def test_no_notice_when_the_password_did_not_change(client):
    transport = _use(FakeTransport())

    assert client.sign_in().status_code == 201
    assert client.sign_in().status_code == 201

    assert transport.sent == []


def test_no_second_notice_on_the_next_sign_in(client):
    transport = _use(FakeTransport())

    client.password_changed()
    assert client.sign_in().status_code == 201

    assert len(transport.sent) == 1


def test_mailer_unavailable_sends_nothing_and_sign_in_succeeds(client):
    transport = _use(FakeTransport(available=False))

    response = client.password_changed()

    assert response.status_code == 201
    assert transport.sent == []


def test_mailer_not_configured_sends_nothing_and_sign_in_succeeds(client, monkeypatch):
    monkeypatch.delenv("PORTFYL_EMAIL_TRANSPORT", raising=False)

    response = client.password_changed()

    assert response.status_code == 201


def test_failing_send_never_fails_the_sign_in(client):
    _use(FakeTransport(error=EmailSendError("brevo_http_500")))

    assert client.password_changed().status_code == 201


def test_unexpected_exception_in_the_send_never_fails_the_sign_in(client):
    _use(FakeTransport(error=RuntimeError(f"boom for {ADDRESS}")))

    assert client.password_changed().status_code == 201


def test_address_never_reaches_logs_or_audit_metadata(client, caplog):
    caplog.set_level(logging.DEBUG)
    _use(FakeTransport(error=RuntimeError(f"boom for {ADDRESS}")))

    client.password_changed()
    # And once more through the success path.
    client.verifier.password_time = T2 + timedelta(days=1)
    _use(FakeTransport())
    client.sign_in()

    assert ADDRESS not in caplog.text
    assert "forgot-password" not in caplog.text
    rows = client.db.scalars(select(AuditLog)).all()
    assert any(row.action == "auth.password_changed" for row in rows)
    assert all(ADDRESS not in json.dumps(row.event_metadata, default=str) for row in rows)
