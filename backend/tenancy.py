"""Trusted request, workspace, and portfolio authorization dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth import csrf_matches, resolve_session, session_token_from_request
from database import get_db, set_rls_context
from models import AuthSession, Membership, Portfolio, User, Workspace


class RequestContextError(Exception):
    def __init__(self, status_code: int, code: str):
        super().__init__(code)
        self.status_code = status_code
        self.code = code


def request_context_error_handler(
    _request: Request,
    exc: RequestContextError,
) -> JSONResponse:
    return JSONResponse({"code": exc.code}, status_code=exc.status_code)


@dataclass(frozen=True)
class RequestContext:
    user: User
    workspace: Workspace
    membership: Membership
    session: AuthSession


def _load_workspace(
    db: Session,
    user_id: UUID,
    membership: Membership,
) -> Workspace | None:
    set_rls_context(
        db,
        user_id=user_id,
        workspace_id=membership.workspace_id,
    )
    return db.scalar(
        select(Workspace).where(
            Workspace.id == membership.workspace_id,
            Workspace.archived_at.is_(None),
        )
    )


def get_request_context(
    request: Request,
    db: Session = Depends(get_db),
    x_workspace_id: Annotated[
        str | None,
        Header(alias="X-Workspace-ID"),
    ] = None,
) -> RequestContext:
    auth_session = resolve_session(db, session_token_from_request(request))
    if auth_session is None:
        raise RequestContextError(401, "authentication_required")

    user = db.get(User, auth_session.user_id)
    if user is None or user.disabled_at is not None:
        raise RequestContextError(401, "authentication_required")

    set_rls_context(db, user_id=user.id, workspace_id=None)
    memberships = db.scalars(
        select(Membership)
        .where(
            Membership.user_id == user.id,
            Membership.status == "active",
        )
        .order_by(Membership.created_at, Membership.id)
    ).all()

    requested_workspace = (x_workspace_id or "").strip()
    available = []
    for membership in memberships:
        candidate = _load_workspace(
            db,
            user_id=user.id,
            membership=membership,
        )
        if candidate is not None:
            available.append((membership, candidate))

    selected_membership: Membership | None = None
    workspace: Workspace | None = None
    if requested_workspace:
        try:
            requested_public_id = UUID(requested_workspace)
        except ValueError as exc:
            raise RequestContextError(404, "resource_not_found") from exc
        for membership, candidate in available:
            if candidate.public_id == requested_public_id:
                selected_membership = membership
                workspace = candidate
                break
        if workspace is None:
            raise RequestContextError(404, "resource_not_found")
    else:
        if len(available) > 1:
            raise RequestContextError(400, "workspace_required")
        if not available:
            raise RequestContextError(404, "resource_not_found")
        selected_membership, workspace = available[0]

    set_rls_context(db, user_id=user.id, workspace_id=workspace.id)
    return RequestContext(
        user=user,
        workspace=workspace,
        membership=selected_membership,
        session=auth_session,
    )


def require_csrf(
    request: Request,
    context: RequestContext = Depends(get_request_context),
) -> RequestContext:
    if not csrf_matches(context.session, request.headers.get("X-CSRF-Token")):
        raise RequestContextError(403, "csrf_failed")
    return context


def require_portfolio(
    portfolio_id: UUID | None = Query(None),
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
) -> Portfolio:
    query = select(Portfolio).where(
        Portfolio.workspace_id == context.workspace.id,
    )
    if portfolio_id is not None:
        portfolio = db.scalar(query.where(Portfolio.public_id == portfolio_id))
    else:
        portfolio = db.scalar(
            query.where(Portfolio.is_default.is_(True)).order_by(
                Portfolio.created_at,
                Portfolio.id,
            )
        )
        if portfolio is None:
            portfolio = db.scalar(query.order_by(Portfolio.created_at, Portfolio.id))
    if portfolio is None:
        raise RequestContextError(404, "resource_not_found")
    return portfolio
