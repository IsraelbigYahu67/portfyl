"""T212 cash-transaction stream: run progress, frontier and stream constraint
(plan 2026-10-03, Task D1).

Revision ID: 0022_t212_cash_stream
Revises: 0020_broker_corporate_actions
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0022_t212_cash_stream"
down_revision: Union[str, Sequence[str], None] = "0020_broker_corporate_actions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONSTRAINT = "ck_broker_sync_event_stream"


def upgrade() -> None:
    op.add_column("broker_connections", sa.Column("cash_frontier_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("broker_connections", sa.Column("cash_frontier_event_id", sa.String(), nullable=True))

    op.add_column("broker_sync_runs", sa.Column("cash_next_page_path", sa.String(), nullable=True))
    op.add_column(
        "broker_sync_runs",
        sa.Column("cash_complete", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "broker_sync_runs",
        sa.Column("cash_loaded", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "broker_sync_runs",
        sa.Column("cash_rate_limit_reset_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "broker_sync_runs",
        sa.Column("cash_known_streak", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "broker_sync_runs",
        sa.Column("cash_last_page_oldest_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.drop_constraint(_CONSTRAINT, "broker_sync_events", type_="check")
    op.create_check_constraint(
        _CONSTRAINT, "broker_sync_events", "stream IN ('orders', 'dividends', 'cash')",
    )


def downgrade() -> None:
    # Staged cash events cannot satisfy the old constraint; they are transient
    # operational data, so drop them rather than fail the downgrade.
    op.execute("DELETE FROM broker_sync_events WHERE stream = 'cash'")
    op.drop_constraint(_CONSTRAINT, "broker_sync_events", type_="check")
    op.create_check_constraint(
        _CONSTRAINT, "broker_sync_events", "stream IN ('orders', 'dividends')",
    )

    for name in (
        "cash_last_page_oldest_at", "cash_known_streak", "cash_rate_limit_reset_at",
        "cash_loaded", "cash_complete", "cash_next_page_path",
    ):
        op.drop_column("broker_sync_runs", name)
    op.drop_column("broker_connections", "cash_frontier_event_id")
    op.drop_column("broker_connections", "cash_frontier_at")
