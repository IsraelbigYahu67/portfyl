from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from audit import record_audit_event
from auth import (
    clear_session_cookie,
    create_session,
    csrf_matches,
    resolve_session,
    revoke_all_sessions,
    revoke_session,
    rotate_csrf_token,
    session_token_from_request,
    set_session_cookie,
)
from database import get_db, set_rls_context
from firebase_identity import (
    FirebaseIdentityVerifier,
    IdentityVerificationError,
    VerifiedIdentity,
)
from models import AuthSession, Membership, User, Workspace


router = APIRouter(prefix="/auth", tags=["auth"])


class SessionExchange(BaseModel):
    id_token: str


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


def _provision_identity(
    db: Session,
    identity: VerifiedIdentity,
) -> User:
    user = db.scalar(select(User).where(User.firebase_uid == identity.uid))
    if user is not None:
        if user.email != identity.email or user.disabled_at is not None:
            raise AuthAPIError(401, "authentication_required")
        user.display_name = identity.display_name
        user.email_verified_at = _verified_now()
        db.flush()
        return user

    user = db.scalar(select(User).where(User.email == identity.email))
    if user is not None:
        if user.firebase_uid not in (None, identity.uid):
            raise AuthAPIError(409, "identity_conflict")
        if user.disabled_at is not None:
            raise AuthAPIError(401, "authentication_required")
        user.firebase_uid = identity.uid
        user.display_name = identity.display_name
        user.email_verified_at = _verified_now()
        db.flush()
        return user

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
    return user


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
    if not csrf_matches(session, request.headers.get("X-CSRF-Token")):
        raise AuthAPIError(403, "csrf_failed")


@router.post("/session", status_code=201)
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

    user = _provision_identity(db, identity)
    issued = create_session(
        db,
        user.id,
        user_agent=request.headers.get("User-Agent"),
    )
    response_payload = _account_payload(db, user, issued.csrf_token)
    record_audit_event(
        db,
        actor_user_id=user.id,
        action="auth.session.created",
        target_type="user",
        target_id=str(user.id),
        metadata={"user_agent": request.headers.get("User-Agent") or ""},
    )
    db.commit()
    response = JSONResponse(response_payload, status_code=201)
    set_session_cookie(response, issued.raw_token)
    return response


@router.get("/me")
def get_me(request: Request, db: Session = Depends(get_db)):
    session, user = _require_session(db, request)
    csrf_token = rotate_csrf_token(db, session)
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
