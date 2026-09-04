"""One-time activation-based cloud trial grants."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from audit import record_audit_event
from billing_config import BillingConfig
from models import NotificationOutbox, TrialGrant, User, Workspace


TRIAL_DURATION = timedelta(days=7)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def identity_fingerprint(email: str, key: str) -> str:
    normalized = email.strip().lower().encode("utf-8")
    return hmac.new(key.encode("utf-8"), normalized, hashlib.sha256).hexdigest()


def activate_trial(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    activation_kind: str,
    config: BillingConfig,
    now: datetime | None = None,
) -> TrialGrant | None:
    """Create the sole workspace/identity grant without committing.

    Returns the existing workspace grant for an idempotent repeat, or ``None``
    if the same verified identity already consumed a trial elsewhere.
    """
    if not config.enabled:
        return None
    if user.email_verified_at is None or not config.trial_identity_key:
        return None
    if activation_kind not in {"csv_import", "broker_connection"}:
        raise ValueError("Unsupported trial activation kind")
    existing = db.scalar(select(TrialGrant).where(TrialGrant.workspace_id == workspace.id))
    if existing is not None:
        return existing
    fingerprint = identity_fingerprint(user.email, config.trial_identity_key)
    if db.scalar(select(TrialGrant).where(TrialGrant.identity_fingerprint == fingerprint)):
        return None
    started = now or _utcnow()
    grant = TrialGrant(
        workspace_id=workspace.id,
        activated_by_user_id=user.id,
        identity_fingerprint=fingerprint,
        activation_kind=activation_kind,
        started_at=started,
        ends_at=started + TRIAL_DURATION,
    )
    try:
        with db.begin_nested():
            db.add(grant)
            db.flush()
            db.add(NotificationOutbox(
                workspace_id=workspace.id,
                user_id=user.id,
                kind="trial_activated",
                deduplication_key=f"trial:{grant.public_id}:activated",
                payload={"trial_ends_at": grant.ends_at.isoformat()},
            ))
            db.flush()
    except IntegrityError:
        return db.scalar(select(TrialGrant).where(TrialGrant.workspace_id == workspace.id))
    record_audit_event(
        db,
        actor_user_id=user.id,
        workspace_id=workspace.id,
        action="billing.trial.activated",
        target_type="trial_grant",
        target_id=str(grant.public_id),
        metadata={"activation_kind": activation_kind, "ends_at": grant.ends_at.isoformat()},
    )
    return grant
