"""Add allocation_targets (target allocation, plan 2026-10-10 Task 2).

Revision ID: 0023_allocation_targets
Revises: 0022_t212_cash_stream
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0023_allocation_targets"
down_revision: Union[str, Sequence[str], None] = "0022_t212_cash_stream"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WORKSPACE_SETTING = "NULLIF(current_setting('portfyl.workspace_id', true), '')::uuid"
_TABLE = "allocation_targets"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=32), nullable=False),
        sa.Column("group_name", sa.String(length=40), nullable=True),
        sa.Column("target_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.CheckConstraint(
            "target_pct >= 0 AND target_pct <= 100",
            name="ck_allocation_target_pct_range",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            name="fk_allocation_target_workspace_portfolio",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "portfolio_id", "ticker", name="uq_allocation_target_ticker",
        ),
    )
    op.create_index("ix_allocation_targets_public_id", _TABLE, ["public_id"], unique=True)
    op.create_index("ix_allocation_targets_workspace_id", _TABLE, ["workspace_id"])
    op.create_index("ix_allocation_targets_portfolio_id", _TABLE, ["portfolio_id"])

    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {_TABLE} TO portfyl_runtime")
    op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {_TABLE}_id_seq TO portfyl_runtime")
    op.execute(f'ALTER TABLE "{_TABLE}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{_TABLE}" FORCE ROW LEVEL SECURITY')
    op.execute(f"""
        CREATE POLICY {_TABLE}_tenant_policy ON {_TABLE}
        USING (workspace_id = {_WORKSPACE_SETTING})
        WITH CHECK (workspace_id = {_WORKSPACE_SETTING})
    """)


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_TABLE}_tenant_policy ON {_TABLE}")
    op.execute(f'ALTER TABLE "{_TABLE}" NO FORCE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{_TABLE}" DISABLE ROW LEVEL SECURITY')
    op.execute(f"REVOKE USAGE, SELECT ON SEQUENCE {_TABLE}_id_seq FROM portfyl_runtime")
    op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE {_TABLE} FROM portfyl_runtime")
    for name in (
        "ix_allocation_targets_portfolio_id",
        "ix_allocation_targets_workspace_id",
        "ix_allocation_targets_public_id",
    ):
        op.drop_index(name, table_name=_TABLE)
    op.drop_table(_TABLE)
