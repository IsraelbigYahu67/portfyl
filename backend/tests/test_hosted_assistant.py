from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import get_db
from edition import Edition
from entitlements import EntitlementDenied, entitlement_denied_handler
from models import Subscription, TrialGrant, UsageCounter, UsageReservation
from routers import assistant
from routers.portfolios import require_portfolio
from tenancy import get_request_context, require_csrf


def _client(db_session, request_context, portfolio, *, raise_server_exceptions=True):
    app = FastAPI()
    app.state.portfyl_edition = Edition.CLOUD
    app.add_exception_handler(EntitlementDenied, entitlement_denied_handler)
    app.include_router(assistant.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_request_context] = lambda: request_context
    app.dependency_overrides[require_csrf] = lambda: request_context
    app.dependency_overrides[require_portfolio] = lambda: portfolio
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def _activate_trial(db_session, request_context, now):
    db_session.add(TrialGrant(
        workspace_id=request_context.workspace.id,
        activated_by_user_id=request_context.user.id,
        identity_fingerprint="f" * 64,
        activation_kind="csv_import",
        started_at=now,
        ends_at=now + timedelta(days=7),
    ))
    db_session.commit()


def test_trial_hosted_ai_is_charged_once_and_replay_does_not_call_provider(
    db_session, request_context, default_portfolio, monkeypatch
):
    now = datetime.now(timezone.utc)
    _activate_trial(db_session, request_context, now)
    monkeypatch.setenv("PORTFYL_HOSTED_DEEPSEEK_API_KEY", "hosted-test-key")
    provider = AsyncMock(return_value=("answer", {"total_tokens": 4}))
    with (
        patch("routers.assistant._build_portfolio_context", return_value={}),
        patch("routers.assistant._call_deepseek", provider),
        _client(db_session, request_context, default_portfolio) as client,
    ):
        payload = {"messages": [{"role": "user", "content": "Review this portfolio"}]}
        first = client.post(
            "/api/assistant/chat", json=payload, headers={"Idempotency-Key": "ai-request-1"}
        )
        replay = client.post(
            "/api/assistant/chat", json=payload, headers={"Idempotency-Key": "ai-request-1"}
        )
    assert first.status_code == 200
    assert replay.status_code == 409
    assert replay.json()["detail"]["code"] == "idempotency_key_already_used"
    assert provider.await_count == 1
    assert db_session.query(UsageCounter).one().used == 1
    assert db_session.query(UsageReservation).one().status == "finalized"


def test_validation_failure_never_reserves_hosted_usage(
    db_session, request_context, default_portfolio, monkeypatch
):
    _activate_trial(db_session, request_context, datetime.now(timezone.utc))
    monkeypatch.setenv("PORTFYL_HOSTED_DEEPSEEK_API_KEY", "hosted-test-key")
    with _client(db_session, request_context, default_portfolio) as client:
        response = client.post(
            "/api/assistant/chat",
            json={"messages": [{"role": "assistant", "content": "not a user turn"}]},
            headers={"Idempotency-Key": "invalid-request"},
        )
    assert response.status_code == 400
    assert db_session.query(UsageCounter).count() == 0
    assert db_session.query(UsageReservation).count() == 0


def test_provider_failure_releases_hosted_usage(
    db_session, request_context, default_portfolio, monkeypatch
):
    _activate_trial(db_session, request_context, datetime.now(timezone.utc))
    monkeypatch.setenv("PORTFYL_HOSTED_DEEPSEEK_API_KEY", "hosted-test-key")
    with (
        patch("routers.assistant._build_portfolio_context", return_value={}),
        patch("routers.assistant._call_deepseek", AsyncMock(side_effect=RuntimeError("down"))),
        _client(
            db_session,
            request_context,
            default_portfolio,
            raise_server_exceptions=False,
        ) as client,
    ):
        response = client.post(
            "/api/assistant/chat",
            json={"messages": [{"role": "user", "content": "hello"}]},
            headers={"Idempotency-Key": "failed-request"},
        )
    assert response.status_code == 500
    assert db_session.query(UsageCounter).one().used == 0
    assert db_session.query(UsageReservation).one().status == "released"


def test_investor_without_byok_cannot_fall_through_to_hosted_ai(
    db_session, request_context, default_portfolio, monkeypatch
):
    now = datetime.now(timezone.utc)
    db_session.add(Subscription(
        workspace_id=request_context.workspace.id,
        stripe_subscription_id="sub_investor_byok",
        stripe_price_id="price_investor_v1",
        plan="investor",
        billing_interval="month",
        price_version="v1",
        status="active",
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    ))
    db_session.commit()
    monkeypatch.setenv("PORTFYL_HOSTED_DEEPSEEK_API_KEY", "hosted-test-key")
    with (
        patch("routers.assistant._build_portfolio_context", return_value={}),
        _client(db_session, request_context, default_portfolio) as client,
    ):
        response = client.post(
            "/api/assistant/chat",
            json={"messages": [{"role": "user", "content": "hello"}]},
            headers={"Idempotency-Key": "investor-hosted"},
        )
    assert response.status_code == 403
    assert response.json()["code"] == "plan_upgrade_required"
    assert response.json()["required_plan"] == "pro"
    assert db_session.query(UsageCounter).count() == 0
