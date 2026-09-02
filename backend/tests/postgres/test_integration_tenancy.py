"""Task 8 integration tenancy coverage for broker and remaining integrations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from auth import create_session
from database import get_db
from models import (
    BrokerConnection,
    BrokerBalance,
    DiscordWebhook,
    Membership,
    OptionsTrade,
    PolymarketPosition,
    Portfolio,
    Transaction,
    User,
    Workspace,
)
from routers import broker as broker_router
from routers import discord as discord_router
from routers import ibkr as ibkr_router
from routers import options as options_router
from routers import polymarket as polymarket_router
from tenancy import RequestContextError, request_context_error_handler


@dataclass(frozen=True)
class TenantRows:
    alice: User
    alice_workspace: Workspace
    alice_portfolio: Portfolio
    alice_t212: BrokerConnection
    alice_ibkr: BrokerConnection
    alice_balance: BrokerBalance
    alice_option: OptionsTrade
    alice_poly_connection: BrokerConnection
    alice_poly_position: PolymarketPosition
    alice_webhook: DiscordWebhook
    alice_session_token: str
    alice_csrf_token: str
    bob: User
    bob_workspace: Workspace
    bob_portfolio: Portfolio
    bob_t212: BrokerConnection
    bob_ibkr: BrokerConnection
    bob_balance: BrokerBalance
    bob_option: OptionsTrade
    bob_poly_connection: BrokerConnection
    bob_poly_position: PolymarketPosition
    bob_webhook: DiscordWebhook


def _clear_tenant_rows(postgres_engine) -> None:
    with Session(postgres_engine) as db:
        db.execute(delete(User))
        db.execute(delete(Workspace))
        db.commit()


@pytest.fixture
def tenant_rows(postgres_engine) -> TenantRows:
    _clear_tenant_rows(postgres_engine)
    with Session(postgres_engine, expire_on_commit=False) as db:
        alice = User(
            firebase_uid=f"firebase-alice-integrations-{uuid4().hex}",
            email=f"alice-integrations-{uuid4().hex}@example.com",
        )
        bob = User(
            firebase_uid=f"firebase-bob-integrations-{uuid4().hex}",
            email=f"bob-integrations-{uuid4().hex}@example.com",
        )
        alice_workspace = Workspace(name="Alice integrations workspace")
        bob_workspace = Workspace(name="Bob integrations workspace")
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
            workspace_id=alice_workspace.id,
            name="Alice integrations portfolio",
            is_default=True,
        )
        bob_portfolio = Portfolio(
            workspace_id=bob_workspace.id,
            name="Bob integrations portfolio",
            is_default=True,
        )
        db.add_all([alice_portfolio, bob_portfolio])
        db.flush()

        alice_t212 = BrokerConnection(
            workspace_id=alice_workspace.id,
            portfolio_id=alice_portfolio.id,
            broker="trading212",
            api_key="alice-api-key",
            api_secret="alice-api-secret",
            environment="live",
        )
        bob_t212 = BrokerConnection(
            workspace_id=bob_workspace.id,
            portfolio_id=bob_portfolio.id,
            broker="trading212",
            api_key="bob-api-key",
            api_secret="bob-api-secret",
            environment="live",
        )
        db.add_all([alice_t212, bob_t212])
        db.flush()

        alice_ibkr = BrokerConnection(
            workspace_id=alice_workspace.id,
            portfolio_id=alice_portfolio.id,
            broker="ibkr",
            api_key="alice-flex-token",
            api_secret="alice-query-id",
        )
        bob_ibkr = BrokerConnection(
            workspace_id=bob_workspace.id,
            portfolio_id=bob_portfolio.id,
            broker="ibkr",
            api_key="bob-flex-token",
            api_secret="bob-query-id",
        )
        alice_balance = BrokerBalance(
            workspace_id=alice_workspace.id,
            portfolio_id=alice_portfolio.id,
            broker="ibkr",
            base_currency="USD",
            cash=100.0,
            net_liquidation=1000.0,
        )
        bob_balance = BrokerBalance(
            workspace_id=bob_workspace.id,
            portfolio_id=bob_portfolio.id,
            broker="ibkr",
            base_currency="EUR",
            cash=9999.0,
            net_liquidation=99999.0,
        )
        db.add_all([alice_ibkr, bob_ibkr, alice_balance, bob_balance])
        db.flush()

        alice_option = OptionsTrade(
            workspace_id=alice_workspace.id,
            portfolio_id=alice_portfolio.id,
            underlying="AAPL",
            strike=150.0,
            expiry=date(2026, 12, 18),
            put_call="C",
            quantity=1,
            open_price=5.0,
            open_date=date(2026, 1, 2),
            pnl=125.0,
            source="ibkr",
        )
        bob_option = OptionsTrade(
            workspace_id=bob_workspace.id,
            portfolio_id=bob_portfolio.id,
            underlying="MSFT",
            strike=400.0,
            expiry=date(2026, 12, 18),
            put_call="P",
            quantity=1,
            open_price=7.0,
            open_date=date(2026, 1, 3),
            pnl=-50.0,
            source="ibkr",
        )
        db.add_all([alice_option, bob_option])
        db.flush()

        alice_poly_connection = BrokerConnection(
            workspace_id=alice_workspace.id,
            portfolio_id=alice_portfolio.id,
            broker="polymarket",
            api_key="0x1111111111111111111111111111111111111111",
        )
        bob_poly_connection = BrokerConnection(
            workspace_id=bob_workspace.id,
            portfolio_id=bob_portfolio.id,
            broker="polymarket",
            api_key="0x2222222222222222222222222222222222222222",
        )
        alice_poly_position = PolymarketPosition(
            workspace_id=alice_workspace.id,
            portfolio_id=alice_portfolio.id,
            condition_id="alice-condition",
            asset_id="alice-asset",
            market_slug="alice-market",
            question="Will Alice remain isolated?",
            outcome="Yes",
            size=10.0,
            avg_price=0.4,
            current_price=0.7,
            status="open",
            pnl=3.0,
        )
        bob_poly_position = PolymarketPosition(
            workspace_id=bob_workspace.id,
            portfolio_id=bob_portfolio.id,
            condition_id="bob-condition",
            asset_id="bob-asset",
            market_slug="bob-market",
            question="Can Bob leak?",
            outcome="No",
            size=20.0,
            avg_price=0.5,
            current_price=0.2,
            status="open",
            pnl=-6.0,
        )
        db.add_all([
            alice_poly_connection,
            bob_poly_connection,
            alice_poly_position,
            bob_poly_position,
        ])
        db.flush()

        alice_webhook = DiscordWebhook(
            workspace_id=alice_workspace.id,
            portfolio_id=alice_portfolio.id,
            webhook_url="https://discord.com/api/webhooks/alice/token",
        )
        bob_webhook = DiscordWebhook(
            workspace_id=bob_workspace.id,
            portfolio_id=bob_portfolio.id,
            webhook_url="https://discord.com/api/webhooks/bob/token",
        )
        db.add_all([alice_webhook, bob_webhook])
        db.flush()

        issued = create_session(db, alice.id)
        db.commit()
        rows = TenantRows(
            alice=alice,
            alice_workspace=alice_workspace,
            alice_portfolio=alice_portfolio,
            alice_t212=alice_t212,
            alice_ibkr=alice_ibkr,
            alice_balance=alice_balance,
            alice_option=alice_option,
            alice_poly_connection=alice_poly_connection,
            alice_poly_position=alice_poly_position,
            alice_webhook=alice_webhook,
            alice_session_token=issued.raw_token,
            alice_csrf_token=issued.csrf_token,
            bob=bob,
            bob_workspace=bob_workspace,
            bob_portfolio=bob_portfolio,
            bob_t212=bob_t212,
            bob_ibkr=bob_ibkr,
            bob_balance=bob_balance,
            bob_option=bob_option,
            bob_poly_connection=bob_poly_connection,
            bob_poly_position=bob_poly_position,
            bob_webhook=bob_webhook,
        )

    try:
        yield rows
    finally:
        _clear_tenant_rows(postgres_engine)


@pytest.fixture
def alice_client(postgres_engine, tenant_rows: TenantRows) -> TestClient:
    app = FastAPI()
    app.add_exception_handler(RequestContextError, request_context_error_handler)
    app.include_router(broker_router.router, prefix="/api")
    app.include_router(discord_router.router, prefix="/api")
    app.include_router(ibkr_router.router, prefix="/api")
    app.include_router(options_router.router, prefix="/api")
    app.include_router(polymarket_router.router, prefix="/api")

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


def test_broker_status_uses_authorized_portfolio_and_public_connection_id(
    alice_client: TestClient,
    tenant_rows: TenantRows,
):
    response = alice_client.get(
        "/api/broker/trading212/status",
        params={"portfolio_id": str(tenant_rows.alice_portfolio.public_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["id"] == str(tenant_rows.alice_t212.public_id)
    assert body["portfolio_id"] == str(tenant_rows.alice_portfolio.public_id)
    assert body["id"] != str(tenant_rows.bob_t212.public_id)


def test_options_list_is_workspace_scoped_and_uses_public_ids(
    alice_client: TestClient,
    tenant_rows: TenantRows,
):
    response = alice_client.get(
        "/api/options/trades",
        params={"portfolio_id": str(tenant_rows.alice_portfolio.public_id)},
    )

    assert response.status_code == 200
    assert response.json() == [{
        "id": str(tenant_rows.alice_option.public_id),
        "portfolio_id": str(tenant_rows.alice_portfolio.public_id),
        "underlying": "AAPL",
        "strike": 150.0,
        "expiry": "2026-12-18",
        "put_call": "C",
        "quantity": 1,
        "open_price": 5.0,
        "close_price": None,
        "open_date": "2026-01-02",
        "close_date": None,
        "status": "closed",
        "multiplier": 100,
        "currency": "USD",
        "pnl": 125.0,
        "commission": 0.0,
        "source": "ibkr",
        "fx_to_czk": None,
        "notes": None,
        "created_at": tenant_rows.alice_option.created_at.isoformat(),
    }]


def test_options_aggregates_use_only_the_authorized_portfolio(
    alice_client: TestClient,
    tenant_rows: TenantRows,
):
    params = {"portfolio_id": str(tenant_rows.alice_portfolio.public_id)}

    summary = alice_client.get("/api/options/summary", params=params)
    by_underlying = alice_client.get("/api/options/by-underlying", params=params)
    calendar = alice_client.get("/api/options/calendar", params=params)

    assert summary.status_code == 200
    assert summary.json()["total_trades"] == 1
    assert summary.json()["total_pnl"] == 125.0
    assert by_underlying.status_code == 200
    assert [row["underlying"] for row in by_underlying.json()] == ["AAPL"]
    assert by_underlying.json()[0]["trades"][0]["id"] == str(
        tenant_rows.alice_option.public_id
    )
    assert calendar.status_code == 200
    assert calendar.json() == []


def test_polymarket_reads_are_workspace_scoped_and_use_public_ids(
    alice_client: TestClient,
    tenant_rows: TenantRows,
):
    params = {"portfolio_id": str(tenant_rows.alice_portfolio.public_id)}

    status = alice_client.get("/api/broker/polymarket/status", params=params)
    positions = alice_client.get("/api/polymarket/positions", params=params)
    summary = alice_client.get("/api/polymarket/summary", params=params)

    assert status.status_code == 200
    assert status.json()["id"] == str(tenant_rows.alice_poly_connection.public_id)
    assert status.json()["portfolio_id"] == str(tenant_rows.alice_portfolio.public_id)
    assert positions.status_code == 200
    assert [row["id"] for row in positions.json()["positions"]] == [
        str(tenant_rows.alice_poly_position.public_id)
    ]
    assert positions.json()["positions"][0]["portfolio_id"] == str(
        tenant_rows.alice_portfolio.public_id
    )
    assert summary.status_code == 200
    assert summary.json()["total_pnl"] == 3.0


def test_discord_webhook_read_is_workspace_scoped_and_uses_public_id(
    alice_client: TestClient,
    tenant_rows: TenantRows,
):
    response = alice_client.get(
        "/api/discord/webhook",
        params={"portfolio_id": str(tenant_rows.alice_portfolio.public_id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["id"] == str(tenant_rows.alice_webhook.public_id)
    assert body["portfolio_id"] == str(tenant_rows.alice_portfolio.public_id)
    assert body["id"] != str(tenant_rows.bob_webhook.public_id)


def test_ibkr_status_and_balance_are_workspace_scoped_and_use_public_ids(
    alice_client: TestClient,
    tenant_rows: TenantRows,
):
    params = {"portfolio_id": str(tenant_rows.alice_portfolio.public_id)}

    status = alice_client.get("/api/broker/ibkr/status", params=params)
    balance = alice_client.get("/api/broker/ibkr/balance", params=params)

    assert status.status_code == 200
    assert status.json()["id"] == str(tenant_rows.alice_ibkr.public_id)
    assert status.json()["portfolio_id"] == str(tenant_rows.alice_portfolio.public_id)
    assert balance.status_code == 200
    assert balance.json()["balance"]["id"] == str(tenant_rows.alice_balance.public_id)
    assert balance.json()["balance"]["portfolio_id"] == str(
        tenant_rows.alice_portfolio.public_id
    )
    assert balance.json()["balance"]["cash"] == 100.0


def test_t212_sync_stamps_the_authorized_workspace_and_portfolio(
    alice_client: TestClient,
    tenant_rows: TenantRows,
    postgres_engine,
    monkeypatch,
):
    monkeypatch.setattr(broker_router, "_fetch_all_orders", lambda *_: [{
        "order": {
            "id": "alice-order",
            "status": "FILLED",
            "ticker": "AAPL",
            "side": "BUY",
            "filledQuantity": 2,
            "createdAt": "2026-02-01T10:00:00Z",
            "instrument": {"currency": "USD", "name": "Apple Inc."},
        },
        "fill": {
            "quantity": 2,
            "price": 100,
            "filledAt": "2026-02-01T10:00:00Z",
        },
    }])
    monkeypatch.setattr(broker_router, "_fetch_all_dividends", lambda *_: [])
    monkeypatch.setattr(broker_router, "_split_adjust", lambda *_: 0)
    monkeypatch.setattr(broker_router, "_drop_corporate_action_pairs", lambda *_: 0)
    monkeypatch.setattr(
        broker_router,
        "bulk_fetch_fx",
        lambda *_: {("USD", date(2026, 2, 1)): 20.0},
    )

    response = alice_client.post(
        "/api/broker/trading212/sync",
        params={"portfolio_id": str(tenant_rows.alice_portfolio.public_id)},
    )

    assert response.status_code == 200
    assert response.json()["imported_orders"] == 1
    with Session(postgres_engine) as db:
        row = db.query(Transaction).one()
        assert row.workspace_id == tenant_rows.alice_workspace.id
        assert row.portfolio_id == tenant_rows.alice_portfolio.id


def test_ibkr_sync_stamps_workspace_without_matching_bob_rows(
    alice_client: TestClient,
    tenant_rows: TenantRows,
    postgres_engine,
    monkeypatch,
):
    monkeypatch.setattr(ibkr_router, "_send_flex_request", AsyncMock(return_value="ref"))
    monkeypatch.setattr(ibkr_router, "_poll_flex_statement", AsyncMock(return_value="<xml/>"))
    monkeypatch.setattr(ibkr_router, "_parse_options_trades", lambda *_: [])
    monkeypatch.setattr(ibkr_router, "_parse_balance", lambda *_: None)
    monkeypatch.setattr(ibkr_router, "_pair_trades", lambda *_: [{
        "underlying": "NVDA",
        "strike": 200.0,
        "expiry": date(2027, 1, 15),
        "put_call": "C",
        "quantity": 1,
        "open_price": 10.0,
        "close_price": 12.0,
        "open_date": date(2026, 3, 1),
        "close_date": date(2026, 3, 2),
        "status": "closed",
        "multiplier": 100,
        "currency": "USD",
        "pnl": 200.0,
        "commission": 0.0,
    }])

    response = alice_client.post(
        "/api/broker/ibkr/sync",
        params={"portfolio_id": str(tenant_rows.alice_portfolio.public_id)},
    )

    assert response.status_code == 200
    assert response.json()["imported"] == 1
    with Session(postgres_engine) as db:
        imported = db.query(OptionsTrade).filter(OptionsTrade.underlying == "NVDA").one()
        assert imported.workspace_id == tenant_rows.alice_workspace.id
        assert imported.portfolio_id == tenant_rows.alice_portfolio.id
        bob = db.get(OptionsTrade, tenant_rows.bob_option.id)
        assert bob is not None
        assert bob.pnl == -50.0


def test_polymarket_sync_replaces_only_the_authorized_workspace(
    alice_client: TestClient,
    tenant_rows: TenantRows,
    postgres_engine,
    monkeypatch,
):
    class Response:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

        def raise_for_status(self):
            return None

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, url, **_kwargs):
            if url.endswith("/trades"):
                return Response([{
                    "conditionId": "alice-new-condition",
                    "asset": "alice-new-asset",
                    "outcome": "Yes",
                    "slug": "alice-new-market",
                    "title": "New Alice market",
                    "side": "BUY",
                    "size": 5,
                    "price": 0.4,
                }])
            return Response([{
                "conditionId": "alice-new-condition",
                "outcome": "Yes",
                "curPrice": 0.6,
            }])

    monkeypatch.setattr(polymarket_router.httpx, "AsyncClient", lambda **_kwargs: Client())

    response = alice_client.post(
        "/api/broker/polymarket/sync",
        params={"portfolio_id": str(tenant_rows.alice_portfolio.public_id)},
    )

    assert response.status_code == 200
    assert response.json()["imported"] == 1
    with Session(postgres_engine) as db:
        alice_rows = db.query(PolymarketPosition).filter(
            PolymarketPosition.workspace_id == tenant_rows.alice_workspace.id
        ).all()
        assert [row.condition_id for row in alice_rows] == ["alice-new-condition"]
        assert alice_rows[0].portfolio_id == tenant_rows.alice_portfolio.id
        bob = db.get(PolymarketPosition, tenant_rows.bob_poly_position.id)
        assert bob is not None
        assert bob.condition_id == "bob-condition"
