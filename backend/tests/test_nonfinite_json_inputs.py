"""NaN / Infinity JSON literals answer 422, never 500 (B1, decision R3).

Starlette parses request bodies with `json.loads`, which accepts the literals
NaN and Infinity. Pydantic rejects them on fields declared with
`allow_inf_nan=False`, but FastAPI's default handler then echoed the offending
value back as `input`, and the JSON response (allow_nan=False) could not render
it: the client got a 500. `main.request_validation_error_handler` fixes that.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

import main
from routers.alerts import AlertCreate, AlertUpdate
from routers.cash import CashCreate, RatesPayload
from schemas import TransactionCreate


JSON = {"content-type": "application/json"}


@pytest.fixture
def client() -> TestClient:
    """Real request models behind the real handler, without auth or a database."""
    app = FastAPI()
    app.add_exception_handler(
        RequestValidationError, main.request_validation_error_handler
    )

    @app.post("/portfolio/transactions")
    def create_transaction(txn: TransactionCreate):
        return {"ok": True}

    @app.post("/cash")
    def create_cash(body: CashCreate):
        return {"ok": True}

    @app.put("/cash/interest-rates")
    def put_rates(body: RatesPayload):
        return {"ok": True}

    @app.post("/alerts")
    def create_alert(body: AlertCreate):
        return {"ok": True}

    @app.patch("/alerts/one")
    def update_alert(body: AlertUpdate):
        return {"ok": True}

    return TestClient(app)


def test_main_app_registers_the_handler():
    assert (
        main.app.exception_handlers[RequestValidationError]
        is main.request_validation_error_handler
    )


TRANSACTION = (
    '{"ticker": "AAPL", "type": "buy", "shares": %s, "price": %s,'
    ' "currency": "USD", "date": "2026-01-02"}'
)
CASH = '{"type": "deposit", "amount": %s, "currency": "USD", "date": "2026-01-02"}'
RATES = '{"rates": [{"currency": "USD", "annual_rate": %s, "enabled": true}]}'
ALERT = '{"ticker": "AAPL", "direction": "above", "target_price": %s}'
ALERT_UPDATE = '{"target_price": %s}'


@pytest.mark.parametrize(
    ("method", "url", "body", "literal"),
    [
        ("post", "/portfolio/transactions", TRANSACTION % ("NaN", "150.0"), "NaN"),
        ("post", "/portfolio/transactions", TRANSACTION % ("10", "NaN"), "NaN"),
        ("post", "/portfolio/transactions", TRANSACTION % ("Infinity", "150.0"), "Infinity"),
        ("post", "/cash", CASH % "Infinity", "Infinity"),
        ("post", "/cash", CASH % "-Infinity", "-Infinity"),
        ("post", "/cash", CASH % "NaN", "NaN"),
        ("put", "/cash/interest-rates", RATES % "Infinity", "Infinity"),
        ("put", "/cash/interest-rates", RATES % "NaN", "NaN"),
        ("post", "/alerts", ALERT % "NaN", "NaN"),
        ("post", "/alerts", ALERT % "Infinity", "Infinity"),
        ("patch", "/alerts/one", ALERT_UPDATE % "NaN", "NaN"),
    ],
)
def test_non_finite_literal_is_422_not_500(client, method, url, body, literal):
    response = getattr(client, method)(url, content=body, headers=JSON)

    assert response.status_code == 422, literal
    detail = response.json()["detail"]
    assert detail and all("loc" in item and "msg" in item for item in detail)


def test_finite_bodies_still_pass(client):
    assert client.post(
        "/portfolio/transactions", content=TRANSACTION % ("10", "150.0"), headers=JSON
    ).status_code == 200
    assert client.post("/cash", content=CASH % "100", headers=JSON).status_code == 200
    assert client.put(
        "/cash/interest-rates", content=RATES % "0.03", headers=JSON
    ).status_code == 200
    assert client.post("/alerts", content=ALERT % "200", headers=JSON).status_code == 200


def test_ordinary_validation_errors_keep_their_shape(client):
    response = client.post("/cash", content=CASH % "-5", headers=JSON)

    assert response.status_code == 422
    item = response.json()["detail"][0]
    assert item["loc"] == ["body", "amount"]
    assert item["type"] == "greater_than"
    assert item["input"] == -5
    assert item["ctx"] == {"gt": 0.0}


def test_unserialisable_values_are_replaced():
    assert main._json_safe(float("nan")) == "nan"
    assert main._json_safe(float("inf")) == "inf"
    assert main._json_safe(ValueError("boom")) == "boom"
    assert main._json_safe({"a": [1, 2]}) == {"a": [1, 2]}
