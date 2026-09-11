"""Invitation-only admission for the cloud beta.

Cloudflare Access is the outer gate. This module is the application-owned
gate: a verified Firebase identity is not allowed to create a Portfyl user or
workspace until its normalized e-mail has an active invitation.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import BetaInvite


class BetaAccessDenied(RuntimeError):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().casefold()


def require_active_invite(db: Session, email: str) -> BetaInvite:
    """Return and, on first use, accept the invitation for ``email``.

    The row is locked so two first-login requests cannot race the transition.
    No User, Workspace, Membership, or AuthSession is created on denial.
    """

    normalized = normalize_email(email)
    invite = db.scalar(
        select(BetaInvite)
        .where(BetaInvite.email == normalized)
        .with_for_update()
    )
    now = _utcnow()
    if (
        invite is None
        or invite.status == "revoked"
        or invite.revoked_at is not None
        or (
            invite.status == "invited"
            and
            invite.expires_at is not None
            and _as_utc(invite.expires_at) <= now
        )
    ):
        raise BetaAccessDenied(normalized)

    if invite.status == "invited":
        invite.status = "accepted"
        invite.accepted_at = now
        db.flush()
    return invite
