"""Cloud-only, no-payment plan switching for the private test."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app_settings import set_workspace_setting
from audit import record_audit_event
from database import get_db
from edition import Edition
from entitlements import PRIVATE_TEST_PLAN_SETTING_KEY, resolve_entitlements
from models import Workspace
from plans import PlanTier
from tenancy import RequestContext, get_request_context, require_csrf


router = APIRouter(prefix="/test-plans", tags=["test-plans"])


class PlanSelection(BaseModel):
    plan: PlanTier


def _selection_payload(db: Session, context: RequestContext) -> dict[str, object]:
    entitlements = resolve_entitlements(
        db,
        edition=Edition.CLOUD,
        workspace_id=context.workspace.id,
    )
    return {
        **entitlements.payload(),
        "switching_enabled": True,
        "payments_enabled": False,
    }


@router.get("")
def get_test_plan(
    db: Session = Depends(get_db),
    context: RequestContext = Depends(get_request_context),
):
    return _selection_payload(db, context)


@router.put("")
def put_test_plan(
    payload: PlanSelection,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_csrf),
):
    # Serialize workspace-setting upserts so two rapid clicks cannot race the
    # unique (workspace_id, key) constraint on a multi-instance deployment.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            select(Workspace.id)
            .where(Workspace.id == context.workspace.id)
            .with_for_update()
        )

    previous = resolve_entitlements(
        db,
        edition=Edition.CLOUD,
        workspace_id=context.workspace.id,
    ).plan
    set_workspace_setting(
        db,
        context.workspace.id,
        PRIVATE_TEST_PLAN_SETTING_KEY,
        payload.plan.value,
    )
    record_audit_event(
        db,
        actor_user_id=context.user.id,
        workspace_id=context.workspace.id,
        action="plan.test_selection_changed",
        target_type="workspace",
        target_id=str(context.workspace.public_id),
        metadata={"from": previous.value, "to": payload.plan.value},
    )
    # Build the response while the request's transaction-local PostgreSQL RLS
    # context is still active. Session.commit() expires ORM state and ends the
    # transaction, so resolving afterward can no longer safely reload the
    # request workspace.
    result = _selection_payload(db, context)
    db.commit()
    return result
