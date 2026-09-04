"""Read-only verification for Portfyl's immutable Stripe Price catalog.

Run from the repository root after exporting the billing environment. The
script retrieves Products/Prices but never creates, updates, archives, or
deletes Stripe objects.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))

from billing_config import BillingConfig, PUBLIC_PRICES  # noqa: E402


def main() -> int:
    config = BillingConfig.from_env(os.environ)
    if not config.enabled or not config.secret_key:
        raise RuntimeError("Set a complete enabled billing configuration first")

    import stripe

    stripe.api_key = config.secret_key
    verified = 0
    for (plan, interval, version), price_id in sorted(
        config.stripe_prices.items(), key=lambda item: tuple(str(part) for part in item[0])
    ):
        price = stripe.Price.retrieve(price_id, expand=["product"])
        if price.type != "recurring" or price.recurring.interval != interval.value:
            raise RuntimeError(f"{version}/{plan.value}/{interval.value}: recurring interval mismatch")
        if price.currency.lower() != "eur":
            raise RuntimeError(f"{version}/{plan.value}/{interval.value}: currency must be EUR")
        product = price.product
        if isinstance(product, str):
            product = stripe.Product.retrieve(product)
        if not product or getattr(product, "deleted", False):
            raise RuntimeError(f"{version}/{plan.value}/{interval.value}: product is unavailable")

        if version == config.current_price_version:
            expected = PUBLIC_PRICES[(plan, interval)]
            if not price.active:
                raise RuntimeError(f"{version}/{plan.value}/{interval.value}: current Price is archived")
            if price.unit_amount != expected.amount_cents:
                raise RuntimeError(
                    f"{version}/{plan.value}/{interval.value}: amount does not match backend catalog"
                )
        verified += 1
        print(f"verified {version}/{plan.value}/{interval.value}")

    print(f"Stripe catalog verification passed ({verified} immutable Prices)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
