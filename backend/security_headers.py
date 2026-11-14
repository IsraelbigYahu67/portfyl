"""Content-Security-Policy and related headers for rendered SPA HTML. See
docs/superpowers/plans/2026-09-19-portfyl-activation-analytics.md Task 7 for
the approved policy text -- only PostHog's EU ingestion/asset hosts, plus the
Firebase/Google and Sentry hosts the app already depends on, are allowed in
connect-src.

Google sign-in (docs/superpowers/plans/2026-10-12-portfyl-google-sign-in.md)
opens Google's own popup through Google Identity Services, whose script,
styles, frames and calls all live under https://accounts.google.com/gsi/.
They are allowed only when PORTFYL_FIREBASE_AUTH_DOMAIN holds a valid bare
hostname; otherwise the policy stays at its strict default and the popup flow
simply cannot start (fail closed). The variable is only this on/off switch
now: its hostname was the Firebase popup's iframe host until 2026-11-14 and is
no longer put into the policy."""
from __future__ import annotations

import os
import re
from collections.abc import Mapping

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

AUTH_DOMAIN_ENV = "PORTFYL_FIREBASE_AUTH_DOMAIN"
# The four sources Google documents for Google Identity Services under a CSP.
GOOGLE_IDENTITY_SCRIPT = "https://accounts.google.com/gsi/client"
GOOGLE_IDENTITY_STYLE = "https://accounts.google.com/gsi/style"
GOOGLE_IDENTITY_PATH = "https://accounts.google.com/gsi/"

# A bare DNS hostname with at least two labels: no scheme, port, path,
# wildcard, whitespace, or CSP punctuation can pass.
_HOSTNAME_RE = re.compile(
    r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)


def firebase_auth_domain(env: Mapping[str, str] | None = None) -> str | None:
    source = os.environ if env is None else env
    value = (source.get(AUTH_DOMAIN_ENV) or "").strip().lower()
    return value if _HOSTNAME_RE.fullmatch(value) else None


def _frame_ancestors(env: Mapping[str, str] | None) -> str:
    source = os.environ if env is None else env
    edition = (source.get("PORTFYL_EDITION") or "").strip().lower()
    return "'self'" if edition == "local" else "'none'"


def build_content_security_policy(env: Mapping[str, str] | None = None) -> str:
    google_sign_in = firebase_auth_domain(env) is not None
    script_src = "script-src 'self'"
    style_src = "style-src 'self' 'unsafe-inline'"
    connect_src = (
        "connect-src 'self' https://eu.i.posthog.com https://eu-assets.i.posthog.com "
        "https://*.googleapis.com https://*.firebaseio.com https://*.ingest.sentry.io"
    )
    if google_sign_in:
        script_src += f" {GOOGLE_IDENTITY_SCRIPT}"
        style_src += f" {GOOGLE_IDENTITY_STYLE}"
        connect_src += f" {GOOGLE_IDENTITY_PATH}"
    directives = [
        "default-src 'self'",
        script_src,
        style_src,
        "img-src 'self' data: blob:",
        "font-src 'self' data:",
        connect_src,
    ]
    if google_sign_in:
        directives.append(f"frame-src {GOOGLE_IDENTITY_PATH}")
    directives += [
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        # The local edition frames itself for the desktop mobile-layout
        # preview; anything but an explicit "local" edition stays unframeable.
        f"frame-ancestors {_frame_ancestors(env)}",
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
