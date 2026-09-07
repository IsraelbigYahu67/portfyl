from __future__ import annotations

import pytest

from datetime import datetime, timezone

from auth import session_cookie_policy
from firebase_identity import (
    FirebaseIdentityVerifier,
    IdentityVerificationError,
    VerifiedIdentity,
)


class FakeFirebaseAuth:
    def __init__(self, claims: dict):
        self.claims = claims
        self.verify_calls: list[tuple[str, object, bool]] = []
        self.revoke_calls: list[tuple[str, object]] = []
        self.delete_calls: list[tuple[str, object]] = []

    def verify_id_token(self, token: str, *, app: object, check_revoked: bool):
        self.verify_calls.append((token, app, check_revoked))
        return self.claims

    def revoke_refresh_tokens(self, uid: str, *, app: object):
        self.revoke_calls.append((uid, app))

    def delete_user(self, uid: str, *, app: object):
        self.delete_calls.append((uid, app))


@pytest.mark.parametrize(
    "env,expected",
    [
        ({}, ("__Host-portfyl_session", True)),
        ({"PORTFYL_TESTING": "1"}, ("portfyl_session", False)),
    ],
)
def test_session_cookie_policy_requires_secure_host_cookie_outside_tests(
    env: dict[str, str],
    expected: tuple[str, bool],
):
    assert session_cookie_policy(env) == expected


def test_firebase_verifier_maps_only_normalized_identity_fields():
    firebase_app = object()
    auth_client = FakeFirebaseAuth({
        "uid": "firebase-alice",
        "email": " Alice@Example.COM ",
        "email_verified": True,
        "name": "Alice Investor",
        "admin": True,
    })
    verifier = FirebaseIdentityVerifier(auth_client=auth_client, app=firebase_app)

    identity = verifier.verify_id_token("firebase-token")

    assert identity == VerifiedIdentity(
        uid="firebase-alice",
        email="alice@example.com",
        email_verified=True,
        display_name="Alice Investor",
    )
    assert auth_client.verify_calls == [("firebase-token", firebase_app, True)]


def test_firebase_verifier_maps_auth_time_for_sensitive_reauthentication():
    firebase_app = object()
    auth_client = FakeFirebaseAuth({
        "uid": "firebase-alice",
        "email": "alice@example.com",
        "email_verified": True,
        "auth_time": 1_788_782_400,
    })
    verifier = FirebaseIdentityVerifier(auth_client=auth_client, app=firebase_app)

    identity = verifier.verify_id_token("fresh-token")

    assert identity.authenticated_at == datetime.fromtimestamp(
        1_788_782_400,
        tz=timezone.utc,
    )


@pytest.mark.parametrize("claims", [
    {"email": "alice@example.com", "email_verified": True},
    {"uid": "firebase-alice", "email_verified": True},
])
def test_firebase_verifier_rejects_identity_without_uid_or_email(claims: dict):
    verifier = FirebaseIdentityVerifier(
        auth_client=FakeFirebaseAuth(claims),
        app=object(),
    )

    with pytest.raises(IdentityVerificationError, match="UID and e-mail"):
        verifier.verify_id_token("firebase-token")


def test_firebase_verifier_revokes_refresh_tokens_for_uid():
    firebase_app = object()
    auth_client = FakeFirebaseAuth({})
    verifier = FirebaseIdentityVerifier(auth_client=auth_client, app=firebase_app)

    verifier.revoke_refresh_tokens("firebase-alice")

    assert auth_client.revoke_calls == [("firebase-alice", firebase_app)]


def test_firebase_verifier_deletes_user_for_completed_account_erasure():
    firebase_app = object()
    auth_client = FakeFirebaseAuth({})
    verifier = FirebaseIdentityVerifier(auth_client=auth_client, app=firebase_app)

    verifier.delete_user("firebase-alice")

    assert auth_client.delete_calls == [("firebase-alice", firebase_app)]
