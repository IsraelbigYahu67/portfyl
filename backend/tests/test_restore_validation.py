from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "validate_restore", REPO_ROOT / "deploy" / "validate-restore.py"
)
validate_restore_module = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = validate_restore_module
_SPEC.loader.exec_module(validate_restore_module)

ALL_TABLES = validate_restore_module.ALL_TABLES
TENANT_RLS_TABLES = validate_restore_module.TENANT_RLS_TABLES
RestoreControl = validate_restore_module.RestoreControl
capture_control = validate_restore_module.capture_control
main = validate_restore_module.main
validate_restore = validate_restore_module.validate_restore


class FakeInspector:
    def __init__(
        self,
        *,
        alembic_head="0003_job_workspace_enumeration",
        rls_status=None,
        policy_counts=None,
        runtime_role=None,
        table_counts=None,
        control_totals=None,
    ):
        self._alembic_head = alembic_head
        self._rls_status = rls_status or {table: (True, True) for table in TENANT_RLS_TABLES}
        self._policy_counts = policy_counts or {table: 1 for table in TENANT_RLS_TABLES}
        self._runtime_role = runtime_role or {
            "exists": True,
            "rolsuper": False,
            "rolbypassrls": False,
        }
        self._table_counts = table_counts or {}
        self._control_totals = control_totals or {}

    def alembic_head(self):
        return self._alembic_head

    def runtime_role_flags(self):
        return self._runtime_role

    def rls_status(self, tables):
        return {table: self._rls_status.get(table, (False, False)) for table in tables}

    def policy_counts(self, tables):
        return {table: self._policy_counts.get(table, 0) for table in tables}

    def table_counts(self, tables):
        return {table: self._table_counts.get(table, 0) for table in tables}

    def transaction_control_totals(self):
        return self._control_totals


def test_restore_validator_rejects_wrong_alembic_revision():
    inspector = FakeInspector(alembic_head="0001_multiuser_schema")
    control = RestoreControl(table_counts={}, control_totals={})

    result = validate_restore(inspector, control, expected_head="0003_job_workspace_enumeration")

    assert result.ok is False
    assert result.errors == [
        "alembic revision mismatch: expected 0003_job_workspace_enumeration, got 0001_multiuser_schema"
    ]


def test_restore_validator_passes_when_everything_matches():
    counts = {"portfolios": 2, "transactions": 4}
    totals = {"transaction_count": "4"}
    inspector = FakeInspector(table_counts=counts, control_totals=totals)
    control = RestoreControl(table_counts=counts, control_totals=totals)

    result = validate_restore(
        inspector, control, expected_head="0003_job_workspace_enumeration"
    )

    assert result.ok is True
    assert result.errors == []


def test_restore_validator_reports_table_count_mismatch():
    inspector = FakeInspector(table_counts={"transactions": 3})
    control = RestoreControl(table_counts={"transactions": 4}, control_totals={})

    result = validate_restore(
        inspector, control, expected_head="0003_job_workspace_enumeration"
    )

    assert result.ok is False
    assert any("table counts differ" in error for error in result.errors)


def test_restore_validator_reports_control_total_mismatch():
    inspector = FakeInspector(control_totals={"transaction_count": "3"})
    control = RestoreControl(table_counts={}, control_totals={"transaction_count": "4"})

    result = validate_restore(
        inspector, control, expected_head="0003_job_workspace_enumeration"
    )

    assert result.ok is False
    assert any("control totals differ" in error for error in result.errors)


def test_restore_validator_requires_rls_enabled_and_forced_on_every_tenant_table():
    rls_status = {table: (True, True) for table in TENANT_RLS_TABLES}
    rls_status["portfolios"] = (True, False)
    inspector = FakeInspector(rls_status=rls_status)
    control = RestoreControl(table_counts={}, control_totals={})

    result = validate_restore(
        inspector, control, expected_head="0003_job_workspace_enumeration"
    )

    assert result.ok is False
    assert any("portfolios" in error and "row level security" in error for error in result.errors)


def test_restore_validator_requires_a_policy_on_every_tenant_table():
    policy_counts = {table: 1 for table in TENANT_RLS_TABLES}
    policy_counts["transactions"] = 0
    inspector = FakeInspector(policy_counts=policy_counts)
    control = RestoreControl(table_counts={}, control_totals={})

    result = validate_restore(
        inspector, control, expected_head="0003_job_workspace_enumeration"
    )

    assert result.ok is False
    assert any("transactions" in error and "policy" in error for error in result.errors)


def test_restore_validator_rejects_runtime_role_with_bypassrls():
    inspector = FakeInspector(
        runtime_role={"exists": True, "rolsuper": False, "rolbypassrls": True}
    )
    control = RestoreControl(table_counts={}, control_totals={})

    result = validate_restore(
        inspector, control, expected_head="0003_job_workspace_enumeration"
    )

    assert result.ok is False
    assert any("BYPASSRLS" in error for error in result.errors)


def test_capture_control_reads_all_tables_and_totals():
    inspector = FakeInspector(
        table_counts={table: 3 for table in ALL_TABLES},
        control_totals={"transaction_count": "3"},
    )

    control = capture_control(inspector)

    assert control.table_counts["transactions"] == 3
    assert set(control.table_counts) == set(ALL_TABLES)
    assert control.control_totals == {"transaction_count": "3"}


def test_restore_validator_never_includes_database_url(monkeypatch, capsys):
    monkeypatch.setenv("RESTORE_DATABASE_URL", "postgresql://secret@example/db")

    exit_code = main([
        "--database-url-env", "RESTORE_DATABASE_URL",
        "--control-file", "missing.json",
    ])

    assert exit_code != 0
    captured = capsys.readouterr()
    assert "secret@example" not in captured.out
    assert "secret@example" not in captured.err


def test_main_reports_missing_env_var_without_touching_control_file(capsys, monkeypatch):
    monkeypatch.delenv("UNSET_DATABASE_URL", raising=False)

    exit_code = main([
        "--database-url-env", "UNSET_DATABASE_URL",
        "--control-file", "missing.json",
    ])

    assert exit_code != 0
    captured = capsys.readouterr()
    assert "UNSET_DATABASE_URL" in captured.err


def test_main_reports_missing_control_file(monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("RESTORE_DATABASE_URL", "postgresql://user@example/db")
    missing = tmp_path / "does-not-exist.json"

    exit_code = main([
        "--database-url-env", "RESTORE_DATABASE_URL",
        "--control-file", str(missing),
    ])

    assert exit_code != 0
    captured = capsys.readouterr()
    assert "control file" in captured.err.lower()
