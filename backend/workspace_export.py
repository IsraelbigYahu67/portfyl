"""Versioned, allow-listed workspace data portability export."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import (
    BrokerConnection,
    Portfolio,
    PriceAlert,
    Transaction,
    Watchlist,
    WatchlistItem,
)
from tenancy import RequestContext


EXPORT_SCHEMA_VERSION = 1


def _iso(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


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
                "csv_covered_through": _iso(connection.t212_csv_covered_through),
                "needs_attention": bool(connection.needs_attention),
                "consecutive_failures": connection.consecutive_failures,
                "created_at": _iso(connection.created_at),
            }
            for connection in connections
            if connection.portfolio_id in portfolio_public_ids
        ],
    }
