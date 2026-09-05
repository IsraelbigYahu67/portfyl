"""Add rate_limit_buckets: global, non-tenant fixed-window rate-limit state.

Revision ID: 0012_rate_limit_buckets
Revises: 0011_remove_payment_runtime
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_rate_limit_buckets"
down_revision: Union[str, Sequence[str], None] = "0011_remove_payment_runtime"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_buckets",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("count >= 0", name="ck_rate_limit_bucket_nonnegative"),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index("ix_rate_limit_buckets_expires_at", "rate_limit_buckets", ["expires_at"])
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE rate_limit_buckets TO portfyl_runtime")


def downgrade() -> None:
    op.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE rate_limit_buckets FROM portfyl_runtime")
    op.drop_index("ix_rate_limit_buckets_expires_at", table_name="rate_limit_buckets")
    op.drop_table("rate_limit_buckets")
