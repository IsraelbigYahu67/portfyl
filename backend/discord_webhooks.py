"""Validation of user-supplied Discord webhook URLs.

The backend POSTs to whatever URL a workspace stores, so an unchecked value is
a server-side request forgery primitive (internal hosts, cloud metadata, other
tenants' services). Only the real Discord webhook endpoints are accepted, and
the check is repeated right before every outbound request because rows stored
before this validator existed may still hold arbitrary URLs.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode, urlsplit, parse_qsl

ALLOWED_HOSTS = frozenset({
    "discord.com",
    "discordapp.com",
    "ptb.discord.com",
    "canary.discord.com",
})
ALLOWED_QUERY_KEYS = frozenset({"wait", "thread_id"})

# /api/webhooks/{id}/{token} or /api/v{N}/webhooks/{id}/{token}; ASCII only.
_PATH_RE = re.compile(r"/api(?:/v[0-9]+)?/webhooks/[0-9]+/[A-Za-z0-9_-]+", re.ASCII)
_QUERY_VALUE_RE = re.compile(r"[A-Za-z0-9_.-]*", re.ASCII)
_FORBIDDEN_CHARS_RE = re.compile(r"[\x00-\x20\x7f\\]")

EXPECTED_FORMAT = "https://discord.com/api/webhooks/<id>/<token>"


class InvalidWebhookUrl(ValueError):
    """The URL is not a Discord webhook endpoint. The message never contains
    the URL itself (it embeds a secret token) so it is safe to log and return."""


def validate_webhook_url(url: str) -> str:
    """Return the normalized webhook URL or raise InvalidWebhookUrl."""
    if not isinstance(url, str):
        raise InvalidWebhookUrl("Webhook URL must be a string")
    url = url.strip()
    if not url or _FORBIDDEN_CHARS_RE.search(url):
        raise InvalidWebhookUrl(f"Invalid Discord webhook URL, expected {EXPECTED_FORMAT}")

    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise InvalidWebhookUrl(f"Invalid Discord webhook URL, expected {EXPECTED_FORMAT}") from None

    if parts.scheme != "https":
        raise InvalidWebhookUrl("Discord webhook URL must use https")
    host = (parts.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise InvalidWebhookUrl("Discord webhook URL must point to discord.com or discordapp.com")
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise InvalidWebhookUrl("Discord webhook URL must not contain credentials")
    if port not in (None, 443):
        raise InvalidWebhookUrl("Discord webhook URL must not specify a port")
    if parts.fragment or "#" in url:
        raise InvalidWebhookUrl("Discord webhook URL must not contain a fragment")
    if not _PATH_RE.fullmatch(parts.path):
        raise InvalidWebhookUrl(f"Invalid Discord webhook URL, expected {EXPECTED_FORMAT}")

    query = ""
    if parts.query:
        try:
            pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
        except ValueError:
            raise InvalidWebhookUrl("Discord webhook URL has a malformed query string") from None
        for key, value in pairs:
            if key not in ALLOWED_QUERY_KEYS or not _QUERY_VALUE_RE.fullmatch(value):
                raise InvalidWebhookUrl("Discord webhook URL only allows the wait and thread_id query parameters")
        query = "?" + urlencode(pairs)

    return f"https://{host}{parts.path}{query}"
