"""Sentry error monitoring -- opt-in via SENTRY_DSN, a no-op without it.

Sentry's own PII/body capture is left off (send_default_pii=False,
max_request_body_size="never") since request bodies can carry a BYOK broker/
LLM key or portfolio data. before_send additionally runs every exception
message, log message, and breadcrumb through logging_setup.redact() -- the
same secret-shape rules the log formatter uses -- as a third, belt-and-
suspenders layer on top of never logging decrypted secrets in the first
place (see logging_setup.py's module docstring, which named this as the
future integration those rules were exposed for).
"""
from __future__ import annotations

import os

import sentry_sdk

from logging_setup import redact


def _scrub_event(event: dict, hint: dict) -> dict:
    message = event.get("message")
    if isinstance(message, str):
        event["message"] = redact(message)
    logentry = event.get("logentry")
    if isinstance(logentry, dict) and isinstance(logentry.get("message"), str):
        logentry["message"] = redact(logentry["message"])
    for exc in (event.get("exception") or {}).get("values") or []:
        if isinstance(exc.get("value"), str):
            exc["value"] = redact(exc["value"])
    for crumb in (event.get("breadcrumbs") or {}).get("values") or []:
        if isinstance(crumb.get("message"), str):
            crumb["message"] = redact(crumb["message"])
    return event


def configure_sentry(*, environment: str) -> None:
    """Called once from main.py at import time, after configure_logging().
    No-op when SENTRY_DSN is unset, or under PORTFYL_TESTING (mirrors
    configure_logging()'s own test guard) so the fast unit suite never
    dials out or needs a fake DSN."""
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn or os.environ.get("PORTFYL_TESTING") == "1":
        return
    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("SENTRY_ENVIRONMENT", environment),
        release=os.environ.get("SENTRY_RELEASE"),
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0")),
        send_default_pii=False,
        max_request_body_size="never",
        before_send=_scrub_event,
    )
