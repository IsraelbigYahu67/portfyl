"""Czech §4 ZDP time test: the holding period must *exceed* 3 years.

The test is decided by the calendar anniversary of the purchase, not by a day
count, so these cases pin the exact boundary day around leap years and 29 Feb.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from tests.helpers import make_txn
from routers.analytics import (
    _compute_capital_gains,
    _compute_czech_tax_by_year,
    _compute_unrealized_gains,
    _first_exempt_day,
    tax_report,
)


def _round_trip(buy_day: date, sell_day: date) -> dict:
    """One lot bought and fully sold; FX 1 so CZK == native."""
    gains = _compute_capital_gains([
        make_txn("AAPL", "buy", 1000, 100.0, date=buy_day, fx_to_czk=1.0),
        make_txn("AAPL", "sell", 1000, 150.0, date=sell_day, fx_to_czk=1.0),
    ])
    assert len(gains) == 1
    return gains[0]


@pytest.mark.parametrize(
    ("buy_day", "last_taxable_day", "first_exempt_day"),
    [
        # Window without a leap day: 1095 days is exactly 3 years, 1096 exceeds it.
        (date(2021, 1, 10), date(2024, 1, 10), date(2024, 1, 11)),
        # Window containing 29 Feb 2024: 1096 days is exactly 3 years.
        (date(2021, 3, 1), date(2024, 3, 1), date(2024, 3, 2)),
        (date(2020, 3, 1), date(2023, 3, 1), date(2023, 3, 2)),
        # Bought on the leap day: the anniversary is 28 Feb 2023.
        (date(2020, 2, 29), date(2023, 2, 28), date(2023, 3, 1)),
        # Third anniversary falls on a leap day.
        (date(2021, 2, 28), date(2024, 2, 28), date(2024, 2, 29)),
        (date(2021, 3, 1), date(2024, 3, 1), date(2024, 3, 2)),
    ],
)
def test_time_test_flips_the_day_after_the_third_anniversary(
    buy_day, last_taxable_day, first_exempt_day
):
    assert _first_exempt_day(buy_day) == first_exempt_day

    on_anniversary = _round_trip(buy_day, last_taxable_day)
    assert on_anniversary["cz_exempt_time_test"] is False

    day_after = _round_trip(buy_day, first_exempt_day)
    assert day_after["cz_exempt_time_test"] is True
    assert day_after["cz_exempt_date"] == first_exempt_day.isoformat()
    assert on_anniversary["cz_exempt_date"] == first_exempt_day.isoformat()


def test_the_old_day_count_got_this_case_wrong():
    # 2021-01-10 -> 2024-01-11 is 1096 days and has no leap day in it. The old
    # `holding_days > 1096` marked it taxable; it is exempt.
    gain = _round_trip(date(2021, 1, 10), date(2024, 1, 11))
    assert gain["holding_days"] == 1096
    assert gain["cz_exempt_time_test"] is True


def test_sale_before_the_boundary_stays_taxable_and_long_after_is_exempt():
    assert _round_trip(date(2021, 1, 10), date(2023, 12, 1))["cz_exempt_time_test"] is False
    assert _round_trip(date(2020, 1, 1), date(2024, 6, 1))["cz_exempt_time_test"] is True


def test_czech_summary_follows_the_corrected_time_test():
    def summary(sell_day: date) -> dict:
        gains = [_round_trip(date(2021, 1, 10), sell_day)]
        (year,) = _compute_czech_tax_by_year(gains)
        return year

    taxable = summary(date(2024, 1, 10))
    exempt = summary(date(2024, 1, 11))

    # Gain 1000 * (150 - 100) = 50 000 CZK; proceeds 150 000 fail the value test.
    assert taxable["value_test_passed"] is False
    assert taxable["time_test_exempt_gain_czk"] == 0.0
    assert taxable["taxable_total_czk"] == pytest.approx(50_000.0)
    assert taxable["exempt_total_czk"] == 0.0

    assert exempt["time_test_exempt_gain_czk"] == pytest.approx(50_000.0)
    assert exempt["taxable_total_czk"] == 0.0
    assert exempt["exempt_total_czk"] == pytest.approx(50_000.0)


class _Today(date):
    """`date` whose today() is fixed; set `_Today.now` before use."""

    now = date(2024, 1, 10)

    @classmethod
    def today(cls):
        return cls.now


def _unrealized_lot(buy_day: date, today: date) -> dict:
    _Today.now = today
    txns = [make_txn("AAPL", "buy", 10, 100.0, date=buy_day)]
    with patch("routers.analytics.date", _Today), \
         patch("routers.analytics.market_data.get_infos",
               return_value={"AAPL": {"currentPrice": 120.0, "currency": "USD"}}):
        (lot,) = _compute_unrealized_gains(txns)
    return lot


def test_unrealized_lot_is_not_exempt_on_the_anniversary_but_is_the_day_after():
    buy_day = date(2021, 1, 10)

    on_anniversary = _unrealized_lot(buy_day, date(2024, 1, 10))
    assert on_anniversary["cz_exempt_time_test"] is False
    assert on_anniversary["cz_days_to_exemption"] == 1
    assert on_anniversary["cz_exempt_date"] == "2024-01-11"

    day_after = _unrealized_lot(buy_day, date(2024, 1, 11))
    assert day_after["cz_exempt_time_test"] is True
    assert day_after["cz_days_to_exemption"] == 0
    assert day_after["cz_exempt_date"] == "2024-01-11"


def test_unrealized_lot_bought_on_the_leap_day():
    buy_day = date(2020, 2, 29)

    assert _unrealized_lot(buy_day, date(2023, 2, 28))["cz_exempt_time_test"] is False
    lot = _unrealized_lot(buy_day, date(2023, 3, 1))
    assert lot["cz_exempt_time_test"] is True
    assert lot["cz_exempt_date"] == "2023-03-01"


def test_unrealized_and_realized_agree_on_the_exempt_date():
    buy_day = date(2021, 3, 1)
    realized = _round_trip(buy_day, date(2024, 3, 2))
    unrealized = _unrealized_lot(buy_day, date(2023, 6, 1))
    assert realized["cz_exempt_date"] == unrealized["cz_exempt_date"] == "2024-03-02"


def test_tax_report_response_carries_the_corrected_flags(db_session, pid, default_portfolio):
    db_session.add_all([
        make_txn("AAPL", "buy", 1000, 100.0, date=date(2021, 1, 10), fx_to_czk=1.0, portfolio_id=pid),
        make_txn("AAPL", "sell", 500, 150.0, date=date(2024, 1, 10), fx_to_czk=1.0, portfolio_id=pid),
        make_txn("AAPL", "sell", 500, 150.0, date=date(2024, 1, 11), fx_to_czk=1.0, portfolio_id=pid),
    ])
    db_session.commit()

    with patch("routers.analytics.market_data.get_infos", return_value={}):
        report = tax_report(year=None, db=db_session, portfolio=default_portfolio)

    by_sell = {g["sell_date"]: g for g in report["gains"]}
    assert by_sell["2024-01-10"]["cz_exempt_time_test"] is False
    assert by_sell["2024-01-11"]["cz_exempt_time_test"] is True
    assert by_sell["2024-01-10"]["cz_exempt_date"] == "2024-01-11"

    (year,) = report["czech_tax"]
    assert year["time_test_exempt_gain_czk"] == pytest.approx(25_000.0)
    assert year["taxable_gain_czk_pre_cap"] == pytest.approx(25_000.0)
