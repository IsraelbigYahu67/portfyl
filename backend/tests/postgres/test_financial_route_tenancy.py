"""Cross-tenant isolation for the Task 6 financial routes: transactions, trade
notes, custom benchmarks, cash rows, and analytics benchmark selection.

Mirrors the app-construction pattern established in test_portfolio_tenancy.py
(a minimal FastAPI app wired with only the routers under test, the shared
RequestContextError handler, and a `get_db` override onto the disposable
Postgres database), but exercises the routers Task 6 touched directly:
routers.portfolio, routers.analytics, routers.benchmarks, routers.cash and
routers.notes.

Every test asserts on Bob's PUBLIC UUIDs reached through Alice's authenticated
client -- the same 404 contract a wholly nonexistent UUID would produce (see
the Global Constraint in the task brief), never on Bob's internal integer
primary keys, which the API must never accept or expose in the first place.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from unittest.mock import patch
from uuid import UUID

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from auth import create_session
from database import get_db
from models import (
    Benchmark,
    Membership,
    Portfolio,
    TradeNote,
    Transaction,
    User,
    Workspace,
)
from routers import analytics as analytics_router
from routers import benchmarks as benchmarks_router
from routers import cash as cash_router
from routers import notes as notes_router
from routers import portfolio as portfolio_router
from routers import portfolios as portfolios_router
from tenancy import RequestContextError, request_context_error_handler


@dataclass(frozen=True)
class TenantRows:
    alice: User
    alice_workspace: Workspace
    alice_portfolio: Portfolio
    alice_session_token: str
    alice_csrf_token: str
    alice_transaction: Transaction
    alice_benchmark: Benchmark
    bob: User
    bob_workspace: Workspace
    bob_portfolio: Portfolio
    bob_transaction: Transaction
    bob_note: TradeNote
    bob_benchmark: Benchmark
    bob_cash_row: Transaction


def _clear_tenant_rows(postgres_engine) -> None:
    with Session(postgres_engine) as db:
        db.execute(delete(User))
        db.execute(delete(Workspace))
        db.commit()


@pytest.fixture
def tenant_rows(postgres_engine) -> TenantRows:
    _clear_tenant_rows(postgres_engine)
    with Session(postgres_engine, expire_on_commit=False) as db:
        alice = User(firebase_uid="firebase-alice-fin", email="alice-fin@example.com")
        bob = User(firebase_uid="firebase-bob-fin", email="bob-fin@example.com")
        alice_workspace = Workspace(name="Alice workspace")
        bob_workspace = Workspace(name="Bob workspace")
        db.add_all([alice, bob, alice_workspace, bob_workspace])
        db.flush()

        db.add_all([
            Membership(
                user_id=alice.id,
                workspace_id=alice_workspace.id,
                role="owner",
                status="active",
            ),
            Membership(
                user_id=bob.id,
                workspace_id=bob_workspace.id,
                role="owner",
                status="active",
            ),
        ])
        alice_portfolio = Portfolio(
            workspace_id=alice_workspace.id, name="Alice portfolio", is_default=True,
        )
        bob_portfolio = Portfolio(
            workspace_id=bob_workspace.id, name="Bob portfolio", is_default=True,
        )
        db.add_all([alice_portfolio, bob_portfolio])
        db.flush()

        alice_transaction = Transaction(
            workspace_id=alice_workspace.id,
            portfolio_id=alice_portfolio.id,
            ticker="AAPL", name="Apple Inc.", type="buy",
            shares=10, price=150.0, currency="USD",
            date=date(2024, 1, 15), source="manual",
        )
        bob_transaction = Transaction(
            workspace_id=bob_workspace.id,
            portfolio_id=bob_portfolio.id,
            ticker="MSFT", name="Microsoft Corp.", type="buy",
            shares=5, price=300.0, currency="USD",
            date=date(2024, 2, 1), source="manual",
        )
        bob_cash_row = Transaction(
            workspace_id=bob_workspace.id,
            portfolio_id=bob_portfolio.id,
            ticker=None, name=None, type="deposit",
            shares=0.0, price=0.0, amount=1000.0, currency="USD",
            date=date(2024, 1, 1), source="manual",
        )
        db.add_all([alice_transaction, bob_transaction, bob_cash_row])
        db.flush()

        bob_note = TradeNote(
            workspace_id=bob_workspace.id,
            transaction_id=bob_transaction.id,
            content="Bob's private note", tags=None, sentiment=None,
        )
        alice_benchmark = Benchmark(
            workspace_id=alice_workspace.id, portfolio_id=alice_portfolio.id,
            name="Alice basket", kind="ticker", ticker="^GSPC",
            is_default=True, is_preset=False,
        )
        bob_benchmark = Benchmark(
            workspace_id=bob_workspace.id, portfolio_id=bob_portfolio.id,
            name="Bob basket", kind="ticker", ticker="^NDX",
            is_default=False, is_preset=False,
        )
        db.add_all([bob_note, alice_benchmark, bob_benchmark])
        db.flush()

        issued = create_session(db, alice.id)
        db.commit()

        rows = TenantRows(
            alice=alice,
            alice_workspace=alice_workspace,
            alice_portfolio=alice_portfolio,
            alice_session_token=issued.raw_token,
            alice_csrf_token=issued.csrf_token,
            alice_transaction=alice_transaction,
            alice_benchmark=alice_benchmark,
            bob=bob,
            bob_workspace=bob_workspace,
            bob_portfolio=bob_portfolio,
            bob_transaction=bob_transaction,
            bob_note=bob_note,
            bob_benchmark=bob_benchmark,
            bob_cash_row=bob_cash_row,
        )

    try:
        yield rows
    finally:
        _clear_tenant_rows(postgres_engine)


@pytest.fixture
def alice_client(postgres_engine, tenant_rows: TenantRows) -> TestClient:
    app = FastAPI()
    app.add_exception_handler(RequestContextError, request_context_error_handler)
    app.include_router(portfolios_router.router, prefix="/api")
    app.include_router(portfolio_router.router, prefix="/api")
    app.include_router(analytics_router.router, prefix="/api")
    app.include_router(benchmarks_router.router, prefix="/api")
    app.include_router(cash_router.router, prefix="/api")
    app.include_router(notes_router.router, prefix="/api")

    def override_get_db():
        with Session(postgres_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(
        app,
        headers={
            "X-Workspace-ID": str(tenant_rows.alice_workspace.public_id),
            "X-CSRF-Token": tenant_rows.alice_csrf_token,
        },
    ) as client:
        client.cookies.set("portfyl_session", tenant_rows.alice_session_token)
        yield client


def _alice_portfolio_param(tenant_rows: TenantRows) -> dict:
    return {"portfolio_id": str(tenant_rows.alice_portfolio.public_id)}


# ---------------------------------------------------------------------------
# Transaction read/update/delete
# ---------------------------------------------------------------------------


def test_foreign_transaction_uuid_is_not_addressable(
    alice_client: TestClient, tenant_rows: TenantRows,
):
    response = alice_client.delete(
        f"/api/portfolio/transactions/{tenant_rows.bob_transaction.public_id}",
        params=_alice_portfolio_param(tenant_rows),
    )
    assert response.status_code == 404


def test_transaction_list_never_includes_other_workspace_and_uses_public_uuids(
    alice_client: TestClient, tenant_rows: TenantRows,
):
    response = alice_client.get(
        "/api/portfolio/transactions", params=_alice_portfolio_param(tenant_rows),
    )

    assert response.status_code == 200
    body = response.json()
    ids = [row["id"] for row in body]
    assert ids == [str(tenant_rows.alice_transaction.public_id)]
    # Every id must be a real UUID string, never Bob's or Alice's raw integer PK.
    UUID(ids[0])
    assert str(tenant_rows.bob_transaction.public_id) not in ids


def test_own_transaction_delete_succeeds(
    alice_client: TestClient, tenant_rows: TenantRows,
):
    response = alice_client.delete(
        f"/api/portfolio/transactions/{tenant_rows.alice_transaction.public_id}",
        params=_alice_portfolio_param(tenant_rows),
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


# ---------------------------------------------------------------------------
# Note read/update/delete
# ---------------------------------------------------------------------------


def test_foreign_note_read_is_not_addressable(
    alice_client: TestClient, tenant_rows: TenantRows,
):
    response = alice_client.get(
        f"/api/notes/transaction/{tenant_rows.bob_transaction.public_id}",
        params=_alice_portfolio_param(tenant_rows),
    )
    assert response.status_code == 404


def test_foreign_note_update_is_not_addressable(
    alice_client: TestClient, tenant_rows: TenantRows,
):
    response = alice_client.put(
        f"/api/notes/transaction/{tenant_rows.bob_transaction.public_id}",
        params=_alice_portfolio_param(tenant_rows),
        json={"content": "stolen"},
    )
    assert response.status_code == 404


def test_foreign_note_delete_is_not_addressable(
    alice_client: TestClient, tenant_rows: TenantRows,
):
    response = alice_client.delete(
        f"/api/notes/transaction/{tenant_rows.bob_transaction.public_id}",
        params=_alice_portfolio_param(tenant_rows),
    )
    assert response.status_code == 404


def test_own_note_roundtrip_uses_public_uuid(
    alice_client: TestClient, tenant_rows: TenantRows,
):
    write = alice_client.put(
        f"/api/notes/transaction/{tenant_rows.alice_transaction.public_id}",
        params=_alice_portfolio_param(tenant_rows),
        json={"content": "own note", "sentiment": "bullish"},
    )
    assert write.status_code == 200
    assert write.json()["transaction_id"] == str(tenant_rows.alice_transaction.public_id)

    read = alice_client.get(
        f"/api/notes/transaction/{tenant_rows.alice_transaction.public_id}",
        params=_alice_portfolio_param(tenant_rows),
    )
    assert read.status_code == 200
    assert read.json()["content"] == "own note"


# ---------------------------------------------------------------------------
# Custom benchmark selection/update/delete
# ---------------------------------------------------------------------------


def test_foreign_benchmark_update_is_not_addressable(
    alice_client: TestClient, tenant_rows: TenantRows,
):
    response = alice_client.patch(
        f"/api/analytics/benchmarks/{tenant_rows.bob_benchmark.public_id}",
        params=_alice_portfolio_param(tenant_rows),
        json={"is_default": True},
    )
    assert response.status_code == 404


def test_foreign_benchmark_delete_is_not_addressable(
    alice_client: TestClient, tenant_rows: TenantRows,
):
    response = alice_client.delete(
        f"/api/analytics/benchmarks/{tenant_rows.bob_benchmark.public_id}",
        params=_alice_portfolio_param(tenant_rows),
    )
    assert response.status_code == 404


def test_own_benchmark_update_succeeds_and_list_excludes_other_workspace(
    alice_client: TestClient, tenant_rows: TenantRows,
):
    update = alice_client.patch(
        f"/api/analytics/benchmarks/{tenant_rows.alice_benchmark.public_id}",
        params=_alice_portfolio_param(tenant_rows),
        json={"name": "Renamed"},
    )
    assert update.status_code == 200
    assert update.json()["name"] == "Renamed"

    listing = alice_client.get(
        "/api/analytics/benchmarks", params=_alice_portfolio_param(tenant_rows),
    )
    assert listing.status_code == 200
    ids = [row["id"] for row in listing.json()]
    assert str(tenant_rows.alice_benchmark.public_id) in ids
    assert str(tenant_rows.bob_benchmark.public_id) not in ids


# ---------------------------------------------------------------------------
# Cash mutation
# ---------------------------------------------------------------------------


def test_foreign_cash_row_update_is_not_addressable(
    alice_client: TestClient, tenant_rows: TenantRows,
):
    response = alice_client.put(
        f"/api/cash/{tenant_rows.bob_cash_row.public_id}",
        params=_alice_portfolio_param(tenant_rows),
        json={"type": "deposit", "amount": 1, "currency": "USD", "date": "2024-01-01"},
    )
    assert response.status_code == 404


def test_foreign_cash_row_delete_is_not_addressable(
    alice_client: TestClient, tenant_rows: TenantRows,
):
    response = alice_client.delete(
        f"/api/cash/{tenant_rows.bob_cash_row.public_id}",
        params=_alice_portfolio_param(tenant_rows),
    )
    assert response.status_code == 404


def test_own_cash_row_mutation_uses_public_uuid(
    alice_client: TestClient, tenant_rows: TenantRows,
):
    created = alice_client.post(
        "/api/cash", params=_alice_portfolio_param(tenant_rows),
        json={"type": "deposit", "amount": 500, "currency": "USD", "date": "2024-01-01"},
    )
    assert created.status_code == 200
    cash_id = created.json()["id"]
    UUID(cash_id)  # public UUID, not the row's raw integer PK

    updated = alice_client.put(
        f"/api/cash/{cash_id}",
        params=_alice_portfolio_param(tenant_rows),
        json={"type": "deposit", "amount": 750, "currency": "USD", "date": "2024-01-02"},
    )
    assert updated.status_code == 200
    assert updated.json()["amount"] == 750


# ---------------------------------------------------------------------------
# Analytics benchmark selection
# ---------------------------------------------------------------------------
# A benchmark_id filter is not a resource path -- an id that doesn't resolve
# inside Alice's own tenant (own workspace+portfolio, or a shared preset) must
# be treated exactly like a wholly nonexistent id: silently ignored, falling
# through to the portfolio-default/preset resolution. It must NEVER surface
# Bob's benchmark.


def test_risk_metrics_ignores_foreign_benchmark_id(
    alice_client: TestClient, tenant_rows: TenantRows,
):
    response = alice_client.get(
        "/api/analytics/risk-metrics",
        params={
            **_alice_portfolio_param(tenant_rows),
            "benchmark_id": str(tenant_rows.bob_benchmark.public_id),
        },
    )

    assert response.status_code == 200
    body = response.json()
    if body.get("benchmark") is not None:
        assert body["benchmark"]["id"] != str(tenant_rows.bob_benchmark.public_id)


def test_benchmark_comparison_ignores_foreign_benchmark_id(
    alice_client: TestClient, tenant_rows: TenantRows,
):
    response = alice_client.get(
        "/api/analytics/benchmarks/comparison",
        params={
            **_alice_portfolio_param(tenant_rows),
            "benchmark_id": str(tenant_rows.bob_benchmark.public_id),
        },
    )

    assert response.status_code == 200
    body = response.json()
    if body.get("benchmark") is not None:
        assert body["benchmark"]["id"] != str(tenant_rows.bob_benchmark.public_id)


# ---------------------------------------------------------------------------
# Cross-portfolio overview
# ---------------------------------------------------------------------------


def test_overview_financial_totals_exclude_other_workspace(
    alice_client: TestClient, tenant_rows: TenantRows,
):
    # Alice holds a real "buy" trade (AAPL), so /overview's get_summary walks
    # the same holdings/day-change/FX code paths a live request would --
    # stub every yfinance-backed lookup so the assertion is deterministic and
    # this integration test never touches the network, matching how every
    # other test in this suite mocks market_data.
    with (
        patch("market_data.get_infos", return_value={
            "AAPL": {"currentPrice": 150.0, "regularMarketPrice": 150.0,
                     "currency": "USD", "sector": "Technology", "quoteType": "EQUITY"},
        }),
        patch("routers.portfolio._fetch_price_and_info", return_value=(150.0, "Apple Inc.", "USD")),
        patch("routers.portfolio._live_fx_to_czk", return_value=20.0),
        patch("routers.portfolio.yf.download", return_value=pd.DataFrame()),
    ):
        response = alice_client.get("/api/portfolios/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["portfolio_count"] == 1
    # Alice's AAPL position (10 sh @ $150 cost == $150 live price -> $0 P&L,
    # $1500 net worth) must be the total -- Bob's $1000 cash deposit, sitting
    # in the very same `transactions` table, must never be folded in.
    assert body["total_net_worth"] == pytest.approx(1500.0)
