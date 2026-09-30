"""Tenant isolation for the corporate-action tables (plan 2026-09-24, B1).

Runs as the real NOBYPASSRLS `portfyl_runtime` role. `matrix_tenants` must be
listed before `runtime_session` (see test_runtime_role.py's fixture-order note).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from import_undo import capture_portfolio_state, restore_snapshot
from models import BrokerCorporateAction, BrokerCorporateActionApplication, Portfolio, Transaction
from database import set_rls_context


def _as(session: Session, tenant) -> None:
    set_rls_context(session, tenant.user_id, tenant.workspace_id)


def test_alice_sees_only_her_corporate_actions_and_applications(matrix_tenants, runtime_session):
    _as(runtime_session, matrix_tenants.alice)

    actions = runtime_session.scalars(select(BrokerCorporateAction)).all()
    applications = runtime_session.scalars(select(BrokerCorporateActionApplication)).all()

    assert len(actions) == 1 and len(applications) == 1
    assert {a.workspace_id for a in actions} == {matrix_tenants.alice.workspace_id}
    assert {a.workspace_id for a in applications} == {matrix_tenants.alice.workspace_id}


def test_alice_cannot_insert_a_corporate_action_into_bobs_workspace(
    matrix_tenants, postgres_engine, runtime_session,
):
    with Session(postgres_engine) as owner:
        bob_portfolio_id = owner.scalars(
            select(Portfolio.id).where(Portfolio.workspace_id == matrix_tenants.bob.workspace_id)
        ).first()
    _as(runtime_session, matrix_tenants.alice)

    with pytest.raises(DBAPIError):
        runtime_session.execute(
            BrokerCorporateAction.__table__.insert().values(
                public_id="00000000-0000-4000-8000-00000000b0b0",
                workspace_id=matrix_tenants.bob.workspace_id,
                portfolio_id=bob_portfolio_id,
                broker="trading212", account_fingerprint="f" * 64,
                provider_instrument_id="X_US_EQ", ticker="X", action_type="STOCK_SPLIT",
                effective_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
                provider_event_key="fill:x|fill:y", ratio_numerator=2, ratio_denominator=1,
                representation="api_normalized",
            )
        )


def test_alice_cannot_delete_bobs_corporate_actions(matrix_tenants, runtime_session):
    _as(runtime_session, matrix_tenants.alice)
    removed_applications = runtime_session.execute(
        delete(BrokerCorporateActionApplication).where(
            BrokerCorporateActionApplication.workspace_id == matrix_tenants.bob.workspace_id
        )
    ).rowcount
    removed_actions = runtime_session.execute(
        delete(BrokerCorporateAction).where(
            BrokerCorporateAction.workspace_id == matrix_tenants.bob.workspace_id
        )
    ).rowcount

    assert (removed_applications, removed_actions) == (0, 0)


def test_deleting_a_portfolio_cascades_its_actions_and_applications(matrix_tenants, postgres_engine):
    alice_ws, bob_ws = matrix_tenants.alice.workspace_id, matrix_tenants.bob.workspace_id
    with Session(postgres_engine) as db:
        db.execute(delete(Portfolio).where(Portfolio.workspace_id == alice_ws))
        db.commit()

        assert db.scalars(select(BrokerCorporateAction).where(
            BrokerCorporateAction.workspace_id == alice_ws)).all() == []
        assert db.scalars(select(BrokerCorporateActionApplication).where(
            BrokerCorporateActionApplication.workspace_id == alice_ws)).all() == []
        assert len(db.scalars(select(BrokerCorporateAction).where(
            BrokerCorporateAction.workspace_id == bob_ws)).all()) == 1


def test_undo_snapshot_round_trips_actions_and_applications_on_postgres(matrix_tenants, postgres_engine):
    """restore_snapshot re-inserts actions before applications under the real
    composite foreign keys and binds the ratio back into a numeric column."""
    alice_ws = matrix_tenants.alice.workspace_id
    with Session(postgres_engine) as db:
        portfolio = db.scalars(select(Portfolio).where(Portfolio.workspace_id == alice_ws)).first()
        snapshot = capture_portfolio_state(db, portfolio)
        assert len(snapshot["corporate_actions"]) == 1
        assert len(snapshot["corporate_action_applications"]) == 1

        restore_snapshot(db, portfolio, snapshot)
        db.commit()

        [action] = db.scalars(select(BrokerCorporateAction).where(
            BrokerCorporateAction.workspace_id == alice_ws)).all()
        [application] = db.scalars(select(BrokerCorporateActionApplication).where(
            BrokerCorporateActionApplication.workspace_id == alice_ws)).all()
        trade = db.scalars(select(Transaction).where(
            Transaction.workspace_id == alice_ws, Transaction.ticker == "AAPL")).one()
        assert (float(action.ratio_numerator), float(action.ratio_denominator)) == (10.0, 1.0)
        assert application.action_id == action.id
        assert application.transaction_id == trade.id
