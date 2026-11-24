"""Cloud billing configuration (Stripe Managed Payments).

Secrets and Stripe object identifiers come from the environment. Plan
capabilities and limits stay code-owned in plans.py, so neither a browser nor
Stripe metadata can grant access: a Stripe Price only ever maps to one of the
two paid tiers named here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Mapping

from plans import PlanTier


DEFAULT_STRIPE_API_VERSION = "2026-09-30.endive"

# Displayed monthly prices in euro cents, VAT included. They must match the
# Stripe Prices configured in PORTFYL_STRIPE_PRICE_*; Stripe stays the source
# of truth for what is actually charged.
MONTHLY_PRICE_CENTS = MappingProxyType({
    PlanTier.INVESTOR: 599,
    PlanTier.PRO: 999,
})

# Bump when the wording of the immediate-start consent shown before checkout
# changes, so the audit log records which text the customer accepted.
CHECKOUT_CONSENT_VERSION = "2026-11-24"

# Withdrawal window: within this many days of the first paid ORDER of a
# subscription, deleting the workspace counts as a withdrawal (the
# subscription is cancelled and every payment refunded in full). After it,
# deletion only cancels. One rule for the status payload and the deletion.
WITHDRAWAL_DAYS = 14


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def withdrawal_ends_at(ordered_at: datetime | None) -> datetime | None:
    """End of the withdrawal window (UTC), or None without an order."""
    if ordered_at is None:
        return None
    return as_utc(ordered_at) + timedelta(days=WITHDRAWAL_DAYS)


def withdrawal_open(ordered_at: datetime | None, now: datetime) -> bool:
    """True while ``now`` (always the SERVER clock) is before the window end."""
    ends_at = withdrawal_ends_at(ordered_at)
    return ends_at is not None and as_utc(now) < ends_at


def billing_enabled(env: Mapping[str, str]) -> bool:
    return env.get("PORTFYL_BILLING_ENABLED", "0").strip() == "1"


@dataclass(frozen=True)
class BillingConfig:
    enabled: bool
    app_url: str
    secret_key: str | None = None
    webhook_secret: str | None = None
    api_version: str = DEFAULT_STRIPE_API_VERSION
    prices: Mapping[PlanTier, str] = field(default_factory=lambda: MappingProxyType({}))

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "BillingConfig":
        app_url = env.get("PORTFYL_APP_URL", "http://localhost:5173").strip().rstrip("/")
        if not billing_enabled(env):
            # Billing is an optional cloud boundary: the local edition and a
            # cloud deploy without payments must not depend on stale or
            # malformed Stripe variables.
            return cls(enabled=False, app_url=app_url)

        secret_key = env.get("STRIPE_SECRET_KEY", "").strip()
        webhook_secret = env.get("STRIPE_WEBHOOK_SECRET", "").strip()
        api_version = env.get("STRIPE_API_VERSION", "").strip() or DEFAULT_STRIPE_API_VERSION
        prices = {
            PlanTier.INVESTOR: env.get("PORTFYL_STRIPE_PRICE_INVESTOR", "").strip(),
            PlanTier.PRO: env.get("PORTFYL_STRIPE_PRICE_PRO", "").strip(),
        }

        missing = []
        if not secret_key:
            missing.append("STRIPE_SECRET_KEY")
        if not webhook_secret:
            missing.append("STRIPE_WEBHOOK_SECRET")
        for plan, price_id in prices.items():
            if not price_id:
                missing.append(f"PORTFYL_STRIPE_PRICE_{plan.value.upper()}")
        if missing:
            raise RuntimeError("Billing configuration is incomplete: " + ", ".join(missing))
        if not secret_key.startswith(("sk_live_", "sk_test_", "rk_live_", "rk_test_")):
            raise RuntimeError("STRIPE_SECRET_KEY must be a Stripe secret or restricted key")
        if not webhook_secret.startswith("whsec_"):
            raise RuntimeError("STRIPE_WEBHOOK_SECRET must be a Stripe webhook signing secret")
        if any(not price_id.startswith("price_") for price_id in prices.values()):
            raise RuntimeError("PORTFYL_STRIPE_PRICE_* must be Stripe Price IDs (price_...)")
        if len(set(prices.values())) != len(prices):
            raise RuntimeError("Each paid plan needs its own Stripe Price")
        if not app_url.startswith(("https://", "http://localhost")):
            raise RuntimeError("PORTFYL_APP_URL must be an https URL when billing is enabled")

        return cls(
            enabled=True,
            app_url=app_url,
            secret_key=secret_key,
            webhook_secret=webhook_secret,
            api_version=api_version,
            prices=MappingProxyType(prices),
        )

    @property
    def livemode(self) -> bool:
        return bool(self.secret_key and self.secret_key.startswith(("sk_live_", "rk_live_")))

    def price_id(self, plan: PlanTier) -> str:
        try:
            return self.prices[plan]
        except KeyError as exc:
            raise KeyError(f"No Stripe Price for plan {plan.value}") from exc

    def plan_for_price(self, price_id: str | None) -> PlanTier | None:
        for plan, configured in self.prices.items():
            if configured == price_id:
                return plan
        return None
