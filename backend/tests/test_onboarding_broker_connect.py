"""Contract: connecting a broker into the onboarding pending portfolio.

The onboarding connect step creates a pending-import portfolio, connects a
broker into it, syncs and then activates it. These tests pin the existing
backend behaviour that flow relies on; no backend change is expected.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException

from models import BrokerConnection, Portfolio, Transaction
from portfolio_activation import pending_portfolio
from routers.broker import connect
from routers.portfolios import (
    activate_pending_import_portfolio,
    create_pending_import_portfolio,
    list_portfolios,
)


def _account_response(account_id=101):
    response = MagicMock(status_code=200)
    response.json.return_value = {"id": account_id}
    return response


def _pending(db_session, request_context) -> Portfolio:
    created = create_pending_import_portfolio(context=request_context, db=db_session)
    assert created["activation_state"] == "pending_import"
    return db_session.query(Portfolio).filter_by(public_id=UUID(created["id"])).one()


def _connect_t212(db_session, request_context, portfolio):
    with patch("routers.broker.httpx.get", return_value=_account_response()):
        return connect(
            payload={"api_key": "valid-key-value-1234567890", "api_secret": "secret"},
            db=db_session,
            portfolio=portfolio,
            _context=request_context,
        )


def test_t212_connect_accepts_empty_pending_portfolio(db_session, request_context):
    pending = _pending(db_session, request_context)
    name = pending.name

    result = _connect_t212(db_session, request_context, pending)

    assert result["ok"] is True
    connection = db_session.query(BrokerConnection).one()
    assert connection.portfolio_id == pending.id
    still_pending = pending_portfolio(db_session, request_context.workspace.id)
    assert still_pending is not None and still_pending.id == pending.id
    db_session.refresh(pending)
    assert pending.name == name == "My portfolio"
    assert db_session.query(Portfolio).count() == 1


def test_activate_after_connect_without_transactions_succeeds(db_session, request_context):
    pending = _pending(db_session, request_context)
    _connect_t212(db_session, request_context, pending)

    result = activate_pending_import_portfolio(
        portfolio_id=pending.public_id,
        context=request_context,
        db=db_session,
    )

    assert result["activation_state"] == "active"
    assert pending_portfolio(
        db_session,
        request_context.workspace.id,
        require_empty=False,
    ) is None


def test_activate_after_broker_rows_conflicts_and_listing_reports_active(
    db_session, request_context
):
    pending = _pending(db_session, request_context)
    db_session.add(Transaction(
        workspace_id=pending.workspace_id,
        portfolio_id=pending.id,
        ticker="AAPL",
        name="Apple",
        type="buy",
        shares=1,
        price=100,
        currency="USD",
        date=date(2026, 1, 2),
        source="ibkr",
    ))
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        activate_pending_import_portfolio(
            portfolio_id=pending.public_id,
            context=request_context,
            db=db_session,
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Only an empty pending portfolio can be activated"

    listed = list_portfolios(context=request_context, db=db_session)
    entry = next(row for row in listed if row["id"] == str(pending.public_id))
    assert entry["activation_state"] == "active"
