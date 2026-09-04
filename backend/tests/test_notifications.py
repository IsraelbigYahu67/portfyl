from __future__ import annotations

from datetime import datetime, timedelta, timezone

from billing_jobs import _enqueue_billing_lifecycle
from models import NotificationOutbox, Subscription
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
        kind="trial_day_three",
        deduplication_key="trial:1:day:3",
        payload={"trial_ends_at": "2026-09-11T00:00:00Z"},
    )
    db_session.add(row)
    db_session.flush()
    transport = RecordingTransport()
    result = deliver_notification_outbox(
        db_session, workspace_id=test_workspace.id, transport=transport,
        now=datetime(2026, 9, 7, tzinfo=timezone.utc),
    )
    assert result == [{"kind": "trial_day_three", "status": "sent"}]
    assert transport.sent[0]["recipient"] == test_user.email
    assert row.status == "sent"


def test_outbox_failure_is_bounded_and_redacted(db_session, test_user, test_workspace):
    row = NotificationOutbox(
        workspace_id=test_workspace.id,
        user_id=test_user.id,
        kind="payment_failed",
        deduplication_key="invoice:1:failed",
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


def test_billing_lifecycle_intents_are_deduplicated(
    db_session, test_user, test_workspace, test_membership
):
    now = datetime(2026, 9, 20, tzinfo=timezone.utc)
    subscription = Subscription(
        workspace_id=test_workspace.id,
        stripe_subscription_id="sub_notice",
        stripe_price_id="price_pro_v1",
        plan="pro",
        billing_interval="month",
        price_version="v1",
        status="past_due",
        current_period_start=now - timedelta(days=30),
        current_period_end=now - timedelta(days=1),
        cancel_at_period_end=True,
        payment_failed_at=now - timedelta(days=15),
        grace_ends_at=now - timedelta(days=1),
    )
    db_session.add(subscription)
    db_session.flush()
    assert _enqueue_billing_lifecycle(
        db_session,
        workspace_id=test_workspace.id,
        subscription=subscription,
        now=now,
    ) == 3
    db_session.flush()
    assert _enqueue_billing_lifecycle(
        db_session,
        workspace_id=test_workspace.id,
        subscription=subscription,
        now=now,
    ) == 0
    assert {row.kind for row in db_session.query(NotificationOutbox).all()} == {
        "payment_failed", "subscription_cancel_scheduled", "grace_expired",
    }
