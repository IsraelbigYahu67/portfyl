"""Phase 7 pending activation through HTTP on the PostgreSQL tenant schema."""

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AuditLog, Portfolio, WorkspaceSetting
from portfolio_activation import (
    PENDING_PORTFOLIO_SETTING_KEY,
    pending_portfolio,
    set_pending_portfolio,
)


CSV = b"date,ticker,type,shares,price,currency\n2026-01-03,MSFT,buy,1,400,CZK\n"


def _bob_pending(postgres_engine, matrix_tenants):
    with Session(postgres_engine) as db:
        portfolio = Portfolio(workspace_id=matrix_tenants.bob.workspace_id, name="Bob pending")
        db.add(portfolio)
        db.flush()
        set_pending_portfolio(db, portfolio)
        public_id = str(portfolio.public_id)
        db.commit()
    return public_id


def _marker(db, workspace_id):
    return db.scalar(select(WorkspaceSetting.value).where(
        WorkspaceSetting.workspace_id == workspace_id,
        WorkspaceSetting.key == PENDING_PORTFOLIO_SETTING_KEY,
    ))


def test_pending_create_list_and_blank_activation_do_not_address_bobs_marker(
    matrix_client, matrix_tenants, postgres_engine,
):
    bob_id = _bob_pending(postgres_engine, matrix_tenants)
    with Session(postgres_engine) as db:
        bob_marker = _marker(db, matrix_tenants.bob.workspace_id)

    first = matrix_client.post("/api/portfolios/pending-import")
    second = matrix_client.post("/api/portfolios/pending-import")
    assert first.status_code == second.status_code == 200
    alice_id = first.json()["id"]
    assert second.json()["id"] == alice_id
    assert first.json()["activation_state"] == "pending_import"
    listed = matrix_client.get("/api/portfolios")
    assert listed.status_code == 200
    assert bob_id not in listed.text
    assert next(row for row in listed.json() if row["id"] == alice_id)["activation_state"] == "pending_import"

    foreign = matrix_client.post(f"/api/portfolios/{bob_id}/activate")
    unknown = matrix_client.post(f"/api/portfolios/{uuid4()}/activate")
    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json() == unknown.json()
    forged = matrix_client.post("/api/portfolios/pending-import", headers={
        "X-Workspace-ID": str(matrix_tenants.bob.workspace_public_id),
    })
    assert forged.status_code == 404

    activated = matrix_client.post(f"/api/portfolios/{alice_id}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["activation_state"] == "active"
    with Session(postgres_engine) as db:
        assert _marker(db, matrix_tenants.alice.workspace_id) is None
        assert _marker(db, matrix_tenants.bob.workspace_id) == bob_marker
        audit = db.scalar(select(AuditLog).where(
            AuditLog.workspace_id == matrix_tenants.alice.workspace_id,
            AuditLog.action == "onboarding.portfolio.activated",
            AuditLog.target_id == alice_id,
        ))
        assert audit.event_metadata == {"kind": "blank"}


def test_pending_import_failure_preserves_marker_and_success_activates_only_alice(
    matrix_client, matrix_tenants, postgres_engine,
):
    bob_id = _bob_pending(postgres_engine, matrix_tenants)
    created = matrix_client.post("/api/portfolios/pending-import")
    assert created.status_code == 200, created.text
    alice_id = created.json()["id"]
    params = {"portfolio_id": alice_id}
    files = {"file": ("portfolio.csv", CSV, "text/csv")}
    preview = matrix_client.post("/api/portfolio/import-csv/preview", params=params, files=files)
    assert preview.status_code == 200, preview.text

    invalid = matrix_client.post("/api/portfolio/import-csv/commit", params={
        **params, "preview_id": str(uuid4()),
    }, files=files)
    assert invalid.status_code == 409, invalid.text
    foreign = matrix_client.post("/api/portfolio/import-csv/commit", params={
        "portfolio_id": bob_id, "preview_id": preview.json()["preview_id"],
    }, files=files)
    assert foreign.status_code == 404
    with Session(postgres_engine) as db:
        assert str(pending_portfolio(db, matrix_tenants.alice.workspace_id).public_id) == alice_id
        assert str(pending_portfolio(db, matrix_tenants.bob.workspace_id).public_id) == bob_id

    committed = matrix_client.post("/api/portfolio/import-csv/commit", params={
        **params, "preview_id": preview.json()["preview_id"],
    }, files=files)
    assert committed.status_code == 200, committed.text
    assert committed.json()["imported"] == 1
    with Session(postgres_engine) as db:
        assert _marker(db, matrix_tenants.alice.workspace_id) is None
        assert str(pending_portfolio(db, matrix_tenants.bob.workspace_id).public_id) == bob_id
        assert db.scalar(select(WorkspaceSetting).where(
            WorkspaceSetting.workspace_id == matrix_tenants.alice.workspace_id,
            WorkspaceSetting.key.like("import_undo:%"),
        )) is not None
        portfolio = db.scalar(select(Portfolio).where(Portfolio.public_id == UUID(alice_id)))
        assert portfolio.workspace_id == matrix_tenants.alice.workspace_id


def test_import_into_active_portfolio_keeps_the_pending_portfolio_hidden(
    matrix_client, matrix_tenants, postgres_engine,
):
    created = matrix_client.post("/api/portfolios/pending-import")
    assert created.status_code == 200, created.text
    pending_id = created.json()["id"]
    params = {"portfolio_id": str(matrix_tenants.alice.portfolio_public_id)}
    files = {"file": ("portfolio.csv", CSV, "text/csv")}
    preview = matrix_client.post("/api/portfolio/import-csv/preview", params=params, files=files)
    assert preview.status_code == 200, preview.text
    committed = matrix_client.post("/api/portfolio/import-csv/commit", params={
        **params, "preview_id": preview.json()["preview_id"],
    }, files=files)
    assert committed.status_code == 200, committed.text
    with Session(postgres_engine) as db:
        assert str(pending_portfolio(db, matrix_tenants.alice.workspace_id).public_id) == pending_id
