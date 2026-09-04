"""Add nullable ciphertext columns for the Discord webhook URL.

Expand step of an expand -> backfill -> contract migration for Workstream D
(docs/superpowers/plans/2026-09-04-portfyl-secrets-jobs.md, Task 3) --
mirrors 0004_broker_secrets_expand. Deliberately chained straight after
0004 (broker expand), before either table's contract step: both tables'
plaintext columns need to coexist with their new ciphertext columns at the
same time so a single run of
`backend/migrations/encrypt_existing_secrets.py --apply` (it already
backfills both tables in one pass) covers both before either contract
migration -- 0006_broker_secrets_contract / 0007_discord_webhook_contract --
runs. The existing plaintext `webhook_url` column is intentionally left in
place here; the application no longer maps it (see models.DiscordWebhook).

Revision ID: 0005_discord_webhook_expand
Revises: 0004_broker_secrets_expand
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_discord_webhook_expand"
down_revision: Union[str, Sequence[str], None] = "0004_broker_secrets_expand"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("discord_webhooks", sa.Column("webhook_url_ciphertext", sa.LargeBinary(), nullable=True))
    op.add_column("discord_webhooks", sa.Column("webhook_url_key_version", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("discord_webhooks", "webhook_url_key_version")
    op.drop_column("discord_webhooks", "webhook_url_ciphertext")
