"""Add the global private-beta admission allow-list.

Revision ID: 0013_private_beta_invites
Revises: 0012_rate_limit_buckets
"""

from __future__ import annotations

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "0013_private_beta_invites"
down_revision: Union[str, Sequence[str], None] = "0012_rate_limit_buckets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "beta_invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("status", sa.String(), server_default="invited", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("email = lower(trim(email))", name="ck_beta_invites_email_normalized"),
        sa.CheckConstraint("status IN ('invited', 'accepted', 'revoked')", name="ck_beta_invites_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_beta_invites_email", "beta_invites", ["email"], unique=True)
    op.create_index("ix_beta_invites_expires_at", "beta_invites", ["expires_at"])
    op.create_index("ix_beta_invites_revoked_at", "beta_invites", ["revoked_at"])
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE beta_invites TO portfyl_runtime")

    # Preserve access for every account that existed before the private-beta
    # gate was introduced. New identities still require an explicit invite.
    connection = op.get_bind()
    emails = connection.execute(sa.text("SELECT email FROM users")).scalars().all()
    for email in emails:
        connection.execute(
            sa.text(
                "INSERT INTO beta_invites (id, email, status, accepted_at) "
                "VALUES (:id, :email, 'accepted', now()) "
                "ON CONFLICT (email) DO NOTHING"
            ),
            {"id": uuid4(), "email": str(email).strip().casefold()},
        )


def downgrade() -> None:
    op.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE beta_invites FROM portfyl_runtime")
    op.drop_index("ix_beta_invites_revoked_at", table_name="beta_invites")
    op.drop_index("ix_beta_invites_expires_at", table_name="beta_invites")
    op.drop_index("ix_beta_invites_email", table_name="beta_invites")
    op.drop_table("beta_invites")
