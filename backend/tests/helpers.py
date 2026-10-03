"""Shared test helpers — reusable without depending on conftest fixtures."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import UUID

from models import BrokerConnection, Transaction


TEST_WORKSPACE_ID = UUID("11111111-1111-4111-8111-111111111111")

# The per-connection history-coverage checkpoints (plan 2026-09-24, Task C1).
T212_COVERAGE_FIELDS = (
    "history_complete_at",
    "orders_frontier_at",
    "orders_frontier_event_id",
    "dividends_frontier_at",
    "dividends_frontier_event_id",
    "cash_frontier_at",
    "cash_frontier_event_id",
    "last_full_audit_at",
)


def make_t212_connection_with_coverage(db, portfolio) -> BrokerConnection:
    """A Trading 212 connection with every history-coverage field set."""
    when = datetime(2024, 6, 1, tzinfo=timezone.utc)
    conn = BrokerConnection(
        workspace_id=portfolio.workspace_id, portfolio_id=portfolio.id,
        broker="trading212", api_key="k" * 20,
        history_complete_at=when,
        orders_frontier_at=when, orders_frontier_event_id="fill:9",
        dividends_frontier_at=when, dividends_frontier_event_id="dividend:9",
        cash_frontier_at=when, cash_frontier_event_id="cash:9",
        last_full_audit_at=when,
    )
    db.add(conn)
    db.commit()
    return conn


def make_txn(
    ticker: str | None = "AAPL",
    type: str = "buy",
    shares: float | None = 10,
    price: float | None = 150.0,
    currency: str = "USD",
    date: date | None = None,
    fx_to_czk: float | None = None,
    name: str | None = None,
    notes: str | None = None,
    source: str | None = "manual",
    portfolio_id: int = 1,
    amount: float | None = None,
    cash_amount: float | None = None,
    cash_currency: str | None = None,
    workspace_id: UUID = TEST_WORKSPACE_ID,
) -> Transaction:
    return Transaction(
        workspace_id=workspace_id,
        portfolio_id=portfolio_id,
        ticker=ticker.upper() if ticker else None,
        name=name or (ticker.upper() if ticker else None),
        type=type,
        shares=shares,
        price=price,
        amount=amount,
        currency=currency,
        date=date or __import__("datetime").date(2024, 1, 15),
        fx_to_czk=fx_to_czk,
        notes=notes,
        source=source,
        cash_amount=cash_amount,
        cash_currency=cash_currency,
    )
