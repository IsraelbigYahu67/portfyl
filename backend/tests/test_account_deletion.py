"""Verified, reversible workspace deletion workflow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from account_deletion import (
    DELETION_GRACE_DAYS,
    cancel_workspace_deletion,
    get_workspace_deletion,
    schedule_workspace_deletion,
)
from firebase_identity import VerifiedIdentity
from models import AuditLog, Membership, Workspace, WorkspaceSetting
from routers.account import (
    DeletionRequestPayload,
    cancel_deletion,
    get_deletion_status,
    schedule_deletion,
)
from routers.settings import router as settings_router
from tenancy import RequestContextError


NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)


def _identity(context, *, authenticated_at=NOW - timedelta(minutes=1), **overrides):
    values = {
        "uid": context.user.firebase_uid,
        "email": context.user.email,
        "email_verified": True,
        "display_name": None,
        "authenticated_at": authenticated_at,
    }
    values.update(overrides)
    return VerifiedIdentity(**values)


def test_fresh_verified_owner_can_schedule_thirty_day_grace(
    db_session,
    request_context,
):
    state = schedule_workspace_deletion(
        db_session,
        request_context,
        identity=_identity(request_context),
        confirmation=request_context.workspace.name,
        now=NOW,
    )
    db_session.commit()

    assert DELETION_GRACE_DAYS == 30
    assert state.requested_at == NOW
    assert state.execute_after == NOW + timedelta(days=30)
    assert get_workspace_deletion(db_session, request_context.workspace.id) == state
    audit = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "account.deletion.scheduled")
    )
    assert audit is not None
    assert audit.workspace_id == request_context.workspace.id
    assert audit.event_metadata == {"grace_days": 30}


def test_repeated_schedule_keeps_original_deadline(db_session, request_context):
    first = schedule_workspace_deletion(
        db_session,
        request_context,
        identity=_identity(request_context),
        confirmation=request_context.workspace.name,
        now=NOW,
    )
    second = schedule_workspace_deletion(
        db_session,
        request_context,
        identity=_identity(request_context, authenticated_at=NOW + timedelta(days=1)),
        confirmation=request_context.workspace.name,
        now=NOW + timedelta(days=1),
    )

    assert second == first
    assert len(db_session.scalars(
        select(AuditLog).where(AuditLog.action == "account.deletion.scheduled")
    ).all()) == 1


@pytest.mark.parametrize(
    ("identity_overrides", "confirmation", "code"),
    [
        ({"uid": "another-firebase-user"}, None, "reauthentication_identity_mismatch"),
        ({"email": "other@example.com"}, None, "reauthentication_identity_mismatch"),
        ({"email_verified": False}, None, "email_verification_required"),
        ({"authenticated_at": NOW - timedelta(minutes=6)}, None, "recent_reauthentication_required"),
        ({"authenticated_at": None}, None, "recent_reauthentication_required"),
        ({}, "wrong workspace", "workspace_confirmation_mismatch"),
    ],
)
def test_schedule_rejects_unverified_or_mismatching_confirmation(
    db_session,
    request_context,
    identity_overrides,
    confirmation,
    code,
):
    with pytest.raises(RequestContextError) as exc_info:
        schedule_workspace_deletion(
            db_session,
            request_context,
            identity=_identity(request_context, **identity_overrides),
            confirmation=(
                request_context.workspace.name if confirmation is None else confirmation
            ),
            now=NOW,
        )

    assert exc_info.value.code == code
    assert get_workspace_deletion(db_session, request_context.workspace.id) is None


def test_schedule_requires_owner_role(db_session, request_context):
    request_context.membership.role = "member"

    with pytest.raises(RequestContextError) as exc_info:
        schedule_workspace_deletion(
            db_session,
            request_context,
            identity=_identity(request_context),
            confirmation=request_context.workspace.name,
            now=NOW,
        )

    assert exc_info.value.code == "workspace_owner_required"


def test_schedule_refuses_workspace_with_another_active_member(
    db_session,
    request_context,
):
    other_user_id = uuid4()
    from models import User

    db_session.add(User(
        id=other_user_id,
        firebase_uid="firebase-other-member",
        email="other-member@example.com",
    ))
    db_session.add(Membership(
        user_id=other_user_id,
        workspace_id=request_context.workspace.id,
        role="member",
        status="active",
    ))
    db_session.flush()

    with pytest.raises(RequestContextError) as exc_info:
        schedule_workspace_deletion(
            db_session,
            request_context,
            identity=_identity(request_context),
            confirmation=request_context.workspace.name,
            now=NOW,
        )

    assert exc_info.value.code == "workspace_has_other_members"


def test_cancel_removes_only_current_workspace_request_and_audits(
    db_session,
    request_context,
):
    schedule_workspace_deletion(
        db_session,
        request_context,
        identity=_identity(request_context),
        confirmation=request_context.workspace.name,
        now=NOW,
    )
    other_workspace = Workspace(id=uuid4(), name="Other workspace")
    db_session.add(other_workspace)
    db_session.flush()
    db_session.add(WorkspaceSetting(
        workspace_id=other_workspace.id,
        key="privacy.workspace_deletion",
        value='{"version":1,"requested_at":"2026-09-07T12:00:00+00:00",'
              '"execute_after":"2026-10-07T12:00:00+00:00",'
              '"requested_by_user_id":"bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"}',
    ))
    db_session.flush()

    assert cancel_workspace_deletion(db_session, request_context) is True
    assert cancel_workspace_deletion(db_session, request_context) is False
    assert get_workspace_deletion(db_session, request_context.workspace.id) is None
    other = db_session.scalar(select(WorkspaceSetting).where(
        WorkspaceSetting.workspace_id == other_workspace.id,
        WorkspaceSetting.key == "privacy.workspace_deletion",
    ))
    assert other is not None
    actions = db_session.scalars(select(AuditLog.action)).all()
    assert actions.count("account.deletion.cancelled") == 1


def test_deletion_endpoints_expose_status_schedule_and_cancel(
    db_session,
    request_context,
):
    identity = _identity(
        request_context,
        authenticated_at=datetime.now(timezone.utc),
    )

    class Verifier:
        def verify_id_token(self, token):
            assert token == "fresh-firebase-token"
            return identity

    initial = get_deletion_status(db_session, request_context)
    scheduled = schedule_deletion(
        DeletionRequestPayload(
            reauth_id_token="fresh-firebase-token",
            confirmation=request_context.workspace.name,
        ),
        db_session,
        request_context,
        Verifier(),
    )
    cancelled = cancel_deletion(db_session, request_context)

    assert initial == {"scheduled": False, "grace_days": 30}
    assert scheduled["scheduled"] is True
    assert scheduled["grace_days"] == 30
    assert scheduled["execute_after"]
    assert cancelled.status_code == 204


def test_deletion_routes_are_mounted_below_settings():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(settings_router, prefix="/api")
    paths = app.openapi()["paths"]
    assert set(paths["/api/settings/account/deletion"]) == {
        "get",
        "post",
        "delete",
    }
