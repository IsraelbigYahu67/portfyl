"""Cross-tenant isolation for Task 7: user/workspace-scoped settings, plus the
watchlist and price-alert routes.

Mirrors the app-construction pattern established in
test_financial_route_tenancy.py (a minimal FastAPI app wired with only the
routers under test, the shared RequestContextError handler, and a `get_db`
override onto the disposable Postgres database).

Every route test asserts on Bob's PUBLIC UUIDs reached through Alice's
authenticated client -- the same 404 a wholly nonexistent UUID would produce
-- never on Bob's internal integer primary keys, which the API must never
accept or expose in the first place.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.orm import Session

from auth import create_session
from database import get_db
from edition import Edition
from app_settings import (
    get_user_setting, set_user_setting,
    get_workspace_setting, set_workspace_setting,
)
from models import Membership, Portfolio, PriceAlert, User, Watchlist, Workspace
from routers import alerts as alerts_router
from routers import watchlists as watchlists_router
from tenancy import RequestContextError, request_context_error_handler


# ---------------------------------------------------------------------------
# Shared user/workspace fixtures (used directly by the settings tests, and as
# building blocks for the route-matrix fixtures below).
# ---------------------------------------------------------------------------


def _clear_tenant_rows(postgres_engine) -> None:
    with Session(postgres_engine) as db:
        db.execute(delete(User))
        db.execute(delete(Workspace))
        db.commit()


@pytest.fixture
def alice(postgres_session: Session) -> User:
    user = User(firebase_uid=f"firebase-alice-{uuid4().hex}", email=f"alice-{uuid4().hex}@example.com")
    postgres_session.add(user)
    postgres_session.flush()
    return user


@pytest.fixture
def bob(postgres_session: Session) -> User:
    user = User(firebase_uid=f"firebase-bob-{uuid4().hex}", email=f"bob-{uuid4().hex}@example.com")
    postgres_session.add(user)
    postgres_session.flush()
    return user


@pytest.fixture
def alice_workspace(postgres_session: Session, alice: User) -> Workspace:
    workspace = Workspace(name="Alice workspace")
    postgres_session.add(workspace)
    postgres_session.flush()
    postgres_session.add(Membership(user_id=alice.id, workspace_id=workspace.id, role="owner", status="active"))
    postgres_session.flush()
    return workspace


@pytest.fixture
def bob_workspace(postgres_session: Session, bob: User) -> Workspace:
    workspace = Workspace(name="Bob workspace")
    postgres_session.add(workspace)
    postgres_session.flush()
    postgres_session.add(Membership(user_id=bob.id, workspace_id=workspace.id, role="owner", status="active"))
    postgres_session.flush()
    return workspace


# ---------------------------------------------------------------------------
# Step 1: scoped-setting isolation (function level, no HTTP).
# ---------------------------------------------------------------------------


def test_same_setting_key_has_independent_user_values(postgres_session, alice, bob):
    set_user_setting(postgres_session, alice.id, "deepseek_model", "a")
    set_user_setting(postgres_session, bob.id, "deepseek_model", "b")
    assert get_user_setting(postgres_session, alice.id, "deepseek_model") == "a"
    assert get_user_setting(postgres_session, bob.id, "deepseek_model") == "b"


def test_same_sync_key_has_independent_workspace_values(postgres_session, alice_workspace, bob_workspace):
    set_workspace_setting(postgres_session, alice_workspace.id, "sync_mode", "daily")
    set_workspace_setting(postgres_session, bob_workspace.id, "sync_mode", "weekly")
    assert get_workspace_setting(postgres_session, alice_workspace.id, "sync_mode") == "daily"
    assert get_workspace_setting(postgres_session, bob_workspace.id, "sync_mode") == "weekly"


def test_missing_user_setting_is_none_not_another_users_value(postgres_session, alice, bob):
    set_user_setting(postgres_session, bob.id, "deepseek_api_key", "bob-secret")
    assert get_user_setting(postgres_session, alice.id, "deepseek_api_key") is None


def test_missing_workspace_setting_is_none_not_another_workspaces_value(postgres_session, alice_workspace, bob_workspace):
    set_workspace_setting(postgres_session, bob_workspace.id, "broker_sync_daily_time", "03:00")
    assert get_workspace_setting(postgres_session, alice_workspace.id, "broker_sync_daily_time") is None


# ---------------------------------------------------------------------------
# Route matrix: watchlists + alerts.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TenantRows:
    alice: User
    alice_workspace: Workspace
    alice_portfolio: Portfolio
    alice_session_token: str
    alice_watchlist: Watchlist
    alice_alert: PriceAlert
    bob: User
    bob_workspace: Workspace
    bob_portfolio: Portfolio
    bob_watchlist: Watchlist
    bob_alert: PriceAlert


@pytest.fixture
def tenant_rows(postgres_engine) -> TenantRows:
    # A route-matrix fixture needs its rows actually committed (the test
    # client's own request-scoped sessions must see them), unlike
    # `postgres_session` above which is rolled back per test -- so this
    # builds its own independent Alice/Bob rows via a raw engine session
    # rather than reusing the `alice`/`bob`/`alice_workspace`/`bob_workspace`
    # fixtures, and cleans up explicitly (see _clear_tenant_rows) instead of
    # relying on a rolled-back transaction.
    _clear_tenant_rows(postgres_engine)
    with Session(postgres_engine, expire_on_commit=False) as db:
        alice = User(firebase_uid=f"firebase-alice-wsa-{uuid4().hex}", email=f"alice-wsa-{uuid4().hex}@example.com")
        bob = User(firebase_uid=f"firebase-bob-wsa-{uuid4().hex}", email=f"bob-wsa-{uuid4().hex}@example.com")
        alice_workspace = Workspace(name="Alice workspace")
        bob_workspace = Workspace(name="Bob workspace")
        db.add_all([alice, bob, alice_workspace, bob_workspace])
        db.flush()

        db.add_all([
            Membership(user_id=alice.id, workspace_id=alice_workspace.id, role="owner", status="active"),
            Membership(user_id=bob.id, workspace_id=bob_workspace.id, role="owner", status="active"),
        ])

        alice_portfolio = Portfolio(workspace_id=alice_workspace.id, name="Alice portfolio", is_default=True)
        bob_portfolio = Portfolio(workspace_id=bob_workspace.id, name="Bob portfolio", is_default=True)
        db.add_all([alice_portfolio, bob_portfolio])
        db.flush()

        alice_watchlist = Watchlist(workspace_id=alice_workspace.id, name="Growth", color="#111111")
        bob_watchlist = Watchlist(workspace_id=bob_workspace.id, name="Tech", color="#222222")
        db.add_all([alice_watchlist, bob_watchlist])
        db.flush()

        alice_alert = PriceAlert(
            workspace_id=alice_workspace.id, portfolio_id=alice_portfolio.id,
            ticker="AAPL", direction="above", target_price=200.0,
            enabled=True, status="active",
        )
        bob_alert = PriceAlert(
            workspace_id=bob_workspace.id, portfolio_id=bob_portfolio.id,
            ticker="MSFT", direction="below", target_price=100.0,
            enabled=True, status="active",
        )
        db.add_all([alice_alert, bob_alert])
        db.flush()

        issued = create_session(db, alice.id)
        db.commit()

        rows = TenantRows(
            alice=alice, alice_workspace=alice_workspace, alice_portfolio=alice_portfolio,
            alice_session_token=issued.raw_token,
            alice_watchlist=alice_watchlist, alice_alert=alice_alert,
            bob=bob, bob_workspace=bob_workspace, bob_portfolio=bob_portfolio,
            bob_watchlist=bob_watchlist, bob_alert=bob_alert,
        )

    try:
        yield rows
    finally:
        _clear_tenant_rows(postgres_engine)


@pytest.fixture
def alice_client(postgres_engine, tenant_rows: TenantRows) -> TestClient:
    app = FastAPI()
    app.state.portfyl_edition = Edition.LOCAL
    app.add_exception_handler(RequestContextError, request_context_error_handler)
    app.include_router(watchlists_router.router, prefix="/api")
    app.include_router(alerts_router.router, prefix="/api")

    def override_get_db():
        with Session(postgres_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(
        app,
        headers={"X-Workspace-ID": str(tenant_rows.alice_workspace.public_id)},
    ) as client:
        client.cookies.set("portfyl_session", tenant_rows.alice_session_token)
        yield client


def _alice_portfolio_param(tenant_rows: TenantRows) -> dict:
    return {"portfolio_id": str(tenant_rows.alice_portfolio.public_id)}


# -------- watchlists ---------------------------------------------------------


def test_watchlist_list_never_includes_other_workspace(alice_client: TestClient, tenant_rows: TenantRows):
    response = alice_client.get("/api/watchlists")

    assert response.status_code == 200
    ids = [row["id"] for row in response.json()]
    assert ids == [str(tenant_rows.alice_watchlist.public_id)]
    UUID(ids[0])  # a real public UUID, never a raw integer PK
    assert str(tenant_rows.bob_watchlist.public_id) not in ids


def test_foreign_watchlist_update_is_not_addressable(alice_client: TestClient, tenant_rows: TenantRows):
    response = alice_client.patch(
        f"/api/watchlists/{tenant_rows.bob_watchlist.public_id}",
        json={"name": "stolen"},
    )
    assert response.status_code == 404


def test_foreign_watchlist_delete_is_not_addressable(alice_client: TestClient, tenant_rows: TenantRows):
    response = alice_client.delete(f"/api/watchlists/{tenant_rows.bob_watchlist.public_id}")
    assert response.status_code == 404


def test_random_uuid_is_indistinguishable_from_foreign_watchlist(alice_client: TestClient, tenant_rows: TenantRows):
    foreign = alice_client.delete(f"/api/watchlists/{tenant_rows.bob_watchlist.public_id}")
    random_uuid = alice_client.delete(f"/api/watchlists/{uuid4()}")
    assert foreign.status_code == random_uuid.status_code == 404


def test_foreign_watchlist_item_add_is_not_addressable(alice_client: TestClient, tenant_rows: TenantRows):
    response = alice_client.post(
        f"/api/watchlists/{tenant_rows.bob_watchlist.public_id}/items",
        json={"ticker": "TSLA"},
    )
    assert response.status_code == 404


def test_own_watchlist_crud_and_item_roundtrip_uses_public_uuids(alice_client: TestClient, tenant_rows: TenantRows):
    created = alice_client.post("/api/watchlists", json={"name": "Dividend growth", "color": "#00ff00"})
    assert created.status_code == 200
    watchlist_id = created.json()["id"]
    UUID(watchlist_id)

    item = alice_client.post(f"/api/watchlists/{watchlist_id}/items", json={"ticker": "ko"})
    assert item.status_code == 200
    item_body = item.json()
    assert item_body["ticker"] == "KO"
    item_id = item_body["id"]
    UUID(item_id)
    assert item_body["watchlist_id"] == watchlist_id

    updated = alice_client.patch(f"/api/watchlists/{watchlist_id}", json={"name": "Renamed"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed"

    remove = alice_client.delete(f"/api/watchlists/{watchlist_id}/items/{item_id}")
    assert remove.status_code == 200

    deleted = alice_client.delete(f"/api/watchlists/{watchlist_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted_id"] == watchlist_id


def test_cross_tenant_duplicate_watchlist_name_succeeds(alice_client: TestClient, tenant_rows: TenantRows):
    # Bob already owns a watchlist named "Tech" (Alice's own seeded watchlist
    # is named "Growth") -- Alice creating her own "Tech" must succeed, since
    # the uniqueness constraint is per-workspace, not global.
    response = alice_client.post("/api/watchlists", json={"name": "Tech"})
    assert response.status_code == 200
    assert response.json()["name"] == "Tech"
    assert response.json()["id"] != str(tenant_rows.bob_watchlist.public_id)


def test_same_tenant_duplicate_watchlist_name_is_conflict(alice_client: TestClient, tenant_rows: TenantRows):
    # Alice already owns "Growth" (seeded by tenant_rows) -- a second one is a 409.
    response = alice_client.post("/api/watchlists", json={"name": "Growth"})
    assert response.status_code == 409


# -------- alerts ---------------------------------------------------------


def test_alert_list_never_includes_other_workspace(alice_client: TestClient, tenant_rows: TenantRows):
    response = alice_client.get("/api/alerts", params=_alice_portfolio_param(tenant_rows))

    assert response.status_code == 200
    ids = [row["id"] for row in response.json()]
    assert ids == [str(tenant_rows.alice_alert.public_id)]
    UUID(ids[0])
    assert str(tenant_rows.bob_alert.public_id) not in ids


def test_foreign_alert_update_is_not_addressable(alice_client: TestClient, tenant_rows: TenantRows):
    response = alice_client.patch(
        f"/api/alerts/{tenant_rows.bob_alert.public_id}",
        params=_alice_portfolio_param(tenant_rows),
        json={"target_price": 1.0},
    )
    assert response.status_code == 404


def test_foreign_alert_delete_is_not_addressable(alice_client: TestClient, tenant_rows: TenantRows):
    response = alice_client.delete(
        f"/api/alerts/{tenant_rows.bob_alert.public_id}",
        params=_alice_portfolio_param(tenant_rows),
    )
    assert response.status_code == 404


def test_random_uuid_is_indistinguishable_from_foreign_alert(alice_client: TestClient, tenant_rows: TenantRows):
    foreign = alice_client.delete(
        f"/api/alerts/{tenant_rows.bob_alert.public_id}",
        params=_alice_portfolio_param(tenant_rows),
    )
    random_uuid = alice_client.delete(
        f"/api/alerts/{uuid4()}", params=_alice_portfolio_param(tenant_rows),
    )
    assert foreign.status_code == random_uuid.status_code == 404


def test_own_alert_crud_uses_public_uuids(alice_client: TestClient, tenant_rows: TenantRows):
    created = alice_client.post(
        "/api/alerts",
        params=_alice_portfolio_param(tenant_rows),
        json={"ticker": "nvda", "direction": "above", "target_price": 900},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["ticker"] == "NVDA"
    alert_id = body["id"]
    UUID(alert_id)

    updated = alice_client.patch(
        f"/api/alerts/{alert_id}",
        params=_alice_portfolio_param(tenant_rows),
        json={"target_price": 950},
    )
    assert updated.status_code == 200
    assert updated.json()["target_price"] == 950

    deleted = alice_client.delete(f"/api/alerts/{alert_id}", params=_alice_portfolio_param(tenant_rows))
    assert deleted.status_code == 200
    assert deleted.json()["deleted_id"] == alert_id


def test_alert_check_only_evaluates_current_workspaces_alerts(
    alice_client: TestClient, tenant_rows: TenantRows, monkeypatch,
):
    # /alerts/check must never fire (or even look at) Bob's alert while acting
    # as Alice -- run_check is given Alice's workspace_id and her portfolio_id
    # only.
    from unittest.mock import AsyncMock, patch

    with patch("routers.alerts.market_data.get_infos", return_value={
        "AAPL": {"currentPrice": 999.0, "regularMarketPrice": 999.0, "currency": "USD"},
    }), patch("routers.alerts.send_discord_notification", AsyncMock(return_value=None)):
        response = alice_client.post("/api/alerts/check", params=_alice_portfolio_param(tenant_rows))

    assert response.status_code == 200
    body = response.json()
    assert body["checked"] is True
    fired_tickers = {row["ticker"] for row in body["fired"]}
    assert fired_tickers == {"AAPL"}  # Alice's own alert; never Bob's MSFT one
