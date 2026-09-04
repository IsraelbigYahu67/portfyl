from __future__ import annotations

from datetime import datetime, timezone
from types import MappingProxyType

import pytest

from billing_config import BillingConfig, BillingInterval, PlanTier
from billing_reconciliation import process_stripe_event, project_subscription, subscription_id_from_event
from models import BillingCustomer, StripeEvent


def _config():
    return BillingConfig(
        enabled=True,
        secret_key="sk_test_key",
        webhook_secret="whsec_key",
        trial_identity_key="trial-key",
        app_url="https://portfyl.test",
        current_price_version="v1",
        stripe_prices=MappingProxyType({
            (PlanTier.INVESTOR, BillingInterval.MONTH, "v1"): "price_investor_month",
            (PlanTier.PRO, BillingInterval.YEAR, "v1"): "price_pro_year",
        }),
    )


def _remote(status="active", price="price_investor_month"):
    return {
        "id": "sub_123",
        "customer": "cus_123",
        "status": status,
        "items": {"data": [{"price": {"id": price}}]},
        "current_period_start": 1788516000,
        "current_period_end": 1791108000,
        "cancel_at_period_end": False,
    }


def test_extracts_subscription_from_old_and_new_invoice_shapes():
    assert subscription_id_from_event({
        "type": "invoice.paid", "data": {"object": {"subscription": "sub_old"}}
    }) == "sub_old"
    assert subscription_id_from_event({
        "type": "invoice.paid",
        "data": {"object": {"parent": {"subscription_details": {"subscription": "sub_new"}}}},
    }) == "sub_new"


def test_projection_pins_price_generation_and_recovers_payment(db_session, test_workspace):
    db_session.add(BillingCustomer(workspace_id=test_workspace.id, stripe_customer_id="cus_123"))
    first = project_subscription(
        db_session,
        workspace_id=test_workspace.id,
        remote=_remote(status="past_due"),
        config=_config(),
        event_type="invoice.payment_failed",
        now=datetime(2026, 9, 4, tzinfo=timezone.utc),
    )
    assert first.price_version == "v1" and first.grace_ends_at is not None
    recovered = project_subscription(
        db_session,
        workspace_id=test_workspace.id,
        remote=_remote(status="active"),
        config=_config(),
        event_type="invoice.paid",
    )
    assert recovered.id == first.id
    assert recovered.grace_ends_at is None and recovered.payment_failed_at is None


def test_unknown_price_fails_closed(db_session, test_workspace):
    with pytest.raises(ValueError, match="unknown Price"):
        project_subscription(
            db_session,
            workspace_id=test_workspace.id,
            remote=_remote(price="price_attacker"),
            config=_config(),
        )


class CanonicalGateway:
    def __init__(self, remote):
        self.remote = remote

    def retrieve_subscription(self, _subscription_id):
        return self.remote


def test_reversed_failure_event_uses_current_recovered_subscription(
    db_session, test_workspace
):
    db_session.add(BillingCustomer(
        workspace_id=test_workspace.id,
        stripe_customer_id="cus_123",
    ))
    event = StripeEvent(
        stripe_event_id="evt_old_failure",
        event_type="invoice.payment_failed",
        object_id="sub_123",
        livemode=False,
    )
    db_session.add(event)
    db_session.flush()
    subscription = process_stripe_event(
        db_session,
        event_row=event,
        gateway=CanonicalGateway(_remote(status="active")),
        config=_config(),
        workspace_id=test_workspace.id,
    )
    assert event.status == "processed"
    assert subscription.status == "active"
    assert subscription.payment_failed_at is None
    assert subscription.grace_ends_at is None


def test_worker_quarantines_unknown_price_without_granting_access(
    db_session, test_workspace
):
    db_session.add(BillingCustomer(
        workspace_id=test_workspace.id,
        stripe_customer_id="cus_123",
    ))
    event = StripeEvent(
        stripe_event_id="evt_unknown_price",
        event_type="customer.subscription.updated",
        object_id="sub_123",
        livemode=False,
    )
    db_session.add(event)
    db_session.flush()
    result = process_stripe_event(
        db_session,
        event_row=event,
        gateway=CanonicalGateway(_remote(price="price_attacker")),
        config=_config(),
        workspace_id=test_workspace.id,
    )
    assert result is None
    assert event.status == "quarantined"
    assert "unknown Price" in event.last_error
