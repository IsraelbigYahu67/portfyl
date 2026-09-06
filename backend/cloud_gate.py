"""The cloud-only global HTTP gate: trusted-edge verification followed by
the global per-IP rate limit, for every /api and /api/* request. Edge
verification runs unconditionally, including for OPTIONS -- only the
rate-limit consumption step is skipped for OPTIONS, so a bare OPTIONS
request without a valid edge token still gets 403'd rather than passing
through uncounted and unauthenticated. (Genuine CORS preflight never
reaches this middleware at all: CORSMiddleware, registered afterwards in
main.py so it wraps this middleware, answers those directly.) Registered
in main.py *before* CORSMiddleware's own app.add_middleware() call so this
middleware ends up more inner than CORS in Starlette's wrap order --
CORSMiddleware then still decorates this middleware's own direct 400/403/
429/503 responses. See
docs/superpowers/specs/2026-09-05-portfyl-rate-limiting-design.md."""
from __future__ import annotations

import logging

from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

import edge_trust
import rate_limit

log = logging.getLogger("portfyl.cloud_gate")


class CloudApiGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if not (path == "/api" or path.startswith("/api/")):
            return await call_next(request)

        try:
            edge_trust.verify_edge_token(request)
        except edge_trust.UntrustedEdge:
            return edge_trust.untrusted_edge_response()

        if request.method == "OPTIONS":
            return await call_next(request)

        try:
            ip = rate_limit.client_ip(request)
        except rate_limit.InvalidClientIp as exc:
            return rate_limit.invalid_client_ip_response(exc)

        try:
            await run_in_threadpool(
                rate_limit.consume_rate_limit,
                rule=rate_limit.RATE_LIMIT_RULES["global"],
                identity=ip,
            )
        except rate_limit.RateLimitExceeded as exc:
            log.info("rate_limit_exceeded rule=%s retry_after=%s", exc.rule_name, exc.retry_after_seconds)
            return rate_limit.rate_limit_exceeded_response(exc)
        except rate_limit.RateLimitUnavailable as exc:
            log.error("rate_limit_error rule=%s exception_type=%s", exc.rule_name, exc.original_exception_type)
            return rate_limit.rate_limit_unavailable_response(exc)

        return await call_next(request)
