"""Add a narrowly-scoped SELECT policy on workspaces for job enumeration.

The `portfyl_runtime` role is NOBYPASSRLS (see 0002_tenant_rls), and
`workspace_tenant_policy` on `workspaces` only ever allows a row through
when `portfyl.workspace_id` is already set to that row's id -- which is
exactly backwards for the one place in the app that legitimately needs to
enumerate every active workspace *before* it can pick one and set that
context: the background job pollers in jobs.py
(`autosync_all_workspaces` / `dividend_notify_all_workspaces` /
`alert_check_all_workspaces`, via `_active_workspace_ids`).

This migration adds a second, permissive, SELECT-only policy on
`workspaces` gated by a separate `portfyl.job_context` flag. Postgres
combines multiple permissive policies for the same command with OR, so
this is additive to `workspace_tenant_policy` -- it does not weaken
per-request tenant isolation:
  * It only applies to SELECT -- INSERT/UPDATE/DELETE on `workspaces`
    still requires `workspace_tenant_policy` (and its WITH CHECK).
  * It only ever grants visibility of workspace rows (id/archived_at are
    the only columns `_active_workspace_ids` selects) to the trusted,
    server-internal job code path -- no HTTP request handler ever sets
    `portfyl.job_context`, so this policy is never reachable from a
    request.

Revision ID: 0003_job_workspace_enumeration
Revises: 0002_tenant_rls
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0003_job_workspace_enumeration"
down_revision: Union[str, Sequence[str], None] = "0002_tenant_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE POLICY workspace_job_enumeration_policy ON workspaces
        FOR SELECT
        USING (NULLIF(current_setting('portfyl.job_context', true), '') = 'true')
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS workspace_job_enumeration_policy ON workspaces")
