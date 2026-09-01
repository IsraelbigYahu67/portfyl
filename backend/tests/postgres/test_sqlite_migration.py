from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.orm import Session

import migrations.sqlite_to_postgres as migration_module
from migrations.sqlite_to_postgres import (
    MigrationAlreadyApplied,
    MigrationOptions,
    MigrationReconciliationError,
    migrate_sqlite,
)
from models import (
    DataMigrationRun,
    Membership,
    Transaction,
    User,
    UserSetting,
    Workspace,
    WorkspaceSetting,
)


FIXTURE_SQL = Path(__file__).resolve().parents[1] / "fixtures" / "legacy_portfyl.sql"


@contextmanager
def admin_session(url: str):
    engine = create_engine(url)
    try:
        with Session(engine) as db:
            yield db
    finally:
        engine.dispose()


@pytest.fixture
def legacy_db(tmp_path: Path) -> Path:
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(FIXTURE_SQL.read_text(encoding="utf-8"))
    finally:
        connection.close()
    return path


@pytest.fixture
def empty_postgres_url(postgres_url: str, postgres_engine) -> str:
    with Session(postgres_engine) as db:
        db.execute(delete(User))
        db.execute(delete(Workspace))
        db.commit()
    yield postgres_url
    with Session(postgres_engine) as db:
        db.execute(delete(User))
        db.execute(delete(Workspace))
        db.commit()


def test_migration_preserves_rows_and_assigns_one_workspace(
    legacy_db: Path,
    empty_postgres_url: str,
):
    report = migrate_sqlite(
        MigrationOptions(
            source=legacy_db,
            target_url=empty_postgres_url,
            owner_email=" Owner@Example.com ",
            dry_run=False,
        )
    )

    assert report.status == "succeeded"
    assert report.table_counts == {
        "users": 1,
        "workspaces": 1,
        "memberships": 1,
        "portfolios": 2,
        "transactions": 4,
        "watchlists": 1,
        "watchlist_items": 1,
        "benchmarks": 1,
        "benchmark_components": 1,
        "broker_connections": 1,
        "broker_balances": 1,
        "options_trades": 1,
        "polymarket_positions": 1,
        "discord_webhooks": 1,
        "trade_notes": 1,
        "cash_interest_rates": 1,
        "dividend_notifications": 1,
        "price_alerts": 1,
        "user_settings": 2,
        "workspace_settings": 4,
    }
    assert len(report.source_sha256) == 64

    with admin_session(empty_postgres_url) as db:
        assert len(db.scalars(select(Workspace)).all()) == 1
        assert {
            row.workspace_id for row in db.scalars(select(Transaction)).all()
        } == {report.workspace_id}
        assert {row.id for row in db.scalars(select(Transaction)).all()} == {1, 2, 3, 4}
        cash_row = db.scalar(select(Transaction).where(Transaction.id == 2))
        assert cash_row is not None
        assert cash_row.ticker is None
        assert cash_row.amount == 1000
        assert cash_row.cash_amount is None
        sequence_state = db.execute(
            text("SELECT last_value, is_called FROM portfolios_id_seq")
        ).one()
        assert sequence_state == (3, False)
        owner = db.scalar(select(User))
        assert owner is not None
        assert owner.email == "owner@example.com"
        membership = db.scalar(select(Membership))
        assert membership is not None
        assert membership.user_id == owner.id
        assert membership.workspace_id == report.workspace_id


def test_migration_classifies_settings_and_records_owner_claim(
    legacy_db: Path,
    empty_postgres_url: str,
):
    report = migrate_sqlite(MigrationOptions(
        source=legacy_db,
        target_url=empty_postgres_url,
        owner_email="OWNER@example.com",
        dry_run=False,
    ))

    with admin_session(empty_postgres_url) as db:
        owner = db.scalar(select(User))
        assert owner is not None
        assert owner.firebase_uid is None
        assert {
            row.key: row.value for row in db.scalars(select(UserSetting)).all()
        } == {
            "deepseek_api_key": "fixture-deepseek-key",
            "deepseek_model": "deepseek-chat",
        }
        assert {
            row.key: row.value for row in db.scalars(select(WorkspaceSetting)).all()
        } == {
            "broker_sync_mode": "daily",
            "broker_sync_daily_time": "04:30",
            "broker_sync_interval_hours": "12",
            "broker_sync_last_run": "2026-08-31T04:30:00+00:00",
        }
        run = db.scalar(select(DataMigrationRun))
        assert run is not None
        assert run.owner_email == "owner@example.com"
        assert run.workspace_id == report.workspace_id
        assert run.table_counts == report.table_counts
        assert run.control_totals == report.control_totals


def test_dry_run_writes_no_rows(legacy_db: Path, empty_postgres_url: str):
    with admin_session(empty_postgres_url) as db:
        sequence_before = db.execute(
            text("SELECT last_value, is_called FROM portfolios_id_seq")
        ).one()
    report = migrate_sqlite(MigrationOptions(
        source=legacy_db,
        target_url=empty_postgres_url,
        owner_email="owner@example.com",
        dry_run=True,
    ))

    assert report.status == "dry_run"
    assert report.table_counts["transactions"] == 4
    with admin_session(empty_postgres_url) as db:
        assert db.scalars(select(User)).all() == []
        assert db.scalars(select(Workspace)).all() == []
        assert db.scalars(select(DataMigrationRun)).all() == []
        assert db.execute(
            text("SELECT last_value, is_called FROM portfolios_id_seq")
        ).one() == sequence_before


def test_duplicate_source_is_rejected(legacy_db: Path, empty_postgres_url: str):
    options = MigrationOptions(
        source=legacy_db,
        target_url=empty_postgres_url,
        owner_email="owner@example.com",
        dry_run=False,
    )
    migrate_sqlite(options)

    with pytest.raises(MigrationAlreadyApplied, match="already imported"):
        migrate_sqlite(options)

    with admin_session(empty_postgres_url) as db:
        assert len(db.scalars(select(Workspace)).all()) == 1
        assert len(db.scalars(select(DataMigrationRun)).all()) == 1


def test_reconciliation_mismatch_rolls_back_all_rows(
    legacy_db: Path,
    empty_postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
):
    real_target_totals = migration_module._target_control_totals

    def mismatched_totals(db, workspace_id):
        totals = real_target_totals(db, workspace_id)
        return {**totals, "transactions_sha256": "0" * 64}

    monkeypatch.setattr(
        migration_module,
        "_target_control_totals",
        mismatched_totals,
    )

    with pytest.raises(MigrationReconciliationError, match="control totals differ"):
        migrate_sqlite(MigrationOptions(
            source=legacy_db,
            target_url=empty_postgres_url,
            owner_email="owner@example.com",
            dry_run=False,
        ))

    with admin_session(empty_postgres_url) as db:
        assert db.scalars(select(User)).all() == []
        assert db.scalars(select(Workspace)).all() == []
        assert db.scalars(select(DataMigrationRun)).all() == []


def test_cli_dry_run_emits_machine_readable_success(
    legacy_db: Path,
    empty_postgres_url: str,
    capsys: pytest.CaptureFixture[str],
):
    exit_code = migration_module.main([
        "--source",
        str(legacy_db),
        "--target-database-url",
        empty_postgres_url,
        "--owner-email",
        "owner@example.com",
        "--dry-run",
    ])

    assert exit_code == 0
    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["status"] == "dry_run"
    assert payload["table_counts"]["transactions"] == 4
    assert empty_postgres_url not in output.out
    assert output.err == ""
