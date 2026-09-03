from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

import database
from models import (
    Benchmark,
    BenchmarkComponent,
    Membership,
    Portfolio,
    Transaction,
    User,
    Workspace,
)


RLS_TABLES = {
    "workspaces",
    "memberships",
    "user_settings",
    "workspace_settings",
    "data_migration_runs",
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
    "job_runs",
}


@dataclass(frozen=True)
class TenantRows:
    alice_id: UUID
    alice_workspace_id: UUID
    bob_workspace_id: UUID
    alice_portfolio_internal_id: int
    bob_portfolio_internal_id: int
    alice_portfolio_id: UUID
    bob_portfolio_id: UUID


@pytest.fixture(scope="module")
def tenant_rows(postgres_engine) -> TenantRows:
    db = sessionmaker(bind=postgres_engine)()
    try:
        alice = User(firebase_uid="alice-firebase", email="alice@example.com")
        bob = User(firebase_uid="bob-firebase", email="bob@example.com")
        alice_workspace = Workspace(name="Alice workspace")
        bob_workspace = Workspace(name="Bob workspace")
        db.add_all([alice, bob, alice_workspace, bob_workspace])
        db.flush()
        db.add_all(
            [
                Membership(user_id=alice.id, workspace_id=alice_workspace.id),
                Membership(user_id=bob.id, workspace_id=bob_workspace.id),
            ]
        )
        alice_portfolio = Portfolio(workspace_id=alice_workspace.id, name="Alice portfolio")
        bob_portfolio = Portfolio(workspace_id=bob_workspace.id, name="Bob portfolio")
        db.add_all([alice_portfolio, bob_portfolio])
        db.commit()
        return TenantRows(
            alice_id=alice.id,
            alice_workspace_id=alice_workspace.id,
            bob_workspace_id=bob_workspace.id,
            alice_portfolio_internal_id=alice_portfolio.id,
            bob_portfolio_internal_id=bob_portfolio.id,
            alice_portfolio_id=alice_portfolio.public_id,
            bob_portfolio_id=bob_portfolio.public_id,
        )
    finally:
        db.close()


def _set_context(session: Session, user_id: UUID, workspace_id: UUID | None) -> None:
    setter = getattr(database, "set_rls_context", None)
    assert setter is not None, "set_rls_context must be implemented"
    setter(session, user_id, workspace_id)


def test_missing_rls_context_matches_no_private_rows(
    runtime_session: Session,
    tenant_rows: TenantRows,
):
    visible = runtime_session.scalars(select(Portfolio)).all()

    assert visible == []


def test_runtime_role_cannot_read_foreign_workspace(
    runtime_session: Session,
    tenant_rows: TenantRows,
):
    _set_context(
        runtime_session,
        tenant_rows.alice_id,
        tenant_rows.alice_workspace_id,
    )

    own = runtime_session.scalars(
        select(Portfolio).where(Portfolio.public_id == tenant_rows.alice_portfolio_id)
    ).all()
    foreign = runtime_session.scalars(
        select(Portfolio).where(Portfolio.public_id == tenant_rows.bob_portfolio_id)
    ).all()

    assert len(own) == 1
    assert foreign == []


def test_runtime_role_cannot_update_or_delete_foreign_workspace(
    runtime_session: Session,
    tenant_rows: TenantRows,
):
    _set_context(
        runtime_session,
        tenant_rows.alice_id,
        tenant_rows.alice_workspace_id,
    )
    updated = runtime_session.execute(
        text("UPDATE portfolios SET name = 'Compromised' WHERE public_id = :id"),
        {"id": tenant_rows.bob_portfolio_id},
    )
    deleted = runtime_session.execute(
        text("DELETE FROM portfolios WHERE public_id = :id"),
        {"id": tenant_rows.bob_portfolio_id},
    )

    assert updated.rowcount == 0
    assert deleted.rowcount == 0


def test_runtime_role_cannot_insert_foreign_workspace(
    runtime_session: Session,
    tenant_rows: TenantRows,
):
    _set_context(
        runtime_session,
        tenant_rows.alice_id,
        tenant_rows.alice_workspace_id,
    )
    runtime_session.add(
        Portfolio(workspace_id=tenant_rows.bob_workspace_id, name="Cross-tenant insert")
    )

    with pytest.raises(DBAPIError, match="row-level security"):
        runtime_session.flush()


def test_child_cannot_reference_foreign_workspace_parent(
    runtime_session: Session,
    tenant_rows: TenantRows,
):
    _set_context(
        runtime_session,
        tenant_rows.alice_id,
        tenant_rows.alice_workspace_id,
    )
    runtime_session.add(
        Transaction(
            workspace_id=tenant_rows.alice_workspace_id,
            portfolio_id=tenant_rows.bob_portfolio_internal_id,
            ticker="CROSS",
            type="buy",
            shares=1,
            price=1,
            date=date(2026, 9, 1),
        )
    )

    with pytest.raises(IntegrityError, match="foreign key"):
        runtime_session.flush()


def test_runtime_role_cannot_create_global_preset(
    runtime_session: Session,
    tenant_rows: TenantRows,
):
    _set_context(
        runtime_session,
        tenant_rows.alice_id,
        tenant_rows.alice_workspace_id,
    )
    runtime_session.add(
        Benchmark(
            workspace_id=tenant_rows.alice_workspace_id,
            portfolio_id=tenant_rows.alice_portfolio_internal_id,
            name="Forged preset",
            kind="ticker",
            ticker="FAKE",
            is_preset=True,
        )
    )

    with pytest.raises(DBAPIError, match="row-level security"):
        runtime_session.flush()


def test_runtime_role_cannot_attach_tenant_component_to_preset(
    runtime_session: Session,
    tenant_rows: TenantRows,
):
    _set_context(
        runtime_session,
        tenant_rows.alice_id,
        tenant_rows.alice_workspace_id,
    )
    preset_id = runtime_session.scalar(
        select(Benchmark.id).where(Benchmark.is_preset.is_(True)).limit(1)
    )
    assert preset_id is not None
    runtime_session.add(
        BenchmarkComponent(
            workspace_id=tenant_rows.alice_workspace_id,
            benchmark_id=preset_id,
            ticker="LEAK",
            weight=1.0,
        )
    )

    with pytest.raises(DBAPIError, match="row-level security"):
        runtime_session.flush()


def test_seeded_presets_are_visible_without_tenant_context(runtime_session: Session):
    presets = runtime_session.scalars(
        select(Benchmark).where(Benchmark.is_preset.is_(True))
    ).all()

    assert {row.name for row in presets} == {
        "S&P 500",
        "NASDAQ 100",
        "Dow Jones",
        "STOXX 50",
        "MSCI World",
        "MSCI ACWI",
        "60/40 (World + Agg Bond)",
    }


def test_rls_context_is_transaction_local(postgres_engine, tenant_rows: TenantRows):
    connection = postgres_engine.connect()
    try:
        first_transaction = connection.begin()
        connection.execute(text("SET LOCAL ROLE portfyl_runtime"))
        first_session = sessionmaker(bind=connection)()
        _set_context(
            first_session,
            tenant_rows.alice_id,
            tenant_rows.alice_workspace_id,
        )
        assert len(first_session.scalars(select(Portfolio)).all()) == 1
        first_session.close()
        first_transaction.rollback()

        second_transaction = connection.begin()
        connection.execute(text("SET LOCAL ROLE portfyl_runtime"))
        second_session = sessionmaker(bind=connection)()
        assert second_session.scalars(select(Portfolio)).all() == []
        second_session.close()
        second_transaction.rollback()
    finally:
        connection.close()


def test_all_tenant_tables_enable_and_force_rls(postgres_session: Session):
    rows = postgres_session.execute(
        text("""
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = ANY(:tables)
        """),
        {"tables": sorted(RLS_TABLES)},
    ).all()

    assert {name for name, _, _ in rows} == RLS_TABLES
    assert all(enabled and forced for _, enabled, forced in rows)


def test_runtime_role_is_non_owner_without_rls_bypass(postgres_session: Session):
    role = postgres_session.execute(
        text("""
            SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls
            FROM pg_roles
            WHERE rolname = 'portfyl_runtime'
        """)
    ).one()
    portfolio_owner = postgres_session.execute(
        text("""
            SELECT pg_get_userbyid(c.relowner)
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = 'portfolios'
        """)
    ).scalar_one()

    assert role == (False, False, False, False)
    assert portfolio_owner != "portfyl_runtime"


def test_runtime_role_can_read_head_but_cannot_mutate_migration_tables(
    postgres_session: Session,
):
    grants = postgres_session.execute(
        text("""
            SELECT table_name, privilege_type
            FROM information_schema.role_table_grants
            WHERE grantee = 'portfyl_runtime'
              AND table_schema = 'public'
              AND table_name IN ('alembic_version', 'data_migration_runs')
        """)
    ).all()

    assert grants == [("alembic_version", "SELECT")]


def test_runtime_role_startup_head_check_is_read_only(runtime_session: Session):
    database.assert_alembic_head(runtime_session)

    with pytest.raises(DBAPIError, match="permission denied"):
        runtime_session.execute(
            text("UPDATE alembic_version SET version_num = 'tampered'")
        )
