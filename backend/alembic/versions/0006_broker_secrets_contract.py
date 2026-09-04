"""Require broker connection ciphertext columns and drop the plaintext ones.

Contract step of the expand -> backfill -> contract sequence started by
0004_broker_secrets_expand / 0005_discord_webhook_expand. Chained after
BOTH tables' expand migrations (see 0005's docstring for why) -- do not run
this against an environment that hasn't had
backend/migrations/encrypt_existing_secrets.py run to completion first
(dry-run then --apply) -- any row still missing api_key_ciphertext loses
its broker connection's api_key when the plaintext column is dropped here,
with no way to recover it.

Revision ID: 0006_broker_secrets_contract
Revises: 0005_discord_webhook_expand
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_broker_secrets_contract"
down_revision: Union[str, Sequence[str], None] = "0005_discord_webhook_expand"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("broker_connections", "api_key_ciphertext", nullable=False)
    op.alter_column("broker_connections", "api_key_key_version", nullable=False)
    op.drop_column("broker_connections", "api_key")
    op.drop_column("broker_connections", "api_secret")


def downgrade() -> None:
    op.add_column("broker_connections", sa.Column("api_key", sa.String(), nullable=True))
    op.add_column("broker_connections", sa.Column("api_secret", sa.String(), nullable=True))
    op.alter_column("broker_connections", "api_key_ciphertext", nullable=True)
    op.alter_column("broker_connections", "api_key_key_version", nullable=True)
    # Plaintext values are unrecoverable once dropped by upgrade() -- this
    # downgrade restores the columns as empty so the schema round-trips,
    # not the data. A real rollback needs encrypt_existing_secrets.py's
    # inverse (decrypt-and-fill), which is out of scope here since the
    # forward migration is only meant to run after a confirmed backfill.
