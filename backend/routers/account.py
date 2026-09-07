"""Workspace data portability and verified deletion endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from database import get_db
from tenancy import RequestContext, get_request_context
from workspace_export import build_workspace_export


router = APIRouter(prefix="/account", tags=["account"])


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
