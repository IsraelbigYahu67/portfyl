"""Cloud-only billing API: Stripe Managed Payments checkout, Customer Portal
and the Stripe webhook.

Stripe (through Link) is the merchant of record. Portfyl never sees card
data; it creates hosted Checkout / Portal sessions and projects the
resulting Subscription into `subscriptions` (billing_sync.py), from which
entitlements.resolve_entitlements derives the plan.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from audit import record_audit_event
from billing_config import CHECKOUT_CONSENT_VERSION, MONTHLY_PRICE_CENTS, BillingConfig
from billing_sync import (
    BillingDataError,
    apply_subscription,
    live_subscription,
    make_stripe_client,
    resolve_workspace_id,
    scope_to_workspace,
    subscription_id_from_event,
    workspace_public_id_of,
)
from database import get_db, release_connection
from entitlements import resolve_entitlements
from models import BillingCustomer, StripeEvent
from plans import PlanTier
from stripe_client import InvalidWebhookSignature, StripeClientProtocol, StripeError, verify_webhook
from tenancy import RequestContext, get_request_context, require_csrf


log = logging.getLogger("portfyl.billing")

router = APIRouter(prefix="/billing", tags=["billing"])
# Mounted separately in main.py: Stripe authenticates with its signature,
# not a session cookie, so this router needs no request context.
webhook_router = APIRouter(prefix="/billing", tags=["billing"])

RELEVANT_EVENT_PREFIXES = ("customer.subscription.", "invoice.", "checkout.session.")


class CheckoutPayload(BaseModel):
    plan: PlanTier
    # The customer's explicit request to start the service immediately and
    # acknowledgement that this ends the EU 14-day withdrawal right
    # (Directive 2011/83/EU art. 16(m)). Managed Payments checkout cannot show
    # custom text, so Portfyl collects it before redirecting.
    accept_immediate_start: bool = False


class CheckoutConfirmPayload(BaseModel):
    session_id: str = Field(min_length=1, max_length=255)


def get_billing_config(request: Request) -> BillingConfig:
    return request.app.state.billing_config


def get_stripe_client(config: BillingConfig = Depends(get_billing_config)) -> StripeClientProtocol:
    if not config.enabled:
        raise HTTPException(status_code=503, detail={"code": "billing_unavailable"})
    return make_stripe_client(config)


def _require_owner(context: RequestContext) -> None:
    if context.membership.role != "owner":
        raise HTTPException(status_code=403, detail={"code": "workspace_owner_required"})


def _stripe_unavailable(exc: StripeError) -> HTTPException:
    log.warning("stripe_request_failed status=%s code=%s", exc.status, exc.code)
    return HTTPException(status_code=502, detail={"code": "payment_provider_unavailable"})


def _status_payload(db: Session, request: Request, context: RequestContext) -> dict:
    config: BillingConfig = request.app.state.billing_config
    access = resolve_entitlements(db, edition=request.app.state.portfyl_edition, workspace_id=context.workspace.id)
    subscription = live_subscription(db, context.workspace.id)
    has_customer = db.scalar(
        select(BillingCustomer.id).where(BillingCustomer.workspace_id == context.workspace.id)
    ) is not None
    return {
        **access.payload(),
        "billing_enabled": config.enabled,
        "can_manage_billing": context.membership.role == "owner",
        "has_billing_account": has_customer,
        "consent_version": CHECKOUT_CONSENT_VERSION,
        "prices": {
            "currency": "eur",
            "monthly_cents": {plan.value: cents for plan, cents in MONTHLY_PRICE_CENTS.items()},
        },
        "subscription": None if subscription is None else {
            "plan": subscription.plan,
            "status": subscription.status,
            "current_period_end": (
                subscription.current_period_end.isoformat() if subscription.current_period_end else None
            ),
            "cancel_at_period_end": bool(subscription.cancel_at_period_end),
            "grace_ends_at": subscription.grace_ends_at.isoformat() if subscription.grace_ends_at else None,
        },
    }


@router.get("/status")
def billing_status(
    request: Request,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(get_request_context),
):
    return _status_payload(db, request, context)


@router.post("/checkout")
def create_checkout(
    payload: CheckoutPayload,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_csrf),
    config: BillingConfig = Depends(get_billing_config),
    client: StripeClientProtocol = Depends(get_stripe_client),
):
    _require_owner(context)
    if payload.plan is PlanTier.FREE:
        raise HTTPException(status_code=422, detail={"code": "paid_plan_required"})
    if not payload.accept_immediate_start:
        raise HTTPException(status_code=422, detail={"code": "immediate_start_consent_required"})
    if live_subscription(db, context.workspace.id) is not None:
        # Plan changes and cancellation of an existing subscription go
        # through the Customer Portal, never a second Checkout.
        raise HTTPException(status_code=409, detail={"code": "subscription_exists"})

    workspace_public_id = str(context.workspace.public_id)
    customer = db.scalar(select(BillingCustomer).where(BillingCustomer.workspace_id == context.workspace.id))
    customer_id = customer.stripe_customer_id if customer else None
    release_connection(db, commit_pending=True)
    try:
        if customer_id is None:
            remote_customer = client.create_customer(
                email=context.user.email,
                workspace_public_id=workspace_public_id,
                idempotency_key=f"customer:{workspace_public_id}",
            )
            customer_id = remote_customer["id"]
        # Repeated clicks within the same ten minutes reuse one session.
        bucket = int(datetime.now(timezone.utc).timestamp() // 600)
        session = client.create_checkout_session(
            {
                "mode": "subscription",
                "managed_payments": {"enabled": True},
                "customer": customer_id,
                "client_reference_id": workspace_public_id,
                "line_items": [{"price": config.price_id(payload.plan), "quantity": 1}],
                "metadata": {"portfyl_workspace_id": workspace_public_id, "portfyl_plan": payload.plan.value},
                "subscription_data": {"metadata": {"portfyl_workspace_id": workspace_public_id}},
                "success_url": f"{config.app_url}/pricing?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
                "cancel_url": f"{config.app_url}/pricing?checkout=canceled",
            },
            idempotency_key=f"checkout:{workspace_public_id}:{payload.plan.value}:{bucket}",
        )
    except StripeError as exc:
        raise _stripe_unavailable(exc) from exc

    if customer is None:
        db.add(BillingCustomer(workspace_id=context.workspace.id, stripe_customer_id=customer_id))
        try:
            db.flush()
        except IntegrityError:
            # A concurrent request stored the same customer first.
            db.rollback()
    record_audit_event(
        db,
        actor_user_id=context.user.id,
        workspace_id=context.workspace.id,
        action="billing.checkout.created",
        target_type="workspace",
        target_id=workspace_public_id,
        metadata={
            "plan": payload.plan.value,
            "immediate_start_consent": True,
            "consent_version": CHECKOUT_CONSENT_VERSION,
        },
    )
    db.commit()
    return {"url": session["url"]}


@router.post("/checkout/confirm")
def confirm_checkout(
    payload: CheckoutConfirmPayload,
    request: Request,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_csrf),
    config: BillingConfig = Depends(get_billing_config),
    client: StripeClientProtocol = Depends(get_stripe_client),
):
    """Called by the pricing page after Stripe redirects back, so the new
    plan is active immediately instead of whenever the webhook lands."""
    release_connection(db, commit_pending=True)
    try:
        session = client.retrieve_checkout_session(payload.session_id)
    except StripeError as exc:
        if exc.status == 404:
            raise HTTPException(status_code=404, detail={"code": "checkout_not_found"}) from exc
        raise _stripe_unavailable(exc) from exc
    if session.get("client_reference_id") != str(context.workspace.public_id):
        raise HTTPException(status_code=404, detail={"code": "checkout_not_found"})
    subscription_id = session.get("subscription")
    if isinstance(subscription_id, dict):
        subscription_id = subscription_id.get("id")
    if session.get("status") == "complete" and subscription_id:
        try:
            remote = client.retrieve_subscription(subscription_id)
        except StripeError as exc:
            raise _stripe_unavailable(exc) from exc
        try:
            apply_subscription(db, workspace_id=context.workspace.id, remote=remote, config=config)
            db.commit()
        except BillingDataError as exc:
            db.rollback()
            log.error("checkout_confirm_quarantined subscription=%s reason=%s", subscription_id, exc)
        except IntegrityError:
            db.rollback()  # the webhook stored it concurrently; the status below reflects it
    return {"checkout_status": session.get("status"), **_status_payload(db, request, context)}


@router.post("/portal")
def create_portal(
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_csrf),
    config: BillingConfig = Depends(get_billing_config),
    client: StripeClientProtocol = Depends(get_stripe_client),
):
    _require_owner(context)
    customer = db.scalar(select(BillingCustomer).where(BillingCustomer.workspace_id == context.workspace.id))
    if customer is None:
        raise HTTPException(status_code=404, detail={"code": "billing_account_not_found"})
    customer_id = customer.stripe_customer_id
    release_connection(db, commit_pending=True)
    try:
        session = client.create_portal_session(customer_id=customer_id, return_url=f"{config.app_url}/pricing")
    except StripeError as exc:
        raise _stripe_unavailable(exc) from exc
    return {"url": session["url"]}


async def _raw_body(request: Request) -> bytes:
    # The signature covers the exact bytes Stripe sent, so read them before
    # any JSON parsing. Async only to await the body; it touches no database.
    return await request.body()


def _mark(db: Session, row: StripeEvent, status: str, error: str | None = None) -> None:
    row.status = status
    row.last_error = error
    if status in ("processed", "ignored"):
        row.processed_at = datetime.now(timezone.utc)
    db.commit()


@webhook_router.post("/webhook")
def stripe_webhook(
    payload: bytes = Depends(_raw_body),
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
    db: Session = Depends(get_db),
    config: BillingConfig = Depends(get_billing_config),
):
    if not config.enabled or not config.webhook_secret:
        raise HTTPException(status_code=503, detail={"code": "billing_unavailable"})
    try:
        event = verify_webhook(payload, stripe_signature, config.webhook_secret)
    except InvalidWebhookSignature as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_signature"}) from exc
    event_id = event.get("id")
    event_type = event.get("type") or ""
    if not event_id or bool(event.get("livemode")) != config.livemode:
        raise HTTPException(status_code=400, detail={"code": "event_mode_mismatch"})

    subscription_id = subscription_id_from_event(event)
    row = db.scalar(select(StripeEvent).where(StripeEvent.stripe_event_id == event_id))
    if row is None:
        row = StripeEvent(stripe_event_id=event_id, event_type=event_type, object_id=subscription_id)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            # A parallel delivery of the same event is being handled.
            db.rollback()
            return {"received": True, "duplicate": True}
    elif row.status in ("processed", "ignored", "quarantined"):
        return {"received": True, "duplicate": True}

    if not event_type.startswith(RELEVANT_EVENT_PREFIXES) or not subscription_id:
        _mark(db, row, "ignored")
        return {"received": True}

    row.attempts += 1
    db.commit()
    release_connection(db)
    try:
        remote = make_stripe_client(config).retrieve_subscription(subscription_id)
    except StripeError as exc:
        if exc.transient:
            _mark(db, row, "failed", exc.code or "stripe_unavailable")
            # Non-2xx makes Stripe redeliver the event with backoff.
            raise HTTPException(status_code=503, detail={"code": "retry_later"}) from exc
        _mark(db, row, "quarantined", exc.code or "stripe_error")
        return {"received": True}

    workspace_public_id = workspace_public_id_of(remote)
    workspace_id = resolve_workspace_id(db, workspace_public_id) if workspace_public_id else None
    if workspace_id is None:
        log.error("stripe_webhook_unmapped event=%s subscription=%s", event_id, subscription_id)
        _mark(db, row, "quarantined", "workspace_not_found")
        return {"received": True}

    scope_to_workspace(db, workspace_id)
    try:
        apply_subscription(db, workspace_id=workspace_id, remote=remote, config=config)
    except BillingDataError as exc:
        db.rollback()
        log.error("stripe_webhook_quarantined event=%s subscription=%s reason=%s", event_id, subscription_id, exc)
        _mark(db, row, "quarantined", str(exc)[:200])
        return {"received": True}
    except IntegrityError as exc:
        db.rollback()
        _mark(db, row, "failed", "concurrent_update")
        raise HTTPException(status_code=503, detail={"code": "retry_later"}) from exc
    _mark(db, row, "processed")
    return {"received": True}
