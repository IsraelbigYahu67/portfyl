"""Cloud-only origin-authentication contract: Cloudflare overwrites any
client-supplied value and injects a random Secret-Manager-held token into
`X-Portfyl-Edge-Token` only on requests it forwards to the origin. A valid
token proves a request came through the trusted edge before any IP-based
rate-limit state (rate_limit.py) is trusted or touched. See
docs/superpowers/specs/2026-09-05-portfyl-rate-limiting-design.md."""
from __future__ import annotations

import hmac
import os
from typing import Mapping

from fastapi import Request
from fastapi.responses import JSONResponse

from edition import Edition, edition_from_env

_EDGE_TOKEN_HEADER = "X-Portfyl-Edge-Token"


class UntrustedEdge(Exception):
    pass


def load_edge_token(env: Mapping[str, str]) -> str:
    token = env.get("PORTFYL_EDGE_TOKEN", "").strip()
    if not token:
        raise RuntimeError("PORTFYL_EDGE_TOKEN is required in the cloud edition and must not be blank")
    return token


EDGE_TOKEN: str | None = (
    load_edge_token(os.environ) if edition_from_env(os.environ) is Edition.CLOUD else None
)


def verify_edge_token(request: Request) -> None:
    values = request.headers.getlist(_EDGE_TOKEN_HEADER)
    if len(values) != 1 or EDGE_TOKEN is None or not hmac.compare_digest(values[0], EDGE_TOKEN):
        raise UntrustedEdge()


def untrusted_edge_response() -> JSONResponse:
    return JSONResponse(
        {"code": "untrusted_edge"},
        status_code=403,
        headers={"Cache-Control": "no-store"},
    )
