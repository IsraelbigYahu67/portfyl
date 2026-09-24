"""Read-only comparison of ledger open quantities with the broker's current
position snapshot (T212 snapshot-first sync plan, §6.3). A mismatch is only
reported -- it never creates an adjustment row."""

from __future__ import annotations

import pytest

from broker_reconciliation import QUANTITY_TOLERANCE, reconcile_positions
from models import BrokerPosition


def _pos(ticker, quantity, provider_ticker=None):
    return BrokerPosition(
        ticker=ticker,
        provider_ticker=provider_ticker or f"{ticker}_US_EQ",
        quantity=quantity,
    )


def _reconcile(ledger, positions, **overrides):
    kwargs = dict(snapshot_available=True, history_complete=True)
    kwargs.update(overrides)
    return reconcile_positions(ledger_shares=ledger, positions=positions, **kwargs)


class TestMatched:
    def test_quantities_within_tolerance_match(self):
        result = _reconcile({"AAPL": 10.00005}, [_pos("AAPL", 10.0)])

        assert result["status"] == "matched"
        assert result["reason"] is None
        assert result["matched_count"] == 1
        assert result["different"] == []
        assert result["tolerance"] == QUANTITY_TOLERANCE

    def test_empty_snapshot_and_empty_ledger_match(self):
        result = _reconcile({}, [])

        assert result["status"] == "matched"
        assert result["matched_count"] == 0

    def test_positions_sharing_a_normalized_ticker_are_summed(self):
        result = _reconcile(
            {"VUSA": 5.0},
            [_pos("VUSA", 3.0, "VUSA_EQ"), _pos("VUSA", 2.0, "VUSAl_EQ")],
        )

        assert result["status"] == "matched"
        assert result["matched_count"] == 1


class TestDifferent:
    def test_unadjusted_forward_split_is_ledger_lower(self):
        result = _reconcile({"NVDA": 10.0}, [_pos("NVDA", 100.0, "NVDA_US_EQ")])

        assert result["status"] == "different"
        assert result["matched_count"] == 0
        (item,) = result["different"]
        assert item["ticker"] == "NVDA"
        assert item["provider_tickers"] == ["NVDA_US_EQ"]
        assert item["broker_quantity"] == pytest.approx(100.0)
        assert item["ledger_quantity"] == pytest.approx(10.0)
        assert item["difference"] == pytest.approx(-90.0)
        assert item["direction"] == "ledger_lower"
        assert "unsupported_corporate_action" in item["likely_causes"]

    def test_ledger_higher_than_broker(self):
        result = _reconcile({"AAPL": 12.0}, [_pos("AAPL", 10.0)])

        (item,) = result["different"]
        assert item["direction"] == "ledger_higher"
        assert item["difference"] == pytest.approx(2.0)
        assert "csv_api_overlap" in item["likely_causes"]

    def test_position_without_ledger_history_is_ledger_missing(self):
        result = _reconcile({}, [_pos("AAPL", 5.0)])

        (item,) = result["different"]
        assert item["direction"] == "ledger_missing"
        assert item["ledger_quantity"] == 0.0
        assert "incomplete_provider_history" in item["likely_causes"]

    def test_open_ledger_without_a_broker_position_is_broker_missing(self):
        result = _reconcile({"AAPL": 5.0}, [])

        (item,) = result["different"]
        assert item["ticker"] == "AAPL"
        assert item["direction"] == "broker_missing"
        assert item["broker_quantity"] == 0.0
        assert item["provider_tickers"] == []

    def test_only_mismatching_tickers_are_listed(self):
        result = _reconcile(
            {"AAPL": 10.0, "NVDA": 10.0},
            [_pos("AAPL", 10.0), _pos("NVDA", 100.0)],
        )

        assert result["status"] == "different"
        assert result["matched_count"] == 1
        assert [item["ticker"] for item in result["different"]] == ["NVDA"]

    def test_stale_snapshot_is_named_as_a_possible_cause(self):
        stale = _reconcile({"AAPL": 12.0}, [_pos("AAPL", 10.0)], snapshot_stale=True)
        fresh = _reconcile({"AAPL": 12.0}, [_pos("AAPL", 10.0)])

        assert "snapshot_stale" in stale["different"][0]["likely_causes"]
        assert "snapshot_stale" not in fresh["different"][0]["likely_causes"]


class TestUnavailable:
    def test_no_snapshot_means_unavailable(self):
        result = _reconcile({"AAPL": 10.0}, [], snapshot_available=False)

        assert result["status"] == "unavailable"
        assert result["reason"] == "no_snapshot"
        assert result["different"] == []
        assert result["matched_count"] == 0

    def test_incomplete_history_means_unavailable(self):
        result = _reconcile({}, [_pos("AAPL", 10.0)], history_complete=False)

        assert result["status"] == "unavailable"
        assert result["reason"] == "history_incomplete"
        assert result["different"] == []

    def test_incomplete_history_takes_precedence_over_a_missing_snapshot(self):
        result = _reconcile({}, [], snapshot_available=False, history_complete=False)

        assert result["reason"] == "history_incomplete"
