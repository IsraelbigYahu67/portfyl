import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date
from unittest.mock import patch

import pytest

from routers.cash import create_cash, get_history, get_balance, CashCreate
from routers.analytics import sector_breakdown
from tests.helpers import make_txn


# ---------------------------------------------------------------------------
# Currency / FX-exposure dimension on /analytics/sector-breakdown
# ---------------------------------------------------------------------------

def test_currency_breakdown_cash_only_single_ccy(db_session, pid):
    # Cash-only, USD deposit, USD display -> the whole allocation is USD.
    with patch("routers.cash.fetch_fx_to_czk", return_value=23.0):
        create_cash(CashCreate(type="deposit", amount=2000, currency="USD", date=date(2024, 1, 1)), db_session, pid)

    result = sector_breakdown(currency="USD", db=db_session, pid=pid)
    cur = result["currencies"]
    assert [c["name"] for c in cur] == ["USD"]
    assert cur[0]["value"] == 2000.0
    assert cur[0]["weight"] == 100.0


def test_currency_breakdown_separates_currencies(db_session, pid):
    # Two cash currencies must land as distinct FX-exposure slices. Patch the
    # display conversion to identity so the test needs no live FX (native amounts
    # ARE the display values); folded_cash_display uses the same patched helper.
    with patch("routers.cash.fetch_fx_to_czk", return_value=1.0):
        create_cash(CashCreate(type="deposit", amount=2000, currency="USD", date=date(2024, 1, 1)), db_session, pid)
        create_cash(CashCreate(type="deposit", amount=30000, currency="CZK", date=date(2024, 1, 2)), db_session, pid)

    with patch("fx.cash_amount_to_display", side_effect=lambda amt, src, dst: amt):
        result = sector_breakdown(currency="USD", db=db_session, pid=pid)

    cur = {c["name"]: c for c in result["currencies"]}
    assert set(cur) == {"USD", "CZK"}
    assert cur["USD"]["value"] == 2000.0
    assert cur["CZK"]["value"] == 30000.0
    # weights are relative to the 32000 total and sum to 100
    assert cur["CZK"]["weight"] == pytest.approx(93.75, abs=0.01)
    assert cur["USD"]["weight"] == pytest.approx(6.25, abs=0.01)
    assert round(sum(c["weight"] for c in result["currencies"]), 2) == 100.0


def test_currency_breakdown_folds_holdings_and_cash(db_session, pid):
    # USD holding + USD cash, USD display -> both fold into the single USD slice
    # (USD holdings short-circuit live FX, so this stays hermetic).
    with patch("routers.cash.fetch_fx_to_czk", return_value=23.0):
        create_cash(CashCreate(type="deposit", amount=2000, currency="USD", date=date(2024, 1, 1)), db_session, pid)
    db_session.add(make_txn(type="buy", shares=10, price=100, currency="USD",
                            date=date(2024, 1, 2), portfolio_id=pid))
    db_session.commit()

    with patch("market_data.get_infos", return_value={
        "AAPL": {"currentPrice": 100.0, "currency": "USD", "sector": "Technology", "quoteType": "EQUITY"},
    }):
        result = sector_breakdown(currency="USD", db=db_session, pid=pid)

    cur = result["currencies"]
    assert [c["name"] for c in cur] == ["USD"]
    # holdings 10*100=1000 + net cash (2000 deposit - 1000 buy) = 1000 -> 2000 USD
    assert cur[0]["value"] == pytest.approx(2000.0, abs=0.01)
    assert cur[0]["weight"] == 100.0


# ---------------------------------------------------------------------------
# /cash/history running-balance series
# ---------------------------------------------------------------------------

def test_cash_history_running_balance(db_session, pid):
    with patch("routers.cash.fetch_fx_to_czk", return_value=1.0):
        create_cash(CashCreate(type="deposit", amount=1000, currency="CZK", date=date(2024, 1, 1)), db_session, pid)
        create_cash(CashCreate(type="deposit", amount=500, currency="CZK", date=date(2024, 2, 1)), db_session, pid)
        create_cash(CashCreate(type="withdrawal", amount=200, currency="CZK", date=date(2024, 3, 1)), db_session, pid)

    out = get_history(currency="CZK", db=db_session, pid=pid)
    series = out["series"]
    assert [p["date"] for p in series] == ["2024-01-01", "2024-02-01", "2024-03-01"]
    assert [p["balance"] for p in series] == [1000.0, 1500.0, 1300.0]
    # final point reconciles with the /balance blended total
    bal = get_balance(currency="CZK", db=db_session, pid=pid)
    assert series[-1]["balance"] == pytest.approx(bal["total"], abs=0.01)


def test_cash_history_collapses_same_day_events(db_session, pid):
    with patch("routers.cash.fetch_fx_to_czk", return_value=1.0):
        create_cash(CashCreate(type="deposit", amount=1000, currency="CZK", date=date(2024, 1, 1)), db_session, pid)
        create_cash(CashCreate(type="fee", amount=50, currency="CZK", date=date(2024, 1, 1)), db_session, pid)

    out = get_history(currency="CZK", db=db_session, pid=pid)
    series = out["series"]
    assert len(series) == 1
    assert series[0]["date"] == "2024-01-01"
    assert series[0]["balance"] == 950.0  # 1000 deposit - 50 fee, one collapsed point


def test_cash_history_empty(db_session, pid):
    out = get_history(currency="USD", db=db_session, pid=pid)
    assert out == {"currency": "USD", "series": []}
