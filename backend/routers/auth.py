from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from rate_limit import client_ip as _client_ip, rate_limit
import legal_acceptance
import trials
import turnstile

from audit import record_audit_event
from beta_access import BetaAccessDenied, require_active_invite
from auth import (
    _as_utc,
    clear_session_cookie,
    create_session,
    csrf_matches,
    resolve_session,
    revoke_all_sessions,
    derive_csrf_token,
    revoke_session,
    session_token_from_request,
    set_session_cookie,
)
from database import get_db, release_connection, set_rls_context
from edition import Edition, edition_from_env
from emails.catalog import EmailKind, normalize_language
from emails.notify import send_account_notice
from emails.transport import load_mailer_settings
from firebase_identity import (
    FirebaseIdentityVerifier,
    IdentityVerificationError,
    VerifiedIdentity,
)
from models import AuthSession, Membership, User, Workspace


router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("portfyl.auth")


class SessionExchange(BaseModel):
    id_token: str
    # Optional app language for the password-changed notice. `Any` so garbage
    # never produces a 422; it is normalised (English fallback) before use.
    lang: Any = None
    # Cloudflare Turnstile token, asked for only when this exchange would
    # create a new identity. `Any` so a wrong type reads as "missing"
    # (bot_check_required) instead of a 422.
    turnstile_token: Any = None
    # The register page's "18+ and I accept the Terms / have read the Privacy
    # Policy" box. Only the literal `true` counts; versions and time are set by
    # the server. Required only when this exchange creates a new account.
    terms_accepted: Any = None


class SignupAcceptance(BaseModel):
    id_token: str
    terms_accepted: Any = None


class AuthAPIError(Exception):
    def __init__(self, status_code: int, code: str):
        super().__init__(code)
        self.status_code = status_code
        self.code = code


def auth_api_error_handler(_request: Request, exc: AuthAPIError) -> JSONResponse:
    return JSONResponse({"code": exc.code}, status_code=exc.status_code)


def get_identity_verifier() -> FirebaseIdentityVerifier:
    return FirebaseIdentityVerifier()


def _verified_now() -> datetime:
    return datetime.now(timezone.utc)


def _refresh_profile(user: User, identity: VerifiedIdentity) -> None:
    # Only a provider that actually supplies a name (e.g. Google) may set it;
    # a later e-mail/password login carries no `name` claim and must not wipe
    # the one already on file.
    if identity.display_name is not None:
        user.display_name = identity.display_name
    user.email_verified_at = _verified_now()


def _provision_identity(
    db: Session,
    identity: VerifiedIdentity,
    *,
    grant_trial: bool = False,
    client_ip: str | None = None,
    terms_accepted: bool = False,
) -> tuple[User, bool]:
    """Return the Portfyl user for a verified identity and whether this
    exchange created it (and its personal workspace). With `grant_trial` (the
    cloud edition) a new workspace also gets its free Pro trial, in the same
    transaction, unless one of the trial guards withholds it. A new user also
    gets their Terms acceptance record (the pending one from e-mail
    registration, or one made from `terms_accepted`); whether it is required
    is the caller's decision."""
    user = db.scalar(select(User).where(User.firebase_uid == identity.uid))
    if user is not None:
        if user.email != identity.email or user.disabled_at is not None:
            raise AuthAPIError(401, "authentication_required")
        _refresh_profile(user, identity)
        db.flush()
        return user, False

    user = db.scalar(select(User).where(User.email == identity.email))
    if user is not None:
        if user.firebase_uid not in (None, identity.uid):
            raise AuthAPIError(409, "identity_conflict")
        if user.disabled_at is not None:
            raise AuthAPIError(401, "authentication_required")
        user.firebase_uid = identity.uid
        _refresh_profile(user, identity)
        db.flush()
        return user, False

    user = User(
        firebase_uid=identity.uid,
        email=identity.email,
        display_name=identity.display_name,
        email_verified_at=_verified_now(),
    )
    db.add(user)
    db.flush()
    legal_acceptance.attach_to_new_user(
        db,
        user_id=user.id,
        firebase_uid=identity.uid,
        accepted_now=terms_accepted,
        source=legal_acceptance.source_for_provider(identity.sign_in_provider),
        now=_verified_now(),
    )

    workspace_id = uuid4()
    set_rls_context(db, user_id=user.id, workspace_id=workspace_id)
    workspace = Workspace(
        id=workspace_id,
        name=(
            f"{identity.display_name}'s workspace"
            if identity.display_name
            else "Personal workspace"
        ),
    )
    membership = Membership(
        user_id=user.id,
        workspace_id=workspace_id,
        role="owner",
        status="active",
    )
    db.add(workspace)
    db.flush()
    db.add(membership)
    db.flush()
    if grant_trial:
        trials.grant_trial(
            db,
            workspace_id=workspace_id,
            email=identity.email,
            now=_verified_now(),
            client_ip=client_ip,
            actor_user_id=user.id,
        )
    return user, True


def _needs_bot_check(db: Session, identity: VerifiedIdentity) -> bool:
    """True when `_provision_identity` would create a new user for `identity`:
    neither the Firebase uid nor the e-mail is known. Existing users are never
    challenged. Read-only."""
    if db.scalar(select(User.id).where(User.firebase_uid == identity.uid)) is not None:
        return False
    return db.scalar(select(User.id).where(User.email == identity.email)) is None


def _verify_bot_check(
    config: turnstile.TurnstileConfig, payload: "SessionExchange", request: Request
) -> None:
    """Raise `bot_check_required` (no usable token) or `bot_check_failed`."""
    token = payload.turnstile_token
    if not isinstance(token, str) or not token.strip():
        raise AuthAPIError(403, "bot_check_required")
    # The auth_session rate-limit dependency has already validated the trusted
    # Cloudflare header, so this cannot raise here.
    reason = turnstile.verify_signup_token(config, token, remote_ip=_client_ip(request))
    if reason is not None:
        # Reason code only: never the token, the secret or the identity.
        log.warning("turnstile_check outcome=%s", reason)
        raise AuthAPIError(403, "bot_check_failed")


def _discard_unaccepted_google_identity(
    db: Session, verifier: FirebaseIdentityVerifier, uid: str
) -> None:
    """Best effort: a failure is logged (never the uid) and must not change
    the answer the caller returns. Only called on the branch that would
    create a NEW Portfyl user."""
    release_connection(db)
    try:
        verifier.delete_user(uid)
    except Exception as exc:
        log.warning("firebase_identity_discard_failed error=%s", type(exc).__name__)


def _read_password_updated_at(
    verifier: FirebaseIdentityVerifier, uid: str
) -> datetime | None:
    """Firebase's "password last changed" time, or None when unknown.

    Best effort: a missing method, a Firebase outage or an unexpected shape
    means "unknown", which skips detection for this sign-in and can never
    fail it. The log line carries a reason code only, no identifiers.
    """
    try:
        value = verifier.password_updated_at(uid)
    except Exception as exc:
        log.warning(
            "password_change_detection outcome=lookup_failed error=%s",
            type(exc).__name__,
        )
        return None
    return _as_utc(value) if isinstance(value, datetime) else None


def _observe_password_change(
    db: Session, user: User, password_updated_at: datetime | None
) -> bool:
    """Record Firebase's password time on `user`; True when it moved forward.

    A user without a password (None) is skipped. A NULL stored value is the
    first sight: store the current time and report no change, so deploying
    never e-mails existing users. The caller commits.
    """
    if password_updated_at is None:
        return False
    seen = user.password_changed_seen_at
    if seen is None:
        user.password_changed_seen_at = password_updated_at
        return False
    if password_updated_at > _as_utc(seen):
        # Compare-and-set in the database: two sign-ins racing on the same
        # change both see it as new in Python, but only one UPDATE matches,
        # so only one revokes, audits and (Task 4) notifies.
        result = db.execute(
            update(User)
            .where(
                User.id == user.id,
                User.password_changed_seen_at < password_updated_at,
            )
            .values(password_changed_seen_at=password_updated_at)
            .execution_options(synchronize_session=False)
        )
        db.expire(user, ["password_changed_seen_at"])
        return bool(result.rowcount)
    return False


def record_password_change(
    db: Session,
    user: User,
    password_updated_at: datetime | None,
    *,
    trigger: str,
) -> bool:
    """React to a moved Firebase password time; True when this call did.

    The one detection both callers share: `/auth/session` (trigger
    `sign_in`) and the password-reset-done endpoint in `routers/auth_email.py`
    (trigger `password_reset`). When the time moved forward past the stored
    value (first sight and an unchanged or older time do nothing, see
    `_observe_password_change`), it ends **every** live Portfyl session of the
    user and stages the `auth.password_changed` audit row. `/auth/session`
    creates its new session afterwards, so that one is not among them.

    The compare-and-set in `_observe_password_change` makes this happen once
    per change, whichever caller sees it first. The caller commits, then calls
    `notify_password_change`. `auth_sessions` and `users` carry no tenant
    policy; the audit row is user-scoped (`workspace_id` NULL), which the
    forced `audit_logs` policy accepts only for the user's own RLS identity, so
    that identity is set here.
    """
    if not _observe_password_change(db, user, password_updated_at):
        return False
    revoked = revoke_all_sessions(db, user.id)
    set_rls_context(db, user_id=user.id, workspace_id=None)
    record_audit_event(
        db,
        actor_user_id=user.id,
        action="auth.password_changed",
        target_type="user",
        target_id=str(user.id),
        metadata={"revoked_count": revoked, "trigger": trigger},
    )
    return True


def notify_password_change(db: Session, user: User, lang: str) -> None:
    """Send the `password_changed` notice after the commit that recorded the
    change. Never raises: a failing notice can undo neither the caller's
    answer nor the revocation."""
    try:
        _on_password_changed(db, user, lang)
    except Exception as exc:
        log.warning(
            "password_changed_notice outcome=failed error=%s",
            type(exc).__name__,
        )


def _on_password_changed(db: Session, user: User, lang: str) -> None:
    """Send the best-effort `password_changed` notice (own-emails wave 2).

    Called once, after the commit that records the change, with `lang` already
    normalised (English fallback). It cannot fail or undo the sign-in: the
    helper never raises and the caller swallows anything else. The notice goes
    to the account address; neither the address nor the link reaches a log line
    or audit metadata from here (the helper logs a kind and a reason code).
    """
    settings = load_mailer_settings(os.environ, edition_from_env(os.environ))
    address = user.email
    if settings is None or not address:
        log.info("password_changed_notice outcome=mailer_off")
        return
    # Firebase's own time of the change (what was just stored), not "now".
    seen_at = user.password_changed_seen_at
    changed_at = _as_utc(seen_at) if seen_at is not None else datetime.now(timezone.utc)
    # Nothing is pending after the commit; hand the connection back before the
    # (up to 5 s) outbound call.
    release_connection(db)
    send_account_notice(
        EmailKind.PASSWORD_CHANGED,
        to=address,
        lang=lang,
        params={"email": address, "datetime": changed_at},
        action_url=f"{settings.app_url}/forgot-password",
    )


def _account_payload(db: Session, user: User, csrf_token: str) -> dict:
    set_rls_context(db, user_id=user.id, workspace_id=None)
    memberships = db.scalars(
        select(Membership)
        .where(
            Membership.user_id == user.id,
            Membership.status == "active",
        )
        .order_by(Membership.created_at, Membership.id)
    ).all()
    workspaces = []
    for membership in memberships:
        set_rls_context(
            db,
            user_id=user.id,
            workspace_id=membership.workspace_id,
        )
        workspace = db.get(Workspace, membership.workspace_id)
        if workspace is not None and workspace.archived_at is None:
            workspaces.append({
                "id": str(workspace.public_id),
                "name": workspace.name,
                "role": membership.role,
            })
    return {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
        },
        "workspaces": workspaces,
        "csrf_token": csrf_token,
    }


def _require_session(db: Session, request: Request) -> tuple[AuthSession, User]:
    session = resolve_session(db, session_token_from_request(request))
    if session is None:
        raise AuthAPIError(401, "authentication_required")
    user = db.get(User, session.user_id)
    if user is None or user.disabled_at is not None:
        raise AuthAPIError(401, "authentication_required")
    return session, user


def _require_csrf(request: Request, session: AuthSession) -> None:
    if not csrf_matches(
        session,
        session_token_from_request(request),
        request.headers.get("X-CSRF-Token"),
    ):
        raise AuthAPIError(403, "csrf_failed")


@router.post("/session", status_code=201, dependencies=[Depends(rate_limit("auth_session", by="ip"))])
def exchange_session(
    payload: SessionExchange,
    request: Request,
    db: Session = Depends(get_db),
    verifier: FirebaseIdentityVerifier = Depends(get_identity_verifier),
):
    try:
        identity = verifier.verify_id_token(payload.id_token)
    except IdentityVerificationError as exc:
        raise AuthAPIError(401, "authentication_required") from exc
    if not identity.email_verified:
        raise AuthAPIError(403, "email_verification_required")

    # Cloudflare Access is the outer private-beta gate, but Portfyl owns the
    # authoritative admission decision. Enforce it before _provision_identity
    # so an uninvited Firebase identity cannot create any application records.
    if request.app.state.portfyl_edition is Edition.CLOUD:
        try:
            require_active_invite(db, identity.email)
        except BetaAccessDenied as exc:
            raise AuthAPIError(403, "beta_access_required") from exc

    is_cloud = request.app.state.portfyl_edition is Edition.CLOUD

    # Bot check, on demand: only an exchange that would create a new identity
    # needs a Turnstile token. The lookup happens before the connection is
    # handed back; the siteverify call after it. An app without a config (a
    # bare test harness) behaves as "off"; main.py always sets one, and it
    # fails closed at startup in the cloud edition.
    bot_check = getattr(request.app.state, "turnstile_config", None)
    new_identity = _needs_bot_check(db, identity)
    terms_accepted = payload.terms_accepted is True

    # Creating a cloud account needs a recorded acceptance of the Terms: this
    # request's flag (first Google sign-in) or the pending record written at
    # e-mail registration. Existing accounts are never asked, and an account
    # without a record (created before this rule) keeps working.
    if (
        is_cloud
        and new_identity
        and not terms_accepted
        and not legal_acceptance.has_pending(db, identity.uid)
    ):
        if identity.sign_in_provider == "google.com":
            # The first Google sign-in on /login creates the Firebase identity
            # before the person has seen the Terms. No Portfyl user exists, so
            # nothing but the bare identity is lost: remove it instead of
            # leaving it orphaned (it is recreated on the next sign-in).
            _discard_unaccepted_google_identity(db, verifier, identity.uid)
        raise AuthAPIError(400, "terms_acceptance_required")

    needs_bot_check = (
        is_cloud
        and bot_check is not None
        and bot_check.mode != "off"
        and new_identity
    )

    # Firebase's "password last changed" time is not in the ID token; it is one
    # outbound lookup, so give the pooled connection back first. Unknown
    # (None) skips detection and never fails the sign-in.
    release_connection(db)
    if needs_bot_check:
        _verify_bot_check(bot_check, payload, request)
    password_updated_at = _read_password_updated_at(verifier, identity.uid)

    user, account_created = _provision_identity(
        db,
        identity,
        grant_trial=is_cloud,
        terms_accepted=terms_accepted,
        # The auth_session rate-limit dependency has already validated this
        # trusted Cloudflare header, so it cannot raise here.
        client_ip=_client_ip(request) if is_cloud else None,
    )
    # A moved password time ends the user's other Portfyl sessions (a reset
    # does not end them on its own; the reset page's call to
    # /auth/email/password-reset-done usually got there first). The session
    # created below is new, so it is not among those revoked.
    password_changed = record_password_change(
        db, user, password_updated_at, trigger="sign_in",
    )
    issued = create_session(
        db,
        user.id,
        user_agent=request.headers.get("User-Agent"),
    )
    response_payload = _account_payload(db, user, issued.csrf_token)
    # Lets the SPA tell a first Google sign-in (a signup) apart from a return
    # visit; /auth/me never carries it.
    response_payload["account_created"] = account_created
    record_audit_event(
        db,
        actor_user_id=user.id,
        action="auth.session.created",
        target_type="user",
        target_id=str(user.id),
        metadata={
            "user_agent": request.headers.get("User-Agent") or "",
            "provider": identity.sign_in_provider or "unknown",
        },
    )
    db.commit()
    if password_changed:
        # After the commit, so a failing hook can neither undo the sign-in nor
        # the session revocation.
        notify_password_change(db, user, normalize_language(payload.lang))
    response = JSONResponse(response_payload, status_code=201)
    set_session_cookie(response, issued.raw_token)
    return response


@router.post(
    "/signup-acceptance",
    dependencies=[Depends(rate_limit("auth_session", by="ip"))],
)
def record_signup_acceptance(
    payload: SignupAcceptance,
    db: Session = Depends(get_db),
    verifier: FirebaseIdentityVerifier = Depends(get_identity_verifier),
):
    """Record the Terms acceptance of an e-mail sign-up, before the address is
    verified (the Portfyl account only exists after that, maybe on another
    device). The Firebase ID token proves whose acceptance it is; the e-mail
    does not have to be verified yet. Idempotent, and a no-op for an identity
    that already has a Portfyl account (those never need it)."""
    try:
        identity = verifier.verify_id_token(payload.id_token)
    except IdentityVerificationError as exc:
        raise AuthAPIError(401, "authentication_required") from exc
    if payload.terms_accepted is not True:
        raise AuthAPIError(400, "terms_acceptance_required")
    if db.scalar(select(User.id).where(User.firebase_uid == identity.uid)) is not None:
        return JSONResponse({"status": "not_needed"}, status_code=200)
    legal_acceptance.record_pending(
        db,
        firebase_uid=identity.uid,
        now=_verified_now(),
        source=legal_acceptance.SOURCE_EMAIL,
    )
    db.commit()
    return JSONResponse({"status": "recorded"}, status_code=201)


@router.get("/me")
def get_me(request: Request, db: Session = Depends(get_db)):
    _session, user = _require_session(db, request)
    # The token is derived from the session cookie, so every tab of this
    # session receives the same value and nothing is rotated or stored here.
    csrf_token = derive_csrf_token(session_token_from_request(request))
    payload = _account_payload(db, user, csrf_token)
    db.commit()
    return payload


@router.post("/logout", status_code=204)
def logout(request: Request, db: Session = Depends(get_db)):
    session, user = _require_session(db, request)
    _require_csrf(request, session)
    revoke_session(db, session_token_from_request(request))
    set_rls_context(db, user_id=user.id, workspace_id=None)
    record_audit_event(
        db,
        actor_user_id=user.id,
        action="auth.session.revoked",
        target_type="auth_session",
        target_id=str(session.id),
    )
    db.commit()
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response


@router.post("/logout-all", status_code=204)
def logout_all(
    request: Request,
    db: Session = Depends(get_db),
    verifier: FirebaseIdentityVerifier = Depends(get_identity_verifier),
):
    session, user = _require_session(db, request)
    _require_csrf(request, session)
    if not user.firebase_uid:
        raise AuthAPIError(401, "authentication_required")
    revoked_count = revoke_all_sessions(db, user.id)
    verifier.revoke_refresh_tokens(user.firebase_uid)
    set_rls_context(db, user_id=user.id, workspace_id=None)
    record_audit_event(
        db,
        actor_user_id=user.id,
        action="auth.sessions.revoked_all",
        target_type="user",
        target_id=str(user.id),
        metadata={"revoked_count": revoked_count},
    )
    db.commit()
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response
