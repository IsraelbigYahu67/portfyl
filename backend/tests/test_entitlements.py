from __future__ import annotations

from datetime import datetime, timezone

import pytest

from plans import MINIMUM_PLAN, PlanTier
from edition import CAPABILITY_REGISTRY, CapabilityClass, Edition
from entitlements import EntitlementDenied, ensure_capability, ensure_count_limit, resolve_entitlements


NOW = datetime(2026, 9, 4, 10, 0, tzinfo=timezone.utc)


def test_cloud_defaults_to_free(db_session, test_workspace):
    result = resolve_entitlements(db_session, edition=Edition.CLOUD, workspace_id=test_workspace.id, now=NOW)
    assert result.plan is PlanTier.FREE
    assert result.source == "free"
    assert "alerts" in result.capabilities
    assert "portfolio_analytics" not in result.capabilities


def test_cloud_free_resolution_does_not_query_payment_state(test_workspace):
    class DatabaseMustNotBeUsed:
        def __getattr__(self, name):
            raise AssertionError(f"cloud entitlement resolution touched db.{name}")

    result = resolve_entitlements(
        DatabaseMustNotBeUsed(),
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
