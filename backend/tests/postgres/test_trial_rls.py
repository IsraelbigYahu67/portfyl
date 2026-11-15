"""The free trial under real PostgreSQL: forced RLS on trial_grants, the grants
on the global guard tables, the atomic one-trial-per-mailbox insert, and the
deletion semantics (grant cascades, guard rows survive)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

import trials
from database import set_rls_context
from firebase_identity import VerifiedIdentity
from models import (
    AuditLog,
    TrialBrokerMark,
    TrialGrant,
    TrialIdentity,
    TrialIpMark,
    User,
    Workspace,
)
from routers.auth import _provision_identity
from tests.postgres.conftest import MatrixTenants

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def _as(session: Session, tenant) -> None:
    set_rls_context(session, tenant.user_id, tenant.workspace_id)


def test_alice_sees_only_her_own_trial_grant(matrix_tenants: MatrixTenants, runtime_session: Session):
    _as(runtime_session, matrix_tenants.alice)
    visible = runtime_session.scalars(select(TrialGrant)).all()
    assert [g.workspace_id for g in visible] == [matrix_tenants.alice.workspace_id]


def test_alice_cannot_insert_a_trial_for_bobs_workspace(
    matrix_tenants: MatrixTenants, runtime_session: Session
):
    _as(runtime_session, matrix_tenants.alice)
    with pytest.raises(DBAPIError):
        with runtime_session.begin_nested():
            runtime_session.add(TrialGrant(
                workspace_id=matrix_tenants.bob.workspace_id,
                started_at=NOW, ends_at=NOW + timedelta(days=10),
            ))
            runtime_session.flush()


def test_a_session_without_context_sees_no_trial_grants(
    matrix_tenants: MatrixTenants, runtime_session: Session
):
    assert runtime_session.scalars(select(TrialGrant)).all() == []


def test_the_second_trial_per_workspace_is_rejected(
    matrix_tenants: MatrixTenants, runtime_session: Session
):
    _as(runtime_session, matrix_tenants.alice)
    with pytest.raises(DBAPIError):
        with runtime_session.begin_nested():
            runtime_session.add(TrialGrant(
                workspace_id=matrix_tenants.alice.workspace_id,
                started_at=NOW, ends_at=NOW + timedelta(days=10),
            ))
            runtime_session.flush()


def test_runtime_role_can_use_the_global_guard_tables(runtime_session: Session):
    runtime_session.add_all([
        TrialIdentity(fingerprint="a" * 64, granted_at=NOW),
        TrialIpMark(ip_fingerprint="b" * 64, granted_at=NOW),
        TrialBrokerMark(fingerprint="c" * 64, kind="account", first_seen_at=NOW),
    ])
    runtime_session.flush()
    assert trials.purge_trial_records(runtime_session, NOW + timedelta(days=400)) == {
        "identities": 1, "ip_marks": 1, "broker_marks": 1,
    }


def test_provisioning_a_new_workspace_grants_one_trial_under_rls(runtime_session: Session):
    identity = VerifiedIdentity(
        uid="firebase-trial-new", email="trial.new+x@example.com",
        email_verified=True, display_name=None,
    )
    user, created = _provision_identity(
        runtime_session, identity, grant_trial=True, client_ip="203.0.113.50"
    )
    assert created
    workspace_id = runtime_session.scalar(text("SELECT current_setting('portfyl.workspace_id')"))
    grant = runtime_session.scalar(select(TrialGrant))
    assert grant is not None and str(grant.workspace_id) == workspace_id

    # The same mailbox as an alias registers again (e.g. after deleting the
    # account): a real PostgreSQL ON CONFLICT DO NOTHING says "already used".
    second = VerifiedIdentity(
        uid="firebase-trial-alias", email="trial.new+y@example.com",
        email_verified=True, display_name=None,
    )
    other_user, created = _provision_identity(
        runtime_session, second, grant_trial=True, client_ip="203.0.113.51"
    )
    assert created
    # The new workspace has no grant; its withheld event carries the reason only.
    event = runtime_session.scalar(select(AuditLog).where(AuditLog.action == "trial.withheld"))
    assert event is not None
    assert event.actor_user_id == other_user.id
    assert event.event_metadata == {"reason": "email_reused"}
    assert user.id != other_user.id


def test_deleting_a_workspace_removes_its_grant_but_keeps_the_guards(postgres_session: Session):
    workspace = Workspace(id=uuid4(), name="Doomed")
    postgres_session.add(workspace)
    postgres_session.flush()
    postgres_session.add_all([
        TrialGrant(workspace_id=workspace.id, started_at=NOW, ends_at=NOW + timedelta(days=10)),
        TrialIdentity(fingerprint="d" * 64, granted_at=NOW),
        TrialBrokerMark(
            fingerprint="e" * 64, kind="account", workspace_id=workspace.id, first_seen_at=NOW
        ),
    ])
    postgres_session.flush()

    postgres_session.execute(delete(Workspace).where(Workspace.id == workspace.id))
    postgres_session.expire_all()

    assert postgres_session.scalar(
        select(TrialGrant).where(TrialGrant.workspace_id == workspace.id)
    ) is None
    assert postgres_session.get(TrialIdentity, "d" * 64) is not None
    mark = postgres_session.get(TrialBrokerMark, "e" * 64)
    assert mark is not None and mark.workspace_id is None
