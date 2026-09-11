from __future__ import annotations

import models
from database import Base, EXPECTED_ALEMBIC_HEAD
from models import BetaInvite, NotificationOutbox, UsageCounter, UsageReservation


def _constraint_names(model) -> set[str]:
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if constraint.name
    }


def test_payment_and_trial_models_are_not_mapped():
    for name in (
        "BillingCustomer",
        "Subscription",
        "TrialGrant",
        "StripeEvent",
        "BillingAction",
    ):
        assert not hasattr(models, name)

    assert set(Base.metadata.tables).isdisjoint(
        {
            "billing_actions",
            "billing_customers",
            "stripe_events",
            "subscriptions",
            "trial_grants",
        }
    )


def test_expected_alembic_head_adds_private_beta_invites():
    assert EXPECTED_ALEMBIC_HEAD == "0013_private_beta_invites"
    assert {
        "ck_beta_invites_email_normalized",
        "ck_beta_invites_status",
    } <= _constraint_names(BetaInvite)


def test_provider_neutral_usage_and_notification_constraints_remain():
    assert {
        "ck_usage_counter_nonnegative",
        "ck_usage_counter_period_order",
        "uq_usage_counter_workspace_id",
    } <= _constraint_names(UsageCounter)
    assert {
        "ck_usage_reservation_positive",
        "ck_usage_reservation_status",
        "fk_usage_reservation_workspace_counter",
    } <= _constraint_names(UsageReservation)
    assert {
        "ck_notification_outbox_status",
        "ck_notification_outbox_attempts",
    } <= _constraint_names(NotificationOutbox)
