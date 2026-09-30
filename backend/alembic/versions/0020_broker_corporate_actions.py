"""Add broker_corporate_actions and broker_corporate_action_applications
(T212 corporate actions, plan 2026-09-24 Track B1).

Numbered 0020 but revises 0021: Track C shipped first and left the number free.

Revision ID: 0020_broker_corporate_actions
Revises: 0021_t212_history_coverage
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0020_broker_corporate_actions"
down_revision: Union[str, Sequence[str], None] = "0021_t212_history_coverage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WORKSPACE_SETTING = "NULLIF(current_setting('portfyl.workspace_id', true), '')::uuid"
_TABLES = ("broker_corporate_actions", "broker_corporate_action_applications")


def upgrade() -> None:
    op.create_table(
        "broker_corporate_actions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("broker", sa.String(), nullable=False),
        sa.Column("account_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("provider_instrument_id", sa.String(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("action_type", sa.String(), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_event_key", sa.String(), nullable=False),
        sa.Column("ratio_numerator", sa.Numeric(20, 10), nullable=False),
        sa.Column("ratio_denominator", sa.Numeric(20, 10), nullable=False),
        sa.Column("representation", sa.String(), nullable=False),
        # Audit integer only, no FK: runs are purgeable operational data.
        sa.Column("run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "representation IN ('api_normalized', 'csv_rows')",
            name="ck_broker_corporate_action_representation",
        ),
        sa.CheckConstraint(
            "ratio_numerator > 0 AND ratio_denominator > 0",
            name="ck_broker_corporate_action_ratio_positive",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            name="fk_broker_corporate_action_workspace_portfolio",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "portfolio_id", "account_fingerprint", "provider_instrument_id",
            "action_type", "effective_at", "provider_event_key",
            name="uq_broker_corporate_action_identity",
        ),
        # Required before the applications' composite FK can reference it.
        sa.UniqueConstraint("workspace_id", "id", name="uq_broker_corporate_action_workspace_id"),
    )
    op.create_index("ix_broker_corporate_actions_public_id", "broker_corporate_actions", ["public_id"], unique=True)
    op.create_index("ix_broker_corporate_actions_workspace_id", "broker_corporate_actions", ["workspace_id"])
    op.create_index("ix_broker_corporate_actions_portfolio_id", "broker_corporate_actions", ["portfolio_id"])

    op.create_table(
        "broker_corporate_action_applications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("action_id", sa.Integer(), nullable=False),
        sa.Column("transaction_id", sa.Integer(), nullable=False),
        sa.Column("shares_before", sa.Float(), nullable=False),
        sa.Column("price_before", sa.Float(), nullable=False),
        sa.Column("shares_after", sa.Float(), nullable=False),
        sa.Column("price_after", sa.Float(), nullable=False),
        sa.Column("applied_by_run_id", sa.Integer(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "action_id"],
            ["broker_corporate_actions.workspace_id", "broker_corporate_actions.id"],
            name="fk_broker_ca_application_workspace_action",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "transaction_id"],
            ["transactions.workspace_id", "transactions.id"],
            name="fk_broker_ca_application_workspace_transaction",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "action_id", "transaction_id",
            name="uq_broker_corporate_action_application",
        ),
    )
    op.create_index(
        "ix_broker_corporate_action_applications_workspace_id",
        "broker_corporate_action_applications", ["workspace_id"],
    )
    op.create_index(
        "ix_broker_corporate_action_applications_action_id",
        "broker_corporate_action_applications", ["action_id"],
    )
    op.create_index(
        "ix_broker_corporate_action_applications_transaction_id",
        "broker_corporate_action_applications", ["transaction_id"],
    )

    for table in _TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO portfyl_runtime")
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO portfyl_runtime")
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(f"""
            CREATE POLICY {table}_tenant_policy ON {table}
            USING (workspace_id = {_WORKSPACE_SETTING})
            WITH CHECK (workspace_id = {_WORKSPACE_SETTING})
        """)


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_policy ON {table}")
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
        op.execute(f"REVOKE USAGE, SELECT ON SEQUENCE {table}_id_seq FROM portfyl_runtime")
        op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE {table} FROM portfyl_runtime")

    for name in (
        "ix_broker_corporate_action_applications_transaction_id",
        "ix_broker_corporate_action_applications_action_id",
        "ix_broker_corporate_action_applications_workspace_id",
    ):
        op.drop_index(name, table_name="broker_corporate_action_applications")
    op.drop_table("broker_corporate_action_applications")

    for name in (
        "ix_broker_corporate_actions_portfolio_id",
        "ix_broker_corporate_actions_workspace_id",
        "ix_broker_corporate_actions_public_id",
    ):
        op.drop_index(name, table_name="broker_corporate_actions")
    op.drop_table("broker_corporate_actions")
