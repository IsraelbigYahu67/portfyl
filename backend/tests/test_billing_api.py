from __future__ import annotations

import json
from types import MappingProxyType

from fastapi import FastAPI
from fastapi.testclient import TestClient

from billing_config import BillingConfig, BillingInterval, PlanTier
from database import get_db
from edition import Edition
from models import AuditLog, BillingAction, BillingCustomer, StripeEvent, Subscription
from routers import billing
from tenancy import get_request_context, require_csrf


class FakeStripe:
    def __init__(self):
        self.checkout_calls = 0
        self.constructed_payload = None
        self.event = {
            "id": "evt_1",
            "type": "customer.subscription.updated",
            "livemode": False,
            "data": {"object": {"id": "sub_1"}},
        }

    def construct_event(self, payload, signature, secret):
        self.constructed_payload = payload
        if signature != "valid":
            raise ValueError("bad signature")
        return self.event

    def create_customer(self, **kwargs):
        return {"id": "cus_1"}

    def create_checkout(self, **kwargs):
        self.checkout_calls += 1
        return {"id": "cs_1", "url": "https://checkout.stripe.test/session"}

    def retrieve_checkout(self, session_id):
        return {"id": session_id, "url": "https://checkout.stripe.test/session"}

    def create_portal(self, **kwargs):
        return {"url": "https://billing.stripe.test/portal"}


def _config():
    return BillingConfig(
        enabled=True,
        secret_key="sk_test_key",
        webhook_secret="whsec_key",
        trial_identity_key="trial-key",
        app_url="https://portfyl.test",
        current_price_version="v1",
        stripe_prices=MappingProxyType({
            (PlanTier.INVESTOR, BillingInterval.MONTH, "v1"): "price_im",
            (PlanTier.INVESTOR, BillingInterval.YEAR, "v1"): "price_iy",
            (PlanTier.PRO, BillingInterval.MONTH, "v1"): "price_pm",
            (PlanTier.PRO, BillingInterval.YEAR, "v1"): "price_py",
        }),
    )


def _client(db_session, request_context, gateway):
    db_session.expire_on_commit = False
    app = FastAPI()
    app.state.portfyl_edition = Edition.CLOUD
    app.state.billing_config = _config()
    app.include_router(billing.router, prefix="/api")
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_request_context] = lambda: request_context
    app.dependency_overrides[require_csrf] = lambda: request_context
    app.dependency_overrides[billing.get_billing_gateway] = lambda: gateway
    return TestClient(app)


def test_checkout_is_backend_catalogued_and_idempotent(db_session, request_context):
    gateway = FakeStripe()
    headers = {"Idempotency-Key": "attempt-1"}
    payload = {"plan": "pro", "interval": "year"}
    with _client(db_session, request_context, gateway) as client:
        first = client.post("/api/billing/checkout", json=payload, headers=headers)
        second = client.post("/api/billing/checkout", json=payload, headers=headers)
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["pending"] is True
    assert gateway.checkout_calls == 1
    assert db_session.query(BillingCustomer).count() == 1
    assert db_session.query(BillingAction).count() == 1


def test_checkout_rejects_idempotency_key_payload_reuse(db_session, request_context):
    gateway = FakeStripe()
    headers = {"Idempotency-Key": "attempt-1"}
    with _client(db_session, request_context, gateway) as client:
        assert client.post("/api/billing/checkout", json={"plan": "pro", "interval": "year"}, headers=headers).status_code == 200
        assert client.post("/api/billing/checkout", json={"plan": "investor", "interval": "year"}, headers=headers).status_code == 409


def test_checkout_rejects_second_pending_or_live_subscription(db_session, request_context):
    gateway = FakeStripe()
    with _client(db_session, request_context, gateway) as client:
        first = client.post(
            "/api/billing/checkout",
            json={"plan": "pro", "interval": "month"},
            headers={"Idempotency-Key": "first"},
        )
        pending = client.post(
            "/api/billing/checkout",
            json={"plan": "investor", "interval": "month"},
            headers={"Idempotency-Key": "second"},
        )
    assert first.status_code == 200
    assert pending.status_code == 409
    assert pending.json()["detail"]["code"] == "checkout_pending"

    action = db_session.query(BillingAction).one()
    action.response_url_expires_at = None
    db_session.add(Subscription(
        workspace_id=request_context.workspace.id,
        stripe_subscription_id="sub_live",
        stripe_price_id="price_pm",
        plan="pro",
        billing_interval="month",
        price_version="v1",
        status="active",
    ))
    db_session.commit()
    with _client(db_session, request_context, gateway) as client:
        live = client.post(
            "/api/billing/checkout",
            json={"plan": "investor", "interval": "year"},
            headers={"Idempotency-Key": "third"},
        )
    assert live.status_code == 409
    assert live.json()["detail"]["code"] == "subscription_already_exists"


def test_portal_creation_is_audited(db_session, request_context):
    gateway = FakeStripe()
    db_session.add(BillingCustomer(
        workspace_id=request_context.workspace.id,
        stripe_customer_id="cus_1",
    ))
    db_session.commit()
    with _client(db_session, request_context, gateway) as client:
        response = client.post("/api/billing/portal")
    assert response.status_code == 200
    assert response.json()["url"].startswith("https://billing.stripe.test/")
    assert db_session.query(AuditLog).filter(AuditLog.action == "billing.portal.created").count() == 1


def test_webhook_verifies_and_deduplicates_before_processing(db_session, request_context):
    gateway = FakeStripe()
    with _client(db_session, request_context, gateway) as client:
        assert client.post("/api/billing/webhook", content=b"{}", headers={"Stripe-Signature": "bad"}).status_code == 400
        exact_body = b'{"spacing":  "must survive"}'
        first = client.post("/api/billing/webhook", content=exact_body, headers={"Stripe-Signature": "valid"})
        second = client.post("/api/billing/webhook", content=exact_body, headers={"Stripe-Signature": "valid"})
    assert first.json() == {"received": True, "duplicate": False}
    assert second.json() == {"received": True, "duplicate": True}
    row = db_session.query(StripeEvent).one()
    assert row.object_id == "sub_1" and row.status == "pending"
    assert gateway.constructed_payload == exact_body


def test_webhook_rejects_livemode_mismatch_without_persisting(db_session, request_context):
    gateway = FakeStripe()
    gateway.event = {**gateway.event, "id": "evt_live", "livemode": True}
    with _client(db_session, request_context, gateway) as client:
        response = client.post(
            "/api/billing/webhook", content=b"{}", headers={"Stripe-Signature": "valid"}
        )
    assert response.status_code == 400
    assert db_session.query(StripeEvent).count() == 0
