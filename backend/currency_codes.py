"""Currency-code normalization shared by importers and FX conversion.

Kept dependency-free so broker importers can use it without pulling in the
market-data stack.
"""
from __future__ import annotations

# Sub-units quoted by Yahoo against their main currency: GBX (pence) amounts
# convert at the pound rate / 100. Yahoo's own GBXCZK=X answers the per-POUND
# rate, which priced LSE pence trades 100x too high.
SUBUNITS: dict[str, tuple[str, float]] = {"GBX": ("GBP", 100.0)}


def normalize_currency(code: str | None, default: str = "USD") -> str:
    """Canonical upper-case currency code. Pence stay distinct from pounds:
    'GBp' (Yahoo's spelling) and 'GBX' both become 'GBX'. A plain .upper()
    turns 'GBp' into 'GBP' and values a pence price 100x too high."""
    raw = str(code or "").strip()
    if not raw:
        return default
    if raw == "GBp":
        return "GBX"
    return raw.upper()


def subunit(currency: str | None) -> tuple[str, float]:
    """(currency whose FX quote to use, divisor) for a currency code."""
    c = normalize_currency(currency)
    return SUBUNITS.get(c, (c, 1.0))
