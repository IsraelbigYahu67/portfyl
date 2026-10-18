"""Versioned, allow-listed workspace data portability export."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (
    AllocationTarget,
    Benchmark,
    BenchmarkComponent,
    BrokerBalance,
    BrokerConnection,
    BrokerCorporateAction,
    BrokerCorporateActionApplication,
    BrokerPosition,
    CashInterestRate,
    DiscordWebhook,
    DividendNotification,
    OptionsTrade,
    Portfolio,
    PolymarketPosition,
    PriceAlert,
    TradeNote,
    Transaction,
    Watchlist,
    WatchlistItem,
    WorkspaceSetting,
)
from tenancy import RequestContext


EXPORT_SCHEMA_VERSION = 6

_WORKSPACE_PREFERENCE_KEYS = (
    "broker_sync_daily_time",
    "broker_sync_interval_hours",
    "broker_sync_mode",
)


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _json_object(value: str | None) -> dict[str, Any]:
    """Decode a stored JSON object without making malformed legacy state fatal."""
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def build_workspace_export(
    db: Session,
    context: RequestContext,
    *,
    exported_at: datetime | None = None,
) -> dict[str, Any]:
    """Build a portable JSON object for exactly one authorized workspace.

    Every model is serialized through an explicit field allow-list. In
    particular, this function never reads BrokerConnection's decrypting
    properties or its ciphertext/key-version columns.
    """
    workspace_id = context.workspace.id
    exported_at = exported_at or datetime.now(timezone.utc)

    portfolios = db.scalars(
        select(Portfolio)
        .where(Portfolio.workspace_id == workspace_id)
        .order_by(Portfolio.created_at, Portfolio.id)
    ).all()
    portfolio_public_ids = {
        portfolio.id: str(portfolio.public_id) for portfolio in portfolios
    }

    transactions = db.scalars(
        select(Transaction)
        .where(Transaction.workspace_id == workspace_id)
        .order_by(Transaction.date, Transaction.created_at, Transaction.id)
    ).all()
    transactions_by_id = {transaction.id: transaction for transaction in transactions}
    watchlists = db.scalars(
        select(Watchlist)
        .where(Watchlist.workspace_id == workspace_id)
        .order_by(Watchlist.created_at, Watchlist.id)
    ).all()
    watchlist_public_ids = {
        watchlist.id: str(watchlist.public_id) for watchlist in watchlists
    }
    watchlist_items = db.scalars(
        select(WatchlistItem)
        .where(WatchlistItem.workspace_id == workspace_id)
        .order_by(
            WatchlistItem.watchlist_id,
            WatchlistItem.created_at,
            WatchlistItem.id,
        )
    ).all()
    items_by_watchlist: dict[int, list[dict[str, Any]]] = {
        watchlist.id: [] for watchlist in watchlists
    }
    for item in watchlist_items:
        if item.watchlist_id in items_by_watchlist:
            items_by_watchlist[item.watchlist_id].append({
                "id": str(item.public_id),
                "watchlist_id": watchlist_public_ids[item.watchlist_id],
                "ticker": item.ticker,
                "note": item.note,
                "created_at": _iso(item.created_at),
            })

    alerts = db.scalars(
        select(PriceAlert)
        .where(PriceAlert.workspace_id == workspace_id)
        .order_by(PriceAlert.created_at, PriceAlert.id)
    ).all()
    connections = db.scalars(
        select(BrokerConnection)
        .where(BrokerConnection.workspace_id == workspace_id)
        .order_by(BrokerConnection.created_at, BrokerConnection.id)
    ).all()
    benchmarks = db.scalars(
        select(Benchmark)
        .where(Benchmark.workspace_id == workspace_id)
        .order_by(Benchmark.created_at, Benchmark.id)
    ).all()
    benchmark_public_ids = {
        benchmark.id: str(benchmark.public_id) for benchmark in benchmarks
    }
    benchmark_components = db.scalars(
        select(BenchmarkComponent)
        .where(BenchmarkComponent.workspace_id == workspace_id)
        .order_by(
            BenchmarkComponent.benchmark_id,
            BenchmarkComponent.ticker,
            BenchmarkComponent.id,
        )
    ).all()
    components_by_benchmark: dict[int, list[dict[str, Any]]] = {
        benchmark.id: [] for benchmark in benchmarks
    }
    for component in benchmark_components:
        benchmark_public_id = benchmark_public_ids.get(component.benchmark_id)
        if benchmark_public_id is not None:
            components_by_benchmark[component.benchmark_id].append({
                "id": str(component.public_id),
                "benchmark_id": benchmark_public_id,
                "ticker": component.ticker,
                "weight": component.weight,
            })

    options_trades = db.scalars(
        select(OptionsTrade)
        .where(OptionsTrade.workspace_id == workspace_id)
        .order_by(OptionsTrade.open_date, OptionsTrade.created_at, OptionsTrade.id)
    ).all()
    broker_balances = db.scalars(
        select(BrokerBalance)
        .where(BrokerBalance.workspace_id == workspace_id)
        .order_by(BrokerBalance.updated_at, BrokerBalance.id)
    ).all()
    broker_positions = db.scalars(
        select(BrokerPosition)
        .where(BrokerPosition.workspace_id == workspace_id)
        .order_by(BrokerPosition.updated_at, BrokerPosition.id)
    ).all()
    corporate_actions = db.scalars(
        select(BrokerCorporateAction)
        .where(BrokerCorporateAction.workspace_id == workspace_id)
        .order_by(BrokerCorporateAction.effective_at, BrokerCorporateAction.id)
    ).all()
    corporate_action_public_ids = {a.id: str(a.public_id) for a in corporate_actions}
    corporate_action_applications = db.scalars(
        select(BrokerCorporateActionApplication)
        .where(BrokerCorporateActionApplication.workspace_id == workspace_id)
        .order_by(BrokerCorporateActionApplication.id)
    ).all()
    polymarket_positions = db.scalars(
        select(PolymarketPosition)
        .where(PolymarketPosition.workspace_id == workspace_id)
        .order_by(PolymarketPosition.created_at, PolymarketPosition.id)
    ).all()
    notification_preferences = db.scalars(
        select(DiscordWebhook)
        .where(DiscordWebhook.workspace_id == workspace_id)
        .order_by(DiscordWebhook.created_at, DiscordWebhook.id)
    ).all()
    trade_notes = db.scalars(
        select(TradeNote)
        .where(TradeNote.workspace_id == workspace_id)
        .order_by(TradeNote.updated_at, TradeNote.id)
    ).all()
    cash_interest_rates = db.scalars(
        select(CashInterestRate)
        .where(CashInterestRate.workspace_id == workspace_id)
        .order_by(
            CashInterestRate.portfolio_id,
            CashInterestRate.currency,
            CashInterestRate.id,
        )
    ).all()
    allocation_targets = db.scalars(
        select(AllocationTarget)
        .where(AllocationTarget.workspace_id == workspace_id)
        .order_by(
            AllocationTarget.portfolio_id,
            AllocationTarget.display_order,
            AllocationTarget.id,
        )
    ).all()
    dividend_notifications = db.scalars(
        select(DividendNotification)
        .where(DividendNotification.workspace_id == workspace_id)
        .order_by(
            DividendNotification.ex_date,
            DividendNotification.sent_at,
            DividendNotification.id,
        )
    ).all()
    workspace_preferences = db.scalars(
        select(WorkspaceSetting)
        .where(
            WorkspaceSetting.workspace_id == workspace_id,
            WorkspaceSetting.key.in_(_WORKSPACE_PREFERENCE_KEYS),
        )
        .order_by(WorkspaceSetting.key, WorkspaceSetting.id)
    ).all()

    return {
        "schema_version": EXPORT_SCHEMA_VERSION,
        "exported_at": _iso(exported_at),
        "workspace": {
            "id": str(context.workspace.public_id),
            "name": context.workspace.name,
            "created_at": _iso(context.workspace.created_at),
            "updated_at": _iso(context.workspace.updated_at),
        },
        "membership": {
            "role": context.membership.role,
            "status": context.membership.status,
            "created_at": _iso(context.membership.created_at),
        },
        "portfolios": [
            {
                "id": str(portfolio.public_id),
                "name": portfolio.name,
                "color": portfolio.color,
                "is_default": bool(portfolio.is_default),
                "csv_covered_through": _iso(portfolio.t212_csv_covered_through),
                "t212_account_fingerprint": portfolio.t212_account_fingerprint,
                "created_at": _iso(portfolio.created_at),
            }
            for portfolio in portfolios
        ],
        "transactions": [
            {
                "id": str(transaction.public_id),
                "portfolio_id": portfolio_public_ids[transaction.portfolio_id],
                "ticker": transaction.ticker,
                "name": transaction.name,
                "type": transaction.type,
                "shares": transaction.shares,
                "price": transaction.price,
                "amount": transaction.amount,
                "currency": transaction.currency,
                "cash_amount": transaction.cash_amount,
                "cash_currency": transaction.cash_currency,
                "date": _iso(transaction.date),
                "notes": transaction.notes,
                "source": transaction.source,
                "source_event_id": transaction.source_event_id,
                "source_event_stream": transaction.source_event_stream,
                "source_account_fingerprint": transaction.source_account_fingerprint,
                "source_credential_generation": transaction.source_credential_generation,
                "source_instrument_id": transaction.source_instrument_id,
                "source_fill_type": transaction.source_fill_type,
                "executed_at": _iso(transaction.executed_at),
                "source_payload_hash": transaction.source_payload_hash,
                "source_mapper_version": transaction.source_mapper_version,
                "fx_to_czk": transaction.fx_to_czk,
                "created_at": _iso(transaction.created_at),
            }
            for transaction in transactions
            if transaction.portfolio_id in portfolio_public_ids
        ],
        "watchlists": [
            {
                "id": str(watchlist.public_id),
                "name": watchlist.name,
                "color": watchlist.color,
                "created_at": _iso(watchlist.created_at),
                "items": items_by_watchlist[watchlist.id],
            }
            for watchlist in watchlists
        ],
        "alerts": [
            {
                "id": str(alert.public_id),
                "portfolio_id": portfolio_public_ids[alert.portfolio_id],
                "ticker": alert.ticker,
                "direction": alert.direction,
                "target_price": alert.target_price,
                "note": alert.note,
                "enabled": bool(alert.enabled),
                "status": alert.status,
                "last_triggered_at": _iso(alert.last_triggered_at),
                "triggered_price": alert.triggered_price,
                "created_at": _iso(alert.created_at),
            }
            for alert in alerts
            if alert.portfolio_id in portfolio_public_ids
        ],
        "broker_connections": [
            {
                "id": str(connection.public_id),
                "portfolio_id": portfolio_public_ids[connection.portfolio_id],
                "broker": connection.broker,
                "environment": connection.environment,
                "auto_sync": bool(connection.auto_sync),
                "last_synced_at": _iso(connection.last_synced_at),
                "positions_snapshot_at": _iso(connection.positions_snapshot_at),
                "account_fingerprint": connection.account_fingerprint,
                "csv_covered_through": _iso(connection.t212_csv_covered_through),
                "needs_attention": bool(connection.needs_attention),
                "consecutive_failures": connection.consecutive_failures,
                "created_at": _iso(connection.created_at),
            }
            for connection in connections
            if connection.portfolio_id in portfolio_public_ids
        ],
        "benchmarks": [
            {
                "id": str(benchmark.public_id),
                "portfolio_id": portfolio_public_ids[benchmark.portfolio_id],
                "name": benchmark.name,
                "kind": benchmark.kind,
                "ticker": benchmark.ticker,
                "is_default": bool(benchmark.is_default),
                "created_at": _iso(benchmark.created_at),
                "components": components_by_benchmark[benchmark.id],
            }
            for benchmark in benchmarks
            if benchmark.portfolio_id in portfolio_public_ids
        ],
        "options_trades": [
            {
                "id": str(trade.public_id),
                "portfolio_id": portfolio_public_ids[trade.portfolio_id],
                "underlying": trade.underlying,
                "strike": trade.strike,
                "expiry": _iso(trade.expiry),
                "put_call": trade.put_call,
                "quantity": trade.quantity,
                "open_price": trade.open_price,
                "close_price": trade.close_price,
                "open_date": _iso(trade.open_date),
                "close_date": _iso(trade.close_date),
                "status": trade.status,
                "multiplier": trade.multiplier,
                "currency": trade.currency,
                "pnl": trade.pnl,
                "commission": trade.commission,
                "source": trade.source,
                "fx_to_czk": trade.fx_to_czk,
                "notes": trade.notes,
                "created_at": _iso(trade.created_at),
            }
            for trade in options_trades
            if trade.portfolio_id in portfolio_public_ids
        ],
        "broker_balances": [
            {
                "id": str(balance.public_id),
                "portfolio_id": portfolio_public_ids[balance.portfolio_id],
                "broker": balance.broker,
                "base_currency": balance.base_currency,
                "cash": balance.cash,
                "stock": balance.stock,
                "options_value": balance.options_value,
                "net_liquidation": balance.net_liquidation,
                "cash_by_currency": _json_object(balance.cash_by_currency),
                "as_of": _iso(balance.as_of),
                "updated_at": _iso(balance.updated_at),
            }
            for balance in broker_balances
            if balance.portfolio_id in portfolio_public_ids
        ],
        "broker_positions": [
            {
                "id": str(position.public_id),
                "portfolio_id": portfolio_public_ids[position.portfolio_id],
                "broker": position.broker,
                "provider_ticker": position.provider_ticker,
                "ticker": position.ticker,
                "name": position.name,
                "currency": position.currency,
                "quantity": position.quantity,
                "pie_quantity": position.pie_quantity,
                "avg_price": position.avg_price,
                "current_price": position.current_price,
                "as_of": _iso(position.as_of),
                "updated_at": _iso(position.updated_at),
            }
            for position in broker_positions
            if position.portfolio_id in portfolio_public_ids
        ],
        "broker_corporate_actions": [
            {
                "id": str(action.public_id),
                "portfolio_id": portfolio_public_ids[action.portfolio_id],
                "broker": action.broker,
                "account_fingerprint": action.account_fingerprint,
                "provider_instrument_id": action.provider_instrument_id,
                "ticker": action.ticker,
                "action_type": action.action_type,
                "effective_at": _iso(action.effective_at),
                "provider_event_key": action.provider_event_key,
                "ratio_numerator": float(action.ratio_numerator),
                "ratio_denominator": float(action.ratio_denominator),
                "representation": action.representation,
                "created_at": _iso(action.created_at),
            }
            for action in corporate_actions
            if action.portfolio_id in portfolio_public_ids
        ],
        "broker_corporate_action_applications": [
            {
                "action_id": corporate_action_public_ids[application.action_id],
                "transaction_id": str(transactions_by_id[application.transaction_id].public_id),
                "shares_before": application.shares_before,
                "price_before": application.price_before,
                "shares_after": application.shares_after,
                "price_after": application.price_after,
                "applied_at": _iso(application.applied_at),
            }
            for application in corporate_action_applications
            if application.action_id in corporate_action_public_ids
            and application.transaction_id in transactions_by_id
        ],
        "polymarket_positions": [
            {
                "id": str(position.public_id),
                "portfolio_id": portfolio_public_ids[position.portfolio_id],
                "condition_id": position.condition_id,
                "asset_id": position.asset_id,
                "market_slug": position.market_slug,
                "question": position.question,
                "outcome": position.outcome,
                "size": position.size,
                "avg_price": position.avg_price,
                "current_price": position.current_price,
                "resolved_price": position.resolved_price,
                "status": position.status,
                "pnl": position.pnl,
                "source": position.source,
                "created_at": _iso(position.created_at),
                "updated_at": _iso(position.updated_at),
            }
            for position in polymarket_positions
            if position.portfolio_id in portfolio_public_ids
        ],
        "notification_preferences": [
            {
                "id": str(preference.public_id),
                "portfolio_id": portfolio_public_ids[preference.portfolio_id],
                "channel": "discord",
                "configured": True,
                "notify_trades": bool(preference.notify_trades),
                "notify_dividends": bool(preference.notify_dividends),
                "notify_milestones": bool(preference.notify_milestones),
                "created_at": _iso(preference.created_at),
            }
            for preference in notification_preferences
            if preference.portfolio_id in portfolio_public_ids
        ],
        "trade_notes": [
            {
                "id": str(note.public_id),
                "transaction_id": str(transactions_by_id[note.transaction_id].public_id),
                "content": note.content,
                "tags": note.tags,
                "sentiment": note.sentiment,
                "updated_at": _iso(note.updated_at),
            }
            for note in trade_notes
            if note.transaction_id in transactions_by_id
        ],
        "cash_interest_rates": [
            {
                "id": str(rate.public_id),
                "portfolio_id": portfolio_public_ids[rate.portfolio_id],
                "currency": rate.currency,
                "annual_rate": rate.annual_rate,
                "enabled": bool(rate.enabled),
                "start_date": _iso(rate.start_date),
                "created_at": _iso(rate.created_at),
            }
            for rate in cash_interest_rates
            if rate.portfolio_id in portfolio_public_ids
        ],
        "allocation_targets": [
            {
                "id": str(target.public_id),
                "portfolio_id": portfolio_public_ids[target.portfolio_id],
                "ticker": target.ticker,
                "group": target.group_name,
                "target_pct": float(target.target_pct),
                "display_order": target.display_order,
                "created_at": _iso(target.created_at),
            }
            for target in allocation_targets
            if target.portfolio_id in portfolio_public_ids
        ],
        "dividend_notifications": [
            {
                "id": str(notification.public_id),
                "portfolio_id": portfolio_public_ids[notification.portfolio_id],
                "ticker": notification.ticker,
                "ex_date": _iso(notification.ex_date),
                "sent_at": _iso(notification.sent_at),
            }
            for notification in dividend_notifications
            if notification.portfolio_id in portfolio_public_ids
        ],
        "workspace_preferences": {
            preference.key: preference.value for preference in workspace_preferences
        },
    }
