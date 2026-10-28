from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

import edge_trust
import rate_limit
from rate_limit import RateLimitRule

# The cloud edition mounts CloudApiGateMiddleware, which rejects every
# untrusted /api/* request with 403 *before* routing -- so in cloud these
# requests must first satisfy the gate, or the 404/405 assertions below
# would be measuring the gate instead of route registration.
_GATE_HEADERS = {
    "X-Portfyl-Edge-Token": "test-edge-token",
    "CF-Connecting-IP": "203.0.113.9",
}


def _let_requests_past_the_cloud_gate(monkeypatch):
    monkeypatch.setattr(edge_trust, "EDGE_TOKEN", "test-edge-token")
    monkeypatch.setattr(
        rate_limit,
        "RATE_LIMIT_RULES",
        {"global": RateLimitRule(name="global", limit=1000, window_seconds=60)},
    )
    monkeypatch.setattr(rate_limit, "consume_rate_limit", lambda **kwargs: None)


LOCAL_ONLY_API_PATHS = {
    "/api/analytics/tax-report",
    "/api/market/screener",
}
BILLING_API_PATHS = {
    "/api/billing/status",
    "/api/billing/checkout",
    "/api/billing/checkout/confirm",
    "/api/billing/portal",
    "/api/billing/webhook",
}
# Endpoints of the removed 2026-09 Stripe runtime that must stay gone.
REMOVED_BILLING_API_PATHS = {
    "/api/billing/prices",
    "/api/billing/entitlements",
}
TEST_PLAN_API_PATHS = {
    "/api/test-plans",
}


def _reload_main(monkeypatch, edition: str):
    monkeypatch.setenv("PORTFYL_EDITION", edition)
    import main

    return importlib.reload(main)


def test_local_edition_registers_owner_only_routes(monkeypatch):
    main = _reload_main(monkeypatch, "local")

    assert LOCAL_ONLY_API_PATHS <= set(main.app.openapi()["paths"])
    assert BILLING_API_PATHS.isdisjoint(main.app.openapi()["paths"])
    assert TEST_PLAN_API_PATHS.isdisjoint(main.app.openapi()["paths"])
    client = TestClient(main.app)
    for path in LOCAL_ONLY_API_PATHS:
        # Authentication may reject the request, but the route itself exists.
        assert client.get(path).status_code != 404


def test_cloud_edition_omits_owner_only_routes_and_mounts_billing(monkeypatch):
    try:
        monkeypatch.delenv("PORTFYL_BILLING_ENABLED", raising=False)
        main = _reload_main(monkeypatch, "cloud")
        paths = set(main.app.openapi()["paths"])

        assert LOCAL_ONLY_API_PATHS.isdisjoint(paths)
        assert BILLING_API_PATHS <= paths
        assert REMOVED_BILLING_API_PATHS.isdisjoint(paths)
        # Payments are off by default, so the private test switch is mounted.
        assert TEST_PLAN_API_PATHS <= paths
        _let_requests_past_the_cloud_gate(monkeypatch)
        client = TestClient(main.app)
        for path in LOCAL_ONLY_API_PATHS:
            assert client.get(path, headers=_GATE_HEADERS).status_code == 404
        # With billing disabled the webhook refuses instead of processing.
        assert client.post("/api/billing/webhook", headers=_GATE_HEADERS).status_code == 503
    finally:
        # Leave the process in the test suite's declared local edition so test
        # ordering cannot leak a cloud app into later imports.
        _reload_main(monkeypatch, "local")


def test_cloud_edition_with_billing_enabled_drops_the_test_plan_switch(monkeypatch):
    try:
        monkeypatch.setenv("PORTFYL_BILLING_ENABLED", "1")
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_edition")
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_edition")
        monkeypatch.setenv("PORTFYL_STRIPE_PRICE_INVESTOR", "price_investor")
        monkeypatch.setenv("PORTFYL_STRIPE_PRICE_PRO", "price_pro")
        monkeypatch.setenv("PORTFYL_APP_URL", "https://portfyl.example")
        main = _reload_main(monkeypatch, "cloud")
        paths = set(main.app.openapi()["paths"])

        assert BILLING_API_PATHS <= paths
        assert TEST_PLAN_API_PATHS.isdisjoint(paths)
    finally:
        for name in (
            "PORTFYL_BILLING_ENABLED", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
            "PORTFYL_STRIPE_PRICE_INVESTOR", "PORTFYL_STRIPE_PRICE_PRO", "PORTFYL_APP_URL",
        ):
            monkeypatch.delenv(name, raising=False)
        _reload_main(monkeypatch, "local")
