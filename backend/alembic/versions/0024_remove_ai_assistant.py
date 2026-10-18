"""Delete stored state of the removed DeepSeek AI assistant.

The assistant router is gone, so the per-user DeepSeek API key (encrypted)
and model preference, and the hosted-AI usage quota rows, are never read
again. Delete them rather than keep personal secrets for a feature that no
longer exists. Data-only and safe while older instances still run: an old
instance merely sees the assistant as unconfigured.

Revision ID: 0024_remove_ai_assistant
Revises: 0023_allocation_targets
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0024_remove_ai_assistant"
down_revision: Union[str, Sequence[str], None] = "0023_allocation_targets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "DELETE FROM user_settings WHERE key IN ('deepseek_api_key', 'deepseek_model')"
    )
    op.execute("DELETE FROM usage_reservations WHERE metric = 'hosted_ai_monthly'")
    op.execute("DELETE FROM usage_counters WHERE metric = 'hosted_ai_monthly'")


def downgrade() -> None:
    # Deleted secrets and quota rows cannot be restored; nothing to undo.
    pass
