"""IBKR Flex Web Service: transient errors are retried, then explained."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import HTTPException

from routers import ibkr

TOKEN = "123456789012345678901234"


def _fail(code: str, message: str = "Statement could not be generated at this time.") -> str:
    return (f"<FlexStatementResponse><Status>Fail</Status><ErrorCode>{code}</ErrorCode>"
            f"<ErrorMessage>{message}</ErrorMessage></FlexStatementResponse>")


SUCCESS = ("<FlexStatementResponse><Status>Success</Status>"
           "<ReferenceCode>REF42</ReferenceCode></FlexStatementResponse>")


def _send(responses):
    get = AsyncMock(side_effect=responses)
    sleep = AsyncMock()
    with patch.object(ibkr, "_flex_get", get), patch.object(ibkr.asyncio, "sleep", sleep):
        result = asyncio.run(ibkr._send_flex_request(TOKEN, "1519214"))
    return result, get, sleep


def test_transient_code_is_retried_until_success():
    result, get, sleep = _send([_fail("1001"), _fail("1018"), SUCCESS])
    assert result == "REF42"
    assert get.await_count == 3
    assert [c.args[0] for c in sleep.await_args_list] == list(ibkr._FLEX_RETRY_DELAYS)


def test_transient_code_that_persists_explains_itself():
    with pytest.raises(HTTPException) as exc:
        _send([_fail("1001")] * (len(ibkr._FLEX_RETRY_DELAYS) + 1))
    assert exc.value.status_code == 503
    assert "1001" in exc.value.detail and "try again" in exc.value.detail


def test_permanent_code_fails_at_once():
    with pytest.raises(HTTPException) as exc:
        _send([_fail("1015", "Token is invalid.")])
    assert exc.value.status_code == 502
    assert "1015" in exc.value.detail


def test_poll_transient_fail_is_explained():
    get = AsyncMock(return_value=_fail("1001"))
    with patch.object(ibkr, "_flex_get", get), patch.object(ibkr.asyncio, "sleep", AsyncMock()):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(ibkr._poll_flex_statement(TOKEN, "REF42"))
    assert exc.value.status_code == 503


def test_http_error_detail_does_not_leak_the_token():
    url = ibkr.FLEX_SEND_URL.format(token=TOKEN, queryId="1")
    request = httpx.Request("GET", url)
    error = httpx.HTTPStatusError("boom " + url, request=request,
                                  response=httpx.Response(500, request=request))
    assert TOKEN not in ibkr._safe_error(error)
