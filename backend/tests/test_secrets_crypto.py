"""Envelope-encryption cipher tests: local Fernet round-trip, fail-closed
edition selection, and a KMS round-trip against a stubbed client (never real
GCP)."""
from __future__ import annotations

import pytest

from edition import Edition
from secrets_crypto import (
    EncryptedValue,
    KmsEnvelopeCipher,
    LocalFernetCipher,
    build_secret_cipher,
)

TEST_KEY = "OmC2HEZsgRV5WF4AjQgE1OZTViBiZm6ILN131PwtgPg="


# ---------------------------------------------------------------------------
# LocalFernetCipher
# ---------------------------------------------------------------------------


def test_local_cipher_round_trips():
    cipher = LocalFernetCipher.from_env({"PORTFYL_LOCAL_SECRET_KEY": TEST_KEY})
    encrypted = cipher.encrypt("sk_live_super_secret")
    assert encrypted.key_version == "local:v1"
    assert b"sk_live_super_secret" not in encrypted.ciphertext
    assert cipher.decrypt(encrypted) == "sk_live_super_secret"


def test_local_cipher_produces_fresh_ciphertext_each_time():
    cipher = LocalFernetCipher.from_env({"PORTFYL_LOCAL_SECRET_KEY": TEST_KEY})
    first = cipher.encrypt("same-plaintext")
    second = cipher.encrypt("same-plaintext")
    assert first.ciphertext != second.ciphertext
    assert cipher.decrypt(first) == cipher.decrypt(second) == "same-plaintext"


def test_local_cipher_rejects_missing_key():
    with pytest.raises(RuntimeError, match="PORTFYL_LOCAL_SECRET_KEY"):
        LocalFernetCipher.from_env({})


def test_local_cipher_rejects_malformed_key():
    with pytest.raises(RuntimeError, match="not a valid Fernet key"):
        LocalFernetCipher.from_env({"PORTFYL_LOCAL_SECRET_KEY": "not-a-fernet-key"})


def test_local_cipher_decrypt_rejects_wrong_key():
    cipher = LocalFernetCipher.from_env({"PORTFYL_LOCAL_SECRET_KEY": TEST_KEY})
    encrypted = cipher.encrypt("secret")
    other_key = "hL3F2q0p8m2m1v9YV1c3r7wq2s9t0u1v2w3x4y5z6A8="
    other_cipher = LocalFernetCipher.from_env({"PORTFYL_LOCAL_SECRET_KEY": other_key})
    with pytest.raises(ValueError, match="Could not decrypt"):
        other_cipher.decrypt(encrypted)


# ---------------------------------------------------------------------------
# KmsEnvelopeCipher (stubbed client -- never real GCP)
# ---------------------------------------------------------------------------


class _FakeKmsResponse:
    def __init__(self, **fields):
        self.__dict__.update(fields)


class _FakeKmsClient:
    """Records the key name used at encrypt time and reproduces it at
    decrypt time, like real Cloud KMS resolving the key version from the
    ciphertext -- without ever touching the network."""

    def __init__(self):
        self.encrypt_calls: list[dict] = []
        self.decrypt_calls: list[dict] = []

    def encrypt(self, request):
        self.encrypt_calls.append(request)
        plaintext = request["plaintext"]
        # Trivial reversible "ciphertext" is enough to prove wiring; real KMS
        # ciphertext is opaque bytes we never inspect.
        ciphertext = b"kms:" + plaintext[::-1]
        version = request["name"] + "/cryptoKeyVersions/3"
        return _FakeKmsResponse(ciphertext=ciphertext, name=version)

    def decrypt(self, request):
        self.decrypt_calls.append(request)
        ciphertext = request["ciphertext"]
        assert ciphertext.startswith(b"kms:")
        plaintext = ciphertext[len(b"kms:"):][::-1]
        return _FakeKmsResponse(plaintext=plaintext)


def test_kms_cipher_round_trips_against_stubbed_client():
    client = _FakeKmsClient()
    cipher = KmsEnvelopeCipher(client, "projects/p/locations/l/keyRings/r/cryptoKeys/k")

    encrypted = cipher.encrypt("broker-api-secret")

    assert isinstance(encrypted, EncryptedValue)
    assert encrypted.key_version == "projects/p/locations/l/keyRings/r/cryptoKeys/k/cryptoKeyVersions/3"
    assert cipher.decrypt(encrypted) == "broker-api-secret"
    assert client.encrypt_calls[0]["name"] == "projects/p/locations/l/keyRings/r/cryptoKeys/k"


def test_kms_cipher_from_env_requires_key_name():
    with pytest.raises(RuntimeError, match="PORTFYL_KMS_KEY_NAME"):
        KmsEnvelopeCipher.from_env({})


# ---------------------------------------------------------------------------
# build_secret_cipher (edition-aware factory)
# ---------------------------------------------------------------------------


def test_build_secret_cipher_uses_local_cipher_for_local_edition():
    cipher = build_secret_cipher(
        {"PORTFYL_LOCAL_SECRET_KEY": TEST_KEY}, Edition.LOCAL
    )
    assert isinstance(cipher, LocalFernetCipher)


def test_build_secret_cipher_ignores_kms_var_in_local_edition():
    cipher = build_secret_cipher(
        {
            "PORTFYL_LOCAL_SECRET_KEY": TEST_KEY,
            "PORTFYL_KMS_KEY_NAME": "projects/p/locations/l/keyRings/r/cryptoKeys/k",
        },
        Edition.LOCAL,
    )
    assert isinstance(cipher, LocalFernetCipher)


def test_build_secret_cipher_fails_closed_for_cloud_edition_without_kms_var():
    with pytest.raises(RuntimeError, match="PORTFYL_KMS_KEY_NAME"):
        build_secret_cipher({}, Edition.CLOUD)
