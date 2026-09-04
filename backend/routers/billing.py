"""Cloud-only billing, entitlement, Stripe Checkout, Portal, and webhook API."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from audit import record_audit_event
from billing_config import BillingConfig, BillingInterval, PlanTier, PUBLIC_PRICES
from billing_reconciliation import subscription_id_from_event
from database import get_db
from edition import Edition
from entitlements import resolve_entitlements
from models import BillingAction, BillingCustomer, StripeEvent, Subscription, UsageCounter, Workspace
from stripe_service import StripeGateway, StripeGatewayProtocol, object_value
from tenancy import RequestContext, get_request_context, require_csrf


router = APIRouter(prefix="/billing", tags=["billing"])


class CheckoutPayload(BaseModel):
    plan: PlanTier
    interval: BillingInterval


def get_billing_config(request: Request) -> BillingConfig:
    return request.app.state.billing_config


def get_billing_gateway(
    config: BillingConfig = Depends(get_billing_config),
) -> StripeGatewayProtocol:
    if not config.enabled:
        raise HTTPException(status_code=503, detail={"code": "billing_unavailable"})
    return StripeGateway(config)


def _require_owner(context: RequestContext) -> None:
    if context.membership.role != "owner":
        raise HTTPException(status_code=403, detail={"code": "workspace_owner_required"})


@router.get("/prices")
def prices():
    return {
        "currency": "eur",
        "prices": [
            {
                "plan": item.plan.value,
                "interval": item.interval.value,
                "amount_cents": item.amount_cents,
            }
            for item in PUBLIC_PRICES.values()
        ],
    }


@router.get("/entitlements")
def current_entitlements(
    request: Request,
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    access = resolve_entitlements(
        db,
        edition=request.app.state.portfyl_edition,
        workspace_id=context.workspace.id,
        env=os.environ,
    )
    result = access.payload()
    now = datetime.now(timezone.utc)
    counters = db.scalars(select(UsageCounter).where(
        UsageCounter.workspace_id == context.workspace.id,
        UsageCounter.period_end > now,
    )).all()
    usage = {row.metric: {"used": row.used, "period_end": row.period_end.isoformat()} for row in counters}
    hosted_limit = access.limits.hosted_ai_monthly
    hosted_metric = "hosted_ai_trial" if access.source == "trial" else "hosted_ai_monthly"
    hosted_used = usage.get(hosted_metric, {}).get("used", 0)
    usage[hosted_metric] = {
        **usage.get(hosted_metric, {}),
        "used": hosted_used,
        "limit": hosted_limit,
        "remaining": max(0, hosted_limit - hosted_used),
    }
    result["usage"] = usage
    return result


@router.post("/checkout")
def checkout(
    payload: CheckoutPayload,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    context: RequestContext = Depends(require_csrf),
    db: Session = Depends(get_db),
    config: BillingConfig = Depends(get_billing_config),
    gateway: StripeGatewayProtocol = Depends(get_billing_gateway),
):
    _require_owner(context)
    if payload.plan is PlanTier.FREE:
        raise HTTPException(status_code=422, detail={"code": "paid_plan_required"})
    key = (idempotency_key or "").strip()
    if not key or len(key) > 255:
        raise HTTPException(status_code=400, detail={"code": "idempotency_key_required"})
    now = datetime.now(timezone.utc)
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            select(Workspace.id)
            .where(Workspace.id == context.workspace.id)
            .with_for_update()
        )
    fingerprint = hashlib.sha256(
        json.dumps(payload.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()
    prior = db.scalar(select(BillingAction).where(
        BillingAction.workspace_id == context.workspace.id,
        BillingAction.idempotency_key == key,
    ))
    if prior is not None:
        if prior.request_fingerprint != fingerprint:
            raise HTTPException(status_code=409, detail={"code": "idempotency_key_reused"})
        if prior.stripe_object_id:
            session = gateway.retrieve_checkout(prior.stripe_object_id)
            return {"url": object_value(session, "url"), "pending": True}

    if db.scalar(select(Subscription.id).where(
        Subscription.workspace_id == context.workspace.id,
        Subscription.ended_at.is_(None),
    )) is not None:
        raise HTTPException(status_code=409, detail={"code": "subscription_already_exists"})
    if db.scalar(select(BillingAction.id).where(
        BillingAction.workspace_id == context.workspace.id,
        BillingAction.action == "checkout.create",
        BillingAction.response_url_expires_at > now,
    )) is not None:
        raise HTTPException(status_code=409, detail={"code": "checkout_pending"})

    customer = db.scalar(select(BillingCustomer).where(BillingCustomer.workspace_id == context.workspace.id))
    if customer is None:
        remote_customer = gateway.create_customer(
            email=context.user.email,
            workspace_public_id=str(context.workspace.public_id),
            idempotency_key=f"customer:{context.workspace.public_id}",
        )
        customer = BillingCustomer(
            workspace_id=context.workspace.id,
            stripe_customer_id=object_value(remote_customer, "id"),
        )
        db.add(customer)
        db.flush()

    session = gateway.create_checkout(
        customer_id=customer.stripe_customer_id,
        price_id=config.price_id(payload.plan, payload.interval),
        workspace_public_id=str(context.workspace.public_id),
        success_url=f"{config.app_url}/pricing?billing=success",
        cancel_url=f"{config.app_url}/pricing?billing=canceled",
        idempotency_key=f"checkout:{context.workspace.public_id}:{key}",
    )
    action = prior or BillingAction(
        workspace_id=context.workspace.id,
        actor_user_id=context.user.id,
        idempotency_key=key,
        action="checkout.create",
        request_fingerprint=fingerprint,
    )
    action.stripe_object_id = object_value(session, "id")
    action.response_url_expires_at = now + timedelta(hours=1)
    if prior is None:
        db.add(action)
    db.flush()
    record_audit_event(
        db,
        actor_user_id=context.user.id,
        workspace_id=context.workspace.id,
        action="billing.checkout.created",
        target_type="billing_action",
        target_id=str(action.public_id),
        metadata={"plan": payload.plan.value, "interval": payload.interval.value},
    )
    db.commit()
    return {"url": object_value(session, "url"), "pending": True}


@router.post("/portal")
def portal(
    context: RequestContext = Depends(require_csrf),
    db: Session = Depends(get_db),
    config: BillingConfig = Depends(get_billing_config),
    gateway: StripeGatewayProtocol = Depends(get_billing_gateway),
):
    _require_owner(context)
    customer = db.scalar(select(BillingCustomer).where(BillingCustomer.workspace_id == context.workspace.id))
    if customer is None:
        raise HTTPException(status_code=404, detail={"code": "billing_customer_not_found"})
    session = gateway.create_portal(
        customer_id=customer.stripe_customer_id,
        return_url=f"{config.app_url}/pricing",
    )
    record_audit_event(
        db,
        actor_user_id=context.user.id,
        workspace_id=context.workspace.id,
        action="billing.portal.created",
        target_type="billing_customer",
        target_id=str(customer.id),
    )
    db.commit()
    return {"url": object_value(session, "url")}


@router.post("/webhook")
async def webhook(
    request: Request,
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
    db: Session = Depends(get_db),
    config: BillingConfig = Depends(get_billing_config),
    gateway: StripeGatewayProtocol = Depends(get_billing_gateway),
):
    if not stripe_signature or not config.webhook_secret:
        raise HTTPException(status_code=400, detail={"code": "invalid_signature"})
    raw = await request.body()
    try:
        event = gateway.construct_event(raw, stripe_signature, config.webhook_secret)
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_signature"}) from exc
    event_id = object_value(event, "id")
    event_type = object_value(event, "type", "")
    livemode = bool(object_value(event, "livemode", False))
    expected_livemode = bool(config.secret_key and config.secret_key.startswith("sk_live_"))
    if not event_id or livemode != expected_livemode:
        raise HTTPException(status_code=400, detail={"code": "event_mode_mismatch"})
    if db.scalar(select(StripeEvent).where(StripeEvent.stripe_event_id == event_id)):
        return {"received": True, "duplicate": True}
    row = StripeEvent(
        stripe_event_id=event_id,
        event_type=event_type,
        object_id=subscription_id_from_event(event),
        livemode=livemode,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
        db.commit()
    except IntegrityError:
        db.rollback()
        return {"received": True, "duplicate": True}
    return {"received": True, "duplicate": False}
