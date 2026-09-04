"""Cloud Scheduler billing reconciliation and notification-outbox pass."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from audit import record_audit_event
from billing_config import BillingConfig
from billing_reconciliation import project_subscription
from jobs import _active_workspace_ids, _set_job_workspace_context
from models import BillingCustomer, Membership, NotificationOutbox, StripeEvent, Subscription, TrialGrant
from stripe_service import StripeGateway, object_value


def _due_events(db: Session, now: datetime) -> list[StripeEvent]:
    return list(db.scalars(
        select(StripeEvent).where(
            StripeEvent.status.in_(("pending", "failed")),
            or_(StripeEvent.next_attempt_at.is_(None), StripeEvent.next_attempt_at <= now),
        ).order_by(StripeEvent.received_at).limit(100)
    ).all())


def _workspace_for_customer(db: Session, customer_id: str):
    for workspace_id in _active_workspace_ids(db):
        _set_job_workspace_context(db, workspace_id)
        if db.scalar(select(BillingCustomer).where(
            BillingCustomer.workspace_id == workspace_id,
            BillingCustomer.stripe_customer_id == customer_id,
        )):
            return workspace_id
    return None


def _workspace_owner_id(db: Session, workspace_id):
    return db.scalar(select(Membership.user_id).where(
        Membership.workspace_id == workspace_id,
        Membership.role == "owner",
        Membership.status == "active",
    ).order_by(Membership.created_at, Membership.id).limit(1))


def _enqueue_billing_lifecycle(
    db: Session,
    *,
    workspace_id,
    subscription: Subscription,
    now: datetime,
) -> int:
    owner_id = _workspace_owner_id(db, workspace_id)
    if owner_id is None:
        return 0
    intents: list[tuple[str, str, dict]] = []
    if subscription.payment_failed_at is not None:
        marker = subscription.payment_failed_at.isoformat()
        intents.append((
            "payment_failed",
            f"subscription:{subscription.public_id}:payment-failed:{marker}",
            {"grace_ends_at": subscription.grace_ends_at.isoformat() if subscription.grace_ends_at else None},
        ))
    if subscription.cancel_at_period_end:
        marker = subscription.current_period_end.isoformat() if subscription.current_period_end else "unknown"
        intents.append((
            "subscription_cancel_scheduled",
            f"subscription:{subscription.public_id}:cancel-scheduled:{marker}",
            {"access_ends_at": marker},
        ))
    if subscription.ended_at is not None:
        marker = subscription.ended_at.isoformat()
        intents.append((
            "subscription_canceled",
            f"subscription:{subscription.public_id}:canceled:{marker}",
            {"ended_at": marker},
        ))
    grace_ends = subscription.grace_ends_at
    if subscription.status == "past_due" and grace_ends is not None:
        grace_ends = grace_ends if grace_ends.tzinfo else grace_ends.replace(tzinfo=timezone.utc)
        if grace_ends <= now:
            marker = grace_ends.isoformat()
            intents.append((
                "grace_expired",
                f"subscription:{subscription.public_id}:grace-expired:{marker}",
                {"grace_ended_at": marker},
            ))

    created = 0
    for kind, key, payload in intents:
        if db.scalar(select(NotificationOutbox.id).where(NotificationOutbox.deduplication_key == key)):
            continue
        db.add(NotificationOutbox(
            workspace_id=workspace_id,
            user_id=owner_id,
            kind=kind,
            deduplication_key=key,
            payload=payload,
        ))
        created += 1
    return created


def _enqueue_trial_reminders(db: Session, workspace_id, now: datetime) -> int:
    count = 0
    grants = db.scalars(select(TrialGrant).where(TrialGrant.workspace_id == workspace_id)).all()
    for grant in grants:
        started = grant.started_at if grant.started_at.tzinfo else grant.started_at.replace(tzinfo=timezone.utc)
        age = now - started
        for day, kind in ((3, "trial_day_three"), (6, "trial_day_six")):
            if age.days < day or grant.activated_by_user_id is None:
                continue
            key = f"trial:{grant.public_id}:day:{day}"
            if db.scalar(select(NotificationOutbox).where(NotificationOutbox.deduplication_key == key)):
                continue
            db.add(NotificationOutbox(
                workspace_id=workspace_id,
                user_id=grant.activated_by_user_id,
                kind=kind,
                deduplication_key=key,
                payload={"trial_ends_at": grant.ends_at.isoformat()},
            ))
            count += 1
    return count


async def billing_reconciliation_pass(db: Session) -> list[dict]:
    """Converge pending webhook events and all mapped active subscriptions."""
    config = BillingConfig.from_env(os.environ)
    if not config.enabled:
        return []
    gateway = StripeGateway(config)
    now = datetime.now(timezone.utc)
    results: list[dict] = []

    for event in _due_events(db, now):
        if not event.object_id:
            event.status = "quarantined"
            event.last_error = "missing subscription reference"
            continue
        event.status = "processing"
        event.attempts += 1
        try:
            remote = gateway.retrieve_subscription(event.object_id)
            workspace_id = _workspace_for_customer(db, object_value(remote, "customer"))
            if workspace_id is None:
                raise ValueError("Stripe Customer is not mapped")
            _set_job_workspace_context(db, workspace_id)
            subscription = project_subscription(
                db,
                workspace_id=workspace_id,
                remote=remote,
                config=config,
                event_type=event.event_type,
                now=now,
            )
            notification_count = _enqueue_billing_lifecycle(
                db,
                workspace_id=workspace_id,
                subscription=subscription,
                now=now,
            )
            owner_id = _workspace_owner_id(db, workspace_id)
            if owner_id is not None:
                record_audit_event(
                    db,
                    actor_user_id=owner_id,
                    workspace_id=workspace_id,
                    action="billing.subscription.reconciled",
                    target_type="subscription",
                    target_id=str(subscription.public_id),
                    metadata={"event_type": event.event_type, "status": subscription.status},
                )
            event.status = "processed"
            event.processed_at = now
            event.last_error = None
            event.next_attempt_at = None
            results.append({
                "event": event.stripe_event_id,
                "status": "processed",
                "notifications": notification_count,
            })
        except ValueError as exc:
            event.status = "quarantined"
            event.last_error = str(exc)
            results.append({"event": event.stripe_event_id, "status": "quarantined"})
        except Exception as exc:
            event.status = "failed"
            event.last_error = type(exc).__name__
            event.next_attempt_at = now + timedelta(minutes=min(60, 2 ** min(event.attempts, 5)))
            results.append({"event": event.stripe_event_id, "status": "retry"})
        db.commit()

    for workspace_id in _active_workspace_ids(db):
        _set_job_workspace_context(db, workspace_id)
        customer = db.scalar(select(BillingCustomer).where(BillingCustomer.workspace_id == workspace_id))
        if customer is not None:
            try:
                for remote in gateway.list_subscriptions(customer.stripe_customer_id):
                    subscription = project_subscription(
                        db,
                        workspace_id=workspace_id,
                        remote=remote,
                        config=config,
                        event_type="reconciliation",
                        now=now,
                    )
                    _enqueue_billing_lifecycle(
                        db,
                        workspace_id=workspace_id,
                        subscription=subscription,
                        now=now,
                    )
                results.append({"workspace": str(workspace_id), "status": "reconciled"})
            except Exception as exc:
                results.append({"workspace": str(workspace_id), "status": "retry", "error": type(exc).__name__})
        reminders = _enqueue_trial_reminders(db, workspace_id, now)
        if reminders:
            results.append({"workspace": str(workspace_id), "trial_reminders": reminders})
        db.commit()
    return results
