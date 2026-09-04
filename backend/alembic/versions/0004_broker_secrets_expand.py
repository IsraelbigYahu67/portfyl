"""Add nullable ciphertext columns for broker connection credentials.

Expand step of an expand -> backfill -> contract migration for Workstream D
(docs/superpowers/plans/2026-09-04-portfyl-secrets-jobs.md, Task 2). The
existing plaintext `api_key`/`api_secret` columns are intentionally left in
place here -- the application no longer maps them (see
models.BrokerConnection), but any row created before this deploy still needs
`backend/migrations/encrypt_existing_secrets.py` run against them before
0005_broker_secrets_contract can safely drop them.

Revision ID: 0004_broker_secrets_expand
Revises: 0003_job_workspace_enumeration

Revision ids in this project stay at or under 32 characters -- Alembic's
own bookkeeping table (`alembic_version.version_num`) is a bare
`VARCHAR(32)`, and a longer id fails to write with a truncation error at
migration time (discovered while developing this migration).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_broker_secrets_expand"
down_revision: Union[str, Sequence[str], None] = "0003_job_workspace_enumeration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("broker_connections", sa.Column("api_key_ciphertext", sa.LargeBinary(), nullable=True))
    op.add_column("broker_connections", sa.Column("api_key_key_version", sa.String(), nullable=True))
    op.add_column("broker_connections", sa.Column("api_secret_ciphertext", sa.LargeBinary(), nullable=True))
    op.add_column("broker_connections", sa.Column("api_secret_key_version", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("broker_connections", "api_secret_key_version")
    op.drop_column("broker_connections", "api_secret_ciphertext")
    op.drop_column("broker_connections", "api_key_key_version")
    op.drop_column("broker_connections", "api_key_ciphertext")
