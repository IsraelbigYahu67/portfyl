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
from routers.portfolio import get_summary
from routers.analytics import sector_breakdown
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


def test_put_interest_rates_route_not_shadowed_by_cash_id():
    # PUT /{cash_id:int} must NOT shadow the literal PUT /interest-rates. Direct
    # function calls (the rest of this file) bypass routing, so assert at the
    # router level that /cash/interest-rates dispatches to put_rates.
    from starlette.routing import Match
    from routers.cash import router
    scope = {"type": "http", "method": "PUT", "path": "/cash/interest-rates"}
    full = [r for r in router.routes if r.matches(scope)[0] == Match.FULL]
    assert full, "no route matched PUT /cash/interest-rates"
    assert full[0].endpoint.__name__ == "put_rates", f"shadowed by {full[0].endpoint.__name__}"


def test_balance_total_mirrors_get_summary_basis(db_session, pid):
    # total must mirror get_summary's basis: native-summed for non-CZK display
    # (get_summary uses live_fx=1.0), converted native->CZK only when display=CZK.
    with patch("routers.cash.fetch_fx_to_czk", return_value=23.0):
        create_cash(CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)), db_session, pid)
    # display=USD: total is native (no conversion), mirroring get_summary's live_fx=1.0
    assert get_balance("USD", db_session, pid)["total"] == 1000.0
    # display=CZK: cash_amount_to_display -> convert_amount pivots USD->CZK->CZK.
    # convert_amount divides by the target's CZK rate, so keep CZK->CZK == 1.0
    # (real fetch_fx_to_czk behavior) and stub only the USD leg to 23.0.
    def _fx(ccy, on_date=None):
        return 1.0 if (ccy or "").upper() == "CZK" else 23.0
    with patch("fx.fetch_fx_to_czk", side_effect=_fx):
        res_czk = get_balance("CZK", db_session, pid)
    assert res_czk["total"] == 23000.0


def test_put_rates_upsert_is_idempotent(db_session, pid):
    # Upserting the same (pid, currency) twice must NOT duplicate rows; the second
    # call's values win.
    put_rates(RatesPayload(rates=[RateItem(currency="USD", annual_rate=0.04, enabled=False)]), db_session, pid)
    put_rates(RatesPayload(rates=[RateItem(currency="USD", annual_rate=0.05, enabled=True)]), db_session, pid)
    from models import CashInterestRate
    rows = db_session.query(CashInterestRate).filter(CashInterestRate.portfolio_id == pid,
                                                     CashInterestRate.currency == "USD").all()
    assert len(rows) == 1
    assert rows[0].annual_rate == 0.05
    assert rows[0].enabled is True


# ---------------------------------------------------------------------------
# Net worth in /portfolio/summary (Task 8)
# ---------------------------------------------------------------------------
# get_summary(currency, db, pid) with no trade-type transactions: get_holdings
# returns [] and the day-change block short-circuits on `if active_day else {}`
# (active_day is {} since _build_holdings skips cash rows), so this never hits
# yfinance/network — hermetic by construction. Only create_cash's
# fetch_fx_to_czk needs mocking (same pattern as the other CRUD tests above).


def test_summary_net_worth_adds_cash(db_session, pid):
    with patch("routers.cash.fetch_fx_to_czk", return_value=23.0):
        create_cash(CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)), db_session, pid)
    s = get_summary(currency="USD", db=db_session, pid=pid)
    assert s["cash"] == 1000.0
    assert s["net_worth"] == round(s["total_value"] + s["cash"] + s["accrued_interest"], 2)


# ---------------------------------------------------------------------------
# Cash bucket in the allocation / sector breakdown (Task 9)
# ---------------------------------------------------------------------------
# sector_breakdown(currency, db, pid) with only cash rows (no trades):
# _get_transactions is trade-guarded (TRADE_TYPES + ticker) so `transactions`
# is empty and the function takes its cash-only early-return branch — never
# touches market_data/yfinance, so this stays hermetic.


def test_allocation_includes_cash_bucket(db_session, pid):
    with patch("routers.cash.fetch_fx_to_czk", return_value=23.0):
        create_cash(CashCreate(type="deposit", amount=2000, currency="USD", date=date(2024, 1, 1)), db_session, pid)

    result = sector_breakdown(currency="USD", db=db_session, pid=pid)

    for key in ("sectors", "countries", "asset_types"):
        bucket_list = result[key]
        cash_rows = [b for b in bucket_list if b["name"] == "Cash"]
        assert len(cash_rows) == 1, f"expected exactly one Cash bucket in {key}"
        assert cash_rows[0]["value"] == 2000.0
        # Cash-only portfolio: Cash is the entire allocation for every dimension.
        assert cash_rows[0]["weight"] == 100.0
        assert round(sum(b["weight"] for b in bucket_list), 2) == 100.0


def test_allocation_cash_pct_included_in_denominator_with_holdings(db_session, pid):
    # With holdings present too, Cash must be folded into the SAME percentage
    # denominator as the sector/country/asset-type buckets (not a separate 100%).
    # Note: the cash ledger is shared with trades (signed_cash treats "buy" as
    # a cash outflow), so deposit 2000 then buy 1000 of stock -> cash balance
    # nets to 1000, matching a real brokerage cash-sweep account.
    with patch("routers.cash.fetch_fx_to_czk", return_value=23.0):
        create_cash(CashCreate(type="deposit", amount=2000, currency="USD", date=date(2024, 1, 1)), db_session, pid)

    trade = make_txn(type="buy", shares=10, price=100, currency="USD",
                      date=date(2024, 1, 2), portfolio_id=pid)
    db_session.add(trade)
    db_session.commit()

    with patch("market_data.get_infos", return_value={
        "AAPL": {"currentPrice": 100.0, "currency": "USD", "sector": "Technology", "quoteType": "EQUITY"},
    }):
        result = sector_breakdown(currency="USD", db=db_session, pid=pid)

    for key in ("sectors", "countries", "asset_types"):
        bucket_list = result[key]
        cash_rows = [b for b in bucket_list if b["name"] == "Cash"]
        assert len(cash_rows) == 1, f"expected exactly one Cash bucket in {key}"
        assert cash_rows[0]["value"] == 1000.0
        # holdings market value = 10 * 100 = 1000; cash = 1000 -> weight = 1000/2000*100
        assert cash_rows[0]["weight"] == pytest.approx(50.0, abs=0.01)
        assert round(sum(b["weight"] for b in bucket_list), 2) == 100.0
    # total_value stays holdings-only (matches get_summary's contract: net_worth = total_value + cash).
    assert result["total_value"] == 1000.0
