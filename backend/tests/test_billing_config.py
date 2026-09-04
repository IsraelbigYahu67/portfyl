from __future__ import annotations

import json

import pytest

from billing_config import (
    BillingConfig,
    BillingInterval,
    PlanTier,
    plan_allows,
    plan_limits,
)


def _enabled_env():
    catalog = {
        "v1": {
            "investor": {"month": "price_im", "year": "price_iy"},
            "pro": {"month": "price_pm", "year": "price_py"},
        }
    }
    return {
        "PORTFYL_BILLING_ENABLED": "1",
        "STRIPE_SECRET_KEY": "sk_test_value",
        "STRIPE_WEBHOOK_SECRET": "whsec_value",
        "PORTFYL_TRIAL_IDENTITY_KEY": "identity-key",
        "PORTFYL_STRIPE_PRICE_CATALOG": json.dumps(catalog),
        "PORTFYL_CURRENT_PRICE_VERSION": "v1",
    }


def test_canonical_limits_and_plan_access():
    limits = plan_limits({})
    assert limits[PlanTier.FREE] == (type(limits[PlanTier.FREE]))(
        portfolios=1, active_positions=15, transactions=250,
        broker_connections=0, watchlists=1, watchlist_symbols=15, alerts=3,
        hosted_ai_monthly=0, autosync_min_hours=None,
    )
    assert limits[PlanTier.INVESTOR].portfolios == 5
    assert limits[PlanTier.INVESTOR].broker_connections == 2
    assert limits[PlanTier.INVESTOR].alerts == 20
    assert limits[PlanTier.INVESTOR].autosync_min_hours == 24
    assert limits[PlanTier.PRO].portfolios == 15
    assert limits[PlanTier.PRO].broker_connections == 5
    assert limits[PlanTier.PRO].alerts == 100
    assert limits[PlanTier.PRO].hosted_ai_monthly == 100
    assert limits[PlanTier.PRO].autosync_min_hours == 6
    assert plan_allows(PlanTier.FREE, "alerts")
    assert not plan_allows(PlanTier.FREE, "portfolio_analytics")
    assert plan_allows(PlanTier.INVESTOR, "assistant_byok")
    assert not plan_allows(PlanTier.INVESTOR, "assistant_hosted")


def test_billing_disabled_requires_no_stripe_configuration():
    config = BillingConfig.from_env({
        "PORTFYL_STRIPE_PRICE_CATALOG": "not-json",
        "STRIPE_SECRET_KEY": "stale-local-secret",
    })
    assert config.enabled is False
    assert config.stripe_prices == {}
    assert config.secret_key is None


def test_enabled_billing_is_fail_closed():
    with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY"):
        BillingConfig.from_env({"PORTFYL_BILLING_ENABLED": "1"})


def test_price_catalog_is_versioned_and_reverse_mapped():
    config = BillingConfig.from_env(_enabled_env())
    assert config.price_id(PlanTier.PRO, BillingInterval.YEAR) == "price_py"
    assert config.price_mapping()["price_im"] == (
        PlanTier.INVESTOR,
        BillingInterval.MONTH,
        "v1",
    )


def test_duplicate_price_ids_are_rejected():
    env = _enabled_env()
    catalog = json.loads(env["PORTFYL_STRIPE_PRICE_CATALOG"])
    catalog["v1"]["pro"]["year"] = "price_pm"
    env["PORTFYL_STRIPE_PRICE_CATALOG"] = json.dumps(catalog)
    with pytest.raises(RuntimeError, match="unique"):
        BillingConfig.from_env(env)


@pytest.mark.parametrize(
    ("catalog_mutation", "message"),
    [
        (lambda catalog: catalog["v1"].__setitem__("enterprise", {"month": "price_x"}), "Unknown plan"),
        (lambda catalog: catalog["v1"]["pro"].__setitem__("weekly", "price_x"), "Unknown interval"),
    ],
)
def test_price_catalog_strictly_parses_plan_and_interval(catalog_mutation, message):
    env = _enabled_env()
    catalog = json.loads(env["PORTFYL_STRIPE_PRICE_CATALOG"])
    catalog_mutation(catalog)
    env["PORTFYL_STRIPE_PRICE_CATALOG"] = json.dumps(catalog)
    with pytest.raises(RuntimeError, match=message):
        BillingConfig.from_env(env)


def test_current_price_generation_must_be_complete():
    env = _enabled_env()
    env["PORTFYL_CURRENT_PRICE_VERSION"] = "v2"
    with pytest.raises(RuntimeError, match="price:investor:month:v2"):
        BillingConfig.from_env(env)


def test_fair_use_limits_must_be_positive():
    with pytest.raises(RuntimeError, match="positive integer"):
        plan_limits({"PORTFYL_PRO_WATCHLIST_LIMIT": "0"})
