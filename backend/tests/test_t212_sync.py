"""Tests for backend/t212_sync.py: the fast T212 positions/summary snapshot.

Task 2 of docs/superpowers/plans/2026-09-20-t212-snapshot-first-sync.md.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

import t212_sync
from models import BrokerPosition
from tests.fixtures.t212 import t212_position, t212_positions_response


def test_fetch_positions_calls_expected_endpoint_and_parses_bare_array():
    response = MagicMock(status_code=200)
    response.json.return_value = t212_positions_response(t212_position())

    with patch("t212_sync.httpx.get", return_value=response) as get:
        result = t212_sync._fetch_positions(
            "https://live.trading212.com/api/v0", {"Authorization": "x"}
        )

    get.assert_called_once_with(
        "https://live.trading212.com/api/v0/equity/positions",
        headers={"Authorization": "x"},
        timeout=15,
    )
    assert result == t212_positions_response(t212_position())


def test_fetch_positions_401_raises_http_exception():
    response = MagicMock(status_code=401)
    with patch("t212_sync.httpx.get", return_value=response):
        with pytest.raises(Exception) as exc_info:
            t212_sync._fetch_positions("base", {})
    assert exc_info.value.status_code == 401


class TestFetchSnapshot:
    """Summary and positions must fail independently of each other."""

    def _summary_fn(self, return_value=None, error=None):
        def fn(base, headers):
            if error:
                raise error
            return return_value
        return fn

    def test_both_succeed(self):
        with patch("t212_sync._fetch_positions", return_value=[t212_position()]):
            result = t212_sync.fetch_snapshot(
                "base", {}, fetch_summary=self._summary_fn(return_value={"currency": "USD"})
            )
        assert result.summary == {"currency": "USD"}
        assert result.summary_error is None
        assert result.positions == [t212_position()]
        assert result.positions_error is None

    def test_summary_fails_positions_still_returned(self):
        with patch("t212_sync._fetch_positions", return_value=[t212_position()]):
            result = t212_sync.fetch_snapshot(
                "base", {}, fetch_summary=self._summary_fn(error=RuntimeError("upstream down"))
            )
        assert result.summary is None
        assert result.summary_error == "upstream down"
        assert result.positions == [t212_position()]
        assert result.positions_error is None

    def test_positions_fail_summary_still_returned(self):
        with patch("t212_sync._fetch_positions", side_effect=RuntimeError("rate limited")):
            result = t212_sync.fetch_snapshot(
                "base", {}, fetch_summary=self._summary_fn(return_value={"currency": "USD"})
            )
        assert result.summary == {"currency": "USD"}
        assert result.positions is None
        assert result.positions_error == "rate limited"

    def test_both_fail_independently(self):
        with patch("t212_sync._fetch_positions", side_effect=RuntimeError("positions down")):
            result = t212_sync.fetch_snapshot(
                "base", {}, fetch_summary=self._summary_fn(error=RuntimeError("summary down"))
            )
        assert result.summary is None and result.summary_error == "summary down"
        assert result.positions is None and result.positions_error == "positions down"


class TestReplacePositions:
    def test_inserts_current_official_position_shape(self, db_session, default_portfolio):
        raw = [{
            "averagePricePaid": 150.0,
            "createdAt": "2024-01-15T10:00:00Z",
            "currentPrice": 175.0,
            "instrument": {
                "currency": "USD",
                "isin": "US0378331005",
                "name": "Apple",
                "ticker": "AAPL_US_EQ",
            },
            "quantity": 10.0,
            "quantityAvailableForTrading": 8.0,
            "quantityInPies": 2.0,
            "walletImpact": {
                "currency": "CZK",
                "currentValue": 40_000.0,
                "fxImpact": 5.0,
                "totalCost": 37_500.0,
                "unrealizedProfitLoss": 2_500.0,
            },
        }]

        count = t212_sync.replace_positions(db_session, default_portfolio, raw)
        db_session.commit()

        assert count == 1
        row = db_session.query(BrokerPosition).one()
        assert row.provider_ticker == "AAPL_US_EQ"
        assert row.ticker == "AAPL"
        assert row.name == "Apple"
        assert row.currency == "USD"
        assert row.quantity == 10.0
        assert row.avg_price == 150.0
        assert row.current_price == 175.0
        assert row.pie_quantity == 2.0
        assert row.ppl == 2_500.0
        assert row.fx_ppl == 5.0
        assert row.initial_fill_date.replace(tzinfo=timezone.utc) == datetime(
            2024, 1, 15, 10, 0, tzinfo=timezone.utc
        )

    def test_inserts_mapped_fields(self, db_session, default_portfolio):
        raw = [t212_position(ticker="AAPL_US_EQ", quantity=10.0, averagePrice=150.0,
                              currentPrice=175.0, ppl=250.0, fxPpl=5.0, pieQuantity=2.0)]
        count = t212_sync.replace_positions(db_session, default_portfolio, raw)
        db_session.commit()

        assert count == 1
        row = db_session.query(BrokerPosition).one()
        assert row.workspace_id == default_portfolio.workspace_id
        assert row.portfolio_id == default_portfolio.id
        assert row.broker == "trading212"
        assert row.provider_ticker == "AAPL_US_EQ"
        assert row.ticker == "AAPL"
        assert row.quantity == 10.0
        assert row.avg_price == 150.0
        assert row.current_price == 175.0
        assert row.ppl == 250.0
        assert row.fx_ppl == 5.0
        assert row.pie_quantity == 2.0
        assert row.initial_fill_date is not None

    def test_inserts_legacy_flat_position_shape(self, db_session, default_portfolio):
        raw = [{
            "ticker": "AAPL_US_EQ",
            "quantity": 10.0,
            "averagePrice": 150.0,
            "currentPrice": 175.0,
            "ppl": 250.0,
            "fxPpl": 5.0,
            "pieQuantity": 2.0,
            "initialFillDate": "2024-01-15T10:00:00Z",
        }]

        assert t212_sync.replace_positions(db_session, default_portfolio, raw) == 1
        db_session.commit()
        row = db_session.query(BrokerPosition).one()
        assert (row.provider_ticker, row.avg_price, row.ppl, row.fx_ppl) == (
            "AAPL_US_EQ", 150.0, 250.0, 5.0,
        )

    def test_normalizes_exchange_suffix_ticker(self, db_session, default_portfolio):
        raw = [t212_position(ticker="NVDd", averagePrice=100.0, currentPrice=110.0)]
        t212_sync.replace_positions(db_session, default_portfolio, raw)
        db_session.commit()
        row = db_session.query(BrokerPosition).one()
        assert row.provider_ticker == "NVDd"
        assert row.ticker == "NVD.DE"

    def test_replace_clears_previous_rows(self, db_session, default_portfolio):
        t212_sync.replace_positions(
            db_session, default_portfolio, [t212_position(ticker="AAPL_US_EQ")]
        )
        db_session.commit()

        t212_sync.replace_positions(
            db_session, default_portfolio, [t212_position(ticker="MSFT_US_EQ")]
        )
        db_session.commit()

        tickers = {r.ticker for r in db_session.query(BrokerPosition).all()}
        assert tickers == {"MSFT"}

    def test_successful_empty_response_clears_stale_positions(self, db_session, default_portfolio):
        t212_sync.replace_positions(
            db_session, default_portfolio, [t212_position(ticker="AAPL_US_EQ")]
        )
        db_session.commit()

        t212_sync.replace_positions(db_session, default_portfolio, [])
        db_session.commit()

        assert db_session.query(BrokerPosition).count() == 0

    def test_skips_rows_missing_required_fields(self, db_session, default_portfolio):
        raw = [
            {"ticker": "", "quantity": 1.0, "averagePrice": 1.0},  # no ticker
            {"ticker": "ABC_US_EQ", "quantity": None, "averagePrice": 1.0},  # no quantity
            {"ticker": "DEF_US_EQ", "quantity": 1.0, "averagePrice": None},  # no avg price
            t212_position(ticker="GHI_US_EQ"),
        ]
        count = t212_sync.replace_positions(db_session, default_portfolio, raw)
        db_session.commit()
        assert count == 1
        assert db_session.query(BrokerPosition).one().ticker == "GHI"

    def test_other_portfolio_rows_untouched(self, db_session, default_portfolio):
        from models import Portfolio

        other = Portfolio(
            workspace_id=default_portfolio.workspace_id,
            name="Other",
        )
        db_session.add(other)
        db_session.commit()
        db_session.refresh(other)

        t212_sync.replace_positions(db_session, other, [t212_position(ticker="TSLA_US_EQ")])
        db_session.commit()

        t212_sync.replace_positions(db_session, default_portfolio, [t212_position(ticker="AAPL_US_EQ")])
        db_session.commit()

        other_tickers = {
            r.ticker for r in db_session.query(BrokerPosition)
            .filter(BrokerPosition.portfolio_id == other.id).all()
        }
        assert other_tickers == {"TSLA"}


class TestSnapshotFreshness:
    def test_none_is_not_fresh(self):
        assert t212_sync.is_snapshot_fresh(None) is False

    def test_fresh_within_window(self):
        now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
        as_of = now - timedelta(hours=24)
        assert t212_sync.is_snapshot_fresh(as_of, now=now) is True

    def test_stale_past_window(self):
        now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
        as_of = now - timedelta(hours=26)
        assert t212_sync.is_snapshot_fresh(as_of, now=now) is False

    def test_boundary_exactly_25_hours_is_fresh(self):
        now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
        as_of = now - timedelta(hours=25)
        assert t212_sync.is_snapshot_fresh(as_of, now=now) is True

    def test_naive_datetime_treated_as_utc(self):
        now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
        as_of_naive = datetime(2026, 9, 20, 0, 0)  # 12h before `now`, no tzinfo
        assert t212_sync.is_snapshot_fresh(as_of_naive, now=now) is True
