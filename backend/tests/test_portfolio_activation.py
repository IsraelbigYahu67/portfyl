from __future__ import annotations

import json
from datetime import date
from uuid import UUID

from fastapi import HTTPException
import pytest

from models import AuditLog, Portfolio, Transaction, Workspace, WorkspaceSetting
from portfolio_activation import (
    PENDING_PORTFOLIO_SETTING_KEY,
    clear_pending_portfolio,
    pending_portfolio,
    set_pending_portfolio,
)
from routers.portfolios import (
    activate_pending_import_portfolio,
    create_pending_import_portfolio,
    list_portfolios,
)
from tenancy import RequestContextError


def test_pending_import_creation_is_idempotent_and_serialized(db_session, request_context):
    first = create_pending_import_portfolio(context=request_context, db=db_session)
    second = create_pending_import_portfolio(context=request_context, db=db_session)

    assert first["id"] == second["id"]
    assert first["activation_state"] == "pending_import"
    assert db_session.query(Portfolio).count() == 1
    assert list_portfolios(context=request_context, db=db_session)[0]["activation_state"] == "pending_import"
    marker = db_session.query(WorkspaceSetting).filter_by(key=PENDING_PORTFOLIO_SETTING_KEY).one()
    assert json.loads(marker.value) == {
        "kind": "csv_import",
        "portfolio_id": first["id"],
        "schema_version": 1,
    }


def test_pending_name_uses_a_workspace_unique_suffix(db_session, request_context):
    db_session.add(Portfolio(workspace_id=request_context.workspace.id, name="My portfolio"))
    db_session.commit()

    result = create_pending_import_portfolio(context=request_context, db=db_session)

    assert result["name"] == "My portfolio 2"


def test_pending_creation_counts_toward_portfolio_capacity(
    db_session,
    request_context,
    monkeypatch,
):
    db_session.add(Portfolio(workspace_id=request_context.workspace.id, name="Existing"))
    db_session.commit()

    def deny_at_limit(_entitlements, resource, *, used, increase):
        assert (resource, used, increase) == ("portfolios", 1, 1)
        raise HTTPException(status_code=403, detail="quota_exceeded")

    monkeypatch.setattr("routers.portfolios.ensure_count_limit", deny_at_limit)
    with pytest.raises(HTTPException) as exc_info:
        create_pending_import_portfolio(context=request_context, db=db_session)
    assert exc_info.value.status_code == 403
    assert db_session.query(Portfolio).count() == 1


def test_explicit_blank_activation_clears_marker_and_records_audit(db_session, request_context):
    created = create_pending_import_portfolio(context=request_context, db=db_session)

    result = activate_pending_import_portfolio(
        portfolio_id=UUID(created["id"]),
        context=request_context,
        db=db_session,
    )

    assert result["activation_state"] == "active"
    assert pending_portfolio(db_session, request_context.workspace.id) is None
    audit = db_session.query(AuditLog).filter_by(action="onboarding.portfolio.activated").one()
    assert audit.target_id == created["id"]
    assert audit.event_metadata == {"kind": "blank"}


def test_activation_requires_the_marked_empty_portfolio(db_session, request_context):
    created = create_pending_import_portfolio(context=request_context, db=db_session)
    portfolio = db_session.query(Portfolio).filter_by(public_id=UUID(created["id"])).one()
    db_session.add(Transaction(
        workspace_id=portfolio.workspace_id,
        portfolio_id=portfolio.id,
        ticker="AAPL",
        name="Apple",
        type="buy",
        shares=1,
        price=100,
        currency="USD",
        date=date(2026, 1, 2),
    ))
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        activate_pending_import_portfolio(
            portfolio_id=portfolio.public_id,
            context=request_context,
            db=db_session,
        )
    assert exc_info.value.status_code == 409
    assert pending_portfolio(
        db_session,
        request_context.workspace.id,
        require_empty=False,
    ).id == portfolio.id


def test_unrelated_portfolio_cannot_clear_marker(db_session, request_context):
    pending = Portfolio(workspace_id=request_context.workspace.id, name="Pending")
    other = Portfolio(workspace_id=request_context.workspace.id, name="Other")
    db_session.add_all([pending, other])
    db_session.flush()
    set_pending_portfolio(db_session, pending)

    assert clear_pending_portfolio(db_session, other) is False
    assert pending_portfolio(db_session, request_context.workspace.id).id == pending.id


def test_foreign_pending_portfolio_is_not_addressable(db_session, request_context):
    foreign_workspace = Workspace(name="Foreign")
    db_session.add(foreign_workspace)
    db_session.flush()
    foreign = Portfolio(workspace_id=foreign_workspace.id, name="Foreign pending")
    db_session.add(foreign)
    db_session.flush()
    set_pending_portfolio(db_session, foreign)
    db_session.commit()

    with pytest.raises(RequestContextError) as exc_info:
        activate_pending_import_portfolio(
            portfolio_id=foreign.public_id,
            context=request_context,
            db=db_session,
        )
    assert exc_info.value.status_code == 404


def test_pending_routes_require_csrf():
    from routers.portfolios import router
    from tenancy import require_csrf

    for path in ("/portfolios/pending-import", "/portfolios/{portfolio_id}/activate"):
        route = next(route for route in router.routes if route.path == path and "POST" in route.methods)
        assert require_csrf in {dependency.call for dependency in route.dependant.dependencies}
