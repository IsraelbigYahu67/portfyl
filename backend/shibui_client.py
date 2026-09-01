"""Client for the Shibui Finance MCP server (https://mcp.shibui.finance).

Shibui is a free, public, unauthenticated remote MCP server backed by a
DuckDB warehouse of US equity data (64y of prices, quarterly/annual
financials, daily valuations, technical indicators, SEC EDGAR filing
metadata) for NYSE/NASDAQ-listed companies. It has no plain REST API -- the
only way to query it is to speak the MCP protocol -- so this is a minimal
MCP client rather than an httpx wrapper like market_data.py's yfinance calls.

Each call opens a fresh session (connect -> initialize -> run the query ->
close). Shibui's own tool descriptions say `get_database_schema` and
`get_query_patterns` are "required once per session" before
`stock_data_query`, but verified live (2026-08-25, both a plain SELECT and a
JOIN query) that skipping them entirely returns byte-identical rows in
roughly a third of the wall time (one MCP roundtrip instead of three) -- the
schema/pattern tools appear to only affect what an LLM caller is shown, not
server-side query validation. Callers should still wrap results in
cache.ttl_cache to keep repeat calls off the hot path.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

SHIBUI_MCP_URL = "https://mcp.shibui.finance/mcp"

# Guards every f-string-interpolated ticker sent to Shibui's stock_data_query
# (that server takes a finished SQL string, not parametrized queries). Shared
# by every module that queries Shibui (routers/market.py, dividend_growth.py).
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")


class ShibuiError(Exception):
    """Raised when the Shibui MCP server errors or returns an unparsable result."""


def _text_of(result) -> str:
    return "".join(c.text for c in result.content if getattr(c, "type", None) == "text")


def _extract_rows(result) -> list[dict[str, Any]]:
    if getattr(result, "is_error", False):
        raise ShibuiError(_text_of(result) or "Shibui query failed")

    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict) and isinstance(structured.get("result"), list):
        return structured["result"]

    try:
        data = json.loads(_text_of(result))
    except (json.JSONDecodeError, TypeError) as e:
        raise ShibuiError(f"Could not parse Shibui response: {e}") from e
    if isinstance(data, dict) and isinstance(data.get("result"), list):
        data = data["result"]
    if not isinstance(data, list):
        raise ShibuiError(f"Unexpected Shibui response shape: {type(data).__name__}")
    return data


async def _query_async(sql: str, user_prompt: str) -> list[dict[str, Any]]:
    async with streamable_http_client(SHIBUI_MCP_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                name="stock_data_query",
                arguments={"query": sql, "user_prompt": user_prompt},
            )
            return _extract_rows(result)


def query(sql: str, user_prompt: str) -> list[dict[str, Any]]:
    """Run a read-only DuckDB SQL query against Shibui's market-data warehouse.

    `sql` must reference tables with the `shibui.` prefix and include a
    LIMIT clause (server-enforced 200-row max). `user_prompt` is Shibui's
    required observability field -- the user-facing reason for the query.
    Raises ShibuiError on failure; never returns partial/garbage rows.
    """
    try:
        return asyncio.run(_query_async(sql, user_prompt))
    except ShibuiError:
        raise
    except Exception as e:
        # Session-level failures (rate limiting, dropped connections, protocol
        # errors during initialize()) surface from the mcp/anyio machinery as
        # MCPError / (Base)ExceptionGroup, not ShibuiError -- every call site
        # in routers/market.py only catches ShibuiError, so an unwrapped
        # transport failure here escaped as a raw 500 instead of the graceful
        # degrade (empty/None -> yfinance fallback, or a clean 404/502)
        # callers expect. Normalize every failure mode at this one choke point.
        raise ShibuiError(f"Shibui MCP request failed: {e}") from e
