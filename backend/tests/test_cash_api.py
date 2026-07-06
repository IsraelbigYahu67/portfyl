import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from models import Portfolio, Transaction
from schemas import TransactionResponse
from routers.portfolio import _build_holdings
from routers.cash import (
    create_cash, list_cash, update_cash, delete_cash, CashCreate,
    get_rates, put_rates, get_balance, RatesPayload, RateItem,
)
from tests.helpers import make_txn


def test_cash_rows_do_not_affect_holdings():
    trades = [make_txn(type="buy", shares=10, price=100, currency="USD")]
    cash = [make_txn(ticker=None, type="deposit", shares=None, price=None,
                     currency="USD", amount=5000, date=date(2024, 1, 1))]
    only_trades = _build_holdings(trades)
    with_cash = _build_holdings(trades + cash)
    assert with_cash.keys() == only_trades.keys()
    assert with_cash == only_trades


def test_cash_rows_do_not_leak_into_closed_holdings():
    """include_closed=True is the path get_holdings actually uses. Without the
    TRADE_TYPES guard, a cash `deposit` (ticker=None) creates a stray None key
    in the holdings dict, which then flows into price/FX lookups downstream."""
    trades = [make_txn(type="buy", shares=10, price=100, currency="USD")]
    cash = [
        make_txn(ticker=None, type="deposit", shares=None, price=None,
                 currency="USD", amount=5000, date=date(2024, 1, 1)),
        make_txn(ticker=None, type="withdrawal", shares=None, price=None,
                 currency="USD", amount=200, date=date(2024, 1, 2)),
        make_txn(ticker=None, type="interest", shares=None, price=None,
                 currency="USD", amount=12, date=date(2024, 1, 3)),
        make_txn(ticker=None, type="fee", shares=None, price=None,
                 currency="USD", amount=5, date=date(2024, 1, 4)),
    ]
    only_trades = _build_holdings(trades, include_closed=True)
    with_cash = _build_holdings(trades + cash, include_closed=True)
    assert None not in with_cash
    assert with_cash.keys() == only_trades.keys()
    assert with_cash == only_trades


# ---------------------------------------------------------------------------
# /api/cash CRUD router (Task 6)
# ---------------------------------------------------------------------------
# fetch_fx_to_czk hits yfinance for a live rate; mirror the pattern already
# used in tests/test_portfolio.py::TestCreateTransaction (patch the name as
# imported into the router module) so these tests stay hermetic/offline.


def test_create_and_list_cash(db_session, pid):
    with patch("routers.cash.fetch_fx_to_czk", return_value=22.5):
        create_cash(CashCreate(type="deposit", amount=1000, currency="usd", date=date(2024, 1, 1)), db_session, pid)
        create_cash(CashCreate(type="fee", amount=5, currency="USD", date=date(2024, 1, 2)), db_session, pid)

    rows = list_cash(db_session, pid)
    assert {r.type for r in rows} == {"deposit", "fee"}
    assert len(rows) == 2
    # newest first
    assert rows[0].type == "fee"
    # currency is upper-cased regardless of input casing
    assert all(r.currency == "USD" for r in rows)
    assert all(r.fx_to_czk == 22.5 for r in rows)


def test_update_cash(db_session, pid):
    with patch("routers.cash.fetch_fx_to_czk", return_value=22.5):
        created = create_cash(CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)), db_session, pid)

    with patch("routers.cash.fetch_fx_to_czk", return_value=24.0):
        updated = update_cash(
            created.id,
            CashCreate(type="withdrawal", amount=250, currency="EUR", date=date(2024, 2, 1), note="oops"),
            db_session, pid,
        )

    assert updated.id == created.id
    assert updated.type == "withdrawal"
    assert updated.amount == 250
    assert updated.currency == "EUR"
    assert updated.date == date(2024, 2, 1)
    assert updated.note == "oops"
    assert updated.fx_to_czk == 24.0


def test_delete_cash(db_session, pid):
    with patch("routers.cash.fetch_fx_to_czk", return_value=22.5):
        created = create_cash(CashCreate(type="fee", amount=5, currency="USD", date=date(2024, 1, 2)), db_session, pid)

    result = delete_cash(created.id, db_session, pid)
    assert result == {"ok": True}
    assert list_cash(db_session, pid) == []


def test_update_missing_cash_raises_404(db_session, pid):
    with pytest.raises(HTTPException) as exc_info:
        update_cash(999, CashCreate(type="fee", amount=5, currency="USD", date=date(2024, 1, 2)), db_session, pid)
    assert exc_info.value.status_code == 404


def test_delete_missing_cash_raises_404(db_session, pid):
    with pytest.raises(HTTPException) as exc_info:
        delete_cash(999, db_session, pid)
    assert exc_info.value.status_code == 404


def test_cash_is_scoped_to_portfolio(db_session, pid):
    other = Portfolio(name="Other", is_default=False)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    with patch("routers.cash.fetch_fx_to_czk", return_value=22.5):
        create_cash(CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)), db_session, pid)
        create_cash(CashCreate(type="deposit", amount=500, currency="USD", date=date(2024, 1, 1)), db_session, other.id)

    assert len(list_cash(db_session, pid)) == 1
    assert len(list_cash(db_session, other.id)) == 1

    # Can't update/delete a row that belongs to a different portfolio.
    other_row = list_cash(db_session, other.id)[0]
    with pytest.raises(HTTPException) as exc_info:
        update_cash(other_row.id, CashCreate(type="fee", amount=1, currency="USD", date=date(2024, 1, 1)), db_session, pid)
    assert exc_info.value.status_code == 404


def test_cash_row_serializes_via_transaction_response(db_session, pid):
    # A persisted cash row has ticker=None; TransactionResponse must tolerate it,
    # else GET /api/portfolio/transactions 500s for the whole portfolio (that
    # endpoint returns ALL rows for the portfolio and serializes via this schema).
    # Note: tests call routers directly, bypassing FastAPI's response_model
    # validation — so we reproduce the 500 by validating through the schema here.
    with patch("routers.cash.fetch_fx_to_czk", return_value=23.0):
        row = create_cash(CashCreate(type="deposit", amount=1000, currency="USD",
                                     date=date(2024, 1, 1)), db_session, pid)
    persisted = db_session.query(Transaction).filter(Transaction.id == row.id).first()
    # Would raise pydantic.ValidationError before the Optional fix; must succeed after.
    TransactionResponse.model_validate(persisted)


def test_cash_endpoints_refuse_trade_rows(db_session, pid):
    # PUT/DELETE cash guard on type.in_(CASH_TYPES): a trade row must be refused.
    trade = make_txn(type="buy", shares=10, price=100, currency="USD", portfolio_id=pid)
    db_session.add(trade); db_session.commit(); db_session.refresh(trade)
    with pytest.raises(HTTPException):
        update_cash(trade.id, CashCreate(type="deposit", amount=1, currency="USD", date=date(2024, 1, 1)), db_session, pid)
    with pytest.raises(HTTPException):
        delete_cash(trade.id, db_session, pid)


# ---------------------------------------------------------------------------
# Interest-rate settings + per-currency balance (Task 7)
# ---------------------------------------------------------------------------


def test_put_and_get_interest_rates(db_session, pid):
    put_rates(RatesPayload(rates=[RateItem(currency="USD", annual_rate=0.045, enabled=True)]), db_session, pid)
    rows = get_rates(db_session, pid)
    assert rows[0].currency == "USD" and rows[0].enabled is True
    assert rows[0].annual_rate == 0.045


def test_balance_endpoint_sums_flows(db_session, pid):
    # by_currency is native, and display currency == native (USD) so convert_amount
    # is a no-op — the balance endpoint never hits the network here. create_cash's
    # fetch_fx_to_czk is mocked to keep it offline (same pattern as the CRUD tests).
    with patch("routers.cash.fetch_fx_to_czk", return_value=22.5):
        create_cash(CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)), db_session, pid)
        create_cash(CashCreate(type="fee", amount=50, currency="USD", date=date(2024, 1, 2)), db_session, pid)
    res = get_balance("USD", db_session, pid)
    assert res["by_currency"]["USD"]["balance"] == 950.0
    assert res["currency"] == "USD"
    assert res["total"] == 950.0
