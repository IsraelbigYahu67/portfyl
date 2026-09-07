from __future__ import annotations

from fastapi import HTTPException
import pytest

from models import Portfolio, Transaction
from routers.portfolios import create_demo_portfolio


def test_demo_creation_is_atomic_scoped_and_clearly_labelled(
    db_session,
    request_context,
):
    result = create_demo_portfolio(context=request_context, db=db_session)

    portfolio = db_session.query(Portfolio).one()
    transactions = db_session.query(Transaction).order_by(Transaction.date, Transaction.id).all()
    assert result == {
        "id": str(portfolio.public_id),
        "name": "Portfyl demo",
        "color": "#6D7048",
        "is_default": True,
        "created_at": portfolio.created_at.isoformat(),
        "transaction_count": 6,
        "demo": True,
    }
    assert len(transactions) == 6
    assert {row.workspace_id for row in transactions} == {request_context.workspace.id}
    assert {row.portfolio_id for row in transactions} == {portfolio.id}
    assert {row.source for row in transactions} == {"demo"}
    assert {row.type for row in transactions} >= {"deposit", "buy", "dividend", "sell"}


def test_demo_creation_refuses_non_empty_workspace(
    db_session,
    request_context,
    default_portfolio,
):
    with pytest.raises(HTTPException) as exc_info:
        create_demo_portfolio(context=request_context, db=db_session)

    assert exc_info.value.status_code == 409
    assert "empty workspace" in str(exc_info.value.detail).lower()
    assert db_session.query(Portfolio).count() == 1
    assert db_session.query(Transaction).count() == 0


def test_demo_route_requires_csrf():
    from routers.portfolios import router
    from tenancy import require_csrf

    route = next(
        route for route in router.routes
        if route.path == "/portfolios/demo" and "POST" in route.methods
    )
    assert require_csrf in {dependency.call for dependency in route.dependant.dependencies}
