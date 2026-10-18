"""Cloud-only fixed-window API rate limiting. See
docs/superpowers/specs/2026-09-05-portfyl-rate-limiting-design.md.

Other modules must read RATE_LIMIT_RULES/KEY_SECRET via a qualified
attribute lookup (`rate_limit.RATE_LIMIT_RULES[...]`) at call time, never
via `from rate_limit import RATE_LIMIT_RULES` -- the latter freezes a stale
reference at import time and breaks test monkeypatching of these globals.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Literal, Mapping

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from database import SessionLocal
from edition import Edition, edition_from_env
from tenancy import RequestContext, get_request_context

_RULE_ENV_VARS: dict[str, tuple[str, str]] = {
    "global": ("RATE_LIMIT_GLOBAL_LIMIT", "RATE_LIMIT_GLOBAL_WINDOW_SECONDS"),
    "auth_session": ("RATE_LIMIT_AUTH_SESSION_LIMIT", "RATE_LIMIT_AUTH_SESSION_WINDOW_SECONDS"),
    "broker_sync": ("RATE_LIMIT_BROKER_SYNC_LIMIT", "RATE_LIMIT_BROKER_SYNC_WINDOW_SECONDS"),
}


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    limit: int
    window_seconds: int

    def __post_init__(self) -> None:
        if self.limit <= 0:
            raise ValueError(f"RateLimitRule {self.name!r} limit must be positive, got {self.limit}")
        if self.window_seconds <= 0:
            raise ValueError(
                f"RateLimitRule {self.name!r} window_seconds must be positive, got {self.window_seconds}"
            )


def _require_positive_int(env: Mapping[str, str], var_name: str) -> int:
    raw = env.get(var_name, "").strip()
    if not raw:
        raise RuntimeError(f"{var_name} is required in the cloud edition and must be a positive integer")
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{var_name} must be a positive integer, got {raw!r}") from exc
    if value <= 0:
        raise RuntimeError(f"{var_name} must be a positive integer, got {raw!r}")
    return value


def load_rate_limit_rules(env: Mapping[str, str]) -> dict[str, RateLimitRule]:
    """Parse and validate all four rules. Cloud requires every one of the
    eight env vars to be an explicit positive integer -- there is no
    zero-means-disabled behavior and no silent fallback for a blank value."""
    return {
        name: RateLimitRule(
            name=name,
            limit=_require_positive_int(env, limit_var),
            window_seconds=_require_positive_int(env, window_var),
        )
        for name, (limit_var, window_var) in _RULE_ENV_VARS.items()
    }


def load_key_secret(env: Mapping[str, str]) -> bytes:
    raw = env.get("RATE_LIMIT_KEY_SECRET", "").strip()
    if not raw:
        raise RuntimeError("RATE_LIMIT_KEY_SECRET is required in the cloud edition and must not be blank")
    return raw.encode("utf-8")


RATE_LIMIT_RULES: dict[str, RateLimitRule] = (
    load_rate_limit_rules(os.environ) if edition_from_env(os.environ) is Edition.CLOUD else {}
)

KEY_SECRET: bytes | None = (
    load_key_secret(os.environ) if edition_from_env(os.environ) is Edition.CLOUD else None
)


_MAX_IP_TEXT_LENGTH = 45  # longest valid IPv6 textual form, e.g. an IPv4-mapped address
_CF_CONNECTING_IP_HEADER = "CF-Connecting-IP"


class InvalidClientIp(Exception):
    pass


class RateLimitExceeded(Exception):
    def __init__(self, rule_name: str, retry_after_seconds: int):
        super().__init__(f"{rule_name}: retry after {retry_after_seconds}s")
        self.rule_name = rule_name
        self.retry_after_seconds = retry_after_seconds


class RateLimitUnavailable(Exception):
    def __init__(self, rule_name: str, original_exception_type: str):
        super().__init__(f"{rule_name}: {original_exception_type}")
        self.rule_name = rule_name
        self.original_exception_type = original_exception_type


def client_ip(request: Request) -> str:
    """Validate and canonicalize the trusted CF-Connecting-IP value. Callers
    must only trust this after edge_trust.verify_edge_token has already
    succeeded for this request."""
    values = request.headers.getlist(_CF_CONNECTING_IP_HEADER)
    if len(values) != 1:
        raise InvalidClientIp()
    raw = values[0].strip()
    if not raw or len(raw) > _MAX_IP_TEXT_LENGTH:
        raise InvalidClientIp()
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError as exc:
        raise InvalidClientIp() from exc


_BUCKET_KEY_VERSION = "1"


def _encode_field(value: str) -> bytes:
    data = value.encode("utf-8")
    return len(data).to_bytes(4, "big") + data


def _bucket_key(*, rule_name: str, identity: str, window_index: int) -> str:
    message = b"".join(
        _encode_field(field)
        for field in (_BUCKET_KEY_VERSION, rule_name, identity, str(window_index))
    )
    return hmac.new(KEY_SECRET, message, hashlib.sha256).hexdigest()


_UPSERT_SQL = text(
    """
    INSERT INTO rate_limit_buckets (key, count, expires_at)
    VALUES (:key, 1, :expires_at)
    ON CONFLICT (key) DO UPDATE
      SET count = CASE
        WHEN rate_limit_buckets.count < :limit_plus_one
          THEN rate_limit_buckets.count + 1
        ELSE rate_limit_buckets.count
      END
    RETURNING count
    """
)


def consume_rate_limit(*, rule: RateLimitRule, identity: str, now: datetime | None = None) -> None:
    """Hash the bucket identity, perform and commit one isolated upsert on a
    brand-new SessionLocal(), then raise if the committed count exceeds the
    rule's limit. Never touches a route's own DB session."""
    captured_now = now or datetime.now(timezone.utc)
    window_index = int(captured_now.timestamp() // rule.window_seconds)
    expires_at = datetime.fromtimestamp((window_index + 1) * rule.window_seconds, tz=timezone.utc)
    key = _bucket_key(rule_name=rule.name, identity=identity, window_index=window_index)

    session = SessionLocal()
    try:
        try:
            count = session.execute(
                _UPSERT_SQL,
                {"key": key, "expires_at": expires_at, "limit_plus_one": rule.limit + 1},
            ).scalar_one()
            session.commit()
        except SQLAlchemyError as exc:
            session.rollback()
            raise RateLimitUnavailable(rule.name, type(exc).__name__) from exc
    finally:
        session.close()

    if count > rule.limit:
        retry_after = max(1, math.ceil((expires_at - captured_now).total_seconds()))
        raise RateLimitExceeded(rule.name, retry_after)


def rate_limit(rule_name: str, *, by: Literal["ip", "workspace"]) -> Callable:
    """Dependency factory shaped like entitlements.require_capability. The
    rule is looked up from RATE_LIMIT_RULES (a bare module-global reference,
    always fresh -- see the module docstring) inside the returned
    dependency, never at rate_limit() call time, so this factory can be used
    identically in the decorator of every edition without RATE_LIMIT_RULES
    needing to already be populated at router-import time."""
    if by == "ip":
        def dependency(request: Request) -> None:
            if request.app.state.portfyl_edition is not Edition.CLOUD:
                return
            consume_rate_limit(rule=RATE_LIMIT_RULES[rule_name], identity=client_ip(request))
        return dependency
    if by == "workspace":
        def dependency(
            request: Request,
            context: RequestContext = Depends(get_request_context),
        ) -> None:
            if request.app.state.portfyl_edition is not Edition.CLOUD:
                return
            consume_rate_limit(rule=RATE_LIMIT_RULES[rule_name], identity=str(context.workspace.id))
        return dependency
    raise ValueError(f"Unknown rate_limit 'by': {by!r}")


def rate_limit_exceeded_response(exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        {"code": "rate_limit_exceeded", "rule": exc.rule_name},
        status_code=429,
        headers={"Retry-After": str(exc.retry_after_seconds), "Cache-Control": "no-store"},
    )


def rate_limit_exceeded_handler(_request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return rate_limit_exceeded_response(exc)


def rate_limit_unavailable_response(_exc: RateLimitUnavailable) -> JSONResponse:
    return JSONResponse(
        {"code": "rate_limiter_unavailable"},
        status_code=503,
        headers={"Retry-After": "1", "Cache-Control": "no-store"},
    )


def rate_limit_unavailable_handler(_request: Request, exc: RateLimitUnavailable) -> JSONResponse:
    return rate_limit_unavailable_response(exc)


def invalid_client_ip_response(_exc: InvalidClientIp) -> JSONResponse:
    return JSONResponse(
        {"code": "invalid_client_ip"},
        status_code=400,
        headers={"Cache-Control": "no-store"},
    )


def invalid_client_ip_handler(_request: Request, exc: InvalidClientIp) -> JSONResponse:
    return invalid_client_ip_response(exc)
