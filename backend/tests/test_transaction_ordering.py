"""Tests for backend/transaction_ordering.py: the shared chronological sort
key (T212 snapshot-first sync plan, §4.5)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from transaction_ordering import TXN_TYPE_ORDER, chronological_key


@dataclass
class _Txn:
    date: date
    type: str
    executed_at: datetime | None = None


def test_date_only_rows_use_type_order_fallback():
    buy = _Txn(date=date(2024, 1, 15), type="buy")
    sell = _Txn(date=date(2024, 1, 15), type="sell")
    dividend = _Txn(date=date(2024, 1, 15), type="dividend")
    ordered = sorted([sell, dividend, buy], key=chronological_key)
    assert [t.type for t in ordered] == ["buy", "dividend", "sell"]


def test_split_open_close_order_matches_existing_txn_type_order():
    assert TXN_TYPE_ORDER["split_close"] < TXN_TYPE_ORDER["split_open"]


def test_different_dates_order_by_date_first():
    early = _Txn(date=date(2024, 1, 1), type="sell")
    late = _Txn(date=date(2024, 6, 1), type="buy")
    assert chronological_key(early) < chronological_key(late)


def test_executed_at_orders_within_the_same_day():
    morning = _Txn(date=date(2024, 1, 15), type="buy",
                    executed_at=datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc))
    afternoon = _Txn(date=date(2024, 1, 15), type="buy",
                      executed_at=datetime(2024, 1, 15, 15, 0, tzinfo=timezone.utc))
    ordered = sorted([afternoon, morning], key=chronological_key)
    assert ordered == [morning, afternoon]


def test_naive_executed_at_treated_as_utc():
    naive = _Txn(date=date(2024, 1, 15), type="buy",
                 executed_at=datetime(2024, 1, 15, 9, 0))
    aware = _Txn(date=date(2024, 1, 15), type="buy",
                 executed_at=datetime(2024, 1, 15, 9, 0, tzinfo=timezone.utc))
    assert chronological_key(naive) == chronological_key(aware)


def test_ordering_is_deterministic_and_stable_across_repeated_sorts():
    rows = [
        _Txn(date=date(2024, 1, 15), type="sell"),
        _Txn(date=date(2024, 1, 15), type="buy",
             executed_at=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)),
        _Txn(date=date(2024, 1, 10), type="dividend"),
    ]
    first = sorted(rows, key=chronological_key)
    second = sorted(rows, key=chronological_key)
    assert first == second
    assert first[0].date == date(2024, 1, 10)
