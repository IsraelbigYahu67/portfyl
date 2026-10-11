"""Opaque, revocable Portfyl sessions.

Firebase proves an e-mail identity only during login. Every later request uses
an opaque Portfyl token whose SHA-256 digest is stored in PostgreSQL. Raw
session and CSRF tokens never enter the database.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session
from fastapi import Request, Response

from models import AuthSession


SESSION_MAX_AGE = timedelta(days=30)
# last_seen_at is a coarse activity marker. Refreshing it on every request
# turned every read into a pending write, so it moves at most this often.
LAST_SEEN_RESOLUTION = timedelta(minutes=5)


def session_cookie_policy(env: Mapping[str, str]) -> tuple[str, bool]:
    local_test_mode = env.get("PORTFYL_TESTING") == "1"
    if local_test_mode:
        return "portfyl_session", False
    return "__Host-portfyl_session", True


SESSION_COOKIE_NAME, COOKIE_SECURE = session_cookie_policy(os.environ)


@dataclass(frozen=True)
class IssuedSession:
    raw_token: str
    csrf_token: str
    expires_at: datetime


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def create_session(
    db: Session,
    user_id: UUID,
    user_agent: str | None = None,
) -> IssuedSession:
    raw_token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    expires_at = _utcnow() + SESSION_MAX_AGE
    db.add(AuthSession(
        user_id=user_id,
        token_digest=_digest(raw_token),
        csrf_digest=_digest(csrf_token),
        expires_at=expires_at,
        user_agent=user_agent,
    ))
    db.flush()
    return IssuedSession(
        raw_token=raw_token,
        csrf_token=csrf_token,
        expires_at=expires_at,
    )


def _find_session(db: Session, raw_token: str) -> AuthSession | None:
    if not raw_token:
        return None
    token_digest = _digest(raw_token)
    row = db.scalar(
        select(AuthSession).where(AuthSession.token_digest == token_digest)
    )
    if row is None or not hmac.compare_digest(row.token_digest, token_digest):
        return None
    return row


def resolve_session(db: Session, raw_token: str) -> AuthSession | None:
    row = _find_session(db, raw_token)
    now = _utcnow()
    if (
        row is None
        or row.revoked_at is not None
        or _as_utc(row.expires_at) <= now
    ):
        return None
    if row.last_seen_at is None or now - _as_utc(row.last_seen_at) >= LAST_SEEN_RESOLUTION:
        row.last_seen_at = now
    return row


def revoke_session(db: Session, raw_token: str) -> bool:
    row = _find_session(db, raw_token)
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = _utcnow()
    db.flush()
    return True


def revoke_all_sessions(db: Session, user_id: UUID) -> int:
    result = db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=_utcnow())
    )
    db.flush()
    return int(result.rowcount or 0)


def csrf_matches(session: AuthSession, raw_token: str | None) -> bool:
    if not raw_token:
        return False
    return hmac.compare_digest(session.csrf_digest, _digest(raw_token))


def rotate_csrf_token(db: Session, session: AuthSession) -> str:
    raw_token = secrets.token_urlsafe(32)
    session.csrf_digest = _digest(raw_token)
    db.flush()
    return raw_token


def session_token_from_request(request: Request) -> str:
    return request.cookies.get(SESSION_COOKIE_NAME, "")


def set_session_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        max_age=int(SESSION_MAX_AGE.total_seconds()),
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        secure=COOKIE_SECURE,
        httponly=True,
        samesite="lax",
        path="/",
    )
