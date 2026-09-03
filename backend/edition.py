"""Edition and capability classification for the shared Portfyl codebase."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class Edition(StrEnum):
    LOCAL = "local"
    CLOUD = "cloud"


class CapabilityClass(StrEnum):
    LOCAL_ONLY = "local_only"
    CLOUD_FREE = "cloud_free"
    CLOUD_INVESTOR = "cloud_investor"
    CLOUD_PRO = "cloud_pro"


@dataclass(frozen=True)
class Capability:
    key: str
    classification: CapabilityClass


def _capability(key: str, classification: CapabilityClass) -> Capability:
    return Capability(key=key, classification=classification)


# This registry classifies product surfaces, not individual quota-bearing API
# operations. Plan enforcement will consume the same classifications in
# Workstream E; until then cloud_* entries are all edition-available.
CAPABILITY_REGISTRY: Mapping[str, Capability] = MappingProxyType({
    capability.key: capability
    for capability in (
        _capability("portfolio_dashboard", CapabilityClass.CLOUD_FREE),
        _capability("portfolio_overview", CapabilityClass.CLOUD_FREE),
        _capability("allocation", CapabilityClass.CLOUD_FREE),
        _capability("transactions", CapabilityClass.CLOUD_FREE),
        _capability("cash", CapabilityClass.CLOUD_FREE),
        _capability("market_search", CapabilityClass.CLOUD_FREE),
        _capability("watchlists", CapabilityClass.CLOUD_FREE),
        _capability("csv_import", CapabilityClass.CLOUD_FREE),
        _capability("dividends", CapabilityClass.CLOUD_FREE),
        _capability("settings", CapabilityClass.CLOUD_FREE),
        _capability("portfolio_analytics", CapabilityClass.CLOUD_INVESTOR),
        _capability("broker_sync", CapabilityClass.CLOUD_INVESTOR),
        _capability("alerts", CapabilityClass.CLOUD_INVESTOR),
        _capability("advanced_research", CapabilityClass.CLOUD_PRO),
        _capability("assistant", CapabilityClass.CLOUD_PRO),
        _capability("options", CapabilityClass.CLOUD_PRO),
        _capability("polymarket", CapabilityClass.CLOUD_PRO),
        _capability("tax_report", CapabilityClass.LOCAL_ONLY),
        _capability("screener", CapabilityClass.LOCAL_ONLY),
    )
})


def edition_from_env(env: Mapping[str, str]) -> Edition:
    raw = env.get("PORTFYL_EDITION", "").strip().lower()
    if not raw:
        raise RuntimeError("PORTFYL_EDITION is required (expected 'local' or 'cloud')")
    try:
        return Edition(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"Unsupported PORTFYL_EDITION {raw!r}; expected 'local' or 'cloud'"
        ) from exc


def edition_allows(edition: Edition, capability_key: str) -> bool:
    try:
        capability = CAPABILITY_REGISTRY[capability_key]
    except KeyError as exc:
        raise KeyError(f"Unknown capability: {capability_key}") from exc
    return edition is Edition.LOCAL or capability.classification is not CapabilityClass.LOCAL_ONLY


def available_capabilities(edition: Edition) -> tuple[Capability, ...]:
    return tuple(
        capability
        for capability in CAPABILITY_REGISTRY.values()
        if edition_allows(edition, capability.key)
    )


def capability_payload(edition: Edition) -> dict[str, object]:
    allowed = available_capabilities(edition)
    return {
        "edition": edition.value,
        "capabilities": [capability.key for capability in allowed],
        "classifications": {
            capability.key: capability.classification.value
            for capability in allowed
        },
    }
