"""broker_requests under real PostgreSQL: forced RLS, per-workspace uniqueness
and cascade (onboarding-flow plan, Task 3). `matrix_tenants` must be listed
before `runtime_session` (see test_runtime_role.py's fixture-order note)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from auth import create_session
from database import set_rls_context
from models import BrokerRequest, User, Workspace
from tests.postgres.conftest import MatrixTenants, _matrix_app


def _as(session: Session, tenant) -> None:
    set_rls_context(session, tenant.user_id, tenant.workspace_id)


def _client(postgres_engine, tenant, session_token, csrf_token) -> TestClient:
    from routers import broker_requests

    app = _matrix_app(postgres_engine)
    app.include_router(broker_requests.router, prefix="/api")
    client = TestClient(
        app,
        headers={
            "X-Workspace-ID": str(tenant.workspace_public_id),
            "X-CSRF-Token": csrf_token,
        },
    )
    client.cookies.set("portfyl_session", session_token)
    return client


@pytest.fixture
def alice_client(postgres_engine, matrix_tenants: MatrixTenants):
    with _client(
        postgres_engine, matrix_tenants.alice,
        matrix_tenants.session_token, matrix_tenants.csrf_token,
    ) as client:
        yield client


@pytest.fixture
def bob_client(postgres_engine, matrix_tenants: MatrixTenants):
    with Session(postgres_engine) as db:
        issued = create_session(db, matrix_tenants.bob.user_id)
        db.commit()
    with _client(postgres_engine, matrix_tenants.bob, issued.raw_token, issued.csrf_token) as client:
        yield client


def _count(postgres_engine, workspace_id) -> int:
    # The engine owner is not subject to RLS here, so this sees every row.
    with Session(postgres_engine) as owner:
        return owner.execute(
            text("SELECT count(*) FROM broker_requests WHERE workspace_id = :w"),
            {"w": workspace_id},
        ).scalar_one()


def test_alices_request_is_invisible_to_bob(
    matrix_tenants: MatrixTenants, alice_client: TestClient, bob_client: TestClient,
    runtime_session: Session,
):
    created = alice_client.post("/api/broker-requests", json={"broker_name": " Trade  Republic "})
    assert created.status_code == 201
    assert created.json() == {"broker_name": "Trade Republic", "created": True}

    # Through the API: Bob is not told "already exists"; his own row is new.
    bobs = bob_client.post("/api/broker-requests", json={"broker_name": "trade republic"})
    assert bobs.status_code == 201
    assert bobs.json() == {"broker_name": "trade republic", "created": True}

    # Through a raw query under RLS: each side sees only its own row.
    _as(runtime_session, matrix_tenants.bob)
    assert sorted(r.broker_name for r in runtime_session.scalars(select(BrokerRequest))) == [
        "Bob seeded broker", "trade republic",
    ]
    assert runtime_session.execute(
        text("SELECT count(*) FROM broker_requests WHERE workspace_id = :w"),
        {"w": matrix_tenants.alice.workspace_id},
    ).scalar_one() == 0
    # No rollback here: it would also drop the fixture's SET LOCAL ROLE.
    _as(runtime_session, matrix_tenants.alice)
    assert sorted(r.broker_name for r in runtime_session.scalars(select(BrokerRequest))) == [
        "Alice seeded broker", "Trade Republic",
    ]


def test_alice_cannot_write_a_row_into_bobs_workspace(
    matrix_tenants: MatrixTenants, runtime_session: Session,
):
    _as(runtime_session, matrix_tenants.alice)
    runtime_session.add(BrokerRequest(
        workspace_id=matrix_tenants.bob.workspace_id,
        user_id=matrix_tenants.alice.user_id,
        broker_name="Sneaky",
    ))
    with pytest.raises(DBAPIError):
        runtime_session.flush()


def test_unscoped_runtime_session_sees_nothing(
    matrix_tenants: MatrixTenants, alice_client: TestClient, runtime_session: Session,
):
    assert alice_client.post("/api/broker-requests", json={"broker_name": "Revolut"}).status_code == 201
    assert runtime_session.scalars(select(BrokerRequest)).all() == []


def test_name_is_unique_per_workspace_case_insensitively(
    matrix_tenants: MatrixTenants, runtime_session: Session,
):
    _as(runtime_session, matrix_tenants.alice)
    runtime_session.add(BrokerRequest(
        workspace_id=matrix_tenants.alice.workspace_id,
        user_id=matrix_tenants.alice.user_id, broker_name="Revolut",
    ))
    runtime_session.flush()
    runtime_session.add(BrokerRequest(
        workspace_id=matrix_tenants.alice.workspace_id,
        user_id=matrix_tenants.alice.user_id, broker_name="REVOLUT",
    ))
    with pytest.raises(IntegrityError):
        runtime_session.flush()


def test_deleting_the_workspace_removes_its_requests(
    matrix_tenants: MatrixTenants, alice_client: TestClient, bob_client: TestClient,
    postgres_engine,
):
    assert alice_client.post("/api/broker-requests", json={"broker_name": "Revolut"}).status_code == 201
    assert bob_client.post("/api/broker-requests", json={"broker_name": "Revolut"}).status_code == 201
    alice_ws, bob_ws = matrix_tenants.alice.workspace_id, matrix_tenants.bob.workspace_id
    # Each tenant already has one seeded row (tests/postgres/conftest.py).
    assert _count(postgres_engine, alice_ws) == 2
    assert _count(postgres_engine, bob_ws) == 2

    with Session(postgres_engine) as owner:
        owner.execute(delete(Workspace).where(Workspace.id == alice_ws))
        owner.commit()

    assert _count(postgres_engine, alice_ws) == 0
    assert _count(postgres_engine, bob_ws) == 2  # Bob's rows are untouched


def test_deleting_the_user_removes_their_requests(
    matrix_tenants: MatrixTenants, alice_client: TestClient, postgres_engine,
):
    assert alice_client.post("/api/broker-requests", json={"broker_name": "Revolut"}).status_code == 201
    with Session(postgres_engine) as owner:
        owner.execute(delete(User).where(User.id == matrix_tenants.alice.user_id))
        owner.commit()
    assert _count(postgres_engine, matrix_tenants.alice.workspace_id) == 0
