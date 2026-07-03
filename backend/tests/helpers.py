"""Shared test helpers — reusable without depending on conftest fixtures."""

from __future__ import annotations

from datetime import date

from models import Transaction


def make_txn(
    ticker: str = "AAPL",
    type: str = "buy",
    shares: float = 10,
    price: float = 150.0,
    currency: str = "USD",
    date: date | None = None,
    fx_to_czk: float | None = None,
    name: str | None = None,
    notes: str | None = None,
    source: str | None = "manual",
    portfolio_id: int = 1,
) -> Transaction:
    return Transaction(
        portfolio_id=portfolio_id,
        ticker=ticker.upper(),
        name=name or ticker.upper(),
        type=type,
        shares=shares,
        price=price,
        currency=currency,
        date=date or date(2024, 1, 15),
        fx_to_czk=fx_to_czk,
        notes=notes,
        source=source,
    )
