"""`POST /api/auth/email/password-reset-done`: end a user's Portfyl sessions
right after a password reset, without trusting the browser.

The action page calls it once after Firebase accepted the new password. The
endpoint never takes the caller's word for it: it asks Firebase for the
account's "password last changed" time and runs the same detection as
``/auth/session`` (shared code in ``routers/auth.py``). Firebase and the mailer
are faked; the PostgreSQL suite repeats the important cases under real RLS
(tests/postgres/test_password_reset_done.py).
"""
from __future__ import annotations

import inspect
import logging
from datetime import timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select, update

import rate_limit
from auth import create_session, resolve_session
from database import get_db
from edition import Edition
from emails import notify
from firebase_identity import IdentityVerificationError
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
from tests.test_password_change_detection import ADDRESS, T1, T2, StubVerifier

DONE_URL = "/api/auth/email/password-reset-done"
IP_HEADERS = {"CF-Connecting-IP": "203.0.113.9"}
ACCEPTED = {"status": "accepted"}
OTHER_ADDRESS = "petr@example.com"


class Clock:
    def __init__(self):
        self.t = 100.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def _shared_limiter_session(db_session):
    class _SharedSession:
        def __getattr__(self, name):
            return getattr(db_session, name)

        def close(self) -> None:
            pass

    return _SharedSession()


class Harness:
    """Both auth routers in one app, so a later sign-in can be checked too."""

    def __init__(self, db_session, monkeypatch, clock, *, cloud=False,
                 ip_limit=1000, target_limit=1000, real_hook=False):
        self.db = db_session
        self.clock = clock
        self.cloud = cloud
        self.verifier = StubVerifier()
        self.hook_calls: list[tuple[str, str]] = []
        self.hook_committed: list[bool] = []
        self.limiter_identities: list[tuple[str, str]] = []

        # SQLite has no set_config; the PostgreSQL suite covers the RLS side.
        monkeypatch.setattr(auth_router, "set_rls_context", lambda *a, **k: None)

        def hook(db, user, lang):
            self.hook_calls.append((user.email, lang))
            self.hook_committed.append(not (db.new or db.dirty))

        if not real_hook:
            monkeypatch.setattr(auth_router, "_on_password_changed", hook)

        app = FastAPI()
        app.state.portfyl_edition = Edition.CLOUD if cloud else Edition.LOCAL
        app.add_exception_handler(auth_router.AuthAPIError, auth_router.auth_api_error_handler)
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
        app.add_exception_handler(RateLimitUnavailable, rate_limit_unavailable_handler)
        app.add_exception_handler(InvalidClientIp, invalid_client_ip_handler)
        app.include_router(auth_router.router, prefix="/api")
        app.include_router(auth_email.router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[auth_router.get_identity_verifier] = lambda: self.verifier
        self.client = TestClient(app)

        if cloud:
            monkeypatch.setattr(rate_limit, "RATE_LIMIT_RULES", {
                "auth_session": RateLimitRule(name="auth_session", limit=1000, window_seconds=60),
                "auth_email": RateLimitRule(name="auth_email", limit=ip_limit, window_seconds=600),
                "auth_email_target": RateLimitRule(
                    name="auth_email_target", limit=target_limit, window_seconds=900),
            })
            monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
            monkeypatch.setattr(rate_limit, "SessionLocal",
                                lambda: _shared_limiter_session(db_session))
            real_consume = rate_limit.consume_rate_limit

            def consume(*, rule, identity, now=None):
                self.limiter_identities.append((rule.name, identity))
                return real_consume(rule=rule, identity=identity, now=now)

            monkeypatch.setattr(rate_limit, "consume_rate_limit", consume)

    # --- actions ---

    def sign_in(self, **body):
        return self.client.post(
            "/api/auth/session", json={"id_token": "tok", **body}, headers=IP_HEADERS,
        )

    def done(self, email=ADDRESS, **body):
        return self.client.post(DONE_URL, json={"email": email, **body}, headers=IP_HEADERS)

    def done_raw(self, body):
        return self.client.post(DONE_URL, json=body, headers=IP_HEADERS)

    # --- state ---

    def user(self, email=ADDRESS) -> User | None:
        self.db.expire_all()
        return self.db.scalar(select(User).where(User.email == email))

    def password_audit(self) -> list[AuditLog]:
        self.db.expire_all()
        return [
            row for row in self.db.scalars(select(AuditLog))
            if row.action == "auth.password_changed"
        ]

    def live_sessions(self, user_id) -> int:
        self.db.expire_all()
        return len(self.db.scalars(
            select(AuthSession).where(
                AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None),
            )
        ).all())

    def signed_in_user_with_sessions(self, count=2) -> tuple[User, list[str]]:
        """Alice signs in once (first sight stores T1), then holds ``count``
        more sessions: an attacker's among them, say."""
        if self.cloud:
            # The cloud sign-in needs a beta invite and a trial; neither
            # matters here, so seed what the sign-in would have left.
            user = User(firebase_uid="uid-1", email=ADDRESS, password_changed_seen_at=T1)
            self.db.add(user)
            self.db.flush()
            create_session(self.db, user.id)
            self.db.commit()
        else:
            assert self.sign_in().status_code == 201
        user = self.user()
        tokens = [create_session(self.db, user.id).raw_token for _ in range(count)]
        self.db.commit()
        return user, tokens


@pytest.fixture
def clock(monkeypatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(auth_email, "_now", fake.now)
    monkeypatch.setattr(auth_email, "_sleep", fake.sleep)
    return fake


@pytest.fixture
def local(db_session, monkeypatch, clock) -> Harness:
    return Harness(db_session, monkeypatch, clock)


@pytest.fixture
def make_cloud(db_session, monkeypatch, clock):
    def factory(**limits) -> Harness:
        return Harness(db_session, monkeypatch, clock, cloud=True, **limits)
    return factory


# --- the change is real: every session ends, once ------------------------------


def test_a_real_reset_ends_every_portfyl_session_of_the_user(local):
    user, tokens = local.signed_in_user_with_sessions(count=2)
    local.verifier.password_time = T2

    response = local.done(lang="cs")

    assert response.status_code == 202
    assert response.json() == ACCEPTED
    local.db.expire_all()
    for token in tokens:
        assert resolve_session(local.db, token) is None
    # No session survives: the caller has none, so there is none to keep.
    assert local.live_sessions(user.id) == 0
    assert local.user().password_changed_seen_at.replace(tzinfo=timezone.utc) == T2


def test_a_real_reset_is_audited_once_without_the_address(local):
    local.signed_in_user_with_sessions(count=2)
    local.verifier.password_time = T2

    local.done()

    (row,) = local.password_audit()
    assert row.event_metadata == {"revoked_count": 3, "trigger": "password_reset"}
    assert row.target_type == "user" and row.target_id == str(local.user().id)
    assert row.workspace_id is None
    assert ADDRESS not in repr(row.event_metadata)


def test_the_notice_is_sent_after_the_commit_in_the_requested_language(local):
    local.signed_in_user_with_sessions()
    local.verifier.password_time = T2

    local.done(lang="CS")

    assert local.hook_calls == [(ADDRESS, "cs")]
    assert local.hook_committed == [True]


@pytest.mark.parametrize("lang", [None, "xx", 5, {"a": 1}, ["cs"], "", "x" * 500])
def test_garbage_language_falls_back_to_english(local, lang):
    local.signed_in_user_with_sessions()
    local.verifier.password_time = T2

    response = local.done(lang=lang)

    assert response.status_code == 202
    assert local.hook_calls == [(ADDRESS, "en")]


def test_the_next_sign_in_does_not_notify_or_revoke_again(local):
    user, _tokens = local.signed_in_user_with_sessions()
    local.verifier.password_time = T2
    assert local.done().status_code == 202

    response = local.sign_in()

    assert response.status_code == 201
    assert local.hook_calls == [(ADDRESS, "en")]
    assert len(local.password_audit()) == 1
    new_token = response.cookies.get("portfyl_session")
    local.db.expire_all()
    assert resolve_session(local.db, new_token) is not None
    assert local.live_sessions(user.id) == 1


def test_a_repeated_call_does_nothing_more(local):
    local.signed_in_user_with_sessions()
    local.verifier.password_time = T2

    assert local.done().status_code == 202
    assert local.done().status_code == 202

    assert local.hook_calls == [(ADDRESS, "en")]
    assert len(local.password_audit()) == 1


def test_a_sign_in_that_saw_the_change_first_leaves_nothing_to_do(local):
    local.signed_in_user_with_sessions()
    local.verifier.password_time = T2
    assert local.sign_in().status_code == 201
    signed_in_session = local.sign_in().cookies.get("portfyl_session")

    assert local.done().status_code == 202

    assert local.hook_calls == [(ADDRESS, "en")]
    assert len(local.password_audit()) == 1
    local.db.expire_all()
    # The session created with the new password stays.
    assert resolve_session(local.db, signed_in_session) is not None


def test_another_users_sessions_are_never_touched(local, db_session):
    local.signed_in_user_with_sessions()
    other = User(firebase_uid="uid-other", email=OTHER_ADDRESS, password_changed_seen_at=T1)
    db_session.add(other)
    db_session.flush()
    other_token = create_session(db_session, other.id).raw_token
    db_session.commit()
    local.verifier.password_time = T2

    assert local.done().status_code == 202

    db_session.expire_all()
    assert resolve_session(db_session, other_token) is not None
    assert local.user(OTHER_ADDRESS).password_changed_seen_at.replace(tzinfo=timezone.utc) == T1


def test_the_address_is_matched_like_a_sign_in(local):
    user, tokens = local.signed_in_user_with_sessions()
    local.verifier.password_time = T2

    assert local.done(email="  Jana@EXAMPLE.com ").status_code == 202

    assert local.live_sessions(user.id) == 0


def test_a_failing_notice_cannot_undo_the_revocation(local, monkeypatch, caplog):
    user, tokens = local.signed_in_user_with_sessions()
    local.verifier.password_time = T2

    def boom(db, user, lang):
        raise RuntimeError(f"smtp exploded for {ADDRESS}")

    monkeypatch.setattr(auth_router, "_on_password_changed", boom)
    with caplog.at_level(logging.DEBUG):
        response = local.done()

    assert response.status_code == 202
    assert response.json() == ACCEPTED
    assert local.live_sessions(user.id) == 0
    assert ADDRESS not in caplog.text


# --- nothing changed (or nothing to check): nothing happens -------------------


def test_an_unchanged_password_time_changes_nothing(local):
    user, tokens = local.signed_in_user_with_sessions()

    assert local.done().status_code == 202

    assert local.live_sessions(user.id) == 3
    assert local.hook_calls == []
    assert local.password_audit() == []


def test_an_older_password_time_changes_nothing(local):
    user, tokens = local.signed_in_user_with_sessions()
    local.verifier.password_time = T1 - timedelta(days=1)

    assert local.done().status_code == 202

    assert local.live_sessions(user.id) == 3
    assert local.user().password_changed_seen_at.replace(tzinfo=timezone.utc) == T1


def test_first_sight_stores_the_time_and_revokes_and_notifies_nobody(local, db_session):
    # A user from before migration 0028 who has not signed in since: the
    # wave 2 first-sight rule applies here as at sign-in.
    user, tokens = local.signed_in_user_with_sessions()
    db_session.execute(update(User).values(password_changed_seen_at=None))
    db_session.commit()
    local.verifier.password_time = T2

    assert local.done().status_code == 202

    assert local.user().password_changed_seen_at.replace(tzinfo=timezone.utc) == T2
    assert local.live_sessions(user.id) == 3
    assert local.hook_calls == []
    assert local.password_audit() == []
    # ... and the next change after that is detected as usual.
    local.verifier.password_time = T2 + timedelta(hours=1)
    assert local.done().status_code == 202
    assert local.live_sessions(user.id) == 0
    assert local.hook_calls == [(ADDRESS, "en")]


def test_google_only_account_is_skipped(local):
    user, tokens = local.signed_in_user_with_sessions()
    local.verifier.password_time = None

    assert local.done().status_code == 202

    assert local.live_sessions(user.id) == 3
    assert local.hook_calls == []


def test_unknown_address_makes_no_firebase_lookup(local):
    response = local.done(email="nobody@example.com")

    assert response.status_code == 202
    assert response.json() == ACCEPTED
    assert local.verifier.lookups == 0


def test_user_without_a_firebase_identity_makes_no_lookup(local, db_session):
    # An imported owner row that has never signed in.
    db_session.add(User(email=ADDRESS))
    db_session.commit()

    assert local.done().status_code == 202

    assert local.verifier.lookups == 0


def test_disabled_user_is_skipped(local, db_session):
    from datetime import datetime

    user, tokens = local.signed_in_user_with_sessions()
    db_session.execute(update(User).values(disabled_at=datetime.now(timezone.utc)))
    db_session.commit()
    lookups_before = local.verifier.lookups
    local.verifier.password_time = T2

    assert local.done().status_code == 202

    assert local.verifier.lookups == lookups_before
    assert local.hook_calls == []


def test_a_failing_firebase_lookup_is_a_quiet_no(local, monkeypatch, caplog):
    user, tokens = local.signed_in_user_with_sessions()
    local.verifier.error = IdentityVerificationError(f"down for {ADDRESS}")

    with caplog.at_level(logging.DEBUG):
        response = local.done()

    assert response.status_code == 202
    assert response.json() == ACCEPTED
    assert local.live_sessions(user.id) == 3
    assert ADDRESS not in caplog.text


def test_an_unexpected_error_still_answers_the_same(local, monkeypatch, caplog):
    def boom(*_args, **_kwargs):
        raise RuntimeError(f"database exploded for {ADDRESS}")

    monkeypatch.setattr(auth_email, "_password_reset_done", boom)
    with caplog.at_level(logging.DEBUG):
        response = local.done()

    assert response.status_code == 202
    assert response.json() == ACCEPTED
    assert ADDRESS not in caplog.text


@pytest.mark.parametrize("body", [
    {},
    {"email": None},
    {"email": 5},
    {"email": ["a@b.c"]},
    {"email": {"x": 1}},
    {"email": ""},
    {"email": "not an address"},
    {"email": "x" * 400 + "@example.com"},
])
def test_invalid_input_gets_the_same_answer_and_no_lookup(local, body):
    response = local.done_raw(body)

    assert response.status_code == 202
    assert response.json() == ACCEPTED
    assert local.verifier.lookups == 0


# --- one answer for everyone -------------------------------------------------


@pytest.mark.parametrize("case", [
    "changed", "unchanged", "unknown", "google_only", "invalid", "lookup_failed",
])
def test_every_case_gets_the_same_status_body_headers_and_wait(local, clock, case):
    local.signed_in_user_with_sessions()
    local.verifier.password_time = T2
    email = ADDRESS
    if case == "unchanged":
        local.verifier.password_time = T1
    elif case == "unknown":
        email = "nobody@example.com"
    elif case == "google_only":
        local.verifier.password_time = None
    elif case == "invalid":
        email = "not an address"
    elif case == "lookup_failed":
        local.verifier.error = IdentityVerificationError("down")

    response = local.done(email=email)

    assert response.status_code == 202
    assert response.json() == ACCEPTED
    assert response.headers["cache-control"] == "no-store"
    assert "set-cookie" not in response.headers
    assert clock.sleeps == [pytest.approx(1.5)]


@pytest.mark.parametrize(("work", "answer_at"), [(0.4, 1.5), (1.6, 2.0), (2.0, 2.0), (2.01, 2.5)])
def test_the_answer_waits_on_the_same_grid_as_the_reset_endpoint(local, clock, monkeypatch, work, answer_at):
    local.signed_in_user_with_sessions()
    local.verifier.password_time = T2
    real_lookup = local.verifier.password_updated_at

    def slow_lookup(uid):
        clock.t += work
        return real_lookup(uid)

    monkeypatch.setattr(local.verifier, "password_updated_at", slow_lookup)

    assert local.done().status_code == 202

    assert len(clock.sleeps) == 1
    assert work + clock.sleeps[0] == pytest.approx(answer_at)


@pytest.mark.parametrize("case", ["changed", "unknown"])
def test_no_transaction_is_held_while_waiting(local, db_session, monkeypatch, case):
    local.signed_in_user_with_sessions()
    local.verifier.password_time = T2
    in_transaction: list[bool] = []
    monkeypatch.setattr(
        auth_email, "_sleep", lambda _s: in_transaction.append(db_session.in_transaction()),
    )

    email = ADDRESS if case == "changed" else "nobody@example.com"
    assert local.done(email=email).status_code == 202

    assert in_transaction == [False]


def test_no_transaction_is_held_during_the_firebase_lookup(local, db_session, monkeypatch):
    local.signed_in_user_with_sessions()
    local.verifier.password_time = T2
    real_lookup = local.verifier.password_updated_at
    in_transaction: list[bool] = []

    def lookup(uid):
        in_transaction.append(db_session.in_transaction())
        return real_lookup(uid)

    monkeypatch.setattr(local.verifier, "password_updated_at", lookup)

    assert local.done().status_code == 202
    assert in_transaction == [False]


def test_nothing_sensitive_reaches_the_logs(local, caplog):
    local.signed_in_user_with_sessions()
    local.verifier.password_time = T2

    with caplog.at_level(logging.DEBUG):
        for email in (ADDRESS, "nobody@example.com", "not an address"):
            local.done(email=email)

    assert ADDRESS not in caplog.text
    assert "nobody@example.com" not in caplog.text
    assert "example.com" not in caplog.text


# --- rate limits (cloud) --------------------------------------------------------


def test_cloud_counts_one_ip_and_one_address_bucket(make_cloud):
    cloud = make_cloud()

    assert cloud.done(email=" Jana@Example.com ").status_code == 202

    assert ("auth_email", "203.0.113.9") in cloud.limiter_identities
    assert ("auth_email_target", f"reset-done:{ADDRESS}") in cloud.limiter_identities


def test_cloud_address_limit_is_silent_and_skips_the_lookup(make_cloud, clock):
    cloud = make_cloud(target_limit=1)
    user, tokens = cloud.signed_in_user_with_sessions()
    cloud.verifier.password_time = T2
    lookups_before = cloud.verifier.lookups

    assert cloud.done().status_code == 202  # uses the one allowed call
    clock.sleeps.clear()
    cloud.verifier.password_time = T2 + timedelta(hours=1)

    response = cloud.done()

    assert response.status_code == 202
    assert response.json() == ACCEPTED
    assert clock.sleeps == [pytest.approx(1.5)]
    assert cloud.verifier.lookups == lookups_before + 1
    assert cloud.hook_calls == [(ADDRESS, "en")]


def test_cloud_limiter_outage_is_silent(make_cloud, monkeypatch):
    cloud = make_cloud()
    user, tokens = cloud.signed_in_user_with_sessions()
    cloud.verifier.password_time = T2
    real_consume = rate_limit.consume_rate_limit

    def consume(*, rule, identity, now=None):
        if rule.name == "auth_email_target":
            raise RateLimitUnavailable(rule.name, "OperationalError")
        return real_consume(rule=rule, identity=identity, now=now)

    monkeypatch.setattr(rate_limit, "consume_rate_limit", consume)

    response = cloud.done()

    assert response.status_code == 202
    assert response.json() == ACCEPTED
    assert cloud.live_sessions(user.id) == 3


def test_cloud_per_ip_limit_is_the_shared_auth_email_rule(make_cloud):
    cloud = make_cloud(ip_limit=1)

    assert cloud.done().status_code == 202
    response = cloud.done()

    # Answered before the body is read, the same for every address: the
    # per-IP count says nothing about any account.
    assert response.status_code == 429
    assert response.json()["rule"] == "auth_email"


def test_local_edition_uses_no_limiter(local, monkeypatch):
    def consume(**_kwargs):
        raise AssertionError("no limiter outside cloud")

    monkeypatch.setattr(rate_limit, "consume_rate_limit", consume)

    assert local.done().status_code == 202


# --- the real notice, end to end ----------------------------------------------


class FakeTransport:
    def __init__(self):
        self.sent = []

    def available(self):
        return True

    def send(self, *, to, email, tag):
        self.sent.append((to, tag))
        return "msg-1"

    def probe(self):
        return None


class FakeMailer:
    def __init__(self, transport):
        self.transport = transport


def test_the_real_notice_goes_out_once_for_a_reset_and_not_again_at_sign_in(
    db_session, monkeypatch, clock,
):
    monkeypatch.setenv("PORTFYL_EMAIL_TRANSPORT", "console")
    monkeypatch.setenv("PORTFYL_EMAIL_APP_URL", "https://app.example.test")
    monkeypatch.delenv("PORTFYL_BREVO_API_KEY", raising=False)
    transport = FakeTransport()
    notify.set_default_mailer(FakeMailer(transport))
    try:
        harness = Harness(db_session, monkeypatch, clock, real_hook=True)
        harness.signed_in_user_with_sessions()
        harness.verifier.password_time = T2
        assert harness.done(lang="cs").status_code == 202
        assert harness.sign_in().status_code == 201

        assert transport.sent == [(ADDRESS, "password_changed")]
    finally:
        notify.set_default_mailer(None)


# --- shape --------------------------------------------------------------------


def test_the_endpoint_and_its_helpers_are_plain_functions():
    for function in (
        auth_email.password_reset_done,
        auth_email._password_reset_done,
        auth_router.record_password_change,
        auth_router.notify_password_change,
    ):
        assert not inspect.iscoroutinefunction(function)
