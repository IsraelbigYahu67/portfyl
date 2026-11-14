from __future__ import annotations

import models
from database import Base, EXPECTED_ALEMBIC_HEAD
from models import BetaInvite, NotificationOutbox, Transaction, UsageCounter, UsageReservation


def _constraint_names(model) -> set[str]:
    return {
        constraint.name
        for constraint in model.__table__.constraints
        if constraint.name
    }


def test_stripe_billing_models_are_mapped_without_trials():
    # Migration 0025 re-adds a slimmer Stripe Managed Payments runtime; the
    # automatic trials and billing-action idempotency table of 0010 stay gone.
    for name in ("TrialGrant", "BillingAction"):
        assert not hasattr(models, name)
    assert set(Base.metadata.tables).isdisjoint({"billing_actions", "trial_grants"})
    assert {"billing_customers", "subscriptions", "stripe_events"} <= set(Base.metadata.tables)
    assert {"ck_subscription_plan", "ck_subscription_status"} <= _constraint_names(models.Subscription)
    assert {"ck_stripe_event_status", "ck_stripe_event_attempts"} <= _constraint_names(models.StripeEvent)


def test_expected_alembic_head_adds_t212_account_binding():
    assert EXPECTED_ALEMBIC_HEAD == "0026_broker_requests"
    assert models.AllocationTarget.__tablename__ == "allocation_targets"
    for column in (
        "cash_next_page_path", "cash_complete", "cash_loaded",
        "cash_rate_limit_reset_at", "cash_known_streak", "cash_last_page_oldest_at",
    ):
        assert hasattr(models.BrokerSyncRun, column)
    assert hasattr(models.BrokerConnection, "cash_frontier_at")
    assert hasattr(models.BrokerConnection, "cash_frontier_event_id")
    assert "cash" in str(
        next(c for c in models.BrokerSyncEvent.__table__.constraints
             if c.name == "ck_broker_sync_event_stream").sqltext
    )
    assert hasattr(models.BrokerSyncRun, "review_details")
    assert hasattr(models.BrokerConnection, "history_complete_at")
    assert hasattr(models.BrokerSyncRun, "orders_known_streak")
    assert hasattr(Transaction, "source_event_id")
    assert hasattr(Transaction, "executed_at")
    assert hasattr(Transaction, "source_account_fingerprint")
    assert hasattr(models.BrokerConnection, "positions_snapshot_at")
    assert hasattr(models.BrokerConnection, "account_fingerprint")
    assert hasattr(models.Portfolio, "t212_account_fingerprint")


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
