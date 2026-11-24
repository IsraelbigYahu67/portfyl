"""Migration 0028: `users.password_changed_seen_at` (own-emails wave 2, Task 2).

The shared engine is session-scoped, so the test always upgrades back to head.
"""
from __future__ import annotations

import os
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, text

from database import EXPECTED_ALEMBIC_HEAD
from tests.postgres.conftest import BACKEND_ROOT

REVISION = "0028_password_changed_seen"


def _column(engine: Engine):
    with engine.connect() as conn:
        return conn.execute(text(
            "SELECT data_type, is_nullable, column_default FROM information_schema.columns "
            "WHERE table_name = 'users' AND column_name = 'password_changed_seen_at'"
        )).one_or_none()


def test_there_is_exactly_one_head_and_it_is_the_expected_one():
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    heads = ScriptDirectory.from_config(config).get_heads()

    assert heads == [EXPECTED_ALEMBIC_HEAD]
    # 0028 is no longer the head (0029 sits on it); it must still be the parent.
    assert ScriptDirectory.from_config(config).get_revision(EXPECTED_ALEMBIC_HEAD).down_revision == REVISION


def test_0028_adds_one_nullable_column_and_keeps_existing_rows_null(
    postgres_engine: Engine, postgres_url: str,
):
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with patch.dict(os.environ, {"DATABASE_URL": postgres_url}):
        command.downgrade(config, "0027_free_trial")
        try:
            assert _column(postgres_engine) is None
            # A user who exists before the column does (an older instance).
            with postgres_engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO users (id, email) VALUES (gen_random_uuid(), 'old@example.com')"
                ))

            command.upgrade(config, REVISION)

            data_type, nullable, default = _column(postgres_engine)
            assert data_type == "timestamp with time zone"
            assert nullable == "YES"
            assert default is None
            with postgres_engine.connect() as conn:
                seen = conn.execute(text(
                    "SELECT password_changed_seen_at FROM users WHERE email = 'old@example.com'"
                )).scalar_one()
            assert seen is None  # no backfill: first sight must not notify

            # A pre-0028 instance's INSERT (without the column) still works.
            with postgres_engine.begin() as conn:
                conn.execute(text(
                    "INSERT INTO users (id, email) VALUES (gen_random_uuid(), 'new@example.com')"
                ))
        finally:
            with postgres_engine.begin() as conn:
                conn.execute(text(
                    "DELETE FROM users WHERE email IN ('old@example.com', 'new@example.com')"
                ))
            command.upgrade(config, "head")
