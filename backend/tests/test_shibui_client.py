"""Tests for shibui_client.query()'s error-normalization contract.

Every call site in routers/market.py (17+ of them) does
`except shibui_client.ShibuiError:` and nothing else, trusting query()'s
docstring promise that it "Raises ShibuiError on failure". That was only
true for failures inside _extract_rows (bad SQL, unparsable response) --
transport/protocol failures from the underlying mcp/anyio machinery (e.g.
the MCP server erroring during session.initialize(), such as during a
rate-limit window) surfaced as a raw MCPError/ExceptionGroup instead, which
none of those call sites catch. That turned a should-be-graceful Shibui
outage into an uncaught 500 on every Shibui-backed endpoint, including
/market/fundamentals/{ticker} (stock detail).
"""

from __future__ import annotations

import pytest


class TestQueryErrorNormalization:
    def test_shibui_error_passes_through_unwrapped(self, monkeypatch):
        import shibui_client

        async def raise_shibui_error(sql, user_prompt):
            raise shibui_client.ShibuiError("bad SQL")

        monkeypatch.setattr(shibui_client, "_query_async", raise_shibui_error)
        with pytest.raises(shibui_client.ShibuiError, match="bad SQL"):
            shibui_client.query("SELECT 1", "test")

    def test_arbitrary_exception_is_normalized_to_shibui_error(self, monkeypatch):
        """The bug: a raw MCPError (or anything else) from the mcp/anyio
        session machinery must not escape query() -- every caller only
        catches ShibuiError."""
        import shibui_client

        async def raise_generic_error(sql, user_prompt):
            raise RuntimeError("Server returned an error response")

        monkeypatch.setattr(shibui_client, "_query_async", raise_generic_error)
        with pytest.raises(shibui_client.ShibuiError, match="Server returned an error response"):
            shibui_client.query("SELECT 1", "test")

    def test_exception_group_is_normalized_to_shibui_error(self, monkeypatch):
        """Reproduces the actual failure shape: anyio TaskGroups wrap
        session-init failures in an ExceptionGroup, not a bare exception."""
        import shibui_client

        async def raise_exception_group(sql, user_prompt):
            raise ExceptionGroup("unhandled errors in a TaskGroup", [RuntimeError("MCPError: rate limited")])

        monkeypatch.setattr(shibui_client, "_query_async", raise_exception_group)
        with pytest.raises(shibui_client.ShibuiError):
            shibui_client.query("SELECT 1", "test")

    def test_successful_query_returns_rows_unmodified(self, monkeypatch):
        import shibui_client

        rows = [{"ticker": "AAPL"}]

        async def fake_query_async(sql, user_prompt):
            return rows

        monkeypatch.setattr(shibui_client, "_query_async", fake_query_async)
        assert shibui_client.query("SELECT 1", "test") == rows
