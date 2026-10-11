"""Releasing a request's DB connection before market-data calls keeps RLS intact.

`database.release_request_connections()` ends the request session's read
transaction before Yahoo Finance is called, so slow quotes no longer pin the
small connection pool. The RLS identity is transaction-local; these tests run
as the NOBYPASSRLS `portfyl_runtime` role to prove that the next transaction
gets the same identity back (only the caller's rows) and that market-data
routes still answer after releasing mid-request.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

import database
from database import get_db, release_request_connections, set_rls_context
from models import Portfolio
from tests.postgres.conftest import MatrixTenants, _matrix_app
from tests.postgres.test_runtime_role_commits import _release, _runtime_connection


@pytest.fixture
def request_scoped():
    """Isolate the per-call registry of request sessions for this test."""
    token = database._request_sessions.set(())
    try:
        yield
    finally:
        database._request_sessions.reset(token)


def _request_session(connection):
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()
    session.info[database._REQUEST_SCOPED_KEY] = True
    return session


def test_a_released_request_session_still_sees_only_its_own_rows(
    matrix_tenants, postgres_engine, request_scoped,
):
    alice = matrix_tenants.alice
    connection = _runtime_connection(postgres_engine)
    session = _request_session(connection)
    try:
        set_rls_context(session, alice.user_id, alice.workspace_id)
        assert set(session.scalars(select(Portfolio.id))) == {alice.portfolio_id}

        release_request_connections()
        assert not session.in_transaction()

        assert set(session.scalars(select(Portfolio.id))) == {alice.portfolio_id}
    finally:
        session.close()
        _release(connection)


@pytest.fixture
def releasing_client(postgres_engine: Engine, matrix_tenants: MatrixTenants):
    app = _matrix_app(postgres_engine)

    def runtime_request_db():
        connection = _runtime_connection(postgres_engine)
        session = _request_session(connection)
        try:
            yield session
        finally:
            session.close()
            _release(connection)

    app.dependency_overrides[get_db] = runtime_request_db
    with TestClient(
        app,
        headers={"X-Workspace-ID": str(matrix_tenants.alice.workspace_public_id)},
    ) as client:
        client.cookies.set("portfyl_session", matrix_tenants.session_token)
        yield client


@pytest.mark.parametrize("path", ["/api/portfolio/holdings", "/api/portfolio/dividends", "/api/portfolio/summary"])
def test_market_data_routes_answer_after_releasing_mid_request(
    path, releasing_client, matrix_tenants, mock_yfinance, monkeypatch,
):
    import market_data

    released: list[bool] = []
    real_release = database.release_request_connections

    def spy():
        released.append(True)
        real_release()

    monkeypatch.setattr(market_data, "_cache", {})
    monkeypatch.setattr(database, "release_request_connections", spy)

    response = releasing_client.get(
        path, params={"portfolio_id": str(matrix_tenants.alice.portfolio_public_id)},
    )

    assert response.status_code == 200, response.text
    assert released, f"{path} never released its connection before market data"
    bob_uuid = str(matrix_tenants.bob.portfolio_public_id)
    assert bob_uuid not in response.text
