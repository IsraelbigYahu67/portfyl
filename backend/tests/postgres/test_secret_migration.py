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


def test_expand_backfill_contract_preserves_broker_and_webhook_secrets(
    rehearsal_database_url, monkeypatch,
):
    monkeypatch.setenv("PORTFYL_EDITION", "local")
    monkeypatch.setenv(
        "PORTFYL_LOCAL_SECRET_KEY", "OmC2HEZsgRV5WF4AjQgE1OZTViBiZm6ILN131PwtgPg="
    )

    # Step 1: expand both tables -- old plaintext columns and the new
    # nullable ciphertext columns coexist for both, exactly like a real
    # pre-backfill database (0005 is chained right after 0004, before either
    # table's contract step -- see 0005_discord_webhook_expand's docstring).
    _upgrade_to(rehearsal_database_url, "0005_discord_webhook_expand")

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
        conn.execute(text(
            "INSERT INTO discord_webhooks (public_id, workspace_id, portfolio_id, webhook_url) "
            "VALUES (:pub, :ws, 1, 'https://discord.com/api/webhooks/legacy/plaintext-token')"
        ), {"pub": uuid.uuid4(), "ws": workspace_id})
    engine.dispose()

    # Step 2: dry run reports both rows but writes nothing.
    dry_run_reports = run_backfill(rehearsal_database_url, apply=False)
    broker_report, discord_report = dry_run_reports
    assert broker_report.total_plaintext_rows == 1
    assert broker_report.encrypted == 0
    assert discord_report.total_plaintext_rows == 1
    assert discord_report.encrypted == 0

    engine = build_engine(DatabaseSettings.from_env({"DATABASE_URL": rehearsal_database_url}))
    with engine.begin() as conn:
        still_null_broker = conn.execute(text(
            "SELECT count(*) FROM broker_connections WHERE api_key_ciphertext IS NULL"
        )).scalar_one()
        still_null_discord = conn.execute(text(
            "SELECT count(*) FROM discord_webhooks WHERE webhook_url_ciphertext IS NULL"
        )).scalar_one()
    engine.dispose()
    assert still_null_broker == 1
    assert still_null_discord == 1

    # Step 3: --apply encrypts both rows in place; plaintext columns untouched.
    apply_reports = run_backfill(rehearsal_database_url, apply=True)
    assert apply_reports[0].encrypted == 1
    assert apply_reports[1].encrypted == 1

    engine = build_engine(DatabaseSettings.from_env({"DATABASE_URL": rehearsal_database_url}))
    with engine.begin() as conn:
        broker_row = conn.execute(text(
            "SELECT api_key, api_key_ciphertext, api_secret_ciphertext FROM broker_connections"
        )).one()
        discord_row = conn.execute(text(
            "SELECT webhook_url, webhook_url_ciphertext FROM discord_webhooks"
        )).one()
    engine.dispose()
    assert broker_row.api_key_ciphertext is not None
    assert broker_row.api_key.encode() not in bytes(broker_row.api_key_ciphertext)
    assert broker_row.api_secret_ciphertext is not None
    assert discord_row.webhook_url_ciphertext is not None
    assert discord_row.webhook_url.encode() not in bytes(discord_row.webhook_url_ciphertext)

    # Step 4: the contract migrations only now become safe.
    _upgrade_to(rehearsal_database_url, "0007_discord_webhook_contract")

    engine = build_engine(DatabaseSettings.from_env({"DATABASE_URL": rehearsal_database_url}))
    with engine.begin() as conn:
        broker_columns = {
            r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'broker_connections'"
            ))
        }
        discord_columns = {
            r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'discord_webhooks'"
            ))
        }
        assert "api_key" not in broker_columns
        assert "api_secret" not in broker_columns
        assert "webhook_url" not in discord_columns
        broker_row = conn.execute(text(
            "SELECT api_key_ciphertext, api_key_key_version, "
            "api_secret_ciphertext, api_secret_key_version FROM broker_connections"
        )).one()
        discord_row = conn.execute(text(
            "SELECT webhook_url_ciphertext, webhook_url_key_version FROM discord_webhooks"
        )).one()
    engine.dispose()

    cipher = build_secret_cipher(os.environ, edition_from_env(os.environ))
    assert cipher.decrypt(
        EncryptedValue(bytes(broker_row.api_key_ciphertext), broker_row.api_key_key_version)
    ) == "legacy-plaintext-key"
    assert cipher.decrypt(
        EncryptedValue(bytes(broker_row.api_secret_ciphertext), broker_row.api_secret_key_version)
    ) == "legacy-plaintext-secret"
    assert cipher.decrypt(
        EncryptedValue(bytes(discord_row.webhook_url_ciphertext), discord_row.webhook_url_key_version)
    ) == "https://discord.com/api/webhooks/legacy/plaintext-token"
