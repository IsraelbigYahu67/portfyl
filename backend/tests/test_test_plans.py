from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import select

import routers.test_plans as test_plans_module
from models import AuditLog
from plans import PlanTier
from routers.test_plans import (
    PlanSelection,
    get_test_plan,
    put_test_plan,
    router,
)
from tenancy import require_csrf


def test_new_workspace_starts_on_free(db_session, request_context):
    result = get_test_plan(db_session, request_context)

    assert result["plan"] == "free"
    assert result["switching_enabled"] is True
    assert result["payments_enabled"] is False


@pytest.mark.parametrize("plan", list(PlanTier))
def test_workspace_can_switch_to_every_plan(db_session, request_context, plan):
    result = put_test_plan(
        PlanSelection(plan=plan),
        db_session,
        request_context,
    )

    assert result["plan"] == plan.value
    assert result["source"] == "test_selection"
    assert result["payments_enabled"] is False
    assert get_test_plan(db_session, request_context)["plan"] == plan.value


def test_plan_change_is_audited(db_session, request_context):
    put_test_plan(
        PlanSelection(plan=PlanTier.PRO),
        db_session,
        request_context,
    )

    event = db_session.scalar(
        select(AuditLog).where(AuditLog.action == "plan.test_selection_changed")
    )
    assert event is not None
    assert event.workspace_id == request_context.workspace.id
    assert event.actor_user_id == request_context.user.id
    assert event.event_metadata == {"from": "free", "to": "pro"}


def test_response_is_built_before_commit_to_preserve_rls_context(
    db_session, request_context, monkeypatch
):
    events = []
    original_payload = test_plans_module._selection_payload
    original_commit = db_session.commit

    def tracked_payload(db, context):
        events.append("payload")
        return original_payload(db, context)

    def tracked_commit():
        events.append("commit")
        return original_commit()

    monkeypatch.setattr(test_plans_module, "_selection_payload", tracked_payload)
    monkeypatch.setattr(db_session, "commit", tracked_commit)

    put_test_plan(
        PlanSelection(plan=PlanTier.INVESTOR),
        db_session,
        request_context,
    )

    assert events == ["payload", "commit"]


def test_unknown_plan_is_rejected():
    with pytest.raises(ValidationError):
        PlanSelection(plan="enterprise")


def test_plan_mutation_uses_csrf_dependency():
    route = next(
        route
        for route in router.routes
        if route.path == "/test-plans" and "PUT" in route.methods
    )
    assert require_csrf in {
        dependency.call for dependency in route.dependant.dependencies
    }
