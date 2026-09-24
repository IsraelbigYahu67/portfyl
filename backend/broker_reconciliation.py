"""Read-only comparison of the ledger's open quantities with the broker's
current position snapshot (T212 snapshot-first sync plan, §6.3).

A mismatch is reported, never repaired: Portfyl creates no synthetic trade or
corporate-action row to force the two sides to agree (plan §3). The
``likely_causes`` are hints derived from the direction of the gap, not a
diagnosis.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

from models import BrokerPosition

# Shares. Matches the open-position epsilon in routers.portfolio._build_holdings;
# fractional T212 quantities and CSV rounding stay well inside it.
QUANTITY_TOLERANCE = 0.0001

_LIKELY_CAUSES = {
    "ledger_missing": ("incomplete_provider_history", "ticker_mapping"),
    "ledger_lower": (
        "incomplete_provider_history", "unsupported_corporate_action", "ticker_mapping",
    ),
    "ledger_higher": (
        "incomplete_provider_history", "unsupported_corporate_action", "csv_api_overlap",
    ),
    "broker_missing": ("incomplete_provider_history", "ticker_mapping"),
}


def _result(status: str, reason: str | None, matched: int, different: list[dict]) -> dict:
    return {
        "status": status,
        "reason": reason,
        "tolerance": QUANTITY_TOLERANCE,
        "matched_count": matched,
        "different": different,
    }


def _direction(ledger: float, broker: float) -> str:
    if ledger <= QUANTITY_TOLERANCE:
        return "ledger_missing"
    if broker <= QUANTITY_TOLERANCE:
        return "broker_missing"
    return "ledger_lower" if ledger < broker else "ledger_higher"


def reconcile_positions(
    *,
    ledger_shares: Mapping[str, float],
    positions: Iterable[BrokerPosition],
    snapshot_available: bool,
    history_complete: bool,
    snapshot_stale: bool = False,
) -> dict:
    """Compare ledger open shares (by normalized ticker) with broker positions.

    Either side lacking authoritative data makes the result ``unavailable``;
    an incomplete history takes precedence over a missing snapshot. Positions
    that share a normalized ticker are summed. Only mismatching tickers are
    listed, each with both quantities and the direction of the gap."""
    if not history_complete:
        return _result("unavailable", "history_incomplete", 0, [])
    if not snapshot_available:
        return _result("unavailable", "no_snapshot", 0, [])

    broker_quantity: dict[str, float] = defaultdict(float)
    provider_tickers: dict[str, list[str]] = defaultdict(list)
    for position in positions:
        broker_quantity[position.ticker] += position.quantity or 0.0
        if position.provider_ticker not in provider_tickers[position.ticker]:
            provider_tickers[position.ticker].append(position.provider_ticker)

    matched = 0
    different: list[dict] = []
    for ticker in sorted(set(broker_quantity) | set(ledger_shares)):
        broker = broker_quantity.get(ticker, 0.0)
        ledger = ledger_shares.get(ticker, 0.0)
        if broker <= QUANTITY_TOLERANCE and ledger <= QUANTITY_TOLERANCE:
            continue
        difference = ledger - broker
        if abs(difference) <= QUANTITY_TOLERANCE:
            matched += 1
            continue
        direction = _direction(ledger, broker)
        causes = list(_LIKELY_CAUSES[direction])
        if snapshot_stale:
            causes.append("snapshot_stale")
        different.append({
            "ticker": ticker,
            "provider_tickers": provider_tickers.get(ticker, []),
            "broker_quantity": round(broker, 8),
            "ledger_quantity": round(ledger, 8),
            "difference": round(difference, 8),
            "direction": direction,
            "likely_causes": causes,
        })

    return _result("different" if different else "matched", None, matched, different)
