from __future__ import annotations

import pytest

from plans import MINIMUM_PLAN, PlanTier, plan_allows, plan_limits


def test_canonical_limits_and_plan_access_are_provider_neutral():
    limits = plan_limits({})
    assert limits[PlanTier.FREE].portfolios == 1
    assert limits[PlanTier.INVESTOR].broker_connections == 2
    assert limits[PlanTier.PRO].alerts == 100
    assert plan_allows(PlanTier.FREE, "alerts")
    assert not plan_allows(PlanTier.FREE, "portfolio_analytics")
    assert "assistant_byok" not in MINIMUM_PLAN
    assert "assistant_hosted" not in MINIMUM_PLAN
    assert MINIMUM_PLAN["advanced_research"] is PlanTier.PRO


def test_fair_use_limits_must_be_positive():
    with pytest.raises(RuntimeError, match="positive integer"):
        plan_limits({"PORTFYL_PRO_WATCHLIST_LIMIT": "0"})
