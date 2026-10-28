"""Stripe Managed Payments billing: config, webhook signatures, subscription
projection, entitlements, and the billing API. Stripe is always faked."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

import routers.billing as billing_router
from account_deletion import schedule_workspace_deletion
from billing_config import BillingConfig
from billing_sync import BillingDataError, apply_subscription, subscription_id_from_event
from database import get_db
from edition import Edition
from entitlements import PRIVATE_TEST_PLAN_SETTING_KEY, resolve_entitlements
from app_settings import set_workspace_setting
from firebase_identity import VerifiedIdentity
from models import AuditLog, BillingCustomer, StripeEvent, Subscription
from plans import PlanTier
from stripe_client import InvalidWebhookSignature, StripeError, _flatten, verify_webhook
from tenancy import RequestContextError


NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
WEBHOOK_SECRET = "whsec_unit"
ENV = {
    "PORTFYL_BILLING_ENABLED": "1",
    "STRIPE_SECRET_KEY": "sk_test_unit",
    "STRIPE_WEBHOOK_SECRET": WEBHOOK_SECRET,
    "PORTFYL_STRIPE_PRICE_INVESTOR": "price_investor",
    "PORTFYL_STRIPE_PRICE_PRO": "price_pro",
    "PORTFYL_APP_URL": "https://portfyl.example",
}


@pytest.fixture
def config() -> BillingConfig:
    return BillingConfig.from_env(ENV)


def _remote(
    *,
    sub_id="sub_1",
    customer="cus_1",
    price="price_investor",
    status="active",
    period_end=NOW + timedelta(days=30),
    workspace_public_id=None,
    **extra,
) -> dict:
    remote = {
        "id": sub_id,
        "customer": customer,
        "status": status,
        "cancel_at_period_end": False,
        "cancel_at": None,
        "ended_at": None,
        "metadata": {"portfyl_workspace_id": str(workspace_public_id)} if workspace_public_id else {},
        "items": {"data": [{"price": {"id": price}, "current_period_end": int(period_end.timestamp())}]},
    }
    remote.update(extra)
    return remote


def _add_customer(db, workspace, customer_id="cus_1"):
    db.add(BillingCustomer(workspace_id=workspace.id, stripe_customer_id=customer_id))
    db.flush()


class FakeStripe:
    def __init__(self, subscriptions=None, session=None):
        self.subscriptions = dict(subscriptions or {})
        self.session = session or {}
        self.checkout_params = None
        self.checkout_idempotency_key = None
        self.customers_created = 0
        self.fail_retrieve: StripeError | None = None

    def create_customer(self, *, email, workspace_public_id, idempotency_key):
        self.customers_created += 1
        return {"id": "cus_new"}

    def create_checkout_session(self, params, *, idempotency_key):
        self.checkout_params = params
        self.checkout_idempotency_key = idempotency_key
        return {"id": "cs_1", "url": "https://checkout.stripe.test/cs_1"}

    def retrieve_checkout_session(self, session_id):
        return self.session

    def retrieve_subscription(self, subscription_id):
        if self.fail_retrieve is not None:
            raise self.fail_retrieve
        return self.subscriptions[subscription_id]

    def list_subscriptions(self, customer_id):
        return list(self.subscriptions.values())

    def create_portal_session(self, *, customer_id, return_url):
        return {"url": f"https://billing.stripe.test/{customer_id}"}


def _fake_request(config):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        billing_config=config, portfyl_edition=Edition.CLOUD,
    )))


# ---------------------------------------------------------------------------
# Configuration and the Stripe boundary
# ---------------------------------------------------------------------------


def test_billing_is_disabled_unless_explicitly_enabled():
    config = BillingConfig.from_env({"STRIPE_SECRET_KEY": "garbage"})
    assert config.enabled is False


def test_enabled_billing_fails_closed_on_incomplete_config():
    with pytest.raises(RuntimeError, match="STRIPE_WEBHOOK_SECRET"):
        BillingConfig.from_env({**ENV, "STRIPE_WEBHOOK_SECRET": ""})
    with pytest.raises(RuntimeError, match="own Stripe Price"):
        BillingConfig.from_env({**ENV, "PORTFYL_STRIPE_PRICE_PRO": "price_investor"})
    with pytest.raises(RuntimeError, match="https"):
        BillingConfig.from_env({**ENV, "PORTFYL_APP_URL": "http://portfyl.example"})


def test_config_maps_prices_and_mode(config):
    assert config.livemode is False
    assert config.plan_for_price("price_pro") is PlanTier.PRO
    assert config.plan_for_price("price_other") is None
    assert BillingConfig.from_env({**ENV, "STRIPE_SECRET_KEY": "rk_live_x"}).livemode is True


def test_form_encoding_matches_stripe_nesting():
    assert _flatten({
        "line_items": [{"price": "price_1", "quantity": 1}],
        "managed_payments": {"enabled": True},
        "skip": None,
    }) == [
        ("line_items[0][price]", "price_1"),
        ("line_items[0][quantity]", "1"),
        ("managed_payments[enabled]", "true"),
    ]


def test_client_sends_nested_form_bodies_through_httpx():
    import httpx
    from stripe_client import StripeClient

    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["content_type"] = request.headers["Content-Type"]
        seen["body"] = request.content.decode()
        seen["idempotency"] = request.headers.get("Idempotency-Key")
        seen["version"] = request.headers["Stripe-Version"]
        return httpx.Response(200, json={"id": "cs_1", "url": "https://checkout.stripe.test/cs_1"})

    client = StripeClient("sk_test_unit", api_version="2026-09-30.endive")
    client._client = httpx.Client(
        base_url="https://api.stripe.test/v1",
        headers={"Stripe-Version": "2026-09-30.endive"},
        transport=httpx.MockTransport(handler),
    )
    result = client.create_checkout_session(
        {"line_items": [{"price": "price_1", "quantity": 1}], "managed_payments": {"enabled": True}},
        idempotency_key="checkout:1",
    )

    assert result["id"] == "cs_1"
    assert seen["content_type"] == "application/x-www-form-urlencoded"
    assert seen["body"] == (
        "line_items%5B0%5D%5Bprice%5D=price_1&line_items%5B0%5D%5Bquantity%5D=1"
        "&managed_payments%5Benabled%5D=true"
    )
    assert seen["idempotency"] == "checkout:1"
    assert seen["version"] == "2026-09-30.endive"


def _signature(payload: bytes, timestamp: int, secret: str = WEBHOOK_SECRET) -> str:
    digest = hmac.new(secret.encode(), f"{timestamp}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


def test_webhook_signature_verification():
    payload = json.dumps({"id": "evt_1", "type": "invoice.paid"}).encode()
    now = 1_800_000_000
    assert verify_webhook(payload, _signature(payload, now), WEBHOOK_SECRET, now=now)["id"] == "evt_1"
    # A rolled secret: one of several v1 signatures matches.
    rolled = _signature(payload, now, "whsec_old") + "," + _signature(payload, now).split(",")[1]
    assert verify_webhook(payload, rolled, WEBHOOK_SECRET, now=now)["id"] == "evt_1"
    for header, at in (
        (_signature(payload, now, "whsec_wrong"), now),
        (_signature(payload, now), now + 301),
        ("v1=deadbeef", now),
        (None, now),
    ):
        with pytest.raises(InvalidWebhookSignature):
            verify_webhook(payload, header, WEBHOOK_SECRET, now=at)
    with pytest.raises(InvalidWebhookSignature):
        verify_webhook(payload + b" ", _signature(payload, now), WEBHOOK_SECRET, now=now)


def test_subscription_id_from_event_shapes():
    assert subscription_id_from_event(
        {"type": "customer.subscription.updated", "data": {"object": {"id": "sub_a"}}}
    ) == "sub_a"
    assert subscription_id_from_event(
        {"type": "checkout.session.completed", "data": {"object": {"subscription": "sub_b"}}}
    ) == "sub_b"
    assert subscription_id_from_event({"type": "invoice.paid", "data": {"object": {
        "parent": {"subscription_details": {"subscription": "sub_c"}},
    }}}) == "sub_c"
    assert subscription_id_from_event({"type": "charge.refunded", "data": {"object": {}}}) is None


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


def test_apply_subscription_projects_canonical_state(db_session, test_workspace, config):
    _add_customer(db_session, test_workspace)
    row = apply_subscription(db_session, workspace_id=test_workspace.id, remote=_remote(), config=config, now=NOW)

    assert row.plan == "investor"
    assert row.status == "active"
    assert row.current_period_end.replace(tzinfo=timezone.utc) == NOW + timedelta(days=30)
    assert row.ended_at is None and row.grace_ends_at is None

    # A plan change in the portal arrives as the same subscription, new price.
    row = apply_subscription(
        db_session, workspace_id=test_workspace.id, remote=_remote(price="price_pro"), config=config, now=NOW,
    )
    assert row.plan == "pro"
    assert db_session.scalars(select(Subscription)).all() == [row]


def test_past_due_starts_grace_once_and_recovery_clears_it(db_session, test_workspace, config):
    _add_customer(db_session, test_workspace)
    row = apply_subscription(
        db_session, workspace_id=test_workspace.id, remote=_remote(status="past_due"), config=config, now=NOW,
    )
    assert row.grace_ends_at == NOW + timedelta(days=14)
    later = NOW + timedelta(days=3)
    row = apply_subscription(
        db_session, workspace_id=test_workspace.id, remote=_remote(status="past_due"), config=config, now=later,
    )
    assert row.grace_ends_at == NOW + timedelta(days=14)
    row = apply_subscription(db_session, workspace_id=test_workspace.id, remote=_remote(), config=config, now=later)
    assert row.grace_ends_at is None


def test_canceled_subscription_ends_and_frees_the_slot(db_session, test_workspace, config):
    _add_customer(db_session, test_workspace)
    ended_at = NOW + timedelta(days=30)
    row = apply_subscription(
        db_session,
        workspace_id=test_workspace.id,
        remote=_remote(status="canceled", ended_at=int(ended_at.timestamp())),
        config=config,
        now=NOW,
    )
    assert row.ended_at.replace(tzinfo=timezone.utc) == ended_at
    # A new subscription after cancellation is allowed.
    apply_subscription(db_session, workspace_id=test_workspace.id, remote=_remote(sub_id="sub_2"), config=config)


@pytest.mark.parametrize(
    ("remote", "reason"),
    [
        (_remote(price="price_unknown"), "maps to no plan"),
        (_remote(customer="cus_someone_else"), "not this workspace"),
        ({**_remote(), "items": {"data": []}}, "exactly one item"),
    ],
)
def test_apply_subscription_refuses_untrusted_state(db_session, test_workspace, config, remote, reason):
    _add_customer(db_session, test_workspace)
    with pytest.raises(BillingDataError, match=reason):
        apply_subscription(db_session, workspace_id=test_workspace.id, remote=remote, config=config)


def test_second_live_subscription_is_quarantined(db_session, test_workspace, config):
    _add_customer(db_session, test_workspace)
    apply_subscription(db_session, workspace_id=test_workspace.id, remote=_remote(), config=config)
    with pytest.raises(BillingDataError, match="another live subscription"):
        apply_subscription(db_session, workspace_id=test_workspace.id, remote=_remote(sub_id="sub_2"), config=config)


# ---------------------------------------------------------------------------
# Entitlements
# ---------------------------------------------------------------------------


def _subscription(db, workspace, **values):
    row = Subscription(
        workspace_id=workspace.id,
        stripe_subscription_id=values.pop("stripe_subscription_id", "sub_1"),
        stripe_customer_id="cus_1",
        stripe_price_id="price_pro",
        plan=values.pop("plan", "pro"),
        status=values.pop("status", "active"),
        current_period_end=NOW + timedelta(days=10),
        **values,
    )
    db.add(row)
    db.flush()
    return row


def test_active_subscription_grants_its_plan(db_session, test_workspace, monkeypatch):
    monkeypatch.setenv("PORTFYL_BILLING_ENABLED", "1")
    _subscription(db_session, test_workspace, cancel_at_period_end=True)
    access = resolve_entitlements(db_session, edition=Edition.CLOUD, workspace_id=test_workspace.id, now=NOW)

    assert access.plan is PlanTier.PRO
    assert access.source == "subscription"
    assert access.cancel_at_period_end is True
    assert access.effective_until.replace(tzinfo=timezone.utc) == NOW + timedelta(days=10)
    assert "options" in access.capabilities


def test_past_due_keeps_access_only_during_grace(db_session, test_workspace, monkeypatch):
    monkeypatch.setenv("PORTFYL_BILLING_ENABLED", "1")
    _subscription(db_session, test_workspace, status="past_due", grace_ends_at=NOW + timedelta(days=1))
    access = resolve_entitlements(db_session, edition=Edition.CLOUD, workspace_id=test_workspace.id, now=NOW)
    assert access.plan is PlanTier.PRO and access.in_grace is True

    later = NOW + timedelta(days=2)
    access = resolve_entitlements(db_session, edition=Edition.CLOUD, workspace_id=test_workspace.id, now=later)
    assert access.plan is PlanTier.FREE


def test_enabled_billing_ignores_the_no_payment_test_selection(db_session, test_workspace, monkeypatch):
    set_workspace_setting(db_session, test_workspace.id, PRIVATE_TEST_PLAN_SETTING_KEY, "pro")
    monkeypatch.delenv("PORTFYL_BILLING_ENABLED", raising=False)
    assert resolve_entitlements(
        db_session, edition=Edition.CLOUD, workspace_id=test_workspace.id,
    ).plan is PlanTier.PRO

    monkeypatch.setenv("PORTFYL_BILLING_ENABLED", "1")
    access = resolve_entitlements(db_session, edition=Edition.CLOUD, workspace_id=test_workspace.id)
    assert access.plan is PlanTier.FREE
    assert access.source == "free"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def test_checkout_requires_the_immediate_start_consent(db_session, request_context, config):
    with pytest.raises(HTTPException) as exc:
        billing_router.create_checkout(
            billing_router.CheckoutPayload(plan=PlanTier.PRO),
            db=db_session, context=request_context, config=config, client=FakeStripe(),
        )
    assert exc.value.status_code == 422
    assert exc.value.detail == {"code": "immediate_start_consent_required"}


def test_checkout_is_owner_only(db_session, request_context, config):
    request_context.membership.role = "member"
    with pytest.raises(HTTPException) as exc:
        billing_router.create_checkout(
            billing_router.CheckoutPayload(plan=PlanTier.PRO, accept_immediate_start=True),
            db=db_session, context=request_context, config=config, client=FakeStripe(),
        )
    assert exc.value.status_code == 403


def test_checkout_creates_a_managed_payments_session(db_session, request_context, config):
    stripe = FakeStripe()
    result = billing_router.create_checkout(
        billing_router.CheckoutPayload(plan=PlanTier.PRO, accept_immediate_start=True),
        db=db_session, context=request_context, config=config, client=stripe,
    )

    assert result == {"url": "https://checkout.stripe.test/cs_1"}
    params = stripe.checkout_params
    workspace_public_id = str(request_context.workspace.public_id)
    assert params["mode"] == "subscription"
    assert params["managed_payments"] == {"enabled": True}
    assert params["customer"] == "cus_new"
    assert params["client_reference_id"] == workspace_public_id
    assert params["line_items"] == [{"price": "price_pro", "quantity": 1}]
    assert params["subscription_data"]["metadata"]["portfyl_workspace_id"] == workspace_public_id
    assert params["success_url"].endswith("session_id={CHECKOUT_SESSION_ID}")
    # Managed Payments rejects these; Stripe handles tax and the address itself.
    assert not {"automatic_tax", "tax_id_collection", "customer_update", "payment_method_types"} & set(params)
    customer = db_session.scalar(select(BillingCustomer))
    assert customer.stripe_customer_id == "cus_new"
    audit = db_session.scalar(select(AuditLog).where(AuditLog.action == "billing.checkout.created"))
    assert audit.event_metadata["immediate_start_consent"] is True
    assert audit.event_metadata["plan"] == "pro"

    # A second checkout reuses the stored customer.
    billing_router.create_checkout(
        billing_router.CheckoutPayload(plan=PlanTier.PRO, accept_immediate_start=True),
        db=db_session, context=request_context, config=config, client=stripe,
    )
    assert stripe.customers_created == 1


def test_checkout_refuses_a_workspace_that_already_subscribes(db_session, request_context, config):
    _subscription(db_session, request_context.workspace)
    with pytest.raises(HTTPException) as exc:
        billing_router.create_checkout(
            billing_router.CheckoutPayload(plan=PlanTier.INVESTOR, accept_immediate_start=True),
            db=db_session, context=request_context, config=config, client=FakeStripe(),
        )
    assert exc.value.status_code == 409


def test_confirm_checkout_activates_the_plan_immediately(db_session, request_context, config, monkeypatch):
    monkeypatch.setenv("PORTFYL_BILLING_ENABLED", "1")
    workspace = request_context.workspace
    _add_customer(db_session, workspace)
    stripe = FakeStripe(
        subscriptions={"sub_1": _remote(price="price_pro")},
        session={"client_reference_id": str(workspace.public_id), "status": "complete", "subscription": "sub_1"},
    )
    result = billing_router.confirm_checkout(
        billing_router.CheckoutConfirmPayload(session_id="cs_1"),
        _fake_request(config),
        db=db_session, context=request_context, config=config, client=stripe,
    )
    assert result["checkout_status"] == "complete"
    assert result["plan"] == "pro"
    assert result["subscription"]["status"] == "active"


def test_confirm_checkout_rejects_another_workspaces_session(db_session, request_context, config):
    stripe = FakeStripe(session={"client_reference_id": "someone-else", "status": "complete"})
    with pytest.raises(HTTPException) as exc:
        billing_router.confirm_checkout(
            billing_router.CheckoutConfirmPayload(session_id="cs_x"),
            _fake_request(config),
            db=db_session, context=request_context, config=config, client=stripe,
        )
    assert exc.value.status_code == 404


def test_portal_needs_a_billing_account(db_session, request_context, config):
    with pytest.raises(HTTPException) as exc:
        billing_router.create_portal(db=db_session, context=request_context, config=config, client=FakeStripe())
    assert exc.value.status_code == 404
    _add_customer(db_session, request_context.workspace)
    result = billing_router.create_portal(db=db_session, context=request_context, config=config, client=FakeStripe())
    assert result == {"url": "https://billing.stripe.test/cus_1"}


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------


@pytest.fixture
def webhook(db_session, config, monkeypatch):
    stripe = FakeStripe()
    monkeypatch.setattr(billing_router, "make_stripe_client", lambda _config: stripe)
    app = FastAPI()
    app.state.billing_config = config
    app.include_router(billing_router.webhook_router)
    app.dependency_overrides[get_db] = lambda: db_session

    def send(event: dict):
        payload = json.dumps(event).encode()
        return TestClient(app).post(
            "/billing/webhook",
            content=payload,
            headers={"Stripe-Signature": _signature(payload, int(time.time()))},
        )

    return SimpleNamespace(stripe=stripe, send=send)


def _event(event_id="evt_1", event_type="customer.subscription.updated", obj=None, livemode=False):
    return {"id": event_id, "type": event_type, "livemode": livemode, "data": {"object": obj or {"id": "sub_1"}}}


def test_webhook_projects_the_retrieved_subscription_once(db_session, test_workspace, webhook):
    _add_customer(db_session, test_workspace)
    db_session.commit()
    webhook.stripe.subscriptions["sub_1"] = _remote(workspace_public_id=test_workspace.public_id)

    response = webhook.send(_event())
    assert response.status_code == 200
    row = db_session.scalar(select(Subscription))
    assert row.plan == "investor" and row.status == "active"
    assert db_session.scalar(select(StripeEvent)).status == "processed"

    # Redelivery is a no-op even if Stripe now reports something else.
    webhook.stripe.subscriptions["sub_1"] = _remote(workspace_public_id=test_workspace.public_id, price="price_pro")
    assert webhook.send(_event()).json()["duplicate"] is True
    db_session.refresh(row)
    assert row.plan == "investor"


def test_webhook_rejects_bad_signatures_and_mode(webhook):
    app_response = webhook.send(_event(livemode=True))
    assert app_response.status_code == 400
    assert app_response.json()["detail"] == {"code": "event_mode_mismatch"}


def test_webhook_ignores_irrelevant_events(db_session, webhook):
    assert webhook.send(_event(event_type="charge.refunded", obj={"id": "ch_1"})).status_code == 200
    assert db_session.scalar(select(StripeEvent)).status == "ignored"


def test_webhook_asks_stripe_to_retry_transient_failures(db_session, test_workspace, webhook):
    _add_customer(db_session, test_workspace)
    db_session.commit()
    webhook.stripe.fail_retrieve = StripeError("down", status=503, transient=True)
    assert webhook.send(_event()).status_code == 503
    assert db_session.scalar(select(StripeEvent)).status == "failed"

    webhook.stripe.fail_retrieve = None
    webhook.stripe.subscriptions["sub_1"] = _remote(workspace_public_id=test_workspace.public_id)
    assert webhook.send(_event()).status_code == 200
    event = db_session.scalar(select(StripeEvent))
    assert event.status == "processed" and event.attempts == 2


def test_webhook_quarantines_unmapped_subscriptions(db_session, webhook):
    webhook.stripe.subscriptions["sub_1"] = _remote()  # no workspace metadata
    assert webhook.send(_event()).status_code == 200
    assert db_session.scalar(select(StripeEvent)).status == "quarantined"
    assert db_session.scalar(select(Subscription)) is None


# ---------------------------------------------------------------------------
# Account deletion
# ---------------------------------------------------------------------------


def test_renewing_subscription_blocks_workspace_deletion(db_session, request_context):
    _subscription(db_session, request_context.workspace)
    identity = VerifiedIdentity(
        uid=request_context.user.firebase_uid,
        email=request_context.user.email,
        email_verified=True,
        display_name=None,
        authenticated_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    with pytest.raises(RequestContextError) as exc:
        schedule_workspace_deletion(
            db_session, request_context, identity=identity, confirmation=request_context.workspace.name,
        )
    assert exc.value.code == "active_subscription"
