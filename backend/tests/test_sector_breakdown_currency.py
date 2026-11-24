"""/analytics/sector-breakdown must answer in the display currency asked for.

It used to collapse every non-CZK request (EUR, GBP, PLN) to USD, so the
frontend (which labels the amounts with the user's chosen currency) showed
dollar amounts under a euro/pound/zloty label.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import date
from unittest.mock import patch

import pytest

from routers.analytics import sector_breakdown
from routers.cash import create_cash, CashCreate
from tests.helpers import make_txn

# Fake "ccy -> CZK" rates; a 10 x 100 USD holding is worth 1000 USD.
CZK_RATES = {"CZK": 1.0, "USD": 20.0, "EUR": 25.0, "GBP": 30.0, "PLN": 5.0}
INFO = {"AAPL": {"currentPrice": 100.0, "currency": "USD", "sector": "Technology",
                 "quoteType": "EQUITY", "country": "United States"}}


def _fake_live_fx_to_czk(currency, cache):
    return CZK_RATES[currency.upper()]


def _fake_live_to_usd(ccy):
    return CZK_RATES[ccy.upper()] / CZK_RATES["USD"]


def _fake_bulk_fetch_fx(pairs):
    return {(c, d): CZK_RATES[c] for c, d in pairs}


def _run(db_session, portfolio, currency):
    with patch("market_data.get_infos", return_value=INFO), \
         patch("routers.portfolio._live_fx_to_czk", side_effect=_fake_live_fx_to_czk), \
         patch("routers.portfolio._live_to_usd", side_effect=_fake_live_to_usd), \
         patch("routers.portfolio.bulk_fetch_fx", side_effect=_fake_bulk_fetch_fx):
        return sector_breakdown(currency=currency, db=db_session, portfolio=portfolio)


@pytest.mark.parametrize(
    ("currency", "expected_value"),
    [
        ("USD", 1000.0),
        ("CZK", 20000.0),        # 1000 USD * 20
        ("EUR", 800.0),          # 1000 USD * 20 / 25
        ("GBP", 666.67),         # 1000 USD * 20 / 30
        ("PLN", 4000.0),         # 1000 USD * 20 / 5
        ("eur", 800.0),          # case-insensitive
    ],
)
def test_sector_breakdown_converts_to_requested_currency(
    db_session, default_portfolio, currency, expected_value
):
    db_session.add(make_txn("AAPL", "buy", 10, 100.0, currency="USD", date=date(2024, 1, 2),
                            portfolio_id=default_portfolio.id, fx_to_czk=20.0))
    db_session.commit()

    result = _run(db_session, default_portfolio, currency)

    assert result["currency"] == currency.upper()
    assert result["total_value"] == pytest.approx(expected_value, abs=0.01)
    assert result["sectors"][0]["value"] == pytest.approx(expected_value, abs=0.01)
    assert result["currencies"][0]["name"] == "USD"  # exposure label stays native
    assert result["currencies"][0]["value"] == pytest.approx(expected_value, abs=0.01)
    # Cost was 1000 USD and the quote is unchanged, so the profit is flat in
    # every display currency (cost converted at the same rates).
    assert result["sectors"][0]["profit"] == pytest.approx(0.0, abs=0.01)


def test_sector_breakdown_converts_cash_to_requested_currency(db_session, default_portfolio):
    with patch("routers.cash.fetch_fx_to_czk", return_value=20.0):
        create_cash(CashCreate(type="deposit", amount=1000, currency="USD",
                               date=date(2024, 1, 1)), db_session, default_portfolio)

    def fake_fetch(ccy, on_date):
        return CZK_RATES[ccy.upper()]

    with patch("fx.fetch_fx_to_czk", side_effect=fake_fetch):
        result = sector_breakdown(currency="EUR", db=db_session, portfolio=default_portfolio)

    assert result["currency"] == "EUR"
    assert result["sectors"][0]["name"] == "Cash"
    assert result["sectors"][0]["value"] == pytest.approx(800.0, abs=0.01)


def test_sector_breakdown_unknown_currency_falls_back_to_usd(db_session, default_portfolio):
    db_session.add(make_txn("AAPL", "buy", 10, 100.0, currency="USD", date=date(2024, 1, 2),
                            portfolio_id=default_portfolio.id, fx_to_czk=20.0))
    db_session.commit()

    result = _run(db_session, default_portfolio, "not-a-currency")

    assert result["currency"] == "USD"
    assert result["total_value"] == pytest.approx(1000.0, abs=0.01)
