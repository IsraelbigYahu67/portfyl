"""The audit row of a password-reset e-mail under real PostgreSQL RLS.

The fast suite proves the row's content against SQLite, where neither forced
RLS nor the restricted runtime role exists. Here the handler's own session
runs as ``portfyl_runtime`` (the role production uses), so the ``User`` lookup,
``set_rls_context`` and the insert into ``audit_logs`` meet the real policy.
Firebase and Brevo are faked; the two fakes mirror the ones in
tests/test_auth_email_routes.py.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select, text
from sqlalchemy.orm import Session, sessionmaker

import rate_limit
from database import get_db, set_rls_context
from edition import Edition
from models import AuditLog, User
from rate_limit import (
    InvalidClientIp,
    RateLimitExceeded,
    RateLimitRule,
    RateLimitUnavailable,
    invalid_client_ip_handler,
    rate_limit_exceeded_handler,
    rate_limit_unavailable_handler,
)
from routers import auth as auth_router
from routers import auth_email
from tests.postgres.conftest import MatrixTenants

RESET_URL = "/api/auth/email/password-reset"
IP_HEADERS = {"CF-Connecting-IP": "203.0.113.9"}
ACTION = "auth.email.sent"


class FakeTransport:
    def __init__(self):
        self.sent: list[tuple[str, str]] = []
        self.probes = 0

    def available(self) -> bool:
        return True

    def send(self, *, to, email, tag):
        self.sent.append((to, tag))
        return "<message-id>"

    def probe(self) -> None:
        self.probes += 1


class FakeLinks:
    """Firebase knows every address: only Portfyl's own ``users`` table
    decides whether an audit row is written."""

    def verification_url(self, email: str, lang: str) -> str:
        return f"https://app.portfyl.com/auth/action?mode=verifyEmail&oobCode=C&lang={lang}"

    def password_reset_url(self, email: str, lang: str) -> str:
        return f"https://app.portfyl.com/auth/action?mode=resetPassword&oobCode=C&lang={lang}"


@pytest.fixture
def reset_app(postgres_engine: Engine, matrix_tenants: MatrixTenants, monkeypatch):
    """The e-mail router in the cloud edition, its request session running as
    the restricted runtime role, the rate limiter on the same database."""
    monkeypatch.setattr(auth_email, "_sleep", lambda _seconds: None)
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_RULES", {
        "auth_email": RateLimitRule(name="auth_email", limit=1000, window_seconds=600),
        "auth_email_target": RateLimitRule(name="auth_email_target", limit=1000, window_seconds=900),
    })
    monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
    monkeypatch.setattr(
        rate_limit, "SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=postgres_engine),
    )
    with postgres_engine.begin() as connection:
        connection.execute(text("DELETE FROM rate_limit_buckets"))

    transport = FakeTransport()
    app = FastAPI()
    app.state.portfyl_edition = Edition.CLOUD
    app.state.portfyl_mailer = auth_email.Mailer(transport, FakeLinks())
    app.add_exception_handler(auth_router.AuthAPIError, auth_router.auth_api_error_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_exception_handler(RateLimitUnavailable, rate_limit_unavailable_handler)
    app.add_exception_handler(InvalidClientIp, invalid_client_ip_handler)
    app.include_router(auth_email.router, prefix="/api")

    def runtime_get_db():
        connection = postgres_engine.connect()
        connection.execute(text("SET ROLE portfyl_runtime"))
        connection.commit()
        db = sessionmaker(autocommit=False, autoflush=False, bind=connection)()
        try:
            yield db
        finally:
            db.close()
            connection.rollback()
            connection.execute(text("RESET ROLE"))
            connection.commit()
            connection.close()

    app.dependency_overrides[get_db] = runtime_get_db
    try:
        with TestClient(app, headers=IP_HEADERS) as client:
            client.transport_fake = transport
            yield client
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(text("DELETE FROM rate_limit_buckets"))


def _address(postgres_engine: Engine, user_id) -> str:
    with Session(postgres_engine) as db:
        return db.scalar(select(User.email).where(User.id == user_id))


def _audit_rows(postgres_engine: Engine) -> list[AuditLog]:
    """All e-mail audit rows, read by the table owner (no RLS)."""
    with Session(postgres_engine, expire_on_commit=False) as db:
        return list(db.scalars(select(AuditLog).where(AuditLog.action == ACTION)))


def test_reset_for_a_portfyl_user_writes_one_audit_row(
    reset_app: TestClient, postgres_engine: Engine, matrix_tenants: MatrixTenants,
):
    alice = matrix_tenants.alice
    address = _address(postgres_engine, alice.user_id)

    response = reset_app.post(RESET_URL, json={"email": address, "lang": "cs"})

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert reset_app.transport_fake.sent == [(address, "password_reset")]
    rows = _audit_rows(postgres_engine)
    assert len(rows) == 1
    row = rows[0]
    assert row.actor_user_id == alice.user_id
    assert row.workspace_id is None
    assert row.target_type == "user" and row.target_id == str(alice.user_id)
    assert row.event_metadata == {"kind": "password_reset", "lang": "cs"}


def test_the_audit_row_is_visible_to_its_user_only(
    reset_app: TestClient, postgres_engine: Engine, matrix_tenants: MatrixTenants,
    runtime_session: Session,
):
    alice, bob = matrix_tenants.alice, matrix_tenants.bob
    address = _address(postgres_engine, alice.user_id)
    assert reset_app.post(RESET_URL, json={"email": address, "lang": "cs"}).status_code == 202
    query = select(AuditLog).where(AuditLog.action == ACTION)

    assert runtime_session.scalars(query).all() == []  # no context: nothing

    set_rls_context(runtime_session, alice.user_id, alice.workspace_id)
    assert [row.actor_user_id for row in runtime_session.scalars(query)] == [alice.user_id]
    set_rls_context(runtime_session, alice.user_id, None)
    assert [row.actor_user_id for row in runtime_session.scalars(query)] == [alice.user_id]

    set_rls_context(runtime_session, bob.user_id, bob.workspace_id)
    assert runtime_session.scalars(query).all() == []
    set_rls_context(runtime_session, bob.user_id, None)
    assert runtime_session.scalars(query).all() == []


def test_reset_for_an_address_without_a_portfyl_user_writes_no_row(
    reset_app: TestClient, postgres_engine: Engine,
):
    response = reset_app.post(RESET_URL, json={"email": "nobody-here@example.com"})

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert reset_app.transport_fake.sent == [("nobody-here@example.com", "password_reset")]
    assert _audit_rows(postgres_engine) == []


def test_the_address_is_stored_in_no_audit_column_and_no_bucket_key(
    reset_app: TestClient, postgres_engine: Engine, matrix_tenants: MatrixTenants,
):
    address = _address(postgres_engine, matrix_tenants.alice.user_id)
    local_part = address.split("@")[0]
    assert reset_app.post(RESET_URL, json={"email": address}).status_code == 202

    with postgres_engine.connect() as connection:
        audit = connection.execute(text(
            "SELECT row_to_json(a)::text FROM audit_logs a WHERE a.action = :action"
        ), {"action": ACTION}).scalars().all()
        keys = connection.execute(text("SELECT key FROM rate_limit_buckets")).scalars().all()

    assert len(audit) == 1
    assert len(keys) == 2  # one per-IP bucket, one per-address bucket
    for stored in audit + keys:
        assert address not in stored
        assert local_part not in stored
        assert "example.com" not in stored
