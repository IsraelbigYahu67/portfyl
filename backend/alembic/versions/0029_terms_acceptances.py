"""Record the Terms acceptance made at sign-up.

`terms_acceptances` is the proof that a person confirmed they are 18 or older,
accepted the Terms of Service and was shown the Privacy Notice when the account
was created (which versions, and when). It is a user-level table like `users`:
no workspace key and no tenant policy. The row is written by the server only;
for an e-mail sign-up it is first written pending (`user_id` NULL, keyed by
`firebase_uid`) and linked to the Portfyl user when the account is created.
`user_id` cascades with the user, so deleting the account deletes the record.

Additive only (one new table, no backfill: accounts created before this
migration simply have no row), so it is safe to apply while older Cloud Run
instances are still serving.

Revision ID: 0029_terms_acceptances
Revises: 0028_password_changed_seen
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0029_terms_acceptances"
down_revision: Union[str, Sequence[str], None] = "0028_password_changed_seen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "terms_acceptances",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("firebase_uid", sa.String(), nullable=True),
        sa.Column("terms_version", sa.String(), nullable=False),
        sa.Column("privacy_notice_version", sa.String(), nullable=False),
        sa.Column("age_confirmed", sa.Boolean(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "user_id IS NOT NULL OR firebase_uid IS NOT NULL",
            name="ck_terms_acceptance_subject",
        ),
        sa.CheckConstraint("age_confirmed IS TRUE", name="ck_terms_acceptance_age"),
        sa.CheckConstraint(
            "source IN ('email_signup', 'google_signup')",
            name="ck_terms_acceptance_source",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_terms_acceptances_user_id", "terms_acceptances", ["user_id"], unique=True)
    op.create_index("ix_terms_acceptances_firebase_uid", "terms_acceptances", ["firebase_uid"], unique=True)
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE terms_acceptances TO portfyl_runtime")


def downgrade() -> None:
    op.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE terms_acceptances FROM portfyl_runtime")
    op.drop_index("ix_terms_acceptances_firebase_uid", table_name="terms_acceptances")
    op.drop_index("ix_terms_acceptances_user_id", table_name="terms_acceptances")
    op.drop_table("terms_acceptances")
