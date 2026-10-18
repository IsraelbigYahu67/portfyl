"""Provider-neutral cloud plan capabilities and resource limits."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class PlanTier(StrEnum):
    FREE = "free"
    INVESTOR = "investor"
    PRO = "pro"


@dataclass(frozen=True)
class PlanLimits:
    portfolios: int | None
    active_positions: int | None
    transactions: int | None
    broker_connections: int | None
    watchlists: int | None
    watchlist_symbols: int | None
    alerts: int | None
    autosync_min_hours: int | None


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be a positive integer")
    return value


def plan_limits(env: Mapping[str, str] | None = None) -> Mapping[PlanTier, PlanLimits]:
    env = env or {}
    return MappingProxyType({
        PlanTier.FREE: PlanLimits(1, 15, 250, 0, 1, 15, 3, None),
        PlanTier.INVESTOR: PlanLimits(
            5,
            None,
            None,
            2,
            5,
            _positive_int(env, "PORTFYL_INVESTOR_WATCHLIST_SYMBOL_LIMIT", 100),
            20,
            24,
        ),
        PlanTier.PRO: PlanLimits(
            15,
            None,
            None,
            5,
            _positive_int(env, "PORTFYL_PRO_WATCHLIST_LIMIT", 50),
            _positive_int(env, "PORTFYL_PRO_WATCHLIST_SYMBOL_LIMIT", 500),
            100,
            6,
        ),
    })


MINIMUM_PLAN = MappingProxyType({
    "portfolio_dashboard": PlanTier.FREE,
    "portfolio_overview": PlanTier.FREE,
    "allocation": PlanTier.FREE,
    "transactions": PlanTier.FREE,
    "cash": PlanTier.FREE,
    "market_search": PlanTier.FREE,
    "watchlists": PlanTier.FREE,
    "csv_import": PlanTier.FREE,
    "dividends": PlanTier.FREE,
    "settings": PlanTier.FREE,
    "alerts": PlanTier.FREE,
    "portfolio_analytics": PlanTier.INVESTOR,
    "dividend_analysis": PlanTier.INVESTOR,
    "standard_research": PlanTier.INVESTOR,
    "notification_integrations": PlanTier.INVESTOR,
    "broker_sync": PlanTier.INVESTOR,
    "advanced_research": PlanTier.PRO,
    "custom_benchmarks": PlanTier.PRO,
    "options": PlanTier.PRO,
    "polymarket": PlanTier.PRO,
})


_PLAN_RANK = {PlanTier.FREE: 0, PlanTier.INVESTOR: 1, PlanTier.PRO: 2}


def plan_allows(plan: PlanTier, capability: str) -> bool:
    try:
        minimum = MINIMUM_PLAN[capability]
    except KeyError as exc:
        raise KeyError(f"Unknown cloud capability: {capability}") from exc
    return _PLAN_RANK[plan] >= _PLAN_RANK[minimum]
