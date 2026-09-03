"""Add job_runs: idempotency/dead-letter tracking for external job triggering.

Revision ID: 0004_job_runs
Revises: 0003_job_workspace_enumeration
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_job_runs"
down_revision: Union[str, Sequence[str], None] = "0003_job_workspace_enumeration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_WORKSPACE_SETTING = (
    "NULLIF(current_setting('portfyl.workspace_id', true), '')::uuid"
)


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("job_name", sa.String(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'dead_letter')",
            name="ck_job_runs_status",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_name", "workspace_id", "period_start", name="uq_job_run_period"),
    )
    op.create_index(op.f("ix_job_runs_workspace_id"), "job_runs", ["workspace_id"], unique=False)

    op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "job_runs" TO portfyl_runtime')
    op.execute("GRANT USAGE, SELECT ON SEQUENCE job_runs_id_seq TO portfyl_runtime")

    op.execute('ALTER TABLE "job_runs" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "job_runs" FORCE ROW LEVEL SECURITY')
    op.execute(f"""
        CREATE POLICY job_runs_tenant_policy ON job_runs
        USING (workspace_id = {_WORKSPACE_SETTING})
        WITH CHECK (workspace_id = {_WORKSPACE_SETTING})
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS job_runs_tenant_policy ON job_runs")
    op.execute('ALTER TABLE "job_runs" NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "job_runs" DISABLE ROW LEVEL SECURITY')
    op.execute("REVOKE USAGE, SELECT ON SEQUENCE job_runs_id_seq FROM portfyl_runtime")
    op.execute('REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE "job_runs" FROM portfyl_runtime')
    op.drop_index(op.f("ix_job_runs_workspace_id"), table_name="job_runs")
    op.drop_table("job_runs")
