"""Demo cleanup on Trading 212 connect, on real PostgreSQL with forced RLS.

Connecting a broker deletes onboarding sample data (demo_cleanup). It runs
as the restricted runtime role and must only ever reach the caller's
workspace: Bob's identical demo portfolio has to survive Alice's connect.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session, sessionmaker

from auth import create_session
from database import get_db
from edition import Edition
from models import AuditLog, Membership, Portfolio, Transaction, User, Workspace
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


def _demo_txn(workspace_id, portfolio_id, ticker):
    return Transaction(
        workspace_id=workspace_id, portfolio_id=portfolio_id, ticker=ticker,
        name=ticker, type="buy", shares=1, price=100.0, currency="USD",
        date=date(2025, 1, 2), source="demo",
    )


def _tenant(db, label):
    user = User(
        firebase_uid=f"firebase-demo-{label}-{uuid4().hex}",
        email=f"demo-{label}-{uuid4().hex}@example.com",
    )
    workspace = Workspace(name=f"{label} workspace")
    db.add_all([user, workspace])
    db.flush()
    db.add(Membership(
        user_id=user.id, workspace_id=workspace.id, role="owner", status="active",
    ))
    demo = Portfolio(workspace_id=workspace.id, name="Portfyl demo", is_default=True)
    real = Portfolio(workspace_id=workspace.id, name="Real")
    db.add_all([demo, real])
    db.flush()
    db.add_all([
        _demo_txn(workspace.id, demo.id, "AAPL"),
        _demo_txn(workspace.id, real.id, "MSFT"),
    ])
    issued = create_session(db, user.id)
    return {
        "workspace": workspace,
        "demo": demo,
        "real": real,
        "token": issued.raw_token,
        "csrf": issued.csrf_token,
    }


@pytest.fixture
def tenants(postgres_engine):
    _clear(postgres_engine)
    with Session(postgres_engine, expire_on_commit=False) as db:
        alice = _tenant(db, "alice")
        bob = _tenant(db, "bob")
        db.commit()
    try:
        yield alice, bob
    finally:
        _clear(postgres_engine)


@pytest.fixture
def alice_client(postgres_engine, tenants, monkeypatch):
    alice, _bob = tenants
    monkeypatch.setattr(broker_router.httpx, "get", lambda *_a, **_k: _Info())
    monkeypatch.setattr(broker_router, "_fetch_account_summary", lambda *_: {
        "id": "demo-cleanup-account",
        "cash": {"availableToTrade": 10.0, "inPies": 0.0, "reservedForOrders": 0.0},
        "currency": "USD",
        "investments": {"currentValue": 20.0},
        "totalValue": 30.0,
    })

    app = FastAPI()
    app.state.portfyl_edition = Edition.LOCAL
    app.add_exception_handler(RequestContextError, request_context_error_handler)
    app.include_router(broker_router.router, prefix="/api")

    def override_get_db():
        # The NOBYPASSRLS runtime role, as in production.
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
            "X-Workspace-ID": str(alice["workspace"].public_id),
            "X-CSRF-Token": alice["csrf"],
        },
        raise_server_exceptions=True,
    ) as client:
        client.cookies.set("portfyl_session", alice["token"])
        yield client


def test_connect_removes_only_the_callers_demo_data(
    alice_client, tenants, postgres_engine,
):
    alice, bob = tenants
    response = alice_client.post(
        "/api/broker/trading212/connect",
        params={"portfolio_id": str(alice["real"].public_id)},
        json={"api_key": "k" * 20, "api_secret": "s" * 20, "environment": "live"},
    )
    assert response.status_code == 200, response.text

    with Session(postgres_engine) as db:
        alice_portfolios = db.scalars(select(Portfolio.name).where(
            Portfolio.workspace_id == alice["workspace"].id
        )).all()
        assert alice_portfolios == ["Real"]
        assert db.scalar(select(Portfolio.is_default).where(
            Portfolio.id == alice["real"].id
        )) is True
        assert db.scalars(select(Transaction.id).where(
            Transaction.workspace_id == alice["workspace"].id
        )).all() == []

        bob_portfolios = sorted(db.scalars(select(Portfolio.name).where(
            Portfolio.workspace_id == bob["workspace"].id
        )).all())
        assert bob_portfolios == ["Portfyl demo", "Real"]
        assert db.query(Transaction).filter(
            Transaction.workspace_id == bob["workspace"].id
        ).count() == 2

        audit = db.scalar(select(AuditLog).where(
            AuditLog.action == "onboarding.demo.removed"
        ))
        assert audit is not None
        assert audit.workspace_id == alice["workspace"].id
        assert audit.event_metadata == {
            "transactions": 2, "portfolios": 1, "renamed": False,
        }
