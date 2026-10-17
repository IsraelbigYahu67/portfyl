"""Top Movers: the %/$ toggle must rank the whole portfolio, not just the
five rows that happened to make the %-ranked list."""

from __future__ import annotations

from datetime import date

import routers.portfolio as portfolio_router
from tests.conftest import make_txn


def _seed(db_session, pid, holdings):
    for ticker, shares in holdings.items():
        db_session.add(make_txn(ticker, "buy", shares, 100.0, date=date(2024, 1, 15), portfolio_id=pid))
    db_session.commit()


def test_value_ranking_covers_all_holdings(db_session, pid, default_portfolio, monkeypatch):
    # Six small positions with big % moves, plus BIG: a huge position that
    # only moves 1% — outside the % top 5, but the largest money move.
    holdings = {"A": 1, "B": 1, "C": 1, "D": 1, "E": 1, "F": 1, "BIG": 1000}
    _seed(db_session, pid, holdings)
    closes = {
        "A": (100.0, 110.0), "B": (100.0, 109.0), "C": (100.0, 108.0),
        "D": (100.0, 107.0), "E": (100.0, 106.0), "F": (100.0, 105.0),
        "BIG": (100.0, 101.0),
    }
    monkeypatch.setattr(portfolio_router, "_two_day_closes", lambda tickers: closes)
    monkeypatch.setattr(portfolio_router, "_fetch_price_and_info",
                        lambda t: (closes[t][1], t, "USD"))
    monkeypatch.setattr(portfolio_router, "_live_fx_to_czk", lambda c, cache: 20.0)

    out = portfolio_router.get_movers(period="1d", db=db_session, portfolio=default_portfolio)

    assert "BIG" not in [m["ticker"] for m in out["gainers"]]
    assert out["value_gainers"][0]["ticker"] == "BIG"
    assert out["value_gainers"][0]["period_pnl"] == 1000.0
    assert out["value_gainers"][0]["period_pnl_czk"] == 20000.0
    # Everything rose, so there are no losers to list.
    assert len(out["value_gainers"]) == 5 and out["value_losers"] == []


def test_gainers_and_losers_only_list_real_movers(db_session, pid, default_portfolio, monkeypatch):
    # Three green, two red, one flat: gainers must not be padded with red
    # rows (nor losers with green ones) just to reach five.
    _seed(db_session, pid, {"G1": 1, "G2": 1, "G3": 1, "R1": 1, "R2": 1, "FLAT": 1})
    closes = {
        "G1": (100.0, 103.0), "G2": (100.0, 102.0), "G3": (100.0, 101.0),
        "R1": (100.0, 98.0), "R2": (100.0, 95.0), "FLAT": (100.0, 100.0),
    }
    monkeypatch.setattr(portfolio_router, "_two_day_closes", lambda tickers: closes)
    monkeypatch.setattr(portfolio_router, "_fetch_price_and_info",
                        lambda t: (closes[t][1], t, "USD"))
    monkeypatch.setattr(portfolio_router, "_live_fx_to_czk", lambda c, cache: 20.0)

    out = portfolio_router.get_movers(period="1d", db=db_session, portfolio=default_portfolio)

    for gainers, losers in (("gainers", "losers"), ("value_gainers", "value_losers")):
        assert [m["ticker"] for m in out[gainers]] == ["G1", "G2", "G3"]
        assert [m["ticker"] for m in out[losers]] == ["R2", "R1"]


def test_value_ranking_compares_in_czk(db_session, pid, default_portfolio, monkeypatch):
    # 100 EUR beats 120 USD once both are normalised to CZK.
    _seed(db_session, pid, {"EU": 1, "US": 1})
    closes = {"EU": (100.0, 200.0), "US": (100.0, 220.0)}
    ccy = {"EU": "EUR", "US": "USD"}
    rates = {"EUR": 25.0, "USD": 20.0}
    monkeypatch.setattr(portfolio_router, "_two_day_closes", lambda tickers: closes)
    monkeypatch.setattr(portfolio_router, "_fetch_price_and_info",
                        lambda t: (closes[t][1], t, ccy[t]))
    monkeypatch.setattr(portfolio_router, "_live_fx_to_czk", lambda c, cache: rates[c])

    out = portfolio_router.get_movers(period="1d", db=db_session, portfolio=default_portfolio)

    assert out["gainers"][0]["ticker"] == "US"        # bigger % move
    assert out["value_gainers"][0]["ticker"] == "EU"  # bigger CZK move


def test_empty_portfolio_has_all_keys(db_session, default_portfolio):
    out = portfolio_router.get_movers(period="1d", db=db_session, portfolio=default_portfolio)
    assert out == {"gainers": [], "losers": [], "value_gainers": [], "value_losers": []}
