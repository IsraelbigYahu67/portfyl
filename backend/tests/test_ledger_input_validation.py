"""Ledger input validation (review findings N5, N9)."""
from __future__ import annotations

import inspect
from datetime import date
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from routers import portfolio
from schemas import TransactionCreate, TransactionResponse
from tests.helpers import make_txn


# --- POST /portfolio/transactions body ---------------------------------------

def _valid_body(**overrides):
    body = {
        "ticker": "AAPL", "type": "buy", "shares": 10, "price": 150.0,
        "currency": "USD", "date": "2026-01-02",
    }
    body.update(overrides)
    return body


@pytest.fixture
def client() -> TestClient:
    """FastAPI body validation of the real input model, without auth/DB deps."""
    app = FastAPI()

    @app.post("/echo")
    def echo(txn: TransactionCreate):
        return txn.model_dump(mode="json")

    return TestClient(app)


def test_create_transaction_route_uses_the_strict_input_model():
    params = inspect.signature(portfolio.create_transaction).parameters
    assert params["txn"].annotation is TransactionCreate


def test_valid_body_is_accepted_and_normalised(client):
    response = client.post("/echo", json=_valid_body(ticker="  aapl ", currency=" usd "))

    assert response.status_code == 200
    assert response.json()["ticker"] == "aapl"
    assert response.json()["currency"] == "USD"


@pytest.mark.parametrize(
    "overrides",
    [
        {"shares": 0},
        {"shares": -1},
        {"price": 0},
        {"price": -0.01},
        {"type": "split"},
        {"type": "deposit"},
        {"type": "BUY"},
        {"ticker": ""},
        {"ticker": "   "},
        {"ticker": "X" * 33},
        {"currency": ""},
        {"currency": "US"},
        {"currency": "USDX"},
        {"currency": "U$D"},
    ],
)
def test_invalid_body_is_422(client, overrides):
    assert client.post("/echo", json=_valid_body(**overrides)).status_code == 422


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("field", ["shares", "price"])
def test_non_finite_numbers_are_refused_by_the_input_model(field, value):
    # Starlette parses JSON with json.loads, which accepts the NaN / Infinity
    # literals, so the model itself has to refuse them. (The HTTP status for
    # that case is decided by the app-wide RequestValidationError handler,
    # which is outside this task: see the hand-over notes.)
    with pytest.raises(ValidationError) as exc_info:
        TransactionCreate(**_valid_body(**{field: value}))

    assert exc_info.value.errors()[0]["loc"] == (field,)


# --- GET stays tolerant of legacy rows ---------------------------------------

def test_get_transactions_still_returns_legacy_rows(db_session, pid, default_portfolio):
    db_session.add(make_txn("KO", "dividend", 5, 0.0, portfolio_id=pid))
    db_session.add(make_txn("T", "buy", 3, 12.5, portfolio_id=pid))
    db_session.commit()

    rows = portfolio.get_transactions(db=db_session, portfolio=default_portfolio)

    by_ticker = {r.ticker: TransactionResponse.model_validate(r) for r in rows}
    assert by_ticker["KO"].price == 0.0
    assert by_ticker["KO"].type == "dividend"
    assert by_ticker["T"].shares == 3


def test_response_model_accepts_values_the_input_model_refuses():
    legacy = {
        "public_id": uuid4(), "ticker": None, "type": "deposit", "shares": 0.0,
        "price": 0.0, "currency": "usd", "date": date(2026, 1, 2), "notes": None,
    }

    parsed = TransactionResponse.model_validate(legacy)

    assert parsed.type == "deposit" and parsed.currency == "usd"
    assert list(TransactionResponse.model_fields) == [
        "ticker", "type", "shares", "price", "currency", "date", "notes",
        "id", "name", "fx_to_czk",
    ]


# --- _live_to_usd ------------------------------------------------------------

class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def fx(monkeypatch):
    monkeypatch.setattr(portfolio, "_USD_FX_CACHE", {})
    monkeypatch.setattr(portfolio, "_LAST_GOOD_USD_FX", {})
    monkeypatch.setattr(portfolio, "_LAST_GOOD_FX", {})
    clock = _Clock()
    monkeypatch.setattr(portfolio, "_usd_fx_clock", clock)
    return clock


def _quotes(monkeypatch, quotes: dict[str, float | None]):
    """market_data.get_info stub: symbol -> price; None or missing -> provider outage."""
    calls: list[str] = []

    def get_info(symbol):
        calls.append(symbol)
        price = quotes.get(symbol)
        if price is None:
            raise RuntimeError("yahoo down")
        return {"regularMarketPrice": price}

    monkeypatch.setattr(portfolio.market_data, "get_info", get_info)
    monkeypatch.setattr(portfolio, "fetch_fx_to_czk", lambda *_: None)
    return calls


def test_live_to_usd_uses_the_direct_quote_and_caches_it(fx, monkeypatch):
    calls = _quotes(monkeypatch, {"EURUSD=X": 1.1})

    assert portfolio._live_to_usd("eur") == 1.1
    assert portfolio._live_to_usd("EUR") == 1.1
    assert calls == ["EURUSD=X"]


def test_live_to_usd_cache_expires(fx, monkeypatch):
    quotes = {"EURUSD=X": 1.1}
    calls = _quotes(monkeypatch, quotes)
    assert portfolio._live_to_usd("EUR") == 1.1

    fx.now += portfolio._USD_FX_TTL_SECONDS - 1
    quotes["EURUSD=X"] = 1.2
    assert portfolio._live_to_usd("EUR") == 1.1  # still fresh
    fx.now += 2
    assert portfolio._live_to_usd("EUR") == 1.2  # expired, re-fetched
    assert calls == ["EURUSD=X", "EURUSD=X"]


def test_live_to_usd_keeps_last_known_good_during_an_outage(fx, monkeypatch, caplog):
    quotes = {"EURUSD=X": 1.1}
    _quotes(monkeypatch, quotes)
    assert portfolio._live_to_usd("EUR") == 1.1

    quotes["EURUSD=X"] = None
    fx.now += portfolio._USD_FX_TTL_SECONDS + 1
    with caplog.at_level("WARNING", logger="portfyl.fx"):
        assert portfolio._live_to_usd("EUR") == 1.1
    assert "last known good" in caplog.text


def test_live_to_usd_retries_the_provider_soon_after_a_fallback(fx, monkeypatch):
    quotes = {"EURUSD=X": 1.1}
    _quotes(monkeypatch, quotes)
    portfolio._live_to_usd("EUR")
    quotes["EURUSD=X"] = None
    fx.now += portfolio._USD_FX_TTL_SECONDS + 1
    assert portfolio._live_to_usd("EUR") == 1.1

    quotes["EURUSD=X"] = 1.3
    fx.now += 61
    assert portfolio._live_to_usd("EUR") == 1.3


def test_live_to_usd_cold_start_pivots_through_czk(fx, monkeypatch):
    # No EURUSD quote at all; EURCZK and USDCZK exist.
    _quotes(monkeypatch, {"EURCZK=X": 24.0, "USDCZK=X": 20.0})

    assert portfolio._live_to_usd("EUR") == pytest.approx(1.2)


def test_live_to_usd_czk_uses_the_pivot(fx, monkeypatch):
    _quotes(monkeypatch, {"USDCZK=X": 20.0})

    assert portfolio._live_to_usd("CZK") == pytest.approx(0.05)


def test_live_to_usd_without_any_source_warns_and_does_not_cache(fx, monkeypatch, caplog):
    quotes: dict[str, float | None] = {}
    calls = _quotes(monkeypatch, quotes)

    with caplog.at_level("WARNING", logger="portfyl.fx"):
        assert portfolio._live_to_usd("EUR") == 1.0
    assert "EUR→USD" in caplog.text
    assert portfolio._USD_FX_CACHE == {} and portfolio._LAST_GOOD_USD_FX == {}

    # The made-up 1.0 is not remembered: the next call tries again and recovers.
    quotes["EURUSD=X"] = 1.1
    assert portfolio._live_to_usd("EUR") == 1.1
    assert calls.count("EURUSD=X") == 2


def test_live_to_usd_ignores_non_finite_quotes(fx, monkeypatch):
    _quotes(monkeypatch, {"EURUSD=X": float("nan"), "EURCZK=X": 24.0, "USDCZK=X": 20.0})

    assert portfolio._live_to_usd("EUR") == pytest.approx(1.2)


def test_live_to_usd_usd_is_one_without_lookups(fx, monkeypatch):
    calls = _quotes(monkeypatch, {})

    assert portfolio._live_to_usd("USD") == 1.0
    assert portfolio._live_to_usd(None) == 1.0
    assert calls == []
