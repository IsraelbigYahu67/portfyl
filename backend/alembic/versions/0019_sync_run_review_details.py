"""Record why a T212 history run needed review.

Revision ID: 0019_sync_run_review_details
Revises: 0018_t212_account_binding
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0019_sync_run_review_details"
down_revision: Union[str, Sequence[str], None] = "0018_t212_account_binding"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("broker_sync_runs", sa.Column("review_details", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("broker_sync_runs", "review_details")
