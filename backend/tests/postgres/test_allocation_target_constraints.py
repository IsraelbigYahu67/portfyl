"""Database-level guarantees for allocation_targets (plan 2026-10-10, Task 4).

Runs as the real NOBYPASSRLS `portfyl_runtime` role. `matrix_tenants` must be
listed before `runtime_session` (see test_runtime_role.py's fixture-order note).
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from database import set_rls_context
from models import AllocationTarget, Portfolio


def _as(session: Session, tenant) -> None:
    set_rls_context(session, tenant.user_id, tenant.workspace_id)


def _portfolio_id(postgres_engine, tenant) -> int:
    with Session(postgres_engine) as owner:
        return owner.scalars(
            select(Portfolio.id).where(Portfolio.workspace_id == tenant.workspace_id)
        ).first()


def test_alice_sees_only_her_targets(matrix_tenants, runtime_session):
    _as(runtime_session, matrix_tenants.alice)
    rows = runtime_session.scalars(select(AllocationTarget)).all()
    assert len(rows) == 1
    assert rows[0].workspace_id == matrix_tenants.alice.workspace_id


def test_target_above_100_is_rejected_by_the_database(
    matrix_tenants, postgres_engine, runtime_session,
):
    portfolio_id = _portfolio_id(postgres_engine, matrix_tenants.alice)
    _as(runtime_session, matrix_tenants.alice)
    runtime_session.add(AllocationTarget(
        workspace_id=matrix_tenants.alice.workspace_id, portfolio_id=portfolio_id,
        ticker="MSFT", target_pct=101, display_order=1,
    ))
    with pytest.raises(IntegrityError):
        runtime_session.flush()


def test_duplicate_ticker_is_rejected_by_the_database(
    matrix_tenants, postgres_engine, runtime_session,
):
    portfolio_id = _portfolio_id(postgres_engine, matrix_tenants.alice)
    _as(runtime_session, matrix_tenants.alice)
    runtime_session.add(AllocationTarget(
        workspace_id=matrix_tenants.alice.workspace_id, portfolio_id=portfolio_id,
        ticker="AAPL", target_pct=10, display_order=1,
    ))
    with pytest.raises(IntegrityError):
        runtime_session.flush()


def test_alice_cannot_insert_into_bobs_workspace(
    matrix_tenants, postgres_engine, runtime_session,
):
    bob_portfolio_id = _portfolio_id(postgres_engine, matrix_tenants.bob)
    _as(runtime_session, matrix_tenants.alice)
    with pytest.raises(DBAPIError):
        runtime_session.execute(
            AllocationTarget.__table__.insert().values(
                public_id="00000000-0000-4000-8000-0000000a110c",
                workspace_id=matrix_tenants.bob.workspace_id,
                portfolio_id=bob_portfolio_id,
                ticker="X", target_pct=5, display_order=0,
            )
        )


def test_deleting_a_portfolio_deletes_its_targets(matrix_tenants, postgres_engine):
    portfolio_id = _portfolio_id(postgres_engine, matrix_tenants.alice)
    with Session(postgres_engine) as owner:
        owner.execute(delete(Portfolio).where(Portfolio.id == portfolio_id))
        owner.commit()
        remaining = owner.scalars(
            select(AllocationTarget).where(AllocationTarget.portfolio_id == portfolio_id)
        ).all()
    assert remaining == []


@pytest.fixture
def committing_runtime_session(postgres_engine):
    """`portfyl_runtime` with a session-level SET ROLE, so the router's real
    commit happens under forced RLS exactly as in production (Cloud Run logs in
    as portfyl_runtime). `runtime_session` cannot show this: it never commits."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

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


def test_saving_targets_under_the_runtime_role_returns_the_saved_set(
    matrix_tenants, postgres_engine, committing_runtime_session,
):
    from routers.allocation_targets import TargetItem, TargetsPayload, replace_targets

    db = committing_runtime_session
    _as(db, matrix_tenants.alice)
    portfolio = db.scalars(
        select(Portfolio).where(Portfolio.id == matrix_tenants.alice.portfolio_id)
    ).one()

    result = replace_targets(
        TargetsPayload(targets=[TargetItem(ticker="msft", target_pct="40", group="Core")]),
        db=db, portfolio=portfolio, context=None,
    )

    assert result == {
        "targets": [{"ticker": "MSFT", "group": "Core", "target_pct": 40.0}],
        "target_total_pct": 40.0,
        "is_complete": False,
    }
    with Session(postgres_engine) as owner:
        stored = owner.scalars(
            select(AllocationTarget.ticker).where(
                AllocationTarget.portfolio_id == matrix_tenants.alice.portfolio_id
            )
        ).all()
    assert stored == ["MSFT"]
