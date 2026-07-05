import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routers.portfolio import aggregate_day_change


def test_aggregate_day_change_basic():
    rows = [
        {"shares": 10, "start": 100.0, "end": 110.0, "fx": 1.0},  # +100
        {"shares": 5,  "start": 200.0, "end": 190.0, "fx": 1.0},  # -50
    ]
    change, prev_value = aggregate_day_change(rows)
    assert round(change, 2) == 50.0
    assert round(prev_value, 2) == 2000.0  # 10*100 + 5*200


def test_aggregate_day_change_applies_fx():
    rows = [{"shares": 1, "start": 100.0, "end": 110.0, "fx": 23.0}]  # +10 native * 23
    change, prev_value = aggregate_day_change(rows)
    assert round(change, 2) == 230.0
    assert round(prev_value, 2) == 2300.0


def test_aggregate_day_change_empty():
    assert aggregate_day_change([]) == (0.0, 0.0)
