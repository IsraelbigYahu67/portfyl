"""Workspace data portability and verified deletion endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from account_deletion import (
    cancel_workspace_deletion,
    deletion_status_payload,
    get_workspace_deletion,
    schedule_workspace_deletion,
)
from database import get_db
from firebase_identity import FirebaseIdentityVerifier, IdentityVerificationError
from routers.auth import get_identity_verifier
from tenancy import (
    RequestContext,
    RequestContextError,
    get_request_context,
    require_csrf,
)
from workspace_export import build_workspace_export


router = APIRouter(prefix="/account", tags=["account"])


class DeletionRequestPayload(BaseModel):
    reauth_id_token: str = Field(min_length=1)
    confirmation: str = Field(min_length=1)


@router.get("/export", response_class=Response)
def export_workspace_data(
    db: Session = Depends(get_db),
    context: RequestContext = Depends(get_request_context),
) -> Response:
    exported_at = datetime.now(timezone.utc)
    payload = build_workspace_export(db, context, exported_at=exported_at)
    filename = (
        f"portfyl-workspace-{context.workspace.public_id}-"
        f"{exported_at:%Y%m%d}.json"
    )
    return Response(
        content=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/deletion")
def get_deletion_status(
    db: Session = Depends(get_db),
    context: RequestContext = Depends(get_request_context),
) -> dict:
    return deletion_status_payload(
        get_workspace_deletion(db, context.workspace.id)
    )


@router.post("/deletion", status_code=202)
def schedule_deletion(
    payload: DeletionRequestPayload,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_csrf),
    verifier: FirebaseIdentityVerifier = Depends(get_identity_verifier),
) -> dict:
    try:
        identity = verifier.verify_id_token(payload.reauth_id_token)
    except IdentityVerificationError as exc:
        raise RequestContextError(
            401,
            "recent_reauthentication_required",
        ) from exc
    state = schedule_workspace_deletion(
        db,
        context,
        identity=identity,
        confirmation=payload.confirmation,
    )
    db.commit()
    return deletion_status_payload(state)


@router.delete("/deletion", status_code=204)
def cancel_deletion(
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_csrf),
) -> Response:
    cancel_workspace_deletion(db, context)
    db.commit()
    return Response(status_code=204)
