"""Remember the Firebase password-changed time Portfyl last saw.

`users.password_changed_seen_at` lets `/auth/session` notice that a password
changed (a reset or a change made directly against Firebase) by comparing
Firebase's "password last changed" time with this value.

Additive only: one nullable column, no default and no backfill (NULL means
"not seen yet", and the first sight notifies nobody), so it is safe to apply
while older Cloud Run instances are still serving.

Revision ID: 0028_password_changed_seen
Revises: 0027_free_trial
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0028_password_changed_seen"
down_revision: Union[str, Sequence[str], None] = "0027_free_trial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "password_changed_seen_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "password_changed_seen_at")
