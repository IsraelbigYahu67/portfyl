import pytest

from routers import portfolio
from routers.portfolio import _normalize_dividend_row
from tests.helpers import make_txn


BASE = {
    "ticker": "MSFT",
    "name": "Microsoft",
    "shares": 10.5,
    "currency": "USD",
    "dividend_rate": 3.32,
    "provider_yield": 0.72,
    "price": 460,
    "ex_date": "2026-08-20",
    "pay_date": "2026-09-10",
    "as_of": "2026-09-13T10:30:00Z",
}


def row(**patch):
    return _normalize_dividend_row(**(BASE | patch))


def test_valid_row_is_estimated_and_complete():
    out = row()
    assert out["date_status"] == "complete"
    assert out["income_status"] == "estimated"
    assert out["annual_income"] == 34.86
    assert out["warnings"] == []


def test_payment_before_ex_date_is_sanitized():
    out = row(pay_date="2026-08-01")
    assert out["pay_date"] is None
    assert out["date_status"] == "inconsistent"
    assert "pay_date_before_ex_date" in out["warnings"]


@pytest.mark.parametrize(
    ("ex_date", "pay_date", "expected"),
    [
        ("2026-08-20", "2026-09-10", "complete"),
        ("2026-08-20", None, "ex_date_only"),
        (None, "2026-09-10", "pay_date_only"),
        (None, None, "unavailable"),
    ],
)
def test_date_status_describes_available_provider_dates(ex_date, pay_date, expected):
    assert row(ex_date=ex_date, pay_date=pay_date)["date_status"] == expected


@pytest.mark.parametrize("rate", [None, 0, -1, float("nan"), float("inf")])
def test_non_positive_or_non_finite_rate_is_unavailable(rate):
    out = row(dividend_rate=rate, provider_yield=None)
    assert out["annual_income"] is None
    assert out["income_status"] == "unavailable"


def test_implied_yield_above_35_percent_requires_review():
    out = row(dividend_rate=40, price=100, provider_yield=None)
    assert out["annual_income"] is None
    assert out["income_status"] == "review"
    assert "implausible_implied_yield" in out["warnings"]


def test_provider_disagreement_requires_both_thresholds():
    out = row(dividend_rate=10, price=100, provider_yield=2)
    assert out["income_status"] == "review"
    assert "provider_fields_disagree" in out["warnings"]

    close_enough = row(dividend_rate=7, price=100, provider_yield=2)
    assert close_enough["income_status"] == "estimated"
    assert "provider_fields_disagree" not in close_enough["warnings"]


def test_provenance_is_additive():
    out = row()
    assert out["source"] == "yahoo_finance"
    assert out["as_of"] == BASE["as_of"]


def test_endpoint_uses_one_timestamp_and_excludes_review_income_from_rows(
    db_session, pid, default_portfolio, monkeypatch
):
    db_session.add(make_txn("SAFE", "buy", 10, 100, portfolio_id=pid))
    db_session.add(make_txn("RISK", "buy", 10, 100, portfolio_id=pid))
    db_session.commit()
    infos = {
        "SAFE": {
            "shortName": "Safe Corp",
            "dividendRate": 2,
            "dividendYield": 2,
            "regularMarketPrice": 100,
            "currency": "USD",
            "exDividendDate": 1787184000,
            "dividendDate": 1788998400,
        },
        "RISK": {
            "shortName": "Risk Corp",
            "dividendRate": 40,
            "dividendYield": 40,
            "regularMarketPrice": 100,
            "currency": "USD",
        },
    }
    monkeypatch.setattr(portfolio.market_data, "get_infos", lambda _: infos)
    monkeypatch.setattr(portfolio.market_data, "get_info", lambda ticker: infos[ticker])
    monkeypatch.setattr(portfolio, "_pay_date_from_calendar", lambda _: None)
    monkeypatch.setattr(portfolio.market_data, "ticker_attrs", lambda symbols, attr: {})

    rows = portfolio.get_dividends(db=db_session, portfolio=default_portfolio)

    assert len({item["as_of"] for item in rows}) == 1
    risky = next(item for item in rows if item["ticker"] == "RISK")
    assert risky["annual_income"] is None
    assert risky["income_status"] == "review"
