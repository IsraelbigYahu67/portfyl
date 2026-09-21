"""Add broker_sync_runs and broker_sync_events (T212 snapshot-first sync,
Task 3: resumable history runs), and BrokerConnection.credential_generation.

Trading 212 Snapshot-First Synchronization Plan
(docs/superpowers/plans/2026-09-20-t212-snapshot-first-sync.md), Task 3.

Revision ID: 0015_broker_sync_runs
Revises: 0014_broker_positions
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015_broker_sync_runs"
down_revision: Union[str, Sequence[str], None] = "0014_broker_positions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WORKSPACE_SETTING = "NULLIF(current_setting('portfyl.workspace_id', true), '')::uuid"


def upgrade() -> None:
    op.add_column(
        "broker_connections",
        sa.Column("credential_generation", sa.Integer(), nullable=False, server_default="1"),
    )
    # Required before broker_sync_runs' composite FK below can reference
    # (workspace_id, id) -- Postgres needs an actual unique constraint on
    # that exact tuple, not just id's own primary-key uniqueness.
    op.create_unique_constraint(
        "uq_broker_connection_workspace_id", "broker_connections", ["workspace_id", "id"],
    )

    op.create_table(
        "broker_sync_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("broker", sa.String(), nullable=False),
        sa.Column("credential_generation", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(), server_default="incremental", nullable=False),
        sa.Column("state", sa.String(), server_default="pending", nullable=False),
        sa.Column("orders_next_page_path", sa.String(), nullable=True),
        sa.Column("orders_complete", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("orders_loaded", sa.Integer(), server_default="0", nullable=False),
        sa.Column("orders_rate_limit_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dividends_next_page_path", sa.String(), nullable=True),
        sa.Column("dividends_complete", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("dividends_loaded", sa.Integer(), server_default="0", nullable=False),
        sa.Column("dividends_rate_limit_reset_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("mode IN ('initial', 'incremental', 'audit')", name="ck_broker_sync_run_mode"),
        sa.CheckConstraint(
            "state IN ('pending','fetching','waiting_rate_limit','finalizing',"
            "'completed','needs_review','failed','cancelled')",
            name="ck_broker_sync_run_state",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            name="fk_broker_sync_run_workspace_portfolio",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "connection_id"],
            ["broker_connections.workspace_id", "broker_connections.id"],
            name="fk_broker_sync_run_workspace_connection",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        # Required before broker_sync_events' composite FK below can
        # reference (workspace_id, id).
        sa.UniqueConstraint("workspace_id", "id", name="uq_broker_sync_run_workspace_id"),
    )
    op.create_index("ix_broker_sync_runs_public_id", "broker_sync_runs", ["public_id"], unique=True)
    op.create_index("ix_broker_sync_runs_workspace_id", "broker_sync_runs", ["workspace_id"])
    op.create_index("ix_broker_sync_runs_portfolio_id", "broker_sync_runs", ["portfolio_id"])
    op.create_index("ix_broker_sync_runs_connection_id", "broker_sync_runs", ["connection_id"])
    # Application-level claim_or_create_run already treats "one active run
    # per connection" as idempotent (returns the existing row instead of
    # inserting), but a genuine concurrent double-click race needs a DB-level
    # backstop -- a partial unique index, not a SQLAlchemy table constraint,
    # so the SQLite fast-test schema (Base.metadata.create_all) is unaffected
    # and doesn't need a dialect-conditional model.
    op.execute("""
        CREATE UNIQUE INDEX uq_broker_sync_run_one_active_per_connection
        ON broker_sync_runs (workspace_id, connection_id)
        WHERE state NOT IN ('completed', 'failed', 'cancelled', 'needs_review')
    """)

    op.create_table(
        "broker_sync_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("broker", sa.String(), nullable=False),
        sa.Column("stream", sa.String(), nullable=False),
        sa.Column("provider_event_id", sa.String(), nullable=False),
        sa.Column("provider_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("stream IN ('orders', 'dividends')", name="ck_broker_sync_event_stream"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "portfolio_id"],
            ["portfolios.workspace_id", "portfolios.id"],
            name="fk_broker_sync_event_workspace_portfolio",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id", "run_id"],
            ["broker_sync_runs.workspace_id", "broker_sync_runs.id"],
            name="fk_broker_sync_event_workspace_run",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id", "run_id", "stream", "provider_event_id",
            name="uq_broker_sync_event_run_stream_identity",
        ),
    )
    op.create_index("ix_broker_sync_events_public_id", "broker_sync_events", ["public_id"], unique=True)
    op.create_index("ix_broker_sync_events_workspace_id", "broker_sync_events", ["workspace_id"])
    op.create_index("ix_broker_sync_events_portfolio_id", "broker_sync_events", ["portfolio_id"])
    op.create_index("ix_broker_sync_events_run_id", "broker_sync_events", ["run_id"])

    for table in ("broker_sync_runs", "broker_sync_events"):
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
    for table in ("broker_sync_events", "broker_sync_runs"):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_policy ON {table}")
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
        op.execute(f"REVOKE USAGE, SELECT ON SEQUENCE {table}_id_seq FROM portfyl_runtime")
        op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE {table} FROM portfyl_runtime")

    for name in (
        "ix_broker_sync_events_run_id", "ix_broker_sync_events_portfolio_id",
        "ix_broker_sync_events_workspace_id", "ix_broker_sync_events_public_id",
    ):
        op.drop_index(name, table_name="broker_sync_events")
    op.drop_table("broker_sync_events")

    op.execute("DROP INDEX IF EXISTS uq_broker_sync_run_one_active_per_connection")
    for name in (
        "ix_broker_sync_runs_connection_id", "ix_broker_sync_runs_portfolio_id",
        "ix_broker_sync_runs_workspace_id", "ix_broker_sync_runs_public_id",
    ):
        op.drop_index(name, table_name="broker_sync_runs")
    op.drop_table("broker_sync_runs")

    op.drop_constraint("uq_broker_connection_workspace_id", "broker_connections", type_="unique")
    op.drop_column("broker_connections", "credential_generation")
