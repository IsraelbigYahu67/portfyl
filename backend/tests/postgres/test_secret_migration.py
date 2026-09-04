"""Rehearsal of the broker-secret expand -> backfill -> contract migration
sequence (Task 2 of docs/superpowers/plans/2026-09-04-portfyl-secrets-jobs.md).

The shared, session-scoped `postgres_engine` fixture (see conftest.py) is
already migrated all the way to head -- ciphertext columns required,
plaintext columns dropped -- so it can't represent the pre-backfill state a
real legacy database (with existing plaintext broker credentials) is in
partway through this sequence. This test drives its own throwaway database
on the same disposable Postgres server instead, independent of that shared
fixture, so it can seed a legacy-shaped row and walk it through every step
an operator will actually run.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from database import DatabaseSettings, build_engine  # noqa: E402
from edition import edition_from_env  # noqa: E402
from migrations.encrypt_existing_secrets import run as run_backfill  # noqa: E402
from secrets_crypto import EncryptedValue, build_secret_cipher  # noqa: E402


@pytest.fixture
def rehearsal_database_url(postgres_url: str):
    base_url = make_url(postgres_url)
    admin_engine = create_engine(
        base_url.set(database="postgres"), isolation_level="AUTOCOMMIT"
    )
    db_name = f"rehearsal_{uuid.uuid4().hex[:16]}"
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    try:
        # str(url) masks the password (hide_password=True) -- render it
        # explicitly or every downstream connection auth-fails against "***".
        yield base_url.set(database=db_name).render_as_string(hide_password=False)
    finally:
        with admin_engine.connect() as conn:
            conn.execute(text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ), {"name": db_name})
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}"'))
        admin_engine.dispose()


def _upgrade_to(database_url: str, revision: str) -> None:
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with patch.dict(os.environ, {"DATABASE_URL": database_url}):
        command.upgrade(alembic_config, revision)


def test_expand_backfill_contract_preserves_broker_credentials(
    rehearsal_database_url, monkeypatch,
):
    monkeypatch.setenv("PORTFYL_EDITION", "local")
    monkeypatch.setenv(
        "PORTFYL_LOCAL_SECRET_KEY", "OmC2HEZsgRV5WF4AjQgE1OZTViBiZm6ILN131PwtgPg="
    )

    # Step 1: expand only -- old plaintext columns and the new nullable
    # ciphertext columns coexist, exactly like a real pre-backfill database.
    _upgrade_to(rehearsal_database_url, "0004_broker_secrets_expand")

    workspace_id = uuid.uuid4()
    engine = build_engine(DatabaseSettings.from_env({"DATABASE_URL": rehearsal_database_url}))
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO workspaces (id, public_id, name) VALUES (:id, :id, 'Rehearsal')"
        ), {"id": workspace_id})
        conn.execute(text(
            "INSERT INTO portfolios (id, public_id, workspace_id, name, is_default) "
            "VALUES (1, :pub, :ws, 'Default', true)"
        ), {"pub": uuid.uuid4(), "ws": workspace_id})
        conn.execute(text(
            "INSERT INTO broker_connections "
            "(public_id, workspace_id, portfolio_id, broker, api_key, api_secret, environment) "
            "VALUES (:pub, :ws, 1, 'trading212', 'legacy-plaintext-key', "
            "'legacy-plaintext-secret', 'live')"
        ), {"pub": uuid.uuid4(), "ws": workspace_id})
    engine.dispose()

    # Step 2: dry run reports the row but writes nothing.
    dry_run_reports = run_backfill(rehearsal_database_url, apply=False)
    assert dry_run_reports[0].total_plaintext_rows == 1
    assert dry_run_reports[0].encrypted == 0

    engine = build_engine(DatabaseSettings.from_env({"DATABASE_URL": rehearsal_database_url}))
    with engine.begin() as conn:
        still_null = conn.execute(text(
            "SELECT count(*) FROM broker_connections WHERE api_key_ciphertext IS NULL"
        )).scalar_one()
    engine.dispose()
    assert still_null == 1

    # Step 3: --apply encrypts the row in place; plaintext columns untouched.
    apply_reports = run_backfill(rehearsal_database_url, apply=True)
    assert apply_reports[0].encrypted == 1

    engine = build_engine(DatabaseSettings.from_env({"DATABASE_URL": rehearsal_database_url}))
    with engine.begin() as conn:
        row = conn.execute(text(
            "SELECT api_key, api_key_ciphertext, api_secret_ciphertext FROM broker_connections"
        )).one()
    engine.dispose()
    assert row.api_key_ciphertext is not None
    assert row.api_key.encode() not in bytes(row.api_key_ciphertext)
    assert row.api_secret_ciphertext is not None

    # Step 4: the contract migration only now becomes safe.
    _upgrade_to(rehearsal_database_url, "0005_broker_secrets_contract")

    engine = build_engine(DatabaseSettings.from_env({"DATABASE_URL": rehearsal_database_url}))
    with engine.begin() as conn:
        columns = {
            r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'broker_connections'"
            ))
        }
        assert "api_key" not in columns
        assert "api_secret" not in columns
        row = conn.execute(text(
            "SELECT api_key_ciphertext, api_key_key_version, "
            "api_secret_ciphertext, api_secret_key_version FROM broker_connections"
        )).one()
    engine.dispose()

    cipher = build_secret_cipher(os.environ, edition_from_env(os.environ))
    assert cipher.decrypt(
        EncryptedValue(bytes(row.api_key_ciphertext), row.api_key_key_version)
    ) == "legacy-plaintext-key"
    assert cipher.decrypt(
        EncryptedValue(bytes(row.api_secret_ciphertext), row.api_secret_key_version)
    ) == "legacy-plaintext-secret"
