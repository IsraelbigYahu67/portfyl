"""Verified, immediate workspace (and, with its last workspace, account) deletion.

``delete_workspace_now`` is the only way to start a deletion: it checks the same
guards as before (owner, typed name, fresh re-authentication, sole member, and
either no renewing subscription or the owner's explicit consent to cancel it
now) and then erases the data in the same request. There is
no grace period and no undo. The deferred state machine below
(``get_workspace_deletion``, ``cancel_workspace_deletion`` and
``purge_due_workspace_deletions``) remains only to finish requests that were
scheduled under the earlier 30-day rule; nothing creates new ones.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from audit import record_audit_event
from emails.catalog import SOURCE_LANGUAGE, EmailKind, normalize_language
from emails.notify import send_account_notice
from firebase_identity import VerifiedIdentity
from database import release_connection
from models import Membership, Subscription, User, Workspace, WorkspaceSetting
from stripe_client import StripeClientProtocol, StripeError
from tenancy import RequestContext, RequestContextError


DELETION_SETTING_KEY = "privacy.workspace_deletion"
DELETION_STATE_VERSION = 1
MAX_REAUTH_AGE = timedelta(minutes=5)
MAX_REAUTH_FUTURE_SKEW = timedelta(minutes=1)

logger = logging.getLogger("portfyl.account_deletion")


@dataclass(frozen=True)
class WorkspaceDeletion:
    version: int
    requested_at: datetime
    execute_after: datetime
    requested_by_user_id: UUID
    # Language of the e-mails about this request (the backend stores no other
    # language). Last and defaulted so states stored before wave 2, which have
    # no such key, still parse (as English).
    lang: str = SOURCE_LANGUAGE


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse(raw: str) -> WorkspaceDeletion:
    try:
        data = json.loads(raw)
        state = WorkspaceDeletion(
            version=int(data["version"]),
            requested_at=_as_utc(datetime.fromisoformat(data["requested_at"])),
            execute_after=_as_utc(datetime.fromisoformat(data["execute_after"])),
            requested_by_user_id=UUID(data["requested_by_user_id"]),
            lang=normalize_language(data.get("lang")),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError("Malformed workspace deletion state") from exc
    if state.version != DELETION_STATE_VERSION:
        raise RuntimeError("Unsupported workspace deletion state version")
    if state.execute_after <= state.requested_at:
        raise RuntimeError("Invalid workspace deletion deadline")
    return state


def get_workspace_deletion(
    db: Session,
    workspace_id: UUID,
) -> WorkspaceDeletion | None:
    row = db.scalar(
        select(WorkspaceSetting).where(
            WorkspaceSetting.workspace_id == workspace_id,
            WorkspaceSetting.key == DELETION_SETTING_KEY,
        )
    )
    if row is None or not row.value:
        return None
    return _parse(row.value)


def _validate_reauthentication(
    context: RequestContext,
    identity: VerifiedIdentity,
    *,
    now: datetime,
) -> None:
    if not identity.email_verified:
        raise RequestContextError(403, "email_verification_required")
    if (
        not context.user.firebase_uid
        or identity.uid != context.user.firebase_uid
        or identity.email != context.user.email
    ):
        raise RequestContextError(403, "reauthentication_identity_mismatch")
    if identity.authenticated_at is None:
        raise RequestContextError(403, "recent_reauthentication_required")
    authenticated_at = _as_utc(identity.authenticated_at)
    age = now - authenticated_at
    if age > MAX_REAUTH_AGE or age < -MAX_REAUTH_FUTURE_SKEW:
        raise RequestContextError(403, "recent_reauthentication_required")


def _validate_deletion_request(
    db: Session,
    context: RequestContext,
    identity: VerifiedIdentity,
    confirmation: str,
    *,
    now: datetime,
    cancel_subscription: bool = False,
) -> str | None:
    """Run every guard. Returns the Stripe id of the renewing subscription the
    caller must cancel before erasing, or ``None`` when there is none."""
    if context.membership.role != "owner":
        raise RequestContextError(403, "workspace_owner_required")
    if confirmation != context.workspace.name:
        raise RequestContextError(400, "workspace_confirmation_mismatch")
    _validate_reauthentication(context, identity, now=now)

    active_members = db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.workspace_id == context.workspace.id,
            Membership.status == "active",
        )
    ) or 0
    if active_members != 1:
        raise RequestContextError(409, "workspace_has_other_members")

    # Deleting the workspace does not stop Stripe from charging the card, so a
    # renewing subscription must be cancelled first: either by the user in the
    # Customer Portal, or here when the user explicitly consented to losing the
    # rest of the paid period. One already set to end at period end, or past
    # due, may proceed untouched.
    renewing = db.scalar(
        select(Subscription.stripe_subscription_id).where(
            Subscription.workspace_id == context.workspace.id,
            Subscription.ended_at.is_(None),
            Subscription.status.in_(("active", "trialing")),
            Subscription.cancel_at_period_end.is_(False),
        )
    )
    if renewing is None:
        return None
    if cancel_subscription is not True:
        raise RequestContextError(409, "active_subscription")
    return renewing


def _cancel_subscription_before_erasure(
    db: Session,
    subscription_id: str,
    stripe_client_factory: Callable[[], StripeClientProtocol] | None,
) -> None:
    """Cancel the renewing subscription in Stripe now (no refund, no final
    invoice). Anything but success aborts the deletion: never erase a
    workspace whose card may still be charged."""
    # Slow outbound call: hand the pooled connection back first. Nothing has
    # been written yet, so this is a plain end of the read transaction.
    release_connection(db)
    try:
        if stripe_client_factory is None:
            raise RuntimeError("Stripe client unavailable")
        client = stripe_client_factory()
        client.cancel_subscription(subscription_id)
    except StripeError as exc:
        # Stripe no longer knows an active subscription under this id: it is
        # already cancelled (or gone), which is what we wanted.
        if exc.status == 404 or exc.code == "resource_missing":
            logger.info("subscription already cancelled in Stripe before deletion")
            return
        logger.warning(
            "subscription cancel for deletion failed status=%s code=%s",
            exc.status, exc.code,
        )
        raise RequestContextError(503, "subscription_cancel_failed") from exc
    except Exception as exc:  # noqa: BLE001 - billing off / client not buildable
        logger.error(
            "subscription cancel for deletion impossible: %s", type(exc).__name__
        )
        raise RequestContextError(503, "subscription_cancel_failed") from exc
    logger.info("subscription cancelled immediately because of workspace deletion")


@dataclass(frozen=True)
class DeletionResult:
    """Outcome of an immediate deletion.

    ``farewell`` is ``(address, language)`` when the account itself went with
    its last workspace, else ``None``. It is read before the user row is
    deleted so the notice can be sent after the commit.
    """

    account_deleted: bool
    farewell: tuple[str, str] | None = None


def _erase_workspace(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    identity_admin,
    now: datetime,
    lang: str,
) -> DeletionResult:
    """Delete the workspace and, if it was the user's last, the user and their
    Firebase identity. Flushes but never commits: the caller owns the
    transaction, so a Firebase failure rolls everything back.
    """
    other_memberships = db.scalar(
        select(func.count())
        .select_from(Membership)
        .where(
            Membership.user_id == user.id,
            Membership.workspace_id != workspace.id,
        )
    ) or 0

    farewell: tuple[str, str] | None = None
    db.delete(workspace)
    db.flush()
    if other_memberships == 0:
        if user.email:
            farewell = (user.email, lang)
        user.disabled_at = now
        db.flush()
        if user.firebase_uid:
            identity_admin.delete_user(user.firebase_uid)
        db.delete(user)
        db.flush()
    return DeletionResult(account_deleted=other_memberships == 0, farewell=farewell)


def delete_workspace_now(
    db: Session,
    context: RequestContext,
    *,
    identity: VerifiedIdentity,
    confirmation: str,
    identity_admin,
    now: datetime | None = None,
    lang: object = None,
    cancel_subscription: bool = False,
    stripe_client_factory: Callable[[], StripeClientProtocol] | None = None,
) -> DeletionResult:
    """Validate and erase the caller's workspace immediately.

    ``cancel_subscription`` is the owner's consent to lose the rest of a paid
    period: a renewing subscription is then cancelled in Stripe (through
    ``stripe_client_factory``, only called when there is one) after all other
    checks pass and before anything is erased.

    Same guards as the old scheduled flow. Nothing is committed here: the
    endpoint commits, then sends the ``account_deleted`` notice from the
    result. There is no audit row to write, because audit rows are scoped to
    the workspace and the user being deleted and would be deleted with them.
    """
    now = _as_utc(now or datetime.now(timezone.utc))
    subscription_id = _validate_deletion_request(
        db, context, identity, confirmation, now=now,
        cancel_subscription=cancel_subscription,
    )
    if subscription_id is not None:
        # The Stripe cancel is external and cannot be rolled back. If the
        # erasure below fails afterwards (for instance Firebase refuses), the
        # subscription stays cancelled: the user can simply retry the deletion
        # and is never charged again.
        _cancel_subscription_before_erasure(db, subscription_id, stripe_client_factory)
    # Same RLS context the cleanup job uses, so the deletes below pass the
    # policies on the workspace and the user.
    _set_cleanup_context(db, context.workspace.id, context.user.id)
    result = _erase_workspace(
        db,
        workspace=context.workspace,
        user=context.user,
        identity_admin=identity_admin,
        now=now,
        lang=normalize_language(lang),
    )
    logger.info("workspace deleted immediately account_deleted=%s", result.account_deleted)
    return result


def send_account_deleted_notice(*, to: str, lang: str, mailer: object) -> bool:
    try:
        return send_account_notice(
            EmailKind.ACCOUNT_DELETED,
            to=to,
            lang=lang,
            params={"email": to},
            mailer=mailer,
        )
    except Exception:  # noqa: BLE001 - a notice must never fail the purge
        logger.error("account_deletion notice kind=account_deleted failed")
        return False


def cancel_workspace_deletion(
    db: Session,
    context: RequestContext,
) -> bool:
    row = db.scalar(
        select(WorkspaceSetting).where(
            WorkspaceSetting.workspace_id == context.workspace.id,
            WorkspaceSetting.key == DELETION_SETTING_KEY,
        )
    )
    if row is None:
        return False
    db.delete(row)
    record_audit_event(
        db,
        actor_user_id=context.user.id,
        workspace_id=context.workspace.id,
        action="account.deletion.cancelled",
        target_type="workspace",
        target_id=str(context.workspace.public_id),
    )
    db.flush()
    return True


def deletion_status_payload(state: WorkspaceDeletion | None) -> dict:
    if state is None:
        return {"scheduled": False}
    return {
        "scheduled": True,
        "requested_at": state.requested_at.isoformat(),
        "execute_after": state.execute_after.isoformat(),
    }


def _rls_enforced(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def _active_workspace_ids(db: Session) -> list[UUID]:
    """Enumerate active workspaces through the existing job-only RLS policy."""
    if not _rls_enforced(db):
        return list(db.scalars(
            select(Workspace.id).where(Workspace.archived_at.is_(None))
        ).all())
    db.execute(text("SELECT set_config('portfyl.job_context', 'true', true)"))
    try:
        return list(db.scalars(
            select(Workspace.id).where(Workspace.archived_at.is_(None))
        ).all())
    finally:
        db.execute(text("SELECT set_config('portfyl.job_context', '', true)"))


def _set_cleanup_context(
    db: Session,
    workspace_id: UUID,
    user_id: UUID | None = None,
) -> None:
    if not _rls_enforced(db):
        return
    db.execute(
        text("SELECT set_config('portfyl.workspace_id', :value, true)"),
        {"value": str(workspace_id)},
    )
    db.execute(
        text("SELECT set_config('portfyl.user_id', :value, true)"),
        {"value": "" if user_id is None else str(user_id)},
    )


def purge_due_workspace_deletions(
    db: Session,
    identity_admin,
    *,
    now: datetime | None = None,
    mailer: object = None,
) -> dict[str, int]:
    """Purge due explicit requests, committing each workspace independently.

    ``identity_admin`` is the narrow Firebase boundary and must expose
    ``delete_user(uid)``. No plan, trial, or subscription state is consulted.

    When the account itself goes (its last workspace), ``account_deleted`` is
    e-mailed in the language stored with the request. The address is read
    before the user row is deleted, but the notice is sent only after the
    commit: a purge that rolled back (for instance because Firebase failed) and
    is retried then never mails twice, and never claims a deletion that did
    not happen. Sending is best effort and cannot fail or undo the purge.
    ``mailer`` defaults to the process-wide one.
    """
    now = _as_utc(now or datetime.now(timezone.utc))
    summary = {
        "scanned": 0,
        "purged": 0,
        "not_due": 0,
        "shared": 0,
        "invalid": 0,
        "errors": 0,
    }
    workspace_ids = _active_workspace_ids(db)

    for workspace_id in workspace_ids:
        summary["scanned"] += 1
        try:
            _set_cleanup_context(db, workspace_id)
            try:
                state = get_workspace_deletion(db, workspace_id)
            except RuntimeError:
                summary["invalid"] += 1
                db.rollback()
                continue
            if state is None:
                db.commit()
                continue
            if state.execute_after > now:
                summary["not_due"] += 1
                db.commit()
                continue

            _set_cleanup_context(
                db,
                workspace_id,
                user_id=state.requested_by_user_id,
            )
            active_members = db.scalar(
                select(func.count())
                .select_from(Membership)
                .where(
                    Membership.workspace_id == workspace_id,
                    Membership.status == "active",
                )
            ) or 0
            if active_members != 1:
                summary["shared"] += 1
                db.commit()
                continue

            requesting_membership = db.scalar(
                select(Membership).where(
                    Membership.workspace_id == workspace_id,
                    Membership.user_id == state.requested_by_user_id,
                    Membership.status == "active",
                    Membership.role == "owner",
                )
            )
            user = db.scalar(
                select(User).where(User.id == state.requested_by_user_id)
            )
            workspace = db.scalar(
                select(Workspace).where(Workspace.id == workspace_id)
            )
            if requesting_membership is None or user is None or workspace is None:
                summary["invalid"] += 1
                db.rollback()
                continue

            result = _erase_workspace(
                db,
                workspace=workspace,
                user=user,
                identity_admin=identity_admin,
                now=now,
                lang=state.lang,
            )
            farewell = result.farewell
            db.commit()
            summary["purged"] += 1
            if farewell is not None:
                send_account_deleted_notice(
                    to=farewell[0], lang=farewell[1], mailer=mailer
                )
        except Exception:
            db.rollback()
            summary["errors"] += 1
            logger.exception("Workspace deletion failed; transaction rolled back")

    return summary
