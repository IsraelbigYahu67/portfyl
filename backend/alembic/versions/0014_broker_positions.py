"""Add broker_positions (T212 snapshot-first sync, Task 2) and expand
broker_balances with the provider's cash/investment components.

Trading 212 Snapshot-First Synchronization Plan
(docs/superpowers/plans/2026-09-20-t212-snapshot-first-sync.md), Task 2:
"Add BrokerPosition, expanded BrokerBalance, ... migration, grants, RLS,
cascade, ... and tenant tests."

Revision ID: 0014_broker_positions
Revises: 0013_private_beta_invites
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_broker_positions"
down_revision: Union[str, Sequence[str], None] = "0013_private_beta_invites"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WORKSPACE_SETTING = "NULLIF(current_setting('portfyl.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.add_column("broker_balances", sa.Column("cash_available", sa.Float(), nullable=True))
    op.add_column("broker_balances", sa.Column("cash_in_pies", sa.Float(), nullable=True))
    op.add_column("broker_balances", sa.Column("cash_reserved", sa.Float(), nullable=True))
    op.add_column("broker_balances", sa.Column("stock_total_cost", sa.Float(), nullable=True))
    op.add_column("broker_balances", sa.Column("stock_unrealized_pnl", sa.Float(), nullable=True))
    op.add_column("broker_balances", sa.Column("broker_realized_pnl", sa.Float(), nullable=True))

    op.create_table(
        "broker_positions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("broker", sa.String(), nullable=False),
        sa.Column("provider_ticker", sa.String(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("currency", sa.String(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("pie_quantity", sa.Float(), nullable=True),
        sa.Column("avg_price", sa.Float(), nullable=False),
        sa.Column("current_price", sa.Float(), nullable=True),
        sa.Column("ppl", sa.Float(), nullable=True),
        sa.Column("fx_ppl", sa.Float(), nullable=True),
        sa.Column("initial_fill_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            name="fk_broker_position_workspace_portfolio",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "broker", "portfolio_id", "provider_ticker",
            name="uq_broker_position_instrument",
        ),
    )
    op.create_index("ix_broker_positions_public_id", "broker_positions", ["public_id"], unique=True)
    op.create_index("ix_broker_positions_workspace_id", "broker_positions", ["workspace_id"])
    op.create_index("ix_broker_positions_portfolio_id", "broker_positions", ["portfolio_id"])
    op.create_index("ix_broker_positions_ticker", "broker_positions", ["ticker"])

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE broker_positions TO portfyl_runtime")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE broker_positions_id_seq TO portfyl_runtime")
    op.execute('ALTER TABLE "broker_positions" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "broker_positions" FORCE ROW LEVEL SECURITY')
    op.execute(f"""
        CREATE POLICY broker_positions_tenant_policy ON broker_positions
        USING (workspace_id = {_WORKSPACE_SETTING})
        WITH CHECK (workspace_id = {_WORKSPACE_SETTING})
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS broker_positions_tenant_policy ON broker_positions")
    op.execute('ALTER TABLE "broker_positions" NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "broker_positions" DISABLE ROW LEVEL SECURITY')
    op.execute("REVOKE USAGE, SELECT ON SEQUENCE broker_positions_id_seq FROM portfyl_runtime")
    op.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE broker_positions FROM portfyl_runtime")

    for name in (
        "ix_broker_positions_ticker", "ix_broker_positions_portfolio_id",
        "ix_broker_positions_workspace_id", "ix_broker_positions_public_id",
    ):
        op.drop_index(name, table_name="broker_positions")
    op.drop_table("broker_positions")

    op.drop_column("broker_balances", "broker_realized_pnl")
    op.drop_column("broker_balances", "stock_unrealized_pnl")
    op.drop_column("broker_balances", "stock_total_cost")
    op.drop_column("broker_balances", "cash_reserved")
    op.drop_column("broker_balances", "cash_in_pies")
    op.drop_column("broker_balances", "cash_available")
