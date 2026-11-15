from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from plans import PlanTier
from entitlements import EntitlementDenied, ensure_final_count_limit, resolve_entitlements
from edition import Edition
from models import Transaction
from routers.portfolio import create_transaction
from schemas import TransactionCreate
from tests.helpers import cap_free_limits


def _fill_positions(db_session, portfolio, count: int) -> None:
    for number in range(count):
        db_session.add(Transaction(
            workspace_id=portfolio.workspace_id,
            portfolio_id=portfolio.id,
            ticker=f"T{number}",
            type="buy",
            shares=1,
            price=1,
            currency="USD",
            date=date(2026, 9, 1),
        ))
    db_session.flush()


def _new_position() -> TransactionCreate:
    return TransactionCreate(
        ticker="overflow",
        type="buy",
        shares=1,
        price=1,
        currency="USD",
        date=date(2026, 9, 4),
    )


def test_overflow_reduction_is_allowed_but_overflow_growth_is_denied(
    db_session, test_workspace, monkeypatch
):
    cap_free_limits(monkeypatch, active_positions=15)
    free = resolve_entitlements(
        db_session,
        edition=Edition.CLOUD,
        workspace_id=test_workspace.id,
    )
    assert free.plan is PlanTier.FREE
    ensure_final_count_limit(free, "active_positions", current=17, final=16)
    with pytest.raises(EntitlementDenied) as denied:
        ensure_final_count_limit(free, "active_positions", current=15, final=16)
    assert denied.value.payload()["resource"] == "active_positions"


def test_manual_trade_cannot_exceed_a_position_cap(db_session, default_portfolio, monkeypatch):
    cap_free_limits(monkeypatch, active_positions=15)
    _fill_positions(db_session, default_portfolio, 15)
    monkeypatch.setenv("PORTFYL_EDITION", "cloud")
    with (
        patch("routers.portfolio.market_data.get_info", return_value={}),
        patch("routers.portfolio.fetch_fx_to_czk", return_value=22),
        pytest.raises(EntitlementDenied) as denied,
    ):
        create_transaction(_new_position(), db=db_session, portfolio=default_portfolio)
    assert denied.value.payload() == {
        "code": "quota_exceeded",
        "plan": "free",
        "resource": "active_positions",
        "limit": 15,
        "used": 15,
    }
    assert db_session.query(Transaction).count() == 15


def test_free_plan_has_no_position_limit(db_session, default_portfolio, monkeypatch):
    _fill_positions(db_session, default_portfolio, 15)
    monkeypatch.setenv("PORTFYL_EDITION", "cloud")
    with (
        patch("routers.portfolio.market_data.get_info", return_value={}),
        patch("routers.portfolio.fetch_fx_to_czk", return_value=22),
    ):
        create_transaction(_new_position(), db=db_session, portfolio=default_portfolio)
    assert db_session.query(Transaction).count() == 16
