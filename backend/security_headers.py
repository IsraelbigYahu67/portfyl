"""Content-Security-Policy and related headers for rendered SPA HTML. See
docs/superpowers/plans/2026-09-19-portfyl-activation-analytics.md Task 7 for
the approved policy text -- only PostHog's EU ingestion/asset hosts, plus the
Firebase/Google and Sentry hosts the app already depends on, are allowed in
connect-src."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_CSP_DIRECTIVES = (
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self' https://eu.i.posthog.com https://eu-assets.i.posthog.com "
    "https://*.googleapis.com https://*.firebaseio.com https://*.ingest.sentry.io",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
)


def build_content_security_policy() -> str:
    return "; ".join(_CSP_DIRECTIVES)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Stamps the approved CSP plus X-Content-Type-Options/Referrer-Policy on
    HTML responses only -- JSON API responses and static assets (images,
    fonts, etc.) are left untouched. Any pre-existing Content-Security-Policy
    header is replaced, not appended to."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("text/html"):
            response.headers["Content-Security-Policy"] = build_content_security_policy()
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
