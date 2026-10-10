"""Cash routes must answer after their own commit under forced RLS.

`set_rls_context` is transaction-local (`set_config(..., true)`) and sessions
expire on commit, so in production (Cloud Run connects as the NOBYPASSRLS
`portfyl_runtime` role) any ORM read after `db.commit()` runs with no workspace
context and finds nothing. The matrix suite cannot see this: its client
connects as the database owner, which bypasses RLS. Here the routes run under a
session-level `SET ROLE portfyl_runtime` and really commit.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch
from uuid import UUID

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from database import set_rls_context
from models import CashInterestRate, Portfolio, Transaction
from routers.cash import (
    CashCreate,
    RateItem,
    RatesPayload,
    create_cash,
    put_rates,
    update_cash,
)


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
def alice_db(matrix_tenants, committing_runtime_session):
    """Alice's request-scoped session and portfolio, as a route sees them."""
    db = committing_runtime_session
    alice = matrix_tenants.alice
    set_rls_context(db, alice.user_id, alice.workspace_id)
    portfolio = db.scalars(select(Portfolio).where(Portfolio.id == alice.portfolio_id)).one()
    return db, portfolio


def _body(amount: float) -> CashCreate:
    return CashCreate(type="deposit", amount=amount, currency="usd", date=date(2026, 9, 1), note="runtime")


def test_create_cash_returns_the_new_row_under_the_runtime_role(alice_db, postgres_engine):
    db, portfolio = alice_db

    with patch("routers.cash.fetch_fx_to_czk", return_value=20.0):
        row = create_cash(_body(123.0), db=db, portfolio=portfolio)

    assert row.amount == 123.0 and row.currency == "USD" and row.fx_to_czk == 20.0
    with Session(postgres_engine) as owner:
        assert owner.scalars(
            select(Transaction.amount).where(Transaction.public_id == row.id)
        ).one() == 123.0


def test_update_cash_returns_the_updated_row_under_the_runtime_role(
    alice_db, matrix_tenants, postgres_engine,
):
    db, portfolio = alice_db
    cash_id = UUID(matrix_tenants.ids["alice_cash"])

    with patch("routers.cash.fetch_fx_to_czk", return_value=20.0):
        row = update_cash(cash_id, _body(456.0), db=db, portfolio=portfolio)

    assert row.id == cash_id and row.amount == 456.0
    with Session(postgres_engine) as owner:
        assert owner.scalars(
            select(Transaction.amount).where(Transaction.public_id == cash_id)
        ).one() == 456.0


def test_put_rates_returns_the_saved_rates_under_the_runtime_role(
    alice_db, matrix_tenants, postgres_engine,
):
    db, portfolio = alice_db

    rates = put_rates(
        RatesPayload(rates=[RateItem(currency="eur", annual_rate=0.03, enabled=True)]),
        db=db, portfolio=portfolio,
    )

    assert {(r.currency, r.annual_rate, r.enabled) for r in rates} >= {("EUR", 0.03, True)}
    with Session(postgres_engine) as owner:
        assert owner.scalars(
            select(CashInterestRate.annual_rate).where(
                CashInterestRate.portfolio_id == matrix_tenants.alice.portfolio_id,
                CashInterestRate.currency == "EUR",
            )
        ).one() == 0.03
