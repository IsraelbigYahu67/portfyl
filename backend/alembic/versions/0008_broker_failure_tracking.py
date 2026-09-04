"""Add dead-letter tracking columns to broker_connections.

Task 6 of docs/superpowers/plans/2026-09-04-portfyl-secrets-jobs.md: a
broker connection that fails every auto-sync pass for
BROKER_AUTOSYNC_FAILURE_THRESHOLD consecutive attempts stops retrying
silently -- jobs.broker_autosync_pass flips auto_sync off and
needs_attention on instead.

Revision ID: 0008_broker_failure_tracking
Revises: 0007_discord_webhook_contract
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_broker_failure_tracking"
down_revision: Union[str, Sequence[str], None] = "0007_discord_webhook_contract"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "broker_connections",
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "broker_connections",
        sa.Column("needs_attention", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("broker_connections", sa.Column("last_error", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("broker_connections", "last_error")
    op.drop_column("broker_connections", "needs_attention")
    op.drop_column("broker_connections", "consecutive_failures")
