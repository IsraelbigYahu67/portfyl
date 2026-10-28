"""Add Stripe Managed Payments billing state.

`billing_customers` and `subscriptions` are tenant tables with forced RLS like
every other workspace-scoped table. `stripe_events` is a global webhook
receipt log (Stripe ids only, no payload) outside RLS, like `job_runs`.
Additive only, so it is safe while older instances are still serving.

Revision ID: 0025_stripe_billing
Revises: 0024_remove_ai_assistant
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0025_stripe_billing"
down_revision: Union[str, Sequence[str], None] = "0024_remove_ai_assistant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_WORKSPACE = "NULLIF(current_setting('portfyl.workspace_id', true), '')::uuid"
_TENANT_TABLES = ("billing_customers", "subscriptions")


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
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_billing_customers_workspace_id", "billing_customers", ["workspace_id"], unique=True)
    op.create_index(
        "ix_billing_customers_stripe_customer_id", "billing_customers", ["stripe_customer_id"], unique=True,
    )

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(), nullable=False),
        sa.Column("stripe_customer_id", sa.String(), nullable=False),
        sa.Column("stripe_price_id", sa.String(), nullable=False),
        sa.Column("plan", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("scheduled_plan", sa.String(), nullable=True),
        sa.Column("scheduled_change_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grace_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("plan IN ('investor', 'pro')", name="ck_subscription_plan"),
        sa.CheckConstraint(
            "scheduled_plan IS NULL OR scheduled_plan IN ('investor', 'pro')",
            name="ck_subscription_scheduled_plan",
        ),
        sa.CheckConstraint(
            "status IN ('incomplete', 'incomplete_expired', 'trialing', 'active', "
            "'past_due', 'canceled', 'unpaid', 'paused')",
            name="ck_subscription_status",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscriptions_public_id", "subscriptions", ["public_id"], unique=True)
    op.create_index("ix_subscriptions_workspace_id", "subscriptions", ["workspace_id"])
    op.create_index(
        "ix_subscriptions_stripe_subscription_id", "subscriptions", ["stripe_subscription_id"], unique=True,
    )
    op.create_index(
        "uq_subscription_live_workspace",
        "subscriptions",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )

    op.create_table(
        "stripe_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("stripe_event_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("object_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), server_default="received", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('received', 'processed', 'ignored', 'failed', 'quarantined')",
            name="ck_stripe_event_status",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_stripe_event_attempts"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stripe_events_stripe_event_id", "stripe_events", ["stripe_event_id"], unique=True)

    for table in _TENANT_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO portfyl_runtime")
        _tenant_policy(table)
    # Receipts are never deleted by the app; an operator prunes old rows.
    op.execute("GRANT SELECT, INSERT, UPDATE ON TABLE stripe_events TO portfyl_runtime")


def downgrade() -> None:
    op.execute("REVOKE SELECT, INSERT, UPDATE ON TABLE stripe_events FROM portfyl_runtime")
    for table in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_workspace_policy ON {table}")
        op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE {table} FROM portfyl_runtime")
    op.drop_table("stripe_events")
    op.drop_table("subscriptions")
    op.drop_table("billing_customers")
