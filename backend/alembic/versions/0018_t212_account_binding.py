"""Bind each portfolio to one upstream Trading 212 account.

Revision ID: 0018_t212_account_binding
Revises: 0017_position_snapshot_time
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0018_t212_account_binding"
down_revision: Union[str, Sequence[str], None] = "0017_position_snapshot_time"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("portfolios", sa.Column("t212_account_fingerprint", sa.String(64), nullable=True))
    op.add_column("broker_connections", sa.Column("account_fingerprint", sa.String(64), nullable=True))
    op.add_column("broker_sync_runs", sa.Column("account_fingerprint", sa.String(64), nullable=True))
    op.add_column("broker_sync_events", sa.Column("account_fingerprint", sa.String(64), nullable=True))
    op.add_column("transactions", sa.Column("source_account_fingerprint", sa.String(64), nullable=True))

    op.execute("""
        CREATE UNIQUE INDEX uq_portfolio_t212_account_fingerprint
        ON portfolios (workspace_id, t212_account_fingerprint)
        WHERE t212_account_fingerprint IS NOT NULL
    """)

    op.execute("DROP INDEX IF EXISTS uq_transaction_source_event_identity")
    op.execute("""
        CREATE UNIQUE INDEX uq_transaction_source_event_identity
        ON transactions (
            workspace_id, portfolio_id, source, source_account_fingerprint,
            source_event_stream, source_event_id
        )
        WHERE source_event_id IS NOT NULL AND source_account_fingerprint IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_transaction_source_event_identity_legacy
        ON transactions (workspace_id, portfolio_id, source, source_event_stream, source_event_id)
        WHERE source_event_id IS NOT NULL AND source_account_fingerprint IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_transaction_source_event_identity_legacy")
    op.execute("DROP INDEX IF EXISTS uq_transaction_source_event_identity")
    op.execute("""
        CREATE UNIQUE INDEX uq_transaction_source_event_identity
        ON transactions (workspace_id, portfolio_id, source, source_event_stream, source_event_id)
        WHERE source_event_id IS NOT NULL
    """)
    op.execute("DROP INDEX IF EXISTS uq_portfolio_t212_account_fingerprint")

    op.drop_column("transactions", "source_account_fingerprint")
    op.drop_column("broker_sync_events", "account_fingerprint")
    op.drop_column("broker_sync_runs", "account_fingerprint")
    op.drop_column("broker_connections", "account_fingerprint")
    op.drop_column("portfolios", "t212_account_fingerprint")
