from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from edition import (
    CAPABILITY_REGISTRY,
    CapabilityClass,
    Edition,
    capability_payload,
    edition_allows,
    edition_from_env,
)
from routers.capabilities import build_router


def test_edition_is_required():
    with pytest.raises(RuntimeError, match="PORTFYL_EDITION is required"):
        edition_from_env({})


def test_unknown_edition_is_rejected():
    with pytest.raises(RuntimeError, match="Unsupported PORTFYL_EDITION"):
        edition_from_env({"PORTFYL_EDITION": "preview"})


def test_only_tax_report_and_screener_are_local_only():
    local_only = {
        key
        for key, capability in CAPABILITY_REGISTRY.items()
        if capability.classification is CapabilityClass.LOCAL_ONLY
    }
    assert local_only == {"tax_report", "screener"}


@pytest.mark.parametrize("capability", ["tax_report", "screener"])
def test_local_only_capabilities_are_allowed_locally_and_denied_in_cloud(capability):
    assert edition_allows(Edition.LOCAL, capability) is True
    assert edition_allows(Edition.CLOUD, capability) is False


def test_cloud_payload_does_not_advertise_local_only_capabilities():
    payload = capability_payload(Edition.CLOUD)
    assert payload["edition"] == "cloud"
    assert "tax_report" not in payload["capabilities"]
    assert "screener" not in payload["capabilities"]
    assert "tax_report" not in payload["classifications"]
    assert "screener" not in payload["classifications"]
    assert payload["classifications"]["alerts"] == "cloud_free"
    assert "assistant_byok" not in payload["classifications"]
    assert "assistant_hosted" not in payload["classifications"]


def test_capabilities_endpoint_reports_local_registry():
    app = FastAPI()
    app.include_router(build_router(Edition.LOCAL), prefix="/api")

    response = TestClient(app).get("/api/capabilities")

    assert response.status_code == 200
    assert response.json()["edition"] == "local"
    assert {"tax_report", "screener"} <= set(response.json()["capabilities"])
