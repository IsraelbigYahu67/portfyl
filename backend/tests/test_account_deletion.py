"""Immediate, verified workspace deletion (and the legacy deferred cleanup)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from account_deletion import (
    cancel_workspace_deletion,
    delete_workspace_now,
    deletion_status_payload,
    get_workspace_deletion,
    purge_due_workspace_deletions,
)
from firebase_identity import VerifiedIdentity
from models import Membership, Subscription, User, Workspace, WorkspaceSetting
from routers.account import (
    DeletionRequestPayload,
    cancel_deletion,
    delete_workspace,
    get_deletion_status,
)
from routers.settings import router as settings_router
from stripe_client import StripeError
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


class RecordingIdentityAdmin:
    def __init__(self, error=None):
        self.deleted_uids = []
        self.error = error

    def delete_user(self, uid):
        if self.error:
            raise self.error
        self.deleted_uids.append(uid)


def _delete_now(db, context, *, admin=None, confirmation=None, **identity_overrides):
    return delete_workspace_now(
        db,
        context,
        identity=_identity(context, **identity_overrides),
        confirmation=context.workspace.name if confirmation is None else confirmation,
        identity_admin=admin or RecordingIdentityAdmin(),
        now=NOW,
    )


class RecordingStripe:
    def __init__(self, error=None):
        self.cancelled = []
        self.error = error

    def cancel_subscription(self, subscription_id):
        self.cancelled.append(subscription_id)
        if self.error:
            raise self.error
        return {"id": subscription_id, "status": "canceled"}


def _add_subscription(db, context, **values):
    row = Subscription(
        workspace_id=context.workspace.id,
        stripe_subscription_id=values.pop("stripe_subscription_id", "sub_live"),
        stripe_customer_id="cus_1",
        stripe_price_id="price_pro",
        plan="pro",
        status=values.pop("status", "active"),
        current_period_end=NOW + timedelta(days=10),
        **values,
    )
    db.add(row)
    db.commit()
    return row


def _delete_with_stripe(db, context, stripe, *, cancel, factory_calls=None):
    def factory():
        if factory_calls is not None:
            factory_calls.append(1)
        if stripe is None:
            raise RuntimeError("billing is not enabled")
        return stripe

    return delete_workspace_now(
        db,
        context,
        identity=_identity(context),
        confirmation=context.workspace.name,
        identity_admin=RecordingIdentityAdmin(),
        now=NOW,
        cancel_subscription=cancel,
        stripe_client_factory=factory,
    )


def test_renewing_subscription_without_consent_is_refused_and_stripe_untouched(
    db_session, request_context,
):
    _add_subscription(db_session, request_context)
    stripe = RecordingStripe()
    calls = []

    with pytest.raises(RequestContextError) as exc_info:
        _delete_with_stripe(db_session, request_context, stripe, cancel=False, factory_calls=calls)

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "active_subscription"
    assert stripe.cancelled == []
    assert calls == []
    assert db_session.get(Workspace, request_context.workspace.id) is not None


def test_consent_cancels_the_subscription_once_then_erases(db_session, request_context):
    _add_subscription(db_session, request_context, stripe_subscription_id="sub_abc")
    workspace_id = request_context.workspace.id
    stripe = RecordingStripe()

    result = _delete_with_stripe(db_session, request_context, stripe, cancel=True)
    db_session.commit()

    assert stripe.cancelled == ["sub_abc"]
    assert result.account_deleted is True
    assert db_session.get(Workspace, workspace_id) is None


def test_trialing_subscription_is_cancelled_too(db_session, request_context):
    _add_subscription(db_session, request_context, status="trialing")
    stripe = RecordingStripe()

    _delete_with_stripe(db_session, request_context, stripe, cancel=True)

    assert stripe.cancelled == ["sub_live"]


def test_stripe_failure_aborts_with_503_and_keeps_the_workspace(db_session, request_context):
    _add_subscription(db_session, request_context)
    stripe = RecordingStripe(error=StripeError("boom", status=500, transient=True))

    with pytest.raises(RequestContextError) as exc_info:
        _delete_with_stripe(db_session, request_context, stripe, cancel=True)

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "subscription_cancel_failed"
    assert stripe.cancelled == ["sub_live"]
    assert db_session.get(Workspace, request_context.workspace.id) is not None
    assert db_session.get(User, request_context.user.id) is not None


def test_billing_off_with_a_renewing_row_aborts_with_503(db_session, request_context):
    _add_subscription(db_session, request_context)

    with pytest.raises(RequestContextError) as exc_info:
        _delete_with_stripe(db_session, request_context, None, cancel=True)

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "subscription_cancel_failed"
    assert db_session.get(Workspace, request_context.workspace.id) is not None


def test_missing_stripe_client_factory_aborts_with_503(db_session, request_context):
    _add_subscription(db_session, request_context)

    with pytest.raises(RequestContextError) as exc_info:
        delete_workspace_now(
            db_session,
            request_context,
            identity=_identity(request_context),
            confirmation=request_context.workspace.name,
            identity_admin=RecordingIdentityAdmin(),
            now=NOW,
            cancel_subscription=True,
        )

    assert exc_info.value.code == "subscription_cancel_failed"
    assert db_session.get(Workspace, request_context.workspace.id) is not None


@pytest.mark.parametrize(
    "error",
    [
        StripeError("No such subscription", status=404, code="resource_missing"),
        StripeError("gone", code="resource_missing"),
    ],
)
def test_subscription_already_cancelled_in_stripe_counts_as_success(
    db_session, request_context, error,
):
    _add_subscription(db_session, request_context)
    workspace_id = request_context.workspace.id
    stripe = RecordingStripe(error=error)

    _delete_with_stripe(db_session, request_context, stripe, cancel=True)
    db_session.commit()

    assert stripe.cancelled == ["sub_live"]
    assert db_session.get(Workspace, workspace_id) is None


def test_no_subscription_never_touches_stripe_even_with_consent(db_session, request_context):
    stripe = RecordingStripe()
    calls = []

    _delete_with_stripe(db_session, request_context, stripe, cancel=True, factory_calls=calls)

    assert stripe.cancelled == []
    assert calls == []


def test_subscription_already_ending_proceeds_without_stripe(db_session, request_context):
    _add_subscription(db_session, request_context, cancel_at_period_end=True)
    workspace_id = request_context.workspace.id
    stripe = RecordingStripe()
    calls = []

    _delete_with_stripe(db_session, request_context, stripe, cancel=False, factory_calls=calls)
    db_session.commit()

    assert stripe.cancelled == []
    assert calls == []
    assert db_session.get(Workspace, workspace_id) is None


def test_consent_does_not_bypass_the_other_guards(db_session, request_context):
    _add_subscription(db_session, request_context)
    stripe = RecordingStripe()

    with pytest.raises(RequestContextError) as exc_info:
        delete_workspace_now(
            db_session,
            request_context,
            identity=_identity(request_context),
            confirmation="wrong workspace",
            identity_admin=RecordingIdentityAdmin(),
            now=NOW,
            cancel_subscription=True,
            stripe_client_factory=lambda: stripe,
        )

    assert exc_info.value.code == "workspace_confirmation_mismatch"
    assert stripe.cancelled == []


def test_endpoint_passes_consent_and_maps_stripe_failure_to_503(db_session, request_context):
    from fastapi import Response

    _add_subscription(db_session, request_context)
    identity = _identity(request_context, authenticated_at=datetime.now(timezone.utc))
    stripe = RecordingStripe(error=StripeError("down", status=503, transient=True))

    class Verifier:
        def verify_id_token(self, token):
            return identity

        def delete_user(self, uid):
            raise AssertionError("must not be reached")

    def call(cancel_subscription):
        return delete_workspace(
            DeletionRequestPayload(
                reauth_id_token="t",
                confirmation=request_context.workspace.name,
                cancel_subscription=cancel_subscription,
            ),
            Response(),
            db_session,
            request_context,
            Verifier(),
            None,
            lambda: stripe,
        )

    with pytest.raises(RequestContextError) as without:
        call(False)
    assert without.value.code == "active_subscription"
    assert stripe.cancelled == []

    with pytest.raises(RequestContextError) as with_consent:
        call(True)
    assert with_consent.value.status_code == 503
    assert with_consent.value.code == "subscription_cancel_failed"
    assert stripe.cancelled == ["sub_live"]
    assert db_session.get(Workspace, request_context.workspace.id) is not None


def test_payload_defaults_to_no_consent():
    payload = DeletionRequestPayload(reauth_id_token="t", confirmation="c")
    assert payload.cancel_subscription is False


def test_verified_owner_deletes_workspace_and_account_at_once(db_session, request_context):
    workspace_id = request_context.workspace.id
    user_id = request_context.user.id
    firebase_uid = request_context.user.firebase_uid
    admin = RecordingIdentityAdmin()

    result = _delete_now(db_session, request_context, admin=admin)
    db_session.commit()

    assert result.account_deleted is True
    assert result.farewell == (request_context.user.email, "en")
    assert db_session.get(Workspace, workspace_id) is None
    assert db_session.get(User, user_id) is None
    assert admin.deleted_uids == [firebase_uid]


def test_delete_keeps_account_when_another_workspace_remains(db_session, request_context):
    deleting_id = request_context.workspace.id
    kept = Workspace(id=uuid4(), name="Kept workspace")
    db_session.add(kept)
    db_session.flush()
    db_session.add(Membership(
        user_id=request_context.user.id, workspace_id=kept.id, role="owner", status="active",
    ))
    db_session.commit()
    admin = RecordingIdentityAdmin()

    result = _delete_now(db_session, request_context, admin=admin)
    db_session.commit()

    assert result.account_deleted is False
    assert result.farewell is None
    assert db_session.get(Workspace, deleting_id) is None
    assert db_session.get(Workspace, kept.id) is not None
    assert db_session.get(User, request_context.user.id) is not None
    assert admin.deleted_uids == []


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
def test_delete_rejects_unverified_or_mismatching_confirmation(
    db_session, request_context, identity_overrides, confirmation, code,
):
    admin = RecordingIdentityAdmin()

    with pytest.raises(RequestContextError) as exc_info:
        _delete_now(
            db_session, request_context, admin=admin,
            confirmation=confirmation, **identity_overrides,
        )

    assert exc_info.value.code == code
    assert db_session.get(Workspace, request_context.workspace.id) is not None
    assert admin.deleted_uids == []


def test_delete_requires_owner_role(db_session, request_context):
    request_context.membership.role = "member"

    with pytest.raises(RequestContextError) as exc_info:
        _delete_now(db_session, request_context)

    assert exc_info.value.code == "workspace_owner_required"
    assert db_session.get(Workspace, request_context.workspace.id) is not None


def test_delete_refuses_workspace_with_another_active_member(db_session, request_context):
    other_user_id = uuid4()
    db_session.add(User(
        id=other_user_id, firebase_uid="firebase-other-member", email="other-member@example.com",
    ))
    db_session.add(Membership(
        user_id=other_user_id, workspace_id=request_context.workspace.id,
        role="member", status="active",
    ))
    db_session.flush()

    with pytest.raises(RequestContextError) as exc_info:
        _delete_now(db_session, request_context)

    assert exc_info.value.code == "workspace_has_other_members"
    assert db_session.get(Workspace, request_context.workspace.id) is not None


def test_failed_identity_deletion_leaves_everything_for_a_rollback(db_session, request_context):
    db_session.commit()
    with pytest.raises(RuntimeError):
        _delete_now(
            db_session, request_context,
            admin=RecordingIdentityAdmin(error=RuntimeError("firebase unavailable")),
        )
    db_session.rollback()

    assert db_session.get(Workspace, request_context.workspace.id) is not None
    assert db_session.get(User, request_context.user.id) is not None


def test_cancel_removes_only_current_workspace_request_and_audits(db_session, request_context):
    _schedule(db_session, request_context)
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
    from models import AuditLog
    actions = db_session.scalars(select(AuditLog.action)).all()
    assert actions.count("account.deletion.cancelled") == 1


def test_status_payload_has_no_grace_period():
    assert deletion_status_payload(None) == {"scheduled": False}


def test_delete_endpoint_erases_now_and_clears_the_session_cookie(db_session, request_context):
    from fastapi import Response

    identity = _identity(request_context, authenticated_at=datetime.now(timezone.utc))
    admin = RecordingIdentityAdmin()
    workspace_id = request_context.workspace.id

    class Verifier:
        def verify_id_token(self, token):
            assert token == "fresh-firebase-token"
            return identity

        def delete_user(self, uid):
            admin.delete_user(uid)

    response = Response()
    body = delete_workspace(
        DeletionRequestPayload(
            reauth_id_token="fresh-firebase-token",
            confirmation=request_context.workspace.name,
        ),
        response,
        db_session,
        request_context,
        Verifier(),
        None,
    )

    assert body == {"deleted": True, "account_deleted": True}
    assert db_session.get(Workspace, workspace_id) is None
    assert admin.deleted_uids == [identity.uid]
    assert "set-cookie" in response.headers  # the session cookie is expired


def test_delete_endpoint_maps_identity_provider_failure_to_503_and_keeps_data(
    db_session, request_context,
):
    from fastapi import Response

    db_session.commit()
    identity = _identity(request_context, authenticated_at=datetime.now(timezone.utc))

    class Verifier:
        def verify_id_token(self, token):
            return identity

        def delete_user(self, uid):
            raise RuntimeError("firebase unavailable")

    with pytest.raises(RequestContextError) as exc_info:
        delete_workspace(
            DeletionRequestPayload(
                reauth_id_token="t", confirmation=request_context.workspace.name,
            ),
            Response(),
            db_session,
            request_context,
            Verifier(),
            None,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "account_deletion_unavailable"
    assert db_session.get(Workspace, request_context.workspace.id) is not None
    assert db_session.get(User, request_context.user.id) is not None


def test_status_and_cancel_endpoints_still_serve_legacy_requests(db_session, request_context):
    assert get_deletion_status(db_session, request_context) == {"scheduled": False}
    _schedule(db_session, request_context)
    status = get_deletion_status(db_session, request_context)
    assert status["scheduled"] is True and status["execute_after"]
    assert "grace_days" not in status
    assert cancel_deletion(db_session, request_context).status_code == 204


def test_deletion_routes_are_mounted_below_settings():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(settings_router, prefix="/api")
    paths = app.openapi()["paths"]
    assert set(paths["/api/settings/account/deletion"]) == {"get", "post", "delete"}


class RecordingIdentityAdmin:
    def __init__(self, error=None):
        self.deleted_uids = []
        self.error = error

    def delete_user(self, uid):
        if self.error:
            raise self.error
        self.deleted_uids.append(uid)


def _schedule(db, context):
    """A request left over from the old 30-day rule (nothing creates these any
    more); the cleanup job must still finish them."""
    state = {
        "version": 1,
        "requested_at": NOW.isoformat(),
        "execute_after": (NOW + timedelta(days=30)).isoformat(),
        "requested_by_user_id": str(context.user.id),
    }
    db.add(WorkspaceSetting(
        workspace_id=context.workspace.id,
        key="privacy.workspace_deletion",
        value=json.dumps(state),
    ))
    db.commit()
    return get_workspace_deletion(db, context.workspace.id)


def test_cleanup_never_purges_before_grace_deadline(db_session, request_context):
    _schedule(db_session, request_context)
    identity_admin = RecordingIdentityAdmin()

    summary = purge_due_workspace_deletions(
        db_session,
        identity_admin,
        now=NOW + timedelta(days=29),
    )

    assert summary == {
        "scanned": 1,
        "purged": 0,
        "not_due": 1,
        "shared": 0,
        "invalid": 0,
        "errors": 0,
    }
    assert db_session.get(Workspace, request_context.workspace.id) is not None
    assert identity_admin.deleted_uids == []


def test_cleanup_purges_due_last_workspace_and_firebase_identity(
    db_session,
    request_context,
):
    workspace_id = request_context.workspace.id
    user_id = request_context.user.id
    firebase_uid = request_context.user.firebase_uid
    _schedule(db_session, request_context)
    identity_admin = RecordingIdentityAdmin()

    summary = purge_due_workspace_deletions(
        db_session,
        identity_admin,
        now=NOW + timedelta(days=30),
    )

    assert summary["purged"] == 1
    assert db_session.get(Workspace, workspace_id) is None
    assert db_session.get(type(request_context.user), user_id) is None
    assert identity_admin.deleted_uids == [firebase_uid]

    repeated = purge_due_workspace_deletions(
        db_session,
        identity_admin,
        now=NOW + timedelta(days=31),
    )
    assert repeated["purged"] == 0
    assert identity_admin.deleted_uids == [firebase_uid]


def test_cleanup_keeps_user_and_firebase_when_another_workspace_remains(
    db_session,
    request_context,
):
    deleting_workspace_id = request_context.workspace.id
    other_workspace = Workspace(id=uuid4(), name="Kept workspace")
    db_session.add(other_workspace)
    db_session.flush()
    db_session.add(Membership(
        user_id=request_context.user.id,
        workspace_id=other_workspace.id,
        role="owner",
        status="active",
    ))
    _schedule(db_session, request_context)
    identity_admin = RecordingIdentityAdmin()

    summary = purge_due_workspace_deletions(
        db_session,
        identity_admin,
        now=NOW + timedelta(days=31),
    )

    assert summary["purged"] == 1
    assert db_session.get(Workspace, deleting_workspace_id) is None
    assert db_session.get(Workspace, other_workspace.id) is not None
    assert db_session.get(type(request_context.user), request_context.user.id) is not None
    assert identity_admin.deleted_uids == []


def test_cleanup_refuses_workspace_that_became_shared(db_session, request_context):
    _schedule(db_session, request_context)
    from models import User

    other_user = User(
        id=uuid4(),
        firebase_uid="firebase-late-member",
        email="late-member@example.com",
    )
    db_session.add(other_user)
    db_session.flush()
    db_session.add(Membership(
        user_id=other_user.id,
        workspace_id=request_context.workspace.id,
        role="member",
        status="active",
    ))
    db_session.flush()

    summary = purge_due_workspace_deletions(
        db_session,
        RecordingIdentityAdmin(),
        now=NOW + timedelta(days=31),
    )

    assert summary["shared"] == 1
    assert summary["purged"] == 0
    assert db_session.get(Workspace, request_context.workspace.id) is not None


def test_cleanup_rolls_back_when_firebase_identity_deletion_fails(
    db_session,
    request_context,
):
    workspace_id = request_context.workspace.id
    user_id = request_context.user.id
    _schedule(db_session, request_context)

    summary = purge_due_workspace_deletions(
        db_session,
        RecordingIdentityAdmin(error=RuntimeError("firebase unavailable")),
        now=NOW + timedelta(days=31),
    )

    assert summary["errors"] == 1
    assert summary["purged"] == 0
    assert db_session.get(Workspace, workspace_id) is not None
    assert db_session.get(type(request_context.user), user_id) is not None
