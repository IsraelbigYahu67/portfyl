"""Migration 0029 and the `terms_acceptances` table under real PostgreSQL.

User-level table (like `users`): no workspace key, no tenant policy, so it is
absent from `RLS_TABLES` / `WORKSPACE_SCOPED_TABLES` by design. The runtime role
gets exactly SELECT/INSERT/UPDATE/DELETE; rows cascade with the user; the
database itself refuses a row without a subject or without the 18+ flag.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import legal_acceptance
from database import EXPECTED_ALEMBIC_HEAD
from firebase_identity import VerifiedIdentity
from models import TermsAcceptance, User
from routers.auth import _provision_identity
from tests.postgres.conftest import BACKEND_ROOT

REVISION = "0029_terms_acceptances"
NOW = datetime(2026, 11, 22, 12, 0, tzinfo=timezone.utc)


def _row(**overrides) -> TermsAcceptance:
    values = dict(
        terms_version="2026-11-22",
        privacy_notice_version="2026-11-22",
        age_confirmed=True,
        accepted_at=NOW,
        source="email_signup",
        firebase_uid="uid-1",
    )
    values.update(overrides)
    return TermsAcceptance(**values)


def test_there_is_exactly_one_head_and_it_is_0029():
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == [EXPECTED_ALEMBIC_HEAD] == [REVISION]
    assert script.get_revision(REVISION).down_revision == "0028_password_changed_seen"


def test_runtime_role_has_exact_grants_on_terms_acceptances(postgres_session: Session):
    privileges = set(postgres_session.scalars(text(
        "SELECT privilege_type FROM information_schema.role_table_grants "
        "WHERE grantee = 'portfyl_runtime' AND table_name = 'terms_acceptances'"
    )).all())

    assert privileges == {"SELECT", "INSERT", "UPDATE", "DELETE"}


def test_the_table_is_not_tenant_scoped(postgres_engine: Engine):
    with postgres_engine.connect() as conn:
        columns = set(conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'terms_acceptances'"
        )).scalars())
        rls = conn.execute(text(
            "SELECT relrowsecurity FROM pg_class WHERE relname = 'terms_acceptances'"
        )).scalar_one()

    assert "workspace_id" not in columns
    assert rls is False


def test_a_row_needs_a_subject_and_the_age_confirmation(postgres_session: Session):
    for bad in (
        _row(firebase_uid=None, user_id=None),
        _row(age_confirmed=False),
        _row(source="somewhere_else"),
    ):
        with pytest.raises(IntegrityError):
            with postgres_session.begin_nested():
                postgres_session.add(bad)
                postgres_session.flush()


def test_one_record_per_user_and_per_firebase_uid(postgres_session: Session):
    user = User(email="one@example.com", firebase_uid="uid-1")
    postgres_session.add(user)
    postgres_session.flush()
    postgres_session.add(_row(user_id=user.id))
    postgres_session.flush()

    for duplicate in (_row(user_id=user.id, firebase_uid="uid-2"), _row(firebase_uid="uid-1")):
        with pytest.raises(IntegrityError):
            with postgres_session.begin_nested():
                postgres_session.add(duplicate)
                postgres_session.flush()


def test_the_record_cascades_with_the_user(postgres_session: Session):
    user = User(email="gone@example.com", firebase_uid="uid-gone")
    postgres_session.add(user)
    postgres_session.flush()
    postgres_session.add(_row(user_id=user.id, firebase_uid="uid-gone"))
    postgres_session.flush()

    postgres_session.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})

    assert postgres_session.scalars(select(TermsAcceptance)).all() == []


def test_a_pending_record_is_linked_to_the_new_user(postgres_session: Session):
    legal_acceptance.record_pending(postgres_session, firebase_uid="uid-new", now=NOW)
    postgres_session.flush()

    user, created = _provision_identity(
        postgres_session,
        VerifiedIdentity(
            uid="uid-new", email="new@example.com", email_verified=True,
            display_name=None, sign_in_provider="password",
        ),
    )

    assert created is True
    [record] = postgres_session.scalars(select(TermsAcceptance)).all()
    assert record.user_id == user.id
    assert record.accepted_at == NOW
    assert record.terms_version == legal_acceptance.LEGAL_TERMS_VERSION


def test_purge_removes_only_stale_pending_records_under_postgres(postgres_session: Session):
    from datetime import timedelta

    user = User(email="kept@example.com", firebase_uid="uid-kept")
    postgres_session.add(user)
    postgres_session.flush()
    postgres_session.add_all([
        _row(firebase_uid="uid-old", accepted_at=NOW - timedelta(days=31)),
        _row(firebase_uid="uid-young", accepted_at=NOW - timedelta(days=29)),
        _row(user_id=user.id, firebase_uid="uid-kept", accepted_at=NOW - timedelta(days=500)),
    ])
    postgres_session.flush()

    assert legal_acceptance.purge_stale_pending(postgres_session, NOW) == 1
    assert legal_acceptance.purge_stale_pending(postgres_session, NOW) == 0

    left = {r.firebase_uid for r in postgres_session.scalars(select(TermsAcceptance)).all()}
    assert left == {"uid-young", "uid-kept"}
