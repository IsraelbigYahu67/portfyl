"""Deterministic, non-reversible upstream broker account identity."""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Mapping


ACCOUNT_FINGERPRINT_ENV = "PORTFYL_ACCOUNT_FINGERPRINT_KEY"
_FINGERPRINT_VERSION = "1"


def _encode_field(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return len(encoded).to_bytes(4, "big") + encoded


def account_fingerprint(
    *,
    broker: str,
    environment: str,
    provider_account_id: object,
    env: Mapping[str, str] | None = None,
) -> str:
    """Return an HMAC identity without persisting the provider account ID."""
    source = env if env is not None else os.environ
    secret = source.get(ACCOUNT_FINGERPRINT_ENV, "").strip()
    if len(secret) < 32:
        raise RuntimeError(
            f"{ACCOUNT_FINGERPRINT_ENV} must contain at least 32 characters"
        )

    if provider_account_id is None:
        raise ValueError("Trading 212 account summary did not contain an account ID")
    account_id = str(provider_account_id).strip()
    if not account_id or len(account_id) > 256:
        raise ValueError("Trading 212 account summary did not contain a valid account ID")

    message = b"".join(
        _encode_field(field)
        for field in (
            _FINGERPRINT_VERSION,
            broker.strip().lower(),
            environment.strip().lower(),
            account_id,
        )
    )
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
