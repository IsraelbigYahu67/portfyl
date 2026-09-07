"""Cloud-only fixed-window API rate limiting. See
docs/superpowers/specs/2026-09-05-portfyl-rate-limiting-design.md.

Other modules must read RATE_LIMIT_RULES/KEY_SECRET via a qualified
attribute lookup (`rate_limit.RATE_LIMIT_RULES[...]`) at call time, never
via `from rate_limit import RATE_LIMIT_RULES` -- the latter freezes a stale
reference at import time and breaks test monkeypatching of these globals.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from edition import Edition, edition_from_env

_RULE_ENV_VARS: dict[str, tuple[str, str]] = {
    "global": ("RATE_LIMIT_GLOBAL_LIMIT", "RATE_LIMIT_GLOBAL_WINDOW_SECONDS"),
    "auth_session": ("RATE_LIMIT_AUTH_SESSION_LIMIT", "RATE_LIMIT_AUTH_SESSION_WINDOW_SECONDS"),
    "broker_sync": ("RATE_LIMIT_BROKER_SYNC_LIMIT", "RATE_LIMIT_BROKER_SYNC_WINDOW_SECONDS"),
    "assistant_chat": ("RATE_LIMIT_ASSISTANT_CHAT_LIMIT", "RATE_LIMIT_ASSISTANT_CHAT_WINDOW_SECONDS"),
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
