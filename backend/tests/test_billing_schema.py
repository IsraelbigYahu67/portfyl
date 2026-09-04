from __future__ import annotations

from models import (
    BillingAction,
    BillingCustomer,
    NotificationOutbox,
    StripeEvent,
    Subscription,
    TrialGrant,
    UsageCounter,
    UsageReservation,
)


def _constraint_names(model) -> set[str]:
    return {constraint.name for constraint in model.__table__.constraints if constraint.name}


def test_billing_schema_contains_only_minimal_provider_projection():
    assert set(StripeEvent.__table__.columns.keys()) == {
        "id", "stripe_event_id", "event_type", "object_id", "livemode", "status",
        "attempts", "last_error", "received_at", "processed_at", "next_attempt_at",
    }
    forbidden = {"payload", "raw_body", "email", "address", "card", "payment_method"}
    for model in (BillingCustomer, Subscription, StripeEvent, BillingAction):
        assert forbidden.isdisjoint(set(model.__table__.columns.keys()))


def test_billing_models_declare_closed_states_and_time_ordering():
    assert {
        "ck_subscription_plan",
        "ck_subscription_interval",
        "ck_subscription_status",
        "ck_subscription_period_order",
        "ck_subscription_grace_order",
    } <= _constraint_names(Subscription)
    assert {"ck_trial_activation_kind", "ck_trial_period_order"} <= _constraint_names(TrialGrant)
    assert {"ck_stripe_event_status", "ck_stripe_event_attempts"} <= _constraint_names(StripeEvent)
    assert {
        "ck_usage_counter_nonnegative", "ck_usage_counter_period_order",
        "uq_usage_counter_workspace_id",
    } <= _constraint_names(UsageCounter)
    assert {
        "ck_usage_reservation_positive", "ck_usage_reservation_status",
        "fk_usage_reservation_workspace_counter",
    } <= _constraint_names(UsageReservation)
    assert {"ck_notification_outbox_status", "ck_notification_outbox_attempts"} <= _constraint_names(NotificationOutbox)
