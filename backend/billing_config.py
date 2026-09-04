"""Closed cloud plan, price, and quota configuration.

Secrets and Stripe object identifiers come from the environment.  Product
capabilities and limits are code-owned so neither a browser nor Stripe metadata
can silently grant access.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class PlanTier(StrEnum):
    FREE = "free"
    INVESTOR = "investor"
    PRO = "pro"


class BillingInterval(StrEnum):
    MONTH = "month"
    YEAR = "year"


@dataclass(frozen=True)
class PlanLimits:
    portfolios: int | None
    active_positions: int | None
    transactions: int | None
    broker_connections: int | None
    watchlists: int | None
    watchlist_symbols: int | None
    alerts: int | None
    hosted_ai_monthly: int
    autosync_min_hours: int | None


@dataclass(frozen=True)
class PublicPrice:
    plan: PlanTier
    interval: BillingInterval
    amount_cents: int
    currency: str = "eur"


PUBLIC_PRICES = MappingProxyType({
    (PlanTier.INVESTOR, BillingInterval.MONTH): PublicPrice(
        PlanTier.INVESTOR, BillingInterval.MONTH, 499
    ),
    (PlanTier.INVESTOR, BillingInterval.YEAR): PublicPrice(
        PlanTier.INVESTOR, BillingInterval.YEAR, 4900
    ),
    (PlanTier.PRO, BillingInterval.MONTH): PublicPrice(
        PlanTier.PRO, BillingInterval.MONTH, 799
    ),
    (PlanTier.PRO, BillingInterval.YEAR): PublicPrice(
        PlanTier.PRO, BillingInterval.YEAR, 7900
    ),
})


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
        PlanTier.FREE: PlanLimits(1, 15, 250, 0, 1, 15, 3, 0, None),
        PlanTier.INVESTOR: PlanLimits(
            5,
            None,
            None,
            2,
            5,
            _positive_int(env, "PORTFYL_INVESTOR_WATCHLIST_SYMBOL_LIMIT", 100),
            20,
            0,
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
    "assistant_byok": PlanTier.INVESTOR,
    "advanced_research": PlanTier.PRO,
    "custom_benchmarks": PlanTier.PRO,
    "assistant_hosted": PlanTier.PRO,
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


@dataclass(frozen=True)
class BillingConfig:
    enabled: bool
    secret_key: str | None
    webhook_secret: str | None
    trial_identity_key: str | None
    app_url: str
    current_price_version: str
    stripe_prices: Mapping[tuple[PlanTier, BillingInterval, str], str]

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "BillingConfig":
        enabled = env.get("PORTFYL_BILLING_ENABLED", "0").strip() == "1"
        version = env.get("PORTFYL_CURRENT_PRICE_VERSION", "v1").strip() or "v1"
        app_url = env.get("PORTFYL_APP_URL", "http://localhost:5173").strip().rstrip("/")
        if not enabled:
            # Billing configuration is an optional cloud boundary. In
            # particular, the private local edition must not become dependent
            # on stale or malformed Stripe environment variables.
            return cls(
                enabled=False,
                secret_key=None,
                webhook_secret=None,
                trial_identity_key=None,
                app_url=app_url,
                current_price_version=version,
                stripe_prices=MappingProxyType({}),
            )
        raw_catalog = env.get("PORTFYL_STRIPE_PRICE_CATALOG", "{}").strip() or "{}"
        try:
            decoded = json.loads(raw_catalog)
        except json.JSONDecodeError as exc:
            raise RuntimeError("PORTFYL_STRIPE_PRICE_CATALOG must be valid JSON") from exc

        prices: dict[tuple[PlanTier, BillingInterval, str], str] = {}
        seen_ids: set[str] = set()
        if not isinstance(decoded, dict):
            raise RuntimeError("PORTFYL_STRIPE_PRICE_CATALOG must be a JSON object")
        for price_version, plans in decoded.items():
            if not isinstance(price_version, str) or not isinstance(plans, dict):
                raise RuntimeError("Invalid Stripe price catalog structure")
            for raw_plan, intervals in plans.items():
                try:
                    plan = PlanTier(raw_plan)
                except ValueError as exc:
                    raise RuntimeError(f"Unknown plan in Stripe price catalog: {raw_plan}") from exc
                if plan is PlanTier.FREE or not isinstance(intervals, dict):
                    raise RuntimeError("Stripe price catalog contains an invalid paid plan")
                for raw_interval, price_id in intervals.items():
                    try:
                        interval = BillingInterval(raw_interval)
                    except ValueError as exc:
                        raise RuntimeError(
                            f"Unknown interval in Stripe price catalog: {raw_interval}"
                        ) from exc
                    if not isinstance(price_id, str) or not price_id.startswith("price_"):
                        raise RuntimeError("Stripe price IDs must start with 'price_'")
                    if price_id in seen_ids:
                        raise RuntimeError("Stripe price IDs must be unique and immutable")
                    seen_ids.add(price_id)
                    prices[(plan, interval, price_version)] = price_id

        secret_key = env.get("STRIPE_SECRET_KEY", "").strip() or None
        webhook_secret = env.get("STRIPE_WEBHOOK_SECRET", "").strip() or None
        trial_identity_key = env.get("PORTFYL_TRIAL_IDENTITY_KEY", "").strip() or None
        missing = []
        if not secret_key:
            missing.append("STRIPE_SECRET_KEY")
        if not webhook_secret:
            missing.append("STRIPE_WEBHOOK_SECRET")
        if not trial_identity_key:
            missing.append("PORTFYL_TRIAL_IDENTITY_KEY")
        for plan in (PlanTier.INVESTOR, PlanTier.PRO):
            for interval in BillingInterval:
                if (plan, interval, version) not in prices:
                    missing.append(f"price:{plan.value}:{interval.value}:{version}")
        if missing:
            raise RuntimeError("Billing configuration is incomplete: " + ", ".join(missing))
        return cls(
            enabled=enabled,
            secret_key=secret_key,
            webhook_secret=webhook_secret,
            trial_identity_key=trial_identity_key,
            app_url=app_url,
            current_price_version=version,
            stripe_prices=MappingProxyType(prices),
        )

    def price_id(self, plan: PlanTier, interval: BillingInterval) -> str:
        if plan is PlanTier.FREE:
            raise KeyError("Free has no Stripe Price")
        try:
            return self.stripe_prices[(plan, interval, self.current_price_version)]
        except KeyError as exc:
            raise KeyError(
                f"No Stripe Price for {plan.value}/{interval.value}/{self.current_price_version}"
            ) from exc

    def price_mapping(self) -> Mapping[str, tuple[PlanTier, BillingInterval, str]]:
        return MappingProxyType({
            price_id: (plan, interval, version)
            for (plan, interval, version), price_id in self.stripe_prices.items()
        })
