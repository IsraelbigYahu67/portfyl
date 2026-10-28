"""Minimal Stripe REST boundary for cloud billing.

Plain httpx instead of the stripe SDK: Portfyl needs six calls and webhook
signature verification, and Managed Payments needs an explicitly pinned API
version. Tests replace the client object and never reach Stripe.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Mapping, Protocol
from urllib.parse import urlencode

import httpx


STRIPE_API_BASE = "https://api.stripe.com/v1"
WEBHOOK_TOLERANCE_SECONDS = 300


class StripeError(Exception):
    """A Stripe request failed. `transient` errors are worth retrying."""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None, transient: bool = False):
        super().__init__(message)
        self.status = status
        self.code = code
        self.transient = transient


class InvalidWebhookSignature(Exception):
    pass


def _flatten(params: Mapping[str, Any], prefix: str = "") -> list[tuple[str, str]]:
    """Encode nested params the way Stripe's form API expects
    (`line_items[0][price]=...`, `metadata[key]=...`)."""
    pairs: list[tuple[str, str]] = []
    for key, value in params.items():
        name = f"{prefix}[{key}]" if prefix else str(key)
        if value is None:
            continue
        if isinstance(value, Mapping):
            pairs.extend(_flatten(value, name))
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                item_name = f"{name}[{index}]"
                if isinstance(item, Mapping):
                    pairs.extend(_flatten(item, item_name))
                else:
                    pairs.append((item_name, _scalar(item)))
        else:
            pairs.append((name, _scalar(value)))
    return pairs


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class StripeClientProtocol(Protocol):
    def create_customer(self, *, email: str, workspace_public_id: str, idempotency_key: str) -> dict: ...
    def create_checkout_session(self, params: Mapping[str, Any], *, idempotency_key: str) -> dict: ...
    def retrieve_checkout_session(self, session_id: str) -> dict: ...
    def retrieve_subscription(self, subscription_id: str) -> dict: ...
    def list_subscriptions(self, customer_id: str) -> list[dict]: ...
    def create_portal_session(self, *, customer_id: str, return_url: str) -> dict: ...


class StripeClient:
    def __init__(self, secret_key: str, *, api_version: str, timeout: float = 15.0):
        self._client = httpx.Client(
            base_url=STRIPE_API_BASE,
            auth=(secret_key, ""),
            headers={"Stripe-Version": api_version},
            timeout=timeout,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        encoded = _flatten(params or {})
        try:
            if method == "GET":
                response = self._client.get(path, params=encoded, headers=headers)
            else:
                # httpx only form-encodes a dict, which cannot repeat or nest
                # keys the way Stripe's `a[0][b]` parameters need.
                response = self._client.request(
                    method,
                    path,
                    content=urlencode(encoded).encode(),
                    headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
                )
        except httpx.HTTPError as exc:
            raise StripeError(f"Stripe request failed: {type(exc).__name__}", transient=True) from exc
        try:
            body = response.json()
        except ValueError:
            body = {}
        if response.status_code >= 400:
            error = body.get("error", {}) if isinstance(body, dict) else {}
            raise StripeError(
                error.get("message") or f"Stripe returned HTTP {response.status_code}",
                status=response.status_code,
                code=error.get("code") or error.get("type"),
                transient=response.status_code == 429 or response.status_code >= 500,
            )
        return body

    def create_customer(self, *, email: str, workspace_public_id: str, idempotency_key: str) -> dict:
        return self._request(
            "POST",
            "/customers",
            params={"email": email, "metadata": {"portfyl_workspace_id": workspace_public_id}},
            idempotency_key=idempotency_key,
        )

    def create_checkout_session(self, params: Mapping[str, Any], *, idempotency_key: str) -> dict:
        return self._request("POST", "/checkout/sessions", params=params, idempotency_key=idempotency_key)

    def retrieve_checkout_session(self, session_id: str) -> dict:
        return self._request("GET", f"/checkout/sessions/{session_id}")

    def retrieve_subscription(self, subscription_id: str) -> dict:
        return self._request("GET", f"/subscriptions/{subscription_id}")

    def list_subscriptions(self, customer_id: str) -> list[dict]:
        body = self._request(
            "GET",
            "/subscriptions",
            params={"customer": customer_id, "status": "all", "limit": 20},
        )
        return list(body.get("data") or [])

    def create_portal_session(self, *, customer_id: str, return_url: str) -> dict:
        return self._request(
            "POST",
            "/billing_portal/sessions",
            params={"customer": customer_id, "return_url": return_url},
        )


def verify_webhook(
    payload: bytes,
    signature_header: str | None,
    secret: str,
    *,
    tolerance: int = WEBHOOK_TOLERANCE_SECONDS,
    now: float | None = None,
) -> dict:
    """Verify a `Stripe-Signature` header and return the decoded event.

    Stripe signs `"{timestamp}.{raw body}"` with HMAC-SHA256 and may send
    several `v1` signatures while a signing secret is being rolled.
    """
    if not signature_header:
        raise InvalidWebhookSignature("missing signature header")
    timestamp: int | None = None
    signatures: list[str] = []
    for part in signature_header.split(","):
        key, _, value = part.strip().partition("=")
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError as exc:
                raise InvalidWebhookSignature("malformed timestamp") from exc
        elif key == "v1" and value:
            signatures.append(value)
    if timestamp is None or not signatures:
        raise InvalidWebhookSignature("malformed signature header")
    current = time.time() if now is None else now
    if abs(current - timestamp) > tolerance:
        raise InvalidWebhookSignature("timestamp outside tolerance")
    expected = hmac.new(
        secret.encode(),
        f"{timestamp}.".encode() + payload,
        hashlib.sha256,
    ).hexdigest()
    if not any(hmac.compare_digest(expected, candidate) for candidate in signatures):
        raise InvalidWebhookSignature("signature mismatch")
    try:
        event = json.loads(payload)
    except ValueError as exc:
        raise InvalidWebhookSignature("payload is not JSON") from exc
    if not isinstance(event, dict):
        raise InvalidWebhookSignature("payload is not an event object")
    return event
