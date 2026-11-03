"""Tests for t212_sync.finalize_run (T212 snapshot-first sync plan, Task 4
scoped slice). Not wired into any automatic path -- these call it directly.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

import t212_sync
from account_identity import account_fingerprint
from models import (BrokerConnection, BrokerCorporateAction, BrokerCorporateActionApplication,
                    BrokerSyncEvent, BrokerSyncRun, Transaction)
from tests.helpers import make_txn


@pytest.fixture
def connection(db_session, default_portfolio):
    fingerprint = account_fingerprint(
        broker="trading212", environment="live", provider_account_id=1,
    )
    default_portfolio.t212_account_fingerprint = fingerprint
    conn = BrokerConnection(
        workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
        broker="trading212", api_key="k" * 20, account_fingerprint=fingerprint,
    )
    db_session.add(conn)
    db_session.commit()
    db_session.refresh(conn)
    return conn


@pytest.fixture
def completed_run(db_session, default_portfolio, connection):
    run = BrokerSyncRun(
        workspace_id=default_portfolio.workspace_id,
        portfolio_id=default_portfolio.id,
        connection_id=connection.id,
        broker="trading212",
        account_fingerprint=connection.account_fingerprint,
        credential_generation=connection.credential_generation,
        mode="incremental",
        state="finalizing",
        orders_complete=True,
        dividends_complete=True,
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    return run


def _order_event(db, run, *, event_id="fill:f1", ticker="AAPL_US_EQ", side="BUY",
                  qty=10, price=150.0, day="2024-06-01", currency="USD",
                  fill_type=None, wallet_impact=None, status="FILLED"):
    fill = {"id": event_id.split(":", 1)[1], "quantity": qty, "price": price,
            "filledAt": f"{day}T10:00:00Z"}
    if fill_type is not None:
        fill["type"] = fill_type
    if wallet_impact is not None:
        fill["walletImpact"] = wallet_impact
    payload = {
        "order": {"id": "order-1", "status": status, "ticker": ticker, "side": side,
                  "filledQuantity": qty, "createdAt": f"{day}T10:00:00Z",
                  "instrument": {"currency": currency, "name": ticker}},
        "fill": fill,
    }
    event = BrokerSyncEvent(
        workspace_id=run.workspace_id, portfolio_id=run.portfolio_id, run_id=run.id,
        broker="trading212", account_fingerprint=run.account_fingerprint,
        stream="orders", provider_event_id=event_id,
        # stage_events always records the parsed provider timestamp.
        provider_timestamp=datetime.fromisoformat(f"{day}T10:00:00+00:00"),
        raw_payload=payload,
    )
    db.add(event)
    db.commit()
    return event


def _add_csv_row(db, portfolio):
    """A row from the T212 CSV export that `t212_csv_covered_through` stands
    for; coverage without one is ignored (t212_sync.csv_coverage_is_stale). A
    different trade, so it never doubles as a fuzzy duplicate of an event."""
    db.add(make_txn(
        "MSFT", "buy", 1, 300.0, date=date(2024, 1, 2), source="t212_csv",
        portfolio_id=portfolio.id,
    ))


def _dividend_event(db, run, *, event_id="dividend:d1", ticker="KO", gross=0.485,
                     quantity=10, day="2024-03-15", currency="USD",
                     account_currency="USD", amount=None):
    payload = {
        "reference": event_id.split(":", 1)[1],
        "ticker": ticker,
        "grossAmountPerShare": gross,
        "quantity": quantity,
        "paidOn": f"{day}T00:00:00Z",
        "currency": account_currency,
        "instrument": {"currency": currency},
    }
    if amount is not None:
        payload["amount"] = amount
    event = BrokerSyncEvent(
        workspace_id=run.workspace_id, portfolio_id=run.portfolio_id, run_id=run.id,
        broker="trading212", account_fingerprint=run.account_fingerprint,
        stream="dividends", provider_event_id=event_id,
        provider_timestamp=datetime.fromisoformat(f"{day}T00:00:00+00:00"),
        raw_payload=payload,
    )
    db.add(event)
    db.commit()
    return event


class TestFinalizeRunGuards:
    def test_raises_on_non_finalizable_run(self, db_session, default_portfolio, connection):
        run = BrokerSyncRun(
            workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
            connection_id=connection.id, broker="trading212",
            credential_generation=connection.credential_generation,
            mode="incremental", state="fetching",
        )
        db_session.add(run)
        db_session.commit()
        with pytest.raises(ValueError):
            t212_sync.finalize_run(db_session, run, default_portfolio)

    def test_raises_on_stale_account_binding(
        self, db_session, default_portfolio, completed_run
    ):
        default_portfolio.t212_account_fingerprint = "different-account"
        db_session.commit()

        with pytest.raises(ValueError, match="account identity"):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)

    def test_raises_on_staged_event_from_another_account(
        self, db_session, default_portfolio, completed_run
    ):
        event = _order_event(db_session, completed_run)
        event.account_fingerprint = "different-account"
        db_session.commit()

        with pytest.raises(ValueError, match="staged event account identity"):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)


class TestFinalizeOrders:
    def test_imports_a_filled_trade(self, db_session, default_portfolio, completed_run):
        _order_event(db_session, completed_run)
        with patch("t212_sync.bulk_fetch_fx", return_value={("USD", date(2024, 6, 1)): 25.0}):
            result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.orders_imported == 1
        assert result.orders_skipped_duplicate == 0
        txn = db_session.query(Transaction).one()
        assert txn.ticker == "AAPL"
        assert txn.type == "buy"
        assert txn.shares == 10
        assert txn.price == 150.0
        assert txn.source == "t212_api"
        assert txn.source_event_id == "fill:f1"
        assert txn.source_event_stream == "orders"
        assert txn.source_account_fingerprint == completed_run.account_fingerprint
        assert txn.source_instrument_id == "AAPL_US_EQ"
        assert txn.executed_at is not None
        assert txn.cash_amount == pytest.approx(10 * 150.0 * 25.0, rel=1e-6)
        assert txn.cash_currency == "CZK"
        assert txn.fx_to_czk == 25.0

    def test_uses_exact_wallet_impact_settlement_when_present(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(
            db_session, completed_run,
            wallet_impact={"netValue": -1510.5, "currency": "USD"},
        )
        with patch("t212_sync.bulk_fetch_fx", return_value={("USD", date(2024, 6, 1)): 25.0}):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        txn = db_session.query(Transaction).one()
        # 1510.5 (exact settlement incl. fees), not the 1500.0 shares*price
        # approximation.
        assert txn.cash_amount == pytest.approx(1510.5 * 25.0, rel=1e-6)

    def test_trade_settlement_currency_can_differ_from_instrument_currency(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, currency="USD",
                     wallet_impact={"netValue": -38000.0, "currency": "CZK"})
        with patch("t212_sync.bulk_fetch_fx", return_value={("USD", date(2024, 6, 1)): 25.0}):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        txn = db_session.query(Transaction).one()
        assert txn.currency == "USD"
        assert txn.fx_to_czk == pytest.approx(25.0)
        assert txn.cash_amount == pytest.approx(38000.0)
        assert txn.cash_currency == "CZK"

    def test_corporate_action_fill_sends_run_to_needs_review_without_ledger_writes(
        self, db_session, default_portfolio, connection, completed_run
    ):
        _order_event(db_session, completed_run, event_id="fill:buy", day="2024-05-01")
        _order_event(
            db_session, completed_run, event_id="fill:split", day="2024-06-10",
            fill_type="STOCK_SPLIT",
        )
        _dividend_event(db_session, completed_run, amount=4.25)

        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        db_session.refresh(completed_run)
        db_session.refresh(connection)
        assert result.needs_review is True
        assert result.unsupported_action_types == ("STOCK_SPLIT",)
        assert result.orders_imported == 0
        assert result.dividends_imported == 0
        assert completed_run.state == "needs_review"
        assert completed_run.completed_at is None
        assert completed_run.last_error == t212_sync.HISTORY_SPLIT_UNVERIFIED_ERROR
        assert completed_run.lease_token is None
        assert completed_run.lease_expires_at is None
        assert connection.last_synced_at is None
        assert db_session.query(Transaction).count() == 0

    def test_needs_review_records_bounded_review_details(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, event_id="fill:a",
                     ticker="NVDA_US_EQ", day="2024-06-10", fill_type="STOCK_DISTRIBUTION")
        _order_event(db_session, completed_run, event_id="fill:b",
                     ticker="GE_US_EQ", day="2024-04-02", fill_type="SPIN_OFF")

        t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        db_session.refresh(completed_run)
        assert completed_run.review_details == [
            {"fill_type": "SPIN_OFF", "ticker": "GE", "date": "2024-04-02"},
            {"fill_type": "STOCK_DISTRIBUTION", "ticker": "NVDA", "date": "2024-06-10"},
        ]
        assert all(set(d) == {"fill_type", "ticker", "date"} for d in completed_run.review_details)

    @pytest.mark.parametrize("fill_type", [
        "STOCK_SPLIT", "STOCK_DISTRIBUTION", "FOP", "FOP_CORRECTION",
        "CUSTOM_STOCK_DISTRIBUTION", "EQUITY_RIGHTS", "SCRIP_STOCK_DIVIDENDS",
        "STOCK_DIVIDENDS", "STOCK_ACQUISITION", "CASH_AND_STOCK_ACQUISITION",
        "SPIN_OFF", "stock_split",
    ])
    def test_every_non_trade_fill_type_needs_review(
        self, db_session, default_portfolio, completed_run, fill_type
    ):
        _order_event(db_session, completed_run, fill_type=fill_type)

        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.needs_review is True
        assert result.unsupported_action_types == (fill_type.upper(),)
        assert completed_run.state == "needs_review"
        assert db_session.query(Transaction).count() == 0

    def test_unsupported_action_types_are_deduplicated_and_sorted(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, event_id="fill:a", fill_type="STOCK_DISTRIBUTION")
        _order_event(db_session, completed_run, event_id="fill:b", fill_type="SPIN_OFF")
        _order_event(db_session, completed_run, event_id="fill:c", fill_type="STOCK_DISTRIBUTION")

        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.unsupported_action_types == ("SPIN_OFF", "STOCK_DISTRIBUTION")

    def test_explicit_trade_fill_type_is_not_a_corporate_action(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, fill_type="TRADE")

        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.needs_review is False
        assert result.orders_imported == 1
        assert completed_run.state == "completed"

    def test_corporate_action_covered_by_csv_export_does_not_need_review(
        self, db_session, default_portfolio, connection, completed_run
    ):
        covered_through = datetime(2024, 6, 15, 12, 0, tzinfo=timezone.utc)
        default_portfolio.t212_csv_covered_through = covered_through
        connection.t212_csv_covered_through = covered_through
        _add_csv_row(db_session, default_portfolio)
        db_session.commit()
        _order_event(
            db_session, completed_run, event_id="fill:split", day="2024-06-10",
            fill_type="STOCK_SPLIT",
        )
        _order_event(db_session, completed_run, event_id="fill:new", day="2024-06-20")

        with patch("t212_sync.bulk_fetch_fx", return_value={("USD", date(2024, 6, 20)): 25.0}):
            result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.needs_review is False
        assert result.orders_imported == 1
        assert result.orders_skipped_duplicate == 1
        assert completed_run.state == "completed"
        assert {
            row.source_event_id for row in db_session.query(Transaction).all()
            if row.source == "t212_api"
        } == {"fill:new"}

    def test_corporate_action_after_csv_coverage_still_needs_review(
        self, db_session, default_portfolio, connection, completed_run
    ):
        covered_through = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        default_portfolio.t212_csv_covered_through = covered_through
        connection.t212_csv_covered_through = covered_through
        db_session.commit()
        _order_event(
            db_session, completed_run, event_id="fill:split", day="2024-06-10",
            fill_type="STOCK_SPLIT",
        )

        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.needs_review is True
        assert completed_run.state == "needs_review"

    def test_needs_review_run_cannot_be_finalized_again(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, fill_type="STOCK_SPLIT")
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        with pytest.raises(ValueError, match="needs_review"):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)

    def test_imports_fill_even_when_parent_order_was_cancelled(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, status="CANCELLED")
        with patch("t212_sync.bulk_fetch_fx", return_value={("USD", date(2024, 6, 1)): 25.0}):
            result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        assert result.orders_imported == 1
        assert db_session.query(Transaction).count() == 1

    def test_order_aggregate_without_fill_is_not_an_execution(
        self, db_session, default_portfolio, completed_run
    ):
        event = _order_event(db_session, completed_run)
        event.raw_payload = {**event.raw_payload, "fill": None}
        db_session.commit()

        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.orders_skipped_invalid == 1
        assert db_session.query(Transaction).count() == 0

    @pytest.mark.parametrize("value", [float("nan"), float("inf")])
    def test_invalid_fill_quantity_never_enters_ledger(
        self, db_session, default_portfolio, completed_run, value
    ):
        _order_event(db_session, completed_run, qty=value)

        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.orders_skipped_invalid == 1
        assert db_session.query(Transaction).count() == 0

    def test_two_distinct_fills_of_a_partial_order_both_import(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, event_id="fill:f1", qty=5,
                     day="2024-06-01", status="PARTIALLY_FILLED")
        _order_event(db_session, completed_run, event_id="fill:f2", qty=5,
                     day="2024-06-01", status="CANCELLED")
        with patch("t212_sync.bulk_fetch_fx", return_value={("USD", date(2024, 6, 1)): 25.0}):
            result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        assert result.orders_imported == 2
        assert {t.source_event_id for t in db_session.query(Transaction).all()} == {"fill:f1", "fill:f2"}

    def test_idempotent_reruns_import_nothing_new(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run)
        with patch("t212_sync.bulk_fetch_fx", return_value={("USD", date(2024, 6, 1)): 25.0}):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)
            second = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert second.orders_imported == 0
        assert second.orders_skipped_duplicate == 1
        assert db_session.query(Transaction).count() == 1

    def test_skips_rows_matching_existing_csv_history_by_key(
        self, db_session, default_portfolio, pid, completed_run
    ):
        db_session.add(make_txn("AAPL", "buy", 10, 150.0, date=date(2024, 6, 1),
                                source=None, portfolio_id=pid))
        db_session.commit()
        _order_event(db_session, completed_run)

        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.orders_skipped_duplicate == 1
        assert db_session.query(Transaction).count() == 1

    def test_one_csv_row_only_matches_one_of_two_identical_provider_fills(
        self, db_session, default_portfolio, pid, completed_run
    ):
        db_session.add(make_txn("AAPL", "buy", 5, 150.0, date=date(2024, 6, 1),
                                source="t212_csv", portfolio_id=pid))
        db_session.commit()
        _order_event(db_session, completed_run, event_id="fill:f1", qty=5)
        _order_event(db_session, completed_run, event_id="fill:f2", qty=5)

        with patch("t212_sync.bulk_fetch_fx", return_value={("USD", date(2024, 6, 1)): 25.0}):
            result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.orders_skipped_duplicate == 1
        assert result.orders_imported == 1
        assert db_session.query(Transaction).count() == 2

    def test_preserves_exact_native_settlement_when_fx_is_unavailable(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run,
                     wallet_impact={"netValue": -1510.5, "currency": "USD"})

        with patch("t212_sync.bulk_fetch_fx", return_value={}):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        txn = db_session.query(Transaction).one()
        assert txn.cash_amount == pytest.approx(1510.5)
        assert txn.cash_currency == "USD"
        assert txn.fx_to_czk is None


class TestFinalizeDividends:
    def test_uses_actual_paid_amount_when_present(
        self, db_session, default_portfolio, completed_run
    ):
        _dividend_event(db_session, completed_run, amount=4.25)
        with patch("t212_sync.bulk_fetch_fx", return_value={("USD", date(2024, 3, 15)): 25.0}):
            result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.dividends_imported == 1
        txn = db_session.query(Transaction).one()
        assert txn.type == "dividend"
        assert txn.shares == 10
        assert txn.price == 0.485
        assert txn.cash_amount == pytest.approx(4.25 * 25.0, rel=1e-6)

    def test_paid_amount_uses_account_currency_while_price_uses_instrument_currency(
        self, db_session, default_portfolio, completed_run
    ):
        _dividend_event(db_session, completed_run, gross=0.5, quantity=10,
                        currency="GBP", account_currency="CZK", amount=130.0)
        with patch("t212_sync.bulk_fetch_fx", return_value={("GBP", date(2024, 3, 15)): 30.0}):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        txn = db_session.query(Transaction).one()
        assert txn.currency == "GBP"
        assert txn.shares == 10
        assert txn.price == 0.5
        assert txn.cash_amount == pytest.approx(130.0)
        assert txn.cash_currency == "CZK"
        assert txn.fx_to_czk == pytest.approx(30.0)

    def test_missing_paid_amount_fails_closed_without_estimating_tax(
        self, db_session, default_portfolio, completed_run
    ):
        _dividend_event(db_session, completed_run, gross=0.485, quantity=10)
        with pytest.raises(ValueError, match="paid amount"):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        assert db_session.query(Transaction).count() == 0

    def test_missing_paid_amount_currency_fails_closed(
        self, db_session, default_portfolio, completed_run
    ):
        event = _dividend_event(db_session, completed_run, amount=4.25)
        event.raw_payload = {**event.raw_payload, "currency": None}
        db_session.commit()

        with pytest.raises(ValueError, match="currency"):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert db_session.query(Transaction).count() == 0

    def test_skips_duplicate_dividend_by_key(
        self, db_session, default_portfolio, pid, completed_run
    ):
        db_session.add(make_txn("CRM", "dividend", 0.4, 0.374, date=date(2024, 6, 1),
                                source=None, portfolio_id=pid))
        db_session.commit()
        _dividend_event(
            db_session, completed_run, ticker="CRM", gross=0.44, quantity=0.4,
            day="2024-06-01", amount=0.1496,
        )
        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        assert result.dividends_skipped_duplicate == 1
        assert db_session.query(Transaction).count() == 1

    def test_invalid_dividend_missing_quantity(self, db_session, default_portfolio, completed_run):
        _dividend_event(db_session, completed_run, quantity=0)
        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        assert result.dividends_skipped_invalid == 1


class TestFinalizeMixed:
    def test_finalization_error_commits_no_partial_ledger_rows(
        self, db_session, default_portfolio, connection, completed_run
    ):
        _order_event(db_session, completed_run)
        _dividend_event(db_session, completed_run, event_id="dividend:broken")

        with pytest.raises(ValueError, match="paid amount"):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert db_session.query(Transaction).count() == 0
        db_session.refresh(completed_run)
        db_session.refresh(connection)
        assert completed_run.state == "finalizing"
        assert completed_run.completed_at is None
        assert connection.last_synced_at is None

    def test_csv_coverage_excludes_older_api_events_globally(
        self, db_session, default_portfolio, connection, completed_run
    ):
        covered_through = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        default_portfolio.t212_csv_covered_through = covered_through
        connection.t212_csv_covered_through = covered_through
        _add_csv_row(db_session, default_portfolio)
        db_session.commit()
        _order_event(
            db_session, completed_run, event_id="fill:covered", day="2024-06-01",
        )
        _order_event(
            db_session, completed_run, event_id="fill:new", day="2024-06-02",
        )
        _dividend_event(
            db_session, completed_run, event_id="dividend:covered",
            day="2024-05-15", amount=4.25,
        )
        _dividend_event(
            db_session, completed_run, event_id="dividend:new",
            day="2024-06-03", amount=4.25,
        )

        with patch("t212_sync.bulk_fetch_fx", return_value={
            ("USD", date(2024, 6, 2)): 25.0,
            ("USD", date(2024, 6, 3)): 25.0,
        }):
            result = t212_sync.finalize_run(
                db_session, completed_run, default_portfolio,
            )

        assert result.orders_imported == 1
        assert result.orders_skipped_duplicate == 1
        assert result.dividends_imported == 1
        assert result.dividends_skipped_duplicate == 1
        assert {
            row.source_event_id for row in db_session.query(Transaction).all()
            if row.source == "t212_api"
        } == {"fill:new", "dividend:new"}

    def test_csv_coverage_without_csv_rows_is_ignored_and_forgotten(
        self, db_session, default_portfolio, connection, completed_run
    ):
        """Production, 2026-10-11: the portfolio still claimed T212 CSV coverage
        through 2026-08-31 although no CSV row was left in its ledger. The
        initial history import then dropped every older order, dividend and
        deposit as "covered by the CSV": 15 of 22 positions were missing and
        cash went negative. Coverage nothing backs must not hide history."""
        covered_through = datetime(2024, 6, 1, 12, 0, tzinfo=timezone.utc)
        default_portfolio.t212_csv_covered_through = covered_through
        connection.t212_csv_covered_through = covered_through
        db_session.commit()
        _order_event(db_session, completed_run, event_id="fill:old", day="2024-05-01")
        _order_event(db_session, completed_run, event_id="fill:new", day="2024-06-02")

        with patch("t212_sync.bulk_fetch_fx", return_value={
            ("USD", date(2024, 5, 1)): 25.0, ("USD", date(2024, 6, 2)): 25.0,
        }):
            result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.orders_imported == 2
        assert result.orders_skipped_duplicate == 0
        db_session.refresh(default_portfolio)
        db_session.refresh(connection)
        assert default_portfolio.t212_csv_covered_through is None
        assert connection.t212_csv_covered_through is None

    def test_orders_and_dividends_together(self, db_session, default_portfolio, completed_run):
        _order_event(db_session, completed_run)
        _dividend_event(db_session, completed_run, amount=4.25)
        with patch("t212_sync.bulk_fetch_fx", return_value={
            ("USD", date(2024, 6, 1)): 25.0, ("USD", date(2024, 3, 15)): 25.0,
        }):
            result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        assert result.orders_imported == 1
        assert result.dividends_imported == 1
        assert db_session.query(Transaction).count() == 2

    def test_payload_hash_and_mapper_version_recorded(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run)
        with patch("t212_sync.bulk_fetch_fx", return_value={("USD", date(2024, 6, 1)): 25.0}):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        txn = db_session.query(Transaction).one()
        assert txn.source_payload_hash
        assert txn.source_mapper_version == "t212_finalize_v2"


class TestFinalizeCoverage:
    """Plan 2026-09-24 Task C1: a completed run records per-stream history
    frontiers on the connection; runs that do not complete never do."""

    def test_completed_initial_run_sets_frontiers(
        self, db_session, default_portfolio, connection, completed_run
    ):
        completed_run.mode = "initial"
        _order_event(db_session, completed_run, event_id="fill:old", day="2024-01-01")
        _order_event(db_session, completed_run, event_id="fill:new", day="2024-06-01")
        _dividend_event(
            db_session, completed_run, event_id="dividend:d9", day="2024-03-15", amount=4.25,
        )

        t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        db_session.refresh(connection)
        assert connection.orders_frontier_event_id == "fill:new"
        assert connection.orders_frontier_at.date() == date(2024, 6, 1)
        assert connection.dividends_frontier_event_id == "dividend:d9"
        assert connection.dividends_frontier_at.date() == date(2024, 3, 15)
        assert connection.history_complete_at is not None
        assert connection.last_full_audit_at is None

    def test_frontier_tie_breaks_on_the_greater_event_id(
        self, db_session, default_portfolio, connection, completed_run
    ):
        completed_run.mode = "initial"
        _order_event(db_session, completed_run, event_id="fill:a", day="2024-06-01")
        _order_event(db_session, completed_run, event_id="fill:b", day="2024-06-01")

        t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        db_session.refresh(connection)
        assert connection.orders_frontier_event_id == "fill:b"

    def test_needs_review_run_sets_no_frontier(
        self, db_session, default_portfolio, connection, completed_run
    ):
        completed_run.mode = "initial"
        _order_event(db_session, completed_run, event_id="fill:x", fill_type="SPIN_OFF")

        t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        db_session.refresh(connection)
        assert connection.history_complete_at is None
        assert connection.orders_frontier_event_id is None
        assert connection.orders_frontier_at is None

    def test_audit_run_also_records_the_audit_time(
        self, db_session, default_portfolio, connection, completed_run
    ):
        completed_run.mode = "audit"
        _order_event(db_session, completed_run, event_id="fill:a", day="2024-06-01")

        t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        db_session.refresh(connection)
        assert connection.history_complete_at is not None
        assert connection.last_full_audit_at is not None

    def test_incremental_run_only_advances_a_frontier(
        self, db_session, default_portfolio, connection, completed_run
    ):
        connection.history_complete_at = datetime(2024, 7, 1, tzinfo=timezone.utc)
        connection.orders_frontier_at = datetime(2024, 8, 1, tzinfo=timezone.utc)
        connection.orders_frontier_event_id = "fill:keep"
        db_session.commit()
        completed_run.mode = "incremental"
        _order_event(db_session, completed_run, event_id="fill:older", day="2024-06-01")

        t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        db_session.refresh(connection)
        assert connection.orders_frontier_event_id == "fill:keep"
        assert connection.orders_frontier_at.date() == date(2024, 8, 1)
        assert connection.history_complete_at.date() == date(2024, 7, 1)

    def test_incremental_run_advances_to_a_newer_event(
        self, db_session, default_portfolio, connection, completed_run
    ):
        connection.orders_frontier_at = datetime(2024, 5, 1, tzinfo=timezone.utc)
        connection.orders_frontier_event_id = "fill:old"
        db_session.commit()
        completed_run.mode = "incremental"
        _order_event(db_session, completed_run, event_id="fill:newer", day="2024-06-01")

        t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        db_session.refresh(connection)
        assert connection.orders_frontier_event_id == "fill:newer"

    def test_retrying_a_completed_run_does_not_refresh_coverage(
        self, db_session, default_portfolio, connection, completed_run
    ):
        completed_run.mode = "audit"
        _order_event(db_session, completed_run, event_id="fill:a", day="2024-06-01")
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        db_session.refresh(connection)
        first_audit = connection.last_full_audit_at
        first_complete = connection.history_complete_at

        t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        db_session.refresh(connection)
        assert connection.last_full_audit_at == first_audit
        assert connection.history_complete_at == first_complete


def _next_run(db, template, mode):
    run = BrokerSyncRun(
        workspace_id=template.workspace_id, portfolio_id=template.portfolio_id,
        connection_id=template.connection_id, broker="trading212",
        account_fingerprint=template.account_fingerprint,
        credential_generation=template.credential_generation,
        mode=mode, state="finalizing", orders_complete=True, dividends_complete=True,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


_FX_JUNE_1 = {("USD", date(2024, 6, 1)): 25.0}


class TestFinalizeAudit:
    """Plan 2026-09-24 Task C3: an audit run revises API rows whose provider
    payload changed under an existing id, and imports late-inserted events."""

    def _import_first(self, db, portfolio, run, **event):
        _order_event(db, run, event_id="fill:f1", **event)
        with patch("t212_sync.bulk_fetch_fx", return_value=_FX_JUNE_1):
            t212_sync.finalize_run(db, run, portfolio)
        return db.query(Transaction).one()

    def test_audit_updates_row_whose_payload_changed(
        self, db_session, default_portfolio, completed_run
    ):
        row = self._import_first(db_session, default_portfolio, completed_run, qty=10, price=150.0)
        old_hash = row.source_payload_hash
        audit = _next_run(db_session, completed_run, "audit")
        _order_event(db_session, audit, event_id="fill:f1", qty=10, price=151.0)

        with patch("t212_sync.bulk_fetch_fx", return_value=_FX_JUNE_1):
            result = t212_sync.finalize_run(db_session, audit, default_portfolio)

        db_session.refresh(row)
        assert result.revised == 1
        assert result.orders_imported == 0
        assert row.price == 151.0
        assert row.source_payload_hash != old_hash
        assert db_session.query(Transaction).count() == 1

    def test_audit_revision_recomputes_fx_when_the_date_moves(
        self, db_session, default_portfolio, completed_run
    ):
        row = self._import_first(db_session, default_portfolio, completed_run)
        audit = _next_run(db_session, completed_run, "audit")
        _order_event(db_session, audit, event_id="fill:f1", day="2024-06-03")

        with patch("t212_sync.bulk_fetch_fx", return_value={("USD", date(2024, 6, 3)): 26.0}):
            t212_sync.finalize_run(db_session, audit, default_portfolio)

        db_session.refresh(row)
        assert row.date == date(2024, 6, 3)
        assert row.fx_to_czk == pytest.approx(26.0)

    def test_audit_leaves_an_unchanged_row_alone(
        self, db_session, default_portfolio, completed_run
    ):
        row = self._import_first(db_session, default_portfolio, completed_run)
        old_hash = row.source_payload_hash
        audit = _next_run(db_session, completed_run, "audit")
        _order_event(db_session, audit, event_id="fill:f1")

        with patch("t212_sync.bulk_fetch_fx", return_value=_FX_JUNE_1):
            result = t212_sync.finalize_run(db_session, audit, default_portfolio)

        db_session.refresh(row)
        assert result.revised == 0
        assert result.orders_skipped_duplicate == 1
        assert row.source_payload_hash == old_hash

    def test_incremental_run_never_revises_existing_rows(
        self, db_session, default_portfolio, completed_run
    ):
        row = self._import_first(db_session, default_portfolio, completed_run, price=150.0)
        later = _next_run(db_session, completed_run, "incremental")
        _order_event(db_session, later, event_id="fill:f1", price=151.0)

        with patch("t212_sync.bulk_fetch_fx", return_value=_FX_JUNE_1):
            result = t212_sync.finalize_run(db_session, later, default_portfolio)

        db_session.refresh(row)
        assert result.revised == 0
        assert result.orders_skipped_duplicate == 1
        assert row.price == 150.0

    def test_audit_revision_updates_the_paid_dividend_amount(
        self, db_session, default_portfolio, completed_run
    ):
        _dividend_event(db_session, completed_run, event_id="dividend:d1", amount=4.25)
        with patch("t212_sync.bulk_fetch_fx", return_value={("USD", date(2024, 3, 15)): 25.0}):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        row = db_session.query(Transaction).one()
        audit = _next_run(db_session, completed_run, "audit")
        _dividend_event(db_session, audit, event_id="dividend:d1", amount=4.5)

        with patch("t212_sync.bulk_fetch_fx", return_value={("USD", date(2024, 3, 15)): 25.0}):
            result = t212_sync.finalize_run(db_session, audit, default_portfolio)

        db_session.refresh(row)
        assert result.revised == 1
        assert result.dividends_imported == 0
        assert row.cash_amount == pytest.approx(4.5 * 25.0, rel=1e-6)
        assert db_session.query(Transaction).count() == 1

    def test_audit_imports_late_inserted_old_dividend(
        self, db_session, default_portfolio, completed_run
    ):
        completed_run.mode = "audit"
        _dividend_event(
            db_session, completed_run, event_id="dividend:div-old", day="2023-02-01",
            amount=2.0,
        )

        with patch("t212_sync.bulk_fetch_fx", return_value={("USD", date(2023, 2, 1)): 22.0}):
            result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.dividends_imported == 1
        assert result.revised == 0
        assert db_session.query(Transaction).one().source_event_id == "dividend:div-old"


def _stage_split(db, run, ticker="NVDA_US_EQ", day="2024-06-10", old=90, new=9, old_px=120, new_px=1200,
                 wallet_impact=None):
    _order_event(db, run, event_id=f"fill:sc-{day}", ticker=ticker, side="SELL",
                 qty=old, price=old_px, day=day, fill_type="STOCK_SPLIT", wallet_impact=wallet_impact)
    _order_event(db, run, event_id=f"fill:so-{day}", ticker=ticker, side="BUY",
                 qty=new, price=new_px, day=day, fill_type="STOCK_SPLIT", wallet_impact=wallet_impact)


class TestSplitFinalization:
    """Plan 2026-09-24 Task B3, against the G1 record (walletImpact ignored but
    equal on both legs, close = SELL, open = BUY)."""

    @pytest.fixture(autouse=True)
    def _no_fx_network(self):
        with patch("t212_sync.bulk_fetch_fx", return_value={}):
            yield

    def test_split_adjusts_prior_api_trade_once(self, db_session, default_portfolio, completed_run):
        _order_event(db_session, completed_run, event_id="fill:t1", ticker="NVDA_US_EQ",
                     qty=90, price=120, day="2024-05-01")
        _stage_split(db_session, completed_run)

        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.needs_review is False
        [buy] = db_session.query(Transaction).filter_by(ticker="NVDA").all()
        assert (buy.shares, buy.price) == (9, 1200)
        assert db_session.query(BrokerCorporateAction).one().representation == "api_normalized"
        assert db_session.query(BrokerCorporateActionApplication).count() == 1

        t212_sync.finalize_run(db_session, completed_run, default_portfolio)  # retry of completed run
        db_session.refresh(buy)
        assert (buy.shares, buy.price) == (9, 1200)
        assert db_session.query(BrokerCorporateActionApplication).count() == 1

    def test_forward_split_adjusts_prior_api_trade(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, event_id="fill:t1", ticker="NVDA_US_EQ",
                     qty=9, price=1200, day="2024-05-01")
        _stage_split(db_session, completed_run, old=9, new=90, old_px=1200, new_px=120)

        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.needs_review is False
        [buy] = db_session.query(Transaction).filter_by(ticker="NVDA").all()
        assert (buy.shares, buy.price) == (90, 120)
        assert db_session.query(BrokerCorporateActionApplication).count() == 1

    def test_forward_split_with_wrong_price_ratio_goes_to_needs_review(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, event_id="fill:t1", ticker="NVDA_US_EQ",
                     qty=9, price=1200, day="2024-05-01")
        _stage_split(db_session, completed_run, old=9, new=90, old_px=1200, new_px=200)

        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.needs_review is True
        assert completed_run.last_error == t212_sync.HISTORY_SPLIT_UNVERIFIED_ERROR
        assert db_session.query(Transaction).count() == 0
        assert db_session.query(BrokerCorporateAction).count() == 0

    def test_split_legs_never_become_transactions(self, db_session, default_portfolio, completed_run):
        _stage_split(db_session, completed_run)
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        assert db_session.query(Transaction).count() == 0

    def test_equal_wallet_impact_is_ignored_and_creates_no_cash_row(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, event_id="fill:t1", ticker="NVDA_US_EQ",
                     qty=90, price=120, day="2024-05-01")
        _stage_split(db_session, completed_run, wallet_impact={"currency": "CZK", "netValue": 646.4})

        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.needs_review is False
        assert [t.type for t in db_session.query(Transaction).all()] == ["buy"]

    def test_unequal_wallet_impact_goes_to_needs_review(self, db_session, default_portfolio, completed_run):
        _order_event(db_session, completed_run, event_id="fill:sc", ticker="NVDA_US_EQ", side="SELL",
                     qty=90, price=120, day="2024-06-10", fill_type="STOCK_SPLIT",
                     wallet_impact={"currency": "CZK", "netValue": 646.4})
        _order_event(db_session, completed_run, event_id="fill:so", ticker="NVDA_US_EQ", side="BUY",
                     qty=9, price=1200, day="2024-06-10", fill_type="STOCK_SPLIT",
                     wallet_impact={"currency": "CZK", "netValue": 10.0})

        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.needs_review is True
        assert db_session.query(Transaction).count() == 0
        assert db_session.query(BrokerCorporateAction).count() == 0

    def test_trade_after_split_is_not_adjusted(self, db_session, default_portfolio, completed_run):
        _order_event(db_session, completed_run, event_id="fill:t2", ticker="NVDA_US_EQ",
                     qty=5, price=125, day="2024-06-11")
        _stage_split(db_session, completed_run)
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        [buy] = db_session.query(Transaction).filter_by(ticker="NVDA").all()
        assert (buy.shares, buy.price) == (5, 125)
        assert db_session.query(BrokerCorporateActionApplication).count() == 0

    def test_split_adjusts_existing_t212_csv_trade(self, db_session, default_portfolio, completed_run):
        db_session.add(make_txn("NVDA", "buy", 90, 120, date=date(2024, 5, 1),
                                portfolio_id=default_portfolio.id, source="t212_csv"))
        db_session.commit()
        _stage_split(db_session, completed_run)
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        [buy] = db_session.query(Transaction).filter_by(ticker="NVDA", type="buy").all()
        assert (buy.shares, buy.price) == (9, 1200)

    def test_csv_split_rows_represent_action_and_nothing_is_adjusted(
        self, db_session, default_portfolio, completed_run
    ):
        for t in (
            make_txn("NVDA", "buy", 90, 120, date=date(2024, 5, 1), portfolio_id=default_portfolio.id, source="t212_csv"),
            make_txn("NVDA", "split_close", 90, 120, date=date(2024, 6, 10), portfolio_id=default_portfolio.id, source="t212_csv"),
            make_txn("NVDA", "split_open", 9, 1200, date=date(2024, 6, 10), portfolio_id=default_portfolio.id, source="t212_csv"),
        ):
            db_session.add(t)
        db_session.commit()
        _stage_split(db_session, completed_run)
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        [buy] = db_session.query(Transaction).filter_by(ticker="NVDA", type="buy").all()
        assert (buy.shares, buy.price) == (90, 120)
        assert db_session.query(BrokerCorporateAction).one().representation == "csv_rows"
        assert db_session.query(BrokerCorporateActionApplication).count() == 0

    def test_manual_trade_is_never_adjusted(self, db_session, default_portfolio, completed_run):
        db_session.add(make_txn("NVDA", "buy", 9, 1200, date=date(2024, 5, 1),
                                portfolio_id=default_portfolio.id, source="manual"))
        db_session.commit()
        _stage_split(db_session, completed_run)
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        [buy] = db_session.query(Transaction).filter_by(ticker="NVDA", type="buy").all()
        assert (buy.shares, buy.price) == (9, 1200)

    def test_unpaired_split_leg_goes_to_needs_review(self, db_session, default_portfolio, completed_run):
        _order_event(db_session, completed_run, event_id="fill:sc", ticker="NVDA_US_EQ", side="SELL",
                     qty=9, price=1200, day="2024-06-10", fill_type="STOCK_SPLIT")
        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        assert result.needs_review is True
        assert db_session.query(Transaction).count() == 0
        assert completed_run.review_details[0]["fill_type"] == "STOCK_SPLIT"

    def test_unverified_spin_off_still_needs_review_with_split_supported(
        self, db_session, default_portfolio, completed_run
    ):
        _stage_split(db_session, completed_run)
        _order_event(db_session, completed_run, event_id="fill:so1", ticker="GE_US_EQ",
                     day="2024-04-02", fill_type="SPIN_OFF")
        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        assert result.needs_review is True
        assert completed_run.last_error == t212_sync.HISTORY_SPIN_OFF_UNVERIFIED_ERROR
        assert [d["fill_type"] for d in completed_run.review_details] == ["SPIN_OFF"]
        assert db_session.query(BrokerCorporateAction).count() == 0


# Observed encoding (owner's account, Mobility Global, 2026-07-02): one BUY
# leg of the new shares at price 0 with a zero walletImpact.
_SPIN_OFF_WALLET = {"currency": "CZK", "netValue": 0, "fxRate": 1, "taxes": []}


class TestSpinOffFinalization:
    @pytest.fixture(autouse=True)
    def _no_fx_network(self):
        with patch("t212_sync.bulk_fetch_fx", return_value={}):
            yield

    def test_observed_spin_off_imports_as_zero_cost_buy(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, event_id="fill:t1", day="2026-06-01")
        _order_event(db_session, completed_run, event_id="fill:so", ticker="MBGL_US_EQ",
                     qty=1.0, price=0, day="2026-07-02", fill_type="SPIN_OFF",
                     wallet_impact=_SPIN_OFF_WALLET)

        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.needs_review is False
        assert result.orders_imported == 2
        assert completed_run.state == "completed"
        spin = db_session.query(Transaction).filter_by(source_event_id="fill:so").one()
        assert (spin.ticker, spin.type, spin.shares, spin.price) == ("MBGL", "buy", 1.0, 0.0)
        assert spin.source_fill_type == "SPIN_OFF"
        assert spin.notes == "T212 Spin-off"
        assert not spin.cash_amount

    def test_spin_off_is_idempotent(self, db_session, default_portfolio, completed_run):
        _order_event(db_session, completed_run, event_id="fill:so", ticker="MBGL_US_EQ",
                     qty=1.0, price=0, day="2026-07-02", fill_type="SPIN_OFF",
                     wallet_impact=_SPIN_OFF_WALLET)
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        again = t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        assert again.orders_imported == 0
        assert db_session.query(Transaction).count() == 1

    @pytest.mark.parametrize("overrides", [
        {"side": "SELL", "qty": -1.0},
        {"price": 12.5},
        {"wallet_impact": {"currency": "CZK", "netValue": 250.0}},
        {"wallet_impact": None},
        {"qty": 0},
    ])
    def test_spin_off_outside_observed_encoding_needs_review(
        self, db_session, default_portfolio, connection, completed_run, overrides
    ):
        kwargs = {"ticker": "MBGL_US_EQ", "qty": 1.0, "price": 0, "day": "2026-07-02",
                  "fill_type": "SPIN_OFF", "wallet_impact": _SPIN_OFF_WALLET, **overrides}
        _order_event(db_session, completed_run, event_id="fill:so", **kwargs)

        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.needs_review is True
        assert completed_run.last_error == t212_sync.HISTORY_SPIN_OFF_UNVERIFIED_ERROR
        assert db_session.query(Transaction).count() == 0
        resolution = t212_sync.review_resolution(completed_run, connection, default_portfolio)
        assert resolution["mapper_supports_all"] is False

    def test_spin_off_with_unsupported_action_keeps_generic_error(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, event_id="fill:so", ticker="MBGL_US_EQ",
                     qty=1.0, price=0, day="2026-07-02", fill_type="SPIN_OFF",
                     wallet_impact=_SPIN_OFF_WALLET)
        _order_event(db_session, completed_run, event_id="fill:sd", fill_type="STOCK_DISTRIBUTION")

        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.unsupported_action_types == ("STOCK_DISTRIBUTION",)
        assert completed_run.last_error == t212_sync.HISTORY_NEEDS_REVIEW_ERROR
        assert db_session.query(Transaction).count() == 0

    def test_late_pre_split_fill_in_later_run_gets_adjusted(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, event_id="fill:t1", ticker="NVDA_US_EQ",
                     qty=90, price=120, day="2024-05-01")
        _stage_split(db_session, completed_run)
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        later = _next_run(db_session, completed_run, "audit")
        _stage_split(db_session, later)
        _order_event(db_session, later, event_id="fill:t0", ticker="NVDA_US_EQ",
                     qty=30, price=110, day="2024-04-01")
        t212_sync.finalize_run(db_session, later, default_portfolio)

        rows = {t.source_event_id: (t.shares, t.price) for t in db_session.query(Transaction).all()}
        assert rows == {"fill:t1": (9, 1200), "fill:t0": (3, 1100)}
        assert db_session.query(BrokerCorporateAction).count() == 1
        assert db_session.query(BrokerCorporateActionApplication).count() == 2

    def test_audit_revision_keeps_recorded_split_adjustment(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, event_id="fill:t1", ticker="NVDA_US_EQ",
                     qty=90, price=120, day="2024-05-01")
        _stage_split(db_session, completed_run)
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        [buy] = db_session.query(Transaction).filter_by(ticker="NVDA").all()

        audit = _next_run(db_session, completed_run, "audit")
        _order_event(db_session, audit, event_id="fill:t1", ticker="NVDA_US_EQ",
                     qty=90, price=121, day="2024-05-01")  # provider corrected the price
        _stage_split(db_session, audit)
        result = t212_sync.finalize_run(db_session, audit, default_portfolio)

        db_session.refresh(buy)
        assert result.revised == 1
        assert buy.shares == pytest.approx(9)
        assert buy.price == pytest.approx(1210)  # 121 / (1/10), not the raw 121
        [application] = db_session.query(BrokerCorporateActionApplication).all()
        assert (application.shares_after, application.price_after) == (pytest.approx(9), pytest.approx(1210))

    def test_changed_ratio_for_recorded_split_goes_to_needs_review_without_reapplying(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, event_id="fill:t1", ticker="NVDA_US_EQ",
                     qty=90, price=120, day="2024-05-01")
        _stage_split(db_session, completed_run, old=90, new=9, old_px=120, new_px=1200)
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        [buy] = db_session.query(Transaction).filter_by(ticker="NVDA").all()
        assert (buy.shares, buy.price) == (9, 1200)

        audit = _next_run(db_session, completed_run, "audit")
        _stage_split(db_session, audit, old=90, new=3, old_px=120, new_px=3600)

        result = t212_sync.finalize_run(db_session, audit, default_portfolio)

        db_session.refresh(buy)
        assert result.needs_review is True
        assert audit.state == "needs_review"
        assert (buy.shares, buy.price) == (9, 1200)
        [action] = db_session.query(BrokerCorporateAction).all()
        assert (action.ratio_numerator, action.ratio_denominator) == (1, 10)
        assert db_session.query(BrokerCorporateActionApplication).count() == 1

    def test_changed_effective_time_for_recorded_split_goes_to_needs_review_without_compounding(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, event_id="fill:t1", ticker="NVDA_US_EQ",
                     qty=90, price=120, day="2024-05-01")
        _stage_split(db_session, completed_run, old=90, new=9, old_px=120, new_px=1200)
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        [buy] = db_session.query(Transaction).filter_by(ticker="NVDA").all()
        assert (buy.shares, buy.price) == (9, 1200)

        audit = _next_run(db_session, completed_run, "audit")
        _order_event(db_session, audit, event_id="fill:sc-2024-06-10", ticker="NVDA_US_EQ",
                     side="SELL", qty=90, price=120, day="2024-06-11", fill_type="STOCK_SPLIT")
        _order_event(db_session, audit, event_id="fill:so-2024-06-10", ticker="NVDA_US_EQ",
                     side="BUY", qty=9, price=1200, day="2024-06-11", fill_type="STOCK_SPLIT")

        result = t212_sync.finalize_run(db_session, audit, default_portfolio)

        db_session.refresh(buy)
        assert result.needs_review is True
        assert audit.state == "needs_review"
        assert (buy.shares, buy.price) == (9, 1200)
        assert db_session.query(BrokerCorporateAction).count() == 1
        assert db_session.query(BrokerCorporateActionApplication).count() == 1

    def test_orphan_leg_of_an_already_recorded_split_is_ignored(
        self, db_session, default_portfolio, completed_run
    ):
        # An incremental overlap window can re-stage only one leg of a split that
        # an earlier run already recorded. That must not block the connection.
        _order_event(db_session, completed_run, event_id="fill:t1", ticker="NVDA_US_EQ",
                     qty=90, price=120, day="2024-05-01")
        _stage_split(db_session, completed_run)
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        later = _next_run(db_session, completed_run, "incremental")
        _order_event(db_session, later, event_id="fill:so-2024-06-10", ticker="NVDA_US_EQ", side="BUY",
                     qty=9, price=1200, day="2024-06-10", fill_type="STOCK_SPLIT")
        result = t212_sync.finalize_run(db_session, later, default_portfolio)

        db_session.refresh(later)
        assert result.needs_review is False
        assert later.state == "completed"
        assert db_session.query(BrokerCorporateActionApplication).count() == 1

    def test_orphan_leg_of_an_unknown_split_still_needs_review(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, event_id="fill:so-2024-06-10", ticker="NVDA_US_EQ", side="BUY",
                     qty=90, price=120, day="2024-06-10", fill_type="STOCK_SPLIT")
        assert t212_sync.finalize_run(db_session, completed_run, default_portfolio).needs_review is True

    def test_audit_revision_that_moves_a_row_past_the_split_drops_the_adjustment(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, event_id="fill:t1", ticker="NVDA_US_EQ",
                     qty=90, price=120, day="2024-05-01")
        _stage_split(db_session, completed_run)
        t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        [buy] = db_session.query(Transaction).filter_by(ticker="NVDA").all()
        assert (buy.shares, buy.price) == (9, 1200)

        audit = _next_run(db_session, completed_run, "audit")
        _order_event(db_session, audit, event_id="fill:t1", ticker="NVDA_US_EQ",
                     qty=90, price=125, day="2024-06-12")  # provider moved the fill after the split
        _stage_split(db_session, audit)
        t212_sync.finalize_run(db_session, audit, default_portfolio)

        db_session.refresh(buy)
        assert (buy.shares, buy.price) == (90, 125)
        assert db_session.query(BrokerCorporateActionApplication).count() == 0


# ---------------------------------------------------------------------------
# Cash-transaction stream (plan 2026-10-03, Task D4)
# ---------------------------------------------------------------------------


def _cash_event(db, run, *, reference="c1", kind="DEPOSIT", amount=3200.0,
                currency="CZK", when="2026-03-01T10:00:00.000Z"):
    payload = {"type": kind, "amount": amount, "currency": currency,
               "reference": reference, "dateTime": when}
    event = BrokerSyncEvent(
        workspace_id=run.workspace_id, portfolio_id=run.portfolio_id, run_id=run.id,
        broker="trading212", account_fingerprint=run.account_fingerprint,
        stream="cash", provider_event_id=f"cash:{reference}",
        provider_timestamp=datetime.fromisoformat(when.replace("Z", "+00:00")),
        raw_payload=payload,
    )
    db.add(event)
    db.commit()
    return event


def _cash_rows(db):
    return db.query(Transaction).filter(Transaction.source_event_stream == "cash").all()


class TestFinalizeCash:
    def test_imports_a_deposit_as_a_ledger_cash_row(
        self, db_session, default_portfolio, completed_run, connection
    ):
        _cash_event(db_session, completed_run)
        with patch("t212_sync.bulk_fetch_fx", return_value={}):
            result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.cash_imported == 1
        [row] = _cash_rows(db_session)
        assert (row.type, row.amount, row.currency) == ("deposit", 3200.0, "CZK")
        assert row.ticker is None and row.shares == 0 and row.price == 0
        assert row.source == "t212_api"
        assert row.source_event_id == "cash:c1"
        assert row.source_account_fingerprint == completed_run.account_fingerprint
        assert row.date == date(2026, 3, 1)
        assert row.executed_at is not None
        assert row.fx_to_czk == 1.0
        assert row.cash_amount is None
        assert "DEPOSIT" in row.notes
        db_session.refresh(connection)
        assert connection.cash_frontier_event_id == "cash:c1"

    def test_every_proven_type_maps_to_the_right_ledger_type(
        self, db_session, default_portfolio, completed_run
    ):
        cases = [
            ("w", "WITHDRAW", -218.8, "withdrawal"),
            ("f", "FEE", -0.16, "fee"),
            ("i1", "INTEREST_ON_FREE_CASH", 0.42, "interest"),
            ("i2", "LENDING_INTEREST", 0.01, "interest"),
            ("t1", "TRANSFER", 200.0, "deposit"),
            ("t2", "TRANSFER", -200.0, "withdrawal"),
        ]
        for ref, kind, amount, _ in cases:
            _cash_event(db_session, completed_run, reference=ref, kind=kind, amount=amount)
        with patch("t212_sync.bulk_fetch_fx", return_value={}):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        by_ref = {r.source_event_id: r for r in _cash_rows(db_session)}
        for ref, _, amount, expected in cases:
            assert by_ref[f"cash:{ref}"].type == expected
            assert by_ref[f"cash:{ref}"].amount == abs(amount)

    def test_a_foreign_currency_row_gets_the_historical_rate(
        self, db_session, default_portfolio, completed_run
    ):
        _cash_event(db_session, completed_run, currency="EUR", amount=100.0)
        with patch("t212_sync.bulk_fetch_fx", return_value={("EUR", date(2026, 3, 1)): 25.1}):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        [row] = _cash_rows(db_session)
        assert (row.currency, row.fx_to_czk, row.cash_amount) == ("EUR", 25.1, None)

    def test_finalizing_again_imports_nothing_new(
        self, db_session, default_portfolio, completed_run
    ):
        _cash_event(db_session, completed_run)
        with patch("t212_sync.bulk_fetch_fx", return_value={}):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)
            again = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert again.cash_imported == 0
        assert again.cash_skipped_duplicate == 1
        assert len(_cash_rows(db_session)) == 1

    def test_rewalking_cash_history_in_a_new_run_imports_nothing_twice(
        self, db_session, default_portfolio, completed_run
    ):
        _cash_event(db_session, completed_run)
        with patch("t212_sync.bulk_fetch_fx", return_value={}):
            first = t212_sync.finalize_run(db_session, completed_run, default_portfolio)
            rewalk = _next_run(db_session, completed_run, "audit")
            _cash_event(db_session, rewalk)  # the same reference, staged again
            second = t212_sync.finalize_run(db_session, rewalk, default_portfolio)

        assert first.cash_imported == 1
        assert second.cash_imported == 0
        assert second.cash_skipped_duplicate == 1
        assert len(_cash_rows(db_session)) == 1

    def test_a_zero_amount_fee_is_skipped_without_blocking_the_run(
        self, db_session, default_portfolio, completed_run
    ):
        # Production 2026-11-03: FEE 0 EUR next to the real fee of a trade.
        _cash_event(db_session, completed_run, reference="real", kind="FEE", amount=-0.03)
        _cash_event(db_session, completed_run, reference="zero", kind="FEE", amount=0)
        with patch("t212_sync.bulk_fetch_fx", return_value={}):
            result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.needs_review is False
        assert [r.source_event_id for r in _cash_rows(db_session)] == ["cash:real"]

    def test_an_unmapped_type_sends_the_run_to_review_before_any_write(
        self, db_session, default_portfolio, completed_run, connection
    ):
        _order_event(db_session, completed_run)
        _cash_event(db_session, completed_run, reference="ok")
        _cash_event(db_session, completed_run, reference="odd", kind="MYSTERY", amount=5.0)
        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.needs_review is True
        assert db_session.query(Transaction).count() == 0
        db_session.refresh(completed_run)
        db_session.refresh(connection)
        assert completed_run.state == "needs_review"
        assert completed_run.last_error == t212_sync.HISTORY_CASH_UNSUPPORTED_ERROR
        assert completed_run.review_details == [
            {"fill_type": None, "ticker": None, "date": "2026-03-01", "cash_type": "MYSTERY"}
        ]
        assert connection.history_complete_at is None

    def test_a_blocked_run_logs_what_blocked_it_without_amounts(
        self, db_session, default_portfolio, completed_run, caplog
    ):
        _cash_event(db_session, completed_run, reference="odd", kind="MYSTERY", amount=12.34)
        _cash_event(db_session, completed_run, reference="bad", kind="FEE", amount=7.5,
                    currency="EUR", when="2026-03-02T10:00:00.000Z")
        with caplog.at_level(logging.WARNING, logger="portfyl.t212_sync"):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        [line] = [r.getMessage() for r in caplog.records
                  if r.getMessage().startswith("T212 history needs review")]
        assert f"run={completed_run.public_id}" in line
        assert f"portfolio={default_portfolio.public_id}" in line
        assert "cash MYSTERY 2026-03-01 CZK sign=+ (unmapped cash transaction type)" in line
        assert "cash FEE 2026-03-02 EUR sign=+ (sign contradicts the proven direction)" in line
        # Amounts are user financial data and never needed to diagnose the type.
        assert "12.34" not in line and "7.5" not in line

    def test_events_covered_by_the_csv_export_are_not_imported(
        self, db_session, default_portfolio, completed_run
    ):
        default_portfolio.t212_csv_covered_through = datetime(2026, 3, 2, tzinfo=timezone.utc)
        _add_csv_row(db_session, default_portfolio)
        _cash_event(db_session, completed_run, reference="old", when="2026-03-01T10:00:00.000Z")
        _cash_event(db_session, completed_run, reference="new", when="2026-03-05T10:00:00.000Z")
        with patch("t212_sync.bulk_fetch_fx", return_value={}):
            result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert [r.source_event_id for r in _cash_rows(db_session)] == ["cash:new"]
        assert result.cash_skipped_duplicate == 1

    def test_a_manual_row_for_the_same_cash_event_is_matched_once(
        self, db_session, default_portfolio, completed_run
    ):
        db_session.add(Transaction(
            workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
            ticker=None, type="deposit", shares=0.0, price=0.0, amount=3200.0,
            currency="CZK", date=date(2026, 3, 1), source="manual",
        ))
        db_session.commit()
        _cash_event(db_session, completed_run, reference="a")
        _cash_event(db_session, completed_run, reference="b")  # a second identical deposit
        with patch("t212_sync.bulk_fetch_fx", return_value={}):
            result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        assert result.cash_skipped_duplicate == 1
        assert result.cash_imported == 1
        assert len(_cash_rows(db_session)) == 1

    def test_an_audit_revises_a_cash_row_whose_payload_changed(
        self, db_session, default_portfolio, completed_run
    ):
        _cash_event(db_session, completed_run, amount=100.0)
        with patch("t212_sync.bulk_fetch_fx", return_value={}):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)
            audit = _next_run(db_session, completed_run, "audit")
            _cash_event(db_session, audit, amount=150.0)
            result = t212_sync.finalize_run(db_session, audit, default_portfolio)

        [row] = _cash_rows(db_session)
        assert row.amount == 150.0
        assert result.revised == 1
