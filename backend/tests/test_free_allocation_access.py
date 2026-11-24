"""The Allocation page is a Free feature, so its sector breakdown must be too.

Before this fix `/analytics/sector-breakdown` required `portfolio_analytics`
(Investor and up). Every Free account therefore got a 403 on the Allocation
page. The genuinely analytical endpoints (risk metrics, correlation) must stay
paid, and nothing else may be opened up for Free.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app_settings import set_workspace_setting
from database import get_db
from edition import Edition
from entitlements import (
    PRIVATE_TEST_PLAN_SETTING_KEY,
    EntitlementDenied,
    entitlement_denied_handler,
)
from plans import MINIMUM_PLAN, PlanTier
from routers import analytics
from routers.portfolios import require_portfolio
from tenancy import get_request_context


@pytest.fixture
def client(db_session, test_workspace, default_portfolio, request_context):
    """The real analytics router in a cloud-edition app for one workspace."""
    app = FastAPI()
    app.state.portfyl_edition = Edition.CLOUD
    app.add_exception_handler(EntitlementDenied, entitlement_denied_handler)
    app.include_router(analytics.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_request_context] = lambda: request_context
    app.dependency_overrides[require_portfolio] = lambda: default_portfolio
    with TestClient(app) as test_client:
        yield test_client


def _select_plan(db_session, workspace, plan: PlanTier) -> None:
    if plan is not PlanTier.FREE:
        set_workspace_setting(
            db_session, workspace.id, PRIVATE_TEST_PLAN_SETTING_KEY, plan.value
        )
    db_session.commit()


def test_free_workspace_gets_the_sector_breakdown(client, db_session, test_workspace):
    _select_plan(db_session, test_workspace, PlanTier.FREE)

    response = client.get("/api/analytics/sector-breakdown", params={"currency": "USD"})

    assert response.status_code == 200
    body = response.json()
    assert {"sectors", "countries", "asset_types", "currencies", "total_value"} <= set(body)


@pytest.mark.parametrize("path", ["/api/analytics/risk-metrics", "/api/analytics/correlation"])
def test_free_workspace_still_cannot_use_paid_analytics(
    client, db_session, test_workspace, path
):
    _select_plan(db_session, test_workspace, PlanTier.FREE)

    response = client.get(path)

    assert response.status_code == 403
    body = response.json()
    assert body["code"] == "plan_upgrade_required"
    assert body["capability"] == "portfolio_analytics"
    assert body["required_plan"] == "investor"


@pytest.mark.parametrize("plan", [PlanTier.INVESTOR, PlanTier.PRO])
def test_paid_workspaces_are_unchanged(client, db_session, test_workspace, plan):
    _select_plan(db_session, test_workspace, plan)

    assert client.get("/api/analytics/sector-breakdown").status_code == 200
    assert client.get("/api/analytics/correlation").status_code == 200


def test_sector_breakdown_reuses_the_free_allocation_capability():
    """No new capability: the endpoint is gated by the existing Free `allocation`."""
    route = next(
        r for r in analytics.router.routes if getattr(r, "path", "") == "/analytics/sector-breakdown"
    )
    gates = [
        dep.call.__closure__[0].cell_contents
        for dep in route.dependant.dependencies
        if getattr(dep.call, "__qualname__", "").startswith("require_capability")
    ]
    assert gates == ["allocation"]
    assert MINIMUM_PLAN["allocation"] is PlanTier.FREE
