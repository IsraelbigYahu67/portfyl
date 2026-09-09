from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from data_retention import cleanup_retained_operational_data
from models import (
    AuthSession,
    DividendNotification,
    NotificationOutbox,
    UsageCounter,
    UsageReservation,
)


NOW = datetime(2026, 9, 9, 3, 17, tzinfo=timezone.utc)


def _session(user_id, suffix: str, *, expires_at, revoked_at=None):
    return AuthSession(
        user_id=user_id,
        token_digest=(suffix * 64)[:64],
        csrf_digest=(suffix.upper() * 64)[:64],
        expires_at=expires_at,
        revoked_at=revoked_at,
    )


def test_cleanup_removes_only_expired_operational_records(
    db_session, test_user, test_workspace, default_portfolio
):
    old = NOW - timedelta(days=500)
    recent = NOW - timedelta(days=10)
    db_session.add_all([
        _session(test_user.id, "a", expires_at=old),
        _session(test_user.id, "b", expires_at=NOW + timedelta(days=1)),
        _session(
            test_user.id,
            "c",
            expires_at=NOW + timedelta(days=1),
            revoked_at=old,
        ),
        _session(
            test_user.id,
            "d",
            expires_at=NOW + timedelta(days=1),
            revoked_at=recent,
        ),
    ])
    counter = UsageCounter(
        workspace_id=test_workspace.id,
        metric="assistant_messages",
        period_start=old,
        period_end=old + timedelta(days=30),
        used=2,
    )
    db_session.add(counter)
    db_session.flush()
    db_session.add_all([
        UsageReservation(
            workspace_id=test_workspace.id,
            counter_id=counter.id,
            metric=counter.metric,
            idempotency_key="old-finalized",
            amount=1,
            status="finalized",
            created_at=old,
            finalized_at=old,
        ),
        UsageReservation(
            workspace_id=test_workspace.id,
            counter_id=counter.id,
            metric=counter.metric,
            idempotency_key="open-reservation",
            amount=1,
            status="reserved",
            created_at=old,
        ),
    ])
    db_session.add_all([
        NotificationOutbox(
            workspace_id=test_workspace.id,
            user_id=test_user.id,
            kind="account_notice",
            deduplication_key="old-sent",
            payload={},
            status="sent",
            sent_at=old,
            created_at=old,
        ),
        NotificationOutbox(
            workspace_id=test_workspace.id,
            user_id=test_user.id,
            kind="account_notice",
            deduplication_key="pending",
            payload={},
            status="pending",
            created_at=old,
        ),
    ])
    db_session.add_all([
        DividendNotification(
            workspace_id=test_workspace.id,
            portfolio_id=default_portfolio.id,
            ticker="OLD",
            ex_date=date(2025, 1, 1),
            sent_at=old,
        ),
        DividendNotification(
            workspace_id=test_workspace.id,
            portfolio_id=default_portfolio.id,
            ticker="NEW",
            ex_date=date(2026, 9, 1),
            sent_at=recent,
        ),
    ])
    db_session.commit()

    result = cleanup_retained_operational_data(db_session, now=NOW)

    assert result == {
        "auth_sessions": 2,
        "usage_reservations": 1,
        "notification_outbox": 1,
        "dividend_notifications": 1,
    }
    assert db_session.query(AuthSession).count() == 2
    assert db_session.query(UsageReservation).count() == 1
    assert db_session.query(NotificationOutbox).count() == 1
    assert db_session.query(DividendNotification).count() == 1


def test_cleanup_rejects_unbounded_or_empty_batch(db_session):
    try:
        cleanup_retained_operational_data(
            db_session,
            now=NOW,
            max_rows_per_category=0,
        )
    except ValueError as exc:
        assert str(exc) == "max_rows_per_category must be positive"
    else:
        raise AssertionError("expected ValueError")
