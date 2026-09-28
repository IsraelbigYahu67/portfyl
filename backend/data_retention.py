"""Bounded cleanup for operational records with an approved private-test TTL."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session, aliased

from account_deletion import _active_workspace_ids, _set_cleanup_context
from models import (
    AuthSession,
    BrokerSyncEvent,
    BrokerSyncRun,
    DividendNotification,
    NotificationOutbox,
    UsageReservation,
)


SESSION_INVALID_RETENTION = timedelta(days=30)
USAGE_RESERVATION_RETENTION = timedelta(days=90)
NOTIFICATION_OUTBOX_RETENTION = timedelta(days=90)
DIVIDEND_NOTIFICATION_RETENTION = timedelta(days=400)
STAGING_RETENTION = timedelta(days=14)
STAGING_REVIEW_RETENTION = timedelta(days=90)
DEFAULT_MAX_ROWS_PER_CATEGORY = 10_000


def _delete_ids(db: Session, model, ids: list) -> int:
    if not ids:
        return 0
    db.execute(delete(model).where(model.id.in_(ids)))
    return len(ids)


def cleanup_retained_operational_data(
    db: Session,
    *,
    now: datetime | None = None,
    max_rows_per_category: int = DEFAULT_MAX_ROWS_PER_CATEGORY,
) -> dict[str, int]:
    """Delete expired operational data in bounded, retry-safe batches.

    Active sessions, open usage reservations, pending/retryable notifications,
    financial records, durable audit evidence, and the latest unresolved broker
    review evidence are deliberately outside this cleanup. Tenant tables are
    processed under one explicit workspace context at a time so PostgreSQL RLS
    remains enforced.
    """
    if max_rows_per_category <= 0:
        raise ValueError("max_rows_per_category must be positive")
    now = now or datetime.now(timezone.utc)
    session_cutoff = now - SESSION_INVALID_RETENTION
    usage_cutoff = now - USAGE_RESERVATION_RETENTION
    outbox_cutoff = now - NOTIFICATION_OUTBOX_RETENTION
    dividend_cutoff = now - DIVIDEND_NOTIFICATION_RETENTION
    staging_cutoff = now - STAGING_RETENTION
    staging_review_cutoff = now - STAGING_REVIEW_RETENTION
    summary = {
        "auth_sessions": 0,
        "usage_reservations": 0,
        "notification_outbox": 0,
        "dividend_notifications": 0,
        "broker_sync_events": 0,
    }

    session_ids = list(db.scalars(
        select(AuthSession.id)
        .where(or_(
            AuthSession.expires_at <= session_cutoff,
            and_(
                AuthSession.revoked_at.is_not(None),
                AuthSession.revoked_at <= session_cutoff,
            ),
        ))
        .order_by(AuthSession.expires_at, AuthSession.id)
        .limit(max_rows_per_category)
    ).all())
    summary["auth_sessions"] = _delete_ids(db, AuthSession, session_ids)
    db.commit()

    remaining = {
        key: max_rows_per_category
        for key in (
            "usage_reservations",
            "notification_outbox",
            "dividend_notifications",
            "broker_sync_events",
        )
    }
    for workspace_id in _active_workspace_ids(db):
        if not any(remaining.values()):
            break
        _set_cleanup_context(db, workspace_id)

        if remaining["usage_reservations"]:
            ids = list(db.scalars(
                select(UsageReservation.id)
                .where(
                    UsageReservation.workspace_id == workspace_id,
                    UsageReservation.status.in_(("finalized", "released")),
                    UsageReservation.finalized_at <= usage_cutoff,
                )
                .order_by(UsageReservation.finalized_at, UsageReservation.id)
                .limit(remaining["usage_reservations"])
            ).all())
            deleted_count = _delete_ids(db, UsageReservation, ids)
            summary["usage_reservations"] += deleted_count
            remaining["usage_reservations"] -= deleted_count

        if remaining["notification_outbox"]:
            ids = list(db.scalars(
                select(NotificationOutbox.id)
                .where(
                    NotificationOutbox.workspace_id == workspace_id,
                    or_(
                        and_(
                            NotificationOutbox.status == "sent",
                            NotificationOutbox.sent_at <= outbox_cutoff,
                        ),
                        and_(
                            NotificationOutbox.status == "failed",
                            NotificationOutbox.attempts >= 5,
                            NotificationOutbox.created_at <= outbox_cutoff,
                        ),
                    ),
                )
                .order_by(NotificationOutbox.created_at, NotificationOutbox.id)
                .limit(remaining["notification_outbox"])
            ).all())
            deleted_count = _delete_ids(db, NotificationOutbox, ids)
            summary["notification_outbox"] += deleted_count
            remaining["notification_outbox"] -= deleted_count

        if remaining["dividend_notifications"]:
            ids = list(db.scalars(
                select(DividendNotification.id)
                .where(
                    DividendNotification.workspace_id == workspace_id,
                    DividendNotification.sent_at <= dividend_cutoff,
                )
                .order_by(DividendNotification.sent_at, DividendNotification.id)
                .limit(remaining["dividend_notifications"])
            ).all())
            deleted_count = _delete_ids(db, DividendNotification, ids)
            summary["dividend_notifications"] += deleted_count
            remaining["dividend_notifications"] -= deleted_count

        if remaining["broker_sync_events"]:
            latest_run = aliased(BrokerSyncRun)
            latest_run_id = (
                select(latest_run.id)
                .where(
                    latest_run.workspace_id == BrokerSyncRun.workspace_id,
                    latest_run.connection_id == BrokerSyncRun.connection_id,
                )
                .order_by(latest_run.created_at.desc(), latest_run.id.desc())
                .limit(1)
                .correlate(BrokerSyncRun)
                .scalar_subquery()
            )
            run_age = func.coalesce(
                BrokerSyncRun.completed_at,
                BrokerSyncRun.updated_at,
            )
            ids = list(db.scalars(
                select(BrokerSyncEvent.id)
                .join(
                    BrokerSyncRun,
                    and_(
                        BrokerSyncRun.workspace_id == BrokerSyncEvent.workspace_id,
                        BrokerSyncRun.id == BrokerSyncEvent.run_id,
                    ),
                )
                .where(
                    BrokerSyncEvent.workspace_id == workspace_id,
                    or_(
                        and_(
                            BrokerSyncRun.state.in_(
                                ("completed", "failed", "cancelled")
                            ),
                            run_age <= staging_cutoff,
                        ),
                        and_(
                            BrokerSyncRun.state == "needs_review",
                            run_age <= staging_review_cutoff,
                            BrokerSyncRun.id != latest_run_id,
                        ),
                    ),
                )
                .order_by(run_age, BrokerSyncEvent.id)
                .limit(remaining["broker_sync_events"])
            ).all())
            deleted_count = _delete_ids(db, BrokerSyncEvent, ids)
            summary["broker_sync_events"] += deleted_count
            remaining["broker_sync_events"] -= deleted_count

        db.commit()

    return summary
