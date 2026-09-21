"""Trading 212 API response fixtures.

Task 1 of docs/superpowers/plans/2026-09-20-t212-snapshot-first-sync.md:
lock the exact field shape the snapshot-first sync (backend/t212_sync.py)
consumes. Field names follow Trading 212's published API docs:

- GET /equity/account/summary — same shape already relied on by
  routers.broker._upsert_t212_balance (see that function's own "verified
  only against a hand-written test fixture" note).
- GET /equity/positions — https://docs.trading212.com/api/positions/getpositions

This module intentionally covers only what backend/t212_sync.py's Task 2
slice consumes (account summary + positions). Order/dividend/cash-transaction
and corporate-action fixtures belong with the history-sync work that
consumes them (plan Tasks 3-4) and are not added speculatively here.
"""

from __future__ import annotations


def t212_account_summary_response(**overrides) -> dict:
    """A GET /equity/account/summary response with every field
    routers.broker._upsert_t212_balance and t212_sync read."""
    base = {
        "currency": "CZK",
        "cash": {
            "availableToTrade": 1000.0,
            "inPies": 300.0,
            "reservedForOrders": 82.17,
        },
        "investments": {
            "currentValue": 60000.0,
            "totalCost": 55000.0,
            "unrealizedProfitLoss": 4500.0,
            "realizedProfitLoss": 500.0,
        },
        "totalValue": 61382.17,
    }
    base.update(overrides)
    return base


def t212_position(**overrides) -> dict:
    """One element of a GET /equity/positions response. `/equity/positions`
    carries no instrument name/currency -- only ticker, quantity, and
    account-currency price/P&L fields."""
    base = {
        "ticker": "AAPL_US_EQ",
        "quantity": 10.0,
        "averagePrice": 150.0,
        "currentPrice": 175.0,
        "ppl": 250.0,
        "fxPpl": 0.0,
        "initialFillDate": "2024-01-15T10:00:00Z",
        "frontend": "API",
        "maxBuy": 100.0,
        "maxSell": 10.0,
        "pieQuantity": 0.0,
    }
    base.update(overrides)
    return base


def t212_positions_response(*positions: dict) -> list[dict]:
    """GET /equity/positions returns a bare JSON array, not {"items": [...]}."""
    return list(positions) if positions else [t212_position()]
