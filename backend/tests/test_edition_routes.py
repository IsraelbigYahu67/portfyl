from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

import edge_trust
import rate_limit
from rate_limit import RateLimitRule

# Every /api/* request now passes through the cloud-only CloudApiGateMiddleware
# (main.py, wired in the rate-limiting feature): it 403s any request lacking a
# valid trusted-edge token before routing ever sees it. The cloud-edition test
# below hits real routes directly to check for 404/405 (route non-existence),
# so it must satisfy the gate first -- these headers/patches make that
# possible without weakening what the test actually verifies.
_GATE_BYPASS_HEADERS = {
    "X-Portfyl-Edge-Token": "test-edge-token",
    "CF-Connecting-IP": "203.0.113.9",
}


def _bypass_cloud_gate(monkeypatch, db_session) -> None:
    monkeypatch.setattr(edge_trust, "EDGE_TOKEN", "test-edge-token")
    monkeypatch.setattr(
        rate_limit,
        "RATE_LIMIT_RULES",
        {"global": RateLimitRule(name="global", limit=100, window_seconds=60)},
    )
    monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
    monkeypatch.setattr(rate_limit, "SessionLocal", lambda: db_session)


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


def _reload_main(monkeypatch, edition: str):
    monkeypatch.setenv("PORTFYL_EDITION", edition)
    import main

    return importlib.reload(main)


def test_local_edition_registers_owner_only_routes(monkeypatch):
    main = _reload_main(monkeypatch, "local")

    assert LOCAL_ONLY_API_PATHS <= set(main.app.openapi()["paths"])
    assert BILLING_API_PATHS.isdisjoint(main.app.openapi()["paths"])
    client = TestClient(main.app)
    for path in LOCAL_ONLY_API_PATHS:
        # Authentication may reject the request, but the route itself exists.
        assert client.get(path).status_code != 404


def test_cloud_edition_omits_owner_only_and_payment_routes(monkeypatch, db_session):
    try:
        main = _reload_main(monkeypatch, "cloud")
        _bypass_cloud_gate(monkeypatch, db_session)

        assert LOCAL_ONLY_API_PATHS.isdisjoint(main.app.openapi()["paths"])
        assert BILLING_API_PATHS.isdisjoint(main.app.openapi()["paths"])
        assert all(
            not path.startswith("/api/billing/")
            for path in main.app.openapi()["paths"]
        )
        client = TestClient(main.app)
        for path in LOCAL_ONLY_API_PATHS:
            assert client.get(path, headers=_GATE_BYPASS_HEADERS).status_code == 404
        for path in BILLING_API_PATHS:
            method = client.post if path not in {"/api/billing/prices", "/api/billing/entitlements"} else client.get
            assert method(path, headers=_GATE_BYPASS_HEADERS).status_code in (404, 405)
    finally:
        # Leave the process in the test suite's declared local edition so test
        # ordering cannot leak a cloud app into later imports.
        _reload_main(monkeypatch, "local")
