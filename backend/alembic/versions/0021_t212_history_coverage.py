"""Per-stream T212 history coverage checkpoints and incremental-run state.

Revision ID: 0021_t212_history_coverage
Revises: 0019_sync_run_review_details

Revision 0020 is intentionally skipped: it is reserved for
0020_broker_corporate_actions (plan 2026-09-24 Track B, gated on G1), which
re-points its own down_revision here when it lands so Alembic keeps exactly
one head.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0021_t212_history_coverage"
down_revision: Union[str, Sequence[str], None] = "0019_sync_run_review_details"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CONNECTION_COLUMNS = (
    ("history_complete_at", sa.DateTime(timezone=True)),
    ("orders_frontier_at", sa.DateTime(timezone=True)),
    ("orders_frontier_event_id", sa.String()),
    ("dividends_frontier_at", sa.DateTime(timezone=True)),
    ("dividends_frontier_event_id", sa.String()),
    ("last_full_audit_at", sa.DateTime(timezone=True)),
)


def upgrade() -> None:
    for name, column_type in _CONNECTION_COLUMNS:
        op.add_column("broker_connections", sa.Column(name, column_type, nullable=True))

    op.add_column(
        "broker_sync_runs",
        sa.Column("orders_known_streak", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "broker_sync_runs",
        sa.Column("orders_last_page_oldest_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "broker_sync_runs",
        sa.Column("dividends_known_streak", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "broker_sync_runs",
        sa.Column("dividends_last_page_oldest_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("broker_sync_runs", "dividends_last_page_oldest_at")
    op.drop_column("broker_sync_runs", "dividends_known_streak")
    op.drop_column("broker_sync_runs", "orders_last_page_oldest_at")
    op.drop_column("broker_sync_runs", "orders_known_streak")

    for name, _ in reversed(_CONNECTION_COLUMNS):
        op.drop_column("broker_connections", name)
