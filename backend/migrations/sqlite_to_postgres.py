from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable
from uuid import UUID, uuid4

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


EXPECTED_ALEMBIC_HEAD = "0002_tenant_rls"
PERSONAL_SETTING_KEYS = frozenset({"deepseek_api_key", "deepseek_model"})
WORKSPACE_SETTING_KEYS = frozenset({
    "broker_sync_mode",
    "broker_sync_daily_time",
    "broker_sync_interval_hours",
    "broker_sync_last_run",
    "sync_mode",
    "sync_daily_time",
    "sync_interval_hours",
    "sync_last_run",
})
IDENTITY_TABLES = (
    "portfolios",
    "transactions",
    "watchlists",
    "watchlist_items",
    "benchmarks",
    "benchmark_components",
    "broker_connections",
    "broker_balances",
    "options_trades",
    "polymarket_positions",
    "discord_webhooks",
    "trade_notes",
    "cash_interest_rates",
    "dividend_notifications",
    "price_alerts",
)


class MigrationError(RuntimeError):
    """Base class for safe, operator-facing migration failures."""


class MigrationAlreadyApplied(MigrationError):
    """Raised when the same source fingerprint already succeeded."""


class MigrationReconciliationError(MigrationError):
    """Raised when copied data does not reconcile with the source."""


@dataclass(frozen=True)
class MigrationOptions:
    source: Path
    target_url: str
    owner_email: str
    dry_run: bool


@dataclass(frozen=True)
class MigrationReport:
    source_sha256: str
    workspace_id: UUID
    table_counts: dict[str, int]
    control_totals: dict[str, str]
    status: str


def _normalize_target_url(url: str) -> str:
    normalized = url.strip()
    if normalized.startswith("postgres://"):
        normalized = "postgresql+psycopg://" + normalized.removeprefix("postgres://")
    elif normalized.startswith("postgresql://"):
        normalized = "postgresql+psycopg://" + normalized.removeprefix("postgresql://")
    if not normalized.startswith("postgresql+psycopg://"):
        raise MigrationError("target database URL must use PostgreSQL with psycopg")
    return normalized


def _normalize_owner_email(email: str) -> str:
    normalized = email.strip().casefold()
    if not normalized or "@" not in normalized:
        raise MigrationError("owner e-mail must be a valid non-empty address")
    return normalized


def _source_sha256(path: Path) -> str:
    if not path.is_file():
        raise MigrationError(f"SQLite source does not exist: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _open_source(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise MigrationError(f"SQLite source does not exist: {path}")
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    violations = connection.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        connection.close()
        raise MigrationError(f"SQLite source has {len(violations)} foreign-key violation(s)")
    return connection


def _table_exists(source: sqlite3.Connection, table: str) -> bool:
    return source.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone() is not None


def _rows(source: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    if not _table_exists(source, table):
        return []
    return list(source.execute(f'SELECT * FROM "{table}" ORDER BY id'))


def _value(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    return row[key] if key in row.keys() else default


def _as_bool(value: Any, default: bool = False) -> bool:
    return default if value is None else bool(value)


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def _as_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _add_mapped_rows(
    db: Session,
    rows: Iterable[sqlite3.Row],
    factory,
) -> tuple[dict[int, Any], list[Any]]:
    source_rows = list(rows)
    objects = [factory(row) for row in source_rows]
    for row, obj in zip(source_rows, objects, strict=True):
        obj.id = int(row["id"])
    db.add_all(objects)
    db.flush()
    return {
        int(row["id"]): obj for row, obj in zip(source_rows, objects, strict=True)
    }, objects


def _copy_source(
    source: sqlite3.Connection,
    db: Session,
    user_id: UUID,
    workspace_id: UUID,
) -> dict[str, int]:
    from models import (
        Benchmark,
        BenchmarkComponent,
        BrokerBalance,
        BrokerConnection,
        CashInterestRate,
        DiscordWebhook,
        DividendNotification,
        OptionsTrade,
        PolymarketPosition,
        Portfolio,
        PriceAlert,
        TradeNote,
        Transaction,
        UserSetting,
        Watchlist,
        WatchlistItem,
        WorkspaceSetting,
    )

    portfolio_map, portfolios = _add_mapped_rows(
        db,
        _rows(source, "portfolios"),
        lambda row: Portfolio(
            workspace_id=workspace_id,
            name=row["name"],
            color=_value(row, "color"),
            is_default=_as_bool(_value(row, "is_default")),
            t212_csv_covered_through=_as_datetime(
                _value(row, "t212_csv_covered_through")
            ),
            created_at=_as_datetime(_value(row, "created_at")),
        ),
    )

    transaction_map, transactions = _add_mapped_rows(
        db,
        _rows(source, "transactions"),
        lambda row: Transaction(
            workspace_id=workspace_id,
            portfolio_id=portfolio_map[int(row["portfolio_id"])].id,
            ticker=_value(row, "ticker"),
            name=_value(row, "name"),
            type=row["type"],
            shares=row["shares"],
            price=row["price"],
            amount=_value(row, "amount"),
            currency=_value(row, "currency") or "USD",
            cash_amount=_value(row, "cash_amount"),
            cash_currency=_value(row, "cash_currency"),
            date=_as_date(row["date"]),
            notes=_value(row, "notes"),
            source=_value(row, "source"),
            fx_to_czk=_value(row, "fx_to_czk"),
            created_at=_as_datetime(_value(row, "created_at")),
        ),
    )

    watchlist_map, watchlists = _add_mapped_rows(
        db,
        _rows(source, "watchlists"),
        lambda row: Watchlist(
            workspace_id=workspace_id,
            name=row["name"],
            color=_value(row, "color"),
            created_at=_as_datetime(_value(row, "created_at")),
        ),
    )
    _, watchlist_items = _add_mapped_rows(
        db,
        _rows(source, "watchlist_items"),
        lambda row: WatchlistItem(
            workspace_id=workspace_id,
            watchlist_id=watchlist_map[int(row["watchlist_id"])].id,
            ticker=row["ticker"],
            note=_value(row, "note"),
            created_at=_as_datetime(_value(row, "created_at")),
        ),
    )

    legacy_benchmarks = [
        row for row in _rows(source, "benchmarks")
        if not _as_bool(_value(row, "is_preset"))
    ]
    benchmark_map, benchmarks = _add_mapped_rows(
        db,
        legacy_benchmarks,
        lambda row: Benchmark(
            workspace_id=workspace_id,
            portfolio_id=portfolio_map[int(row["portfolio_id"])].id,
            name=row["name"],
            kind=row["kind"],
            ticker=_value(row, "ticker"),
            is_default=_as_bool(_value(row, "is_default")),
            is_preset=False,
            created_at=_as_datetime(_value(row, "created_at")),
        ),
    )
    legacy_components = [
        row for row in _rows(source, "benchmark_components")
        if int(row["benchmark_id"]) in benchmark_map
    ]
    _, benchmark_components = _add_mapped_rows(
        db,
        legacy_components,
        lambda row: BenchmarkComponent(
            workspace_id=workspace_id,
            benchmark_id=benchmark_map[int(row["benchmark_id"])].id,
            ticker=row["ticker"],
            weight=row["weight"],
        ),
    )

    _, broker_connections = _add_mapped_rows(
        db,
        _rows(source, "broker_connections"),
        lambda row: BrokerConnection(
            workspace_id=workspace_id,
            portfolio_id=portfolio_map[int(row["portfolio_id"])].id,
            broker=row["broker"],
            api_key=row["api_key"],
            api_secret=_value(row, "api_secret") or "",
            environment=_value(row, "environment") or "live",
            auto_sync=_as_bool(_value(row, "auto_sync")),
            last_synced_at=_as_datetime(_value(row, "last_synced_at")),
            t212_csv_covered_through=_as_datetime(
                _value(row, "t212_csv_covered_through")
            ),
            created_at=_as_datetime(_value(row, "created_at")),
        ),
    )
    _, broker_balances = _add_mapped_rows(
        db,
        _rows(source, "broker_balances"),
        lambda row: BrokerBalance(
            workspace_id=workspace_id,
            portfolio_id=portfolio_map[int(row["portfolio_id"])].id,
            broker=row["broker"],
            base_currency=_value(row, "base_currency"),
            cash=_value(row, "cash"),
            stock=_value(row, "stock"),
            options_value=_value(row, "options_value"),
            net_liquidation=_value(row, "net_liquidation"),
            cash_by_currency=_value(row, "cash_by_currency"),
            as_of=_as_date(_value(row, "as_of")),
            updated_at=_as_datetime(_value(row, "updated_at")),
        ),
    )
    _, options_trades = _add_mapped_rows(
        db,
        _rows(source, "options_trades"),
        lambda row: OptionsTrade(
            workspace_id=workspace_id,
            portfolio_id=portfolio_map[int(row["portfolio_id"])].id,
            underlying=row["underlying"],
            strike=row["strike"],
            expiry=_as_date(row["expiry"]),
            put_call=row["put_call"],
            quantity=row["quantity"],
            open_price=row["open_price"],
            close_price=_value(row, "close_price"),
            open_date=_as_date(row["open_date"]),
            close_date=_as_date(_value(row, "close_date")),
            status=_value(row, "status") or "closed",
            multiplier=_value(row, "multiplier", 100),
            currency=_value(row, "currency") or "USD",
            pnl=_value(row, "pnl"),
            commission=_value(row, "commission", 0.0),
            source=_value(row, "source"),
            fx_to_czk=_value(row, "fx_to_czk"),
            notes=_value(row, "notes"),
            created_at=_as_datetime(_value(row, "created_at")),
        ),
    )
    _, polymarket_positions = _add_mapped_rows(
        db,
        _rows(source, "polymarket_positions"),
        lambda row: PolymarketPosition(
            workspace_id=workspace_id,
            portfolio_id=portfolio_map[int(row["portfolio_id"])].id,
            condition_id=row["condition_id"],
            asset_id=row["asset_id"],
            market_slug=_value(row, "market_slug"),
            question=row["question"],
            outcome=row["outcome"],
            size=row["size"],
            avg_price=row["avg_price"],
            current_price=_value(row, "current_price"),
            resolved_price=_value(row, "resolved_price"),
            status=_value(row, "status") or "open",
            pnl=_value(row, "pnl"),
            source=_value(row, "source") or "polymarket",
            created_at=_as_datetime(_value(row, "created_at")),
            updated_at=_as_datetime(_value(row, "updated_at")),
        ),
    )
    _, discord_webhooks = _add_mapped_rows(
        db,
        _rows(source, "discord_webhooks"),
        lambda row: DiscordWebhook(
            workspace_id=workspace_id,
            portfolio_id=portfolio_map[int(row["portfolio_id"])].id,
            webhook_url=row["webhook_url"],
            notify_trades=_as_bool(_value(row, "notify_trades"), True),
            notify_dividends=_as_bool(_value(row, "notify_dividends"), True),
            notify_milestones=_as_bool(_value(row, "notify_milestones"), True),
            created_at=_as_datetime(_value(row, "created_at")),
        ),
    )
    _, trade_notes = _add_mapped_rows(
        db,
        _rows(source, "trade_notes"),
        lambda row: TradeNote(
            workspace_id=workspace_id,
            transaction_id=transaction_map[int(row["transaction_id"])].id,
            content=row["content"],
            tags=_value(row, "tags"),
            sentiment=_value(row, "sentiment"),
            updated_at=_as_datetime(_value(row, "updated_at")),
        ),
    )
    _, cash_interest_rates = _add_mapped_rows(
        db,
        _rows(source, "cash_interest_rates"),
        lambda row: CashInterestRate(
            workspace_id=workspace_id,
            portfolio_id=portfolio_map[int(row["portfolio_id"])].id,
            currency=row["currency"],
            annual_rate=row["annual_rate"],
            enabled=_as_bool(row["enabled"]),
            start_date=_as_date(_value(row, "start_date")),
            created_at=_as_datetime(_value(row, "created_at")),
        ),
    )
    _, dividend_notifications = _add_mapped_rows(
        db,
        _rows(source, "dividend_notifications"),
        lambda row: DividendNotification(
            workspace_id=workspace_id,
            portfolio_id=portfolio_map[int(row["portfolio_id"])].id,
            ticker=row["ticker"],
            ex_date=_as_date(row["ex_date"]),
            sent_at=_as_datetime(_value(row, "sent_at")),
        ),
    )
    _, price_alerts = _add_mapped_rows(
        db,
        _rows(source, "price_alerts"),
        lambda row: PriceAlert(
            workspace_id=workspace_id,
            portfolio_id=portfolio_map[int(row["portfolio_id"])].id,
            ticker=row["ticker"],
            direction=row["direction"],
            target_price=row["target_price"],
            note=_value(row, "note"),
            enabled=_as_bool(_value(row, "enabled"), True),
            status=_value(row, "status") or "active",
            last_triggered_at=_as_datetime(_value(row, "last_triggered_at")),
            triggered_price=_value(row, "triggered_price"),
            created_at=_as_datetime(_value(row, "created_at")),
        ),
    )

    setting_rows = _rows(source, "app_settings")
    unknown_keys = {
        row["key"] for row in setting_rows
        if row["key"] not in PERSONAL_SETTING_KEYS | WORKSPACE_SETTING_KEYS
    }
    if unknown_keys:
        raise MigrationError(
            "unclassified legacy setting key(s): " + ", ".join(sorted(unknown_keys))
        )
    user_settings = [
        UserSetting(
            user_id=user_id,
            key=row["key"],
            value=_value(row, "value"),
            created_at=_as_datetime(_value(row, "updated_at")),
            updated_at=_as_datetime(_value(row, "updated_at")),
        )
        for row in setting_rows if row["key"] in PERSONAL_SETTING_KEYS
    ]
    workspace_settings = [
        WorkspaceSetting(
            workspace_id=workspace_id,
            key=row["key"],
            value=_value(row, "value"),
            created_at=_as_datetime(_value(row, "updated_at")),
            updated_at=_as_datetime(_value(row, "updated_at")),
        )
        for row in setting_rows if row["key"] in WORKSPACE_SETTING_KEYS
    ]
    db.add_all(user_settings + workspace_settings)
    db.flush()

    return {
        "users": 1,
        "workspaces": 1,
        "memberships": 1,
        "portfolios": len(portfolios),
        "transactions": len(transactions),
        "watchlists": len(watchlists),
        "watchlist_items": len(watchlist_items),
        "benchmarks": len(benchmarks),
        "benchmark_components": len(benchmark_components),
        "broker_connections": len(broker_connections),
        "broker_balances": len(broker_balances),
        "options_trades": len(options_trades),
        "polymarket_positions": len(polymarket_positions),
        "discord_webhooks": len(discord_webhooks),
        "trade_notes": len(trade_notes),
        "cash_interest_rates": len(cash_interest_rates),
        "dividend_notifications": len(dividend_notifications),
        "price_alerts": len(price_alerts),
        "user_settings": len(user_settings),
        "workspace_settings": len(workspace_settings),
    }


def _target_counts(db: Session, user_id: UUID, workspace_id: UUID) -> dict[str, int]:
    from models import (
        Benchmark,
        BenchmarkComponent,
        BrokerBalance,
        BrokerConnection,
        CashInterestRate,
        DiscordWebhook,
        DividendNotification,
        Membership,
        OptionsTrade,
        PolymarketPosition,
        Portfolio,
        PriceAlert,
        TradeNote,
        Transaction,
        User,
        UserSetting,
        Watchlist,
        WatchlistItem,
        Workspace,
        WorkspaceSetting,
    )

    scoped_models = {
        "portfolios": Portfolio,
        "transactions": Transaction,
        "watchlists": Watchlist,
        "watchlist_items": WatchlistItem,
        "benchmarks": Benchmark,
        "benchmark_components": BenchmarkComponent,
        "broker_connections": BrokerConnection,
        "broker_balances": BrokerBalance,
        "options_trades": OptionsTrade,
        "polymarket_positions": PolymarketPosition,
        "discord_webhooks": DiscordWebhook,
        "trade_notes": TradeNote,
        "cash_interest_rates": CashInterestRate,
        "dividend_notifications": DividendNotification,
        "price_alerts": PriceAlert,
        "workspace_settings": WorkspaceSetting,
    }
    counts = {
        name: db.scalar(
            select(func.count()).select_from(model).where(model.workspace_id == workspace_id)
        ) or 0
        for name, model in scoped_models.items()
    }
    counts.update({
        "users": db.scalar(
            select(func.count()).select_from(User).where(User.id == user_id)
        ) or 0,
        "workspaces": db.scalar(
            select(func.count()).select_from(Workspace).where(Workspace.id == workspace_id)
        ) or 0,
        "memberships": db.scalar(
            select(func.count()).select_from(Membership).where(
                Membership.user_id == user_id,
                Membership.workspace_id == workspace_id,
            )
        ) or 0,
        "user_settings": db.scalar(
            select(func.count()).select_from(UserSetting).where(
                UserSetting.user_id == user_id
            )
        ) or 0,
    })
    return {name: int(value) for name, value in counts.items()}


def _reset_identity_sequences(db: Session) -> None:
    quote = db.bind.dialect.identifier_preparer.quote
    for table in IDENTITY_TABLES:
        max_id = db.scalar(text(f'SELECT max(id) FROM {quote(table)}'))
        next_id = max(0, int(max_id or 0)) + 1
        sequence = f"{table}_id_seq"
        db.execute(text(
            f"ALTER SEQUENCE {quote(sequence)} RESTART WITH {next_id}"
        ))


_TRANSACTION_FIELDS = (
    "portfolio_name",
    "ticker",
    "name",
    "type",
    "shares",
    "price",
    "amount",
    "currency",
    "cash_amount",
    "cash_currency",
    "date",
    "notes",
    "source",
    "fx_to_czk",
)


def _decimal_text(value: Any) -> str:
    decimal = Decimal(str(value or 0))
    if decimal == 0:
        return "0"
    return format(decimal.normalize(), "f")


def _canonical_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return _decimal_text(value)
    return value


def _control_totals(records: list[dict[str, Any]]) -> dict[str, str]:
    canonical = [
        {field: _canonical_value(record.get(field)) for field in _TRANSACTION_FIELDS}
        for record in records
    ]
    serialized_rows = [
        json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        for record in canonical
    ]
    payload = "\n".join(sorted(serialized_rows)).encode("utf-8")
    return {
        "transactions_sha256": hashlib.sha256(payload).hexdigest(),
        "transaction_count": str(len(records)),
        "transaction_shares_sum": _decimal_text(
            sum(Decimal(str(record.get("shares") or 0)) for record in records)
        ),
        "transaction_amount_sum": _decimal_text(
            sum(Decimal(str(record.get("amount") or 0)) for record in records)
        ),
        "transaction_cash_amount_sum": _decimal_text(
            sum(Decimal(str(record.get("cash_amount") or 0)) for record in records)
        ),
    }


def _source_control_totals(source: sqlite3.Connection) -> dict[str, str]:
    portfolio_names = {
        int(row["id"]): row["name"] for row in _rows(source, "portfolios")
    }
    records = []
    for row in _rows(source, "transactions"):
        records.append({
            "portfolio_name": portfolio_names[int(row["portfolio_id"])],
            **{field: _value(row, field) for field in _TRANSACTION_FIELDS[1:]},
        })
    return _control_totals(records)


def _target_control_totals(db: Session, workspace_id: UUID) -> dict[str, str]:
    from models import Portfolio, Transaction

    rows = db.execute(
        select(Transaction, Portfolio.name)
        .join(
            Portfolio,
            (Portfolio.workspace_id == Transaction.workspace_id)
            & (Portfolio.id == Transaction.portfolio_id),
        )
        .where(Transaction.workspace_id == workspace_id)
    ).all()
    records = []
    for transaction, portfolio_name in rows:
        records.append({
            "portfolio_name": portfolio_name,
            **{
                field: getattr(transaction, field)
                for field in _TRANSACTION_FIELDS[1:]
            },
        })
    return _control_totals(records)


def _foreign_key_violations(db: Session) -> list[str]:
    constraints = db.execute(text("""
        SELECT
            constraint_row.conname,
            constraint_row.convalidated,
            child_namespace.nspname,
            child_table.relname,
            parent_namespace.nspname,
            parent_table.relname,
            ARRAY(
                SELECT child_attribute.attname
                FROM unnest(constraint_row.conkey) WITH ORDINALITY AS key(attnum, position)
                JOIN pg_attribute AS child_attribute
                  ON child_attribute.attrelid = constraint_row.conrelid
                 AND child_attribute.attnum = key.attnum
                ORDER BY key.position
            ) AS child_columns,
            ARRAY(
                SELECT parent_attribute.attname
                FROM unnest(constraint_row.confkey) WITH ORDINALITY AS key(attnum, position)
                JOIN pg_attribute AS parent_attribute
                  ON parent_attribute.attrelid = constraint_row.confrelid
                 AND parent_attribute.attnum = key.attnum
                ORDER BY key.position
            ) AS parent_columns
        FROM pg_constraint AS constraint_row
        JOIN pg_class AS child_table ON child_table.oid = constraint_row.conrelid
        JOIN pg_namespace AS child_namespace ON child_namespace.oid = child_table.relnamespace
        JOIN pg_class AS parent_table ON parent_table.oid = constraint_row.confrelid
        JOIN pg_namespace AS parent_namespace ON parent_namespace.oid = parent_table.relnamespace
        WHERE constraint_row.contype = 'f'
          AND child_namespace.nspname = 'public'
    """)).all()

    quote = db.bind.dialect.identifier_preparer.quote
    violations: list[str] = []
    for (
        name,
        validated,
        child_schema,
        child_table,
        parent_schema,
        parent_table,
        child_columns,
        parent_columns,
    ) in constraints:
        if not validated:
            violations.append(f"{name}: constraint is not validated")
            continue
        child_ref = f"{quote(child_schema)}.{quote(child_table)}"
        parent_ref = f"{quote(parent_schema)}.{quote(parent_table)}"
        child_not_null = " AND ".join(
            f"child.{quote(column)} IS NOT NULL" for column in child_columns
        )
        parent_match = " AND ".join(
            f"parent.{quote(parent)} = child.{quote(child)}"
            for child, parent in zip(child_columns, parent_columns, strict=True)
        )
        orphan_count = db.scalar(text(
            f"SELECT count(*) FROM {child_ref} AS child "
            f"WHERE {child_not_null} "
            f"AND NOT EXISTS (SELECT 1 FROM {parent_ref} AS parent WHERE {parent_match})"
        ))
        if orphan_count:
            violations.append(f"{name}: {orphan_count} orphan row(s)")
    return violations


def _assert_target_empty(db: Session) -> None:
    from models import User, Workspace

    user_count = db.scalar(select(func.count()).select_from(User)) or 0
    workspace_count = db.scalar(select(func.count()).select_from(Workspace)) or 0
    if user_count or workspace_count:
        raise MigrationError(
            "target must contain no tenant users or workspaces before owner import"
        )


def _assert_migration_role(db: Session) -> str:
    role_name, is_superuser, bypasses_rls = db.execute(text("""
        SELECT role.rolname, role.rolsuper, role.rolbypassrls
        FROM pg_roles AS role
        WHERE role.rolname = current_user
    """)).one()
    if not (is_superuser or bypasses_rls):
        raise MigrationError(
            "target URL must use the migration-owner role with BYPASSRLS, not the runtime role"
        )
    return str(role_name)


def migrate_sqlite(options: MigrationOptions) -> MigrationReport:
    source_path = Path(options.source).resolve()
    fingerprint = _source_sha256(source_path)
    owner_email = _normalize_owner_email(options.owner_email)
    target_url = _normalize_target_url(options.target_url)

    os.environ.setdefault("DATABASE_URL", target_url)
    from database import assert_alembic_head, set_rls_context
    from models import DataMigrationRun, Membership, User, Workspace

    source = _open_source(source_path)
    engine = create_engine(target_url, pool_pre_ping=True)
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection)
    try:
        assert_alembic_head(db, expected_head=EXPECTED_ALEMBIC_HEAD)
        migration_role = _assert_migration_role(db)
        db.execute(text(
            "SELECT pg_advisory_xact_lock(hashtext('portfyl_sqlite_owner_migration'))"
        ))
        duplicate = db.scalar(
            select(DataMigrationRun.id).where(
                DataMigrationRun.source_fingerprint == fingerprint,
                DataMigrationRun.status == "succeeded",
            )
        )
        if duplicate is not None:
            raise MigrationAlreadyApplied(
                f"SQLite source {fingerprint} was already imported successfully"
            )
        _assert_target_empty(db)

        user_id = uuid4()
        workspace_id = uuid4()
        set_rls_context(db, user_id=user_id, workspace_id=workspace_id)
        user = User(id=user_id, email=owner_email)
        workspace = Workspace(
            id=workspace_id,
            name="Owner workspace",
        )
        membership = Membership(
            user_id=user_id,
            workspace_id=workspace_id,
            role="owner",
            status="active",
        )
        db.add_all([user, workspace])
        db.flush()
        db.add(membership)
        db.flush()

        source_counts = _copy_source(
            source,
            db,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        _reset_identity_sequences(db)
        target_counts = _target_counts(db, user_id=user_id, workspace_id=workspace_id)
        source_totals = _source_control_totals(source)
        target_totals = _target_control_totals(db, workspace_id=workspace_id)
        foreign_key_errors = _foreign_key_violations(db)

        errors = []
        if source_counts != target_counts:
            errors.append(
                f"table counts differ: source={source_counts!r}, target={target_counts!r}"
            )
        if source_totals != target_totals:
            errors.append(
                f"control totals differ: source={source_totals!r}, target={target_totals!r}"
            )
        errors.extend(foreign_key_errors)
        if errors:
            raise MigrationReconciliationError("; ".join(errors))

        status = "dry_run" if options.dry_run else "succeeded"
        report = MigrationReport(
            source_sha256=fingerprint,
            workspace_id=workspace_id,
            table_counts=source_counts,
            control_totals=source_totals,
            status=status,
        )
        if options.dry_run:
            transaction.rollback()
        else:
            db.add(DataMigrationRun(
                source_fingerprint=fingerprint,
                workspace_id=workspace_id,
                owner_email=owner_email,
                status="succeeded",
                table_counts=source_counts,
                control_totals=source_totals,
                validation_report={
                    "source_counts": source_counts,
                    "target_counts": target_counts,
                    "foreign_key_errors": foreign_key_errors,
                    "migration_role": migration_role,
                },
                completed_at=datetime.now(timezone.utc),
            ))
            try:
                db.flush()
            except IntegrityError as exc:
                if "source_fingerprint" in str(exc):
                    raise MigrationAlreadyApplied(
                        f"SQLite source {fingerprint} was already imported successfully"
                    ) from exc
                raise
            transaction.commit()
        return report
    except Exception:
        if transaction.is_active:
            transaction.rollback()
        raise
    finally:
        db.close()
        connection.close()
        engine.dispose()
        source.close()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Import one legacy Portfyl SQLite owner database into PostgreSQL"
    )
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--target-database-url", required=True)
    parser.add_argument("--owner-email", required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        report = migrate_sqlite(MigrationOptions(
            source=args.source,
            target_url=args.target_database_url,
            owner_email=args.owner_email,
            dry_run=args.dry_run,
        ))
    except Exception as exc:
        print(f"SQLite migration failed: {exc}", file=sys.stderr)
        return 1
    payload = asdict(report)
    payload["workspace_id"] = str(report.workspace_id)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
