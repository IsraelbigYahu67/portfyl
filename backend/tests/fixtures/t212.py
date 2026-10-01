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
    """One element of the current documented GET /equity/positions response.

    Tests may keep using the legacy ergonomic keyword names below; the helper
    translates them into the official nested response shape so mocks exercise
    the same contract as the live API.
    """
    base = {
        "averagePricePaid": 150.0,
        "createdAt": "2024-01-15T10:00:00Z",
        "currentPrice": 175.0,
        "instrument": {
            "currency": "USD",
            "isin": "US0378331005",
            "name": "Apple",
            "ticker": "AAPL_US_EQ",
        },
        "quantity": 10.0,
        "quantityAvailableForTrading": 10.0,
        "quantityInPies": 0.0,
        "walletImpact": {
            "currency": "CZK",
            "currentValue": 17_500.0,
            "fxImpact": 0.0,
            "totalCost": 15_000.0,
            "unrealizedProfitLoss": 250.0,
        },
    }
    aliases = {
        "ticker": ("instrument", "ticker"),
        "averagePrice": (None, "averagePricePaid"),
        "pieQuantity": (None, "quantityInPies"),
        "initialFillDate": (None, "createdAt"),
        "ppl": ("walletImpact", "unrealizedProfitLoss"),
        "fxPpl": ("walletImpact", "fxImpact"),
    }
    for legacy_name, (container, current_name) in aliases.items():
        if legacy_name not in overrides:
            continue
        value = overrides.pop(legacy_name)
        if container is None:
            base[current_name] = value
        else:
            base[container][current_name] = value
    base.update(overrides)
    return base


def t212_positions_response(*positions: dict) -> list[dict]:
    """GET /equity/positions returns a bare JSON array, not {"items": [...]}."""
    return list(positions) if positions else [t212_position()]
