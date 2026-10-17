"""Broker instrument identity -> Yahoo Finance symbol.

Order: (1) broker symbol + known venue, no network; (2) ISIN via OpenFIGI,
filtered to the venue's Bloomberg exchange code; (3) unresolved -> the parser
reports an error. Never fall back to the ISIN or the product name as a
ticker: market data would silently be missing for that holding.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from cache import BoundedTTLCache
from importers.openfigi import OpenFigiClient

# Canonical venue key -> Yahoo suffix. Extend only with a verified example.
VENUE_SUFFIX: dict[str, str] = {
    "US": "",
    "XETRA": ".DE",
    "FRANKFURT": ".F",
    "LSE": ".L",
    "AMSTERDAM": ".AS",
    "PARIS": ".PA",
    "MILAN": ".MI",
    "SIX": ".SW",
    "PRAGUE": ".PR",
    "TORONTO": ".TO",
    "BRUSSELS": ".BR",
    "MADRID": ".MC",
    "VIENNA": ".VI",
    "WARSAW": ".WA",
    "HONGKONG": ".HK",
}
# Canonical venue key -> Bloomberg exchCode used by OpenFIGI. PRAGUE "CP" is
# an assumption until a real lookup (plan Task 0 step 3.5) confirms it.
# XETRA uses the German composite "GR": Xetra-traded ETFs (VWCE, EUNL) have
# no "GY" listing in OpenFIGI, while stocks carry both with the same ticker.
VENUE_FIGI: dict[str, str] = {
    "US": "US", "XETRA": "GR", "FRANKFURT": "GF", "LSE": "LN", "AMSTERDAM": "NA",
    "PARIS": "FP", "MILAN": "IM", "SIX": "SW", "PRAGUE": "CP",
}
# exchCode -> venue, for candidates of an unfiltered (venue-less) lookup.
_FIGI_VENUE: dict[str, str] = {code: venue for venue, code in VENUE_FIGI.items()} | {"GY": "XETRA"}
_POSITIVE_TTL = 30 * 24 * 3600
_NEGATIVE_TTL = 24 * 3600
_MISS = object()


@dataclass(frozen=True)
class InstrumentRef:
    isin: str | None = None
    symbol: str | None = None
    venue: str | None = None
    currency: str | None = None
    name: str | None = None


class InstrumentResolver(Protocol):
    def resolve_many(self, refs: Sequence[InstrumentRef]) -> dict[InstrumentRef, str]: ...


def yahoo_symbol(symbol: str, venue: str) -> str:
    clean = symbol.strip().upper()
    if venue == "US":
        return clean.replace(" ", "-").replace(".", "-").replace("/", "-")
    if venue == "HONGKONG" and clean.isdigit():
        clean = clean.zfill(4)
    return f"{clean.replace(' ', '-')}{VENUE_SUFFIX[venue]}"


def unresolved_errors(refs: Sequence[InstrumentRef], resolved: dict[InstrumentRef, str]) -> list[str]:
    errors = []
    for ref in dict.fromkeys(refs):
        if ref not in resolved:
            errors.append(
                f"Cannot determine the market ticker for {ref.name or ref.symbol or '?'} "
                f"(ISIN {ref.isin or '-'}, venue {ref.venue or '-'}); nothing was imported"
            )
    return errors


_SHARED_CACHE = BoundedTTLCache(maxsize=20_000, ttl=_POSITIVE_TTL)


class DefaultInstrumentResolver:
    def __init__(self, figi: OpenFigiClient | None, cache: BoundedTTLCache | None = None):
        self.figi = figi
        self.cache = cache if cache is not None else BoundedTTLCache(maxsize=20_000, ttl=_POSITIVE_TTL)

    @classmethod
    def from_env(cls) -> "DefaultInstrumentResolver":
        return cls(OpenFigiClient.from_env(), cache=_SHARED_CACHE)

    def resolve_many(self, refs: Sequence[InstrumentRef]) -> dict[InstrumentRef, str]:
        resolved: dict[InstrumentRef, str] = {}
        pending: list[InstrumentRef] = []
        for ref in dict.fromkeys(refs):
            if ref.symbol and ref.venue in VENUE_SUFFIX:
                resolved[ref] = yahoo_symbol(ref.symbol, ref.venue)
                continue
            if not ref.isin:
                continue
            cached = self.cache.get((ref.isin, ref.venue), _MISS)
            if cached is _MISS:
                pending.append(ref)
            elif cached is not None:
                resolved[ref] = cached
        # Refs that differ only in name/currency share one lookup.
        lookups = list(dict.fromkeys((ref.isin, ref.venue) for ref in pending))
        if lookups and self.figi is not None:
            matches = self.figi.map_isins([(isin, VENUE_FIGI.get(venue or "")) for isin, venue in lookups])
            found: dict[tuple, str | None] = {}
            for (isin, venue), candidates in zip(lookups, matches):
                ticker = self._pick(venue, candidates)
                found[(isin, venue)] = ticker
                self.cache.set((isin, venue), ticker, ttl=_POSITIVE_TTL if ticker else _NEGATIVE_TTL)
            for ref in pending:
                ticker = found.get((ref.isin, ref.venue))
                if ticker:
                    resolved[ref] = ticker
        return resolved

    @staticmethod
    def _pick(venue: str | None, candidates: list[dict]) -> str | None:
        wanted = VENUE_FIGI.get(venue or "")
        for item in candidates:
            if item.get("marketSector") not in (None, "Equity"):
                continue
            if wanted and item.get("exchCode") != wanted:
                continue
            match = _FIGI_VENUE.get(item.get("exchCode"))
            if match and item.get("ticker"):
                return yahoo_symbol(item["ticker"], match)
        return None
