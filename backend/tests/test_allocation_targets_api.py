"""Target allocation API (plan 2026-10-10, Task 3). Router functions are called
directly, as elsewhere in the fast suite; the HTTP surface and tenant isolation
are covered by tests/postgres (Task 4)."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from models import AllocationTarget, Portfolio
from routers.allocation_targets import (
    TargetItem,
    TargetsPayload,
    _current_holdings,
    list_targets,
    replace_targets,
    target_drift,
)


def payload(*items):
    return TargetsPayload(targets=[TargetItem(**item) for item in items])


def save(db, portfolio, context, *items):
    return replace_targets(payload(*items), db=db, portfolio=portfolio, context=context)


def test_list_is_empty_by_default(db_session, default_portfolio):
    assert list_targets(db=db_session, portfolio=default_portfolio) == {
        "targets": [], "target_total_pct": 0.0, "is_complete": False,
    }


def test_replace_saves_normalized_targets_in_order(db_session, default_portfolio, request_context):
    result = save(
        db_session, default_portfolio, request_context,
        {"ticker": " msft ", "target_pct": "40", "group": " Core "},
        {"ticker": "AAPL", "target_pct": "60"},
    )

    assert result == {
        "targets": [
            {"ticker": "MSFT", "group": "Core", "target_pct": 40.0},
            {"ticker": "AAPL", "group": None, "target_pct": 60.0},
        ],
        "target_total_pct": 100.0,
        "is_complete": True,
    }


def test_replace_overwrites_the_previous_set(db_session, default_portfolio, request_context):
    save(db_session, default_portfolio, request_context,
         {"ticker": "AAPL", "target_pct": "60"}, {"ticker": "MSFT", "target_pct": "40"})
    save(db_session, default_portfolio, request_context, {"ticker": "NVDA", "target_pct": "10"})

    result = list_targets(db=db_session, portfolio=default_portfolio)
    assert [t["ticker"] for t in result["targets"]] == ["NVDA"]
    assert db_session.query(AllocationTarget).count() == 1


def test_empty_payload_clears_all_targets(db_session, default_portfolio, request_context):
    save(db_session, default_portfolio, request_context, {"ticker": "AAPL", "target_pct": "60"})
    assert save(db_session, default_portfolio, request_context)["targets"] == []


def test_invalid_set_is_rejected_without_changing_saved_targets(
    db_session, default_portfolio, request_context,
):
    save(db_session, default_portfolio, request_context, {"ticker": "AAPL", "target_pct": "50"})

    with pytest.raises(HTTPException) as exc:
        save(db_session, default_portfolio, request_context,
             {"ticker": "aapl", "target_pct": "10"}, {"ticker": "AAPL", "target_pct": "20"})

    assert exc.value.status_code == 422
    assert exc.value.detail == "AAPL has more than one target."
    assert list_targets(db=db_session, portfolio=default_portfolio)["targets"] == [
        {"ticker": "AAPL", "group": None, "target_pct": 50.0},
    ]


def test_targets_are_scoped_to_their_portfolio(db_session, default_portfolio, request_context):
    other = Portfolio(workspace_id=default_portfolio.workspace_id, name="Other")
    db_session.add(other)
    db_session.commit()

    save(db_session, default_portfolio, request_context, {"ticker": "AAPL", "target_pct": "100"})

    assert list_targets(db=db_session, portfolio=other)["targets"] == []


def test_drift_joins_targets_with_current_holdings(db_session, default_portfolio, request_context):
    save(db_session, default_portfolio, request_context, {"ticker": "AAPL", "target_pct": "60"})
    holdings = [
        {"ticker": "AAPL", "name": "Apple", "market_value": 600.0, "closed": False, "price_status": "live"},
        {"ticker": "TSLA", "name": "Tesla", "market_value": 400.0, "closed": False, "price_status": "live"},
    ]

    with patch("routers.allocation_targets._current_holdings", return_value=holdings) as fake:
        result = target_drift(currency="czk", db=db_session, portfolio=default_portfolio)

    fake.assert_called_once_with(db_session, default_portfolio, "CZK")
    assert result["currency"] == "CZK"
    assert result["source"]
    assert result["as_of"].endswith("Z")
    assert result["rows"][0]["drift_pct"] == 0.0
    assert result["unassigned_pct"] == 40.0


def test_current_holdings_reads_active_holdings_only(db_session, default_portfolio):
    with patch("routers.allocation_targets.get_holdings", return_value=[]) as fake:
        assert _current_holdings(db_session, default_portfolio, "USD") == []

    fake.assert_called_once_with(
        include_closed=False, currency="USD", db=db_session, portfolio=default_portfolio,
    )
