"""Tests for the Discord webhook sender's delivery-result contract.

Callers that gate one-shot state (alert trigger flags, dividend dedup rows)
depend on send_discord_notification reporting delivery: True = accepted,
False = failed (retry later), None = no webhook configured.
"""

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
from unittest.mock import patch, MagicMock

from models import DiscordWebhook
from routers.discord import send_discord_notification
from tests.helpers import TEST_WORKSPACE_ID


def _hook(db, pid, workspace_id=TEST_WORKSPACE_ID):
    hook = DiscordWebhook(workspace_id=workspace_id, portfolio_id=pid,
                          webhook_url="https://discord.com/api/webhooks/1/x",
                          notify_trades=True, notify_dividends=True,
                          notify_milestones=True)
    db.add(hook)
    db.commit()
    return hook


def _send(db, pid, workspace_id=TEST_WORKSPACE_ID):
    return asyncio.run(send_discord_notification(db, workspace_id, pid, "t", "d"))


class _StubClient:
    """Minimal httpx.AsyncClient stand-in: returns a canned response or raises."""

    def __init__(self, response=None, exc=None):
        self._response = response
        self._exc = exc

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, *args, **kwargs):
        if self._exc:
            raise self._exc
        return self._response


def test_returns_none_without_webhook(db_session, pid):
    assert _send(db_session, pid) is None


def test_returns_true_when_discord_accepts(db_session, pid):
    _hook(db_session, pid)
    resp = MagicMock(status_code=204)
    with patch("routers.discord.httpx.AsyncClient", lambda: _StubClient(response=resp)):
        assert _send(db_session, pid) is True


def test_returns_false_on_network_error(db_session, pid):
    _hook(db_session, pid)
    with patch("routers.discord.httpx.AsyncClient", lambda: _StubClient(exc=RuntimeError("down"))):
        assert _send(db_session, pid) is False


def test_returns_false_on_error_status(db_session, pid):
    _hook(db_session, pid)
    resp = MagicMock(status_code=404)  # deleted/stale webhook
    with patch("routers.discord.httpx.AsyncClient", lambda: _StubClient(response=resp)):
        assert _send(db_session, pid) is False


def test_foreign_workspace_never_reaches_another_tenants_webhook(db_session, pid):
    """The workspace predicate is mandatory, not decorative: a caller holding
    the right internal portfolio ID but a different workspace must get the
    "no webhook configured" answer, never another tenant's webhook URL."""
    from uuid import uuid4

    _hook(db_session, pid)
    other_workspace = uuid4()
    resp = MagicMock(status_code=204)
    with patch("routers.discord.httpx.AsyncClient", lambda: _StubClient(response=resp)):
        assert _send(db_session, pid, workspace_id=other_workspace) is None
