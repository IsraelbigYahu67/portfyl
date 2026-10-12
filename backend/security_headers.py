"""Content-Security-Policy and related headers for rendered SPA HTML. See
docs/superpowers/plans/2026-09-19-portfyl-activation-analytics.md Task 7 for
the approved policy text -- only PostHog's EU ingestion/asset hosts, plus the
Firebase/Google and Sentry hosts the app already depends on, are allowed in
connect-src.

Google sign-in (docs/superpowers/plans/2026-10-12-portfyl-google-sign-in.md)
uses Firebase's popup flow, which loads Google's gapi loader from
https://apis.google.com and embeds a hidden iframe served from the Firebase
auth domain. Both are allowed only when PORTFYL_FIREBASE_AUTH_DOMAIN holds a
valid bare hostname; otherwise the policy stays at its strict default and the
popup flow simply cannot start (fail closed)."""
from __future__ import annotations

import os
import re
from collections.abc import Mapping

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

AUTH_DOMAIN_ENV = "PORTFYL_FIREBASE_AUTH_DOMAIN"
GOOGLE_SIGN_IN_SCRIPT_HOST = "https://apis.google.com"

# A bare DNS hostname with at least two labels: no scheme, port, path,
# wildcard, whitespace, or CSP punctuation can pass.
_HOSTNAME_RE = re.compile(
    r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)


def firebase_auth_domain(env: Mapping[str, str] | None = None) -> str | None:
    source = os.environ if env is None else env
    value = (source.get(AUTH_DOMAIN_ENV) or "").strip().lower()
    return value if _HOSTNAME_RE.fullmatch(value) else None


def build_content_security_policy(env: Mapping[str, str] | None = None) -> str:
    auth_domain = firebase_auth_domain(env)
    script_src = "script-src 'self'"
    if auth_domain:
        script_src += f" {GOOGLE_SIGN_IN_SCRIPT_HOST}"
    directives = [
        "default-src 'self'",
        script_src,
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        "connect-src 'self' https://eu.i.posthog.com https://eu-assets.i.posthog.com "
        "https://*.googleapis.com https://*.firebaseio.com https://*.ingest.sentry.io",
    ]
    if auth_domain:
        directives.append(f"frame-src https://{auth_domain}")
    directives += [
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
    return "; ".join(directives)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Stamps the approved CSP plus X-Content-Type-Options/Referrer-Policy on
    HTML responses only -- JSON API responses and static assets (images,
    fonts, etc.) are left untouched. Any pre-existing Content-Security-Policy
    header is replaced, not appended to. The policy is built once, when the
    middleware is constructed, not per request."""

    def __init__(self, app, *, env: Mapping[str, str] | None = None) -> None:
        super().__init__(app)
        self._policy = build_content_security_policy(env)

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("text/html"):
            response.headers["Content-Security-Policy"] = self._policy
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
