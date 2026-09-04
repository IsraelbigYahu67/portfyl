"""Provider-neutral transactional notification outbox delivery."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from models import NotificationOutbox, User


class NotificationTransport(Protocol):
    def send(self, *, recipient: str, kind: str, payload: dict) -> None: ...


def deliver_notification_outbox(
    db: Session,
    *,
    workspace_id: UUID,
    transport: NotificationTransport,
    now: datetime | None = None,
    max_attempts: int = 5,
) -> list[dict]:
    """Deliver due rows for exactly one RLS-scoped workspace.

    The caller owns commit/rollback. The outbox payload is deliberately small
    template metadata and must never contain credentials or portfolio data.
    """
    now = now or datetime.now(timezone.utc)
    rows = db.scalars(
        select(NotificationOutbox).where(
            NotificationOutbox.workspace_id == workspace_id,
            NotificationOutbox.status.in_(("pending", "failed")),
            NotificationOutbox.attempts < max_attempts,
            or_(NotificationOutbox.next_attempt_at.is_(None), NotificationOutbox.next_attempt_at <= now),
        ).order_by(NotificationOutbox.created_at).limit(100)
    ).all()
    results = []
    for row in rows:
        user = db.get(User, row.user_id)
        if user is None:
            row.status = "failed"
            row.attempts = max_attempts
            row.last_error = "recipient_missing"
            continue
        row.status = "sending"
        row.attempts += 1
        try:
            transport.send(recipient=user.email, kind=row.kind, payload=dict(row.payload or {}))
            row.status = "sent"
            row.sent_at = now
            row.last_error = None
            row.next_attempt_at = None
            results.append({"kind": row.kind, "status": "sent"})
        except Exception as exc:
            row.status = "failed"
            row.last_error = type(exc).__name__
            row.next_attempt_at = now + timedelta(minutes=min(60, 2 ** min(row.attempts, 5)))
            results.append({"kind": row.kind, "status": "retry"})
    db.flush()
    return results
