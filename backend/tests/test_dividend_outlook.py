from datetime import date, datetime, time, timedelta, timezone

import pandas as pd

from routers import portfolio
from routers.portfolio import _confirmed_payment_month, _outlook_window
from tests.helpers import make_txn


def _epoch(day: date) -> int:
    return int(datetime.combine(day, time(12), tzinfo=timezone.utc).timestamp())


def test_outlook_window_spans_twelve_months_across_the_year_end():
    window = _outlook_window(date(2026, 10, 11))
    assert window[0] == (2026, 10)
    assert window[2] == (2026, 12)
    assert window[3] == (2027, 1)
    assert window[-1] == (2027, 9)
    assert len(set(window)) == 12


def test_confirmed_month_needs_a_date_that_is_still_ahead():
    today = date(2026, 10, 11)
    assert _confirmed_payment_month({"dividendDate": _epoch(date(2026, 11, 3))}, today) == (2026, 11)
    # A past pay date is history, not an announcement.
    assert _confirmed_payment_month({"dividendDate": _epoch(date(2026, 9, 3))}, today) is None
    # With no pay date ahead, a future ex-date stands in.
    info = {"dividendDate": _epoch(date(2026, 9, 3)), "exDividendDate": _epoch(date(2026, 10, 20))}
    assert _confirmed_payment_month(info, today) == (2026, 10)
    assert _confirmed_payment_month({}, today) is None


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

    outlook = portfolio.get_dividend_forecast(db=db_session, portfolio=default_portfolio)["outlook"]

    window = _outlook_window(today)
    assert [(m["year"]) for m in outlook["months"]] == [y for y, _ in window]

    confirmed_ym = (pay_day.year, pay_day.month)
    history_months = {(today + timedelta(days=d)).month: v for d, v in zip(offsets, per_share)}
    expected_forecast = 0.0
    for ym, row in zip(window, outlook["months"]):
        if ym == confirmed_ym:
            assert [e["status"] for e in row["entries"]] == ["confirmed"]
            assert row["entries"][0]["amount"] == 5.0  # 10 shares * latest 0.50
            assert row["confirmed"] == 5.0 and row["forecasted"] == 0.0
        elif ym[1] in history_months:
            assert [e["status"] for e in row["entries"]] == ["forecasted"]
            assert row["entries"][0]["amount"] == round(10 * history_months[ym[1]], 2)
            expected_forecast += 10 * history_months[ym[1]]
        else:
            assert row["entries"] == []
    assert outlook["total_confirmed"] == 5.0
    assert outlook["total_forecasted"] == round(expected_forecast, 2)
