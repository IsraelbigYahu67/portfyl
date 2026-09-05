from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import get_db
from edition import Edition
from entitlements import EntitlementDenied, entitlement_denied_handler
from models import UsageCounter, UsageReservation
from routers import assistant
from routers.portfolios import require_portfolio
from tenancy import get_request_context, require_csrf


def test_free_cloud_workspace_cannot_call_hosted_assistant(
    db_session, request_context, default_portfolio, monkeypatch
):
    app = FastAPI()
    app.state.portfyl_edition = Edition.CLOUD
    app.add_exception_handler(EntitlementDenied, entitlement_denied_handler)
    app.include_router(assistant.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_request_context] = lambda: request_context
    app.dependency_overrides[require_csrf] = lambda: request_context
    app.dependency_overrides[require_portfolio] = lambda: default_portfolio
    provider = AsyncMock(return_value=("answer", {"total_tokens": 4}))
    monkeypatch.setenv("PORTFYL_HOSTED_DEEPSEEK_API_KEY", "hosted-test-key")

    with patch("routers.assistant._call_deepseek", provider), TestClient(app) as client:
        response = client.post(
            "/api/assistant/chat",
            json={"messages": [{"role": "user", "content": "Review this portfolio"}]},
            headers={"Idempotency-Key": "ai-request-1"},
        )

    assert response.status_code == 403
    assert response.json()["code"] == "plan_upgrade_required"
    assert response.json()["required_plan"] == "investor"
    provider.assert_not_awaited()
    assert db_session.query(UsageCounter).count() == 0
    assert db_session.query(UsageReservation).count() == 0
