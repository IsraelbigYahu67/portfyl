from __future__ import annotations

import hashlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import rate_limit
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from auth import create_session, resolve_session, revoke_session
from database import get_db
from edition import Edition
from firebase_identity import IdentityVerificationError, VerifiedIdentity
from models import AuditLog, AuthSession, BetaInvite, Membership, User, Workspace
from routers import auth as auth_router


@pytest.fixture
def alice(postgres_session: Session) -> User:
    suffix = uuid4().hex
    user = User(
        firebase_uid=f"firebase-alice-{suffix}",
        email=f"alice-{suffix}@example.com",
    )
    postgres_session.add(user)
    postgres_session.flush()
    return user


def test_create_session_stores_only_hash(postgres_session: Session, alice: User):
    issued = create_session(postgres_session, alice.id, user_agent="pytest")

    row = postgres_session.scalar(select(AuthSession))
    assert row is not None
    assert issued.raw_token not in row.token_digest
    assert row.token_digest == hashlib.sha256(issued.raw_token.encode()).hexdigest()
    assert issued.csrf_token not in row.csrf_digest
    assert row.csrf_digest == hashlib.sha256(issued.csrf_token.encode()).hexdigest()
    assert row.user_agent == "pytest"


def test_revoked_session_cannot_resolve(postgres_session: Session, alice: User):
    issued = create_session(postgres_session, alice.id)
    revoke_session(postgres_session, issued.raw_token)

    assert resolve_session(postgres_session, issued.raw_token) is None


def test_expired_session_cannot_resolve(postgres_session: Session, alice: User):
    issued = create_session(postgres_session, alice.id)
    row = postgres_session.scalar(select(AuthSession))
    assert row is not None
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    postgres_session.flush()

    assert resolve_session(postgres_session, issued.raw_token) is None


class StubIdentityVerifier:
    def __init__(self):
        self.identities = {
            "alice-token": VerifiedIdentity(
                uid="firebase-alice",
                email="alice@example.com",
                email_verified=True,
                display_name="Alice Investor",
            ),
            "owner-token": VerifiedIdentity(
                uid="firebase-owner",
                email="owner@example.com",
                email_verified=True,
                display_name="Original Owner",
            ),
            "unverified-token": VerifiedIdentity(
                uid="firebase-unverified",
                email="unverified@example.com",
                email_verified=False,
                display_name=None,
            ),
            # Same Firebase UID as alice-token: Firebase's default "one
            # account per e-mail" linking keeps the UID when Google is added.
            "alice-google-token": VerifiedIdentity(
                uid="firebase-alice",
                email="alice@example.com",
                email_verified=True,
                display_name="Alice From Google",
                sign_in_provider="google.com",
            ),
            "alice-password-token": VerifiedIdentity(
                uid="firebase-alice",
                email="alice@example.com",
                email_verified=True,
                display_name=None,
                sign_in_provider="password",
            ),
            "google-unverified-token": VerifiedIdentity(
                uid="firebase-google-unverified",
                email="unverified@workspace.example",
                email_verified=False,
                display_name="Unverified",
                sign_in_provider="google.com",
            ),
            "bob-google-token": VerifiedIdentity(
                uid="firebase-bob-google",
                email="bob@gmail.com",
                email_verified=True,
                display_name="Bob Google",
                sign_in_provider="google.com",
            ),
        }
        self.revoked_uids: list[str] = []

    def verify_id_token(self, token: str) -> VerifiedIdentity:
        try:
            return self.identities[token]
        except KeyError as exc:
            raise IdentityVerificationError("invalid test token") from exc

    def revoke_refresh_tokens(self, uid: str) -> None:
        self.revoked_uids.append(uid)


@contextmanager
def admin_session(postgres_engine):
    with Session(postgres_engine) as db:
        yield db


@pytest.fixture
def empty_auth_database(postgres_engine):
    with admin_session(postgres_engine) as db:
        db.execute(delete(BetaInvite))
        db.execute(delete(User))
        db.execute(delete(Workspace))
        db.commit()
    yield
    with admin_session(postgres_engine) as db:
        db.execute(delete(BetaInvite))
        db.execute(delete(User))
        db.execute(delete(Workspace))
        db.commit()


@pytest.fixture
def verifier() -> StubIdentityVerifier:
    return StubIdentityVerifier()


@pytest.fixture
def client(postgres_engine, empty_auth_database, verifier) -> TestClient:
    app = FastAPI()
    # main.py always stamps this, and route dependencies read it unguarded
    # (entitlements.require_capability, rate_limit.rate_limit). LOCAL keeps
    # these auth/session/RLS tests behaving exactly as before -- the
    # /api/auth/session rate limit no-ops outside cloud and has its own
    # dedicated coverage in tests/test_rate_limit_routes.py.
    app.state.portfyl_edition = Edition.LOCAL
    app.include_router(auth_router.router, prefix="/api")
    app.add_exception_handler(
        auth_router.AuthAPIError,
        auth_router.auth_api_error_handler,
    )

    def override_get_db():
        with Session(postgres_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[auth_router.get_identity_verifier] = lambda: verifier
    with TestClient(app) as test_client:
        yield test_client


def test_verified_identity_creates_user_workspace_membership_and_session(
    client: TestClient,
    postgres_engine,
):
    response = client.post("/api/auth/session", json={"id_token": "alice-token"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["user"]["email"] == "alice@example.com"
    assert len(payload["workspaces"]) == 1
    assert payload["csrf_token"]
    assert "portfyl_session" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    with admin_session(postgres_engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Workspace)) == 1
        assert db.scalar(select(func.count()).select_from(Membership)) == 1
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 1
        audit = db.scalar(select(AuditLog))
        assert audit is not None
        assert audit.action == "auth.session.created"


def test_unverified_identity_is_rejected(client: TestClient, postgres_engine):
    response = client.post(
        "/api/auth/session",
        json={"id_token": "unverified-token"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "email_verification_required"
    with admin_session(postgres_engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0


def test_cloud_beta_rejects_uninvited_identity_before_provisioning(
    client: TestClient,
    postgres_engine,
    monkeypatch,
):
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_RULES", {
        "auth_session": rate_limit.RateLimitRule("auth_session", 100, 60),
    })
    monkeypatch.setattr(rate_limit, "consume_rate_limit", lambda **_kwargs: None)
    client.app.state.portfyl_edition = Edition.CLOUD

    response = client.post(
        "/api/auth/session",
        json={"id_token": "alice-token"},
        headers={"CF-Connecting-IP": "203.0.113.10"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "beta_access_required"
    with admin_session(postgres_engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
        assert db.scalar(select(func.count()).select_from(Workspace)) == 0
        assert db.scalar(select(func.count()).select_from(AuthSession)) == 0


def test_cloud_beta_accepts_invite_and_provisions_once(
    client: TestClient,
    postgres_engine,
    monkeypatch,
):
    with admin_session(postgres_engine) as db:
        db.add(BetaInvite(email="alice@example.com", status="invited"))
        db.commit()
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_RULES", {
        "auth_session": rate_limit.RateLimitRule("auth_session", 100, 60),
    })
    monkeypatch.setattr(rate_limit, "consume_rate_limit", lambda **_kwargs: None)
    client.app.state.portfyl_edition = Edition.CLOUD

    response = client.post(
        "/api/auth/session",
        json={"id_token": "alice-token"},
        headers={"CF-Connecting-IP": "203.0.113.11"},
    )

    assert response.status_code == 201
    with admin_session(postgres_engine) as db:
        invite = db.scalar(select(BetaInvite).where(BetaInvite.email == "alice@example.com"))
        assert invite is not None
        assert invite.status == "accepted"
        assert invite.accepted_at is not None
        assert db.scalar(select(func.count()).select_from(User)) == 1


def test_verified_owner_claims_only_exact_normalized_pending_email(
    client: TestClient,
    postgres_engine,
):
    with admin_session(postgres_engine) as db:
        pending = User(email="owner@example.com")
        workspace = Workspace(name="Imported owner workspace")
        db.add_all([pending, workspace])
        db.flush()
        db.add(Membership(
            user_id=pending.id,
            workspace_id=workspace.id,
            role="owner",
            status="active",
        ))
        db.commit()
        pending_id = pending.id
        workspace_id = workspace.id

    response = client.post("/api/auth/session", json={"id_token": "owner-token"})

    assert response.status_code == 201
    with admin_session(postgres_engine) as db:
        owner = db.scalar(select(User))
        membership = db.scalar(select(Membership))
        assert owner is not None
        assert owner.id == pending_id
        assert owner.firebase_uid == "firebase-owner"
        assert owner.email_verified_at is not None
        assert membership is not None
        assert membership.workspace_id == workspace_id
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Workspace)) == 1


def test_google_identity_signup_provisions_account_and_audits_provider(
    client: TestClient,
    postgres_engine,
):
    response = client.post("/api/auth/session", json={"id_token": "bob-google-token"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["account_created"] is True
    assert payload["user"]["display_name"] == "Bob Google"
    assert payload["workspaces"][0]["name"] == "Bob Google's workspace"
    with admin_session(postgres_engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Membership)) == 1
        audit = db.scalar(select(AuditLog))
        assert audit is not None
        assert audit.event_metadata["provider"] == "google.com"


def test_repeat_exchange_reports_existing_account(client: TestClient):
    first = client.post("/api/auth/session", json={"id_token": "alice-token"})
    second = client.post("/api/auth/session", json={"id_token": "alice-token"})

    assert first.json()["account_created"] is True
    assert second.json()["account_created"] is False
    me = client.get("/api/auth/me")
    assert "account_created" not in me.json()


def test_password_and_google_sign_ins_share_one_account(
    client: TestClient,
    postgres_engine,
):
    flags = []
    for token in ("alice-password-token", "alice-google-token", "alice-password-token"):
        response = client.post("/api/auth/session", json={"id_token": token})
        assert response.status_code == 201
        flags.append(response.json()["account_created"])

    assert flags == [True, False, False]
    with admin_session(postgres_engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Workspace)) == 1
        assert db.scalar(select(func.count()).select_from(Membership)) == 1
        user = db.scalar(select(User))
        assert user is not None
        # The trailing password login has no name claim and must not erase
        # the name Google supplied.
        assert user.display_name == "Alice From Google"
        assert [row.event_metadata["provider"] for row in db.scalars(
            select(AuditLog).order_by(AuditLog.created_at)
        )] == ["password", "google.com", "password"]


def test_unverified_google_identity_is_rejected(client: TestClient, postgres_engine):
    response = client.post(
        "/api/auth/session",
        json={"id_token": "google-unverified-token"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "email_verification_required"
    with admin_session(postgres_engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0


def test_cloud_beta_rejects_uninvited_google_identity_before_provisioning(
    client: TestClient,
    postgres_engine,
    monkeypatch,
):
    monkeypatch.setattr(rate_limit, "RATE_LIMIT_RULES", {
        "auth_session": rate_limit.RateLimitRule("auth_session", 100, 60),
    })
    monkeypatch.setattr(rate_limit, "consume_rate_limit", lambda **_kwargs: None)
    client.app.state.portfyl_edition = Edition.CLOUD

    response = client.post(
        "/api/auth/session",
        json={"id_token": "bob-google-token"},
        headers={"CF-Connecting-IP": "203.0.113.12"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "beta_access_required"
    with admin_session(postgres_engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
        assert db.scalar(select(func.count()).select_from(Workspace)) == 0


def test_me_bootstraps_account_and_rotates_usable_csrf(client: TestClient):
    login = client.post("/api/auth/session", json={"id_token": "alice-token"})
    assert login.status_code == 201

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "alice@example.com"
    assert response.json()["csrf_token"]
    logout = client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": response.json()["csrf_token"]},
    )
    assert logout.status_code == 204


@pytest.mark.parametrize("csrf_header", [None, "wrong-token"])
def test_logout_rejects_missing_or_wrong_csrf(
    client: TestClient,
    csrf_header: str | None,
):
    login = client.post("/api/auth/session", json={"id_token": "alice-token"})
    headers = {} if csrf_header is None else {"X-CSRF-Token": csrf_header}

    response = client.post("/api/auth/logout", headers=headers)

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


def test_logout_revokes_only_current_session(client: TestClient, postgres_engine):
    first = client.post("/api/auth/session", json={"id_token": "alice-token"})
    assert first.status_code == 201
    second = client.post("/api/auth/session", json={"id_token": "alice-token"})
    assert second.status_code == 201

    response = client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": second.json()["csrf_token"]},
    )

    assert response.status_code == 204
    with admin_session(postgres_engine) as db:
        sessions = db.scalars(select(AuthSession)).all()
        assert len(sessions) == 2
        assert sum(row.revoked_at is not None for row in sessions) == 1
        assert [row.action for row in db.scalars(
            select(AuditLog).order_by(AuditLog.created_at)
        )] == [
            "auth.session.created", "auth.session.created", "auth.session.revoked"
        ]


def test_logout_all_revokes_database_and_firebase_sessions(
    client: TestClient,
    postgres_engine,
    verifier: StubIdentityVerifier,
):
    first = client.post("/api/auth/session", json={"id_token": "alice-token"})
    assert first.status_code == 201
    second = client.post("/api/auth/session", json={"id_token": "alice-token"})
    assert second.status_code == 201

    response = client.post(
        "/api/auth/logout-all",
        headers={"X-CSRF-Token": second.json()["csrf_token"]},
    )

    assert response.status_code == 204
    assert verifier.revoked_uids == ["firebase-alice"]
    with admin_session(postgres_engine) as db:
        sessions = db.scalars(select(AuthSession)).all()
        assert len(sessions) == 2
        assert all(row.revoked_at is not None for row in sessions)
        assert [row.action for row in db.scalars(
            select(AuditLog).order_by(AuditLog.created_at)
        )] == [
            "auth.session.created", "auth.session.created",
            "auth.sessions.revoked_all",
        ]


@pytest.fixture
def main_client(
    postgres_engine,
    empty_auth_database,
    verifier,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    import main

    def override_get_db():
        with Session(postgres_engine) as db:
            yield db

    main.app.dependency_overrides[get_db] = override_get_db
    main.app.dependency_overrides[
        auth_router.get_identity_verifier
    ] = lambda: verifier
    monkeypatch.setattr(
        main,
        "SessionLocal",
        sessionmaker(bind=postgres_engine),
    )
    test_client = TestClient(main.app)
    try:
        yield test_client
    finally:
        test_client.close()
        main.app.dependency_overrides.clear()


def test_main_app_exposes_public_firebase_session_exchange(main_client: TestClient):
    response = main_client.post(
        "/api/auth/session",
        json={"id_token": "alice-token"},
    )

    assert response.status_code == 201
    assert response.json()["user"]["email"] == "alice@example.com"


def test_main_app_no_longer_registers_shared_password_routes(main_client: TestClient):
    import main

    registered_paths = {
        route.path for route in main.app.routes if hasattr(route, "path")
    }
    assert "/login" not in registered_paths
    assert "/logout" not in registered_paths
    assert "/api/auth/login" not in registered_paths


def test_main_gate_rejects_session_for_disabled_user(
    main_client: TestClient,
    postgres_engine,
):
    with admin_session(postgres_engine) as db:
        user = User(
            firebase_uid="firebase-disabled",
            email="disabled@example.com",
            disabled_at=datetime.now(timezone.utc),
        )
        db.add(user)
        db.flush()
        issued = create_session(db, user.id)
        db.commit()

    main_client.cookies.set("portfyl_session", issued.raw_token)
    response = main_client.get("/api/portfolios")

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"
