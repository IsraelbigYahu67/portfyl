"""Add durable provider provenance columns to transactions (T212
snapshot-first sync, Task 4 slice: finalize_run's exact-settlement mapping).

Trading 212 Snapshot-First Synchronization Plan
(docs/superpowers/plans/2026-09-20-t212-snapshot-first-sync.md), Task 4
(scoped slice -- see the plan's status note and t212_sync.finalize_run's
docstring for what this increment does and does not cover).

Revision ID: 0016_transaction_provenance
Revises: 0015_broker_sync_runs
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0016_transaction_provenance"
down_revision: Union[str, Sequence[str], None] = "0015_broker_sync_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("source_event_id", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("source_event_stream", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("source_credential_generation", sa.Integer(), nullable=True))
    op.add_column("transactions", sa.Column("source_instrument_id", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("source_fill_type", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("transactions", sa.Column("source_payload_hash", sa.String(), nullable=True))
    op.add_column("transactions", sa.Column("source_mapper_version", sa.String(), nullable=True))

    # Idempotency backstop for t212_sync.finalize_run: re-finalizing an
    # already-finalized staged event (a retried job tick, an overlapping
    # worker) must be a no-op, never a duplicate ledger row. Legacy rows have
    # a NULL source_event_id and are excluded by the WHERE clause -- a
    # partial index, not a SQLAlchemy table constraint, so the SQLite
    # fast-test schema (Base.metadata.create_all) is unaffected.
    op.execute("""
        CREATE UNIQUE INDEX uq_transaction_source_event_identity
        ON transactions (workspace_id, portfolio_id, source, source_event_stream, source_event_id)
        WHERE source_event_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_transaction_source_event_identity")
    op.drop_column("transactions", "source_mapper_version")
    op.drop_column("transactions", "source_payload_hash")
    op.drop_column("transactions", "executed_at")
    op.drop_column("transactions", "source_fill_type")
    op.drop_column("transactions", "source_instrument_id")
    op.drop_column("transactions", "source_credential_generation")
    op.drop_column("transactions", "source_event_stream")
    op.drop_column("transactions", "source_event_id")
