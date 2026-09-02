import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
from unittest.mock import patch, AsyncMock
from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from models import PriceAlert
from routers.alerts import (
    create_alert, list_alerts, update_alert, delete_alert, run_check,
    AlertCreate, AlertUpdate,
)


def _infos(price, currency="USD"):
    """Stand-in for market_data.get_infos: every requested ticker quotes `price`."""
    def _fn(tickers, *a, **k):
        return {t: {"currentPrice": price, "regularMarketPrice": price, "currency": currency}
                for t in tickers}
    return _fn


def _fire(db, portfolio):
    """run_check is a coroutine; drive it synchronously so we don't need pytest-asyncio."""
    return asyncio.run(run_check(db, portfolio.workspace_id, portfolio.id))


# -------- CRUD -------------------------------------------------------------

def test_create_normalizes_ticker_and_defaults(db_session, default_portfolio):
    a = create_alert(AlertCreate(ticker="aapl", direction="above", target_price=200), db_session, default_portfolio)
    assert a["ticker"] == "AAPL"
    assert a["status"] == "active"
    assert a["enabled"] is True
    assert a["triggered_price"] is None


def test_list_annotates_current_price(db_session, default_portfolio):
    create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=200), db_session, default_portfolio)
    with patch("routers.alerts.market_data.get_infos", _infos(180)):
        rows = list_alerts(db_session, default_portfolio)
    assert len(rows) == 1
    assert rows[0]["current_price"] == 180


def test_update_and_delete(db_session, default_portfolio):
    a = create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=200), db_session, default_portfolio)
    upd = update_alert(UUID(a["id"]), AlertUpdate(target_price=210, note="near ATH"), db_session, default_portfolio)
    assert upd["target_price"] == 210
    assert upd["note"] == "near ATH"

    delete_alert(UUID(a["id"]), db_session, default_portfolio)
    with patch("routers.alerts.market_data.get_infos", _infos(180)):
        assert list_alerts(db_session, default_portfolio) == []


def test_update_delete_missing_404(db_session, default_portfolio):
    from uuid import uuid4
    missing = uuid4()
    with pytest.raises(HTTPException):
        update_alert(missing, AlertUpdate(note="x"), db_session, default_portfolio)
    with pytest.raises(HTTPException):
        delete_alert(missing, db_session, default_portfolio)


# -------- run_check firing semantics --------------------------------------

def test_above_fires_and_marks_triggered(db_session, default_portfolio):
    create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=150), db_session, default_portfolio)
    sent = AsyncMock()
    with patch("routers.alerts.market_data.get_infos", _infos(175)), \
         patch("routers.alerts.send_discord_notification", sent):
        fired = _fire(db_session, default_portfolio)
    assert len(fired) == 1
    assert fired[0]["ticker"] == "AAPL"
    assert fired[0]["triggered_price"] == 175
    sent.assert_awaited_once()
    row = db_session.query(PriceAlert).first()
    assert row.status == "triggered"
    assert row.triggered_price == 175
    assert row.last_triggered_at is not None


def test_below_fires(db_session, default_portfolio):
    create_alert(AlertCreate(ticker="AAPL", direction="below", target_price=100), db_session, default_portfolio)
    with patch("routers.alerts.market_data.get_infos", _infos(95)), \
         patch("routers.alerts.send_discord_notification", AsyncMock()):
        fired = _fire(db_session, default_portfolio)
    assert len(fired) == 1


def test_no_fire_when_not_crossed(db_session, default_portfolio):
    create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=200), db_session, default_portfolio)
    sent = AsyncMock()
    with patch("routers.alerts.market_data.get_infos", _infos(180)), \
         patch("routers.alerts.send_discord_notification", sent):
        fired = _fire(db_session, default_portfolio)
    assert fired == []
    sent.assert_not_awaited()
    assert db_session.query(PriceAlert).first().status == "active"


def test_no_data_skips_without_firing(db_session, default_portfolio):
    create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=150), db_session, default_portfolio)
    sent = AsyncMock()
    # price 0 == "no live data this pass" — must not fire, stays active for retry
    with patch("routers.alerts.market_data.get_infos", _infos(0)), \
         patch("routers.alerts.send_discord_notification", sent):
        fired = _fire(db_session, default_portfolio)
    assert fired == []
    sent.assert_not_awaited()
    assert db_session.query(PriceAlert).first().status == "active"


def test_triggered_does_not_refire(db_session, default_portfolio):
    create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=150), db_session, default_portfolio)
    sent = AsyncMock()
    with patch("routers.alerts.market_data.get_infos", _infos(175)), \
         patch("routers.alerts.send_discord_notification", sent):
        _fire(db_session, default_portfolio)
        again = _fire(db_session, default_portfolio)
    assert again == []
    assert sent.await_count == 1


def test_disabled_alert_not_checked(db_session, default_portfolio):
    a = create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=150), db_session, default_portfolio)
    update_alert(UUID(a["id"]), AlertUpdate(enabled=False), db_session, default_portfolio)
    with patch("routers.alerts.market_data.get_infos", _infos(175)), \
         patch("routers.alerts.send_discord_notification", AsyncMock()):
        assert _fire(db_session, default_portfolio) == []


def test_alert_stays_armed_when_discord_delivery_fails(db_session, default_portfolio):
    # send_discord_notification returns False when the webhook post fails — the
    # alert must stay active so the next pass retries, instead of flipping to
    # triggered with no notification ever delivered.
    create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=150), db_session, default_portfolio)
    with patch("routers.alerts.market_data.get_infos", _infos(175)), \
         patch("routers.alerts.send_discord_notification", AsyncMock(return_value=False)):
        fired = _fire(db_session, default_portfolio)
    assert fired == []
    row = db_session.query(PriceAlert).first()
    assert row.status == "active"
    assert row.triggered_price is None

    # Webhook recovers: the same crossing fires and is recorded.
    with patch("routers.alerts.market_data.get_infos", _infos(175)), \
         patch("routers.alerts.send_discord_notification", AsyncMock(return_value=True)):
        fired = _fire(db_session, default_portfolio)
    assert len(fired) == 1
    assert db_session.query(PriceAlert).first().status == "triggered"


def test_update_cannot_force_triggered_status(db_session, default_portfolio):
    # Only the checker sets "triggered": a PATCH must not fake a trigger (or
    # silently disarm monitoring) by writing the status directly.
    create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=150), db_session, default_portfolio)
    with pytest.raises(ValidationError):
        AlertUpdate(status="triggered")
    assert db_session.query(PriceAlert).first().status == "active"


def test_reset_rearms_and_can_fire_again(db_session, default_portfolio):
    a = create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=150), db_session, default_portfolio)
    with patch("routers.alerts.market_data.get_infos", _infos(175)), \
         patch("routers.alerts.send_discord_notification", AsyncMock()):
        _fire(db_session, default_portfolio)

    r = update_alert(UUID(a["id"]), AlertUpdate(status="active"), db_session, default_portfolio)
    assert r["status"] == "active"
    assert r["triggered_price"] is None
    assert r["last_triggered_at"] is None

    with patch("routers.alerts.market_data.get_infos", _infos(175)), \
         patch("routers.alerts.send_discord_notification", AsyncMock()):
        fired = _fire(db_session, default_portfolio)
    assert len(fired) == 1


# -------- workspace scoping --------------------------------------------------

def test_run_check_never_fires_alerts_outside_the_given_workspace(db_session, default_portfolio):
    from uuid import uuid4
    from models import Portfolio, Workspace

    other_workspace = Workspace(id=uuid4(), name="Other workspace")
    db_session.add(other_workspace)
    db_session.flush()
    other_portfolio = Portfolio(workspace_id=other_workspace.id, name="Other", is_default=True)
    db_session.add(other_portfolio)
    db_session.commit()
    db_session.refresh(other_portfolio)

    create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=150), db_session, default_portfolio)
    create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=150), db_session, other_portfolio)

    sent = AsyncMock()
    with patch("routers.alerts.market_data.get_infos", _infos(175)), \
         patch("routers.alerts.send_discord_notification", sent):
        fired = asyncio.run(run_check(db_session, default_portfolio.workspace_id))

    # Only default_portfolio's alert fires -- other_workspace's identical alert
    # is untouched even though run_check was given no portfolio_id filter.
    assert len(fired) == 1
    other_alert = db_session.query(PriceAlert).filter(
        PriceAlert.workspace_id == other_workspace.id
    ).first()
    assert other_alert.status == "active"
