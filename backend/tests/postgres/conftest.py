from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from database import DatabaseSettings, build_engine


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _assert_disposable_postgres_url(url: str) -> None:
    database = make_url(url).database or ""
    normalized = database.casefold()
    if not (
        normalized == "test"
        or normalized.startswith("test_")
        or normalized.endswith("_test")
    ):
        raise RuntimeError(
            "PostgreSQL integration tests require a disposable database whose name contains 'test'"
        )


@pytest.fixture(scope="session")
def postgres_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://portfyl_test:portfyl_test@localhost:55441/portfyl_test",
    )


@pytest.fixture(scope="session")
def postgres_engine(postgres_url: str) -> Engine:
    _assert_disposable_postgres_url(postgres_url)
    engine = build_engine(DatabaseSettings.from_env({"DATABASE_URL": postgres_url}))
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_roles WHERE rolname = 'portfyl_runtime'
                ) THEN
                    CREATE ROLE portfyl_runtime NOLOGIN;
                END IF;
            END
            $$
        """))
        connection.execute(text(
            "ALTER ROLE portfyl_runtime BYPASSRLS CREATEDB CREATEROLE"
        ))

    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with patch.dict(os.environ, {"DATABASE_URL": postgres_url}):
        command.upgrade(alembic_config, "head")
    try:
        yield engine
    finally:
        with patch.dict(os.environ, {"DATABASE_URL": postgres_url}):
            command.downgrade(alembic_config, "base")
        engine.dispose()


@pytest.fixture
def postgres_session(postgres_engine: Engine) -> Session:
    connection = postgres_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def runtime_session(postgres_engine: Engine) -> Session:
    connection = postgres_engine.connect()
    transaction = connection.begin()
    connection.execute(text("SET LOCAL ROLE portfyl_runtime"))
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


# ---------------------------------------------------------------------------
# Task 9: shared Alice/Bob tenant fixtures for the complete go/no-go matrix.
#
# Earlier task-scoped suites (test_portfolio_tenancy, test_financial_route_tenancy,
# test_watchlist_settings_alert_tenancy, test_integration_tenancy) each seed their
# own narrow slice and define their own `tenant_rows` / `alice_client`, which
# shadow anything here. These fixtures deliberately carry NEW names so they add
# a full-surface dataset without changing the behaviour of any existing file.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TenantContext:
    """Everything a test needs to act as -- or address -- one tenant."""

    user_id: UUID
    workspace_id: UUID
    workspace_public_id: UUID
    portfolio_id: int
    portfolio_public_id: UUID


@dataclass(frozen=True)
class MatrixTenants:
    alice: TenantContext
    bob: TenantContext
    session_token: str   # Alice's opaque session cookie value
    csrf_token: str      # Alice's CSRF header value
    ids: dict[str, str]  # matrix_cases placeholder -> UUID string


def _seed_tenant(db: Session, *, label: str, watchlist_name: str, ids: dict[str, str]):
    """Seed one complete tenant: identity, membership, portfolio and one row in
    every workspace-owned domain table the API can address. `watchlist_name` is
    deliberately the SAME string for both tenants so the matrix can prove that
    name uniqueness is per-workspace (cross-tenant duplicate succeeds) while
    still being enforced inside one workspace (409)."""
    from app_settings import set_user_secret
    from auth import create_session
    from models import (
        Benchmark,
        BrokerBalance,
        BrokerConnection,
        BrokerPosition,
        BrokerSyncEvent,
        BrokerSyncRun,
        CashInterestRate,
        DiscordWebhook,
        Membership,
        NotificationOutbox,
        OptionsTrade,
        PolymarketPosition,
        Portfolio,
        PriceAlert,
        TradeNote,
        Transaction,
        User,
        UserSetting,
        UsageCounter,
        UsageReservation,
        Watchlist,
        WatchlistItem,
        Workspace,
        WorkspaceSetting,
    )

    user = User(
        firebase_uid=f"firebase-{label}-matrix-{uuid4().hex}",
        email=f"{label}-matrix-{uuid4().hex}@example.com",
    )
    workspace = Workspace(name=f"{label.title()} matrix workspace")
    db.add_all([user, workspace])
    db.flush()
    db.add(Membership(
        user_id=user.id, workspace_id=workspace.id, role="owner", status="active",
    ))

    portfolio = Portfolio(
        workspace_id=workspace.id, name=f"{label.title()} portfolio", is_default=True,
    )
    db.add(portfolio)
    db.flush()

    trade = Transaction(
        workspace_id=workspace.id, portfolio_id=portfolio.id,
        ticker="AAPL", name="Apple Inc.", type="buy",
        shares=10.0, price=150.0, currency="USD",
        date=date(2024, 1, 15), source="manual",
    )
    cash_row = Transaction(
        workspace_id=workspace.id, portfolio_id=portfolio.id,
        ticker=None, name=None, type="deposit",
        shares=0.0, price=0.0, amount=1000.0, currency="USD",
        date=date(2024, 1, 1), source="manual",
    )
    db.add_all([trade, cash_row])
    db.flush()

    watchlist = Watchlist(workspace_id=workspace.id, name=watchlist_name)
    benchmark = Benchmark(
        workspace_id=workspace.id, portfolio_id=portfolio.id,
        name=f"{label.title()} basket", kind="ticker", ticker="^GSPC",
        is_default=True, is_preset=False,
    )
    t212_connection = BrokerConnection(
        workspace_id=workspace.id, portfolio_id=portfolio.id,
        broker="trading212", api_key=f"{label}-t212-key",
        api_secret=f"{label}-t212-secret", environment="live",
    )
    db.add_all([
        TradeNote(
            workspace_id=workspace.id, transaction_id=trade.id,
            content=f"{label}'s private note",
        ),
        CashInterestRate(
            workspace_id=workspace.id, portfolio_id=portfolio.id,
            currency="USD", annual_rate=0.01, enabled=True,
        ),
        PriceAlert(
            workspace_id=workspace.id, portfolio_id=portfolio.id,
            ticker="AAPL", direction="above", target_price=1000.0,
            enabled=True, status="active",
        ),
        t212_connection,
        BrokerConnection(
            workspace_id=workspace.id, portfolio_id=portfolio.id,
            broker="ibkr", api_key=f"{label}-flex-token",
            api_secret=f"{label}-query-id",
        ),
        BrokerConnection(
            workspace_id=workspace.id, portfolio_id=portfolio.id,
            broker="polymarket", api_key=f"0x{label[0] * 40}",
        ),
        BrokerBalance(
            workspace_id=workspace.id, portfolio_id=portfolio.id,
            broker="ibkr", base_currency="USD", cash=100.0, net_liquidation=1000.0,
        ),
        BrokerPosition(
            workspace_id=workspace.id, portfolio_id=portfolio.id,
            broker="trading212", provider_ticker="AAPL_US_EQ", ticker="AAPL",
            quantity=10.0, avg_price=150.0, current_price=175.0,
            as_of=datetime(2026, 9, 4, tzinfo=timezone.utc),
        ),
        OptionsTrade(
            workspace_id=workspace.id, portfolio_id=portfolio.id,
            underlying="AAPL", strike=150.0, expiry=date(2026, 12, 18),
            put_call="C", quantity=1, open_price=5.0, open_date=date(2026, 1, 2),
            pnl=125.0, source="ibkr",
        ),
        PolymarketPosition(
            workspace_id=workspace.id, portfolio_id=portfolio.id,
            condition_id=f"{label}-condition", asset_id=f"{label}-asset",
            market_slug=f"{label}-market", question=f"Is {label} isolated?",
            outcome="Yes", size=10.0, avg_price=0.4, current_price=0.7,
            status="open", pnl=3.0,
        ),
        DiscordWebhook(
            workspace_id=workspace.id, portfolio_id=portfolio.id,
            webhook_url=f"https://discord.com/api/webhooks/{label}/token",
        ),
        UserSetting(user_id=user.id, key="deepseek_model", value="deepseek-chat"),
        WorkspaceSetting(workspace_id=workspace.id, key="broker_sync_mode", value="daily"),
        WorkspaceSetting(
            workspace_id=workspace.id, key="broker_sync_daily_time",
            value="02:00" if label == "alice" else "23:45",
        ),
        watchlist,
        benchmark,
    ])
    db.flush()
    set_user_secret(db, user.id, "deepseek_api_key", f"{label}-secret-key")

    sync_run = BrokerSyncRun(
        workspace_id=workspace.id, portfolio_id=portfolio.id,
        connection_id=t212_connection.id, broker="trading212",
        credential_generation=t212_connection.credential_generation,
        mode="incremental", state="fetching",
        orders_loaded=1,
    )
    db.add(sync_run)
    db.flush()
    db.add(BrokerSyncEvent(
        workspace_id=workspace.id, portfolio_id=portfolio.id,
        run_id=sync_run.id, broker="trading212", stream="orders",
        provider_event_id=f"fill:{label}-1",
        raw_payload={"order": {"id": f"{label}-order-1"}},
    ))

    now = datetime(2026, 9, 4, tzinfo=timezone.utc)
    usage = UsageCounter(
        workspace_id=workspace.id,
        metric="hosted_ai_monthly",
        period_start=now,
        period_end=now + timedelta(days=30),
        used=1,
    )
    db.add(usage)
    db.flush()
    reservation = UsageReservation(
        workspace_id=workspace.id,
        counter_id=usage.id,
        metric="hosted_ai_monthly",
        idempotency_key=f"{label}-request",
        amount=1,
        status="finalized",
        finalized_at=now,
    )
    db.add_all([
        reservation,
        NotificationOutbox(
            workspace_id=workspace.id,
            user_id=user.id,
            kind="account_notice",
            deduplication_key=f"account:{label}:notice",
            payload={},
        ),
    ])
    db.flush()

    item = WatchlistItem(
        workspace_id=workspace.id, watchlist_id=watchlist.id, ticker="MSFT",
    )
    db.add(item)
    db.flush()

    ids.update({
        f"{label}_workspace": str(workspace.public_id),
        f"{label}_portfolio": str(portfolio.public_id),
        f"{label}_transaction": str(trade.public_id),
        f"{label}_cash": str(cash_row.public_id),
        f"{label}_watchlist": str(watchlist.public_id),
        f"{label}_watchlist_item": str(item.public_id),
        f"{label}_benchmark": str(benchmark.public_id),
        f"{label}_alert": str(
            db.query(PriceAlert).filter(PriceAlert.workspace_id == workspace.id).one().public_id
        ),
    })

    issued = create_session(db, user.id) if label == "alice" else None
    context = TenantContext(
        user_id=user.id,
        workspace_id=workspace.id,
        workspace_public_id=workspace.public_id,
        portfolio_id=portfolio.id,
        portfolio_public_id=portfolio.public_id,
    )
    return context, issued


def _clear_matrix_rows(postgres_engine: Engine) -> None:
    """Every tenant table cascades from `workspaces.id` / `users.id`, so
    deleting those two roots removes everything the matrix seeds."""
    from models import User, Workspace

    with Session(postgres_engine) as db:
        db.execute(delete(User))
        db.execute(delete(Workspace))
        db.commit()


@pytest.fixture
def matrix_tenants(postgres_engine: Engine) -> MatrixTenants:
    """Two fully-populated tenants (Alice and Bob) plus Alice's session/CSRF
    tokens and a placeholder -> UUID map for the literal cases in
    tests/postgres/matrix_cases.py."""
    _clear_matrix_rows(postgres_engine)
    ids: dict[str, str] = {}
    with Session(postgres_engine, expire_on_commit=False) as db:
        alice, issued = _seed_tenant(
            db, label="alice", watchlist_name="Shared name", ids=ids,
        )
        bob, _ = _seed_tenant(
            db, label="bob", watchlist_name="Shared name", ids=ids,
        )
        db.commit()

    ids["random"] = str(uuid4())
    tenants = MatrixTenants(
        alice=alice,
        bob=bob,
        session_token=issued.raw_token,
        csrf_token=issued.csrf_token,
        ids=ids,
    )
    try:
        yield tenants
    finally:
        _clear_matrix_rows(postgres_engine)


@pytest.fixture
def alice_context(matrix_tenants: MatrixTenants) -> TenantContext:
    return matrix_tenants.alice


@pytest.fixture
def bob_context(matrix_tenants: MatrixTenants) -> TenantContext:
    return matrix_tenants.bob


def _matrix_app(postgres_engine: Engine) -> FastAPI:
    """The full protected API surface, wired exactly like main.py mounts it
    (same prefixes, same shared RequestContextError handler) but without the
    SPA/static mounts and background pollers."""
    from database import get_db
    from routers import (
        alerts,
        analytics,
        assistant,
        benchmarks,
        broker,
        cash,
        discord,
        ibkr,
        notes,
        options,
        polymarket,
        portfolio,
        portfolios,
        settings,
        watchlists,
    )
    from tenancy import RequestContextError, request_context_error_handler

    app = FastAPI()
    from edition import Edition
    app.state.portfyl_edition = Edition.LOCAL
    app.add_exception_handler(RequestContextError, request_context_error_handler)
    for module in (
        portfolios, portfolio, analytics, benchmarks, cash, notes,
        watchlists, settings, alerts, assistant,
        broker, ibkr, options, polymarket, discord,
    ):
        app.include_router(module.router, prefix="/api")

    def override_get_db():
        with Session(postgres_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    return app


@pytest.fixture
def matrix_client(postgres_engine: Engine, matrix_tenants: MatrixTenants) -> TestClient:
    """Alice's authenticated client over the complete protected API."""
    with TestClient(
        _matrix_app(postgres_engine),
        headers={
            "X-Workspace-ID": str(matrix_tenants.alice.workspace_public_id),
            "X-CSRF-Token": matrix_tenants.csrf_token,
        },
    ) as client:
        client.cookies.set("portfyl_session", matrix_tenants.session_token)
        yield client


@pytest.fixture
def anonymous_matrix_client(postgres_engine: Engine, matrix_tenants: MatrixTenants) -> TestClient:
    """Same app, no session cookie -- proves the 401 half of the contract."""
    with TestClient(_matrix_app(postgres_engine)) as client:
        yield client


@pytest.fixture
def matrix_bob_portfolio(matrix_tenants: MatrixTenants) -> SimpleNamespace:
    return SimpleNamespace(
        id=matrix_tenants.bob.portfolio_id,
        public_id=matrix_tenants.bob.portfolio_public_id,
    )


@pytest.fixture
def matrix_bob_workspace(matrix_tenants: MatrixTenants) -> SimpleNamespace:
    return SimpleNamespace(
        id=matrix_tenants.bob.workspace_id,
        public_id=matrix_tenants.bob.workspace_public_id,
    )
