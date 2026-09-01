from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from auth import create_session
from database import get_db
from models import Membership, Portfolio, User, Workspace
from routers import portfolios
from tenancy import (
    RequestContextError,
    request_context_error_handler,
    require_portfolio,
)


@dataclass(frozen=True)
class TenantRows:
    alice: User
    alice_workspace: Workspace
    alice_portfolio: Portfolio
    alice_session_token: str
    alice_csrf_token: str
    bob: User
    bob_workspace: Workspace
    bob_portfolio: Portfolio


def _clear_tenant_rows(postgres_engine) -> None:
    with Session(postgres_engine) as db:
        db.execute(delete(User))
        db.execute(delete(Workspace))
        db.commit()


@pytest.fixture
def tenant_rows(postgres_engine) -> TenantRows:
    _clear_tenant_rows(postgres_engine)
    with Session(postgres_engine, expire_on_commit=False) as db:
        alice = User(firebase_uid="firebase-alice", email="alice@example.com")
        bob = User(firebase_uid="firebase-bob", email="bob@example.com")
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
            workspace_id=alice_workspace.id,
            name="Alice portfolio",
            is_default=True,
        )
        bob_portfolio = Portfolio(
            workspace_id=bob_workspace.id,
            name="Bob portfolio",
            is_default=True,
        )
        db.add_all([alice_portfolio, bob_portfolio])
        db.flush()
        issued = create_session(db, alice.id)
        db.commit()

        rows = TenantRows(
            alice=alice,
            alice_workspace=alice_workspace,
            alice_portfolio=alice_portfolio,
            alice_session_token=issued.raw_token,
            alice_csrf_token=issued.csrf_token,
            bob=bob,
            bob_workspace=bob_workspace,
            bob_portfolio=bob_portfolio,
        )

    try:
        yield rows
    finally:
        _clear_tenant_rows(postgres_engine)


@pytest.fixture
def alice_client(postgres_engine, tenant_rows: TenantRows) -> TestClient:
    app = FastAPI()
    app.add_exception_handler(RequestContextError, request_context_error_handler)
    app.include_router(portfolios.router, prefix="/api")

    @app.get("/api/resolved-portfolio")
    def resolved_portfolio(portfolio: Portfolio = Depends(require_portfolio)):
        return {"id": str(portfolio.public_id)}

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


def test_alice_lists_only_alice_portfolios(
    alice_client: TestClient,
    tenant_rows: TenantRows,
):
    response = alice_client.get("/api/portfolios")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [
        str(tenant_rows.alice_portfolio.public_id)
    ]


def test_missing_session_is_rejected(
    alice_client: TestClient,
):
    alice_client.cookies.clear()

    response = alice_client.get("/api/portfolios")

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_forged_workspace_header_is_not_enumerable(
    alice_client: TestClient,
    tenant_rows: TenantRows,
):
    response = alice_client.get(
        "/api/portfolios",
        headers={"X-Workspace-ID": str(tenant_rows.bob_workspace.public_id)},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "resource_not_found"


def test_single_workspace_is_inferred_when_header_is_absent(
    alice_client: TestClient,
    tenant_rows: TenantRows,
):
    del alice_client.headers["X-Workspace-ID"]

    response = alice_client.get("/api/portfolios")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [
        str(tenant_rows.alice_portfolio.public_id)
    ]


def test_multiple_workspaces_require_explicit_header(
    alice_client: TestClient,
    tenant_rows: TenantRows,
    postgres_engine,
):
    with Session(postgres_engine) as db:
        second_workspace = Workspace(name="Alice second workspace")
        db.add(second_workspace)
        db.flush()
        db.add(Membership(
            user_id=tenant_rows.alice.id,
            workspace_id=second_workspace.id,
            role="owner",
            status="active",
        ))
        db.commit()
    del alice_client.headers["X-Workspace-ID"]

    response = alice_client.get("/api/portfolios")

    assert response.status_code == 400
    assert response.json()["code"] == "workspace_required"


def test_archived_workspace_does_not_prevent_single_workspace_inference(
    alice_client: TestClient,
    tenant_rows: TenantRows,
    postgres_engine,
):
    with Session(postgres_engine) as db:
        archived_workspace = Workspace(
            name="Archived workspace",
            archived_at=datetime.now(timezone.utc),
        )
        db.add(archived_workspace)
        db.flush()
        db.add(Membership(
            user_id=tenant_rows.alice.id,
            workspace_id=archived_workspace.id,
            role="owner",
            status="active",
        ))
        db.commit()
    del alice_client.headers["X-Workspace-ID"]

    response = alice_client.get("/api/portfolios")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [
        str(tenant_rows.alice_portfolio.public_id)
    ]


def test_portfolio_mutation_requires_csrf(
    alice_client: TestClient,
    tenant_rows: TenantRows,
):
    response = alice_client.patch(
        f"/api/portfolios/{tenant_rows.alice_portfolio.public_id}",
        headers={"X-CSRF-Token": ""},
        json={"name": "Renamed"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "csrf_failed"


def test_create_portfolio_scopes_name_and_row_to_current_workspace(
    alice_client: TestClient,
    tenant_rows: TenantRows,
    postgres_engine,
):
    with Session(postgres_engine) as db:
        db.add(Portfolio(
            workspace_id=tenant_rows.bob_workspace.id,
            name="Shared name",
        ))
        db.commit()

    response = alice_client.post(
        "/api/portfolios",
        json={"name": "Shared name", "color": "#123456"},
    )

    assert response.status_code == 200
    public_id = UUID(response.json()["id"])
    with Session(postgres_engine) as db:
        created = db.scalar(
            select(Portfolio).where(Portfolio.public_id == public_id)
        )
        assert created is not None
        assert created.workspace_id == tenant_rows.alice_workspace.id
        assert created.color == "#123456"

    duplicate = alice_client.post(
        "/api/portfolios",
        json={"name": "Shared name"},
    )
    assert duplicate.status_code == 409


def test_update_own_portfolio_uses_public_uuid(
    alice_client: TestClient,
    tenant_rows: TenantRows,
    postgres_engine,
):
    response = alice_client.patch(
        f"/api/portfolios/{tenant_rows.alice_portfolio.public_id}",
        json={"name": "Alice renamed"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(tenant_rows.alice_portfolio.public_id)
    with Session(postgres_engine) as db:
        renamed = db.scalar(
            select(Portfolio).where(
                Portfolio.public_id == tenant_rows.alice_portfolio.public_id
            )
        )
        assert renamed is not None
        assert renamed.name == "Alice renamed"


def test_delete_last_portfolio_counts_only_current_workspace(
    alice_client: TestClient,
    tenant_rows: TenantRows,
    postgres_engine,
):
    response = alice_client.delete(
        f"/api/portfolios/{tenant_rows.alice_portfolio.public_id}"
    )

    assert response.status_code == 400
    with Session(postgres_engine) as db:
        assert db.scalar(
            select(Portfolio).where(
                Portfolio.public_id == tenant_rows.alice_portfolio.public_id
            )
        ) is not None


def test_delete_default_selects_replacement_only_in_current_workspace(
    alice_client: TestClient,
    tenant_rows: TenantRows,
    postgres_engine,
):
    with Session(postgres_engine, expire_on_commit=False) as db:
        replacement = Portfolio(
            workspace_id=tenant_rows.alice_workspace.id,
            name="Alice replacement",
        )
        db.add(replacement)
        db.commit()

    response = alice_client.delete(
        f"/api/portfolios/{tenant_rows.alice_portfolio.public_id}"
    )

    assert response.status_code == 200
    assert response.json()["deleted_id"] == str(
        tenant_rows.alice_portfolio.public_id
    )
    with Session(postgres_engine) as db:
        alice_replacement = db.scalar(
            select(Portfolio).where(Portfolio.public_id == replacement.public_id)
        )
        bob_portfolio = db.scalar(
            select(Portfolio).where(
                Portfolio.public_id == tenant_rows.bob_portfolio.public_id
            )
        )
        assert alice_replacement is not None
        assert alice_replacement.is_default is True
        assert bob_portfolio is not None
        assert bob_portfolio.is_default is True


def test_overview_counts_only_current_workspace(
    alice_client: TestClient,
):
    response = alice_client.get("/api/portfolios/overview")

    assert response.status_code == 200
    assert response.json()["portfolio_count"] == 1


def test_require_portfolio_resolves_default_and_hides_foreign_uuid(
    alice_client: TestClient,
    tenant_rows: TenantRows,
):
    default_response = alice_client.get("/api/resolved-portfolio")
    foreign_response = alice_client.get(
        "/api/resolved-portfolio",
        params={"portfolio_id": str(tenant_rows.bob_portfolio.public_id)},
    )

    assert default_response.status_code == 200
    assert default_response.json()["id"] == str(
        tenant_rows.alice_portfolio.public_id
    )
    assert foreign_response.status_code == 404
    assert foreign_response.json()["code"] == "resource_not_found"


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_alice_cannot_mutate_bob_portfolio(
    alice_client: TestClient,
    tenant_rows: TenantRows,
    method: str,
):
    response = alice_client.request(
        method.upper(),
        f"/api/portfolios/{tenant_rows.bob_portfolio.public_id}",
        json={"name": "stolen"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "resource_not_found"


def test_main_app_uses_dependency_scoped_request_context(
    postgres_engine,
    tenant_rows: TenantRows,
):
    import main

    def override_get_db():
        with Session(postgres_engine) as db:
            yield db

    main.app.dependency_overrides[get_db] = override_get_db
    client = TestClient(
        main.app,
        headers={
            "X-Workspace-ID": str(tenant_rows.alice_workspace.public_id),
        },
        raise_server_exceptions=False,
    )
    client.cookies.set("portfyl_session", tenant_rows.alice_session_token)
    try:
        response = client.get("/api/portfolios")
    finally:
        client.close()
        main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [
        str(tenant_rows.alice_portfolio.public_id)
    ]


def test_runtime_role_resolves_user_membership_then_workspace_context(
    postgres_engine,
    tenant_rows: TenantRows,
):
    app = FastAPI()
    app.add_exception_handler(RequestContextError, request_context_error_handler)
    app.include_router(portfolios.router, prefix="/api")

    def override_get_db():
        connection = postgres_engine.connect()
        transaction = connection.begin()
        connection.execute(text("SET LOCAL ROLE portfyl_runtime"))
        db = Session(bind=connection)
        try:
            yield db
        finally:
            db.close()
            if transaction.is_active:
                transaction.rollback()
            connection.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(
        app,
        headers={
            "X-Workspace-ID": str(tenant_rows.alice_workspace.public_id),
        },
    ) as client:
        client.cookies.set("portfyl_session", tenant_rows.alice_session_token)
        response = client.get("/api/portfolios")

    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [
        str(tenant_rows.alice_portfolio.public_id)
    ]
