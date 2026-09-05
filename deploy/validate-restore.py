"""Verify a restored PostgreSQL database (typically a Neon PITR recovery
branch) before it is trusted or promoted. Never prints a database URL or any
part of one -- only the environment variable *name* holding it is accepted,
and connection attempts are the last thing this script does, after every
argument/file check that can fail cheaply.

Two modes:
- validate (default): compare Alembic head, tenant RLS enforcement, the
  runtime role's privileges, table counts, and transaction control totals
  against a --control-file captured earlier from the source of truth.
- --capture: connect to a database (normally production, on a schedule or
  before a drill) and write a fresh --control-file for later validation.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# database.py validates DATABASE_URL at import time even though this script
# uses its own --database-url-env indirection; a placeholder satisfies that
# fail-closed check without ever being connected to (engines are lazy).
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/unused")

from database import EXPECTED_ALEMBIC_HEAD  # noqa: E402
from migrations.sqlite_to_postgres import _TRANSACTION_FIELDS, _control_totals  # noqa: E402


# Mirrors backend/alembic/versions/0002_tenant_rls.py's forced-RLS table set.
TENANT_RLS_TABLES: tuple[str, ...] = (
    "workspaces",
    "data_migration_runs",
    "portfolios",
    "transactions",
    "watchlists",
    "watchlist_items",
    "workspace_settings",
    "broker_connections",
    "broker_balances",
    "options_trades",
    "polymarket_positions",
    "discord_webhooks",
    "trade_notes",
    "cash_interest_rates",
    "dividend_notifications",
    "price_alerts",
    "memberships",
    "user_settings",
    "benchmarks",
    "benchmark_components",
    "audit_logs",
    "usage_counters",
    "usage_reservations",
    "notification_outbox",
)

# Every application table -- RLS-forced tenant tables plus the identity/audit
# tables that are access-controlled at the application layer instead.
ALL_TABLES: tuple[str, ...] = (
    "users",
    "auth_sessions",
    "job_runs",
) + TENANT_RLS_TABLES


@dataclass(frozen=True)
class RestoreControl:
    table_counts: dict[str, int]
    control_totals: dict[str, str]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RestoreControl":
        return cls(
            table_counts={str(k): int(v) for k, v in payload["table_counts"].items()},
            control_totals={str(k): str(v) for k, v in payload["control_totals"].items()},
        )

    def to_dict(self) -> dict[str, Any]:
        return {"table_counts": self.table_counts, "control_totals": self.control_totals}


@dataclass(frozen=True)
class RestoreValidationResult:
    ok: bool
    errors: list[str]
    table_counts: dict[str, int]
    control_totals: dict[str, str]


class RestoreInspector(Protocol):
    def alembic_head(self) -> str | None: ...
    def runtime_role_flags(self) -> dict[str, bool]: ...
    def rls_status(self, tables: Sequence[str]) -> dict[str, tuple[bool, bool]]: ...
    def policy_counts(self, tables: Sequence[str]) -> dict[str, int]: ...
    def table_counts(self, tables: Sequence[str]) -> dict[str, int]: ...
    def transaction_control_totals(self) -> dict[str, str]: ...


class PostgresRestoreInspector:
    """Read-only catalog/data inspection for one restored PostgreSQL database."""

    def __init__(self, connection) -> None:
        self._connection = connection

    def alembic_head(self) -> str | None:
        try:
            return self._connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
        except SQLAlchemyError:
            return None

    def runtime_role_flags(self) -> dict[str, bool]:
        row = self._connection.execute(text(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'portfyl_runtime'"
        )).one_or_none()
        if row is None:
            return {"exists": False, "rolsuper": False, "rolbypassrls": False}
        rolsuper, rolbypassrls = row
        return {"exists": True, "rolsuper": bool(rolsuper), "rolbypassrls": bool(rolbypassrls)}

    def rls_status(self, tables: Sequence[str]) -> dict[str, tuple[bool, bool]]:
        rows = self._connection.execute(text("""
            SELECT relname, relrowsecurity, relforcerowsecurity
            FROM pg_class
            JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
            WHERE pg_namespace.nspname = 'public' AND relname = ANY(:tables)
        """), {"tables": list(tables)}).all()
        return {name: (bool(row_security), bool(forced)) for name, row_security, forced in rows}

    def policy_counts(self, tables: Sequence[str]) -> dict[str, int]:
        rows = self._connection.execute(text("""
            SELECT tablename, count(*)
            FROM pg_policies
            WHERE schemaname = 'public' AND tablename = ANY(:tables)
            GROUP BY tablename
        """), {"tables": list(tables)}).all()
        return {name: int(count) for name, count in rows}

    def table_counts(self, tables: Sequence[str]) -> dict[str, int]:
        quote = self._connection.dialect.identifier_preparer.quote
        return {
            table: self._connection.execute(
                text(f"SELECT count(*) FROM {quote(table)}")
            ).scalar_one()
            for table in tables
        }

    def transaction_control_totals(self) -> dict[str, str]:
        rows = self._connection.execute(text("""
            SELECT
                portfolios.name, transactions.ticker, transactions.name, transactions.type,
                transactions.shares, transactions.price, transactions.amount,
                transactions.currency, transactions.cash_amount, transactions.cash_currency,
                transactions.date, transactions.notes, transactions.source, transactions.fx_to_czk
            FROM transactions
            JOIN portfolios
              ON portfolios.workspace_id = transactions.workspace_id
             AND portfolios.id = transactions.portfolio_id
        """)).all()
        records = [dict(zip(_TRANSACTION_FIELDS, row, strict=True)) for row in rows]
        return _control_totals(records)


def validate_restore(
    inspector: RestoreInspector,
    control: RestoreControl,
    expected_head: str,
) -> RestoreValidationResult:
    errors: list[str] = []

    actual_head = inspector.alembic_head()
    if actual_head != expected_head:
        errors.append(
            f"alembic revision mismatch: expected {expected_head}, got {actual_head or 'none'}"
        )

    rls_status = inspector.rls_status(TENANT_RLS_TABLES)
    for table in TENANT_RLS_TABLES:
        row_security, forced = rls_status.get(table, (False, False))
        if not (row_security and forced):
            errors.append(f"{table}: row level security is not enabled and forced")

    policy_counts = inspector.policy_counts(TENANT_RLS_TABLES)
    for table in TENANT_RLS_TABLES:
        if policy_counts.get(table, 0) < 1:
            errors.append(f"{table}: no row security policy present")

    runtime_role = inspector.runtime_role_flags()
    if runtime_role.get("rolbypassrls"):
        errors.append("portfyl_runtime role has BYPASSRLS")
    if runtime_role.get("rolsuper"):
        errors.append("portfyl_runtime role is a superuser")

    actual_counts = inspector.table_counts(sorted(control.table_counts))
    if actual_counts != control.table_counts:
        errors.append(
            f"table counts differ: expected={control.table_counts!r}, actual={actual_counts!r}"
        )

    actual_totals = inspector.transaction_control_totals()
    if actual_totals != control.control_totals:
        errors.append(
            f"control totals differ: expected={control.control_totals!r}, actual={actual_totals!r}"
        )

    return RestoreValidationResult(
        ok=not errors, errors=errors, table_counts=actual_counts, control_totals=actual_totals,
    )


def capture_control(inspector: RestoreInspector) -> RestoreControl:
    return RestoreControl(
        table_counts=inspector.table_counts(ALL_TABLES),
        control_totals=inspector.transaction_control_totals(),
    )


def _normalize_url(url: str) -> str:
    normalized = url.strip()
    if normalized.startswith("postgres://"):
        normalized = "postgresql+psycopg://" + normalized.removeprefix("postgres://")
    elif normalized.startswith("postgresql://"):
        normalized = "postgresql+psycopg://" + normalized.removeprefix("postgresql://")
    return normalized


def _masked_source(url: str) -> str:
    return make_url(_normalize_url(url)).render_as_string(hide_password=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate (or capture a baseline for) a restored Portfyl PostgreSQL database"
    )
    parser.add_argument(
        "--database-url-env", required=True,
        help="Name of the environment variable holding the database URL; the URL itself is never logged",
    )
    parser.add_argument("--control-file", help="Path to the JSON control file (validate mode)")
    parser.add_argument("--expected-alembic-head", default=EXPECTED_ALEMBIC_HEAD)
    parser.add_argument("--capture", action="store_true", help="Write a fresh control file instead of validating")
    parser.add_argument("--output", help="Path to write the captured control file (--capture mode)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    database_url = os.environ.get(args.database_url_env)
    if not database_url:
        print(f"environment variable {args.database_url_env} is not set", file=sys.stderr)
        return 1

    if args.capture:
        if not args.output:
            print("--capture requires --output", file=sys.stderr)
            return 1
        output_path = Path(args.output)
    else:
        if not args.control_file:
            print("--control-file is required unless --capture is set", file=sys.stderr)
            return 1
        control_path = Path(args.control_file)
        if not control_path.is_file():
            print(f"control file not found: {control_path}", file=sys.stderr)
            return 1
        control = RestoreControl.from_dict(json.loads(control_path.read_text()))

    engine = create_engine(_normalize_url(database_url), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            inspector = PostgresRestoreInspector(connection)
            if args.capture:
                control = capture_control(inspector)
                output_path.write_text(json.dumps(control.to_dict(), sort_keys=True, indent=2))
                print(f"captured control file for {_masked_source(database_url)} -> {output_path}")
                return 0

            result = validate_restore(inspector, control, args.expected_alembic_head)
    finally:
        engine.dispose()

    if result.ok:
        print(json.dumps({"ok": True, "table_counts": result.table_counts}, sort_keys=True))
        return 0

    print(f"restore validation failed for {_masked_source(database_url)}:", file=sys.stderr)
    for error in result.errors:
        print(f"  - {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
