"""PostgreSQL/RLS coverage for account privacy endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session


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
    assert own.json() == {"scheduled": False}
    assert foreign.status_code == 404
    assert foreign.json() == {"code": "resource_not_found"}


def test_immediate_deletion_erases_alice_completely_and_leaves_bob_alone(
    matrix_client,
    matrix_tenants,
    postgres_engine,
):
    """The full-stack delete under forced RLS: every tenant table Alice's
    workspace owns cascades away, her user and sessions go with it, the
    identity provider is told, the cookie is cleared, and Bob is untouched."""
    from firebase_identity import VerifiedIdentity
    from models import AuthSession, Membership, Portfolio, User, Workspace
    from routers.auth import get_identity_verifier

    alice = matrix_tenants.alice
    bob = matrix_tenants.bob
    with Session(postgres_engine) as db:
        user = db.get(User, alice.user_id)
        uid, email = user.firebase_uid, user.email
        name = db.get(Workspace, alice.workspace_id).name
    deleted_uids = []

    class Verifier:
        def verify_id_token(self, token):
            return VerifiedIdentity(
                uid=uid,
                email=email,
                email_verified=True,
                display_name=None,
                authenticated_at=datetime.now(timezone.utc),
            )

        def delete_user(self, firebase_uid):
            deleted_uids.append(firebase_uid)

    matrix_client.app.dependency_overrides[get_identity_verifier] = lambda: Verifier()

    wrong = matrix_client.post(
        "/api/settings/account/deletion",
        json={"reauth_id_token": "t", "confirmation": "not the name"},
    )
    assert wrong.status_code == 400
    assert wrong.json() == {"code": "workspace_confirmation_mismatch"}

    response = matrix_client.post(
        "/api/settings/account/deletion",
        json={"reauth_id_token": "t", "confirmation": name},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "deleted": True,
        "account_deleted": True,
        "refunded": False,
        "refunded_amount_cents": None,
        "currency": None,
    }
    assert deleted_uids == [uid]
    assert "portfyl_session=" in response.headers["set-cookie"]
    with Session(postgres_engine) as db:
        assert db.get(Workspace, alice.workspace_id) is None
        assert db.get(User, alice.user_id) is None
        assert db.scalar(select(func.count()).select_from(Portfolio).where(
            Portfolio.workspace_id == alice.workspace_id)) == 0
        assert db.scalar(select(func.count()).select_from(Membership).where(
            Membership.user_id == alice.user_id)) == 0
        assert db.scalar(select(func.count()).select_from(AuthSession).where(
            AuthSession.user_id == alice.user_id)) == 0
        assert db.get(Workspace, bob.workspace_id) is not None
        assert db.get(User, bob.user_id) is not None
        assert db.scalar(select(func.count()).select_from(Portfolio).where(
            Portfolio.workspace_id == bob.workspace_id)) == 1
