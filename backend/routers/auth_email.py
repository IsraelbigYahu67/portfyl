"""Verification and password-reset e-mails sent by Portfyl through Brevo.

Three unauthenticated endpoints (spec 5.3): the two e-mails, and
``/password-reset-done``, which the reset page calls after Firebase accepted a
new password so that Portfyl ends the user's sessions at once (spec 7). They
use no session cookie, so like ``/auth/session`` they carry no CSRF
dependency; they are protected by rate limits instead (per IP, and per account
or address).

Rules this module keeps:

* Every endpoint and dependency is a plain ``def`` (they run in the
  threadpool). No pooled connection is held while waiting on an outbound
  Firebase or Brevo call or on the timing floor: the e-mail endpoints use the
  database only after their outbound calls, and ``/password-reset-done``
  releases its connection before the Firebase lookup.
* No e-mail address, link, one-time code or key reaches a log line, an
  exception text or audit metadata. Failures are logged as a reason code or an
  exception *class name* only.
* The password-reset answer never depends on the account: status and body are
  the same for an existing account, an unknown address, a malformed ``email``,
  a hit per-address limit, a Firebase error and a Brevo error. The handler
  never returns before ``RESET_MIN_SECONDS`` and answers on a
  ``RESET_STEP_SECONDS`` grid above it. Every reset makes exactly one Brevo
  call, a send or else a health probe, so the mailer's health flag (which
  turns the next answer into a 503) moves the same way for every address.
* ``/password-reset-done`` follows the same answer rule (always ``202
  accepted`` after the same floor) and never trusts its caller: it ends
  sessions only when Firebase's own password time moved past the stored one.
"""

from __future__ import annotations

import logging
import math
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
from database import get_db, release_connection, set_rls_context
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
from routers import auth as auth_routes
from routers.auth import AuthAPIError, get_identity_verifier

log = logging.getLogger("portfyl.auth_email")

router = APIRouter(prefix="/auth/email", tags=["auth"])

# The reset endpoint does not answer sooner than this, measured from the start
# of its work, so the slower "account exists" path is not visible in the
# response time. Above the floor the answer is rounded up to the next step,
# so what is left of a difference between the paths is hidden unless it
# crosses a step boundary. Tests patch ``_now`` and ``_sleep``.
RESET_MIN_SECONDS = 1.5
RESET_STEP_SECONDS = 0.5
MAX_ADDRESS_LENGTH = 320
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
    # Accepts anything: a missing, non-string or over-long value is handled as
    # an invalid address (202, nothing sent), never a 422 that would answer
    # differently from a well-formed request.
    email: Any = None
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


class _ResetAttempt:
    """Whether this reset request reached ``transport.send`` (even a send that
    then failed). A request that did not gets a health probe instead."""

    send_attempted = False


def _attempt_password_reset(
    request: Request, mailer: Mailer, db: Session, raw_address: Any, lang: str,
    attempt: _ResetAttempt,
) -> None:
    kind = EmailKind.PASSWORD_RESET
    typed = raw_address.strip() if isinstance(raw_address, str) else None
    if typed is None or len(typed) > MAX_ADDRESS_LENGTH:
        log.info("auth_email kind=%s lang=%s outcome=invalid_address", kind.value, lang)
        return

    # The typed address is what Firebase is asked about, what the e-mail shows
    # and where it goes. The normalized form is only for the per-address limit
    # and the ``User`` lookup (``users.email`` is stored normalized).
    address = normalize_email(typed)

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

    if not _PLAUSIBLE_ADDRESS.fullmatch(typed):
        log.info("auth_email kind=%s lang=%s outcome=invalid_address", kind.value, lang)
        return

    try:
        action_url = mailer.links.password_reset_url(typed, lang)
    except AccountNotFound:
        log.info("auth_email kind=%s lang=%s outcome=no_account", kind.value, lang)
        return
    except ActionLinkError as exc:
        log.error(
            "auth_email kind=%s lang=%s outcome=failed error=%s",
            kind.value, lang, _error_code(exc),
        )
        return

    rendered = render(kind, lang, params={"email": typed}, action_url=action_url)
    attempt.send_attempted = True
    try:
        message_id = mailer.transport.send(to=typed, email=rendered, tag=kind.value)
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
    attempt = _ResetAttempt()
    try:
        _attempt_password_reset(request, mailer, db, payload.email, lang, attempt)
    except Exception as exc:  # noqa: BLE001 - the answer must not depend on any failure
        log.error(
            "auth_email kind=%s lang=%s outcome=failed error=%s",
            EmailKind.PASSWORD_RESET.value, lang, _error_code(exc),
        )
    if not attempt.send_attempted:
        # One Brevo call on every path: without it only a reset for an
        # existing account could move the health flag, and "202 turned into
        # 503" would reveal the account.
        try:
            mailer.transport.probe()
        except Exception as exc:  # noqa: BLE001 - probe() should not raise; never trust it
            log.error("auth_email probe failed error=%s", type(exc).__name__)

    return _accepted_after_floor(db, start)


def _accepted_after_floor(db: Session, start: float) -> JSONResponse:
    """The one answer of both reset endpoints: ``202 accepted``, never sooner
    than ``RESET_MIN_SECONDS`` after ``start`` and on the ``RESET_STEP_SECONDS``
    grid above it, with no pooled connection held while waiting."""
    # The account lookup may have left a read transaction open; do not hold a
    # pooled connection while waiting out the floor.
    try:
        release_connection(db)
    except Exception as exc:  # noqa: BLE001
        log.error("auth_email release failed error=%s", type(exc).__name__)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass

    elapsed = _now() - start
    steps = math.ceil(elapsed / RESET_STEP_SECONDS - 1e-9)  # 2.0 s stays 2.0 s
    target = max(RESET_MIN_SECONDS, steps * RESET_STEP_SECONDS)
    _sleep(max(0.0, target - elapsed))
    return _json(202, {"status": "accepted"})


# --- after a password reset ---------------------------------------------------


class PasswordResetDoneRequest(BaseModel):
    # Same leniency as PasswordResetRequest: any value, never a 422.
    email: Any = None
    lang: Any = None


def _password_reset_done(
    request: Request, db: Session, verifier: Any, raw_address: Any, lang: str,
) -> None:
    """Run the sign-in's password-change detection for the named account.

    The caller's claim that a reset happened is never trusted: only Firebase's
    own "password last changed" time, compared with the stored value, can end
    sessions (``routers.auth.record_password_change``). So the worst a caller
    can do is make Portfyl notice a real change sooner. Every early return is
    silent; the endpoint answers the same whatever happens here.
    """
    typed = raw_address.strip() if isinstance(raw_address, str) else None
    if typed is None or len(typed) > MAX_ADDRESS_LENGTH:
        log.info("password_reset_done outcome=invalid_address")
        return
    address = normalize_email(typed)

    if _is_cloud(request):
        try:
            _consume_target(f"reset-done:{address}")
        except RateLimitExceeded:
            log.info("password_reset_done outcome=target_limited")
            return
        except RateLimitUnavailable as exc:
            log.error(
                "password_reset_done outcome=limiter_unavailable error=%s",
                exc.original_exception_type,
            )
            return

    if not _PLAUSIBLE_ADDRESS.fullmatch(typed):
        log.info("password_reset_done outcome=invalid_address")
        return

    # `users` has no tenant policy (sign-in has to find the user before any
    # RLS identity exists), so this lookup works without a request context.
    user = db.scalar(select(User).where(User.email == address))
    if user is None or not user.firebase_uid or user.disabled_at is not None:
        log.info("password_reset_done outcome=no_tracked_account")
        return
    firebase_uid = user.firebase_uid

    # One outbound Firebase lookup: hand the pooled connection back first.
    release_connection(db)
    password_updated_at = auth_routes._read_password_updated_at(verifier, firebase_uid)
    if password_updated_at is None:
        log.info("password_reset_done outcome=no_password_time")
        return

    if not auth_routes.record_password_change(
        db, user, password_updated_at, trigger="password_reset",
    ):
        db.commit()  # first sight stores the time; otherwise nothing is pending
        log.info("password_reset_done outcome=no_change")
        return
    db.commit()
    log.info("password_reset_done outcome=sessions_revoked")
    auth_routes.notify_password_change(db, user, lang)


@router.post(
    "/password-reset-done",
    dependencies=[Depends(rate_limit_dependency("auth_email", by="ip"))],
)
def password_reset_done(
    payload: PasswordResetDoneRequest,
    request: Request,
    db: Session = Depends(get_db),
    verifier: Any = Depends(get_identity_verifier),
):
    """Called once by the reset page after Firebase accepted a new password.

    Ends the user's Portfyl sessions and sends the ``password_changed`` notice
    now instead of at the next sign-in (which still checks, as the fallback).
    Unauthenticated and without CSRF like the other two endpoints here. The
    answer is ``202 accepted`` with the reset endpoint's timing floor for an
    existing, unknown, Google-only, unchanged or invalid address, a hit
    per-address limit and any failure. Only the per-IP limit (429, before the
    body is read) and a malformed JSON body (422) differ, and neither depends
    on an account. Works with the mailer off: ending sessions does not need it.
    """
    start = _now()
    lang = normalize_language(payload.lang)
    try:
        _password_reset_done(request, db, verifier, payload.email, lang)
    except Exception as exc:  # noqa: BLE001 - the answer must not depend on any failure
        log.error("password_reset_done outcome=failed error=%s", type(exc).__name__)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
    return _accepted_after_floor(db, start)
