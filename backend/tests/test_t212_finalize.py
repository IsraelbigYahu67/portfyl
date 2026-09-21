"""Tests for t212_sync.finalize_run (T212 snapshot-first sync plan, Task 4
scoped slice). Not wired into any automatic path -- these call it directly.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import patch

import pytest

import t212_sync
from models import BrokerConnection, BrokerSyncEvent, BrokerSyncRun, Transaction
from tests.helpers import make_txn


@pytest.fixture
def connection(db_session, default_portfolio):
    conn = BrokerConnection(
        workspace_id=default_portfolio.workspace_id, portfolio_id=default_portfolio.id,
        broker="trading212", api_key="k" * 20,
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
        credential_generation=connection.credential_generation,
        mode="incremental",
        state="completed",
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
        broker="trading212", stream="orders", provider_event_id=event_id,
        raw_payload=payload,
    )
    db.add(event)
    db.commit()
    return event


def _dividend_event(db, run, *, event_id="dividend:d1", ticker="KO", gross=0.485,
                     quantity=10, day="2024-03-15", currency="USD", amount=None):
    payload = {
        "reference": event_id.split(":", 1)[1],
        "ticker": ticker,
        "grossAmountPerShare": gross,
        "quantity": quantity,
        "paidOn": f"{day}T00:00:00Z",
        "instrument": {"currency": currency},
    }
    if amount is not None:
        payload["amount"] = amount
    event = BrokerSyncEvent(
        workspace_id=run.workspace_id, portfolio_id=run.portfolio_id, run_id=run.id,
        broker="trading212", stream="dividends", provider_event_id=event_id,
        raw_payload=payload,
    )
    db.add(event)
    db.commit()
    return event


class TestFinalizeRunGuards:
    def test_raises_on_non_completed_run(self, db_session, default_portfolio, connection):
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

    def test_skips_non_trade_fill_types(self, db_session, default_portfolio, completed_run):
        _order_event(db_session, completed_run, fill_type="STOCK_SPLIT")
        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        assert result.orders_skipped_non_trade == 1
        assert result.orders_imported == 0
        assert db_session.query(Transaction).count() == 0

    def test_skips_unfilled_orders(self, db_session, default_portfolio, completed_run):
        _order_event(db_session, completed_run, status="CANCELLED")
        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        assert result.orders_skipped_invalid == 1
        assert result.orders_imported == 0

    def test_two_distinct_fills_of_a_partial_order_both_import(
        self, db_session, default_portfolio, completed_run
    ):
        _order_event(db_session, completed_run, event_id="fill:f1", qty=5, day="2024-06-01")
        _order_event(db_session, completed_run, event_id="fill:f2", qty=5, day="2024-06-02")
        with patch("t212_sync.bulk_fetch_fx", return_value={
            ("USD", date(2024, 6, 1)): 25.0, ("USD", date(2024, 6, 2)): 25.0,
        }):
            result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        assert result.orders_imported == 2

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
        assert txn.price == 4.25
        assert txn.cash_amount == pytest.approx(4.25 * 25.0, rel=1e-6)

    def test_falls_back_to_85_percent_when_amount_absent(
        self, db_session, default_portfolio, completed_run
    ):
        _dividend_event(db_session, completed_run, gross=0.485, quantity=10)
        with patch("t212_sync.bulk_fetch_fx", return_value={("USD", date(2024, 3, 15)): 25.0}):
            t212_sync.finalize_run(db_session, completed_run, default_portfolio)

        txn = db_session.query(Transaction).one()
        assert txn.price == pytest.approx(round(0.485 * 10 * 0.85, 6))

    def test_skips_duplicate_dividend_by_key(
        self, db_session, default_portfolio, pid, completed_run
    ):
        db_session.add(make_txn("CRM", "dividend", 0.4, 0.374, date=date(2024, 6, 1),
                                source=None, portfolio_id=pid))
        db_session.commit()
        _dividend_event(
            db_session, completed_run, ticker="CRM", gross=0.44, quantity=0.4,
            day="2024-06-01",
        )
        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        assert result.dividends_skipped_duplicate == 1
        assert db_session.query(Transaction).count() == 1

    def test_invalid_dividend_missing_quantity(self, db_session, default_portfolio, completed_run):
        _dividend_event(db_session, completed_run, quantity=0)
        result = t212_sync.finalize_run(db_session, completed_run, default_portfolio)
        assert result.dividends_skipped_invalid == 1


class TestFinalizeMixed:
    def test_orders_and_dividends_together(self, db_session, default_portfolio, completed_run):
        _order_event(db_session, completed_run)
        _dividend_event(db_session, completed_run)
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
        assert txn.source_mapper_version == "t212_finalize_v1"
