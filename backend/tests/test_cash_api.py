import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date, datetime, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

import pandas as pd

from models import BrokerBalance, Portfolio, Transaction
from schemas import TransactionResponse
from routers.portfolio import _build_holdings
from routers.cash import (
    create_cash, list_cash, update_cash, delete_cash, CashCreate,
    get_rates, put_rates, get_balance, get_reconciliation, RatesPayload, RateItem,
)
from routers.portfolio import get_summary, get_transactions, get_performance
from routers.analytics import (
    sector_breakdown,
    _basket_daily_returns,
    _build_value_cashflow_series,
    _lifetime_money_weighted,
    _modified_dietz_daily_returns,
)
from cash_ledger import has_external_cashflows, TRADE_TYPES
from tests.helpers import TEST_WORKSPACE_ID, make_txn


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


def test_create_and_list_cash(db_session, pid, default_portfolio):
    with patch("routers.cash.fetch_fx_to_czk", return_value=22.5):
        create_cash(CashCreate(type="deposit", amount=1000, currency="usd", date=date(2024, 1, 1)), db_session, default_portfolio)
        create_cash(CashCreate(type="fee", amount=5, currency="USD", date=date(2024, 1, 2)), db_session, default_portfolio)

    rows = list_cash(db_session, default_portfolio)
    assert {r.type for r in rows} == {"deposit", "fee"}
    assert len(rows) == 2
    # newest first
    assert rows[0].type == "fee"
    # currency is upper-cased regardless of input casing
    assert all(r.currency == "USD" for r in rows)
    assert all(r.fx_to_czk == 22.5 for r in rows)


def test_update_cash(db_session, pid, default_portfolio):
    with patch("routers.cash.fetch_fx_to_czk", return_value=22.5):
        created = create_cash(CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)), db_session, default_portfolio)

    with patch("routers.cash.fetch_fx_to_czk", return_value=24.0):
        updated = update_cash(
            created.id,
            CashCreate(type="withdrawal", amount=250, currency="EUR", date=date(2024, 2, 1), note="oops"),
            db_session, default_portfolio,
        )

    assert updated.id == created.id
    assert updated.type == "withdrawal"
    assert updated.amount == 250
    assert updated.currency == "EUR"
    assert updated.date == date(2024, 2, 1)
    assert updated.note == "oops"
    assert updated.fx_to_czk == 24.0


def test_delete_cash(db_session, pid, default_portfolio):
    with patch("routers.cash.fetch_fx_to_czk", return_value=22.5):
        created = create_cash(CashCreate(type="fee", amount=5, currency="USD", date=date(2024, 1, 2)), db_session, default_portfolio)

    result = delete_cash(created.id, db_session, default_portfolio)
    assert result == {"ok": True}
    assert list_cash(db_session, default_portfolio) == []


def test_cash_crud_rejects_broker_managed_rows(db_session, pid, default_portfolio):
    row = make_txn(
        ticker=None, type="deposit", shares=0, price=0, amount=1000,
        currency="USD", date=date(2024, 1, 1), portfolio_id=pid,
        source="t212_api",
    )
    db_session.add(row)
    db_session.commit()

    with pytest.raises(HTTPException) as update_error:
        update_cash(
            row.public_id,
            CashCreate(
                type="withdrawal", amount=250, currency="USD",
                date=date(2024, 2, 1),
            ),
            db_session,
            default_portfolio,
        )
    with pytest.raises(HTTPException) as delete_error:
        delete_cash(row.public_id, db_session, default_portfolio)

    assert update_error.value.status_code == 409
    assert delete_error.value.status_code == 409
    persisted = db_session.query(Transaction).filter_by(id=row.id).one()
    assert persisted.type == "deposit"
    assert persisted.amount == 1000


def test_update_missing_cash_raises_404(db_session, pid, default_portfolio):
    with pytest.raises(HTTPException) as exc_info:
        update_cash(uuid4(), CashCreate(type="fee", amount=5, currency="USD", date=date(2024, 1, 2)), db_session, default_portfolio)
    assert exc_info.value.status_code == 404


def test_delete_missing_cash_raises_404(db_session, pid, default_portfolio):
    with pytest.raises(HTTPException) as exc_info:
        delete_cash(uuid4(), db_session, default_portfolio)
    assert exc_info.value.status_code == 404


def test_cash_is_scoped_to_portfolio(db_session, pid, default_portfolio):
    other = Portfolio(workspace_id=TEST_WORKSPACE_ID, name="Other", is_default=False)
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)

    with patch("routers.cash.fetch_fx_to_czk", return_value=22.5):
        create_cash(CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)), db_session, default_portfolio)
        create_cash(CashCreate(type="deposit", amount=500, currency="USD", date=date(2024, 1, 1)), db_session, other)

    assert len(list_cash(db_session, default_portfolio)) == 1
    assert len(list_cash(db_session, other)) == 1

    # Can't update/delete a row that belongs to a different portfolio.
    other_row = list_cash(db_session, other)[0]
    with pytest.raises(HTTPException) as exc_info:
        update_cash(other_row.id, CashCreate(type="fee", amount=1, currency="USD", date=date(2024, 1, 1)), db_session, default_portfolio)
    assert exc_info.value.status_code == 404


def test_cash_row_serializes_via_transaction_response(db_session, pid, default_portfolio):
    # A persisted cash row has ticker=None; TransactionResponse must tolerate it,
    # else GET /api/portfolio/transactions 500s for the whole portfolio (that
    # endpoint returns ALL rows for the portfolio and serializes via this schema).
    # Note: tests call routers directly, bypassing FastAPI's response_model
    # validation — so we reproduce the 500 by validating through the schema here.
    with patch("routers.cash.fetch_fx_to_czk", return_value=23.0):
        row = create_cash(CashCreate(type="deposit", amount=1000, currency="USD",
                                     date=date(2024, 1, 1)), db_session, default_portfolio)
    persisted = db_session.query(Transaction).filter(Transaction.public_id == row.id).first()
    # Would raise pydantic.ValidationError before the Optional fix; must succeed after.
    TransactionResponse.model_validate(persisted)


def test_cash_endpoints_refuse_trade_rows(db_session, pid, default_portfolio):
    # PUT/DELETE cash guard on type.in_(CASH_TYPES): a trade row must be refused.
    trade = make_txn(type="buy", shares=10, price=100, currency="USD", portfolio_id=pid)
    db_session.add(trade); db_session.commit(); db_session.refresh(trade)
    with pytest.raises(HTTPException):
        update_cash(trade.public_id, CashCreate(type="deposit", amount=1, currency="USD", date=date(2024, 1, 1)), db_session, default_portfolio)
    with pytest.raises(HTTPException):
        delete_cash(trade.public_id, db_session, default_portfolio)


# ---------------------------------------------------------------------------
# GET /api/portfolio/transactions excludes cash rows (FIX A)
# ---------------------------------------------------------------------------
# Cash rows (ticker=None) belong to the Cash ledger, not the Transactions page.
# Un-filtered, they used to leak in as blank rows and crash the page's
# ticker-filter (`t.ticker.toLowerCase()` on null).


def test_get_transactions_excludes_cash_rows(db_session, pid, default_portfolio):
    trade = make_txn(type="buy", shares=10, price=100, currency="USD", portfolio_id=pid)
    db_session.add(trade)
    db_session.commit()

    with patch("routers.cash.fetch_fx_to_czk", return_value=23.0):
        create_cash(CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)), db_session, default_portfolio)

    rows = get_transactions(db_session, default_portfolio)

    assert len(rows) == 1
    assert rows[0].ticker == "AAPL"
    assert rows[0].type == "buy"
    assert all(r.ticker is not None for r in rows)
    assert all(r.type in TRADE_TYPES for r in rows)


# ---------------------------------------------------------------------------
# Interest-rate settings + per-currency balance (Task 7)
# ---------------------------------------------------------------------------


def test_put_and_get_interest_rates(db_session, pid, default_portfolio):
    put_rates(RatesPayload(rates=[RateItem(currency="USD", annual_rate=0.045, enabled=True)]), db_session, default_portfolio)
    rows = get_rates(db_session, default_portfolio)
    assert rows[0].currency == "USD" and rows[0].enabled is True
    assert rows[0].annual_rate == 0.045


def test_balance_endpoint_sums_flows(db_session, pid, default_portfolio):
    # by_currency is native, and display currency == native (USD) so convert_amount
    # is a no-op — the balance endpoint never hits the network here. create_cash's
    # fetch_fx_to_czk is mocked to keep it offline (same pattern as the CRUD tests).
    with patch("routers.cash.fetch_fx_to_czk", return_value=22.5):
        create_cash(CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)), db_session, default_portfolio)
        create_cash(CashCreate(type="fee", amount=50, currency="USD", date=date(2024, 1, 2)), db_session, default_portfolio)
    res = get_balance("USD", db_session, default_portfolio)
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


def test_balance_total_mirrors_get_summary_basis(db_session, pid, default_portfolio):
    # total must mirror get_summary's basis: native-summed for non-CZK display
    # (get_summary uses live_fx=1.0), converted native->CZK only when display=CZK.
    with patch("routers.cash.fetch_fx_to_czk", return_value=23.0):
        create_cash(CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)), db_session, default_portfolio)
    # display=USD: total is native (no conversion), mirroring get_summary's live_fx=1.0
    assert get_balance("USD", db_session, default_portfolio)["total"] == 1000.0
    # display=CZK: cash_amount_to_display -> convert_amount pivots USD->CZK->CZK.
    # convert_amount divides by the target's CZK rate, so keep CZK->CZK == 1.0
    # (real fetch_fx_to_czk behavior) and stub only the USD leg to 23.0.
    def _fx(ccy, on_date=None):
        return 1.0 if (ccy or "").upper() == "CZK" else 23.0
    with patch("fx.fetch_fx_to_czk", side_effect=_fx):
        res_czk = get_balance("CZK", db_session, default_portfolio)
    assert res_czk["total"] == 23000.0


def test_put_rates_upsert_is_idempotent(db_session, pid, default_portfolio):
    # Upserting the same (pid, currency) twice must NOT duplicate rows; the second
    # call's values win.
    put_rates(RatesPayload(rates=[RateItem(currency="USD", annual_rate=0.04, enabled=False)]), db_session, default_portfolio)
    put_rates(RatesPayload(rates=[RateItem(currency="USD", annual_rate=0.05, enabled=True)]), db_session, default_portfolio)
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


def test_summary_net_worth_adds_cash(db_session, pid, default_portfolio):
    # Deposit present -> has_external_cashflows True -> cash is surfaced. New
    # folded semantic: "cash" already includes accrued interest (0 here, no
    # rate configured), so net_worth = total_value + cash (no separate +accrued).
    with patch("routers.cash.fetch_fx_to_czk", return_value=23.0):
        create_cash(CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)), db_session, default_portfolio)
    s = get_summary(currency="USD", db=db_session, portfolio=default_portfolio)
    assert s["cash"] == 1000.0
    assert s["net_worth"] == round(s["total_value"] + s["cash"], 2)


def test_summary_no_cash_when_no_deposits(db_session, pid, default_portfolio):
    # Trade-only portfolio (no deposit/withdrawal rows) -> guard active:
    # cash is NOT surfaced at all, net_worth == total_value. Mock market-data /
    # day-change lookups so this stays hermetic (no live yfinance calls) --
    # an open position otherwise drives get_summary's day-change block into a
    # real yf.download for a single ticker.
    trade = make_txn(type="buy", shares=10, price=100, currency="USD", portfolio_id=pid)
    db_session.add(trade)
    db_session.commit()

    with patch("market_data.get_infos", return_value={
            "AAPL": {"currentPrice": 100.0, "currency": "USD"},
        }), \
         patch("routers.portfolio.yf.download", return_value=pd.DataFrame()):
        s = get_summary(currency="USD", db=db_session, portfolio=default_portfolio)

    assert s["cash"] == 0.0
    assert s["net_worth"] == s["total_value"]


def test_summary_uses_current_broker_cash_without_csv_cash_rows(
    db_session, pid, default_portfolio
):
    db_session.add(BrokerBalance(
        workspace_id=default_portfolio.workspace_id,
        portfolio_id=pid,
        broker="trading212",
        base_currency="USD",
        cash=1382.17,
        cash_by_currency='{"USD": 1382.17}',
        as_of=date(2026, 9, 20),
    ))
    db_session.commit()

    s = get_summary(currency="USD", db=db_session, portfolio=default_portfolio)

    assert s["cash"] == pytest.approx(1382.17)
    assert s["accrued_interest"] == 0.0
    assert s["net_worth"] == pytest.approx(s["total_value"] + 1382.17)
    assert s["cash_source"] == "broker"
    assert s["cash_as_of"] == "2026-09-20"


def test_summary_broker_cash_overrides_older_ledger_balance(
    db_session, pid, default_portfolio
):
    with patch("routers.cash.fetch_fx_to_czk", return_value=23.0):
        create_cash(
            CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)),
            db_session,
            default_portfolio,
        )
    db_session.add(BrokerBalance(
        workspace_id=default_portfolio.workspace_id,
        portfolio_id=pid,
        broker="trading212",
        base_currency="USD",
        cash=250.0,
        as_of=date(2026, 9, 20),
    ))
    db_session.commit()

    s = get_summary(currency="USD", db=db_session, portfolio=default_portfolio)

    assert s["cash"] == 250.0
    assert s["cash_source"] == "broker"


# ---------------------------------------------------------------------------
# Cash reconciliation: broker snapshot vs. recorded ledger (P0)
# ---------------------------------------------------------------------------


def test_reconciliation_unavailable_without_broker_balance(db_session, pid, default_portfolio):
    with patch("routers.cash.fetch_fx_to_czk", return_value=1.0):
        create_cash(
            CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)),
            db_session,
            default_portfolio,
        )

    result = get_reconciliation(currency="USD", db=db_session, portfolio=default_portfolio)

    assert result.broker_amount is None
    assert result.broker_currency is None
    assert result.broker_as_of is None
    assert result.broker_updated_at is None
    assert result.ledger_amount == pytest.approx(1000.0)
    assert result.difference is None
    assert result.tolerance == 1.0
    assert result.status == "unavailable"


def test_reconciliation_matched_within_tolerance(db_session, pid, default_portfolio):
    with patch("routers.cash.fetch_fx_to_czk", return_value=1.0):
        create_cash(
            CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)),
            db_session,
            default_portfolio,
        )
    db_session.add(BrokerBalance(
        workspace_id=default_portfolio.workspace_id,
        portfolio_id=pid,
        broker="trading212",
        base_currency="USD",
        cash=1000.5,
        as_of=date(2026, 9, 20),
        updated_at=datetime(2026, 9, 20, 10, 0, 0),
    ))
    db_session.commit()

    result = get_reconciliation(currency="USD", db=db_session, portfolio=default_portfolio)

    assert result.broker_amount == pytest.approx(1000.5)
    assert result.broker_currency == "USD"
    assert result.broker_as_of == date(2026, 9, 20)
    assert result.broker_updated_at == "2026-09-20T10:00:00"
    assert result.ledger_amount == pytest.approx(1000.0)
    assert result.difference == pytest.approx(0.5)
    assert result.tolerance == 1.0
    assert result.status == "matched"


def test_reconciliation_different_outside_tolerance(db_session, pid, default_portfolio):
    with patch("routers.cash.fetch_fx_to_czk", return_value=1.0):
        create_cash(
            CashCreate(type="deposit", amount=1000, currency="USD", date=date(2024, 1, 1)),
            db_session,
            default_portfolio,
        )
    db_session.add(BrokerBalance(
        workspace_id=default_portfolio.workspace_id,
        portfolio_id=pid,
        broker="trading212",
        base_currency="USD",
        cash=1500.0,
        as_of=date(2026, 9, 20),
    ))
    db_session.commit()

    result = get_reconciliation(currency="USD", db=db_session, portfolio=default_portfolio)

    assert result.difference == pytest.approx(500.0)
    assert result.status == "different"


def test_reconciliation_no_ledger_history_when_broker_present_but_no_cashflows(db_session, pid, default_portfolio):
    """No cash rows at all is a legitimate ledger state (e.g. a brand-new
    broker-only portfolio) -- it must not be conflated with 'unavailable',
    which means no BROKER snapshot exists, nor reported as 'different' (a
    misleading verdict when there is nothing meaningful to compare yet)."""
    db_session.add(BrokerBalance(
        workspace_id=default_portfolio.workspace_id,
        portfolio_id=pid,
        broker="trading212",
        base_currency="USD",
        cash=250.0,
        as_of=date(2026, 9, 20),
    ))
    db_session.commit()

    result = get_reconciliation(currency="USD", db=db_session, portfolio=default_portfolio)

    assert result.ledger_amount == 0.0
    assert result.broker_amount == pytest.approx(250.0)
    assert result.difference is None
    assert result.status == "no_ledger_history"


def test_reconciliation_no_ledger_history_ignores_trade_only_cash_outflow(db_session, pid, default_portfolio):
    """A Trading 212 sync imports orders/dividends but never deposit/withdrawal
    rows (see test_sync_persists_current_cash_snapshot_without_cash_transactions
    in test_broker.py) -- a buy-only ledger must not report a large phantom
    negative 'different' figure just because signed_cash treats buys as a
    cash outflow. This is the exact scenario that motivated this status."""
    trade = make_txn(type="buy", shares=10, price=100, currency="USD", portfolio_id=pid)
    db_session.add(trade)
    db_session.add(BrokerBalance(
        workspace_id=default_portfolio.workspace_id,
        portfolio_id=pid,
        broker="trading212",
        base_currency="USD",
        cash=250.0,
        as_of=date(2026, 9, 20),
    ))
    db_session.commit()

    result = get_reconciliation(currency="USD", db=db_session, portfolio=default_portfolio)

    assert result.status == "no_ledger_history"
    assert result.broker_amount == pytest.approx(250.0)
    assert result.ledger_amount == 0.0
    assert result.difference is None


# ---------------------------------------------------------------------------
# Cash bucket in the allocation / sector breakdown (Task 9)
# ---------------------------------------------------------------------------
# sector_breakdown(currency, db, pid) with only cash rows (no trades):
# _get_transactions is trade-guarded (TRADE_TYPES + ticker) so `transactions`
# is empty and the function takes its cash-only early-return branch — never
# touches market_data/yfinance, so this stays hermetic.


def test_allocation_includes_cash_bucket(db_session, pid, default_portfolio):
    with patch("routers.cash.fetch_fx_to_czk", return_value=23.0):
        create_cash(CashCreate(type="deposit", amount=2000, currency="USD", date=date(2024, 1, 1)), db_session, default_portfolio)

    result = sector_breakdown(currency="USD", db=db_session, portfolio=default_portfolio)

    for key in ("sectors", "asset_types"):
        bucket_list = result[key]
        cash_rows = [b for b in bucket_list if b["name"] == "Cash"]
        assert len(cash_rows) == 1, f"expected exactly one Cash bucket in {key}"
        assert cash_rows[0]["value"] == 2000.0
        # Cash-only portfolio: Cash is the entire allocation for these dimensions.
        assert cash_rows[0]["weight"] == 100.0
        assert round(sum(b["weight"] for b in bucket_list), 2) == 100.0
    # Country dimension never carries Cash — cash has no country, so a
    # cash-only portfolio has an empty country breakdown.
    assert result["countries"] == []


def test_allocation_uses_current_broker_cash_without_csv_cash_rows(
    db_session, pid, default_portfolio
):
    db_session.add(BrokerBalance(
        workspace_id=default_portfolio.workspace_id,
        portfolio_id=pid,
        broker="trading212",
        base_currency="USD",
        cash=2000.0,
        cash_by_currency='{"USD": 2000.0}',
        as_of=date(2026, 9, 20),
    ))
    db_session.commit()

    result = sector_breakdown(currency="USD", db=db_session, portfolio=default_portfolio)

    for key in ("sectors", "asset_types", "currencies"):
        assert result[key] == [{"name": "Cash" if key != "currencies" else "USD",
                                "value": 2000.0, "weight": 100.0, "profit": None}]
    assert result["countries"] == []


def test_allocation_cash_pct_included_in_denominator_with_holdings(db_session, pid, default_portfolio):
    # With holdings present too, Cash must be folded into the SAME percentage
    # denominator as the sector/country/asset-type buckets (not a separate 100%).
    # Note: the cash ledger is shared with trades (signed_cash treats "buy" as
    # a cash outflow), so deposit 2000 then buy 1000 of stock -> cash balance
    # nets to 1000, matching a real brokerage cash-sweep account.
    with patch("routers.cash.fetch_fx_to_czk", return_value=23.0):
        create_cash(CashCreate(type="deposit", amount=2000, currency="USD", date=date(2024, 1, 1)), db_session, default_portfolio)

    trade = make_txn(type="buy", shares=10, price=100, currency="USD",
                      date=date(2024, 1, 2), portfolio_id=pid)
    db_session.add(trade)
    db_session.commit()

    with patch("market_data.get_infos", return_value={
        "AAPL": {"currentPrice": 100.0, "currency": "USD", "sector": "Technology", "quoteType": "EQUITY"},
    }):
        result = sector_breakdown(currency="USD", db=db_session, portfolio=default_portfolio)

    for key in ("sectors", "asset_types"):
        bucket_list = result[key]
        cash_rows = [b for b in bucket_list if b["name"] == "Cash"]
        assert len(cash_rows) == 1, f"expected exactly one Cash bucket in {key}"
        assert cash_rows[0]["value"] == 1000.0
        # holdings market value = 10 * 100 = 1000; cash = 1000 -> weight = 1000/2000*100
        assert cash_rows[0]["weight"] == pytest.approx(50.0, abs=0.01)
        assert round(sum(b["weight"] for b in bucket_list), 2) == 100.0
    # Countries: no Cash slice; weights renormalize over holdings alone.
    countries = result["countries"]
    assert all(b["name"] != "Cash" for b in countries)
    assert round(sum(b["weight"] for b in countries), 2) == pytest.approx(100.0, abs=0.01)
    # total_value stays holdings-only (matches get_summary's contract: net_worth = total_value + cash).
    assert result["total_value"] == 1000.0


def test_allocation_no_cash_bucket_without_deposits(db_session, pid, default_portfolio):
    # Trade-only portfolio (no deposit/withdrawal rows) -> guard active: NO Cash
    # bucket in any dimension, weights sum to ~100 across holdings alone (same
    # contract as before the cash model).
    trade = make_txn(type="buy", shares=10, price=100, currency="USD",
                      date=date(2024, 1, 2), portfolio_id=pid)
    db_session.add(trade)
    db_session.commit()

    with patch("market_data.get_infos", return_value={
        "AAPL": {"currentPrice": 100.0, "currency": "USD", "sector": "Technology", "quoteType": "EQUITY"},
    }):
        result = sector_breakdown(currency="USD", db=db_session, portfolio=default_portfolio)

    for key in ("sectors", "countries", "asset_types"):
        bucket_list = result[key]
        assert all(b["name"] != "Cash" for b in bucket_list)
        assert round(sum(b["weight"] for b in bucket_list), 2) == pytest.approx(100.0, abs=0.01)


# ---------------------------------------------------------------------------
# Returns integration: deposits/withdrawals as external cashflows (Task 10)
# ---------------------------------------------------------------------------
# _build_value_cashflow_series / _lifetime_money_weighted are the real entry
# points /risk-metrics (and, for the V/C series, /analytics/benchmarks/
# comparison) call. They're exercised directly here (mirroring how
# test_analytics.py calls other private analytics helpers directly) with a
# mocked price panel + ticker-currency lookup so no network is hit. All
# amounts are USD, so _live_to_usd short-circuits (routers/portfolio.py:562,
# `if c == "USD": return 1.0`) without needing a mock either. "today" is
# frozen so the XIRR figure -- which anchors its final flow on date.today() --
# is a deterministic regression pin instead of drifting with the calendar.


class _FrozenDate(date):
    @classmethod
    def today(cls):
        return date(2024, 2, 1)


@pytest.mark.parametrize("with_deposit", [False, True])
def test_lifetime_dividends_use_paid_cash(with_deposit, pid):
    dividend = make_txn("AAPL", "dividend", 10, 1.0, currency="USD",
                        date=date(2024, 1, 2), portfolio_id=pid)
    dividend.cash_amount = 8.5
    dividend.cash_currency = "USD"
    txns = [dividend]
    if with_deposit:
        txns.insert(0, make_txn(ticker=None, type="deposit", shares=0, price=0,
                                amount=100, currency="USD", date=date(2024, 1, 1),
                                portfolio_id=pid))

    with patch("routers.analytics.date", _FrozenDate):
        lifetime = _lifetime_money_weighted(txns, pd.Series([100.0]))

    assert lifetime["dividends"] == pytest.approx(8.5)


def _mock_price_panel(index, closes):
    return pd.DataFrame({"Close": closes}, index=index)


def test_value_series_orders_same_day_position_events_by_execution_time(pid):
    sell = make_txn(
        "AAPL", "sell", 1, 110.0, currency="USD",
        date=date(2024, 1, 1), portfolio_id=pid,
    )
    sell.executed_at = datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc)
    buy = make_txn(
        "AAPL", "buy", 1, 100.0, currency="USD",
        date=date(2024, 1, 1), portfolio_id=pid,
    )
    buy.executed_at = datetime(2024, 1, 1, 15, 0, tzinfo=timezone.utc)
    idx = pd.date_range("2024-01-01", periods=2, freq="D")

    with patch("routers.analytics.yf.download", return_value=_mock_price_panel(idx, [100, 105])), \
         patch("routers.analytics.market_data.get_infos", return_value={"AAPL": {"currency": "USD"}}):
        value, cashflow, _ = _build_value_cashflow_series([buy, sell], date(2024, 1, 1))

    assert value.tolist() == pytest.approx([100, 105])
    assert cashflow.tolist() == pytest.approx([100, 0])


def test_lifetime_metrics_order_same_day_trades_by_execution_time(pid):
    sell = make_txn(
        "AAPL", "sell", 1, 110.0, currency="USD",
        date=date(2024, 1, 1), portfolio_id=pid,
    )
    sell.executed_at = datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc)
    buy = make_txn(
        "AAPL", "buy", 1, 100.0, currency="USD",
        date=date(2024, 1, 1), portfolio_id=pid,
    )
    buy.executed_at = datetime(2024, 1, 1, 15, 0, tzinfo=timezone.utc)

    with patch("routers.analytics.date", _FrozenDate):
        lifetime = _lifetime_money_weighted([buy, sell], pd.Series([105.0]))

    assert lifetime["total_invested"] == pytest.approx(100.0)
    assert lifetime["realized_pnl"] == pytest.approx(0.0)
    assert lifetime["unrealized_pnl"] == pytest.approx(5.0)
    assert lifetime["net_profit"] == pytest.approx(5.0)


def test_returns_unchanged_without_cash(db_session, pid):
    """Fallback: trade-only txns (no deposit/withdrawal rows) must produce the
    exact same V/C series and lifetime dict as the pre-Task-10 implementation.
    These numbers were locked by running this test against the code BEFORE
    the cash-aware branch was added."""
    txns = [
        make_txn("AAPL", "buy", 10, 100.0, currency="USD", date=date(2024, 1, 1), portfolio_id=pid),
        make_txn("AAPL", "buy", 5, 110.0, currency="USD", date=date(2024, 1, 3), portfolio_id=pid),
        make_txn("AAPL", "sell", 5, 120.0, currency="USD", date=date(2024, 1, 5), portfolio_id=pid),
    ]
    for t in txns:
        db_session.add(t)
    db_session.commit()

    assert has_external_cashflows(txns) is False

    idx = pd.date_range("2024-01-01", periods=10, freq="D")
    closes = [100, 101, 102, 103, 104, 105, 106, 107, 108, 109]
    with patch("routers.analytics.yf.download", return_value=_mock_price_panel(idx, closes)), \
         patch("routers.analytics.market_data.get_infos", return_value={"AAPL": {"currency": "USD"}}), \
         patch("routers.analytics.date", _FrozenDate):
        V, C, closes_index = _build_value_cashflow_series(txns, date(2023, 12, 27))
        lifetime = _lifetime_money_weighted(txns, V)

    assert V.tolist() == pytest.approx([1000, 1010, 1530, 1545, 1040, 1050, 1060, 1070, 1080, 1090])
    assert C.tolist() == pytest.approx([1000, 0, 550, 0, -600, 0, 0, 0, 0, 0])

    assert lifetime["current_value"] == pytest.approx(1090.0)
    assert lifetime["total_invested"] == pytest.approx(1033.33, abs=0.01)
    assert lifetime["cum_buys_cost"] == pytest.approx(1550.0)
    assert lifetime["realized_pnl"] == pytest.approx(83.33, abs=0.01)
    assert lifetime["dividends"] == 0.0
    assert lifetime["unrealized_pnl"] == pytest.approx(56.67, abs=0.01)
    assert lifetime["net_profit"] == pytest.approx(140.0, abs=0.01)
    assert lifetime["simple_roi"] == pytest.approx(9.03, abs=0.01)
    assert lifetime["xirr"] == pytest.approx(371.69, abs=0.01)


def test_returns_use_deposits_as_external_cashflows(db_session, pid):
    """With a deposit present, C comes from the deposit (not the buy it later
    funds) and V folds in the running cash balance -- the buy becomes internal
    reallocation (cash -> position), so the money-weighted return reflects
    contributed capital rather than trade activity."""
    txns = [
        make_txn(ticker=None, type="deposit", shares=0.0, price=0.0, amount=2000,
                 currency="USD", date=date(2024, 1, 1), portfolio_id=pid),
        make_txn("AAPL", "buy", 10, 100.0, currency="USD", date=date(2024, 1, 3), portfolio_id=pid),
    ]
    for t in txns:
        db_session.add(t)
    db_session.commit()

    assert has_external_cashflows(txns) is True

    idx = pd.date_range("2024-01-01", periods=6, freq="D")
    closes = [100, 100, 100, 105, 110, 115]
    with patch("routers.analytics.yf.download", return_value=_mock_price_panel(idx, closes)), \
         patch("routers.analytics.market_data.get_infos", return_value={"AAPL": {"currency": "USD"}}), \
         patch("routers.analytics.date", _FrozenDate):
        V, C, closes_index = _build_value_cashflow_series(txns, date(2023, 12, 27))
        lifetime = _lifetime_money_weighted(txns, V)

    # External cashflow C is driven by the $2000 deposit (day 1), NOT the
    # $1000 buy (day 3) it later funds -- the buy no longer appears in C.
    assert C.tolist() == pytest.approx([2000, 0, 0, 0, 0, 0])
    # V folds in the running cash balance: day1 = 0 holdings + 2000 cash;
    # day3 = 1000 holdings (10@100) + 1000 leftover cash (net of the buy);
    # thereafter only the holdings leg moves with the AAPL close price.
    assert V.tolist() == pytest.approx([2000, 2000, 2000, 2050, 2100, 2150])

    # current_value/unrealized_pnl/simple_roi stay positions-only (net worth
    # minus the still-idle cash), matching get_summary's total_value-vs-
    # net_worth split -- otherwise the untouched $1000 cash would be double
    # counted as "profit".
    assert lifetime["current_value"] == pytest.approx(1150.0)   # 10 shares @ 115
    assert lifetime["total_invested"] == pytest.approx(1000.0)
    assert lifetime["unrealized_pnl"] == pytest.approx(150.0)
    assert lifetime["net_profit"] == pytest.approx(150.0)
    assert lifetime["simple_roi"] == pytest.approx(15.0)         # 150/1000, not 1150/1000
    # XIRR is driven by the deposit (-2000 @ Jan 1) against ending NET WORTH
    # (+2150 @ frozen "today"), reflecting contributed capital rather than
    # the trade.
    assert lifetime["xirr"] == pytest.approx(134.32, abs=0.01)


def test_daily_net_worth_counts_dividends_interest_and_fees_as_return():
    """Dropping any internal cash event from V must change the expected 1.3% return."""
    txns = [
        make_txn(ticker=None, type="deposit", shares=0, price=0, amount=1000,
                 currency="USD", date=date(2024, 1, 1)),
        make_txn("AAPL", "buy", 10, 100, currency="USD", cash_amount=1000,
                 cash_currency="USD", date=date(2024, 1, 1)),
        make_txn("AAPL", "dividend", 10, 1, currency="USD", cash_amount=10,
                 cash_currency="USD", date=date(2024, 1, 2)),
        make_txn(ticker=None, type="interest", shares=0, price=0, amount=5,
                 currency="USD", date=date(2024, 1, 2)),
        make_txn(ticker=None, type="fee", shares=0, price=0, amount=2,
                 currency="USD", date=date(2024, 1, 2)),
    ]
    idx = pd.date_range("2024-01-01", periods=2, freq="D")
    with patch("routers.analytics.yf.download", return_value=_mock_price_panel(idx, [100, 100])), \
         patch("routers.analytics.market_data.get_infos", return_value={"AAPL": {"currency": "USD"}}):
        V, C, _ = _build_value_cashflow_series(txns, date(2024, 1, 1))
        daily = _modified_dietz_daily_returns(V, C, date(2024, 1, 1))

    assert V.tolist() == pytest.approx([1000, 1013])
    assert C.tolist() == pytest.approx([1000, 0])
    assert daily.tolist() == pytest.approx([0.013])


def test_stock_split_preserves_value_and_cost_without_cashflow():
    """Ignoring either split leg must distort the ending shares or daily return."""
    txns = [
        make_txn(ticker=None, type="deposit", shares=0, price=0, amount=1000,
                 currency="USD", date=date(2024, 1, 1)),
        make_txn("GNPX", "buy", 10, 100, currency="USD", cash_amount=1000,
                 cash_currency="USD", date=date(2024, 1, 1)),
        make_txn("GNPX", "split_open", 5, 200, currency="USD", date=date(2024, 1, 2)),
        make_txn("GNPX", "split_close", 10, 100, currency="USD", date=date(2024, 1, 2)),
    ]
    idx = pd.date_range("2024-01-01", periods=2, freq="D")
    with patch("routers.analytics.yf.download", return_value=_mock_price_panel(idx, [100, 200])), \
         patch("routers.analytics.market_data.get_infos", return_value={"GNPX": {"currency": "USD"}}):
        V, C, _ = _build_value_cashflow_series(txns, date(2024, 1, 1))
        daily = _modified_dietz_daily_returns(V, C, date(2024, 1, 1))

    holding = _build_holdings(txns)["GNPX"]
    assert holding["shares"] == pytest.approx(5)
    assert holding["cost"] == pytest.approx(1000)
    assert V.tolist() == pytest.approx([1000, 1000])
    assert C.tolist() == pytest.approx([1000, 0])
    assert daily.tolist() == pytest.approx([0])


@pytest.mark.parametrize(
    "split_ratio,new_shares,adjusted_closes",
    [
        (1 / 22, 10 / 22, [52.8, 52.8, 52.8]),
        (2, 20, [1.2, 1.2, 1.2]),
    ],
)
@pytest.mark.parametrize("multi_index", [False, True])
def test_yahoo_split_adjusted_closes_do_not_create_historical_profit(
    split_ratio, new_shares, adjusted_closes, multi_index,
):
    """Yahoo Close is split-adjusted even with auto_adjust=False; broker shares aren't."""
    txns = [
        make_txn(ticker=None, type="deposit", shares=0, price=0, amount=1000,
                 currency="USD", date=date(2024, 1, 1)),
        make_txn("GNPX", "buy", 10, 2.4, currency="USD", cash_amount=24,
                 cash_currency="USD", date=date(2024, 1, 2)),
        make_txn("GNPX", "split_close", 10, 2.4,
                 currency="USD", date=date(2024, 1, 3)),
        make_txn("GNPX", "split_open", new_shares, 2.4 / split_ratio,
                 currency="USD", date=date(2024, 1, 3)),
    ]
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    panel = pd.DataFrame({
        "Close": adjusted_closes,
        "Stock Splits": [0, 0, split_ratio],
        "Dividends": [0, 0, 0],
    }, index=idx)
    if multi_index:
        panel.columns = pd.MultiIndex.from_tuples(
            [(field, "GNPX") for field in panel.columns]
        )
    with patch("routers.analytics.yf.download", return_value=panel), \
         patch("routers.analytics.market_data.get_infos", return_value={"GNPX": {"currency": "USD"}}):
        V, C, _ = _build_value_cashflow_series(txns, date(2024, 1, 1))
        daily = _modified_dietz_daily_returns(V, C, date(2024, 1, 1))

    assert V.tolist() == pytest.approx([1000, 1000, 1000])
    assert C.tolist() == pytest.approx([1000, 0, 0])
    assert daily.tolist() == pytest.approx([0, 0])


def _split_panel(adjusted_closes, split_ratio):
    idx = pd.date_range("2024-01-01", periods=len(adjusted_closes), freq="D")
    splits = [0] * (len(adjusted_closes) - 1) + [split_ratio]
    return pd.DataFrame({
        "Close": adjusted_closes,
        "Stock Splits": splits,
        "Dividends": [0] * len(adjusted_closes),
    }, index=idx)


def test_split_already_normalized_in_ledger_keeps_yahoo_adjusted_closes():
    """The T212 API sync rescales pre-split buys to post-split units and adds no
    split rows (t212_corporate_actions.apply_splits). Undoing Yahoo's split
    adjustment then values those shares at the pre-split price (BKNG 25:1)."""
    txns = [
        make_txn(ticker=None, type="deposit", shares=0, price=0, amount=1000,
                 currency="USD", date=date(2024, 1, 1)),
        # As traded: 10 shares at 2.4; stored after the 2:1 split as 20 at 1.2.
        make_txn("BKNG", "buy", 20, 1.2, currency="USD", cash_amount=24,
                 cash_currency="USD", date=date(2024, 1, 2)),
    ]
    with patch("routers.analytics.yf.download", return_value=_split_panel([1.2, 1.2, 1.2], 2)), \
         patch("routers.analytics.market_data.get_infos", return_value={"BKNG": {"currency": "USD"}}):
        V, C, _ = _build_value_cashflow_series(txns, date(2024, 1, 1))
        daily = _modified_dietz_daily_returns(V, C, date(2024, 1, 1))

    assert V.tolist() == pytest.approx([1000, 1000, 1000])
    assert daily.tolist() == pytest.approx([0, 0])


def test_position_closed_before_split_still_uses_as_traded_closes():
    """No split rows, but nothing was held across the split: the rows are as
    traded, so Yahoo's adjustment must still be undone."""
    txns = [
        make_txn(ticker=None, type="deposit", shares=0, price=0, amount=1000,
                 currency="USD", date=date(2024, 1, 1)),
        make_txn("BKNG", "buy", 10, 2.4, currency="USD", cash_amount=24,
                 cash_currency="USD", date=date(2024, 1, 1)),
        make_txn("BKNG", "sell", 10, 2.4, currency="USD", cash_amount=24,
                 cash_currency="USD", date=date(2024, 1, 2)),
    ]
    with patch("routers.analytics.yf.download", return_value=_split_panel([1.2, 1.2, 1.2], 2)), \
         patch("routers.analytics.market_data.get_infos", return_value={"BKNG": {"currency": "USD"}}):
        V, C, _ = _build_value_cashflow_series(txns, date(2024, 1, 1))

    assert V.tolist() == pytest.approx([1000, 1000, 1000])


def test_basket_returns_do_not_show_a_split_as_a_crash():
    with patch("routers.analytics.yf.download", return_value=_split_panel([1.2, 1.2, 1.2], 2)):
        returns = _basket_daily_returns(
            [{"ticker": "BKNG", "weight": 1}], date(2024, 1, 1),
            pd.date_range("2024-01-01", periods=3, freq="D"),
        )

    assert returns.dropna().tolist() == pytest.approx([0, 0])


def test_modified_dietz_weights_external_flow_and_geometrically_links_days():
    """Treating cashback as return or arithmetically summing days breaks this literal."""
    txns = [
        make_txn(ticker=None, type="deposit", shares=0, price=0, amount=1000,
                 currency="USD", date=date(2024, 1, 1)),
        make_txn("AAPL", "buy", 10, 100, currency="USD", cash_amount=1000,
                 cash_currency="USD", date=date(2024, 1, 1)),
        make_txn(ticker=None, type="cashback", shares=0, price=0, amount=100,
                 currency="USD", date=date(2024, 1, 2)),
    ]
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    with patch("routers.analytics.yf.download", return_value=_mock_price_panel(idx, [100, 110, 121])), \
         patch("routers.analytics.market_data.get_infos", return_value={"AAPL": {"currency": "USD"}}):
        V, C, _ = _build_value_cashflow_series(txns, date(2024, 1, 1))
        daily = _modified_dietz_daily_returns(V, C, date(2024, 1, 1))

    assert V.tolist() == pytest.approx([1000, 1200, 1310])
    assert C.tolist() == pytest.approx([1000, 100, 0])
    assert daily.tolist() == pytest.approx([0.0952380952, 0.0916666667])
    assert float((1 + daily).prod() - 1) == pytest.approx(0.1956349206)


def test_modified_dietz_keeps_legitimate_return_above_fifty_percent():
    idx = pd.date_range("2024-01-01", periods=2, freq="D")
    V = pd.Series([100.0, 160.0], index=idx)
    C = pd.Series([0.0, 0.0], index=idx)

    daily = _modified_dietz_daily_returns(V, C, date(2024, 1, 1))

    assert daily.tolist() == pytest.approx([0.60])


def test_performance_endpoint_returns_net_worth_and_cumulative_twr(db_session, pid, default_portfolio):
    """Using holdings-only value or treating cashback as return breaks the endpoint."""
    txns = [
        make_txn(ticker=None, type="deposit", shares=0, price=0, amount=1000,
                 currency="USD", date=date(2024, 1, 1), portfolio_id=pid),
        make_txn("AAPL", "buy", 10, 100, currency="USD", cash_amount=1000,
                 cash_currency="USD", date=date(2024, 1, 1), portfolio_id=pid),
        make_txn(ticker=None, type="cashback", shares=0, price=0, amount=100,
                 currency="USD", date=date(2024, 1, 2), portfolio_id=pid),
    ]
    db_session.add_all(txns)
    db_session.commit()
    idx = pd.date_range("2024-01-01", periods=3, freq="D")

    with patch("routers.analytics.yf.download", return_value=_mock_price_panel(idx, [100, 110, 121])), \
         patch("routers.analytics.market_data.get_infos", return_value={"AAPL": {"currency": "USD"}}):
        result = get_performance(currency="USD", period="all", db=db_session, portfolio=default_portfolio)

    assert [row["value"] for row in result] == pytest.approx([1000, 1200, 1310])
    assert [row["pnl_pct"] for row in result] == pytest.approx([0, 9.52, 19.56], abs=0.01)


def test_performance_period_and_lifetime_returns_are_distinct(db_session, pid, default_portfolio):
    today = date.today()
    first_day = today - pd.Timedelta(days=10)
    txns = [
        make_txn(ticker=None, type="deposit", shares=0, price=0, amount=1000,
                 currency="USD", date=first_day, portfolio_id=pid),
        make_txn("AAPL", "buy", 10, 100, currency="USD", cash_amount=1000,
                 cash_currency="USD", date=first_day, portfolio_id=pid),
    ]
    db_session.add_all(txns)
    db_session.commit()
    idx = pd.date_range(first_day, today, freq="D")
    prices = [100.0, 100.0, 120.0] + [120.0] * 7 + [132.0]

    with patch("routers.analytics.yf.download", return_value=_mock_price_panel(idx, prices)), \
         patch("routers.analytics.market_data.get_infos", return_value={"AAPL": {"currency": "USD"}}):
        result = get_performance(currency="USD", period="7d", db=db_session, portfolio=default_portfolio)

    assert result[-1]["pnl_pct"] == pytest.approx(10.0, abs=0.01)
    assert result[-1]["total_pnl_pct"] == pytest.approx(32.0, abs=0.01)
    assert result[-1]["pnl"] == pytest.approx(120.0, abs=0.01)
    assert result[-1]["total_pnl"] == pytest.approx(320.0, abs=0.01)
