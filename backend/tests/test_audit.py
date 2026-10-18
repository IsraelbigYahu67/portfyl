from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from audit import record_audit_event
from models import AuditLog, User, Workspace
from routers.broker import connect as connect_t212, disconnect as disconnect_t212
from routers.discord import (
    WebhookCreate,
    WebhookUpdate,
    create_webhook,
    delete_webhook,
    update_webhook,
)
from routers.ibkr import connect as connect_ibkr, disconnect as disconnect_ibkr
from routers.settings import get_audit_log


def test_record_audit_event_persists_fields_and_recursively_redacts(db_session, request_context):
    row = record_audit_event(
        db_session,
        actor_user_id=request_context.user.id,
        workspace_id=request_context.workspace.id,
        action="credential.changed",
        target_type="integration",
        target_id="public-target",
        metadata={
            "url": "https://discord.com/api/webhooks/123/super-secret-token",
            "nested": ["portfyl_session=raw-cookie", {"safe": "workspace-42"}],
        },
    )
    db_session.commit()

    stored = db_session.get(AuditLog, row.id)
    rendered = str(stored.event_metadata)
    assert stored.action == "credential.changed"
    assert stored.target_id == "public-target"
    assert "super-secret-token" not in rendered
    assert "raw-cookie" not in rendered
    assert "workspace-42" in rendered


def test_personal_and_workspace_audit_rows_are_application_scoped(
    db_session, request_context
):
    other_user = User(firebase_uid="other", email="other@example.com")
    other_workspace = Workspace(name="Other")
    db_session.add_all([other_user, other_workspace])
    db_session.flush()

    for actor, workspace, action in (
        (request_context.user.id, request_context.workspace.id, "own.workspace"),
        (request_context.user.id, None, "own.personal"),
        (other_user.id, other_workspace.id, "other.workspace"),
        (other_user.id, None, "other.personal"),
    ):
        record_audit_event(
            db_session, actor_user_id=actor, workspace_id=workspace, action=action
        )
    db_session.commit()

    result = get_audit_log(1, 50, db_session, request_context)
    assert {item["action"] for item in result["items"]} == {
        "own.workspace", "own.personal"
    }
    assert result["total"] == 2

    first_page = get_audit_log(1, 1, db_session, request_context)
    assert len(first_page["items"]) == 1
    assert first_page["page"] == 1
    assert first_page["page_size"] == 1
    assert first_page["total"] == 2


def test_t212_connection_create_and_delete_are_audited(
    db_session, default_portfolio, request_context
):
    upstream = MagicMock(status_code=200)
    upstream.raise_for_status.return_value = None
    with patch("routers.broker.httpx.get", return_value=upstream):
        connect_t212(
            {"api_key": "broker-key", "api_secret": "broker-secret"},
            db_session,
            default_portfolio,
            request_context,
        )
    disconnect_t212(db_session, default_portfolio, request_context)

    rows = db_session.query(AuditLog).order_by(AuditLog.created_at).all()
    assert [row.action for row in rows] == [
        "broker.connection.created", "broker.connection.deleted"
    ]
    assert all(row.event_metadata["broker"] == "trading212" for row in rows)
    assert "broker-key" not in str([row.event_metadata for row in rows])


def test_discord_webhook_create_and_delete_are_audited(
    db_session, default_portfolio, request_context
):
    create_webhook(
        WebhookCreate(webhook_url="https://discord.com/api/webhooks/123/token"),
        default_portfolio,
        db_session,
        request_context,
    )
    update_webhook(
        WebhookUpdate(notify_trades=False),
        default_portfolio,
        db_session,
        request_context,
    )
    delete_webhook(default_portfolio, db_session, request_context)

    rows = db_session.query(AuditLog).order_by(AuditLog.created_at).all()
    assert [row.action for row in rows] == [
        "discord.webhook.created", "discord.webhook.updated",
        "discord.webhook.deleted",
    ]
    assert "discord.com" not in str([row.event_metadata for row in rows])


def test_ibkr_connection_create_and_delete_are_audited(
    db_session, default_portfolio, request_context
):
    with patch("routers.ibkr._send_flex_request", AsyncMock(return_value="ref")):
        connect_ibkr(
            {"flex_token": "flex-token", "query_id": "query-id"},
            db_session,
            default_portfolio,
            request_context,
        )
    disconnect_ibkr(db_session, default_portfolio, request_context)

    rows = db_session.query(AuditLog).order_by(AuditLog.created_at).all()
    assert [row.action for row in rows] == [
        "broker.connection.created", "broker.connection.deleted"
    ]
    assert all(row.event_metadata["broker"] == "ibkr" for row in rows)
    assert "flex-token" not in str([row.event_metadata for row in rows])
