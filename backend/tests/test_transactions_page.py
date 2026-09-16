"""Tests for the paged portfolio-transactions endpoint."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from routers.portfolio import get_transactions_page
from tests.helpers import make_txn


def _seed(db_session, pid, n=5):
    transactions = [
        make_txn(
            "AAPL",
            "buy",
            10,
            150.0,
            date=date(2024, 1, day),
            portfolio_id=pid,
            notes="first buy" if day == 1 else None,
        )
        for day in range(1, n + 1)
    ]
    db_session.add_all(transactions)
    db_session.commit()
    return transactions


class TestTransactionsPage:
    def test_default_page_returns_50_or_fewer_newest_first(
        self, db_session, pid, default_portfolio
    ):
        _seed(db_session, pid, n=5)

        result = get_transactions_page(db=db_session, portfolio=default_portfolio)

        assert result["total"] == 5
        assert result["offset"] == 0
        assert result["limit"] == 50
        dates = [item.date for item in result["items"]]
        assert dates == sorted(dates, reverse=True)

    def test_offset_and_limit_slice_correctly(self, db_session, pid, default_portfolio):
        _seed(db_session, pid, n=30)

        result = get_transactions_page(
            offset=25, limit=25, db=db_session, portfolio=default_portfolio
        )

        assert result["total"] == 30
        assert result["offset"] == 25
        assert result["limit"] == 25
        assert len(result["items"]) == 5

    def test_limit_100_is_accepted(self, db_session, pid, default_portfolio):
        _seed(db_session, pid, n=30)

        result = get_transactions_page(
            limit=100, db=db_session, portfolio=default_portfolio
        )

        assert result["limit"] == 100
        assert len(result["items"]) == 30

    @pytest.mark.parametrize("limit", [10, 30, 49, 51, 200])
    def test_invalid_limit_rejected(self, db_session, default_portfolio, limit):
        with pytest.raises(HTTPException) as exc:
            get_transactions_page(
                limit=limit, db=db_session, portfolio=default_portfolio
            )
        assert exc.value.status_code == 422

    def test_negative_offset_rejected(self, db_session, default_portfolio):
        with pytest.raises(HTTPException) as exc:
            get_transactions_page(
                offset=-1, db=db_session, portfolio=default_portfolio
            )
        assert exc.value.status_code == 422

    def test_q_matches_ticker_case_insensitively(
        self, db_session, pid, default_portfolio
    ):
        _seed(db_session, pid, n=2)
        db_session.add(
            make_txn(
                "MSFT", "buy", 5, 300.0, date=date(2024, 2, 1), portfolio_id=pid
            )
        )
        db_session.commit()

        result = get_transactions_page(
            q="aapl", db=db_session, portfolio=default_portfolio
        )

        assert result["total"] == 2
        assert all(item.ticker == "AAPL" for item in result["items"])

    def test_q_matches_notes(self, db_session, pid, default_portfolio):
        _seed(db_session, pid, n=3)

        result = get_transactions_page(
            q="first buy", db=db_session, portfolio=default_portfolio
        )

        assert result["total"] == 1
        assert result["items"][0].notes == "first buy"

    def test_type_filter(self, db_session, pid, default_portfolio):
        _seed(db_session, pid, n=2)
        db_session.add(
            make_txn(
                "AAPL", "sell", 3, 175.0, date=date(2024, 3, 1), portfolio_id=pid
            )
        )
        db_session.commit()

        result = get_transactions_page(
            type="sell", db=db_session, portfolio=default_portfolio
        )

        assert result["total"] == 1
        assert result["items"][0].type == "sell"

    def test_sort_ticker_ascending(self, db_session, pid, default_portfolio):
        db_session.add_all(
            [
                make_txn(
                    "MSFT", "buy", 1, 1.0, date=date(2024, 1, 1), portfolio_id=pid
                ),
                make_txn(
                    "AAPL", "buy", 1, 1.0, date=date(2024, 1, 1), portfolio_id=pid
                ),
            ]
        )
        db_session.commit()

        result = get_transactions_page(
            sort="ticker", db=db_session, portfolio=default_portfolio
        )

        assert [item.ticker for item in result["items"]] == ["AAPL", "MSFT"]

    def test_sort_uses_id_as_deterministic_secondary_key(
        self, db_session, pid, default_portfolio
    ):
        db_session.add_all(
            [
                make_txn(
                    "AAPL", "buy", 1, 1.0, date=date(2024, 1, 1), portfolio_id=pid
                ),
                make_txn(
                    "MSFT", "buy", 1, 1.0, date=date(2024, 1, 1), portfolio_id=pid
                ),
            ]
        )
        db_session.commit()

        first = get_transactions_page(db=db_session, portfolio=default_portfolio)
        second = get_transactions_page(db=db_session, portfolio=default_portfolio)

        assert [item.id for item in first["items"]] == [
            item.id for item in second["items"]
        ]

    def test_invalid_sort_rejected(self, db_session, default_portfolio):
        with pytest.raises(HTTPException) as exc:
            get_transactions_page(
                sort="bogus", db=db_session, portfolio=default_portfolio
            )
        assert exc.value.status_code == 422

    def test_cash_rows_excluded_like_the_unpaged_endpoint(
        self, db_session, pid, default_portfolio
    ):
        _seed(db_session, pid, n=1)
        db_session.add(
            make_txn(
                None,
                "deposit",
                0,
                0,
                date=date(2024, 1, 1),
                portfolio_id=pid,
                amount=1000.0,
            )
        )
        db_session.commit()

        result = get_transactions_page(db=db_session, portfolio=default_portfolio)

        assert result["total"] == 1

    def test_scoped_to_portfolio(
        self, db_session, pid, default_portfolio, test_workspace
    ):
        from models import Portfolio

        _seed(db_session, pid, n=3)
        other = Portfolio(workspace_id=test_workspace.id, name="Other")
        db_session.add(other)
        db_session.commit()
        db_session.add(
            make_txn(
                "TSLA",
                "buy",
                1,
                1.0,
                date=date(2024, 1, 1),
                portfolio_id=other.id,
            )
        )
        db_session.commit()

        result = get_transactions_page(db=db_session, portfolio=default_portfolio)

        assert result["total"] == 3

    def test_exact_ticker_filter_is_normalized_and_returns_latest(self, db_session, pid, default_portfolio):
        db_session.add_all(
            [
                make_txn("AAPL", "buy", 1, 100.0, date=date(2024, 1, 1), portfolio_id=pid),
                make_txn("AAPL", "sell", 2, 200.0, date=date(2024, 2, 1), portfolio_id=pid),
                make_txn("AAPLX", "buy", 3, 300.0, date=date(2024, 3, 1), portfolio_id=pid),
            ]
        )
        db_session.commit()

        result = get_transactions_page(
            ticker="  aapl ", sort="-date", limit=1, db=db_session, portfolio=default_portfolio
        )

        assert result["total"] == 2
        assert len(result["items"]) == 1
        assert result["items"][0].ticker == "AAPL"
        assert result["items"][0].type == "sell"

    def test_ticker_combines_with_q_and_type(self, db_session, pid, default_portfolio):
        db_session.add_all(
            [
                make_txn("AAPL", "buy", 1, 100.0, date=date(2024, 1, 1), portfolio_id=pid, notes="starter"),
                make_txn("AAPL", "sell", 1, 110.0, date=date(2024, 2, 1), portfolio_id=pid, notes="trim"),
                make_txn("MSFT", "buy", 1, 300.0, date=date(2024, 2, 1), portfolio_id=pid, notes="starter"),
            ]
        )
        db_session.commit()

        result = get_transactions_page(
            ticker="AAPL", q="starter", type="buy", db=db_session, portfolio=default_portfolio
        )

        assert result["total"] == 1
        assert result["items"][0].ticker == "AAPL"

    def test_ticker_filter_does_not_leak_another_workspace(self, db_session, default_portfolio):
        from models import Portfolio, Workspace

        other_workspace = Workspace(name="Other tenant")
        db_session.add(other_workspace)
        db_session.flush()
        other_portfolio = Portfolio(workspace_id=other_workspace.id, name="Other")
        db_session.add(other_portfolio)
        db_session.flush()
        db_session.add(
            make_txn("NVDA", "buy", 1, 1.0, date=date(2024, 1, 1), portfolio_id=other_portfolio.id)
        )
        db_session.commit()

        result = get_transactions_page(
            ticker="NVDA", db=db_session, portfolio=default_portfolio
        )

        assert result["total"] == 0
