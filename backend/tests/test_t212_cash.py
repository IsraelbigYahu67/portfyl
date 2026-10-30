from datetime import datetime, timezone

import pytest

from t212_cash import (
    CashRow,
    UnsupportedCash,
    cash_event_id,
    cash_event_time,
    map_cash_event,
)


def _item(kind, amount, reference="ref-1", currency="CZK", when="2026-03-01T10:15:30.123Z"):
    return {
        "type": kind,
        "amount": amount,
        "currency": currency,
        "reference": reference,
        "dateTime": when,
    }


@pytest.mark.parametrize(
    "kind, amount, expected",
    [
        ("DEPOSIT", 3200.0, "deposit"),
        ("WITHDRAW", -218.8, "withdrawal"),
        ("FEE", -0.16, "fee"),
        ("INTEREST_ON_FREE_CASH", 0.42, "interest"),
        ("LENDING_INTEREST", 0.01, "interest"),
        ("TRANSFER", 200.0, "deposit"),
        ("TRANSFER", -200.0, "withdrawal"),
    ],
)
def test_types_map_per_the_signed_off_record(kind, amount, expected):
    row = map_cash_event(_item(kind, amount))
    assert isinstance(row, CashRow)
    assert row.type == expected
    assert row.amount == abs(amount)
    assert row.currency == "CZK"
    assert row.event_id == "cash:ref-1"


def test_timestamp_is_utc_and_date_is_the_utc_day():
    row = map_cash_event(_item("DEPOSIT", 5, when="2026-03-01T23:59:59.999Z"))
    assert row.executed_at == datetime(2026, 3, 1, 23, 59, 59, 999000, tzinfo=timezone.utc)
    assert row.date.isoformat() == "2026-03-01"


def test_transfer_keeps_its_source_subtype_in_the_notes():
    assert "TRANSFER" in map_cash_event(_item("TRANSFER", 80.0)).notes
    assert "DEPOSIT" in map_cash_event(_item("DEPOSIT", 80.0)).notes


@pytest.mark.parametrize(
    "item",
    [
        _item("DEPOSIT", 0),
        _item("DEPOSIT", None),
        _item("DEPOSIT", "abc"),
        _item("DEPOSIT", float("nan")),
        _item("DEPOSIT", 5, currency=""),
        _item("DEPOSIT", 5, when=None),
        _item("DEPOSIT", 5, when="not a date"),
        _item("TRANSFER", 0),
        _item("CURRENCY_CONVERSION", 5),
        _item("MYSTERY", 5),
        _item(None, 5),
    ],
)
def test_anything_unproven_is_unsupported(item):
    verdict = map_cash_event(item)
    assert isinstance(verdict, UnsupportedCash)
    assert verdict.reason


def test_a_sign_that_contradicts_the_proven_direction_is_unsupported():
    """Signs were proven per type; a contradiction is a data problem, not a
    reason to guess the direction."""
    assert isinstance(map_cash_event(_item("DEPOSIT", -5)), UnsupportedCash)
    assert isinstance(map_cash_event(_item("WITHDRAW", 5)), UnsupportedCash)
    assert isinstance(map_cash_event(_item("FEE", 5)), UnsupportedCash)
    assert isinstance(map_cash_event(_item("INTEREST_ON_FREE_CASH", -5)), UnsupportedCash)


def test_event_identity_prefers_the_reference_and_falls_back_to_a_fingerprint():
    assert cash_event_id(_item("DEPOSIT", 5, reference="abc")) == "cash:abc"
    no_ref = _item("DEPOSIT", 5, reference=None)
    assert cash_event_id(no_ref).startswith("cash-fp:")
    assert cash_event_id(no_ref) == cash_event_id(dict(no_ref))
    assert cash_event_id(no_ref) != cash_event_id(_item("DEPOSIT", 6, reference=None))


def test_event_time_parses_or_returns_none():
    assert cash_event_time(_item("DEPOSIT", 5)) == datetime(
        2026, 3, 1, 10, 15, 30, 123000, tzinfo=timezone.utc
    )
    assert cash_event_time(_item("DEPOSIT", 5, when=None)) is None


def test_currency_conversion_legs_are_recognised_by_their_shared_instant():
    from t212_cash import fx_conversion_event_ids

    when = "2026-06-03T11:13:59.410Z"
    items = [
        _item("FEE", -0.16, "fee", "CZK", when),
        _item("DEPOSIT", 104.08, "in", "CZK", when),
        _item("WITHDRAW", -5, "out", "USD", when),
    ]
    assert fx_conversion_event_ids(items) == {"cash:in", "cash:out"}


@pytest.mark.parametrize(
    "items",
    [
        # same currency: an ordinary deposit and withdrawal
        [_item("DEPOSIT", 100, "a"), _item("WITHDRAW", -50, "b")],
        # different instants
        [_item("DEPOSIT", 100, "a", "CZK", "2026-06-03T11:00:00Z"),
         _item("WITHDRAW", -5, "b", "USD", "2026-06-03T11:00:01Z")],
        # ambiguous: two deposits at the same instant
        [_item("DEPOSIT", 100, "a"), _item("DEPOSIT", 5, "c"), _item("WITHDRAW", -5, "b", "USD")],
        # a lone withdrawal
        [_item("WITHDRAW", -5, "b", "USD")],
    ],
)
def test_unpaired_or_ambiguous_cash_events_are_not_conversions(items):
    from t212_cash import fx_conversion_event_ids

    assert fx_conversion_event_ids(items) == set()
