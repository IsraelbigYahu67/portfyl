from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import Transaction


CSV = b"date,ticker,type,shares,price,currency\n2026-01-03,MSFT,buy,1,400,CZK\n"


def _count(db: Session, workspace_id) -> int:
    return db.scalar(
        select(func.count()).select_from(Transaction).where(
            Transaction.workspace_id == workspace_id
        )
    ) or 0


def test_preview_commit_and_undo_stay_inside_alice_workspace(
    matrix_client,
    matrix_tenants,
    postgres_engine,
):
    params = {"portfolio_id": str(matrix_tenants.alice.portfolio_public_id)}
    preview = matrix_client.post(
        "/api/portfolio/import-csv/preview",
        params=params,
        files={"file": ("portfolio.csv", CSV, "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["counts"]["added"] == 1

    with Session(postgres_engine) as db:
        assert _count(db, matrix_tenants.alice.workspace_id) == 2
        assert _count(db, matrix_tenants.bob.workspace_id) == 2
    commit = matrix_client.post(
        "/api/portfolio/import-csv/commit",
        params={**params, "preview_id": preview.json()["preview_id"]},
        files={"file": ("portfolio.csv", CSV, "text/csv")},
    )
    assert commit.status_code == 200, commit.text
    assert commit.json()["imported"] == 1

    with Session(postgres_engine) as db:
        assert _count(db, matrix_tenants.alice.workspace_id) == 3
        assert _count(db, matrix_tenants.bob.workspace_id) == 2

    undo = matrix_client.post("/api/portfolio/import-csv/undo", params=params)
    assert undo.status_code == 200, undo.text
    assert undo.json() == {"restored": 2, "undone": True}

    with Session(postgres_engine) as db:
        assert _count(db, matrix_tenants.alice.workspace_id) == 2
        assert _count(db, matrix_tenants.bob.workspace_id) == 2
