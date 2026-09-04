"""Add cloud billing, trial, entitlement usage, and notification state.

Revision ID: 0010_billing_entitlements
Revises: 0009_audit_log
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_billing_entitlements"
down_revision: Union[str, Sequence[str], None] = "0009_audit_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WORKSPACE = "NULLIF(current_setting('portfyl.workspace_id', true), '')::uuid"


def _tenant_policy(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(f"""
        CREATE POLICY {table}_workspace_policy ON {table}
        USING (workspace_id = {_WORKSPACE})
        WITH CHECK (workspace_id = {_WORKSPACE})
    """)


def upgrade() -> None:
    op.create_table(
        "billing_customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("stripe_customer_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", name="uq_billing_customer_workspace"),
    )
    op.create_index("ix_billing_customers_workspace_id", "billing_customers", ["workspace_id"])
    op.create_index("ix_billing_customers_stripe_customer_id", "billing_customers", ["stripe_customer_id"], unique=True)

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(), nullable=False),
        sa.Column("stripe_price_id", sa.String(), nullable=False),
        sa.Column("plan", sa.String(), nullable=False),
        sa.Column("billing_interval", sa.String(), nullable=False),
        sa.Column("price_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("payment_failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grace_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("plan IN ('investor', 'pro')", name="ck_subscription_plan"),
        sa.CheckConstraint("billing_interval IN ('month', 'year')", name="ck_subscription_interval"),
        sa.CheckConstraint("status IN ('incomplete', 'incomplete_expired', 'trialing', 'active', 'past_due', 'canceled', 'unpaid', 'paused')", name="ck_subscription_status"),
        sa.CheckConstraint("current_period_start IS NULL OR current_period_end IS NULL OR current_period_end > current_period_start", name="ck_subscription_period_order"),
        sa.CheckConstraint("payment_failed_at IS NULL OR grace_ends_at IS NULL OR grace_ends_at > payment_failed_at", name="ck_subscription_grace_order"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscriptions_public_id", "subscriptions", ["public_id"], unique=True)
    op.create_index("ix_subscriptions_workspace_id", "subscriptions", ["workspace_id"])
    op.create_index("ix_subscriptions_stripe_subscription_id", "subscriptions", ["stripe_subscription_id"], unique=True)
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index("ix_subscriptions_ended_at", "subscriptions", ["ended_at"])
    op.create_index("uq_subscription_live_workspace", "subscriptions", ["workspace_id"], unique=True, postgresql_where=sa.text("ended_at IS NULL"))

    op.create_table(
        "trial_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("activated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("identity_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("activation_kind", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("activation_kind IN ('csv_import', 'broker_connection')", name="ck_trial_activation_kind"),
        sa.CheckConstraint("ends_at > started_at", name="ck_trial_period_order"),
        sa.ForeignKeyConstraint(["activated_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", name="uq_trial_workspace"),
        sa.UniqueConstraint("identity_fingerprint", name="uq_trial_identity_fingerprint"),
    )
    op.create_index("ix_trial_grants_public_id", "trial_grants", ["public_id"], unique=True)
    op.create_index("ix_trial_grants_workspace_id", "trial_grants", ["workspace_id"])
    op.create_index("ix_trial_grants_activated_by_user_id", "trial_grants", ["activated_by_user_id"])
    op.create_index("ix_trial_grants_ends_at", "trial_grants", ["ends_at"])

    op.create_table(
        "stripe_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("stripe_event_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("object_id", sa.String(), nullable=True),
        sa.Column("livemode", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'processing', 'processed', 'failed', 'quarantined')", name="ck_stripe_event_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_stripe_event_attempts"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stripe_events_stripe_event_id", "stripe_events", ["stripe_event_id"], unique=True)
    op.create_index("ix_stripe_events_event_type", "stripe_events", ["event_type"])
    op.create_index("ix_stripe_events_object_id", "stripe_events", ["object_id"])
    op.create_index("ix_stripe_events_status", "stripe_events", ["status"])
    op.create_index("ix_stripe_events_next_attempt_at", "stripe_events", ["next_attempt_at"])

    op.create_table(
        "billing_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("stripe_object_id", sa.String(), nullable=True),
        sa.Column("response_url_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "idempotency_key", name="uq_billing_action_idempotency"),
    )
    op.create_index("ix_billing_actions_public_id", "billing_actions", ["public_id"], unique=True)
    op.create_index("ix_billing_actions_workspace_id", "billing_actions", ["workspace_id"])
    op.create_index("ix_billing_actions_actor_user_id", "billing_actions", ["actor_user_id"])

    op.create_table(
        "usage_counters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("used >= 0", name="ck_usage_counter_nonnegative"),
        sa.CheckConstraint("period_end > period_start", name="ck_usage_counter_period_order"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "metric", "period_start", name="uq_usage_counter_period"),
        sa.UniqueConstraint("workspace_id", "id", name="uq_usage_counter_workspace_id"),
    )
    op.create_index("ix_usage_counters_workspace_id", "usage_counters", ["workspace_id"])
    op.create_index("ix_usage_counters_metric", "usage_counters", ["metric"])

    op.create_table(
        "usage_reservations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("counter_id", sa.Uuid(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), server_default="reserved", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount > 0", name="ck_usage_reservation_positive"),
        sa.CheckConstraint("status IN ('reserved', 'finalized', 'released')", name="ck_usage_reservation_status"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "counter_id"],
            ["usage_counters.workspace_id", "usage_counters.id"],
            name="fk_usage_reservation_workspace_counter",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "metric", "idempotency_key", name="uq_usage_reservation_idempotency"),
    )
    op.create_index("ix_usage_reservations_public_id", "usage_reservations", ["public_id"], unique=True)
    op.create_index("ix_usage_reservations_workspace_id", "usage_reservations", ["workspace_id"])
    op.create_index("ix_usage_reservations_counter_id", "usage_reservations", ["counter_id"])
    op.create_index("ix_usage_reservations_metric", "usage_reservations", ["metric"])

    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("deduplication_key", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), server_default="pending", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending', 'sending', 'sent', 'failed')", name="ck_notification_outbox_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_notification_outbox_attempts"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deduplication_key"),
    )
    op.create_index("ix_notification_outbox_public_id", "notification_outbox", ["public_id"], unique=True)
    op.create_index("ix_notification_outbox_workspace_id", "notification_outbox", ["workspace_id"])
    op.create_index("ix_notification_outbox_user_id", "notification_outbox", ["user_id"])
    op.create_index("ix_notification_outbox_kind", "notification_outbox", ["kind"])
    op.create_index("ix_notification_outbox_status", "notification_outbox", ["status"])
    op.create_index("ix_notification_outbox_next_attempt_at", "notification_outbox", ["next_attempt_at"])

    tenant_tables = (
        "billing_customers", "subscriptions", "trial_grants", "billing_actions",
        "usage_counters", "usage_reservations", "notification_outbox",
    )
    for table in tenant_tables:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO portfyl_runtime")
        _tenant_policy(table)
    op.execute("GRANT SELECT, INSERT, UPDATE ON TABLE stripe_events TO portfyl_runtime")


def downgrade() -> None:
    tenant_tables = (
        "notification_outbox", "usage_reservations", "usage_counters",
        "billing_actions", "trial_grants", "subscriptions", "billing_customers",
    )
    for table in tenant_tables:
        op.execute(f"DROP POLICY IF EXISTS {table}_workspace_policy ON {table}")
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
        op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE {table} FROM portfyl_runtime")
    op.execute("REVOKE SELECT, INSERT, UPDATE ON TABLE stripe_events FROM portfyl_runtime")
    for table in (
        "notification_outbox", "usage_reservations", "usage_counters",
        "billing_actions", "stripe_events", "trial_grants", "subscriptions",
        "billing_customers",
    ):
        op.drop_table(table)
