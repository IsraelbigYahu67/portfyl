from __future__ import annotations

from datetime import datetime, timezone

from models import NotificationOutbox
from notifications import deliver_notification_outbox


class RecordingTransport:
    def __init__(self, fail=False):
        self.fail = fail
        self.sent = []

    def send(self, **message):
        if self.fail:
            raise ConnectionError("provider unavailable")
        self.sent.append(message)


def test_outbox_sends_once_without_portfolio_data(db_session, test_user, test_workspace):
    row = NotificationOutbox(
        workspace_id=test_workspace.id,
        user_id=test_user.id,
        kind="account_notice",
        deduplication_key="account:1:notice",
        payload={"message": "Your account is ready"},
    )
    db_session.add(row)
    db_session.flush()
    transport = RecordingTransport()
    result = deliver_notification_outbox(
        db_session, workspace_id=test_workspace.id, transport=transport,
        now=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )
    assert result == [{"kind": "account_notice", "status": "sent"}]
    assert transport.sent[0]["recipient"] == test_user.email
    assert row.status == "sent"


def test_outbox_failure_is_bounded_and_redacted(db_session, test_user, test_workspace):
    row = NotificationOutbox(
        workspace_id=test_workspace.id,
        user_id=test_user.id,
        kind="account_notice",
        deduplication_key="account:1:failed-notice",
        payload={},
    )
    db_session.add(row)
    db_session.flush()
    deliver_notification_outbox(
        db_session,
        workspace_id=test_workspace.id,
        transport=RecordingTransport(fail=True),
    )
    assert row.status == "failed"
    assert row.last_error == "ConnectionError"
