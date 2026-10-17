from datetime import date

import httpx
import pytest

from etoro_client import ENDPOINTS, EtoroAuthError, EtoroClient, EtoroRateLimited, PAGE_SIZE


def _client(handler):
    return EtoroClient("app", "user", transport=httpx.MockTransport(handler))


def test_sends_both_keys_and_a_request_id():
    seen = []

    def handler(request):
        seen.append(dict(request.headers))
        return httpx.Response(200, json={"clientPortfolio": {"positions": []}})
    client = _client(handler)
    client.positions()
    client.positions()
    assert seen[0]["x-api-key"] == "app" and seen[0]["x-user-key"] == "user"
    assert seen[0]["x-request-id"] != seen[1]["x-request-id"]


def test_positions_reads_client_portfolio():
    def handler(request):
        assert request.url.path == ENDPOINTS["positions"]
        return httpx.Response(200, json={"clientPortfolio": {"positions": [{"positionID": 1}]}})
    assert _client(handler).positions() == [{"positionID": 1}]


def test_history_walks_yearly_windows_and_pages():
    calls = []

    def handler(request):
        window = request.url.params["minDate"]
        page = int(request.url.params["page"])
        calls.append((window, page))
        if page == 1:
            full_page = [{"positionId": f"{window}-{i}"} for i in range(PAGE_SIZE)]
            return httpx.Response(200, json=full_page)
        return httpx.Response(200, json=[{"positionId": f"{window}-last"}])
    rows = _client(handler).trade_history(date(2024, 1, 1))
    windows = sorted({window for window, _ in calls})
    assert len(windows) >= 3
    assert {page for _, page in calls} == {1, 2}
    assert len(rows) == len(windows) * (PAGE_SIZE + 1)


def test_history_deduplicates_positions_seen_in_several_windows():
    def handler(request):
        return httpx.Response(200, json=[{"positionId": 7}])
    assert len(_client(handler).trade_history(date(2024, 1, 1))) == 1


def test_instruments_resolve_exchange_and_type_descriptions():
    def handler(request):
        path = request.url.path
        if path == ENDPOINTS["instruments"]:
            assert request.url.params["instrumentIds"] == "1001,2002"
            return httpx.Response(200, json={"instrumentDisplayDatas": [
                {"instrumentID": 1001, "symbolFull": "AAPL", "exchangeID": 4, "instrumentTypeID": 5,
                 "instrumentDisplayName": "Apple"},
                {"instrumentID": 2002, "symbolFull": "BTC", "exchangeID": 8, "instrumentTypeID": 10},
            ]})
        if path == ENDPOINTS["exchanges"]:
            return httpx.Response(200, json={"exchangeInfo": [
                {"exchangeID": 4, "exchangeDescription": "Nasdaq"},
                {"exchangeID": 8, "exchangeDescription": "Digital Currency"}]})
        return httpx.Response(200, json={"instrumentTypes": [
            {"instrumentTypeID": 5, "instrumentTypeDescription": "Stocks"},
            {"instrumentTypeID": 10, "instrumentTypeDescription": "Crypto"}]})
    info = _client(handler).instruments([2002, 1001, 1001])
    assert info[1001] == {"symbol": "AAPL", "exchange": "Nasdaq", "type": "Stocks", "name": "Apple"}
    assert info[2002]["type"] == "Crypto"


def test_cash_transactions_follow_the_cursor():
    def handler(request):
        token = request.url.params.get("pageToken")
        if token is None:
            return httpx.Response(200, json={"results": [{"id": "1"}],
                                             "pagination": {"nextPageToken": "abc", "hasNext": True}})
        return httpx.Response(200, json={"results": [{"id": "2"}],
                                         "pagination": {"nextPageToken": None, "hasNext": False}})
    assert [r["id"] for r in _client(handler).cash_transactions("acc-1")] == ["1", "2"]


def test_401_raises_auth_error():
    with pytest.raises(EtoroAuthError):
        _client(lambda r: httpx.Response(401)).positions()


def test_429_raises_with_retry_after():
    with pytest.raises(EtoroRateLimited) as exc:
        _client(lambda r: httpx.Response(429, headers={"Retry-After": "12"})).positions()
    assert exc.value.retry_after == 12
