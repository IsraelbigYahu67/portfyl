"""Track successful empty Trading 212 position snapshots.

Revision ID: 0017_position_snapshot_time
Revises: 0016_transaction_provenance
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0017_position_snapshot_time"
down_revision: Union[str, Sequence[str], None] = "0016_transaction_provenance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("broker_connections", sa.Column("positions_snapshot_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("broker_connections", "positions_snapshot_at")
