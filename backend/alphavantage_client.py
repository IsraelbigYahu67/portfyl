"""Client for Alpha Vantage's free REST API -- used only for the on-demand
Congress/political-trades feature (see PLAN.md, phase 1g). Unlike
shibui_client.py, Alpha Vantage has a plain REST API (no MCP), so this
uses a plain httpx.AsyncClient rather than shibui_client's MCP session
dance.

Free tier is 25 requests/day, so callers must only ever invoke this on
explicit user action (a button click), never from a background job or
auto-prefetch -- see PLAN.md 1g-i. The 24h ttl_cache applied at the route
layer keeps repeat clicks on the same ticker/day off the quota too.
"""
from __future__ import annotations

import os
from typing import Any

import httpx

ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")


class AlphaVantageError(Exception):
    """Raised when Alpha Vantage errors, rate-limits, or returns an unexpected shape."""


async def _get(params: dict[str, str]) -> dict[str, Any]:
    if not ALPHA_VANTAGE_API_KEY:
        raise AlphaVantageError("ALPHA_VANTAGE_API_KEY is not configured")

    query = {**params, "apikey": ALPHA_VANTAGE_API_KEY}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(ALPHA_VANTAGE_URL, params=query)
    except httpx.TimeoutException as e:
        raise AlphaVantageError("Alpha Vantage timed out") from e
    except httpx.HTTPError as e:
        raise AlphaVantageError(f"Could not reach Alpha Vantage: {e}") from e

    if resp.status_code >= 400:
        raise AlphaVantageError(f"Alpha Vantage HTTP error {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
    except ValueError as e:
        raise AlphaVantageError(f"Could not parse Alpha Vantage response: {e}") from e

    # Rate-limit / quota messages come back as HTTP 200 with a plain-English note.
    if isinstance(data, dict) and ("Note" in data or "Information" in data):
        raise AlphaVantageError(str(data.get("Note") or data.get("Information")))
    if isinstance(data, dict) and "Error Message" in data:
        raise AlphaVantageError(str(data["Error Message"]))
    return data


async def congress_trades(symbol: str) -> dict[str, Any]:
    """All disclosed congressional trades referencing `symbol` (STOCK Act
    periodic transaction reports, House + Senate). Returns the raw response
    dict (`trades`, `trades_total_count`, `trades_truncated`)."""
    data = await _get({"function": "CONGRESS_TRADES", "symbol": symbol})
    if not isinstance(data, dict) or not isinstance(data.get("trades"), list):
        raise AlphaVantageError(f"Unexpected CONGRESS_TRADES response shape: {type(data).__name__}")
    return data
