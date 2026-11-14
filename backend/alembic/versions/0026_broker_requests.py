"""Add broker_requests ("notify me when my broker is supported", onboarding-flow plan Task 3).

Additive only (a new table), so it is safe to apply while older Cloud Run
instances are still serving.

Revision ID: 0026_broker_requests
Revises: 0025_stripe_billing
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0026_broker_requests"
down_revision: Union[str, Sequence[str], None] = "0025_stripe_billing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WORKSPACE_SETTING = "NULLIF(current_setting('portfyl.workspace_id', true), '')::uuid"
_TABLE = "broker_requests"


def upgrade() -> None:
    op.create_table(
        _TABLE,
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("broker_name", sa.String(length=60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_broker_requests_public_id", _TABLE, ["public_id"], unique=True)
    op.create_index("ix_broker_requests_workspace_id", _TABLE, ["workspace_id"])
    op.create_index("ix_broker_requests_user_id", _TABLE, ["user_id"])
    op.create_index(
        "uq_broker_requests_workspace_name",
        _TABLE,
        ["workspace_id", sa.text("lower(broker_name)")],
        unique=True,
    )

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
        "uq_broker_requests_workspace_name",
        "ix_broker_requests_user_id",
        "ix_broker_requests_workspace_id",
        "ix_broker_requests_public_id",
    ):
        op.drop_index(name, table_name=_TABLE)
    op.drop_table(_TABLE)
