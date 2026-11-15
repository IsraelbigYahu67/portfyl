"""Verification and password-reset e-mails sent by Portfyl through Brevo.

Two unauthenticated endpoints (spec 5.3). They use no session cookie, so like
``/auth/session`` they carry no CSRF dependency; they are protected by rate
limits instead (per IP, and per account or address).

Rules this module keeps:

* Both endpoints and every dependency are plain ``def`` (they run in the
  threadpool). The database session is not used before the outbound Firebase
  and Brevo calls, so no pooled connection is held while waiting on them.
* No e-mail address, link, one-time code or key reaches a log line, an
  exception text or audit metadata. Failures are logged as a reason code or an
  exception *class name* only.
* The password-reset answer never depends on the account: status and body are
  the same for an existing account, an unknown address, a hit per-address
  limit, a Firebase error and a Brevo error, and the handler never returns
  before ``RESET_MIN_SECONDS``.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Mapping

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

import rate_limit as rate_limit_module
from audit import record_audit_event
from beta_access import normalize_email
from database import get_db, set_rls_context
from edition import Edition
from emails.catalog import EmailKind, normalize_language
from emails.links import AccountNotFound, ActionLinkBuilder, ActionLinkError
from emails.render import render
from emails.transport import (
    BrevoTransport,
    ConsoleTransport,
    EmailSendError,
    EmailTransport,
    load_mailer_settings,
)
from firebase_identity import IdentityVerificationError
from models import User
from rate_limit import RateLimitExceeded, RateLimitUnavailable
from rate_limit import rate_limit as rate_limit_dependency
from routers.auth import AuthAPIError, get_identity_verifier

log = logging.getLogger("portfyl.auth_email")

router = APIRouter(prefix="/auth/email", tags=["auth"])

# The reset endpoint does not answer sooner than this, measured from the start
# of its work, so the slower "account exists" path is not visible in the
# response time. Tests patch ``_now`` and ``_sleep``.
RESET_MIN_SECONDS = 1.5
_now = time.monotonic
_sleep = time.sleep

_SEND_REASON = re.compile(r"brevo_[a-z0-9_]{1,40}")
_PLAUSIBLE_ADDRESS = re.compile(r"[^@\s]+@[^@\s]+")


@dataclass(frozen=True)
class Mailer:
    transport: EmailTransport
    links: ActionLinkBuilder


def build_mailer(env: Mapping[str, str], edition: Edition) -> Mailer | None:
    """Build the mailer once at startup. Never raises and never touches the
    network: a broken setting means the mailer is off (both endpoints then
    answer 503 and the frontend falls back to Firebase), not that the service
    fails to start."""
    try:
        settings = load_mailer_settings(env, edition)
        if settings is None:
            return None
        transport: EmailTransport = (
            ConsoleTransport() if settings.console else BrevoTransport(settings)
        )
        return Mailer(transport=transport, links=ActionLinkBuilder(app_url=settings.app_url))
    except Exception as exc:  # noqa: BLE001 - startup must survive any setting
        log.error("auth_email mailer construction failed error=%s", type(exc).__name__)
        return None


def get_mailer(request: Request) -> Mailer | None:
    return getattr(request.app.state, "portfyl_mailer", None)


class VerificationRequest(BaseModel):
    id_token: str = Field(max_length=4096)
    # Accepts anything: a garbage value must give English, never a 422.
    lang: Any = None


class PasswordResetRequest(BaseModel):
    email: str = Field(max_length=320)
    lang: Any = None


def _json(status_code: int, body: dict) -> JSONResponse:
    return JSONResponse(body, status_code=status_code, headers={"Cache-Control": "no-store"})


def _error_code(exc: BaseException) -> str:
    """A loggable description of a failure: a Brevo reason code or a class
    name. Never ``str(exc)`` of anything that could carry an address, a link
    or a code."""
    if isinstance(exc, EmailSendError):
        reason = str(exc)
        if _SEND_REASON.fullmatch(reason):
            return reason
    return type(exc).__name__


def _is_cloud(request: Request) -> bool:
    return request.app.state.portfyl_edition is Edition.CLOUD


def _consume_target(rule_identity: str) -> None:
    rate_limit_module.consume_rate_limit(
        rule=rate_limit_module.RATE_LIMIT_RULES["auth_email_target"],
        identity=rule_identity,
    )


@router.post(
    "/verification",
    dependencies=[Depends(rate_limit_dependency("auth_email", by="ip"))],
)
def send_verification_email(
    payload: VerificationRequest,
    request: Request,
    mailer: Mailer | None = Depends(get_mailer),
    verifier: Any = Depends(get_identity_verifier),
):
    if mailer is None or not mailer.transport.available():
        return _json(503, {"code": "email_unavailable"})

    # The address comes from the verified token, never from the body.
    try:
        identity = verifier.verify_id_token(payload.id_token)
    except IdentityVerificationError as exc:
        raise AuthAPIError(401, "authentication_required") from exc

    if identity.email_verified:
        return _json(200, {"status": "already_verified"})

    if _is_cloud(request):
        # RateLimitExceeded -> the normal 429; RateLimitUnavailable -> its 503.
        _consume_target(f"verify:{identity.uid}")

    lang = normalize_language(payload.lang)
    kind = EmailKind.VERIFY_EMAIL
    try:
        action_url = mailer.links.verification_url(identity.email, lang)
        rendered = render(
            kind, lang, params={"email": identity.email}, action_url=action_url
        )
        message_id = mailer.transport.send(
            to=identity.email, email=rendered, tag=kind.value
        )
    except Exception as exc:  # noqa: BLE001 - every failure is the same 503
        log.error(
            "auth_email kind=%s lang=%s outcome=failed error=%s",
            kind.value, lang, _error_code(exc),
        )
        return _json(503, {"code": "email_send_failed"})

    log.info(
        "auth_email kind=%s lang=%s outcome=sent message_id=%s",
        kind.value, lang, message_id,
    )
    return _json(202, {"status": "sent"})


def _record_reset_audit(db: Session, address: str, lang: str) -> None:
    """Audit row for a password reset sent to an existing Portfyl user.

    ``actor_user_id`` is required, so an address with no Portfyl user (never
    signed in, or unknown) gets no row. A failure here is logged and
    swallowed: the answer must not reveal that the account exists.
    """
    try:
        user = db.scalar(select(User).where(User.email == address))
        if user is None:
            return
        set_rls_context(db, user_id=user.id, workspace_id=None)
        record_audit_event(
            db,
            actor_user_id=user.id,
            action="auth.email.sent",
            target_type="user",
            target_id=str(user.id),
            metadata={"kind": EmailKind.PASSWORD_RESET.value, "lang": lang},
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        log.error("auth_email audit failed error=%s", type(exc).__name__)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass


def _attempt_password_reset(
    request: Request, mailer: Mailer, db: Session, raw_address: str, lang: str
) -> None:
    kind = EmailKind.PASSWORD_RESET
    address = normalize_email(raw_address)

    if _is_cloud(request):
        try:
            _consume_target(f"reset:{address}")
        except RateLimitExceeded:
            log.info("auth_email kind=%s lang=%s outcome=target_limited", kind.value, lang)
            return
        except RateLimitUnavailable as exc:
            log.error(
                "auth_email kind=%s lang=%s outcome=limiter_unavailable error=%s",
                kind.value, lang, exc.original_exception_type,
            )
            return

    if len(address) > 320 or not _PLAUSIBLE_ADDRESS.fullmatch(address):
        log.info("auth_email kind=%s lang=%s outcome=invalid_address", kind.value, lang)
        return

    try:
        action_url = mailer.links.password_reset_url(address, lang)
    except AccountNotFound:
        log.info("auth_email kind=%s lang=%s outcome=no_account", kind.value, lang)
        return
    except ActionLinkError as exc:
        log.error(
            "auth_email kind=%s lang=%s outcome=failed error=%s",
            kind.value, lang, _error_code(exc),
        )
        return

    rendered = render(kind, lang, params={"email": address}, action_url=action_url)
    try:
        message_id = mailer.transport.send(to=address, email=rendered, tag=kind.value)
    except EmailSendError as exc:
        log.error(
            "auth_email kind=%s lang=%s outcome=failed error=%s",
            kind.value, lang, _error_code(exc),
        )
        return

    log.info(
        "auth_email kind=%s lang=%s outcome=sent message_id=%s",
        kind.value, lang, message_id,
    )
    _record_reset_audit(db, address, lang)


@router.post(
    "/password-reset",
    dependencies=[Depends(rate_limit_dependency("auth_email", by="ip"))],
)
def send_password_reset_email(
    payload: PasswordResetRequest,
    request: Request,
    mailer: Mailer | None = Depends(get_mailer),
    db: Session = Depends(get_db),
):
    if mailer is None or not mailer.transport.available():
        return _json(503, {"code": "email_unavailable"})

    start = _now()
    lang = normalize_language(payload.lang)
    try:
        _attempt_password_reset(request, mailer, db, payload.email, lang)
    except Exception as exc:  # noqa: BLE001 - the answer must not depend on any failure
        log.error(
            "auth_email kind=%s lang=%s outcome=failed error=%s",
            EmailKind.PASSWORD_RESET.value, lang, _error_code(exc),
        )
    _sleep(max(0.0, RESET_MIN_SECONDS - (_now() - start)))
    return _json(202, {"status": "accepted"})
