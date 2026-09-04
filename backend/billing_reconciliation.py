"""Replay-safe projection of canonical Stripe subscription state."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from billing_config import BillingConfig
from models import BillingCustomer, StripeEvent, Subscription
from stripe_service import StripeGatewayProtocol, object_value


GRACE_PERIOD = timedelta(days=14)
SUPPORTED_EVENT_PREFIXES = ("customer.subscription.", "invoice.")


def _utc_timestamp(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


def subscription_id_from_event(event: Any) -> str | None:
    event_type = object_value(event, "type", "")
    obj = object_value(object_value(event, "data", {}), "object", {})
    if event_type.startswith("customer.subscription."):
        return object_value(obj, "id")
    if event_type.startswith("invoice."):
        direct = object_value(obj, "subscription")
        if direct:
            return direct
        parent = object_value(obj, "parent", {}) or {}
        details = object_value(parent, "subscription_details", {}) or {}
        return object_value(details, "subscription")
    return None


def project_subscription(
    db: Session,
    *,
    workspace_id,
    remote: Any,
    config: BillingConfig,
    event_type: str = "",
    now: datetime | None = None,
) -> Subscription:
    now = now or datetime.now(timezone.utc)
    items = object_value(object_value(remote, "items", {}), "data", []) or []
    if len(items) != 1:
        raise ValueError("Stripe subscription must contain exactly one item")
    price = object_value(items[0], "price", {})
    price_id = object_value(price, "id")
    try:
        plan, interval, price_version = config.price_mapping()[price_id]
    except KeyError as exc:
        raise ValueError("Stripe subscription uses an unknown Price ID") from exc
    stripe_subscription_id = object_value(remote, "id")
    row = db.scalar(select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id))
    if row is None:
        row = Subscription(
            workspace_id=workspace_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_price_id=price_id,
            plan=plan.value,
            billing_interval=interval.value,
            price_version=price_version,
            status="incomplete",
        )
        db.add(row)
    elif (
        row.stripe_price_id != price_id
        and row.plan == plan.value
        and row.billing_interval == interval.value
    ):
        raise ValueError(
            "Continuous subscription cannot change price generation without a plan or interval change"
        )

    status = object_value(remote, "status", "incomplete")
    row.stripe_price_id = price_id
    row.plan = plan.value
    row.billing_interval = interval.value
    row.price_version = price_version
    row.status = status
    row.current_period_start = _utc_timestamp(object_value(remote, "current_period_start"))
    row.current_period_end = _utc_timestamp(object_value(remote, "current_period_end"))
    row.cancel_at_period_end = bool(object_value(remote, "cancel_at_period_end", False))

    # The retrieved Subscription is canonical. Never let an older invoice
    # event re-introduce grace after Stripe already reports recovery.
    if status == "past_due":
        if row.payment_failed_at is None:
            row.payment_failed_at = now
        if row.grace_ends_at is None:
            row.grace_ends_at = now + GRACE_PERIOD
    elif status in {"active", "trialing"}:
        row.payment_failed_at = None
        row.grace_ends_at = None

    if status in {"canceled", "unpaid", "incomplete_expired", "paused"}:
        row.ended_at = _utc_timestamp(object_value(remote, "ended_at")) or now
    else:
        row.ended_at = None
    db.flush()
    return row


def process_stripe_event(
    db: Session,
    *,
    event_row: StripeEvent,
    gateway: StripeGatewayProtocol,
    config: BillingConfig,
    workspace_id,
) -> Subscription | None:
    if not event_row.event_type.startswith(SUPPORTED_EVENT_PREFIXES):
        event_row.status = "processed"
        event_row.processed_at = datetime.now(timezone.utc)
        return None
    if not event_row.object_id:
        event_row.status = "quarantined"
        event_row.last_error = "missing subscription reference"
        return None
    event_row.status = "processing"
    event_row.attempts += 1
    try:
        remote = gateway.retrieve_subscription(event_row.object_id)
        customer_id = object_value(remote, "customer")
        customer = db.scalar(
            select(BillingCustomer).where(
                BillingCustomer.workspace_id == workspace_id,
                BillingCustomer.stripe_customer_id == customer_id,
            )
        )
        if customer is None:
            raise ValueError("Stripe Customer is not mapped to this workspace")
        result = project_subscription(
            db,
            workspace_id=workspace_id,
            remote=remote,
            config=config,
            event_type=event_row.event_type,
        )
        event_row.status = "processed"
        event_row.processed_at = datetime.now(timezone.utc)
        event_row.last_error = None
        event_row.next_attempt_at = None
        return result
    except ValueError as exc:
        event_row.status = "quarantined"
        event_row.last_error = str(exc)
        return None
    except Exception as exc:
        event_row.status = "failed"
        event_row.last_error = type(exc).__name__
        event_row.next_attempt_at = datetime.now(timezone.utc) + timedelta(
            minutes=min(60, 2 ** min(event_row.attempts, 5))
        )
        raise
