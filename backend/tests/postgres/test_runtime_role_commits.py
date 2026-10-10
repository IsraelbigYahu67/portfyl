"""The request RLS context must survive the request's own commits.

`set_rls_context` uses `set_config(..., true)`, which PostgreSQL discards at the
end of every transaction, and request sessions expire their objects on commit.
In production Cloud Run connects as the NOBYPASSRLS `portfyl_runtime` role, so
any read after a route's `db.commit()` used to run with no workspace context and
find nothing (HTTP 500 although the write had committed). The Alice/Bob matrix
cannot show this because its client connects as the database owner, which
bypasses RLS; this file runs the same writes as `portfyl_runtime`.
"""

from __future__ import annotations

from typing import Any, Mapping

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from database import get_db, set_rls_context
from models import Portfolio
from tests.postgres.conftest import MatrixTenants, _matrix_app
from tests.postgres.matrix_cases import (
    ALICE_PORTFOLIO_PARAMS,
    OWN_DELETE_CASES,
    OWN_MUTATIONS,
    RESOURCE_CASES,
    resolve,
    resolve_params,
)
from tests.postgres.test_alice_bob_matrix import _Hermetic


def _runtime_connection(postgres_engine: Engine):
    connection = postgres_engine.connect()
    connection.execute(text("SET ROLE portfyl_runtime"))
    connection.commit()
    return connection


def _release(connection) -> None:
    try:
        connection.execute(text("RESET ROLE"))
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def runtime_db(postgres_engine: Engine):
    """A request-style session (same options as SessionLocal) as portfyl_runtime."""
    connection = _runtime_connection(postgres_engine)
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()
    try:
        yield session
    finally:
        session.close()
        _release(connection)


def _visible_portfolio_ids(db) -> set[int]:
    return set(db.scalars(select(Portfolio.id)).all())


# ---------------------------------------------------------------------------
# Session level
# ---------------------------------------------------------------------------


def test_context_survives_a_commit_in_the_same_session(matrix_tenants, runtime_db):
    alice = matrix_tenants.alice
    set_rls_context(runtime_db, alice.user_id, alice.workspace_id)
    runtime_db.commit()

    assert _visible_portfolio_ids(runtime_db) == {alice.portfolio_id}


def test_context_survives_a_rollback_in_the_same_session(matrix_tenants, runtime_db):
    alice = matrix_tenants.alice
    set_rls_context(runtime_db, alice.user_id, alice.workspace_id)
    runtime_db.rollback()

    assert _visible_portfolio_ids(runtime_db) == {alice.portfolio_id}


def test_a_later_context_replaces_the_earlier_one(matrix_tenants, runtime_db):
    set_rls_context(runtime_db, matrix_tenants.alice.user_id, matrix_tenants.alice.workspace_id)
    runtime_db.commit()
    set_rls_context(runtime_db, matrix_tenants.bob.user_id, matrix_tenants.bob.workspace_id)
    runtime_db.commit()

    assert _visible_portfolio_ids(runtime_db) == {matrix_tenants.bob.portfolio_id}


def test_context_never_leaks_into_the_next_session_on_the_same_connection(
    matrix_tenants, postgres_engine,
):
    connection = _runtime_connection(postgres_engine)
    try:
        first = sessionmaker(bind=connection)()
        set_rls_context(first, matrix_tenants.alice.user_id, matrix_tenants.alice.workspace_id)
        first.commit()
        assert _visible_portfolio_ids(first) == {matrix_tenants.alice.portfolio_id}
        first.close()

        second = sessionmaker(bind=connection)()
        assert _visible_portfolio_ids(second) == set()
        second.close()
    finally:
        _release(connection)


# ---------------------------------------------------------------------------
# HTTP level: the matrix's own-side writes, as portfyl_runtime
# ---------------------------------------------------------------------------


@pytest.fixture
def runtime_client(postgres_engine: Engine, matrix_tenants: MatrixTenants) -> TestClient:
    app = _matrix_app(postgres_engine)

    def runtime_get_db():
        connection = _runtime_connection(postgres_engine)
        session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()
        try:
            yield session
        finally:
            session.close()
            _release(connection)

    app.dependency_overrides[get_db] = runtime_get_db
    with TestClient(
        app,
        headers={
            "X-Workspace-ID": str(matrix_tenants.alice.workspace_public_id),
            "X-CSRF-Token": matrix_tenants.csrf_token,
        },
    ) as client:
        client.cookies.set("portfyl_session", matrix_tenants.session_token)
        yield client


def _send(client: TestClient, method: str, url: str, params: Mapping[str, str] | None, payload: Any):
    kwargs: dict[str, Any] = {"params": dict(params or {})}
    if payload is not None:
        kwargs["json"] = dict(payload) if isinstance(payload, Mapping) else payload
    with _Hermetic():
        return client.request(method, url, **kwargs)


@pytest.mark.parametrize(
    "case", [c for c in RESOURCE_CASES if c.create_payload], ids=lambda c: c.resource,
)
def test_create_succeeds_as_the_runtime_role(case, runtime_client, matrix_tenants):
    response = _send(
        runtime_client, "POST", resolve(case.create_url or case.list_url, matrix_tenants.ids),
        resolve_params(case.params, matrix_tenants.ids), case.create_payload,
    )
    assert response.status_code == case.create_status, response.text


@pytest.mark.parametrize(
    "case", [c for c in RESOURCE_CASES if c.own_url and c.update_payload], ids=lambda c: c.resource,
)
def test_update_succeeds_as_the_runtime_role(case, runtime_client, matrix_tenants):
    response = _send(
        runtime_client, case.update_method, resolve(case.own_url, matrix_tenants.ids),
        resolve_params(case.params, matrix_tenants.ids), case.update_payload,
    )
    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    ("name", "method", "url", "payload", "expected"), OWN_MUTATIONS,
    ids=[row[0] for row in OWN_MUTATIONS],
)
def test_own_mutation_succeeds_as_the_runtime_role(
    name, method, url, payload, expected, runtime_client, matrix_tenants,
):
    response = _send(
        runtime_client, method, resolve(url, matrix_tenants.ids),
        resolve_params(ALICE_PORTFOLIO_PARAMS, matrix_tenants.ids), payload,
    )
    assert response.status_code == expected, response.text


@pytest.mark.parametrize(
    ("resource", "url", "params", "expected"), OWN_DELETE_CASES,
    ids=[row[0] for row in OWN_DELETE_CASES],
)
def test_own_delete_succeeds_as_the_runtime_role(
    resource, url, params, expected, runtime_client, matrix_tenants,
):
    response = _send(
        runtime_client, "DELETE", resolve(url, matrix_tenants.ids),
        resolve_params(params, matrix_tenants.ids), None,
    )
    assert response.status_code == expected, response.text
