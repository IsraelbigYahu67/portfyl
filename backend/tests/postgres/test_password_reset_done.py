"""`POST /api/auth/email/password-reset-done` under real PostgreSQL RLS.

The fast suite (tests/test_password_reset_done.py) proves the behaviour
against SQLite. Here the handler's own session runs as ``portfyl_runtime``
(the role production uses), so the ``User`` lookup, the session revocation,
``set_rls_context`` and the ``audit_logs`` insert meet the forced policies,
and the Alice/Bob matrix tenants prove that a reset for Alice never touches
Bob. Firebase and the notice hook are faked.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select, text, update
from sqlalchemy.orm import Session, sessionmaker

import rate_limit
from auth import create_session, resolve_session
from database import get_db, set_rls_context
from edition import Edition
from models import AuditLog, AuthSession, User
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

DONE_URL = "/api/auth/email/password-reset-done"
IP_HEADERS = {"CF-Connecting-IP": "203.0.113.9"}
ACTION = "auth.password_changed"
T1 = datetime(2026, 11, 1, 9, 0, 0, tzinfo=timezone.utc)
T2 = T1 + timedelta(days=3)


class FakeVerifier:
    """Firebase's "password last changed" time per uid (None = no password)."""

    def __init__(self):
        self.password_times: dict[str, datetime | None] = {}
        self.lookups: list[str] = []

    def password_updated_at(self, uid: str) -> datetime | None:
        self.lookups.append(uid)
        return self.password_times.get(uid)


@pytest.fixture
def hook_calls(monkeypatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        auth_router, "_on_password_changed",
        lambda db, user, lang: calls.append((user.email, lang)),
    )
    return calls


@pytest.fixture
def verifier() -> FakeVerifier:
    return FakeVerifier()


@pytest.fixture
def done_app(postgres_engine: Engine, matrix_tenants: MatrixTenants, verifier, monkeypatch):
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

    app = FastAPI()
    app.state.portfyl_edition = Edition.CLOUD
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
    app.dependency_overrides[auth_router.get_identity_verifier] = lambda: verifier
    try:
        with TestClient(app, headers=IP_HEADERS) as client:
            yield client
    finally:
        with postgres_engine.begin() as connection:
            connection.execute(text("DELETE FROM rate_limit_buckets"))


@pytest.fixture
def tracked(postgres_engine: Engine, matrix_tenants: MatrixTenants, verifier):
    """Alice and Bob both signed in before (stored T1), each holding two more
    sessions; Firebase reports T1 for both until a test moves one."""
    tokens: dict[str, list[str]] = {}
    with Session(postgres_engine) as db:
        for name in ("alice", "bob"):
            tenant = getattr(matrix_tenants, name)
            db.execute(
                update(User)
                .where(User.id == tenant.user_id)
                .values(password_changed_seen_at=T1)
            )
            tokens[name] = [create_session(db, tenant.user_id).raw_token for _ in range(2)]
            user = db.get(User, tenant.user_id)
            verifier.password_times[user.firebase_uid] = T1
        db.commit()
    tokens["alice"].append(matrix_tenants.session_token)
    return tokens


def _user(postgres_engine: Engine, user_id) -> User:
    with Session(postgres_engine, expire_on_commit=False) as db:
        return db.get(User, user_id)


def _live_sessions(postgres_engine: Engine, user_id) -> int:
    with Session(postgres_engine) as db:
        return db.scalar(
            select(func.count()).select_from(AuthSession).where(
                AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None),
            )
        )


def _audit_rows(postgres_engine: Engine) -> list[AuditLog]:
    """Read by the table owner (no RLS)."""
    with Session(postgres_engine, expire_on_commit=False) as db:
        return list(db.scalars(select(AuditLog).where(AuditLog.action == ACTION)))


def test_a_reset_for_alice_ends_all_her_sessions_and_never_touches_bob(
    done_app: TestClient, postgres_engine: Engine, matrix_tenants: MatrixTenants,
    verifier: FakeVerifier, tracked, hook_calls,
):
    alice, bob = matrix_tenants.alice, matrix_tenants.bob
    alice_user = _user(postgres_engine, alice.user_id)
    verifier.password_times[alice_user.firebase_uid] = T2

    response = done_app.post(DONE_URL, json={"email": alice_user.email, "lang": "cs"})

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert _live_sessions(postgres_engine, alice.user_id) == 0
    with Session(postgres_engine) as db:
        for token in tracked["alice"]:
            assert resolve_session(db, token) is None
        for token in tracked["bob"]:
            assert resolve_session(db, token) is not None
    assert _live_sessions(postgres_engine, bob.user_id) == 2
    assert _user(postgres_engine, alice.user_id).password_changed_seen_at == T2
    assert _user(postgres_engine, bob.user_id).password_changed_seen_at == T1
    assert hook_calls == [(alice_user.email, "cs")]
    (row,) = _audit_rows(postgres_engine)
    assert row.actor_user_id == alice.user_id
    assert row.workspace_id is None
    assert row.target_type == "user" and row.target_id == str(alice.user_id)
    assert row.event_metadata == {"revoked_count": 3, "trigger": "password_reset"}


def test_the_audit_row_is_visible_to_alice_only(
    done_app: TestClient, postgres_engine: Engine, matrix_tenants: MatrixTenants,
    verifier: FakeVerifier, tracked, hook_calls, runtime_session: Session,
):
    alice, bob = matrix_tenants.alice, matrix_tenants.bob
    alice_user = _user(postgres_engine, alice.user_id)
    verifier.password_times[alice_user.firebase_uid] = T2
    assert done_app.post(DONE_URL, json={"email": alice_user.email}).status_code == 202
    query = select(AuditLog).where(AuditLog.action == ACTION)

    assert runtime_session.scalars(query).all() == []  # no context: nothing

    set_rls_context(runtime_session, alice.user_id, None)
    assert [row.actor_user_id for row in runtime_session.scalars(query)] == [alice.user_id]
    set_rls_context(runtime_session, bob.user_id, bob.workspace_id)
    assert runtime_session.scalars(query).all() == []
    set_rls_context(runtime_session, bob.user_id, None)
    assert runtime_session.scalars(query).all() == []


def test_a_call_naming_bob_without_a_change_touches_nobody(
    done_app: TestClient, postgres_engine: Engine, matrix_tenants: MatrixTenants,
    verifier: FakeVerifier, tracked, hook_calls,
):
    alice, bob = matrix_tenants.alice, matrix_tenants.bob
    alice_user = _user(postgres_engine, alice.user_id)
    bob_user = _user(postgres_engine, bob.user_id)
    # Alice's password did change, but the call names Bob's address.
    verifier.password_times[alice_user.firebase_uid] = T2

    assert done_app.post(DONE_URL, json={"email": bob_user.email}).status_code == 202

    assert verifier.lookups == [bob_user.firebase_uid]
    assert _live_sessions(postgres_engine, alice.user_id) == 3
    assert _live_sessions(postgres_engine, bob.user_id) == 2
    assert hook_calls == []
    assert _audit_rows(postgres_engine) == []


def test_the_later_sign_in_check_finds_nothing_left_to_do(
    done_app: TestClient, postgres_engine: Engine, matrix_tenants: MatrixTenants,
    verifier: FakeVerifier, tracked, hook_calls,
):
    alice = matrix_tenants.alice
    alice_user = _user(postgres_engine, alice.user_id)
    verifier.password_times[alice_user.firebase_uid] = T2
    assert done_app.post(DONE_URL, json={"email": alice_user.email}).status_code == 202

    # What /auth/session runs for the same user, as the runtime role.
    with postgres_engine.connect() as connection:
        connection.execute(text("SET ROLE portfyl_runtime"))
        db = Session(bind=connection)
        try:
            user = db.get(User, alice.user_id)
            assert auth_router.record_password_change(
                db, user, T2, trigger="sign_in",
            ) is False
            db.commit()
        finally:
            db.close()
            connection.rollback()
            connection.execute(text("RESET ROLE"))
            connection.commit()

    assert hook_calls == [(alice_user.email, "en")]
    assert len(_audit_rows(postgres_engine)) == 1


def test_unknown_and_first_sight_addresses_change_nothing(
    done_app: TestClient, postgres_engine: Engine, matrix_tenants: MatrixTenants,
    verifier: FakeVerifier, tracked, hook_calls,
):
    alice = matrix_tenants.alice
    alice_user = _user(postgres_engine, alice.user_id)
    with Session(postgres_engine) as db:
        db.execute(
            update(User).where(User.id == alice.user_id).values(password_changed_seen_at=None)
        )
        db.commit()
    verifier.password_times[alice_user.firebase_uid] = T2

    for email in ("nobody-here@example.com", alice_user.email):
        assert done_app.post(DONE_URL, json={"email": email}).status_code == 202

    assert _live_sessions(postgres_engine, alice.user_id) == 3
    assert _user(postgres_engine, alice.user_id).password_changed_seen_at == T2
    assert hook_calls == []
    assert _audit_rows(postgres_engine) == []


def test_the_address_is_stored_in_no_audit_column_and_no_bucket_key(
    done_app: TestClient, postgres_engine: Engine, matrix_tenants: MatrixTenants,
    verifier: FakeVerifier, tracked, hook_calls,
):
    alice_user = _user(postgres_engine, matrix_tenants.alice.user_id)
    verifier.password_times[alice_user.firebase_uid] = T2
    local_part = alice_user.email.split("@")[0]
    assert done_app.post(DONE_URL, json={"email": alice_user.email}).status_code == 202

    with postgres_engine.connect() as connection:
        audit = connection.execute(text(
            "SELECT row_to_json(a)::text FROM audit_logs a WHERE a.action = :action"
        ), {"action": ACTION}).scalars().all()
        keys = connection.execute(text("SELECT key FROM rate_limit_buckets")).scalars().all()

    assert len(audit) == 1
    assert len(keys) == 2  # one per-IP bucket, one per-address bucket
    for stored in audit + keys:
        assert alice_user.email not in stored
        assert local_part not in stored
        assert "example.com" not in stored
