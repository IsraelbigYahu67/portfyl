"""Stripe billing under the real RLS-forced runtime role: the webhook's
context-free workspace lookup, and tenant isolation of the billing tables."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from billing_config import BillingConfig
from billing_sync import apply_subscription, resolve_workspace_id, scope_to_workspace
from models import BillingCustomer, Subscription


CONFIG = BillingConfig.from_env({
    "PORTFYL_BILLING_ENABLED": "1",
    "STRIPE_SECRET_KEY": "sk_test_rls",
    "STRIPE_WEBHOOK_SECRET": "whsec_rls",
    "PORTFYL_STRIPE_PRICE_INVESTOR": "price_investor",
    "PORTFYL_STRIPE_PRICE_PRO": "price_pro",
    "PORTFYL_APP_URL": "https://portfyl.example",
})


def _remote(customer: str) -> dict:
    period_end = datetime.now(timezone.utc) + timedelta(days=30)
    return {
        "id": f"sub_{customer}",
        "customer": customer,
        "status": "active",
        "cancel_at_period_end": False,
        "items": {"data": [{"price": {"id": "price_pro"}, "current_period_end": int(period_end.timestamp())}]},
    }


def test_webhook_lookup_finds_a_workspace_without_leaking_tenants(matrix_tenants, runtime_session: Session):
    alice = matrix_tenants.alice
    assert resolve_workspace_id(runtime_session, alice.workspace_public_id) == alice.workspace_id
    # The job_context flag is cleared again: an unscoped session sees nothing.
    flag = runtime_session.execute(text("SELECT current_setting('portfyl.job_context', true)")).scalar()
    assert flag in (None, "")
    assert runtime_session.scalars(select(BillingCustomer)).all() == []


def test_billing_rows_are_workspace_isolated(matrix_tenants, runtime_session: Session):
    alice, bob = matrix_tenants.alice, matrix_tenants.bob

    scope_to_workspace(runtime_session, alice.workspace_id)
    alice_customer = runtime_session.scalar(select(BillingCustomer))  # seeded by matrix_tenants
    row = apply_subscription(
        runtime_session,
        workspace_id=alice.workspace_id,
        remote=_remote(alice_customer.stripe_customer_id),
        config=CONFIG,
    )
    assert row.plan == "pro"
    assert {s.workspace_id for s in runtime_session.scalars(select(Subscription))} == {alice.workspace_id}

    scope_to_workspace(runtime_session, bob.workspace_id)
    visible = runtime_session.scalars(select(Subscription)).all()
    assert visible and {s.workspace_id for s in visible} == {bob.workspace_id}
    assert row.stripe_subscription_id not in {s.stripe_subscription_id for s in visible}
    assert [c.workspace_id for c in runtime_session.scalars(select(BillingCustomer))] == [bob.workspace_id]

    # Writing Alice's workspace while scoped to Bob violates WITH CHECK.
    with pytest.raises(DBAPIError):
        with runtime_session.begin_nested():
            runtime_session.add(BillingCustomer(workspace_id=alice.workspace_id, stripe_customer_id="cus_forged"))
            runtime_session.flush()
