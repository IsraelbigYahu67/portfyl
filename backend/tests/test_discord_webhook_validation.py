"""SSRF hardening for Discord webhooks (review 2026-10-14, finding N1): only
real Discord webhook URLs may be stored, and an invalid URL already in the
database must never receive a request."""
from __future__ import annotations

import asyncio
import logging
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException

from discord_webhooks import InvalidWebhookUrl, validate_webhook_url
from models import DiscordWebhook
from routers.discord import (
    WebhookCreate,
    WebhookTestMessage,
    WebhookUpdate,
    create_webhook,
    get_webhook,
    send_discord_notification,
    test_webhook as run_webhook_test,
    update_webhook,
)
from tests.helpers import TEST_WORKSPACE_ID

GOOD = "https://discord.com/api/webhooks/123456/abc_DEF-9"


@pytest.mark.parametrize("url", [
    GOOD,
    "https://discordapp.com/api/webhooks/123456/abc_DEF-9",
    "https://ptb.discord.com/api/webhooks/123456/abc",
    "https://canary.discord.com/api/webhooks/123456/abc",
    "https://discord.com/api/v10/webhooks/123456/abc",
    "https://discord.com/api/webhooks/123456/abc?wait=true",
    "https://discord.com/api/webhooks/123456/abc?thread_id=123",
    "https://discord.com/api/webhooks/123456/abc?wait=true&thread_id=123",
    "https://DISCORD.com:443/api/webhooks/123456/abc",
    "  https://discord.com/api/webhooks/123456/abc  ",
])
def test_accepts_real_discord_webhook_urls(url):
    assert validate_webhook_url(url).startswith("https://")


def test_normalizes_host_and_default_port():
    assert (validate_webhook_url("https://DISCORD.com:443/api/webhooks/1/x?wait=true")
            == "https://discord.com/api/webhooks/1/x?wait=true")


@pytest.mark.parametrize("url", [
    "http://discord.com/api/webhooks/123456/abc",
    "ftp://discord.com/api/webhooks/123456/abc",
    "//discord.com/api/webhooks/123456/abc",
    "discord.com/api/webhooks/123456/abc",
    "https://evil.com/api/webhooks/123456/abc",
    "https://discord.com.evil.com/api/webhooks/123456/abc",
    "https://evildiscord.com/api/webhooks/123456/abc",
    "https://sub.discord.com/api/webhooks/123456/abc",
    "https://discord.com@evil.com/api/webhooks/123456/abc",
    "https://user:pw@discord.com/api/webhooks/123456/abc",
    "https://evil.com#@discord.com/api/webhooks/123456/abc",
    "https://evil.com\\@discord.com/api/webhooks/123456/abc",
    "https://10.0.0.5/api/webhooks/123456/abc",
    "https://169.254.169.254/api/webhooks/123456/abc",
    "https://[::1]/api/webhooks/123456/abc",
    "https://2130706433/api/webhooks/123456/abc",
    "https://localhost/api/webhooks/123456/abc",
    "http://10.0.0.5/x?discord.com/api/webhooks",
    "https://discord.com:8080/api/webhooks/123456/abc",
    "https://discord.com:80/api/webhooks/123456/abc",
    "https://discord.com:notaport/api/webhooks/123456/abc",
    "https://discord.com/api/webhooks/123456",
    "https://discord.com/api/webhooks/123456/",
    "https://discord.com/api/webhooks/",
    "https://discord.com/api/webhooks/abc/token",
    "https://discord.com/api/webhooks/123456/tok en",
    "https://discord.com/api/webhooks/123456/abc/slack",
    "https://discord.com/api/webhooks/123456/abc/extra",
    "https://discord.com/login",
    "https://discord.com/",
    "https://discord.com",
    "https://discord.com/x/api/webhooks/123456/abc",
    "https://discord.com/api/vX/webhooks/123456/abc",
    "https://discord.com/api/webhooks/123456/abc#frag",
    "https://discord.com/api/webhooks/123456/abc?wait=true#frag",
    "https://discord.com/api/webhooks/123456/abc?token=x",
    "https://discord.com/api/webhooks/123456/abc?wait=true&redirect=http://evil",
    "https://discord.com/api/webhooks/123456/abc?wait=http://evil.com/x",
    "https://discord.com/api/webhooks/123456/abc?wait",
    "https://discord.com/api/webhooks/123456/abc\nHost: evil.com",
    "https://discord.com/api/webhooks/123456/abc\x00",
    "",
    "   ",
])
def test_rejects_everything_else(url):
    with pytest.raises(InvalidWebhookUrl):
        validate_webhook_url(url)


def test_rejection_message_never_contains_the_url():
    secret = "https://evil.example/api/webhooks/123456/very-secret-token"
    with pytest.raises(InvalidWebhookUrl) as exc:
        validate_webhook_url(secret)
    assert "very-secret-token" not in str(exc.value)
    assert "evil.example" not in str(exc.value)


# --- router behaviour -------------------------------------------------------

def _store(db, pid, url):
    hook = DiscordWebhook(workspace_id=TEST_WORKSPACE_ID, portfolio_id=pid,
                          webhook_url=url)
    db.add(hook)
    db.commit()
    return hook


def test_create_rejects_invalid_url_and_stores_nothing(db_session, default_portfolio, request_context):
    with pytest.raises(HTTPException) as exc:
        create_webhook(WebhookCreate(webhook_url="http://10.0.0.5/x?discord.com/api/webhooks"),
                       default_portfolio, db_session, request_context)
    assert exc.value.status_code == 400
    assert db_session.query(DiscordWebhook).count() == 0


def test_create_stores_the_normalized_url(db_session, default_portfolio, request_context):
    create_webhook(WebhookCreate(webhook_url=" https://DISCORD.com/api/webhooks/1/x "),
                   default_portfolio, db_session, request_context)
    hook = db_session.query(DiscordWebhook).one()
    assert hook.webhook_url == "https://discord.com/api/webhooks/1/x"


def test_patch_with_invalid_url_is_400_and_keeps_the_stored_url(db_session, default_portfolio, request_context):
    _store(db_session, default_portfolio.id, GOOD)
    with pytest.raises(HTTPException) as exc:
        update_webhook(WebhookUpdate(webhook_url="https://169.254.169.254/latest/meta-data"),
                       default_portfolio, db_session, request_context)
    assert exc.value.status_code == 400
    db_session.rollback()
    db_session.expire_all()
    assert db_session.query(DiscordWebhook).one().webhook_url == GOOD


def test_patch_with_valid_url_replaces_it(db_session, default_portfolio, request_context):
    _store(db_session, default_portfolio.id, GOOD)
    update_webhook(WebhookUpdate(webhook_url="https://discordapp.com/api/webhooks/9/new"),
                   default_portfolio, db_session, request_context)
    db_session.expire_all()
    assert db_session.query(DiscordWebhook).one().webhook_url == "https://discordapp.com/api/webhooks/9/new"


def test_patch_without_url_does_not_revalidate_the_stored_one(db_session, default_portfolio, request_context):
    """Toggling a notification flag must keep working for a legacy row."""
    _store(db_session, default_portfolio.id, "http://10.0.0.5/legacy")
    update_webhook(WebhookUpdate(notify_trades=False), default_portfolio, db_session, request_context)
    db_session.expire_all()
    assert db_session.query(DiscordWebhook).one().notify_trades is False


def test_get_reports_valid_flag(db_session, default_portfolio):
    hook = _store(db_session, default_portfolio.id, GOOD)
    result = get_webhook(default_portfolio, db_session)
    assert result["valid"] is True

    hook.webhook_url = "http://10.0.0.5/legacy-secret-token"
    db_session.commit()
    result = get_webhook(default_portfolio, db_session)
    assert result["valid"] is False
    assert "10.0.0.5" not in str(result)
    assert "legacy-secret-token" not in str(result)


class _SyncClient:
    last_kwargs: dict = {}

    def __init__(self, response=None, exc=None):
        self._response, self._exc = response, exc

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, **kwargs):
        _SyncClient.last_kwargs = {"url": url, **kwargs}
        if self._exc:
            raise self._exc
        return self._response


def test_test_endpoint_returns_status_only_never_the_body(db_session, default_portfolio):
    _store(db_session, default_portfolio.id, GOOD)
    resp = MagicMock(status_code=404, text="internal-secret-response-body")
    with patch("routers.discord.httpx.Client", lambda: _SyncClient(response=resp)):
        with pytest.raises(HTTPException) as exc:
            run_webhook_test(WebhookTestMessage(), default_portfolio, db_session)
    assert exc.value.status_code == 502
    assert exc.value.detail == "Discord returned 404"
    assert "internal-secret-response-body" not in str(exc.value.detail)
    assert _SyncClient.last_kwargs["follow_redirects"] is False
    assert _SyncClient.last_kwargs["timeout"]


def test_test_endpoint_does_not_follow_redirects_to_other_hosts(db_session, default_portfolio):
    _store(db_session, default_portfolio.id, GOOD)
    resp = MagicMock(status_code=302, text="")
    with patch("routers.discord.httpx.Client", lambda: _SyncClient(response=resp)):
        with pytest.raises(HTTPException) as exc:
            run_webhook_test(WebhookTestMessage(), default_portfolio, db_session)
    assert exc.value.detail == "Discord returned 302"


def test_test_endpoint_hides_network_error_details(db_session, default_portfolio):
    _store(db_session, default_portfolio.id, GOOD)
    err = httpx.ConnectError("connect to 10.1.2.3 failed")
    with patch("routers.discord.httpx.Client", lambda: _SyncClient(exc=err)):
        with pytest.raises(HTTPException) as exc:
            run_webhook_test(WebhookTestMessage(), default_portfolio, db_session)
    assert exc.value.status_code == 502
    assert "10.1.2.3" not in str(exc.value.detail)


def test_test_endpoint_succeeds_for_valid_url(db_session, default_portfolio):
    _store(db_session, default_portfolio.id, GOOD)
    with patch("routers.discord.httpx.Client",
               lambda: _SyncClient(response=MagicMock(status_code=204))):
        assert run_webhook_test(WebhookTestMessage(), default_portfolio, db_session) == {"status": "sent"}
    assert _SyncClient.last_kwargs["url"] == GOOD


def test_test_endpoint_refuses_invalid_stored_url_without_a_request(db_session, default_portfolio):
    _store(db_session, default_portfolio.id, "http://169.254.169.254/latest/meta-data")
    client = MagicMock()
    with patch("routers.discord.httpx.Client", client):
        with pytest.raises(HTTPException) as exc:
            run_webhook_test(WebhookTestMessage(), default_portfolio, db_session)
    assert exc.value.status_code == 400
    client.assert_not_called()
    assert "169.254" not in str(exc.value.detail)


def test_send_notification_with_invalid_stored_url_makes_no_request(db_session, pid, caplog):
    _store(db_session, pid, "http://10.0.0.5/x?discord.com/api/webhooks/1/leaky-token")
    client = MagicMock()
    with patch("routers.discord.httpx.AsyncClient", client), \
            caplog.at_level(logging.WARNING, logger="portfyl.discord"):
        result = asyncio.run(send_discord_notification(db_session, TEST_WORKSPACE_ID, pid, "t", "d"))
    assert result is None
    client.assert_not_called()
    assert caplog.records, "a warning must be logged"
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "10.0.0.5" not in logged and "leaky-token" not in logged


def test_send_notification_posts_with_redirects_disabled(db_session, pid):
    _store(db_session, pid, GOOD)
    seen = {}

    class _Stub:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            seen.update(url=url, **kwargs)
            return MagicMock(status_code=204)

    with patch("routers.discord.httpx.AsyncClient", lambda: _Stub()):
        assert asyncio.run(send_discord_notification(db_session, TEST_WORKSPACE_ID, pid, "t", "d")) is True
    assert seen["url"] == GOOD
    assert seen["follow_redirects"] is False
    assert seen["timeout"]
