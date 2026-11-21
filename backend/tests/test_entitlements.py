from __future__ import annotations

from datetime import datetime, timezone

import pytest

import entitlements as entitlements_module
from app_settings import set_workspace_setting
from plans import MINIMUM_PLAN, PlanTier
from edition import CAPABILITY_REGISTRY, CapabilityClass, Edition
from entitlements import (
    PRIVATE_TEST_PLAN_SETTING_KEY,
    EntitlementDenied,
    ensure_capability,
    ensure_count_limit,
    resolve_entitlements,
)


NOW = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)


def test_cloud_defaults_to_free(db_session, test_workspace):
    result = resolve_entitlements(db_session, edition=Edition.CLOUD, workspace_id=test_workspace.id, now=NOW)
    assert result.plan is PlanTier.FREE
    assert result.source == "free"
    assert "alerts" in result.capabilities
    assert "portfolio_analytics" not in result.capabilities


def test_cloud_free_resolution_reads_subscription_then_test_plan_setting(test_workspace, monkeypatch):
    class DatabaseMustNotBeUsed:
        def __getattr__(self, name):
            raise AssertionError(f"cloud entitlement resolution touched db.{name}")

    seen = {}

    def get_test_setting(db, workspace_id, key):
        seen.update(db=db, workspace_id=workspace_id, key=key)
        return None

    def no_subscription(db, workspace_id):
        seen["subscription_workspace_id"] = workspace_id
        return None

    monkeypatch.delenv("PORTFYL_BILLING_ENABLED", raising=False)
    monkeypatch.setattr(entitlements_module, "_live_subscription", no_subscription)
    monkeypatch.setattr(entitlements_module, "_trial_state", lambda db, workspace_id, now: (None, None))
    monkeypatch.setattr(entitlements_module, "get_workspace_setting", get_test_setting)
    result = resolve_entitlements(
        DatabaseMustNotBeUsed(),
        edition=Edition.CLOUD,
        workspace_id=test_workspace.id,
        now=NOW,
    )

    assert result.plan is PlanTier.FREE
    assert result.source == "free"
    assert seen["subscription_workspace_id"] == test_workspace.id
    assert seen["workspace_id"] == test_workspace.id
    assert seen["key"] == PRIVATE_TEST_PLAN_SETTING_KEY


@pytest.mark.parametrize(
    ("selected", "expected_capability"),
    [
        (PlanTier.INVESTOR, "portfolio_analytics"),
        (PlanTier.PRO, "advanced_research"),
    ],
)
def test_cloud_uses_workspace_test_plan(
    db_session, test_workspace, selected, expected_capability
):
    set_workspace_setting(
        db_session,
        test_workspace.id,
        PRIVATE_TEST_PLAN_SETTING_KEY,
        selected.value,
    )

    result = resolve_entitlements(
        db_session,
        edition=Edition.CLOUD,
        workspace_id=test_workspace.id,
        now=NOW,
    )

    assert result.plan is selected
    assert result.source == "test_selection"
    assert expected_capability in result.capabilities


def test_cloud_invalid_test_plan_fails_closed(db_session, test_workspace):
    set_workspace_setting(
        db_session,
        test_workspace.id,
        PRIVATE_TEST_PLAN_SETTING_KEY,
        "enterprise",
    )

    result = resolve_entitlements(
        db_session,
        edition=Edition.CLOUD,
        workspace_id=test_workspace.id,
        now=NOW,
    )

    assert result.plan is PlanTier.FREE
    assert result.source == "free"


def test_local_bypasses_plan_limits(db_session, test_workspace):
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


def test_cloud_rejects_local_only_capability_before_plan_evaluation(db_session, test_workspace):
    local = resolve_entitlements(
        db_session, edition=Edition.LOCAL, workspace_id=test_workspace.id, now=NOW
    )
    with pytest.raises(EntitlementDenied) as denied:
        ensure_capability(local, "tax_report", edition=Edition.CLOUD)
    assert denied.value.payload() == {"code": "edition_unavailable", "capability": "tax_report"}


# --- the free trial in the resolution order -----------------------------------

TRIAL_ENV = {"PORTFYL_TRIAL_FINGERPRINT_KEY": "test-only-trial-fingerprint-key-0000000001"}


def _start_trial(db, workspace):
    import trials

    grant = trials.grant_trial(
        db, workspace_id=workspace.id, email="trial@example.com", now=NOW, env=TRIAL_ENV
    )
    assert grant is not None
    return grant


def _resolve_with(db, workspace, env):
    return resolve_entitlements(
        db, edition=Edition.CLOUD, workspace_id=workspace.id, now=NOW, env=env
    )


def test_live_subscription_wins_over_trial(db_session, test_workspace):
    from models import Subscription

    _start_trial(db_session, test_workspace)
    db_session.add(Subscription(
        workspace_id=test_workspace.id,
        stripe_subscription_id="sub_x", stripe_customer_id="cus_x", stripe_price_id="price_x",
        plan="investor", status="active",
    ))
    db_session.flush()

    result = _resolve_with(db_session, test_workspace, TRIAL_ENV)

    assert result.plan is PlanTier.INVESTOR
    assert result.source == "subscription"


def test_test_selection_wins_over_trial_when_billing_off(db_session, test_workspace):
    _start_trial(db_session, test_workspace)
    set_workspace_setting(
        db_session, test_workspace.id, PRIVATE_TEST_PLAN_SETTING_KEY, PlanTier.INVESTOR.value
    )

    result = _resolve_with(db_session, test_workspace, TRIAL_ENV)

    assert result.plan is PlanTier.INVESTOR
    assert result.source == "test_selection"


def test_trial_wins_over_free_when_billing_on(db_session, test_workspace):
    _start_trial(db_session, test_workspace)
    env = {**TRIAL_ENV, "PORTFYL_BILLING_ENABLED": "1"}
    # A stale test selection must not matter once real payments are on.
    set_workspace_setting(
        db_session, test_workspace.id, PRIVATE_TEST_PLAN_SETTING_KEY, PlanTier.FREE.value
    )

    result = _resolve_with(db_session, test_workspace, env)

    assert result.plan is PlanTier.PRO
    assert result.source == "trial"


def test_trial_wins_over_free_when_billing_off_and_no_selection(db_session, test_workspace):
    _start_trial(db_session, test_workspace)

    result = _resolve_with(db_session, test_workspace, TRIAL_ENV)

    assert result.plan is PlanTier.PRO
    assert result.source == "trial"
    assert "advanced_research" in result.capabilities


def test_invalid_test_selection_does_not_hide_the_trial(db_session, test_workspace):
    _start_trial(db_session, test_workspace)
    set_workspace_setting(db_session, test_workspace.id, PRIVATE_TEST_PLAN_SETTING_KEY, "enterprise")

    assert _resolve_with(db_session, test_workspace, TRIAL_ENV).source == "trial"


def test_not_eligible_payload_is_free(db_session, test_workspace):
    set_workspace_setting(db_session, test_workspace.id, "trial_withheld", "1")
    env = {**TRIAL_ENV, "PORTFYL_BILLING_ENABLED": "1"}

    payload = _resolve_with(db_session, test_workspace, env).payload()

    assert payload["plan"] == "free"
    assert payload["source"] == "free"
    assert payload["trial_ended_reason"] == "not_eligible"


def test_local_edition_ignores_trial(db_session, test_workspace):
    _start_trial(db_session, test_workspace)

    result = resolve_entitlements(
        db_session, edition=Edition.LOCAL, workspace_id=test_workspace.id, now=NOW
    )

    assert result.source == "local"
    assert result.payload()["trial_ended_reason"] is None
