"""Envelope-encryption cipher for secrets stored at rest.

Two implementations, selected by edition exactly the way
``DatabaseSettings.from_env`` selects a database backend -- fail closed, no
implicit fallback between editions:

* :class:`LocalFernetCipher` -- the local edition (and the fast test suite)
  never talks to Google Cloud, so secrets are encrypted with a symmetric
  Fernet key read from ``PORTFYL_LOCAL_SECRET_KEY``.
* :class:`KmsEnvelopeCipher` -- the cloud edition calls Google Cloud KMS's
  ``encrypt``/``decrypt`` directly against a configured key
  (``PORTFYL_KMS_KEY_NAME``). Cloud KMS performs envelope encryption
  internally (a per-request data-encryption key wrapped by the configured key
  version); the application never generates or stores its own DEK. This is a
  deliberate simplification over app-side DEK generation/wrapping -- our
  secrets (broker API keys, webhook URLs, an AI API key) are all well under
  KMS's direct-encrypt payload limit and low-volume, so a second moving part
  buys nothing.

Callers never construct a cipher directly; use :func:`build_secret_cipher`,
which is the only edition-aware entry point.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from cryptography.fernet import Fernet, InvalidToken

from edition import Edition


@dataclass(frozen=True)
class EncryptedValue:
    """A secret at rest: opaque ciphertext plus the key version that produced
    it, so a future key rotation can identify which secrets still need
    re-encryption under a new version."""

    ciphertext: bytes
    key_version: str


class SecretCipher(Protocol):
    def encrypt(self, plaintext: str) -> EncryptedValue: ...
    def decrypt(self, value: EncryptedValue) -> str: ...


class LocalFernetCipher:
    """Symmetric Fernet cipher keyed by ``PORTFYL_LOCAL_SECRET_KEY``. Used by
    the local edition and by tests -- never by the cloud edition."""

    KEY_VERSION = "local:v1"

    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "LocalFernetCipher":
        raw = env.get("PORTFYL_LOCAL_SECRET_KEY", "").strip()
        if not raw:
            raise RuntimeError(
                "PORTFYL_LOCAL_SECRET_KEY is required to encrypt stored "
                "secrets in the local edition. Generate one with: "
                'python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"'
            )
        try:
            return cls(raw.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise RuntimeError(
                "PORTFYL_LOCAL_SECRET_KEY is not a valid Fernet key"
            ) from exc

    def encrypt(self, plaintext: str) -> EncryptedValue:
        return EncryptedValue(
            ciphertext=self._fernet.encrypt(plaintext.encode("utf-8")),
            key_version=self.KEY_VERSION,
        )

    def decrypt(self, value: EncryptedValue) -> str:
        try:
            return self._fernet.decrypt(value.ciphertext).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError(
                "Could not decrypt secret: invalid token or wrong key"
            ) from exc


class KmsEnvelopeCipher:
    """Google Cloud KMS symmetric encrypt/decrypt against one configured
    key. ``client`` is injected so tests never talk to real GCP -- only
    :meth:`from_env` (used by application startup, not by tests) constructs a
    real ``KeyManagementServiceClient``."""

    def __init__(self, client, key_name: str) -> None:
        self._client = client
        self._key_name = key_name

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "KmsEnvelopeCipher":
        key_name = env.get("PORTFYL_KMS_KEY_NAME", "").strip()
        if not key_name:
            raise RuntimeError(
                "PORTFYL_KMS_KEY_NAME is required to encrypt stored secrets "
                "in the cloud edition "
                "(projects/*/locations/*/keyRings/*/cryptoKeys/*)"
            )
        from google.cloud import kms

        return cls(kms.KeyManagementServiceClient(), key_name)

    def encrypt(self, plaintext: str) -> EncryptedValue:
        response = self._client.encrypt(
            request={"name": self._key_name, "plaintext": plaintext.encode("utf-8")}
        )
        return EncryptedValue(ciphertext=response.ciphertext, key_version=response.name)

    def decrypt(self, value: EncryptedValue) -> str:
        response = self._client.decrypt(
            request={"name": self._key_name, "ciphertext": value.ciphertext}
        )
        return response.plaintext.decode("utf-8")


def build_secret_cipher(env: Mapping[str, str], edition: Edition) -> SecretCipher:
    """The only edition-aware entry point. Cloud always uses KMS; every other
    edition uses the local Fernet cipher -- both fail closed on missing
    configuration rather than silently falling back."""
    if edition is Edition.CLOUD:
        return KmsEnvelopeCipher.from_env(env)
    return LocalFernetCipher.from_env(env)
