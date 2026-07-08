"""Shared test helpers — reusable without depending on conftest fixtures."""

from __future__ import annotations

from datetime import date

from models import Transaction


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
) -> Transaction:
    return Transaction(
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
