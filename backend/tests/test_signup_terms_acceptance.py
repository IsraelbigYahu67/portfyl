"""The server-side record of the Terms acceptance made at sign-up.

Cloud accounts cannot be created without it (first Google sign-in, and e-mail
sign-up through the pending record); existing accounts are never blocked; the
versions and the time are always the server's; export and deletion cover it.
Firebase is faked, the route runs against the in-memory SQLite session (like
test_auth_session_turnstile.py)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

import legal_acceptance
import rate_limit
import turnstile
from account_deletion import delete_workspace_now
from database import get_db
from edition import Edition
from firebase_identity import IdentityVerificationError, VerifiedIdentity
from models import TermsAcceptance, User, Workspace
from routers import auth as auth_router
from workspace_export import build_workspace_export

ADDRESS = "nova@example.com"
HEADERS = {"CF-Connecting-IP": "203.0.113.9"}
OFF = turnstile.TurnstileConfig(mode="off")


class StubVerifier:
    """`tok` is the unverified e-mail/password identity (just registered),
    `verified` the same account after verification, `google` a Google one."""

    def __init__(self):
        self.identities = {
            "tok": VerifiedIdentity(
                uid="uid-new", email=ADDRESS, email_verified=False,
                display_name=None, sign_in_provider="password",
            ),
            "verified": VerifiedIdentity(
                uid="uid-new", email=ADDRESS, email_verified=True,
                display_name=None, sign_in_provider="password",
            ),
            "google": VerifiedIdentity(
                uid="uid-google", email="gina@example.com", email_verified=True,
                display_name="Gina", sign_in_provider="google.com",
            ),
        }

    def verify_id_token(self, token: str) -> VerifiedIdentity:
        if token not in self.identities:
            raise IdentityVerificationError("bad token")
        return self.identities[token]

    def password_updated_at(self, uid):
        return None

    def delete_user(self, uid):
        DELETED.append(uid)
        if DELETE_ERROR:
            raise IdentityVerificationError("Firebase user deletion failed")


# One StubVerifier is built per request, so what it was asked to delete is
# kept here; Harness resets both.
DELETED: list[str] = []
DELETE_ERROR: list[bool] = []


class Harness:
    def __init__(self, db_session, monkeypatch, *, edition=Edition.CLOUD):
        self.db = db_session
        DELETED.clear()
        DELETE_ERROR.clear()
        monkeypatch.setattr(auth_router, "set_rls_context", lambda *a, **k: None)
        monkeypatch.setattr(auth_router, "require_active_invite", lambda db, email: None)
        monkeypatch.setitem(rate_limit.RATE_LIMIT_RULES, "auth_session", None)
        monkeypatch.setattr(rate_limit, "consume_rate_limit", lambda **k: None)

        app = FastAPI()
        app.state.portfyl_edition = edition
        app.state.turnstile_config = OFF
        app.add_exception_handler(auth_router.AuthAPIError, auth_router.auth_api_error_handler)
        app.include_router(auth_router.router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[auth_router.get_identity_verifier] = StubVerifier
        self.client = TestClient(app)

    def sign_in(self, token="verified", **body):
        return self.client.post(
            "/api/auth/session", json={"id_token": token, **body}, headers=HEADERS
        )

    def register_terms(self, token="tok", **body):
        return self.client.post(
            "/api/auth/signup-acceptance",
            json={"id_token": token, "terms_accepted": True, **body},
            headers=HEADERS,
        )

    def count(self, model) -> int:
        self.db.expire_all()
        return self.db.scalar(select(func.count()).select_from(model))

    def records(self) -> list[TermsAcceptance]:
        self.db.expire_all()
        return list(self.db.scalars(select(TermsAcceptance)).all())


@pytest.fixture
def harness(db_session, monkeypatch):
    return Harness(db_session, monkeypatch)


# --- first Google sign-in ----------------------------------------------------


def test_a_new_cloud_account_without_acceptance_is_refused_and_nothing_is_created(harness):
    response = harness.sign_in("google")

    assert response.status_code == 400
    assert response.json() == {"code": "terms_acceptance_required"}
    assert harness.count(User) == 0
    assert harness.count(Workspace) == 0
    assert harness.count(TermsAcceptance) == 0


def test_a_refused_first_google_sign_in_deletes_the_orphaned_firebase_identity(harness):
    response = harness.sign_in("google")

    assert response.status_code == 400
    assert response.json() == {"code": "terms_acceptance_required"}
    assert DELETED == ["uid-google"]


def test_a_failing_firebase_delete_never_changes_the_refusal(harness):
    DELETE_ERROR.append(True)

    response = harness.sign_in("google")

    assert response.status_code == 400
    assert response.json() == {"code": "terms_acceptance_required"}
    assert DELETED == ["uid-google"]
    assert harness.count(User) == 0


def test_an_accepted_first_google_sign_in_keeps_its_firebase_identity(harness):
    response = harness.sign_in("google", terms_accepted=True)

    assert response.status_code == 201
    assert DELETED == []


def test_an_existing_google_user_is_never_touched_even_without_the_flag(harness, db_session):
    harness.sign_in("google", terms_accepted=True)
    DELETED.clear()

    response = harness.sign_in("google")

    assert response.status_code == 201
    assert DELETED == []
    assert harness.count(User) == 1


def test_an_e_mail_identity_without_a_record_is_refused_but_not_deleted(harness):
    """Only the Google branch discards: a password account holds a credential
    the person chose, and the register page cleans up its own failures."""
    response = harness.sign_in("verified")

    assert response.status_code == 400
    assert DELETED == []


def test_the_local_edition_never_asks_for_terms_or_deletes_anything(db_session, monkeypatch):
    local = Harness(db_session, monkeypatch, edition=Edition.LOCAL)

    assert local.sign_in("google").status_code == 201
    assert DELETED == []


@pytest.mark.parametrize("value", [False, None, "true", 1, "yes", [True]])
def test_only_the_literal_true_counts_as_acceptance(harness, value):
    response = harness.sign_in("google", terms_accepted=value)

    assert response.status_code == 400
    assert response.json() == {"code": "terms_acceptance_required"}
    assert harness.count(User) == 0


def test_first_google_sign_in_with_acceptance_stores_the_record(harness):
    before = datetime.now(timezone.utc) - timedelta(seconds=5)

    response = harness.sign_in("google", terms_accepted=True)

    assert response.status_code == 201
    assert response.json()["account_created"] is True
    [record] = harness.records()
    user = harness.db.scalar(select(User).where(User.email == "gina@example.com"))
    assert record.user_id == user.id
    assert record.terms_version == legal_acceptance.LEGAL_TERMS_VERSION == "2026-11-24"
    assert record.privacy_notice_version == legal_acceptance.LEGAL_PRIVACY_VERSION
    assert record.age_confirmed is True
    assert record.source == "google_signup"
    accepted_at = record.accepted_at
    if accepted_at.tzinfo is None:  # SQLite drops the zone
        accepted_at = accepted_at.replace(tzinfo=timezone.utc)
    assert before <= accepted_at <= datetime.now(timezone.utc) + timedelta(seconds=5)


def test_the_client_cannot_choose_versions_or_time(harness):
    response = harness.sign_in(
        "google",
        terms_accepted=True,
        terms_version="1999-01-01",
        privacy_notice_version="1999-01-01",
        accepted_at="1999-01-01T00:00:00Z",
    )

    assert response.status_code == 201
    [record] = harness.records()
    assert record.terms_version == legal_acceptance.LEGAL_TERMS_VERSION
    assert record.privacy_notice_version == legal_acceptance.LEGAL_PRIVACY_VERSION
    assert record.accepted_at.year >= 2026


# --- e-mail / password sign-up ----------------------------------------------


def test_email_signup_without_a_pending_record_is_refused(harness):
    response = harness.sign_in("verified")

    assert response.status_code == 400
    assert response.json() == {"code": "terms_acceptance_required"}
    assert harness.count(User) == 0


def test_email_signup_pending_record_is_linked_when_the_account_is_created(harness):
    # Registration: the Firebase user exists, the e-mail is not verified yet.
    registered = harness.register_terms("tok")
    assert registered.status_code == 201
    assert registered.json() == {"status": "recorded"}
    [pending] = harness.records()
    assert pending.user_id is None
    assert pending.firebase_uid == "uid-new"
    assert pending.source == "email_signup"
    accepted_at = pending.accepted_at

    # Later (maybe on another device) the verified address signs in: no flag.
    response = harness.sign_in("verified")

    assert response.status_code == 201
    assert response.json()["account_created"] is True
    [record] = harness.records()
    user = harness.db.scalar(select(User).where(User.email == ADDRESS))
    assert record.user_id == user.id
    assert record.accepted_at == accepted_at  # the moment of acceptance, not of sign-in
    assert record.terms_version == legal_acceptance.LEGAL_TERMS_VERSION


def test_registering_twice_keeps_the_first_acceptance(harness):
    harness.register_terms("tok")
    [first] = harness.records()
    first_at = first.accepted_at

    again = harness.register_terms("tok")

    assert again.status_code == 201
    [only] = harness.records()
    assert only.accepted_at == first_at


def test_signup_acceptance_needs_the_flag_and_a_valid_token(harness):
    no_flag = harness.register_terms("tok", terms_accepted=False)
    bad_token = harness.register_terms("nope")

    assert no_flag.status_code == 400
    assert no_flag.json() == {"code": "terms_acceptance_required"}
    assert bad_token.status_code == 401
    assert harness.count(TermsAcceptance) == 0


# --- existing accounts -------------------------------------------------------


def test_an_existing_account_without_a_record_signs_in_without_acceptance(harness):
    harness.sign_in("google", terms_accepted=True)
    harness.db.query(TermsAcceptance).delete()  # as if it pre-dated the record
    harness.db.commit()

    again = harness.sign_in("google")

    assert again.status_code == 201
    assert again.json()["account_created"] is False
    assert harness.count(TermsAcceptance) == 0  # left NULL, not invented


def test_an_account_known_only_by_email_signs_in_without_acceptance(harness):
    harness.db.add(User(email=ADDRESS, firebase_uid=None))
    harness.db.commit()

    response = harness.sign_in("verified")

    assert response.status_code == 201
    assert response.json()["account_created"] is False
    assert harness.count(TermsAcceptance) == 0


def test_signup_acceptance_is_a_no_op_for_an_identity_that_has_an_account(harness):
    harness.sign_in("google", terms_accepted=True)
    harness.db.query(TermsAcceptance).delete()
    harness.db.commit()

    response = harness.client.post(
        "/api/auth/signup-acceptance",
        json={"id_token": "google", "terms_accepted": True},
        headers=HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == {"status": "not_needed"}
    assert harness.count(TermsAcceptance) == 0


# --- local edition -----------------------------------------------------------


def test_the_local_edition_does_not_require_acceptance(db_session, monkeypatch):
    local = Harness(db_session, monkeypatch, edition=Edition.LOCAL)

    without = local.sign_in("google")

    assert without.status_code == 201
    assert local.count(TermsAcceptance) == 0


def test_the_local_edition_still_records_an_acceptance_that_is_sent(db_session, monkeypatch):
    local = Harness(db_session, monkeypatch, edition=Edition.LOCAL)

    response = local.sign_in("google", terms_accepted=True)

    assert response.status_code == 201
    assert local.count(TermsAcceptance) == 1


# --- export and deletion -----------------------------------------------------


def _accept(db, user, **overrides):
    values = dict(
        user_id=user.id,
        terms_version="2026-11-22",
        privacy_notice_version="2026-11-22",
        age_confirmed=True,
        accepted_at=datetime(2026, 11, 22, 9, 30, tzinfo=timezone.utc),
        source="email_signup",
    )
    values.update(overrides)
    row = TermsAcceptance(**values)
    db.add(row)
    db.flush()
    return row


def test_export_includes_the_acceptance_record(db_session, request_context):
    _accept(db_session, request_context.user)
    db_session.commit()

    payload = build_workspace_export(db_session, request_context)

    exported = dict(payload["legal_acceptance"])
    # SQLite drops the zone; PostgreSQL returns "+00:00".
    assert exported.pop("accepted_at").startswith("2026-11-22T09:30:00")
    assert exported == {
        "terms_version": "2026-11-22",
        "privacy_notice_version": "2026-11-22",
        "age_confirmed": True,
        "source": "email_signup",
    }


def test_export_has_no_acceptance_for_an_account_that_predates_the_record(
    db_session, request_context,
):
    payload = build_workspace_export(db_session, request_context)

    assert payload["legal_acceptance"] is None


def test_deleting_the_account_deletes_the_acceptance_record(db_session, request_context):
    _accept(db_session, request_context.user)
    db_session.commit()

    class Admin:
        def delete_user(self, uid):
            pass

    now = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)
    delete_workspace_now(
        db_session,
        request_context,
        identity=VerifiedIdentity(
            uid=request_context.user.firebase_uid,
            email=request_context.user.email,
            email_verified=True,
            display_name=None,
            authenticated_at=now - timedelta(minutes=1),
        ),
        confirmation=request_context.workspace.name,
        identity_admin=Admin(),
        now=now,
    )
    db_session.commit()

    assert db_session.scalar(select(func.count()).select_from(TermsAcceptance)) == 0


# --- cleanup of unfinished registrations --------------------------------------


NOW = datetime(2026, 12, 1, 3, 17, tzinfo=timezone.utc)


def _pending(db, uid, age_days):
    row = TermsAcceptance(
        firebase_uid=uid,
        terms_version="2026-11-24",
        privacy_notice_version="2026-11-24",
        age_confirmed=True,
        accepted_at=NOW - timedelta(days=age_days),
        source="email_signup",
    )
    db.add(row)
    db.flush()
    return row


def test_purge_removes_only_old_pending_rows(db_session, request_context):
    assert legal_acceptance.PENDING_ACCEPTANCE_MAX_AGE_DAYS == 30
    _pending(db_session, "uid-old", 31)
    _pending(db_session, "uid-young", 29)
    _pending(db_session, "uid-edge", 30)  # exactly 30 days: not yet older than 30
    linked = _accept(db_session, request_context.user, accepted_at=NOW - timedelta(days=400))
    db_session.commit()

    deleted = legal_acceptance.purge_stale_pending(db_session, NOW)
    db_session.commit()

    assert deleted == 1
    left = {r.firebase_uid for r in db_session.scalars(select(TermsAcceptance)).all()}
    assert left == {"uid-young", "uid-edge", None}
    assert db_session.get(TermsAcceptance, linked.id) is not None


def test_purge_is_idempotent_and_reports_zero_when_nothing_is_stale(db_session):
    _pending(db_session, "uid-old", 90)
    db_session.commit()

    assert legal_acceptance.purge_stale_pending(db_session, NOW) == 1
    db_session.commit()
    assert legal_acceptance.purge_stale_pending(db_session, NOW) == 0


def test_the_daily_cleanup_job_purges_stale_pending_acceptances(db_session, monkeypatch):
    import asyncio
    from unittest.mock import Mock

    from jobs import account_deletion_cleanup_pass

    monkeypatch.setattr(
        "account_deletion.purge_due_workspace_deletions",
        Mock(return_value={
            "scanned": 0, "purged": 0, "not_due": 0, "shared": 0, "invalid": 0, "errors": 0,
        }),
    )
    _pending(db_session, "uid-old", 45)
    _pending(db_session, "uid-young", 3)
    db_session.commit()

    asyncio.run(account_deletion_cleanup_pass(db_session, now=NOW, identity_admin=object()))

    assert [r.firebase_uid for r in db_session.scalars(select(TermsAcceptance)).all()] == ["uid-young"]
