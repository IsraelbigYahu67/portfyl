"""Best-effort account notices (wave 2): render one e-mail and hand it to Brevo.

``send_account_notice`` is called *after* the user's action is committed
(password change seen, deletion requested, purge). It must never fail, delay
beyond the transport's own 5 s timeout, or roll anything back, so it never
raises and only answers whether the provider accepted the message.

Rules this module keeps (see ``emails.transport`` for the same ones):

* No e-mail address, link, one-time code or key reaches a log line or an
  exception text. A line carries the kind, the language and a reason code or an
  exception *class name* only.
* A missing mailer, an unavailable transport (health flag) and a failing send
  all give ``False``; the first two make no outbound call at all.
* Plain ``def``; the one blocking call is ``transport.send`` (connect 3 s,
  5 s total). Do not call it from the event loop or while holding a database
  connection you could release.

This module must not import ``routers``: ``routers.auth`` will call it, and
``routers.auth_email`` imports ``routers.auth``. The mailer is duck-typed
(``.transport`` with ``available()`` and ``send()``); the default one is built
lazily, on first use, by a function-local import.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from datetime import date, datetime
from typing import Any, Mapping

from emails.catalog import EmailKind, format_date, format_datetime, normalize_language
from emails.render import render
from emails.transport import EmailSendError

logger = logging.getLogger("portfyl.emails.notify")

_SEND_REASON = re.compile(r"brevo_[a-z0-9_]{1,40}")

_default_lock = threading.Lock()
_default_mailer: Any = None
_default_resolved = False


def set_default_mailer(mailer: Any) -> None:
    """Share the application's mailer (``app.state.portfyl_mailer``) so that
    notices sent outside a request use the same transport, and with it the same
    health flag. ``None`` clears it; the next send builds one from the
    environment."""
    global _default_mailer, _default_resolved
    with _default_lock:
        _default_mailer = mailer
        _default_resolved = mailer is not None


def _resolve_default_mailer() -> Any:
    global _default_mailer, _default_resolved
    with _default_lock:
        if not _default_resolved:
            # Function-local on purpose: see the module docstring.
            from edition import edition_from_env
            from routers.auth_email import build_mailer

            _default_mailer = build_mailer(os.environ, edition_from_env(os.environ))
            _default_resolved = True
        return _default_mailer


def _error_code(exc: BaseException) -> str:
    """A loggable description of a failure: a Brevo reason code or a class
    name, never ``str(exc)`` of anything that could carry an address."""
    if isinstance(exc, EmailSendError):
        reason = str(exc)
        if _SEND_REASON.fullmatch(reason):
            return reason
    return type(exc).__name__


def _prepare_params(lang: str, params: Mapping[str, Any]) -> dict[str, str]:
    """Strings pass through. A ``date`` / ``datetime`` under ``date`` or
    ``datetime`` is formatted in ``lang`` (UTC), so callers never format."""
    out: dict[str, str] = {}
    for key, value in params.items():
        if key == "datetime" and isinstance(value, datetime):
            out[key] = format_datetime(value, lang)
        elif key == "date" and isinstance(value, (date, datetime)):
            out[key] = format_date(value, lang)
        else:
            out[key] = str(value)
    return out


def send_account_notice(
    kind: EmailKind,
    *,
    to: str,
    lang: str,
    params: Mapping[str, Any],
    action_url: str | None = None,
    mailer: Any = None,
) -> bool:
    """Render ``kind`` in ``lang`` and send it to ``to``. Never raises.

    Returns ``True`` only when the provider accepted the message. ``mailer``
    is the app's ``Mailer`` (anything with ``.transport``); ``None`` uses the
    process-wide default.
    """
    kind_name = kind.value if isinstance(kind, EmailKind) else "unknown"
    code = normalize_language(lang)
    try:
        resolved = mailer if mailer is not None else _resolve_default_mailer()
        if resolved is None:
            logger.info("account_notice kind=%s lang=%s outcome=mailer_off", kind_name, code)
            return False
        transport = resolved.transport
        if not transport.available():
            logger.info("account_notice kind=%s lang=%s outcome=unavailable", kind_name, code)
            return False
        rendered = render(
            kind, code, params=_prepare_params(code, params), action_url=action_url
        )
        message_id = transport.send(to=to, email=rendered, tag=kind.value)
    except Exception as exc:  # noqa: BLE001 - a notice must never break its caller
        logger.error(
            "account_notice kind=%s lang=%s outcome=failed error=%s",
            kind_name, code, _error_code(exc),
        )
        return False

    logger.info(
        "account_notice kind=%s lang=%s outcome=sent message_id=%s", kind_name, code, message_id
    )
    return True
