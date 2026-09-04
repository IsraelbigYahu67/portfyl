from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import MappingProxyType

import pytest

from billing_config import BillingConfig, BillingInterval, PlanTier
from billing_reconciliation import project_subscription
from edition import Edition
from entitlements import resolve_entitlements


NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


def _config(current: str) -> BillingConfig:
    return BillingConfig(
        enabled=True,
        secret_key="sk_test_founder",
        webhook_secret="whsec_founder",
        trial_identity_key="trial-founder",
        app_url="https://portfyl.test",
        current_price_version=current,
        stripe_prices=MappingProxyType({
            (PlanTier.INVESTOR, BillingInterval.MONTH, "v1"): "price_investor_month_v1",
            (PlanTier.INVESTOR, BillingInterval.YEAR, "v1"): "price_investor_year_v1",
            (PlanTier.PRO, BillingInterval.MONTH, "v1"): "price_pro_month_v1",
            (PlanTier.PRO, BillingInterval.YEAR, "v1"): "price_pro_year_v1",
            (PlanTier.INVESTOR, BillingInterval.MONTH, "v2"): "price_investor_month_v2",
            (PlanTier.INVESTOR, BillingInterval.YEAR, "v2"): "price_investor_year_v2",
            (PlanTier.PRO, BillingInterval.MONTH, "v2"): "price_pro_month_v2",
            (PlanTier.PRO, BillingInterval.YEAR, "v2"): "price_pro_year_v2",
        }),
    )


def _remote(
    *,
    subscription_id: str = "sub_founder",
    price_id: str = "price_investor_month_v1",
    status: str = "active",
    cancel_at_period_end: bool = False,
    ended_at: int | None = None,
) -> dict:
    return {
        "id": subscription_id,
        "customer": "cus_founder",
        "status": status,
        "items": {"data": [{"price": {"id": price_id}}]},
        "current_period_start": int(NOW.timestamp()),
        "current_period_end": int((NOW + timedelta(days=30)).timestamp()),
        "cancel_at_period_end": cancel_at_period_end,
        "ended_at": ended_at,
    }


def test_continuous_subscription_keeps_v1_when_public_generation_moves_to_v2(
    db_session, test_workspace
):
    row = project_subscription(
        db_session,
        workspace_id=test_workspace.id,
        remote=_remote(),
        config=_config("v1"),
        now=NOW,
    )
    renewed = project_subscription(
        db_session,
        workspace_id=test_workspace.id,
        remote=_remote(),
        config=_config("v2"),
        now=NOW + timedelta(days=20),
    )
    assert renewed.id == row.id
    assert renewed.price_version == "v1"
    assert renewed.stripe_price_id == "price_investor_month_v1"


def test_same_plan_and_interval_cannot_be_silently_repriced(
    db_session, test_workspace
):
    project_subscription(
        db_session,
        workspace_id=test_workspace.id,
        remote=_remote(),
        config=_config("v1"),
        now=NOW,
    )
    with pytest.raises(ValueError, match="cannot change price generation"):
        project_subscription(
            db_session,
            workspace_id=test_workspace.id,
            remote=_remote(price_id="price_investor_month_v2"),
            config=_config("v2"),
            now=NOW + timedelta(days=1),
        )


def test_failed_payment_recovery_preserves_founder_price_and_restores_access(
    db_session, test_workspace
):
    row = project_subscription(
        db_session,
        workspace_id=test_workspace.id,
        remote=_remote(status="past_due"),
        config=_config("v2"),
        event_type="invoice.payment_failed",
        now=NOW,
    )
    expired = resolve_entitlements(
        db_session,
        edition=Edition.CLOUD,
        workspace_id=test_workspace.id,
        now=NOW + timedelta(days=15),
    )
    assert expired.plan is PlanTier.FREE

    restored = project_subscription(
        db_session,
        workspace_id=test_workspace.id,
        remote=_remote(status="active"),
        config=_config("v2"),
        event_type="invoice.paid",
        now=NOW + timedelta(days=15),
    )
    access = resolve_entitlements(
        db_session,
        edition=Edition.CLOUD,
        workspace_id=test_workspace.id,
        now=NOW + timedelta(days=15),
    )
    assert restored.id == row.id and restored.price_version == "v1"
    assert restored.payment_failed_at is None and restored.grace_ends_at is None
    assert access.plan is PlanTier.INVESTOR


def test_scheduled_cancel_keeps_access_then_resubscription_uses_v2(
    db_session, test_workspace
):
    founder = project_subscription(
        db_session,
        workspace_id=test_workspace.id,
        remote=_remote(cancel_at_period_end=True),
        config=_config("v2"),
        now=NOW,
    )
    access = resolve_entitlements(
        db_session,
        edition=Edition.CLOUD,
        workspace_id=test_workspace.id,
        now=NOW + timedelta(days=10),
    )
    assert access.plan is PlanTier.INVESTOR and access.cancel_at_period_end

    project_subscription(
        db_session,
        workspace_id=test_workspace.id,
        remote=_remote(status="canceled", ended_at=int((NOW + timedelta(days=30)).timestamp())),
        config=_config("v2"),
        event_type="customer.subscription.deleted",
        now=NOW + timedelta(days=30),
    )
    successor = project_subscription(
        db_session,
        workspace_id=test_workspace.id,
        remote=_remote(
            subscription_id="sub_successor",
            price_id="price_investor_month_v2",
        ),
        config=_config("v2"),
        now=NOW + timedelta(days=31),
    )
    assert founder.ended_at is not None
    assert successor.price_version == "v2"
    assert successor.stripe_price_id == "price_investor_month_v2"
