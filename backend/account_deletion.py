"""Durable state machine for verified, grace-period workspace deletion."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app_settings import set_workspace_setting
from audit import record_audit_event
from emails.catalog import SOURCE_LANGUAGE, EmailKind, normalize_language
from emails.notify import send_account_notice
from firebase_identity import VerifiedIdentity
from models import Membership, Subscription, User, Workspace, WorkspaceSetting
from tenancy import RequestContext, RequestContextError


DELETION_SETTING_KEY = "privacy.workspace_deletion"
DELETION_STATE_VERSION = 1
DELETION_GRACE_DAYS = 30
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


def _serialize(state: WorkspaceDeletion) -> str:
    return json.dumps({
        **asdict(state),
        "requested_at": state.requested_at.isoformat(),
        "execute_after": state.execute_after.isoformat(),
        "requested_by_user_id": str(state.requested_by_user_id),
    }, separators=(",", ":"))


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


def schedule_workspace_deletion(
    db: Session,
    context: RequestContext,
    *,
    identity: VerifiedIdentity,
    confirmation: str,
    now: datetime | None = None,
    lang: object = None,
) -> WorkspaceDeletion:
    now = _as_utc(now or datetime.now(timezone.utc))
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

    # Deleting the workspace does not stop Stripe from charging the card, so
    # a renewing subscription must be cancelled (Customer Portal) first. One
    # already set to end at period end, or past due, may proceed.
    renewing = db.scalar(
        select(Subscription.id).where(
            Subscription.workspace_id == context.workspace.id,
            Subscription.ended_at.is_(None),
            Subscription.status.in_(("active", "trialing")),
            Subscription.cancel_at_period_end.is_(False),
        )
    )
    if renewing is not None:
        raise RequestContextError(409, "active_subscription")

    existing = get_workspace_deletion(db, context.workspace.id)
    if existing is not None:
        return existing

    state = WorkspaceDeletion(
        version=DELETION_STATE_VERSION,
        requested_at=now,
        execute_after=now + timedelta(days=DELETION_GRACE_DAYS),
        requested_by_user_id=context.user.id,
        lang=normalize_language(lang),
    )
    set_workspace_setting(
        db,
        context.workspace.id,
        DELETION_SETTING_KEY,
        _serialize(state),
    )
    record_audit_event(
        db,
        actor_user_id=context.user.id,
        workspace_id=context.workspace.id,
        action="account.deletion.scheduled",
        target_type="workspace",
        target_id=str(context.workspace.public_id),
        metadata={"grace_days": DELETION_GRACE_DAYS},
    )
    return state


def send_deletion_scheduled_notice(
    *,
    to: str,
    state: WorkspaceDeletion,
    mailer: object,
) -> bool:
    """Best-effort ``account_deletion_scheduled`` e-mail; call it only after the
    request is committed. Never raises. The button leads to Settings, where the
    deletion is cancelled."""
    try:
        app_url = getattr(getattr(mailer, "links", None), "_app_url", "")
        return send_account_notice(
            EmailKind.ACCOUNT_DELETION_SCHEDULED,
            to=to,
            lang=state.lang,
            params={"email": to, "date": state.execute_after},
            action_url=f"{app_url}/settings" if app_url else None,
            mailer=mailer,
        )
    except Exception:  # noqa: BLE001 - a notice must never fail the request
        logger.error("account_deletion notice kind=account_deletion_scheduled failed")
        return False


def _send_account_deleted_notice(*, to: str, lang: str, mailer: object) -> bool:
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
        return {"scheduled": False, "grace_days": DELETION_GRACE_DAYS}
    return {
        "scheduled": True,
        "requested_at": state.requested_at.isoformat(),
        "execute_after": state.execute_after.isoformat(),
        "grace_days": DELETION_GRACE_DAYS,
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

            other_memberships = db.scalar(
                select(func.count())
                .select_from(Membership)
                .where(
                    Membership.user_id == user.id,
                    Membership.workspace_id != workspace_id,
                )
            ) or 0

            farewell: tuple[str, str] | None = None
            db.delete(workspace)
            db.flush()
            if other_memberships == 0:
                if user.email:
                    farewell = (user.email, state.lang)
                user.disabled_at = now
                db.flush()
                if user.firebase_uid:
                    identity_admin.delete_user(user.firebase_uid)
                db.delete(user)
                db.flush()
            db.commit()
            summary["purged"] += 1
            if farewell is not None:
                _send_account_deleted_notice(
                    to=farewell[0], lang=farewell[1], mailer=mailer
                )
        except Exception:
            db.rollback()
            summary["errors"] += 1
            logger.exception("Workspace deletion failed; transaction rolled back")

    return summary
