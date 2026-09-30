"""Workspace data portability export."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from uuid import UUID, uuid4

from fastapi import FastAPI

from models import (
    Benchmark,
    BenchmarkComponent,
    BrokerBalance,
    BrokerConnection,
    BrokerCorporateAction,
    BrokerCorporateActionApplication,
    CashInterestRate,
    DiscordWebhook,
    DividendNotification,
    Membership,
    OptionsTrade,
    Portfolio,
    PolymarketPosition,
    PriceAlert,
    TradeNote,
    Transaction,
    UserSetting,
    Watchlist,
    WatchlistItem,
    Workspace,
    WorkspaceSetting,
)
from routers.account import export_workspace_data
from routers.settings import router as settings_router
from tests.helpers import make_txn
from workspace_export import build_workspace_export


EXPORTED_AT = datetime(2026, 9, 7, 12, 30, tzinfo=timezone.utc)


def _seed_export_rows(db, context):
    portfolio = Portfolio(
        public_id=UUID("10000000-0000-4000-8000-000000000001"),
        workspace_id=context.workspace.id,
        name="Retirement",
        color="#22c55e",
        is_default=True,
        t212_account_fingerprint="f" * 64,
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
        source="t212_api",
        source_event_id="fill-123",
        source_event_stream="orders",
        source_account_fingerprint="f" * 64,
        source_credential_generation=2,
        source_instrument_id="MSFT_US_EQ",
        source_fill_type="TRADE",
        executed_at=datetime(2026, 1, 2, 15, 30, tzinfo=timezone.utc),
        source_payload_hash="a" * 64,
        source_mapper_version="t212_finalize_v1",
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
        account_fingerprint="f" * 64,
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
    return portfolio, transaction


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

    assert payload["schema_version"] == 4
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
    assert payload["transactions"][0]["source_event_id"] == "fill-123"
    assert payload["transactions"][0]["source_account_fingerprint"] == "f" * 64
    assert payload["portfolios"][0]["t212_account_fingerprint"] == "f" * 64
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
        "positions_snapshot_at",
        "account_fingerprint",
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


def test_export_v2_includes_remaining_user_data_but_not_secrets_or_internal_state(
    db_session,
    request_context,
):
    portfolio, transaction = _seed_export_rows(db_session, request_context)
    benchmark = Benchmark(
        public_id=UUID("70000000-0000-4000-8000-000000000001"),
        workspace_id=request_context.workspace.id,
        portfolio_id=portfolio.id,
        name="Balanced",
        kind="custom",
        is_default=True,
        is_preset=False,
    )
    db_session.add(benchmark)
    db_session.flush()
    db_session.add_all([
        BenchmarkComponent(
            public_id=UUID("71000000-0000-4000-8000-000000000001"),
            workspace_id=request_context.workspace.id,
            benchmark_id=benchmark.id,
            ticker="SPY",
            weight=0.6,
        ),
        OptionsTrade(
            public_id=UUID("72000000-0000-4000-8000-000000000001"),
            workspace_id=request_context.workspace.id,
            portfolio_id=portfolio.id,
            underlying="MSFT",
            strike=450,
            expiry=date(2026, 12, 18),
            put_call="C",
            quantity=1,
            open_price=8.5,
            open_date=date(2026, 1, 10),
            status="open",
            notes="covered call",
        ),
        BrokerBalance(
            public_id=UUID("73000000-0000-4000-8000-000000000001"),
            workspace_id=request_context.workspace.id,
            portfolio_id=portfolio.id,
            broker="ibkr",
            base_currency="USD",
            cash=500,
            stock=2000,
            options_value=120,
            net_liquidation=2620,
            cash_by_currency='{"USD": 500}',
            as_of=date(2026, 9, 6),
        ),
        PolymarketPosition(
            public_id=UUID("74000000-0000-4000-8000-000000000001"),
            workspace_id=request_context.workspace.id,
            portfolio_id=portfolio.id,
            condition_id="condition-1",
            asset_id="asset-1",
            market_slug="example-market",
            question="Will the example happen?",
            outcome="Yes",
            size=10,
            avg_price=0.4,
            current_price=0.5,
            status="open",
        ),
        DiscordWebhook(
            public_id=UUID("75000000-0000-4000-8000-000000000001"),
            workspace_id=request_context.workspace.id,
            portfolio_id=portfolio.id,
            webhook_url="https://discord.com/api/webhooks/123/NEVER-EXPORT",
            notify_trades=True,
            notify_dividends=False,
            notify_milestones=True,
        ),
        TradeNote(
            public_id=UUID("76000000-0000-4000-8000-000000000001"),
            workspace_id=request_context.workspace.id,
            transaction_id=transaction.id,
            content="Why I bought",
            tags="quality,long-term",
            sentiment="bullish",
        ),
        CashInterestRate(
            public_id=UUID("77000000-0000-4000-8000-000000000001"),
            workspace_id=request_context.workspace.id,
            portfolio_id=portfolio.id,
            currency="USD",
            annual_rate=0.03,
            enabled=True,
            start_date=date(2026, 1, 1),
        ),
        DividendNotification(
            public_id=UUID("78000000-0000-4000-8000-000000000001"),
            workspace_id=request_context.workspace.id,
            portfolio_id=portfolio.id,
            ticker="MSFT",
            ex_date=date(2026, 8, 20),
        ),
        WorkspaceSetting(
            workspace_id=request_context.workspace.id,
            key="broker_sync_mode",
            value="daily",
        ),
        WorkspaceSetting(
            workspace_id=request_context.workspace.id,
            key="privacy.workspace_deletion",
            value='{"requested_by_user_id":"INTERNAL"}',
        ),
        WorkspaceSetting(
            workspace_id=request_context.workspace.id,
            key="onboarding_pending_portfolio",
            value='{"schema_version":1,"portfolio_id":"internal","kind":"csv_import"}',
        ),
        UserSetting(
            user_id=request_context.user.id,
            key="deepseek_model",
            value="deepseek-reasoner",
        ),
        UserSetting(
            user_id=request_context.user.id,
            key="deepseek_api_key",
            value="encrypted:NEVER-EXPORT-AI-KEY",
        ),
    ])
    other_portfolio = db_session.query(Portfolio).filter_by(name="Must not leak").one()
    db_session.add(OptionsTrade(
        workspace_id=other_portfolio.workspace_id,
        portfolio_id=other_portfolio.id,
        underlying="CROSS-TENANT-OPTION",
        strike=1,
        expiry=date(2026, 12, 18),
        put_call="P",
        quantity=1,
        open_price=1,
        open_date=date(2026, 1, 10),
        status="open",
    ))
    db_session.flush()

    payload = build_workspace_export(
        db_session,
        request_context,
        exported_at=EXPORTED_AT,
    )
    encoded = json.dumps(payload)

    assert payload["benchmarks"][0]["components"] == [{
        "id": "71000000-0000-4000-8000-000000000001",
        "benchmark_id": "70000000-0000-4000-8000-000000000001",
        "ticker": "SPY",
        "weight": 0.6,
    }]
    assert payload["options_trades"][0]["notes"] == "covered call"
    assert payload["broker_balances"][0]["cash_by_currency"] == {"USD": 500}
    assert payload["polymarket_positions"][0]["question"] == "Will the example happen?"
    assert payload["notification_preferences"][0]["notify_dividends"] is False
    assert payload["trade_notes"][0]["transaction_id"] == str(transaction.public_id)
    assert payload["cash_interest_rates"][0]["annual_rate"] == 0.03
    assert payload["dividend_notifications"][0]["ticker"] == "MSFT"
    assert payload["workspace_preferences"] == {"broker_sync_mode": "daily"}
    assert payload["user_preferences"] == {"assistant_model": "deepseek-reasoner"}

    for forbidden in (
        "NEVER-EXPORT",
        "NEVER-EXPORT-AI-KEY",
        "webhook_url",
        "deepseek_api_key",
        "privacy.workspace_deletion",
        "onboarding_pending_portfolio",
        "requested_by_user_id",
        "workspace_id",
        "transaction_id\": 1",
        "CROSS-TENANT-OPTION",
    ):
        assert forbidden not in encoded


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


def test_export_includes_corporate_actions_and_applications(db_session, request_context):
    portfolio, _ = _seed_export_rows(db_session, request_context)
    txn = make_txn(
        "NVDA", "buy", 90, 120, portfolio_id=portfolio.id, source="t212_api",
        workspace_id=request_context.workspace.id,
    )
    db_session.add(txn)
    db_session.flush()
    action = BrokerCorporateAction(
        workspace_id=request_context.workspace.id, portfolio_id=portfolio.id,
        broker="trading212", account_fingerprint="f" * 64, provider_instrument_id="NVDA_US_EQ",
        ticker="NVDA", action_type="STOCK_SPLIT",
        effective_at=datetime(2024, 6, 10, tzinfo=timezone.utc), provider_event_key="fill:a|fill:b",
        ratio_numerator=10, ratio_denominator=1, representation="api_normalized",
    )
    db_session.add(action)
    db_session.flush()
    db_session.add(BrokerCorporateActionApplication(
        workspace_id=request_context.workspace.id, action_id=action.id, transaction_id=txn.id,
        shares_before=9, price_before=1200, shares_after=90, price_after=120,
    ))
    db_session.commit()

    payload = build_workspace_export(db_session, request_context, exported_at=EXPORTED_AT)

    assert payload["schema_version"] == 4
    [a] = payload["broker_corporate_actions"]
    assert a["action_type"] == "STOCK_SPLIT"
    assert float(a["ratio_numerator"]) == 10.0
    assert a["portfolio_id"] == payload["portfolios"][0]["id"]
    assert a["account_fingerprint"] == "f" * 64
    [ap] = payload["broker_corporate_action_applications"]
    assert ap["shares_after"] == 90
    assert ap["action_id"] == a["id"]
