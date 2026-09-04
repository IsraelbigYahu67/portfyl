from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from billing_config import MINIMUM_PLAN, PlanTier
from edition import CAPABILITY_REGISTRY, CapabilityClass, Edition
from entitlements import EntitlementDenied, ensure_capability, ensure_count_limit, resolve_entitlements
from models import Subscription, TrialGrant


NOW = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)


def test_cloud_defaults_to_free(db_session, test_workspace):
    result = resolve_entitlements(db_session, edition=Edition.CLOUD, workspace_id=test_workspace.id, now=NOW)
    assert result.plan is PlanTier.FREE
    assert result.source == "free"
    assert "alerts" in result.capabilities
    assert "portfolio_analytics" not in result.capabilities


def test_active_trial_grants_pro_and_expires_without_deletion(db_session, test_user, test_workspace):
    grant = TrialGrant(
        workspace_id=test_workspace.id,
        activated_by_user_id=test_user.id,
        identity_fingerprint="a" * 64,
        activation_kind="csv_import",
        started_at=NOW,
        ends_at=NOW + timedelta(days=7),
    )
    db_session.add(grant)
    db_session.flush()
    active = resolve_entitlements(db_session, edition=Edition.CLOUD, workspace_id=test_workspace.id, now=NOW)
    expired = resolve_entitlements(db_session, edition=Edition.CLOUD, workspace_id=test_workspace.id, now=NOW + timedelta(days=7))
    assert active.plan is PlanTier.PRO and active.source == "trial"
    assert active.limits.hosted_ai_monthly == 15
    assert expired.plan is PlanTier.FREE
    assert db_session.get(TrialGrant, grant.id) is grant


def test_paid_subscription_and_grace(db_session, test_workspace):
    sub = Subscription(
        workspace_id=test_workspace.id,
        stripe_subscription_id="sub_1",
        stripe_price_id="price_1",
        plan="investor",
        billing_interval="month",
        price_version="v1",
        status="past_due",
        current_period_end=NOW - timedelta(days=1),
        payment_failed_at=NOW - timedelta(days=2),
        grace_ends_at=NOW + timedelta(days=12),
    )
    db_session.add(sub)
    db_session.flush()
    grace = resolve_entitlements(db_session, edition=Edition.CLOUD, workspace_id=test_workspace.id, now=NOW)
    after = resolve_entitlements(db_session, edition=Edition.CLOUD, workspace_id=test_workspace.id, now=NOW + timedelta(days=13))
    assert grace.plan is PlanTier.INVESTOR and grace.in_grace
    assert after.plan is PlanTier.FREE


def test_local_bypasses_billing_tables(db_session, test_workspace):
    result = resolve_entitlements(db_session, edition=Edition.LOCAL, workspace_id=test_workspace.id, now=NOW)
    assert result.source == "local"
    assert {"tax_report", "screener"} <= set(result.capabilities)


def test_local_bypass_never_touches_the_database(test_workspace):
    class DatabaseMustNotBeUsed:
        def __getattr__(self, name):
            raise AssertionError(f"local entitlement resolution touched db.{name}")

    result = resolve_entitlements(
        DatabaseMustNotBeUsed(),
        edition=Edition.LOCAL,
        workspace_id=test_workspace.id,
        now=NOW,
    )
    assert result.source == "local"


def test_capability_and_limit_denials(db_session, test_workspace):
    free = resolve_entitlements(db_session, edition=Edition.CLOUD, workspace_id=test_workspace.id, now=NOW)
    with pytest.raises(EntitlementDenied) as denied:
        ensure_capability(free, "portfolio_analytics", edition=Edition.CLOUD)
    assert denied.value.payload()["required_plan"] == "investor"
    with pytest.raises(EntitlementDenied) as limited:
        ensure_count_limit(free, "portfolios", used=1)
    assert limited.value.payload() == {
        "code": "quota_exceeded", "plan": "free", "resource": "portfolios", "limit": 1, "used": 1
    }


def test_every_capability_is_explicitly_local_only_or_has_a_minimum_plan():
    for key, capability in CAPABILITY_REGISTRY.items():
        if capability.classification is CapabilityClass.LOCAL_ONLY:
            assert key not in MINIMUM_PLAN
        else:
            assert key in MINIMUM_PLAN


@pytest.mark.parametrize("status", ["paused", "unpaid", "canceled", "incomplete_expired"])
def test_terminal_or_suspended_subscription_does_not_grant_access(
    db_session, test_workspace, status
):
    db_session.add(Subscription(
        workspace_id=test_workspace.id,
        stripe_subscription_id=f"sub_{status}",
        stripe_price_id="price_1",
        plan="pro",
        billing_interval="month",
        price_version="v1",
        status=status,
        current_period_start=NOW - timedelta(days=1),
        current_period_end=NOW + timedelta(days=29),
        ended_at=NOW if status != "paused" else None,
    ))
    db_session.flush()
    access = resolve_entitlements(
        db_session, edition=Edition.CLOUD, workspace_id=test_workspace.id, now=NOW
    )
    assert access.plan is PlanTier.FREE


def test_cloud_rejects_local_only_capability_before_plan_evaluation(db_session, test_workspace):
    local = resolve_entitlements(
        db_session, edition=Edition.LOCAL, workspace_id=test_workspace.id, now=NOW
    )
    with pytest.raises(EntitlementDenied) as denied:
        ensure_capability(local, "tax_report", edition=Edition.CLOUD)
    assert denied.value.payload() == {"code": "edition_unavailable", "capability": "tax_report"}


def test_scheduled_cancellation_keeps_access_until_exact_period_end(db_session, test_workspace):
    db_session.add(Subscription(
        workspace_id=test_workspace.id,
        stripe_subscription_id="sub_scheduled_cancel",
        stripe_price_id="price_pro",
        plan="pro",
        billing_interval="month",
        price_version="v1",
        status="active",
        current_period_start=NOW - timedelta(days=1),
        current_period_end=NOW + timedelta(days=1),
        cancel_at_period_end=True,
    ))
    db_session.flush()
    before = resolve_entitlements(
        db_session, edition=Edition.CLOUD, workspace_id=test_workspace.id,
        now=NOW + timedelta(days=1) - timedelta(microseconds=1),
    )
    at_end = resolve_entitlements(
        db_session, edition=Edition.CLOUD, workspace_id=test_workspace.id,
        now=NOW + timedelta(days=1),
    )
    assert before.plan is PlanTier.PRO and before.cancel_at_period_end
    assert at_end.plan is PlanTier.FREE
