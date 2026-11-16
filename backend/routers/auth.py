from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from rate_limit import client_ip as _client_ip, rate_limit
import trials

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
from edition import Edition
from emails.catalog import normalize_language
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
) -> tuple[User, bool]:
    """Return the Portfyl user for a verified identity and whether this
    exchange created it (and its personal workspace). With `grant_trial` (the
    cloud edition) a new workspace also gets its free Pro trial, in the same
    transaction, unless one of the trial guards withholds it."""
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


def _on_password_changed(db: Session, user: User, lang: str) -> None:
    """Hook called once after the commit that records a password change.

    Deliberately a no-op here: Task 4 of the wave 2 plan fills it in with the
    best-effort `password_changed` e-mail (`lang` is already normalised;
    English is the fallback). It runs after the sign-in is committed, and the
    caller swallows any exception, so it can never fail or undo the sign-in.
    Do not put e-mail addresses in logs or audit metadata from here.
    """
    return None


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

    # Firebase's "password last changed" time is not in the ID token; it is one
    # outbound lookup, so give the pooled connection back first. Unknown
    # (None) skips detection and never fails the sign-in.
    release_connection(db)
    password_updated_at = _read_password_updated_at(verifier, identity.uid)

    is_cloud = request.app.state.portfyl_edition is Edition.CLOUD
    user, account_created = _provision_identity(
        db,
        identity,
        grant_trial=is_cloud,
        # The auth_session rate-limit dependency has already validated this
        # trusted Cloudflare header, so it cannot raise here.
        client_ip=_client_ip(request) if is_cloud else None,
    )
    # A moved password time ends the user's other Portfyl sessions (a reset
    # does not end them on its own). The session created below is new, so it
    # is not among those revoked.
    password_changed = _observe_password_change(db, user, password_updated_at)
    revoked_other_sessions = (
        revoke_all_sessions(db, user.id) if password_changed else 0
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
    if password_changed:
        record_audit_event(
            db,
            actor_user_id=user.id,
            action="auth.password_changed",
            target_type="user",
            target_id=str(user.id),
            metadata={"revoked_count": revoked_other_sessions},
        )
    db.commit()
    if password_changed:
        # After the commit, so a failing hook can neither undo the sign-in nor
        # the session revocation.
        try:
            _on_password_changed(db, user, normalize_language(payload.lang))
        except Exception as exc:
            log.warning(
                "password_changed_notice outcome=failed error=%s",
                type(exc).__name__,
            )
    response = JSONResponse(response_payload, status_code=201)
    set_session_cookie(response, issued.raw_token)
    return response


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
