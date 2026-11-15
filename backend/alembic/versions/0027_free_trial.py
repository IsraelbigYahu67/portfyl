"""Add the 10-day free Pro trial tables.

`trial_grants` is a tenant table (forced RLS). `trial_identities`,
`trial_ip_marks` and `trial_broker_marks` are global, non-tenant abuse-guard
tables that hold only HMAC fingerprints (never raw e-mails, IPs or broker
account numbers). All four land here so the broker check needs no migration.

Additive only (new tables), so it is safe to apply while older Cloud Run
instances are still serving.

Revision ID: 0027_free_trial
Revises: 0026_broker_requests
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0027_free_trial"
down_revision: Union[str, Sequence[str], None] = "0026_broker_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WORKSPACE = "NULLIF(current_setting('portfyl.workspace_id', true), '')::uuid"
_GLOBAL_TABLES = ("trial_identities", "trial_ip_marks", "trial_broker_marks")


def upgrade() -> None:
    op.create_table(
        "trial_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("ends_at > started_at", name="ck_trial_period_order"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trial_grants_public_id", "trial_grants", ["public_id"], unique=True)
    op.create_index("ix_trial_grants_workspace_id", "trial_grants", ["workspace_id"], unique=True)
    op.create_index("ix_trial_grants_ends_at", "trial_grants", ["ends_at"])

    op.create_table(
        "trial_identities",
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("fingerprint"),
    )
    op.create_index("ix_trial_identities_granted_at", "trial_identities", ["granted_at"])

    op.create_table(
        "trial_ip_marks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ip_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trial_ip_marks_ip_fingerprint", "trial_ip_marks", ["ip_fingerprint"])
    op.create_index("ix_trial_ip_marks_granted_at", "trial_ip_marks", ["granted_at"])

    op.create_table(
        "trial_broker_marks",
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("fingerprint"),
    )
    op.create_index("ix_trial_broker_marks_workspace_id", "trial_broker_marks", ["workspace_id"])
    op.create_index("ix_trial_broker_marks_first_seen_at", "trial_broker_marks", ["first_seen_at"])

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE trial_grants TO portfyl_runtime")
    op.execute('ALTER TABLE "trial_grants" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "trial_grants" FORCE ROW LEVEL SECURITY')
    op.execute(f"""
        CREATE POLICY trial_grants_workspace_policy ON trial_grants
        USING (workspace_id = {_WORKSPACE})
        WITH CHECK (workspace_id = {_WORKSPACE})
    """)
    for table in _GLOBAL_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO portfyl_runtime")


def downgrade() -> None:
    for table in _GLOBAL_TABLES:
        op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE {table} FROM portfyl_runtime")
    op.execute("DROP POLICY IF EXISTS trial_grants_workspace_policy ON trial_grants")
    op.execute('ALTER TABLE "trial_grants" NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "trial_grants" DISABLE ROW LEVEL SECURITY')
    op.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE trial_grants FROM portfyl_runtime")

    op.drop_index("ix_trial_broker_marks_first_seen_at", table_name="trial_broker_marks")
    op.drop_index("ix_trial_broker_marks_workspace_id", table_name="trial_broker_marks")
    op.drop_table("trial_broker_marks")
    op.drop_index("ix_trial_ip_marks_granted_at", table_name="trial_ip_marks")
    op.drop_index("ix_trial_ip_marks_ip_fingerprint", table_name="trial_ip_marks")
    op.drop_table("trial_ip_marks")
    op.drop_index("ix_trial_identities_granted_at", table_name="trial_identities")
    op.drop_table("trial_identities")
    op.drop_index("ix_trial_grants_ends_at", table_name="trial_grants")
    op.drop_index("ix_trial_grants_workspace_id", table_name="trial_grants")
    op.drop_index("ix_trial_grants_public_id", table_name="trial_grants")
    op.drop_table("trial_grants")
