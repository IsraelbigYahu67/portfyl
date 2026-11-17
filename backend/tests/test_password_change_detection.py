"""Password-change detection at /auth/session (own-emails wave 2, Task 2).

Firebase is always faked. The verifier tests build real `UserRecord` objects so
a change in what the installed Admin SDK returns shows up here, and the route
tests run the real `exchange_session` against the in-memory SQLite session (the
PostgreSQL suite repeats the important cases against the real stack).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from firebase_admin import _user_mgt
from sqlalchemy import select, update

from auth import create_session, resolve_session
from database import get_db
from edition import Edition
from firebase_identity import (
    FirebaseIdentityVerifier,
    IdentityVerificationError,
    VerifiedIdentity,
)
from models import AuditLog, AuthSession, User
from routers import auth as auth_router

T1 = datetime(2026, 11, 1, 9, 0, 0, tzinfo=timezone.utc)
T2 = T1 + timedelta(days=3)
T1_MS = int(T1.timestamp() * 1000)
T2_MS = int(T2.timestamp() * 1000)
ADDRESS = "jana@example.com"


# --- the Firebase boundary ---------------------------------------------------


def _record(*, providers=("password",), password_updated_ms=T1_MS, created_ms=1_700_000_000_000):
    data = {
        "localId": "uid-1",
        "email": ADDRESS,
        "createdAt": str(created_ms),
        "providerUserInfo": [
            {"providerId": provider, "rawId": f"raw-{provider}"} for provider in providers
        ],
    }
    if password_updated_ms is not None:
        data["passwordUpdatedAt"] = password_updated_ms
    return _user_mgt.UserRecord(data)


class FakeFirebaseAuth:
    def __init__(self, record=None, error: Exception | None = None):
        self.record = record
        self.error = error
        self.calls: list[tuple[str, object]] = []

    def get_user(self, uid, *, app):
        self.calls.append((uid, app))
        if self.error is not None:
            raise self.error
        return self.record


def _password_time(record=None, error=None):
    auth_client = FakeFirebaseAuth(record, error)
    verifier = FirebaseIdentityVerifier(auth_client=auth_client, app=object())
    return verifier.password_updated_at("uid-1"), auth_client


def test_verifier_reads_password_updated_at_in_milliseconds():
    value, auth_client = _password_time(_record(password_updated_ms=T2_MS))

    assert value == T2
    assert value.tzinfo is not None
    assert [uid for uid, _app in auth_client.calls] == ["uid-1"]


def test_verifier_falls_back_to_creation_time_when_field_is_missing():
    value, _ = _password_time(_record(password_updated_ms=None, created_ms=T1_MS))

    assert value == T1


def test_verifier_skips_users_without_a_password():
    value, _ = _password_time(_record(providers=("google.com",)))

    assert value is None


def test_verifier_reads_password_time_of_user_with_google_and_password():
    value, _ = _password_time(_record(providers=("google.com", "password")))

    assert value == T1


def test_verifier_garbage_time_is_unknown_not_an_error():
    record = _record()
    record._data["passwordUpdatedAt"] = "not-a-number"

    value, _ = _password_time(record)

    assert value is None


def test_verifier_lookup_failure_is_an_identity_error():
    with pytest.raises(IdentityVerificationError):
        _password_time(error=RuntimeError("firebase down"))


# --- the route ----------------------------------------------------------------


class StubVerifier:
    """`password_time` is what Firebase would report for the user now."""

    def __init__(self, password_time=T1, *, error: Exception | None = None):
        self.password_time = password_time
        self.error = error
        self.lookups = 0

    def verify_id_token(self, token: str) -> VerifiedIdentity:
        if token != "tok":
            raise IdentityVerificationError("bad token")
        return VerifiedIdentity(
            uid="uid-1", email=ADDRESS, email_verified=True, display_name=None,
            sign_in_provider="password",
        )

    def password_updated_at(self, uid: str):
        self.lookups += 1
        if self.error is not None:
            raise self.error
        return self.password_time


class NoLookupVerifier:
    """A verifier that predates the lookup (other tests' stubs look like this)."""

    def verify_id_token(self, token: str) -> VerifiedIdentity:
        return StubVerifier().verify_id_token(token)


class Harness:
    def __init__(self, db_session, monkeypatch, verifier):
        self.db = db_session
        self.verifier = verifier
        self.hook_calls: list[tuple[str, str]] = []
        self.hook_committed: list[bool] = []

        # SQLite has no set_config; the PostgreSQL suite covers the RLS side.
        monkeypatch.setattr(auth_router, "set_rls_context", lambda *a, **k: None)

        def hook(db, user, lang):
            self.hook_calls.append((user.email, lang))
            # Runs after the commit: nothing may still be pending.
            self.hook_committed.append(not (db.new or db.dirty))

        monkeypatch.setattr(auth_router, "_on_password_changed", hook)

        app = FastAPI()
        app.state.portfyl_edition = Edition.LOCAL
        app.add_exception_handler(auth_router.AuthAPIError, auth_router.auth_api_error_handler)
        app.include_router(auth_router.router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[auth_router.get_identity_verifier] = lambda: self.verifier
        self.client = TestClient(app)

    def sign_in(self, **body):
        return self.client.post("/api/auth/session", json={"id_token": "tok", **body})

    def user(self) -> User:
        self.db.expire_all()
        return self.db.scalar(select(User).where(User.email == ADDRESS))

    def audit_actions(self) -> list[str]:
        return [row.action for row in self.db.scalars(select(AuditLog))]


@pytest.fixture
def harness(db_session, monkeypatch):
    return Harness(db_session, monkeypatch, StubVerifier())


def _sign_in_then_move_time(harness: Harness, new_time):
    assert harness.sign_in().status_code == 201
    harness.verifier.password_time = new_time


def test_first_sight_stores_the_time_and_notifies_nobody(harness):
    response = harness.sign_in()

    assert response.status_code == 201
    stored = harness.user().password_changed_seen_at
    assert stored is not None and stored.replace(tzinfo=timezone.utc) == T1
    assert harness.hook_calls == []
    assert "auth.password_changed" not in harness.audit_actions()


def test_existing_user_with_null_value_is_first_sight_not_a_change(harness, db_session):
    # A user who existed before this column did.
    assert harness.sign_in().status_code == 201
    db_session.execute(update(User).values(password_changed_seen_at=None))
    db_session.commit()
    harness.verifier.password_time = T2

    assert harness.sign_in().status_code == 201

    stored = harness.user().password_changed_seen_at
    assert stored.replace(tzinfo=timezone.utc) == T2
    assert harness.hook_calls == []
    assert "auth.password_changed" not in harness.audit_actions()


def test_unchanged_password_does_nothing(harness):
    _sign_in_then_move_time(harness, T1)

    assert harness.sign_in().status_code == 201

    assert harness.hook_calls == []
    assert "auth.password_changed" not in harness.audit_actions()


def test_older_time_is_not_a_change(harness):
    _sign_in_then_move_time(harness, T1 - timedelta(days=1))

    assert harness.sign_in().status_code == 201

    assert harness.hook_calls == []
    assert harness.user().password_changed_seen_at.replace(tzinfo=timezone.utc) == T1


def test_changed_password_revokes_other_sessions_keeps_the_new_one(harness, db_session):
    _sign_in_then_move_time(harness, T2)
    user = harness.user()
    other_a = create_session(db_session, user.id).raw_token
    other_b = create_session(db_session, user.id).raw_token
    db_session.commit()

    response = harness.sign_in(lang="cs")

    assert response.status_code == 201
    new_token = response.cookies.get("portfyl_session")
    db_session.expire_all()
    assert resolve_session(db_session, other_a) is None
    assert resolve_session(db_session, other_b) is None
    assert new_token and resolve_session(db_session, new_token) is not None
    live = db_session.scalars(
        select(AuthSession).where(AuthSession.revoked_at.is_(None))
    ).all()
    assert len(live) == 1
    assert harness.user().password_changed_seen_at.replace(tzinfo=timezone.utc) == T2


def test_changed_password_writes_one_audit_event_without_the_address(harness):
    _sign_in_then_move_time(harness, T2)

    harness.sign_in()

    events = [
        row for row in harness.db.scalars(select(AuditLog))
        if row.action == "auth.password_changed"
    ]
    assert len(events) == 1
    assert events[0].event_metadata == {"revoked_count": 1, "trigger": "sign_in"}
    assert ADDRESS not in repr(events[0].event_metadata)
    assert events[0].target_type == "user"


def test_hook_gets_the_normalised_language_after_the_commit(harness):
    _sign_in_then_move_time(harness, T2)

    harness.sign_in(lang="CS")

    assert harness.hook_calls == [(ADDRESS, "cs")]
    assert harness.hook_committed == [True]


@pytest.mark.parametrize("lang", [None, "xx", 5, {"a": 1}, ["cs"], "", "x" * 500])
def test_garbage_language_never_gives_a_422_and_falls_back_to_english(harness, lang):
    _sign_in_then_move_time(harness, T2)

    response = harness.sign_in(lang=lang)

    assert response.status_code == 201
    assert harness.hook_calls == [(ADDRESS, "en")]


def test_a_failing_hook_cannot_fail_the_sign_in_or_undo_the_revocation(
    harness, db_session, monkeypatch, caplog
):
    _sign_in_then_move_time(harness, T2)
    other = create_session(db_session, harness.user().id).raw_token
    db_session.commit()

    def boom(db, user, lang):
        raise RuntimeError(f"smtp exploded for {ADDRESS}")

    monkeypatch.setattr(auth_router, "_on_password_changed", boom)

    with caplog.at_level(logging.DEBUG):
        response = harness.sign_in()

    assert response.status_code == 201
    db_session.expire_all()
    assert resolve_session(db_session, other) is None
    assert ADDRESS not in caplog.text


def test_google_only_user_is_skipped(db_session, monkeypatch):
    harness = Harness(db_session, monkeypatch, StubVerifier(password_time=None))

    assert harness.sign_in().status_code == 201
    assert harness.sign_in().status_code == 201

    assert harness.user().password_changed_seen_at is None
    assert harness.hook_calls == []
    assert "auth.password_changed" not in harness.audit_actions()


def test_lookup_failure_never_fails_the_sign_in(db_session, monkeypatch, caplog):
    verifier = StubVerifier(error=IdentityVerificationError(f"down for {ADDRESS}"))
    harness = Harness(db_session, monkeypatch, verifier)

    with caplog.at_level(logging.DEBUG):
        response = harness.sign_in()

    assert response.status_code == 201
    assert verifier.lookups == 1
    assert harness.user().password_changed_seen_at is None
    assert harness.hook_calls == []
    assert ADDRESS not in caplog.text


def test_verifier_without_the_lookup_method_still_signs_in(db_session, monkeypatch):
    harness = Harness(db_session, monkeypatch, NoLookupVerifier())

    assert harness.sign_in().status_code == 201

    assert harness.user().password_changed_seen_at is None
    assert harness.hook_calls == []


def test_only_one_of_two_racing_sign_ins_sees_the_change(harness, db_session):
    assert harness.sign_in().status_code == 201
    user = harness.user()
    # The other request already moved the stored value; this one's in-memory
    # copy is stale, so Python alone would call it a change too.
    db_session.execute(
        update(User).where(User.id == user.id).values(password_changed_seen_at=T2)
    )

    assert auth_router._observe_password_change(db_session, user, T2) is False
