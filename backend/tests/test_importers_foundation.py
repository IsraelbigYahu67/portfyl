from datetime import date

import pytest

from importers.dividends import DividendLeg, net_dividend_rows
from importers.ids import occurrence_ids
from importers.numbers import detect_decimal, parse_number


@pytest.mark.parametrize("raw, decimal, expected", [
    ("1,234.56", ".", 1234.56),
    ("$1,234.56", ".", 1234.56),
    ("-$1,234.56", ".", -1234.56),
    ("$-5.00", ".", -5.0),
    ("($12.00)", ".", -12.0),
    ("1.234,56", ",", 1234.56),
    ("1 234,56", ",", 1234.56),
    ("1 234,56", ",", 1234.56),
    ("-0,5", ",", -0.5),
    ("190.5", ".", 190.5),
    (12, ".", 12.0),
])
def test_parse_number_locales(raw, decimal, expected):
    assert parse_number(raw, decimal=decimal) == pytest.approx(expected)


@pytest.mark.parametrize("raw", [None, "", "  ", "-", "--", float("nan")])
def test_parse_number_empty_is_none(raw):
    assert parse_number(raw, decimal=".") is None


def test_parse_number_garbage_raises():
    with pytest.raises(ValueError):
        parse_number("abc", decimal=".")


def test_parse_number_rejects_wrong_locale_ambiguity():
    # "1.234" in a comma-decimal file is one thousand two hundred thirty-four.
    assert parse_number("1.234", decimal=",") == 1234.0


def test_detect_decimal():
    assert detect_decimal(["1234,56", "-3,1", "10"]) == ","
    assert detect_decimal(["1234.56", "-3.1", "10"]) == "."
    assert detect_decimal(["10", "20"]) == "."
    with pytest.raises(ValueError):
        detect_decimal(["1,5", "2.5"])


def test_occurrence_ids_distinguish_identical_rows():
    ids = occurrence_ids([("2025-01-02", "buy", "AAPL", 1), ("2025-01-02", "buy", "AAPL", 1)])
    assert ids[0] != ids[1]
    assert ids[0].endswith("#1") and ids[1].endswith("#2")


def test_occurrence_ids_stable_across_overlapping_exports():
    q1 = [("2025-01-02", "buy", "AAPL", 1), ("2025-02-03", "sell", "AAPL", 1)]
    full_year = [*q1, ("2025-07-01", "buy", "MSFT", 2)]
    assert occurrence_ids(q1) == occurrence_ids(full_year)[:2]


def _leg(kind, amount, key="A1", **kw):
    base = dict(group_key=key, kind=kind, ticker="AAPL", name="Apple",
                pay_date=date(2025, 2, 15), currency="USD", amount=amount, shares=10.0)
    base.update(kw)
    return DividendLeg(**base)


def test_net_dividend_single_row():
    rows, errors, skipped = net_dividend_rows([_leg("gross", 2.4), _leg("tax", -0.36)], source="ibkr")
    assert errors == [] and skipped == 0
    [row] = rows
    assert row["type"] == "dividend"
    assert row["cash_amount"] == pytest.approx(2.04)
    assert row["cash_currency"] == "USD"
    assert row["shares"] == 10.0
    assert row["price"] == pytest.approx(0.204)
    assert row["source"] == "ibkr" and row["source_event_stream"] == "dividends"
    assert row["source_event_id"] == "div:A1"


def test_net_dividend_reversal_and_reissue():
    legs = [_leg("gross", 2.4), _leg("tax", -0.36), _leg("gross", -2.4), _leg("tax", 0.36),
            _leg("gross", 2.5), _leg("tax", -0.375)]
    rows, errors, _ = net_dividend_rows(legs, source="ibkr")
    assert errors == []
    assert [r["cash_amount"] for r in rows] == [pytest.approx(2.125)]


def test_fully_reversed_dividend_is_skipped():
    rows, errors, skipped = net_dividend_rows([_leg("gross", 2.4), _leg("gross", -2.4)], source="ibkr")
    assert rows == [] and errors == [] and skipped == 1


def test_tax_without_gross_is_error():
    rows, errors, _ = net_dividend_rows([_leg("tax", -0.36)], source="ibkr")
    assert rows == [] and len(errors) == 1 and "AAPL" in errors[0]


def test_mixed_currency_group_is_error():
    _, errors, _ = net_dividend_rows([_leg("gross", 2.4), _leg("tax", -0.5, currency="EUR")], source="ibkr")
    assert errors


def test_unknown_share_count_uses_one():
    [row], _, _ = net_dividend_rows([_leg("gross", 3.0, shares=None)], source="degiro")
    assert row["shares"] == 1.0 and row["price"] == 3.0
