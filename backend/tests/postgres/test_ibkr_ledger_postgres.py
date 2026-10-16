"""IBKR stock ledger import on real PostgreSQL: unique event identity, forced
RLS under the runtime role, and the Flex XML upload staying in Alice's
workspace."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from database import set_rls_context
from ibkr_ledger import apply_flex_ledger
from importers.instruments import DefaultInstrumentResolver
from models import Portfolio, Transaction

FIXTURE = (Path(__file__).resolve().parents[1] / "fixtures" / "brokers" / "ibkr"
           / "flex_2025_sample.xml").read_text()
RESOLVER = DefaultInstrumentResolver(figi=None)


@pytest.fixture(autouse=True)
def _offline_lookups(monkeypatch):
    monkeypatch.setattr("routers.portfolio.bulk_fetch_fx", lambda keys: {})
    monkeypatch.setattr("routers.portfolio.get_instrument_resolver", lambda: RESOLVER)


def _ibkr_count(db: Session, workspace_id) -> int:
    return db.scalar(
        select(func.count()).select_from(Transaction).where(
            Transaction.workspace_id == workspace_id, Transaction.source == "ibkr",
        )
    ) or 0


@pytest.fixture
def committing_runtime_session(postgres_engine):
    connection = postgres_engine.connect()
    connection.execute(text("SET ROLE portfyl_runtime"))
    connection.commit()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()
    try:
        yield session
    finally:
        session.close()
        try:
            connection.execute(text("RESET ROLE"))
            connection.commit()
        finally:
            connection.close()


@pytest.fixture
def alice_ibkr_portfolio_id(matrix_tenants, postgres_engine) -> int:
    """A dedicated portfolio: the matrix seed's own AAPL rows would (rightly)
    block the import as trades from another source."""
    with Session(postgres_engine) as owner:
        portfolio = Portfolio(workspace_id=matrix_tenants.alice.workspace_id, name="IBKR")
        owner.add(portfolio)
        owner.commit()
        return portfolio.id


def _as(db: Session, tenant, portfolio_id: int) -> Portfolio:
    set_rls_context(db, tenant.user_id, tenant.workspace_id)
    return db.scalars(select(Portfolio).where(Portfolio.id == portfolio_id)).one()


def test_flex_sync_is_idempotent_and_invisible_to_bob(
    matrix_tenants, alice_ibkr_portfolio_id, committing_runtime_session, postgres_engine,
):
    db = committing_runtime_session
    alice, bob = matrix_tenants.alice, matrix_tenants.bob

    first = apply_flex_ledger(db, _as(db, alice, alice_ibkr_portfolio_id), FIXTURE, resolver=RESOLVER)
    db.commit()
    second = apply_flex_ledger(db, _as(db, alice, alice_ibkr_portfolio_id), FIXTURE, resolver=RESOLVER)
    db.commit()
    assert first["status"] == "imported" and first["imported"] > 0
    assert second == {"status": "imported", "imported": 0,
                      "already_present": first["imported"], "errors": []}

    with Session(postgres_engine) as owner:
        assert _ibkr_count(owner, alice.workspace_id) == first["imported"]
        assert _ibkr_count(owner, bob.workspace_id) == 0

    # Under the runtime role Bob's context sees none of Alice's rows.
    set_rls_context(db, bob.user_id, bob.workspace_id)
    assert db.scalar(select(func.count()).select_from(Transaction)
                     .where(Transaction.source == "ibkr")) == 0
    db.rollback()


def test_unique_index_backs_the_event_identity(
    matrix_tenants, alice_ibkr_portfolio_id, committing_runtime_session,
):
    db = committing_runtime_session
    alice = matrix_tenants.alice
    apply_flex_ledger(db, _as(db, alice, alice_ibkr_portfolio_id), FIXTURE, resolver=RESOLVER)
    db.commit()

    portfolio = _as(db, alice, alice_ibkr_portfolio_id)
    original = db.scalars(select(Transaction).where(
        Transaction.workspace_id == alice.workspace_id,
        Transaction.source == "ibkr", Transaction.source_event_id == "9001",
    )).one()
    db.add(Transaction(
        workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id, date=original.date,
        type="buy", ticker="AAPL", shares=1.0, price=1.0, currency="USD", source="ibkr",
        source_event_stream="trades", source_event_id="9001",
    ))
    with pytest.raises(IntegrityError):
        db.flush()
    db.rollback()


def test_flex_xml_upload_stays_in_alice_workspace(matrix_client, matrix_tenants, postgres_engine):
    # An XML upload appends next to the seed's rows (no duplicate guard: the
    # user chose this portfolio and sees the preview first).
    params = {"portfolio_id": str(matrix_tenants.alice.portfolio_public_id)}
    upload = {"file": ("statement.xml", FIXTURE.encode(), "application/xml")}
    preview = matrix_client.post("/api/portfolio/import-csv/preview", params=params, files=upload)
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["format"] == "Interactive Brokers (Flex XML)"
    assert body["skipped_reasons"] == {"options (synced to Options)": 1, "unsupported asset: BOND": 1}

    commit = matrix_client.post(
        "/api/portfolio/import-csv/commit",
        params={**params, "preview_id": body["preview_id"]}, files=upload,
    )
    assert commit.status_code == 200, commit.text
    imported = commit.json()["imported"]
    assert imported > 0

    with Session(postgres_engine) as owner:
        assert _ibkr_count(owner, matrix_tenants.alice.workspace_id) == imported
        assert _ibkr_count(owner, matrix_tenants.bob.workspace_id) == 0

    again = matrix_client.post("/api/portfolio/import-csv/preview", params=params, files=upload)
    assert again.status_code == 200, again.text
    assert again.json()["counts"]["added"] == 0
