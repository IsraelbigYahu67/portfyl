"""Add security audit trail and recurring-job success state.

Revision ID: 0009_audit_log
Revises: 0008_broker_failure_tracking
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_audit_log"
down_revision: Union[str, Sequence[str], None] = "0008_broker_failure_tracking"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WORKSPACE_SETTING = "NULLIF(current_setting('portfyl.workspace_id', true), '')::uuid"
_USER_SETTING = "NULLIF(current_setting('portfyl.user_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=True),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=True),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_public_id", "audit_logs", ["public_id"], unique=True)
    op.create_index("ix_audit_logs_workspace_id", "audit_logs", ["workspace_id"])
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_table(
        "job_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_name", sa.String(), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_runs_job_name", "job_runs", ["job_name"], unique=True)

    op.execute("GRANT SELECT, INSERT ON TABLE audit_logs TO portfyl_runtime")
    op.execute("GRANT SELECT, INSERT, UPDATE ON TABLE job_runs TO portfyl_runtime")
    op.execute('ALTER TABLE "audit_logs" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "audit_logs" FORCE ROW LEVEL SECURITY')
    op.execute(f"""
        CREATE POLICY audit_logs_scope_policy ON audit_logs
        USING (
            (workspace_id IS NOT NULL AND workspace_id = {_WORKSPACE_SETTING})
            OR (workspace_id IS NULL AND actor_user_id = {_USER_SETTING})
        )
        WITH CHECK (
            (workspace_id IS NOT NULL AND workspace_id = {_WORKSPACE_SETTING})
            OR (workspace_id IS NULL AND actor_user_id = {_USER_SETTING})
        )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_logs_scope_policy ON audit_logs")
    op.execute('ALTER TABLE "audit_logs" NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "audit_logs" DISABLE ROW LEVEL SECURITY')
    op.execute("REVOKE SELECT, INSERT, UPDATE ON TABLE job_runs FROM portfyl_runtime")
    op.execute("REVOKE SELECT, INSERT ON TABLE audit_logs FROM portfyl_runtime")
    op.drop_index("ix_job_runs_job_name", table_name="job_runs")
    op.drop_table("job_runs")
    for name in (
        "ix_audit_logs_created_at", "ix_audit_logs_action",
        "ix_audit_logs_actor_user_id", "ix_audit_logs_workspace_id",
        "ix_audit_logs_public_id",
    ):
        op.drop_index(name, table_name="audit_logs")
    op.drop_table("audit_logs")
