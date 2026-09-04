from __future__ import annotations

import importlib

from fastapi.testclient import TestClient


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


def test_cloud_edition_omits_owner_only_routes_from_openapi_and_dispatch(monkeypatch):
    try:
        main = _reload_main(monkeypatch, "cloud")

        assert LOCAL_ONLY_API_PATHS.isdisjoint(main.app.openapi()["paths"])
        assert BILLING_API_PATHS <= set(main.app.openapi()["paths"])
        client = TestClient(main.app)
        for path in LOCAL_ONLY_API_PATHS:
            assert client.get(path).status_code == 404
    finally:
        # Leave the process in the test suite's declared local edition so test
        # ordering cannot leak a cloud app into later imports.
        _reload_main(monkeypatch, "local")
