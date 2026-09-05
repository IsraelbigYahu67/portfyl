"""Structured logging: secret redaction + request/job correlation ids.

:func:`configure_logging` is called once, at import time from main.py,
before any other logger emits. It installs one root handler that:

* stamps every record with the current request/job correlation id (a
  ``contextvars.ContextVar`` set by main.py's request middleware and by
  each background-job tick -- default ``"-"`` outside of either);
* redacts known SECRET SHAPES from the final formatted line -- Discord
  webhook tokens, ``Authorization`` header values, and Portfyl session/CSRF
  cookie values. This is pattern-based, not literal-value-based: nothing in
  the logging system is ever told which live string is "the" secret to
  scrub, so redaction has to recognize secrets by their shape in whatever
  gets logged (an error message, a repr'd request, a stray debug print).
  Broker API keys and the DeepSeek key have no recognizable shape of their
  own, so the real defense for those is simply never logging the decrypted
  value in the first place (see secrets_crypto.py / models.py) -- this
  module is the second, belt-and-suspenders layer for the handful of
  secrets that DO have a recognizable shape once they leak into a message.
"""
from __future__ import annotations

import contextvars
import logging
import os
import re

correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "correlation_id", default="-"
)

_REDACTION_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Discord webhook URL: keep the host/path shape, redact id + token.
    (re.compile(r"(discord(?:app)?\.com/api/webhooks/)\d+/[A-Za-z0-9_\-]+"), r"\1[REDACTED]"),
    # Authorization header values: "Authorization: Bearer <token>" / "Basic <token>"
    # / a bare Trading 212-style key with no scheme prefix.
    (re.compile(r"(Authorization[\"'\s:=]+)(Bearer|Basic)\s+\S+", re.IGNORECASE), r"\1\2 [REDACTED]"),
    # Portfyl session / CSRF cookie values.
    (re.compile(r"((?:__Host-)?portfyl_session=)[^;\s]+"), r"\1[REDACTED]"),
    (re.compile(r"(X-CSRF-Token[\"'\s:=]+)\S+", re.IGNORECASE), r"\1[REDACTED]"),
]


def redact(text: str) -> str:
    """Apply every known secret-shape pattern to `text`. Exposed directly so
    non-logging call sites (e.g. a future error-monitoring integration) can
    reuse the same rules."""
    for pattern, replacement in _REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class _CorrelationIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get()
        return True


class RedactingFormatter(logging.Formatter):
    """Redacts the fully rendered line rather than mutating record.msg/args
    -- msg/args go through %-formatting inside logging internals, and a
    redacted replacement string containing a stray literal "%" would raise
    there. Post-processing the final string sidesteps that entirely."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


_CONFIGURED = False


def configure_logging(*, force: bool = False) -> None:
    """Idempotent -- safe to call multiple times (main.py calls it once at
    import time). A no-op under PORTFYL_TESTING unless `force=True`: pytest
    manages its own log capture/formatting on the root logger, and clearing
    its handlers here would silently break `caplog`-based assertions and
    on-failure log output in every other test module. Tests that want to
    exercise this module's actual formatting call it with force=True and
    restore logging state themselves (see test_logging_setup.py)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    if os.environ.get("PORTFYL_TESTING") == "1" and not force:
        return
    _CONFIGURED = True

    handler = logging.StreamHandler()
    handler.setFormatter(RedactingFormatter(
        "%(asctime)s %(levelname)s [%(correlation_id)s] %(name)s: %(message)s"
    ))
    handler.addFilter(_CorrelationIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
