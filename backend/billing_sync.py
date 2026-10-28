"""Project canonical Stripe subscription state into Portfyl (cloud only).

Every write here starts from a Subscription retrieved from the Stripe API
with Portfyl's own key. Webhook payloads only say *which* subscription to
re-fetch, so a replayed, reordered or forged-but-validly-signed event can
never set a status Stripe does not currently report.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from billing_config import BillingConfig
from database import set_rls_context
from models import BillingCustomer, Subscription, Workspace
from stripe_client import StripeClient, StripeClientProtocol, StripeError


log = logging.getLogger("portfyl.billing")

# Stripe's smart retries keep trying a failed renewal for about two weeks;
# paid features stay on for the same window so a card hiccup is not a lockout.
GRACE_PERIOD = timedelta(days=14)
ENTITLED_STATUSES = frozenset({"active", "trialing"})
ENDED_STATUSES = frozenset({"canceled", "incomplete_expired", "unpaid"})
WORKSPACE_METADATA_KEY = "portfyl_workspace_id"

# Webhook-driven writes have no signed-in user. RLS on the billing tables
# only checks portfyl.workspace_id; this never-issued user id keeps every
# user-scoped policy (users, memberships) closed for the session.
SYSTEM_ACTOR_ID = UUID(int=0)


class BillingDataError(ValueError):
    """Stripe state that Portfyl must not apply automatically (unknown price,
    unmapped customer, a second live subscription). Never retried; logged
    for an operator."""


def make_stripe_client(config: BillingConfig) -> StripeClientProtocol:
    if not config.enabled or not config.secret_key:
        raise RuntimeError("Stripe billing is not configured")
    return StripeClient(config.secret_key, api_version=config.api_version)


def _value(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def _id(value: Any) -> str | None:
    """Stripe returns a bare id or, when expanded, the whole object."""
    if isinstance(value, dict):
        return value.get("id")
    return value or None


def _timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


def subscription_id_from_event(event: dict) -> str | None:
    event_type = _value(event, "type", "") or ""
    obj = _value(_value(event, "data", {}), "object", {}) or {}
    if event_type.startswith("customer.subscription."):
        return _value(obj, "id")
    if event_type.startswith("checkout.session."):
        return _id(_value(obj, "subscription"))
    if event_type.startswith("invoice."):
        direct = _id(_value(obj, "subscription"))
        if direct:
            return direct
        parent = _value(obj, "parent", {}) or {}
        details = _value(parent, "subscription_details", {}) or {}
        return _id(_value(details, "subscription"))
    return None


def workspace_public_id_of(remote: dict) -> UUID | None:
    raw = _value(_value(remote, "metadata", {}) or {}, WORKSPACE_METADATA_KEY)
    try:
        return UUID(str(raw)) if raw else None
    except ValueError:
        return None


def _postgres(db: Session) -> bool:
    return db.get_bind().dialect.name == "postgresql"


def resolve_workspace_id(db: Session, public_id: UUID) -> UUID | None:
    """Find a workspace by its public id without a request context.

    Uses the same SELECT-only `portfyl.job_context` policy the scheduler
    jobs use (migration 0003) for exactly one lookup; the flag is cleared
    before returning so nothing else in this session sees other tenants.
    """
    statement = select(Workspace.id).where(
        Workspace.public_id == public_id,
        Workspace.archived_at.is_(None),
    )
    if not _postgres(db):
        return db.scalar(statement)
    db.execute(text("SELECT set_config('portfyl.job_context', 'true', true)"))
    try:
        return db.scalar(statement)
    finally:
        db.execute(text("SELECT set_config('portfyl.job_context', '', true)"))


def scope_to_workspace(db: Session, workspace_id: UUID) -> None:
    if _postgres(db):  # the fast suite's SQLite has neither set_config nor RLS
        set_rls_context(db, user_id=SYSTEM_ACTOR_ID, workspace_id=workspace_id)


def live_subscription(db: Session, workspace_id: UUID) -> Subscription | None:
    return db.scalar(select(Subscription).where(
        Subscription.workspace_id == workspace_id,
        Subscription.ended_at.is_(None),
    ))


def apply_subscription(
    db: Session,
    *,
    workspace_id: UUID,
    remote: dict,
    config: BillingConfig,
    now: datetime | None = None,
) -> Subscription:
    """Upsert the local projection of one retrieved Stripe Subscription.

    The caller must already have scoped `db` to `workspace_id` and commits.
    """
    now = now or datetime.now(timezone.utc)
    stripe_subscription_id = _value(remote, "id")
    customer_id = _id(_value(remote, "customer"))
    if not stripe_subscription_id or not customer_id:
        raise BillingDataError("subscription without id or customer")

    customer = db.scalar(select(BillingCustomer).where(BillingCustomer.workspace_id == workspace_id))
    if customer is None or customer.stripe_customer_id != customer_id:
        raise BillingDataError("subscription customer is not this workspace's customer")

    items = _value(_value(remote, "items", {}) or {}, "data", []) or []
    if len(items) != 1:
        raise BillingDataError("subscription must contain exactly one item")
    price_id = _id(_value(items[0], "price"))
    plan = config.plan_for_price(price_id)
    if plan is None:
        raise BillingDataError("subscription uses a price that maps to no plan")
    # Since API version 2025-03-31 the billing period lives on the item.
    period_end = _value(items[0], "current_period_end") or _value(remote, "current_period_end")

    if _postgres(db):
        # Serialize concurrent webhook / checkout-confirm / reconcile writes
        # for one workspace so the live-subscription check below is stable.
        db.execute(select(Workspace.id).where(Workspace.id == workspace_id).with_for_update())

    row = db.scalar(select(Subscription).where(Subscription.stripe_subscription_id == stripe_subscription_id))
    if row is not None and row.workspace_id != workspace_id:
        raise BillingDataError("subscription already belongs to another workspace")

    status = _value(remote, "status", "incomplete")
    ended = status in ENDED_STATUSES
    if not ended:
        other = db.scalar(select(Subscription.id).where(
            Subscription.workspace_id == workspace_id,
            Subscription.ended_at.is_(None),
            Subscription.stripe_subscription_id != stripe_subscription_id,
        ))
        if other is not None:
            raise BillingDataError("workspace already has another live subscription")

    if row is None:
        row = Subscription(workspace_id=workspace_id, stripe_subscription_id=stripe_subscription_id)
        db.add(row)
    row.stripe_customer_id = customer_id
    row.stripe_price_id = price_id
    row.plan = plan.value
    row.status = status
    row.current_period_end = _timestamp(period_end)
    row.cancel_at_period_end = bool(
        _value(remote, "cancel_at_period_end", False) or _value(remote, "cancel_at")
    )
    if status == "past_due":
        if row.grace_ends_at is None:
            row.grace_ends_at = now + GRACE_PERIOD
    elif status in ENTITLED_STATUSES:
        row.grace_ends_at = None
    row.ended_at = (_timestamp(_value(remote, "ended_at")) or now) if ended else None
    db.flush()
    return row


async def billing_reconcile_pass(db: Session) -> list[dict]:
    """Daily safety net for lost webhooks: re-fetch every billing customer's
    subscriptions from Stripe and converge the local projection."""
    from jobs import _active_workspace_ids, _set_job_workspace_context

    config = BillingConfig.from_env(os.environ)
    if not config.enabled:
        return []
    client = make_stripe_client(config)
    results: list[dict] = []
    for workspace_id in _active_workspace_ids(db):
        _set_job_workspace_context(db, workspace_id)
        customer = db.scalar(select(BillingCustomer).where(BillingCustomer.workspace_id == workspace_id))
        if customer is None:
            db.commit()
            continue
        customer_id = customer.stripe_customer_id
        known = set(db.scalars(select(Subscription.stripe_subscription_id).where(
            Subscription.workspace_id == workspace_id,
        )).all())
        db.commit()  # no transaction (or pooled connection) held across the Stripe call
        try:
            remotes = client.list_subscriptions(customer_id)
        except StripeError as exc:
            results.append({"workspace": str(workspace_id), "status": "retry", "error": exc.code or "stripe_error"})
            continue
        _set_job_workspace_context(db, workspace_id)
        for remote in remotes:
            if _value(remote, "status") in ENDED_STATUSES and _value(remote, "id") not in known:
                continue  # history from before Portfyl tracked it
            try:
                apply_subscription(db, workspace_id=workspace_id, remote=remote, config=config)
            except BillingDataError as exc:
                log.error("billing_reconcile_quarantined subscription=%s reason=%s", _value(remote, "id"), exc)
                results.append({"subscription": _value(remote, "id"), "status": "quarantined"})
        db.commit()
        results.append({"workspace": str(workspace_id), "status": "reconciled"})
    return results
