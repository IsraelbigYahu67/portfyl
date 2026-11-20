"""Cloudflare Turnstile bot check for new Portfyl identities.

The check is on demand: `/auth/session` asks for a token only when it is about
to create a new `User` (see `routers/auth.py`), so existing users never load
or see Turnstile. This module owns three things:

* `TurnstileConfig.from_env`: the configuration, which **fails closed** at
  startup. The cloud edition refuses to start without `PORTFYL_TURNSTILE_SECRET`
  unless the operator explicitly sets `PORTFYL_TURNSTILE_DISABLED=1`.
* `verify_signup_token`: one server-side `siteverify` call (sync `httpx`, 5 s
  budget) that returns `None` on success or a reason code. It never logs or
  returns the token or the secret.
* `csp_enabled` / `health_check`: the CSP and `/health` helpers.

Cloudflare's published dummy keys (`1x0000...`, `2x0000...`, `3x0000...`) are
accepted only together with `PORTFYL_TURNSTILE_TEST_KEYS=1`, so they cannot be
left in production by accident. Verified against the Turnstile docs on
2026-11-20: siteverify URL and fields, tokens expire after 300 s and verify
once, CSP needs `script-src` and `frame-src` for `challenges.cloudflare.com`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Mapping
from urllib.parse import urlsplit

import httpx

from edition import Edition

log = logging.getLogger("portfyl.turnstile")

SECRET_ENV = "PORTFYL_TURNSTILE_SECRET"
DISABLED_ENV = "PORTFYL_TURNSTILE_DISABLED"
TEST_KEYS_ENV = "PORTFYL_TURNSTILE_TEST_KEYS"
APP_URL_ENV = "PORTFYL_APP_URL"

SIGNUP_ACTION = "signup"
SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TIMEOUT = httpx.Timeout(5.0, connect=3.0)
CSP_SOURCE = "https://challenges.cloudflare.com"

_DUMMY_SECRET_PREFIXES = ("1x0000", "2x0000", "3x0000")
_MAX_TOKEN_LENGTH = 2048  # Cloudflare's documented maximum

Mode = Literal["on", "off", "test"]


@dataclass(frozen=True)
class TurnstileConfig:
    mode: Mode
    secret: str | None = None
    hostname: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str], edition: Edition) -> "TurnstileConfig":
        if edition is not Edition.CLOUD:
            return cls(mode="off")

        secret = env.get(SECRET_ENV, "").strip()
        disabled = env.get(DISABLED_ENV, "").strip() == "1"
        if secret and disabled:
            raise RuntimeError(
                f"{SECRET_ENV} and {DISABLED_ENV}=1 are both set; choose one"
            )
        if not secret:
            if not disabled:
                raise RuntimeError(
                    f"{SECRET_ENV} is required in the cloud edition "
                    f"(or set {DISABLED_ENV}=1 to run without the sign-up bot check)"
                )
            log.warning("Turnstile is disabled (%s=1): new sign-ups are not bot-checked", DISABLED_ENV)
            return cls(mode="off")

        if secret.startswith(_DUMMY_SECRET_PREFIXES):
            if env.get(TEST_KEYS_ENV, "").strip() != "1":
                raise RuntimeError(
                    f"{SECRET_ENV} is a Cloudflare dummy key; that needs {TEST_KEYS_ENV}=1"
                )
            return cls(mode="test", secret=secret)

        hostname = urlsplit(env.get(APP_URL_ENV, "").strip()).hostname
        if not hostname:
            raise RuntimeError(f"{APP_URL_ENV} is required when {SECRET_ENV} is set")
        return cls(mode="on", secret=secret, hostname=hostname.lower())


def verify_signup_token(
    config: TurnstileConfig,
    token: object,
    *,
    remote_ip: str | None,
    client: httpx.Client | None = None,
) -> str | None:
    """`None` when the token is valid, else one of `"missing_token"`,
    `"rejected"`, `"wrong_action"`, `"wrong_hostname"`, `"unavailable"`
    (timeout, network error or a Cloudflare-side failure).

    In `test` mode (dummy keys) the action and hostname are not compared.
    """
    if config.mode == "off":
        return None
    if not isinstance(token, str) or not token.strip():
        return "missing_token"
    if len(token) > _MAX_TOKEN_LENGTH:
        return "rejected"

    data = {"secret": config.secret or "", "response": token}
    if remote_ip:
        data["remoteip"] = remote_ip

    owned = client is None
    http = client or httpx.Client(timeout=TIMEOUT)
    try:
        response = http.post(SITEVERIFY_URL, data=data, timeout=TIMEOUT)
        response.raise_for_status()
        body = response.json()
    except (httpx.HTTPError, ValueError):
        return "unavailable"
    finally:
        if owned:
            http.close()

    if not isinstance(body, dict):
        return "unavailable"
    if body.get("success") is not True:
        codes = body.get("error-codes")
        if isinstance(codes, list) and "internal-error" in codes:
            return "unavailable"
        return "rejected"
    if config.mode == "test":
        return None
    if body.get("action") != SIGNUP_ACTION:
        return "wrong_action"
    hostname = body.get("hostname")
    if not isinstance(hostname, str) or hostname.lower() != config.hostname:
        return "wrong_hostname"
    return None


def csp_enabled(env: Mapping[str, str]) -> bool:
    """True when the SPA may load Turnstile: cloud edition with a secret."""
    edition = (env.get("PORTFYL_EDITION") or "").strip().lower()
    return edition == "cloud" and bool(env.get(SECRET_ENV, "").strip())


def health_check(config: TurnstileConfig) -> dict:
    return {"status": {"on": "ok", "test": "test", "off": "disabled"}[config.mode]}
