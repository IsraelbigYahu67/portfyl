import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
from unittest.mock import patch, AsyncMock

import pytest
from fastapi import HTTPException

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


def _fire(db, pid):
    """run_check is a coroutine; drive it synchronously so we don't need pytest-asyncio."""
    return asyncio.run(run_check(db, pid))


# -------- CRUD -------------------------------------------------------------

def test_create_normalizes_ticker_and_defaults(db_session, pid):
    a = create_alert(AlertCreate(ticker="aapl", direction="above", target_price=200), db_session, pid)
    assert a["ticker"] == "AAPL"
    assert a["status"] == "active"
    assert a["enabled"] is True
    assert a["triggered_price"] is None


def test_list_annotates_current_price(db_session, pid):
    create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=200), db_session, pid)
    with patch("routers.alerts.market_data.get_infos", _infos(180)):
        rows = list_alerts(db_session, pid)
    assert len(rows) == 1
    assert rows[0]["current_price"] == 180


def test_update_and_delete(db_session, pid):
    a = create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=200), db_session, pid)
    upd = update_alert(a["id"], AlertUpdate(target_price=210, note="near ATH"), db_session, pid)
    assert upd["target_price"] == 210
    assert upd["note"] == "near ATH"

    delete_alert(a["id"], db_session, pid)
    with patch("routers.alerts.market_data.get_infos", _infos(180)):
        assert list_alerts(db_session, pid) == []


def test_update_delete_missing_404(db_session, pid):
    with pytest.raises(HTTPException):
        update_alert(999, AlertUpdate(note="x"), db_session, pid)
    with pytest.raises(HTTPException):
        delete_alert(999, db_session, pid)


# -------- run_check firing semantics --------------------------------------

def test_above_fires_and_marks_triggered(db_session, pid):
    create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=150), db_session, pid)
    sent = AsyncMock()
    with patch("routers.alerts.market_data.get_infos", _infos(175)), \
         patch("routers.alerts.send_discord_notification", sent):
        fired = _fire(db_session, pid)
    assert len(fired) == 1
    assert fired[0]["ticker"] == "AAPL"
    assert fired[0]["triggered_price"] == 175
    sent.assert_awaited_once()
    row = db_session.query(PriceAlert).first()
    assert row.status == "triggered"
    assert row.triggered_price == 175
    assert row.last_triggered_at is not None


def test_below_fires(db_session, pid):
    create_alert(AlertCreate(ticker="AAPL", direction="below", target_price=100), db_session, pid)
    with patch("routers.alerts.market_data.get_infos", _infos(95)), \
         patch("routers.alerts.send_discord_notification", AsyncMock()):
        fired = _fire(db_session, pid)
    assert len(fired) == 1


def test_no_fire_when_not_crossed(db_session, pid):
    create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=200), db_session, pid)
    sent = AsyncMock()
    with patch("routers.alerts.market_data.get_infos", _infos(180)), \
         patch("routers.alerts.send_discord_notification", sent):
        fired = _fire(db_session, pid)
    assert fired == []
    sent.assert_not_awaited()
    assert db_session.query(PriceAlert).first().status == "active"


def test_no_data_skips_without_firing(db_session, pid):
    create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=150), db_session, pid)
    sent = AsyncMock()
    # price 0 == "no live data this pass" — must not fire, stays active for retry
    with patch("routers.alerts.market_data.get_infos", _infos(0)), \
         patch("routers.alerts.send_discord_notification", sent):
        fired = _fire(db_session, pid)
    assert fired == []
    sent.assert_not_awaited()
    assert db_session.query(PriceAlert).first().status == "active"


def test_triggered_does_not_refire(db_session, pid):
    create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=150), db_session, pid)
    sent = AsyncMock()
    with patch("routers.alerts.market_data.get_infos", _infos(175)), \
         patch("routers.alerts.send_discord_notification", sent):
        _fire(db_session, pid)
        again = _fire(db_session, pid)
    assert again == []
    assert sent.await_count == 1


def test_disabled_alert_not_checked(db_session, pid):
    a = create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=150), db_session, pid)
    update_alert(a["id"], AlertUpdate(enabled=False), db_session, pid)
    with patch("routers.alerts.market_data.get_infos", _infos(175)), \
         patch("routers.alerts.send_discord_notification", AsyncMock()):
        assert _fire(db_session, pid) == []


def test_reset_rearms_and_can_fire_again(db_session, pid):
    a = create_alert(AlertCreate(ticker="AAPL", direction="above", target_price=150), db_session, pid)
    with patch("routers.alerts.market_data.get_infos", _infos(175)), \
         patch("routers.alerts.send_discord_notification", AsyncMock()):
        _fire(db_session, pid)

    r = update_alert(a["id"], AlertUpdate(status="active"), db_session, pid)
    assert r["status"] == "active"
    assert r["triggered_price"] is None
    assert r["last_triggered_at"] is None

    with patch("routers.alerts.market_data.get_infos", _infos(175)), \
         patch("routers.alerts.send_discord_notification", AsyncMock()):
        fired = _fire(db_session, pid)
    assert len(fired) == 1
