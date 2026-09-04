"""Require the Discord webhook ciphertext columns and drop the plaintext one.

Contract step of the expand -> backfill -> contract sequence started by
0005_discord_webhook_expand, chained after 0006_broker_secrets_contract so
both tables finish their contract step back to back. Do not run this
against an environment that hasn't had
backend/migrations/encrypt_existing_secrets.py run to completion first
(dry-run then --apply) -- any row still missing webhook_url_ciphertext
loses its webhook URL when the plaintext column is dropped here, with no
way to recover it.

Revision ID: 0007_discord_webhook_contract
Revises: 0006_broker_secrets_contract
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_discord_webhook_contract"
down_revision: Union[str, Sequence[str], None] = "0006_broker_secrets_contract"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("discord_webhooks", "webhook_url_ciphertext", nullable=False)
    op.alter_column("discord_webhooks", "webhook_url_key_version", nullable=False)
    op.drop_column("discord_webhooks", "webhook_url")


def downgrade() -> None:
    op.add_column("discord_webhooks", sa.Column("webhook_url", sa.String(), nullable=True))
    op.alter_column("discord_webhooks", "webhook_url_ciphertext", nullable=True)
    op.alter_column("discord_webhooks", "webhook_url_key_version", nullable=True)
    # Plaintext is unrecoverable once dropped -- see 0006_broker_secrets_contract's
    # downgrade() note; the same reasoning applies here.
