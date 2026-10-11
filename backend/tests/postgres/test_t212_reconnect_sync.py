"""Trading 212 sync after Disconnect + Connect on real PostgreSQL with forced RLS.

Production regression (2026-10-11): the first POST /trading212/sync after a
disconnect/reconnect returned 500 with ``ObjectDeletedError`` on the freshly
created BrokerSyncRun when the response was built.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, text
from sqlalchemy.orm import Session, sessionmaker

from auth import create_session
from database import get_db
from edition import Edition
from models import BrokerSyncRun, Membership, Portfolio, User, Workspace
import t212_sync
from routers import broker as broker_router
from tenancy import RequestContextError, request_context_error_handler


class _Info:
    status_code = 200

    def raise_for_status(self):
        return None


def _clear(postgres_engine) -> None:
    with Session(postgres_engine) as db:
        db.execute(delete(User))
        db.execute(delete(Workspace))
        db.commit()


@pytest.fixture
def t212_tenant(postgres_engine):
    _clear(postgres_engine)
    with Session(postgres_engine, expire_on_commit=False) as db:
        user = User(
            firebase_uid=f"firebase-reconnect-{uuid4().hex}",
            email=f"reconnect-{uuid4().hex}@example.com",
        )
        workspace = Workspace(name="Reconnect workspace")
        db.add_all([user, workspace])
        db.flush()
        db.add(Membership(
            user_id=user.id, workspace_id=workspace.id, role="owner", status="active",
        ))
        portfolio = Portfolio(workspace_id=workspace.id, name="Reconnect", is_default=True)
        db.add(portfolio)
        db.flush()
        issued = create_session(db, user.id)
        db.commit()
        tenant = {
            "workspace": workspace,
            "portfolio": portfolio,
            "token": issued.raw_token,
            "csrf": issued.csrf_token,
        }
    try:
        yield tenant
    finally:
        _clear(postgres_engine)


@pytest.fixture
def t212_client(postgres_engine, t212_tenant, monkeypatch):
    monkeypatch.setattr(broker_router.httpx, "get", lambda *_a, **_k: _Info())
    monkeypatch.setattr(broker_router, "_fetch_account_summary", lambda *_: {
        "id": "reconnect-account",
        "cash": {"availableToTrade": 10.0, "inPies": 0.0, "reservedForOrders": 0.0},
        "currency": "USD",
        "investments": {"currentValue": 20.0},
        "totalValue": 30.0,
    })
    monkeypatch.setattr(t212_sync, "_fetch_positions", lambda *_: [
        {"ticker": "MSFT_US_EQ", "quantity": 3.0, "averagePrice": 250.0, "currentPrice": 260.0},
    ])

    app = FastAPI()
    app.state.portfyl_edition = Edition.LOCAL
    app.add_exception_handler(RequestContextError, request_context_error_handler)
    app.include_router(broker_router.router, prefix="/api")

    def override_get_db():
        # Production connects as the NOBYPASSRLS `portfyl_runtime` role; the
        # owner would bypass the policies and hide RLS-visibility bugs.
        connection = postgres_engine.connect()
        connection.execute(text("SET ROLE portfyl_runtime"))
        connection.commit()
        db = sessionmaker(autocommit=False, autoflush=False, bind=connection)()
        try:
            yield db
        finally:
            db.close()
            try:
                connection.execute(text("RESET ROLE"))
                connection.commit()
            finally:
                connection.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(
        app,
        headers={
            "X-Workspace-ID": str(t212_tenant["workspace"].public_id),
            "X-CSRF-Token": t212_tenant["csrf"],
        },
        raise_server_exceptions=True,
    ) as client:
        client.cookies.set("portfyl_session", t212_tenant["token"])
        yield client


def _call(client, method, path, tenant, **kwargs):
    return client.request(
        method, f"/api/broker/trading212/{path}",
        params={"portfolio_id": str(tenant["portfolio"].public_id)}, **kwargs,
    )


def test_sync_after_disconnect_and_reconnect_returns_a_fresh_run(
    t212_client, t212_tenant, postgres_engine,
):
    creds = {"api_key": "k" * 20, "api_secret": "s" * 20, "environment": "live"}

    assert _call(t212_client, "post", "connect", t212_tenant, json=creds).status_code == 200
    first = _call(t212_client, "post", "sync", t212_tenant)
    assert first.status_code == 202, first.text
    first_run_id = first.json()["history"]["run_id"]

    assert _call(t212_client, "delete", "connect", t212_tenant).status_code == 200
    with Session(postgres_engine) as db:
        assert db.query(BrokerSyncRun).count() == 0  # cascaded away

    assert _call(t212_client, "post", "connect", t212_tenant, json=creds).status_code == 200
    second = _call(t212_client, "post", "sync", t212_tenant)
    assert second.status_code == 202, second.text
    history = second.json()["history"]
    assert history["run_id"] != first_run_id
    assert history["status"] == "pending"

    # Duplicate click: still one active run, same id.
    third = _call(t212_client, "post", "sync", t212_tenant)
    assert third.status_code == 202, third.text
    assert third.json()["history"]["run_id"] == history["run_id"]
    with Session(postgres_engine) as db:
        assert db.query(BrokerSyncRun).count() == 1
