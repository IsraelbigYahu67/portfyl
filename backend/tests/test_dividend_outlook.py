from datetime import date, datetime, time, timedelta, timezone

import pandas as pd
import pytest

from routers import portfolio
from routers.portfolio import (
    _announced_payment,
    _ex_to_pay_lag,
    _outlook_window,
    _project_payments,
)
from tests.helpers import make_txn


def _epoch(day: date) -> int:
    return int(datetime.combine(day, time(12), tzinfo=timezone.utc).timestamp())


def _by_month(events: list[dict]) -> dict[tuple[int, int], list[dict]]:
    out: dict[tuple[int, int], list[dict]] = {}
    for e in events:
        out.setdefault((e["date"].year, e["date"].month), []).append(e)
    return out


def test_outlook_window_spans_twelve_months_across_the_year_end():
    window = _outlook_window(date(2026, 10, 11))
    assert window[0] == (2026, 10)
    assert window[2] == (2026, 12)
    assert window[3] == (2027, 1)
    assert window[-1] == (2027, 9)
    assert len(set(window)) == 12


def test_announced_payment_needs_a_date_that_is_still_ahead():
    today = date(2026, 10, 11)
    assert _announced_payment({"dividendDate": _epoch(date(2026, 11, 3))}, today, 0) == date(2026, 11, 3)
    # A past pay date is history, not an announcement.
    assert _announced_payment({"dividendDate": _epoch(date(2026, 9, 3))}, today, 0) is None
    # With no pay date ahead, a future ex-date stands in, shifted by the pay lag.
    info = {"dividendDate": _epoch(date(2026, 9, 3)), "exDividendDate": _epoch(date(2026, 10, 20))}
    assert _announced_payment(info, today, 0) == date(2026, 10, 20)
    assert _announced_payment(info, today, 21) == date(2026, 11, 10)
    assert _announced_payment({}, today, 0) is None


def test_pay_lag_prefers_the_provider_ex_and_pay_pair():
    info = {"exDividendDate": _epoch(date(2026, 11, 19)), "dividendDate": _epoch(date(2026, 12, 10))}
    assert _ex_to_pay_lag(info, [], []) == 21


def test_pay_lag_ignores_an_ex_and_pay_pair_from_different_payments():
    # A pay date months after the ex-date belongs to another payment.
    info = {"exDividendDate": _epoch(date(2026, 8, 20)), "dividendDate": _epoch(date(2026, 12, 10))}
    assert _ex_to_pay_lag(info, [], []) == 0


def test_pay_lag_falls_back_to_the_users_credited_dividends():
    ex_dates = [date(2026, 2, 19), date(2026, 5, 21), date(2026, 8, 20)]
    paid = [date(2026, 3, 12), date(2026, 6, 11), date(2026, 9, 10)]
    assert _ex_to_pay_lag({}, ex_dates, paid) == 21
    assert _ex_to_pay_lag({}, ex_dates, []) == 0


# Microsoft-like quarterly payer: ex-date ~20th of Feb/May/Aug/Nov, paid ~3
# weeks later in Mar/Jun/Sep/Dec.
MSFT_HISTORY = [
    (date(2025, 11, 20), 0.83),
    (date(2026, 2, 19), 0.91),
    (date(2026, 5, 21), 0.91),
    (date(2026, 8, 20), 0.91),
]


def test_announced_payment_replaces_the_forecast_from_the_ex_date_month():
    """The reported bug: a November forecast next to a December confirmed payment."""
    window = _outlook_window(date(2026, 10, 16))
    events = _project_payments(
        MSFT_HISTORY, window, lag_days=0, announced=date(2026, 12, 10), paid_dates=[]
    )

    months = _by_month(events)
    assert (2026, 11) not in months
    assert [e["status"] for e in months[(2026, 12)]] == ["confirmed"]
    assert months[(2026, 12)][0]["per_share"] == 0.91  # sized like the latest payment
    assert len(events) == 4


def test_pay_lag_moves_forecasts_into_the_payment_month():
    window = _outlook_window(date(2026, 10, 16))
    events = _project_payments(
        MSFT_HISTORY, window, lag_days=21, announced=date(2026, 12, 10), paid_dates=[]
    )

    assert [(e["date"], e["status"]) for e in events] == [
        (date(2026, 12, 10), "confirmed"),
        (date(2027, 3, 12), "forecasted"),
        (date(2027, 6, 11), "forecasted"),
        (date(2027, 9, 10), "forecasted"),
    ]


def test_announced_payment_matches_a_forecast_across_the_year_end():
    window = _outlook_window(date(2026, 12, 20))
    history = [(date(2025, 12, 29), 0.5), (date(2026, 3, 30), 0.5), (date(2026, 6, 29), 0.5), (date(2026, 9, 28), 0.5)]
    events = _project_payments(
        history, window, lag_days=0, announced=date(2027, 1, 8), paid_dates=[]
    )

    months = _by_month(events)
    assert (2026, 12) not in months
    assert [e["status"] for e in months[(2027, 1)]] == ["confirmed"]
    assert len(events) == 4


def test_credited_dividend_cancels_the_forecast_in_the_neighbouring_month():
    # Last year's ex-date fell on 28 Nov; this year the payment already came
    # in on 30 Oct. It must not be forecast again in November.
    window = _outlook_window(date(2026, 11, 3))
    history = [(date(2025, 11, 28), 0.4), (date(2026, 2, 27), 0.4), (date(2026, 5, 29), 0.4), (date(2026, 8, 28), 0.4)]
    events = _project_payments(
        history, window, lag_days=0, announced=None, paid_dates=[date(2026, 10, 30)]
    )

    assert (2026, 11) not in _by_month(events)
    assert len(events) == 3


def test_last_years_credit_does_not_cancel_this_years_forecast():
    window = _outlook_window(date(2026, 10, 16))
    events = _project_payments(
        MSFT_HISTORY, window, lag_days=21, announced=None, paid_dates=[date(2025, 12, 11)]
    )

    assert date(2026, 12, 11) in [e["date"] for e in events]


def test_moved_ex_date_does_not_forecast_the_payment_twice():
    # The September ex-date moved to late August this year; both sit inside
    # the ~13-month history but describe one quarterly payment.
    window = _outlook_window(date(2026, 10, 16))
    history = [
        (date(2025, 9, 12), 0.40),
        (date(2025, 12, 11), 0.40),
        (date(2026, 3, 12), 0.40),
        (date(2026, 6, 11), 0.40),
        (date(2026, 8, 27), 0.50),
    ]
    events = _project_payments(history, window, lag_days=0, announced=None, paid_dates=[])

    assert len(events) == 4
    merged = [e for e in events if e["date"].month in (8, 9)]
    assert len(merged) == 1
    assert merged[0]["per_share"] == pytest.approx(0.45)


def test_monthly_payer_keeps_one_payment_per_month():
    window = _outlook_window(date(2026, 10, 16))
    history = [(date(2025, 9, 15), 0.10)] + [
        (date(2025 + (m // 12), m % 12 + 1, 15), 0.20) for m in range(9, 22)
    ]  # 15 Sep 2025 .. 15 Oct 2026
    events = _project_payments(
        history, window, lag_days=0, announced=None, paid_dates=[date(2026, 10, 15)]
    )

    months = _by_month(events)
    assert (2026, 10) not in months  # already credited
    assert sorted(months) == window[1:]
    assert all(len(rows) == 1 for rows in months.values())
    assert months[(2027, 9)][0]["per_share"] == pytest.approx(0.15)  # two Septembers averaged


def test_forecast_outlook_marks_announced_payment_confirmed_and_the_rest_forecasted(
    db_session, pid, default_portfolio, monkeypatch
):
    today = datetime.now().date()
    db_session.add(make_txn("QRT", "buy", 10, 100, portfolio_id=pid))
    db_session.commit()

    # Quarterly payer; the latest payment (35 days ago) is 0.50 per share.
    offsets = [-308, -217, -126, -35]
    per_share = [0.20, 0.30, 0.40, 0.50]
    history = pd.Series(
        per_share, index=pd.DatetimeIndex([pd.Timestamp(today + timedelta(days=d)) for d in offsets])
    )
    pay_day = today + timedelta(days=20)
    infos = {"QRT": {"shortName": "Quarterly Corp", "currency": "USD", "dividendDate": _epoch(pay_day)}}
    monkeypatch.setattr(portfolio.market_data, "get_infos", lambda _: infos)
    monkeypatch.setattr(portfolio.market_data, "get_info", lambda t: infos[t])
    monkeypatch.setattr(
        portfolio.market_data, "ticker_attrs", lambda symbols, attr: {s: history for s in symbols}
    )
    monkeypatch.setattr(portfolio, "_live_to_usd", lambda _: 1.0)

    result = portfolio.get_dividend_forecast(db=db_session, portfolio=default_portfolio)
    outlook = result["outlook"]

    window = _outlook_window(today)
    assert [(m["year"]) for m in outlook["months"]] == [y for y, _ in window]

    # The announced payment stands in for the one projected from 308 days
    # ago (0.20); the other three quarters stay forecasted.
    confirmed_ym = (pay_day.year, pay_day.month)
    statuses = [e["status"] for row in outlook["months"] for e in row["entries"]]
    assert sorted(statuses) == ["confirmed", "forecasted", "forecasted", "forecasted"]
    for ym, row in zip(window, outlook["months"]):
        if ym == confirmed_ym:
            assert [e["status"] for e in row["entries"]] == ["confirmed"]
            assert row["entries"][0]["amount"] == 5.0  # 10 shares * latest 0.50
    forecast_amounts = sorted(
        e["amount"] for row in outlook["months"] for e in row["entries"] if e["status"] == "forecasted"
    )
    assert forecast_amounts == [3.0, 4.0, 5.0]
    assert outlook["total_confirmed"] == 5.0
    assert outlook["total_forecasted"] == 12.0

    # The calendar-year chart shows the same upcoming payments.
    for ym, row in zip(window, outlook["months"]):
        if ym[0] == today.year:
            assert result["months"][ym[1] - 1]["estimated"] == round(row["confirmed"] + row["forecasted"], 2)
