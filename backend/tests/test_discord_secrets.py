"""DiscordWebhook.webhook_url is stored only as ciphertext; the property
transparently encrypts on write and decrypts on read (mirrors
test_broker_secrets.py for BrokerConnection)."""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

from models import DiscordWebhook
from routers.discord import get_webhook, send_discord_notification
from tests.helpers import TEST_WORKSPACE_ID


class TestAtRestEncryption:
    def test_no_plaintext_survives_on_the_row(self, db_session, pid):
        hook = DiscordWebhook(
            workspace_id=TEST_WORKSPACE_ID, portfolio_id=pid,
            webhook_url="https://discord.com/api/webhooks/123/super-secret-token",
        )
        db_session.add(hook)
        db_session.commit()

        assert hook.webhook_url_ciphertext is not None
        assert b"super-secret-token" not in hook.webhook_url_ciphertext
        column_names = {c.name for c in DiscordWebhook.__table__.columns}
        assert "webhook_url" not in column_names

    def test_round_trips_through_the_property(self, db_session, pid):
        hook = DiscordWebhook(
            workspace_id=TEST_WORKSPACE_ID, portfolio_id=pid,
            webhook_url="https://discord.com/api/webhooks/123/token",
        )
        db_session.add(hook)
        db_session.commit()
        db_session.expire_all()

        reloaded = db_session.get(DiscordWebhook, hook.id)
        assert reloaded.webhook_url == "https://discord.com/api/webhooks/123/token"

    def test_api_preview_never_contains_webhook_id_or_token(
        self, db_session, default_portfolio
    ):
        hook = DiscordWebhook(
            workspace_id=default_portfolio.workspace_id,
            portfolio_id=default_portfolio.id,
            webhook_url="https://discord.com/api/webhooks/123456/private-token",
        )
        db_session.add(hook)
        db_session.commit()

        result = get_webhook(default_portfolio, db_session)

        assert result["webhook_url_preview"] == "https://discord.com/api/webhooks/***/***"
        assert "123456" not in str(result)
        assert "private-token" not in str(result)


class TestNotificationDecryptsStoredWebhookUrl:
    def test_send_notification_posts_to_the_decrypted_url(self, db_session, pid):
        hook = DiscordWebhook(
            workspace_id=TEST_WORKSPACE_ID, portfolio_id=pid,
            webhook_url="https://discord.com/api/webhooks/123/real-token",
        )
        db_session.add(hook)
        db_session.commit()

        seen_urls = []

        class _StubClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def post(self, url, *args, **kwargs):
                seen_urls.append(url)
                return MagicMock(status_code=204)

        with patch("routers.discord.httpx.AsyncClient", lambda: _StubClient()):
            asyncio.run(send_discord_notification(
                db_session, TEST_WORKSPACE_ID, pid, "title", "description",
            ))

        assert seen_urls == ["https://discord.com/api/webhooks/123/real-token"]
