import json

import httpx
import pytest

from importers.instruments import (
    DefaultInstrumentResolver, InstrumentRef, unresolved_errors, yahoo_symbol,
)
from importers.openfigi import OpenFigiClient, OpenFigiUnavailable


@pytest.mark.parametrize("symbol, venue, expected", [
    ("AAPL", "US", "AAPL"),
    ("BRK B", "US", "BRK-B"),
    ("BRK.B", "US", "BRK-B"),
    ("VWCE", "XETRA", "VWCE.DE"),
    ("VUSA", "LSE", "VUSA.L"),
    ("ASML", "AMSTERDAM", "ASML.AS"),
    ("CEZ", "PRAGUE", "CEZ.PR"),
    ("700", "HONGKONG", "0700.HK"),
])
def test_yahoo_symbol(symbol, venue, expected):
    assert yahoo_symbol(symbol, venue) == expected


def test_symbol_and_known_venue_needs_no_network():
    resolver = DefaultInstrumentResolver(figi=None)
    ref = InstrumentRef(symbol="VWCE", venue="XETRA", isin="IE00BK5BQT80")
    assert resolver.resolve_many([ref]) == {ref: "VWCE.DE"}


def _figi(handler):
    return OpenFigiClient(api_key=None, transport=httpx.MockTransport(handler))


def test_isin_resolved_via_openfigi_with_venue_filter():
    def handler(request):
        [job] = json.loads(request.read())
        assert job == {"idType": "ID_ISIN", "idValue": "IE00BK5BQT80", "exchCode": "GY"}
        return httpx.Response(200, json=[{"data": [
            {"ticker": "VWCE", "exchCode": "GY", "marketSector": "Equity"},
        ]}])
    resolver = DefaultInstrumentResolver(figi=_figi(handler))
    ref = InstrumentRef(isin="IE00BK5BQT80", venue="XETRA")
    assert resolver.resolve_many([ref]) == {ref: "VWCE.DE"}


def test_wrong_exchange_candidate_is_ignored():
    def handler(request):
        return httpx.Response(200, json=[{"data": [
            {"ticker": "VWRA", "exchCode": "LN", "marketSector": "Equity"},
        ]}])
    resolver = DefaultInstrumentResolver(figi=_figi(handler))
    assert resolver.resolve_many([InstrumentRef(isin="IE00BK5BQT80", venue="XETRA")]) == {}


def test_unresolved_instrument_is_error():
    def handler(request):
        return httpx.Response(200, json=[{"warning": "No identifier found."}])
    resolver = DefaultInstrumentResolver(figi=_figi(handler))
    ref = InstrumentRef(isin="XS0000000000", venue="XETRA", name="Obscure ETF")
    resolved = resolver.resolve_many([ref])
    assert resolved == {}
    [error] = unresolved_errors([ref], resolved)
    assert "XS0000000000" in error and "Obscure ETF" in error


def test_openfigi_rate_limit_raises_unavailable():
    resolver = DefaultInstrumentResolver(
        figi=_figi(lambda r: httpx.Response(429, headers={"Retry-After": "60"}))
    )
    with pytest.raises(OpenFigiUnavailable):
        resolver.resolve_many([InstrumentRef(isin="IE00BK5BQT80", venue="XETRA")])


def test_openfigi_short_response_raises_unavailable():
    resolver = DefaultInstrumentResolver(figi=_figi(lambda r: httpx.Response(200, json=[])))
    with pytest.raises(OpenFigiUnavailable):
        resolver.resolve_many([InstrumentRef(isin="IE00BK5BQT80", venue="XETRA")])


def test_results_are_cached_between_calls():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(200, json=[{"data": [{"ticker": "VWCE", "exchCode": "GY", "marketSector": "Equity"}]}])
    resolver = DefaultInstrumentResolver(figi=_figi(handler))
    ref = InstrumentRef(isin="IE00BK5BQT80", venue="XETRA")
    resolver.resolve_many([ref])
    resolver.resolve_many([ref])
    assert len(calls) == 1


def test_refs_differing_only_by_name_share_one_lookup():
    sizes = []

    def handler(request):
        jobs = json.loads(request.read())
        sizes.append(len(jobs))
        return httpx.Response(200, json=[{"data": [{"ticker": "VWCE", "exchCode": "GY"}]}] * len(jobs))
    resolver = DefaultInstrumentResolver(figi=_figi(handler))
    a = InstrumentRef(isin="IE00BK5BQT80", venue="XETRA", name="Vanguard")
    b = InstrumentRef(isin="IE00BK5BQT80", venue="XETRA", name="VANGUARD FTSE ALL-WORLD")
    assert resolver.resolve_many([a, b]) == {a: "VWCE.DE", b: "VWCE.DE"}
    assert sizes == [1]


def test_batches_respect_job_limit():
    sizes = []

    def handler(request):
        jobs = json.loads(request.read())
        sizes.append(len(jobs))
        return httpx.Response(200, json=[{"warning": "No identifier found."}] * len(jobs))
    resolver = DefaultInstrumentResolver(figi=_figi(handler))
    refs = [InstrumentRef(isin=f"US00000000{i:02d}", venue="US") for i in range(23)]
    resolver.resolve_many(refs)
    assert sizes == [10, 10, 3]
