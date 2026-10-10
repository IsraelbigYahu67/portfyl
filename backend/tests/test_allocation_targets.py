"""Target allocation: pure validation and drift (plan 2026-10-10, Task 1)."""

from decimal import Decimal

import pytest

from allocation_targets import (
    TargetSetError,
    TargetSpec,
    compute_drift,
    is_complete,
    normalize_group,
    normalize_ticker,
    validate_target_set,
)


def spec(ticker, pct, group=None):
    return TargetSpec(ticker, Decimal(pct), group)


def holding(ticker, value, *, closed=False, price_status="live", name=None):
    return {
        "ticker": ticker,
        "name": name or ticker.title(),
        "market_value": value,
        "closed": closed,
        "price_status": price_status,
    }


class TestNormalize:
    def test_ticker_is_trimmed_and_upper_cased(self):
        assert normalize_ticker("  vwce.de ") == "VWCE.DE"
        assert normalize_ticker("brk-b") == "BRK-B"

    @pytest.mark.parametrize("raw", ["", "   ", "AA PL", "A" * 33, "AAPL;DROP"])
    def test_invalid_ticker_is_rejected(self, raw):
        with pytest.raises(TargetSetError):
            normalize_ticker(raw)

    def test_blank_group_is_none(self):
        assert normalize_group("   ") is None
        assert normalize_group(None) is None

    def test_group_is_trimmed(self):
        assert normalize_group("  Core ") == "Core"

    def test_long_group_is_rejected(self):
        with pytest.raises(TargetSetError, match="at most 40"):
            normalize_group("x" * 41)


class TestValidateTargetSet:
    def test_total_is_returned(self):
        assert validate_target_set([spec("AAPL", "60"), spec("MSFT", "40")]) == Decimal("100")

    def test_partial_and_empty_sets_are_allowed(self):
        assert validate_target_set([spec("AAPL", "50")]) == Decimal("50")
        assert validate_target_set([]) == Decimal("0")

    def test_zero_target_is_a_valid_explicit_target(self):
        assert validate_target_set([spec("AAPL", "0")]) == Decimal("0")

    def test_duplicate_ticker_rejected(self):
        with pytest.raises(TargetSetError, match="AAPL has more than one target"):
            validate_target_set([spec("AAPL", "10"), spec("AAPL", "20")])

    def test_more_than_two_decimals_rejected(self):
        with pytest.raises(TargetSetError, match="two decimal places"):
            validate_target_set([spec("AAPL", "33.333")])

    @pytest.mark.parametrize("pct", ["-1", "100.01"])
    def test_out_of_range_rejected(self, pct):
        with pytest.raises(TargetSetError, match="between 0 and 100"):
            validate_target_set([spec("AAPL", pct)])

    def test_sum_over_tolerance_rejected(self):
        with pytest.raises(TargetSetError, match="more than 100%"):
            validate_target_set([spec("A", "60"), spec("B", "40.02")])

    def test_sum_within_tolerance_allowed(self):
        assert validate_target_set([spec("A", "60"), spec("B", "40.01")]) == Decimal("100.01")

    def test_too_many_targets_rejected(self):
        with pytest.raises(TargetSetError, match="at most 200"):
            validate_target_set([spec(f"T{i}", "0") for i in range(201)])

    def test_is_complete_uses_the_tolerance(self):
        assert is_complete(Decimal("99.99")) is True
        assert is_complete(Decimal("100.01")) is True
        assert is_complete(Decimal("99.98")) is False


class TestComputeDrift:
    def test_drift_for_held_and_unheld_targets(self):
        result = compute_drift(
            [holding("AAPL", 700.0, name="Apple"), holding("TSLA", 300.0, name="Tesla")],
            [spec("AAPL", "60", "Core"), spec("MSFT", "30", "Core")],
        )

        assert result["total_value"] == 1000.0
        assert result["target_total_pct"] == 90.0
        assert result["is_complete"] is False
        assert result["unassigned_pct"] == 30.0
        assert result["warnings"] == ["targets_incomplete"]
        assert result["rows"] == [
            {"ticker": "AAPL", "name": "Apple", "group": "Core", "held": True,
             "target_pct": 60.0, "current_pct": 70.0, "drift_pct": 10.0,
             "market_value": 700.0, "value_to_target": -100.0},
            {"ticker": "MSFT", "name": None, "group": "Core", "held": False,
             "target_pct": 30.0, "current_pct": 0.0, "drift_pct": -30.0,
             "market_value": 0.0, "value_to_target": 300.0},
            {"ticker": "TSLA", "name": "Tesla", "group": None, "held": True,
             "target_pct": None, "current_pct": 30.0, "drift_pct": None,
             "market_value": 300.0, "value_to_target": None},
        ]
        assert result["groups"] == [
            {"group": "Core", "target_pct": 90.0, "current_pct": 70.0, "drift_pct": -20.0},
        ]

    def test_ticker_matching_ignores_case(self):
        result = compute_drift([holding("vwce.de", 500.0)], [spec("VWCE.DE", "100")])
        assert result["rows"][0]["held"] is True
        assert result["rows"][0]["current_pct"] == 100.0
        assert result["unassigned_pct"] == 0.0

    def test_closed_positions_count_as_not_held(self):
        result = compute_drift(
            [holding("AAPL", 0.0, closed=True), holding("MSFT", 1000.0)],
            [spec("AAPL", "50")],
        )
        aapl = result["rows"][0]
        assert aapl["held"] is False and aapl["current_pct"] == 0.0
        assert [r["ticker"] for r in result["rows"]] == ["AAPL", "MSFT"]

    def test_empty_portfolio_has_no_division_by_zero(self):
        result = compute_drift([], [spec("AAPL", "100")])
        row = result["rows"][0]
        assert result["total_value"] == 0.0
        assert row["current_pct"] == 0.0 and row["drift_pct"] == -100.0
        assert row["value_to_target"] is None
        assert result["is_complete"] is True
        assert result["warnings"] == []

    def test_missing_price_is_flagged(self):
        result = compute_drift(
            [holding("AAPL", 0.0, price_status="missing"), holding("MSFT", 1000.0)],
            [spec("AAPL", "50"), spec("MSFT", "50")],
        )
        assert result["missing_price_tickers"] == ["AAPL"]
        assert result["warnings"] == ["missing_prices"]

    def test_unassigned_holdings_are_sorted_by_value(self):
        result = compute_drift([holding("A", 100.0), holding("B", 300.0)], [])
        assert [r["ticker"] for r in result["rows"]] == ["B", "A"]
        assert result["unassigned_pct"] == 100.0

    def test_groups_keep_first_seen_order_and_skip_ungrouped_targets(self):
        result = compute_drift(
            [holding("A", 500.0), holding("B", 500.0)],
            [spec("A", "40", "Growth"), spec("C", "10"), spec("B", "50", "Income")],
        )
        assert [g["group"] for g in result["groups"]] == ["Growth", "Income"]
