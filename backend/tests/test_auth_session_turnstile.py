"""/auth/session asks for a Turnstile token only when it would create a new
identity (cloud edition, check not off). Firebase and Cloudflare are faked; the
route runs against the in-memory SQLite session like
test_password_change_detection.py."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

import rate_limit
import turnstile
from database import get_db
from edition import Edition
from firebase_identity import IdentityVerificationError, VerifiedIdentity
from models import TrialGrant, TrialIdentity, User, Workspace
from routers import auth as auth_router

ADDRESS = "nova@example.com"
HEADERS = {"CF-Connecting-IP": "203.0.113.9"}
ON = turnstile.TurnstileConfig(mode="on", secret="0x4AAAAAAA-secret-0000000000000", hostname="app.portfyl.com")
OFF = turnstile.TurnstileConfig(mode="off")


class StubVerifier:
    def __init__(self, uid="uid-new", email=ADDRESS):
        self.uid, self.email = uid, email

    def verify_id_token(self, token: str) -> VerifiedIdentity:
        if token != "tok":
            raise IdentityVerificationError("bad token")
        return VerifiedIdentity(
            uid=self.uid, email=self.email, email_verified=True, display_name=None,
            sign_in_provider="password",
        )

    def password_updated_at(self, uid):
        return None


class Harness:
    def __init__(self, db_session, monkeypatch, *, edition=Edition.CLOUD, config=ON, verifier=None):
        self.db = db_session
        self.calls: list[object] = []
        self.order: list[str] = []
        self.result: str | None = None  # what the fake siteverify answers

        monkeypatch.setattr(auth_router, "set_rls_context", lambda *a, **k: None)
        monkeypatch.setattr(auth_router, "require_active_invite", lambda db, email: None)
        # The cloud rate limit looks its rule up before consuming it.
        monkeypatch.setitem(rate_limit.RATE_LIMIT_RULES, "auth_session", None)
        monkeypatch.setattr(rate_limit, "consume_rate_limit", lambda **k: None)

        real_release = auth_router.release_connection

        def release(db):
            self.order.append("release")
            real_release(db)

        monkeypatch.setattr(auth_router, "release_connection", release)

        def fake_verify(cfg, token, *, remote_ip, client=None):
            self.order.append("verify")
            self.calls.append((token, remote_ip))
            return self.result

        monkeypatch.setattr(turnstile, "verify_signup_token", fake_verify)

        app = FastAPI()
        app.state.portfyl_edition = edition
        if config is not None:
            app.state.turnstile_config = config
        app.add_exception_handler(auth_router.AuthAPIError, auth_router.auth_api_error_handler)
        app.include_router(auth_router.router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[auth_router.get_identity_verifier] = lambda: verifier or StubVerifier()
        self.client = TestClient(app)

    def sign_in(self, **body):
        # A new cloud account also needs the Terms acceptance (default: given),
        # so these tests keep exercising the bot check on its own.
        payload = {"id_token": "tok", "terms_accepted": True, **body}
        return self.client.post("/api/auth/session", json=payload, headers=HEADERS)

    def count(self, model) -> int:
        self.db.expire_all()
        return self.db.scalar(select(func.count()).select_from(model))


@pytest.fixture
def harness(db_session, monkeypatch):
    return Harness(db_session, monkeypatch)


def _nothing_created(h: Harness) -> None:
    assert h.count(User) == 0
    assert h.count(Workspace) == 0
    assert h.count(TrialGrant) == 0
    assert h.count(TrialIdentity) == 0


def test_new_identity_without_a_token_needs_the_bot_check(harness):
    response = harness.sign_in()

    assert response.status_code == 403
    assert response.json() == {"code": "bot_check_required"}
    assert harness.calls == []
    _nothing_created(harness)


@pytest.mark.parametrize("token", [5, {"a": 1}, "", "  ", ["x"]])
def test_a_token_of_the_wrong_type_reads_as_missing_not_422(harness, token):
    response = harness.sign_in(turnstile_token=token)

    assert response.status_code == 403
    assert response.json() == {"code": "bot_check_required"}
    assert harness.calls == []


def test_a_rejected_token_creates_nothing(harness):
    harness.result = "rejected"

    response = harness.sign_in(turnstile_token="t")

    assert response.status_code == 403
    assert response.json() == {"code": "bot_check_failed"}
    _nothing_created(harness)


@pytest.mark.parametrize("reason", ["unavailable", "wrong_action", "wrong_hostname", "missing_token"])
def test_every_failure_reason_blocks_the_new_identity(harness, reason):
    harness.result = reason

    assert harness.sign_in(turnstile_token="t").json() == {"code": "bot_check_failed"}
    _nothing_created(harness)


def test_a_valid_token_creates_the_account_and_the_trial(harness):
    harness.result = None

    response = harness.sign_in(turnstile_token="t")

    assert response.status_code == 201
    assert response.json()["account_created"] is True
    assert harness.calls == [("t", "203.0.113.9")]
    assert harness.count(User) == 1
    assert harness.count(TrialGrant) == 1


def test_verification_runs_after_the_connection_is_released(harness):
    harness.result = None
    harness.sign_in(turnstile_token="t")

    assert harness.order.index("release") < harness.order.index("verify")


def test_an_existing_user_is_never_challenged(harness):
    harness.result = None
    assert harness.sign_in(turnstile_token="t").status_code == 201
    harness.calls.clear()

    # Same Firebase uid, no token.
    again = harness.sign_in()
    assert again.status_code == 201
    assert again.json()["account_created"] is False
    assert harness.calls == []


def test_an_existing_user_found_by_email_is_never_challenged(db_session, monkeypatch):
    h = Harness(db_session, monkeypatch, verifier=StubVerifier(uid="uid-first"))
    h.result = None
    assert h.sign_in(turnstile_token="t").status_code == 201
    h.calls.clear()

    # A known e-mail whose account has no Firebase uid yet gets one on its
    # next sign-in; that is a match by e-mail, not a new identity.
    h.db.execute(update(User).values(firebase_uid=None))
    h.db.flush()
    other = Harness(db_session, monkeypatch, verifier=StubVerifier(uid="uid-second"))
    other.result = None
    response = other.sign_in()

    assert response.status_code == 201
    assert response.json()["account_created"] is False
    assert other.calls == []


def test_mode_off_lets_a_new_identity_in_without_a_token(db_session, monkeypatch):
    h = Harness(db_session, monkeypatch, config=OFF)

    response = h.sign_in()

    assert response.status_code == 201
    assert h.calls == []


def test_an_app_without_a_config_behaves_as_off(db_session, monkeypatch):
    h = Harness(db_session, monkeypatch, config=None)

    assert h.sign_in().status_code == 201
    assert h.calls == []


def test_the_local_edition_is_never_checked(db_session, monkeypatch):
    h = Harness(db_session, monkeypatch, edition=Edition.LOCAL, config=ON)

    assert h.sign_in().status_code == 201
    assert h.calls == []
