"""Small Stripe boundary; tests replace this gateway and never call Stripe."""

from __future__ import annotations

from typing import Any, Protocol

from billing_config import BillingConfig, BillingInterval, PlanTier


class StripeGatewayProtocol(Protocol):
    def construct_event(self, payload: bytes, signature: str, secret: str) -> dict: ...
    def create_customer(self, *, email: str, workspace_public_id: str, idempotency_key: str) -> Any: ...
    def create_checkout(self, **kwargs) -> Any: ...
    def retrieve_checkout(self, session_id: str) -> Any: ...
    def create_portal(self, *, customer_id: str, return_url: str) -> Any: ...
    def retrieve_subscription(self, subscription_id: str) -> Any: ...
    def list_subscriptions(self, customer_id: str) -> list[Any]: ...


class StripeGateway:
    def __init__(self, config: BillingConfig):
        if not config.enabled or not config.secret_key:
            raise RuntimeError("Stripe billing is not configured")
        try:
            import stripe
        except ImportError as exc:  # pragma: no cover - deployment dependency guard
            raise RuntimeError("Stripe SDK is not installed") from exc
        stripe.api_key = config.secret_key
        self.stripe = stripe

    def construct_event(self, payload: bytes, signature: str, secret: str) -> dict:
        return self.stripe.Webhook.construct_event(payload, signature, secret)

    def create_customer(self, *, email: str, workspace_public_id: str, idempotency_key: str):
        return self.stripe.Customer.create(
            email=email,
            metadata={"portfyl_workspace_id": workspace_public_id},
            idempotency_key=idempotency_key,
        )

    def create_checkout(
        self,
        *,
        customer_id: str,
        price_id: str,
        workspace_public_id: str,
        success_url: str,
        cancel_url: str,
        idempotency_key: str,
    ):
        return self.stripe.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            client_reference_id=workspace_public_id,
            line_items=[{"price": price_id, "quantity": 1}],
            automatic_tax={"enabled": True},
            billing_address_collection="required",
            customer_update={"address": "auto", "name": "auto"},
            tax_id_collection={"enabled": True},
            metadata={"portfyl_workspace_id": workspace_public_id},
            subscription_data={"metadata": {"portfyl_workspace_id": workspace_public_id}},
            success_url=success_url,
            cancel_url=cancel_url,
            idempotency_key=idempotency_key,
        )

    def retrieve_checkout(self, session_id: str):
        return self.stripe.checkout.Session.retrieve(session_id)

    def create_portal(self, *, customer_id: str, return_url: str):
        return self.stripe.billing_portal.Session.create(customer=customer_id, return_url=return_url)

    def retrieve_subscription(self, subscription_id: str):
        return self.stripe.Subscription.retrieve(subscription_id)

    def list_subscriptions(self, customer_id: str) -> list[Any]:
        result = self.stripe.Subscription.list(customer=customer_id, status="all", limit=100)
        return list(result.auto_paging_iter())


def object_value(obj: Any, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)
