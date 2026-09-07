"""PostgreSQL/RLS coverage for account privacy endpoints."""

from __future__ import annotations

import json


def test_workspace_export_is_rls_scoped_and_secret_free(
    matrix_client,
    matrix_tenants,
):
    response = matrix_client.get("/api/settings/account/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-disposition"].startswith("attachment;")
    payload = response.json()
    encoded = json.dumps(payload)
    assert payload["workspace"]["id"] == str(
        matrix_tenants.alice.workspace_public_id
    )
    assert str(matrix_tenants.alice.portfolio_public_id) in encoded
    assert str(matrix_tenants.bob.workspace_public_id) not in encoded
    assert str(matrix_tenants.bob.portfolio_public_id) not in encoded
    for forbidden in (
        "api_key",
        "api_secret",
        "ciphertext",
        "key_version",
        "webhook",
    ):
        assert forbidden not in encoded


def test_deletion_status_cannot_be_read_by_switching_workspace_header(
    matrix_client,
    matrix_tenants,
):
    own = matrix_client.get("/api/settings/account/deletion")
    foreign = matrix_client.get(
        "/api/settings/account/deletion",
        headers={"X-Workspace-ID": str(matrix_tenants.bob.workspace_public_id)},
    )

    assert own.status_code == 200
    assert own.json() == {"scheduled": False, "grace_days": 30}
    assert foreign.status_code == 404
    assert foreign.json() == {"code": "resource_not_found"}
