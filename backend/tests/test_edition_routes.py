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
    "/api/billing/prices",
    "/api/billing/entitlements",
    "/api/billing/checkout",
    "/api/billing/portal",
    "/api/billing/webhook",
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


def test_cloud_edition_omits_owner_only_and_payment_routes(monkeypatch):
    try:
        main = _reload_main(monkeypatch, "cloud")

        assert LOCAL_ONLY_API_PATHS.isdisjoint(main.app.openapi()["paths"])
        assert BILLING_API_PATHS.isdisjoint(main.app.openapi()["paths"])
        assert all(
            not path.startswith("/api/billing/")
            for path in main.app.openapi()["paths"]
        )
        assert TEST_PLAN_API_PATHS <= set(main.app.openapi()["paths"])
        _let_requests_past_the_cloud_gate(monkeypatch)
        client = TestClient(main.app)
        for path in LOCAL_ONLY_API_PATHS:
            assert client.get(path, headers=_GATE_HEADERS).status_code == 404
        for path in BILLING_API_PATHS:
            method = client.post if path not in {"/api/billing/prices", "/api/billing/entitlements"} else client.get
            assert method(path, headers=_GATE_HEADERS).status_code in (404, 405)
    finally:
        # Leave the process in the test suite's declared local edition so test
        # ordering cannot leak a cloud app into later imports.
        _reload_main(monkeypatch, "local")
