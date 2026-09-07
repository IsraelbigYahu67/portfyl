"""Workspace data portability export."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from fastapi import FastAPI

from models import (
    BrokerConnection,
    Membership,
    Portfolio,
    PriceAlert,
    Transaction,
    Watchlist,
    WatchlistItem,
    Workspace,
)
from routers.account import export_workspace_data
from routers.settings import router as settings_router
from workspace_export import build_workspace_export


EXPORTED_AT = datetime(2026, 9, 7, 12, 30, tzinfo=timezone.utc)


def _seed_export_rows(db, context):
    portfolio = Portfolio(
        public_id=UUID("10000000-0000-4000-8000-000000000001"),
        workspace_id=context.workspace.id,
        name="Retirement",
        color="#22c55e",
        is_default=True,
    )
    watchlist = Watchlist(
        public_id=UUID("20000000-0000-4000-8000-000000000001"),
        workspace_id=context.workspace.id,
        name="Quality",
        color="#38bdf8",
    )
    db.add_all([portfolio, watchlist])
    db.flush()
    transaction = Transaction(
        public_id=UUID("30000000-0000-4000-8000-000000000001"),
        workspace_id=context.workspace.id,
        portfolio_id=portfolio.id,
        ticker="MSFT",
        name="Microsoft",
        type="buy",
        shares=2,
        price=400,
        amount=800,
        currency="USD",
        date=date(2026, 1, 2),
        notes="portable note",
        source="manual",
        fx_to_czk=23.1,
    )
    item = WatchlistItem(
        public_id=UUID("40000000-0000-4000-8000-000000000001"),
        workspace_id=context.workspace.id,
        watchlist_id=watchlist.id,
        ticker="NVDA",
        note="watch note",
    )
    alert = PriceAlert(
        public_id=UUID("50000000-0000-4000-8000-000000000001"),
        workspace_id=context.workspace.id,
        portfolio_id=portfolio.id,
        ticker="MSFT",
        direction="above",
        target_price=500,
        note="alert note",
    )
    connection = BrokerConnection(
        public_id=UUID("60000000-0000-4000-8000-000000000001"),
        workspace_id=context.workspace.id,
        portfolio_id=portfolio.id,
        broker="t212",
        api_key="TOP-SECRET-KEY",
        api_secret="TOP-SECRET-VALUE",
        environment="live",
        auto_sync=True,
        needs_attention=True,
        last_error="Authorization: Bearer TOP-SECRET-ERROR",
    )
    db.add_all([transaction, item, alert, connection])

    other_workspace = Workspace(id=uuid4(), name="Other tenant")
    db.add(other_workspace)
    db.flush()
    other_portfolio = Portfolio(
        workspace_id=other_workspace.id,
        name="Must not leak",
        is_default=True,
    )
    db.add(other_portfolio)
    db.flush()
    db.add(Transaction(
        workspace_id=other_workspace.id,
        portfolio_id=other_portfolio.id,
        ticker="LEAK",
        name="Cross tenant",
        type="buy",
        shares=1,
        price=1,
        currency="USD",
        date=date(2026, 1, 1),
    ))
    db.flush()
    return portfolio


def test_export_contains_portable_workspace_data_without_cross_tenant_rows(
    db_session,
    request_context,
):
    _seed_export_rows(db_session, request_context)

    payload = build_workspace_export(
        db_session,
        request_context,
        exported_at=EXPORTED_AT,
    )

    assert payload["schema_version"] == 1
    assert payload["exported_at"] == "2026-09-07T12:30:00+00:00"
    assert payload["workspace"]["id"] == str(request_context.workspace.public_id)
    assert payload["membership"] == {
        "role": "owner",
        "status": "active",
        "created_at": request_context.membership.created_at.isoformat(),
    }
    assert [row["name"] for row in payload["portfolios"]] == ["Retirement"]
    assert payload["transactions"][0]["portfolio_id"] == payload["portfolios"][0]["id"]
    assert payload["transactions"][0]["notes"] == "portable note"
    assert payload["watchlists"][0]["items"][0]["ticker"] == "NVDA"
    assert payload["alerts"][0]["portfolio_id"] == payload["portfolios"][0]["id"]
    assert payload["broker_connections"][0]["portfolio_id"] == payload["portfolios"][0]["id"]
    assert "Must not leak" not in json.dumps(payload)
    assert "LEAK" not in json.dumps(payload)


def test_export_is_allow_listed_and_never_serializes_broker_secrets(
    db_session,
    request_context,
):
    _seed_export_rows(db_session, request_context)

    payload = build_workspace_export(
        db_session,
        request_context,
        exported_at=EXPORTED_AT,
    )
    encoded = json.dumps(payload)
    broker = payload["broker_connections"][0]

    assert set(broker) == {
        "id",
        "portfolio_id",
        "broker",
        "environment",
        "auto_sync",
        "last_synced_at",
        "csv_covered_through",
        "needs_attention",
        "consecutive_failures",
        "created_at",
    }
    for forbidden in (
        "TOP-SECRET-KEY",
        "TOP-SECRET-VALUE",
        "TOP-SECRET-ERROR",
        "api_key",
        "api_secret",
        "ciphertext",
        "key_version",
        "last_error",
        "workspace_id",
    ):
        assert forbidden not in encoded


def test_export_orders_rows_deterministically(db_session, request_context):
    _seed_export_rows(db_session, request_context)
    earlier = Portfolio(
        public_id=UUID("10000000-0000-4000-8000-000000000000"),
        workspace_id=request_context.workspace.id,
        name="Earlier",
        is_default=False,
        created_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    db_session.add(earlier)
    db_session.flush()

    payload = build_workspace_export(
        db_session,
        request_context,
        exported_at=EXPORTED_AT,
    )

    assert [row["name"] for row in payload["portfolios"]] == ["Earlier", "Retirement"]


def test_export_endpoint_returns_named_json_attachment(db_session, request_context):
    _seed_export_rows(db_session, request_context)

    response = export_workspace_data(db_session, request_context)
    payload = json.loads(response.body)

    assert response.media_type == "application/json"
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="portfyl-workspace-'
    )
    assert response.headers["content-disposition"].endswith('.json"')
    assert payload["workspace"]["id"] == str(request_context.workspace.public_id)


def test_account_export_router_is_mounted_below_settings():
    app = FastAPI()
    app.include_router(settings_router, prefix="/api")
    paths = set(app.openapi()["paths"])
    assert "/api/settings/account/export" in paths
