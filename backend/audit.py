"""Security audit trail helpers.

Callers own the surrounding transaction: an audit row is committed atomically
with the mutation it describes.  Metadata is recursively passed through the
same secret-shape redactor used by application logging.  This intentionally
replaces a matching secret with ``[REDACTED]`` instead of rejecting the whole
business operation; callers must still pass identifiers and non-sensitive
context only.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from logging_setup import redact
from models import AuditLog


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, Mapping):
        return {redact(str(key)): _sanitize(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_sanitize(item) for item in value]
    return value


def record_audit_event(
    db: Session,
    *,
    actor_user_id: UUID,
    action: str,
    workspace_id: UUID | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> AuditLog:
    """Stage one sanitized, immutable audit row without committing it."""
    row = AuditLog(
        actor_user_id=actor_user_id,
        workspace_id=workspace_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        event_metadata=_sanitize(dict(metadata or {})),
    )
    db.add(row)
    db.flush()
    return row
