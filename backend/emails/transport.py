"""E-mail transports: Brevo over HTTP (with a health flag) and a console stand-in.

Nothing here may put an API key, an e-mail address or a response body into an
exception message or a log line. ``EmailSendError`` carries a reason code only.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Mapping, Protocol, TextIO
from urllib.parse import urlsplit

import httpx

from edition import Edition

logger = logging.getLogger("portfyl.emails.transport")

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
FAILURE_THRESHOLD = 3
COOLDOWN_SECONDS = 300
_TIMEOUT = httpx.Timeout(5.0, connect=3.0)
_AUTH_FAILURE_STATUSES = frozenset({401, 403})

_DEFAULT_SENDER_EMAIL = "noreply@mail.portfyl.com"
_DEFAULT_SENDER_NAME = "Portfyl"
_DEFAULT_REPLY_TO = "support@portfyl.com"
_LOCAL_APP_URL = "http://localhost:5173"


class EmailSendError(RuntimeError):
    """A send failed. The message is a short reason code, never a detail."""


class RenderedEmailLike(Protocol):
    subject: str
    html: str
    text: str


@dataclass(frozen=True)
class MailerSettings:
    api_key: str | None
    sender_email: str
    sender_name: str
    reply_to: str
    app_url: str
    console: bool


def _setting(env: Mapping[str, str], name: str, default: str = "") -> str:
    value = env.get(name)
    if value is None:
        return default
    return str(value).strip() or default


def _valid_app_url(url: str, *, require_https: bool) -> bool:
    try:
        parts = urlsplit(url)
        host = parts.hostname
        parts.port  # noqa: B018 - raises ValueError on a malformed port
    except ValueError:
        return False
    schemes = {"https"} if require_https else {"http", "https"}
    return parts.scheme in schemes and bool(host)


def load_mailer_settings(env: Mapping[str, str], edition: Edition) -> MailerSettings | None:
    """Read the e-mail settings. ``None`` means the mailer is off.

    Never raises: a missing or wrong value must not stop the service starting.
    A configured key with unusable settings logs one ERROR (without the key).
    """
    try:
        api_key = _setting(env, "PORTFYL_BREVO_API_KEY") or None
        sender_email = _setting(env, "PORTFYL_EMAIL_FROM", _DEFAULT_SENDER_EMAIL)
        sender_name = _setting(env, "PORTFYL_EMAIL_FROM_NAME", _DEFAULT_SENDER_NAME)
        reply_to = _setting(env, "PORTFYL_EMAIL_REPLY_TO", _DEFAULT_REPLY_TO)
        app_url = _setting(env, "PORTFYL_EMAIL_APP_URL").rstrip("/")

        if edition is Edition.CLOUD:
            console = False
            if api_key is None:
                return None
            if not _valid_app_url(app_url, require_https=True):
                logger.error("PORTFYL_BREVO_API_KEY is set but PORTFYL_EMAIL_APP_URL is missing or not an "
                             "https URL; the mailer stays off")
                return None
        else:
            console = _setting(env, "PORTFYL_EMAIL_TRANSPORT").lower() == "console"
            if not console and api_key is None:
                return None
            app_url = app_url or _LOCAL_APP_URL
            if not _valid_app_url(app_url, require_https=False):
                logger.error("PORTFYL_EMAIL_APP_URL is not an http(s) URL; the mailer stays off")
                return None

        return MailerSettings(api_key=api_key, sender_email=sender_email, sender_name=sender_name,
                              reply_to=reply_to, app_url=app_url, console=console)
    except Exception:  # noqa: BLE001 - settings loading must never break startup
        logger.error("E-mail settings could not be read; the mailer stays off")
        return None


class EmailTransport(Protocol):
    def available(self) -> bool: ...

    def send(self, *, to: str, email: RenderedEmailLike, tag: str) -> str | None:
        """Send one e-mail. Returns the provider's message id, if it gave one."""


class BrevoTransport:
    """Posts to Brevo's transactional API. Connect 3 s, 5 s otherwise, no retry.

    Health flag: after a 401/403 or ``FAILURE_THRESHOLD`` failed sends in a row
    the transport reports itself unavailable for ``COOLDOWN_SECONDS``. The state
    is per instance and in memory; endpoints run in the threadpool, hence the lock.
    """

    def __init__(
        self,
        settings: MailerSettings,
        *,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._client = client if client is not None else httpx.Client(timeout=_TIMEOUT)
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = 0
        self._unavailable_until: float | None = None

    def available(self) -> bool:
        with self._lock:
            if self._unavailable_until is None:
                return True
            if self._clock() >= self._unavailable_until:
                self._unavailable_until = None
                self._failures = 0
                return True
            return False

    def send(self, *, to: str, email: RenderedEmailLike, tag: str) -> str | None:
        settings = self._settings
        payload = {
            "sender": {"email": settings.sender_email, "name": settings.sender_name},
            "to": [{"email": to}],
            "replyTo": {"email": settings.reply_to, "name": settings.sender_name},
            "subject": email.subject,
            "htmlContent": email.html,
            "textContent": email.text,
            "tags": [tag],
        }
        headers = {"api-key": settings.api_key or "", "accept": "application/json"}
        try:
            response = self._client.post(BREVO_URL, json=payload, headers=headers, timeout=_TIMEOUT)
        except httpx.TimeoutException:
            self._record_failure("brevo_timeout")
            raise EmailSendError("brevo_timeout") from None
        except httpx.HTTPError:
            self._record_failure("brevo_network")
            raise EmailSendError("brevo_network") from None

        if response.status_code != 201:
            reason = f"brevo_http_{response.status_code}"
            self._record_failure(reason, auth=response.status_code in _AUTH_FAILURE_STATUSES)
            raise EmailSendError(reason)

        self._record_success()
        return _message_id(response)

    def _record_success(self) -> None:
        with self._lock:
            self._failures = 0
            self._unavailable_until = None

    def _record_failure(self, reason: str, *, auth: bool = False) -> None:
        with self._lock:
            self._failures += 1
            if not (auth or self._failures >= FAILURE_THRESHOLD):
                return
            self._unavailable_until = self._clock() + COOLDOWN_SECONDS
            self._failures = 0
        logger.error("Mailer switched off for %s s (%s)", COOLDOWN_SECONDS, reason)


def _message_id(response: httpx.Response) -> str | None:
    try:
        body = response.json()
    except ValueError:
        return None
    message_id = body.get("messageId") if isinstance(body, dict) else None
    return message_id if isinstance(message_id, str) and message_id else None


class ConsoleTransport:
    """Prints the e-mail instead of sending it. Outside the cloud edition only."""

    def __init__(self, *, out: TextIO | None = None) -> None:
        self._out = out if out is not None else sys.stdout

    def available(self) -> bool:
        return True

    def send(self, *, to: str, email: RenderedEmailLike, tag: str) -> str | None:
        print(f"--- e-mail [{tag}] to {to} ---\nSubject: {email.subject}\n\n{email.text}\n---",
              file=self._out, flush=True)
        return None
