from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from data_retention import cleanup_retained_operational_data
from models import (
    AuthSession,
    BrokerConnection,
    BrokerSyncEvent,
    BrokerSyncRun,
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


def _connection(db, portfolio):
    connection = BrokerConnection(
        workspace_id=portfolio.workspace_id,
        portfolio_id=portfolio.id,
        broker="trading212",
        api_key_ciphertext=b"test-key",
        api_key_key_version="test",
        account_fingerprint="f" * 64,
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


def _sync_run(db, connection, portfolio, *, state, age_days):
    timestamp = NOW - timedelta(days=age_days)
    run = BrokerSyncRun(
        workspace_id=portfolio.workspace_id,
        portfolio_id=portfolio.id,
        connection_id=connection.id,
        broker="trading212",
        account_fingerprint=connection.account_fingerprint,
        credential_generation=connection.credential_generation,
        mode="incremental",
        state=state,
        completed_at=(
            timestamp if state in {"completed", "failed", "cancelled"} else None
        ),
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _staged_event(db, run, event_id):
    event = BrokerSyncEvent(
        workspace_id=run.workspace_id,
        portfolio_id=run.portfolio_id,
        run_id=run.id,
        broker="trading212",
        account_fingerprint=run.account_fingerprint,
        stream="orders",
        provider_event_id=event_id,
        raw_payload={"fill": {"id": event_id, "type": "TRADE"}},
    )
    db.add(event)
    db.commit()
    return event


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
        metric="example_monthly",
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
        "broker_sync_events": 0,
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


def test_old_completed_run_events_are_purged(db_session, default_portfolio):
    connection = _connection(db_session, default_portfolio)
    run = _sync_run(
        db_session,
        connection,
        default_portfolio,
        state="completed",
        age_days=15,
    )
    _staged_event(db_session, run, "fill:old-completed")

    summary = cleanup_retained_operational_data(db_session, now=NOW)

    assert db_session.query(BrokerSyncEvent).count() == 0
    assert summary["broker_sync_events"] == 1


def test_recent_completed_run_events_are_kept(db_session, default_portfolio):
    connection = _connection(db_session, default_portfolio)
    run = _sync_run(
        db_session,
        connection,
        default_portfolio,
        state="completed",
        age_days=3,
    )
    _staged_event(db_session, run, "fill:recent-completed")

    summary = cleanup_retained_operational_data(db_session, now=NOW)

    assert db_session.query(BrokerSyncEvent).count() == 1
    assert summary["broker_sync_events"] == 0


def test_latest_needs_review_run_events_are_never_purged(
    db_session, default_portfolio
):
    connection = _connection(db_session, default_portfolio)
    run = _sync_run(
        db_session,
        connection,
        default_portfolio,
        state="needs_review",
        age_days=200,
    )
    _staged_event(db_session, run, "fill:latest-review")

    summary = cleanup_retained_operational_data(db_session, now=NOW)

    assert db_session.query(BrokerSyncEvent).count() == 1
    assert summary["broker_sync_events"] == 0


def test_superseded_old_needs_review_events_are_purged(
    db_session, default_portfolio
):
    connection = _connection(db_session, default_portfolio)
    old_run = _sync_run(
        db_session,
        connection,
        default_portfolio,
        state="needs_review",
        age_days=100,
    )
    _staged_event(db_session, old_run, "fill:superseded-review")
    _sync_run(
        db_session,
        connection,
        default_portfolio,
        state="completed",
        age_days=1,
    )

    summary = cleanup_retained_operational_data(db_session, now=NOW)

    assert db_session.query(BrokerSyncEvent).count() == 0
    assert summary["broker_sync_events"] == 1


def test_active_run_events_are_never_purged(db_session, default_portfolio):
    connection = _connection(db_session, default_portfolio)
    run = _sync_run(
        db_session,
        connection,
        default_portfolio,
        state="fetching",
        age_days=30,
    )
    _staged_event(db_session, run, "fill:active")

    summary = cleanup_retained_operational_data(db_session, now=NOW)

    assert db_session.query(BrokerSyncEvent).count() == 1
    assert summary["broker_sync_events"] == 0
