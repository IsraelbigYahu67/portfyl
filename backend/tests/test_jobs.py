"""Tests for the background job passes (jobs.py): broker auto-sync and
dividend ex-date notifications. Network and Discord are always patched."""

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
from datetime import date
from unittest.mock import patch, AsyncMock

from models import BrokerConnection, DiscordWebhook, DividendNotification
from jobs import broker_autosync_pass, dividend_exdate_pass
from tests.helpers import make_txn


def _run(coro):
    return asyncio.run(coro)


def _connect(db, pid, broker="trading212", auto_sync=True):
    conn = BrokerConnection(portfolio_id=pid, broker=broker, api_key="k" * 20,
                            api_secret="", environment="live", auto_sync=auto_sync)
    db.add(conn)
    db.commit()
    return conn


def _webhook(db, pid, **flags):
    hook = DiscordWebhook(portfolio_id=pid,
                          webhook_url="https://discord.com/api/webhooks/1/x",
                          notify_trades=flags.get("notify_trades", True),
                          notify_dividends=flags.get("notify_dividends", True),
                          notify_milestones=True)
    db.add(hook)
    db.commit()
    return hook


# -------- broker_autosync_pass ---------------------------------------------

def test_autosync_skips_connections_without_flag(db_session, pid):
    _connect(db_session, pid, auto_sync=False)
    with patch("routers.broker.sync_transactions") as sync:
        results = _run(broker_autosync_pass(db_session))
    assert results == []
    sync.assert_not_called()


def test_autosync_syncs_t212_and_notifies(db_session, pid):
    _connect(db_session, pid, auto_sync=True)
    _webhook(db_session, pid, notify_trades=True)
    sent = AsyncMock()
    fake = {"imported_orders": 2, "imported_dividends": 1, "total_imported": 3, "errors": []}
    with patch("routers.broker.sync_transactions", return_value=fake) as sync, \
         patch("jobs.send_discord_notification", sent):
        results = _run(broker_autosync_pass(db_session))
    sync.assert_called_once()
    assert results == [{"portfolio_id": pid, "broker": "trading212", "ok": True, "imported": 3}]
    sent.assert_awaited_once()
    assert "3" in sent.await_args.args[2]  # title mentions the import count


def test_autosync_no_notification_when_nothing_imported(db_session, pid):
    _connect(db_session, pid, auto_sync=True)
    _webhook(db_session, pid, notify_trades=True)
    sent = AsyncMock()
    fake = {"imported_orders": 0, "imported_dividends": 0, "total_imported": 0, "errors": []}
    with patch("routers.broker.sync_transactions", return_value=fake), \
         patch("jobs.send_discord_notification", sent):
        results = _run(broker_autosync_pass(db_session))
    assert results[0]["imported"] == 0
    sent.assert_not_awaited()


def test_autosync_respects_notify_trades_flag(db_session, pid):
    _connect(db_session, pid, auto_sync=True)
    _webhook(db_session, pid, notify_trades=False)
    sent = AsyncMock()
    fake = {"imported_orders": 5, "imported_dividends": 0, "total_imported": 5, "errors": []}
    with patch("routers.broker.sync_transactions", return_value=fake), \
         patch("jobs.send_discord_notification", sent):
        _run(broker_autosync_pass(db_session))
    sent.assert_not_awaited()


def test_autosync_one_failure_does_not_block_others(db_session, default_portfolio):
    from models import Portfolio
    p2 = Portfolio(name="Second")
    db_session.add(p2)
    db_session.commit()
    _connect(db_session, default_portfolio.id, auto_sync=True)
    _connect(db_session, p2.id, auto_sync=True)

    calls = []

    def flaky(db, pid, owner):
        calls.append(pid)
        if pid == default_portfolio.id:
            raise RuntimeError("T212 down")
        return {"imported_orders": 1, "imported_dividends": 0, "total_imported": 1, "errors": []}

    with patch("routers.broker.sync_transactions", side_effect=flaky), \
         patch("jobs.send_discord_notification", AsyncMock()):
        results = _run(broker_autosync_pass(db_session))

    assert calls == [default_portfolio.id, p2.id]  # both attempted
    assert [r["ok"] for r in results] == [False, True]
    assert "T212 down" in results[0]["error"]


def test_autosync_ibkr_uses_ibkr_sync(db_session, pid):
    _connect(db_session, pid, broker="ibkr", auto_sync=True)
    ibkr_sync = AsyncMock(return_value={"imported": 4})
    with patch("routers.ibkr._run_ibkr_sync", ibkr_sync), \
         patch("jobs.send_discord_notification", AsyncMock()):
        results = _run(broker_autosync_pass(db_session))
    ibkr_sync.assert_awaited_once()
    assert results == [{"portfolio_id": pid, "broker": "ibkr", "ok": True, "imported": 4}]


# -------- dividend_exdate_pass ----------------------------------------------

def _div_info(ex_date, amount=0.25):
    """Stand-in for _next_dividend_info."""
    def _fn(ticker):
        return {"ticker": ticker,
                "ex_date": ex_date.isoformat() if ex_date else None,
                "amount_per_share": amount, "frequency": "quarterly"}
    return _fn


def _seed_holding(db, pid, ticker="AAPL", shares=10):
    db.add(make_txn(ticker, "buy", shares, 100.0, date=date(2024, 1, 15), portfolio_id=pid))
    db.commit()


def test_dividend_pass_announces_upcoming_exdate(db_session, pid):
    _webhook(db_session, pid, notify_dividends=True)
    _seed_holding(db_session, pid)
    today = date(2026, 7, 12)
    sent = AsyncMock()
    with patch("routers.dividend_calendar._next_dividend_info", _div_info(date(2026, 7, 14))), \
         patch("jobs.send_discord_notification", sent):
        announced = _run(dividend_exdate_pass(db_session, today=today, lead_days=3))
    assert len(announced) == 1
    assert announced[0]["ticker"] == "AAPL"
    assert announced[0]["est_payment"] == 2.5  # 10 sh * 0.25
    sent.assert_awaited_once()
    assert "AAPL" in sent.await_args.args[3]
    row = db_session.query(DividendNotification).one()
    assert row.ticker == "AAPL"
    assert row.ex_date == date(2026, 7, 14)


def test_dividend_pass_never_announces_twice(db_session, pid):
    _webhook(db_session, pid, notify_dividends=True)
    _seed_holding(db_session, pid)
    today = date(2026, 7, 12)
    sent = AsyncMock()
    with patch("routers.dividend_calendar._next_dividend_info", _div_info(date(2026, 7, 14))), \
         patch("jobs.send_discord_notification", sent):
        first = _run(dividend_exdate_pass(db_session, today=today, lead_days=3))
        second = _run(dividend_exdate_pass(db_session, today=today, lead_days=3))
    assert len(first) == 1
    assert second == []
    assert sent.await_count == 1
    assert db_session.query(DividendNotification).count() == 1


def test_dividend_pass_ignores_exdates_outside_window(db_session, pid):
    _webhook(db_session, pid, notify_dividends=True)
    _seed_holding(db_session, pid)
    today = date(2026, 7, 12)
    sent = AsyncMock()
    # Ex-date 10 days out, window is 3 — nothing to announce (yet).
    with patch("routers.dividend_calendar._next_dividend_info", _div_info(date(2026, 7, 22))), \
         patch("jobs.send_discord_notification", sent):
        announced = _run(dividend_exdate_pass(db_session, today=today, lead_days=3))
    assert announced == []
    sent.assert_not_awaited()
    # A past ex-date must not be announced either.
    with patch("routers.dividend_calendar._next_dividend_info", _div_info(date(2026, 7, 10))), \
         patch("jobs.send_discord_notification", sent):
        announced = _run(dividend_exdate_pass(db_session, today=today, lead_days=3))
    assert announced == []


def test_dividend_pass_respects_notify_dividends_flag(db_session, pid):
    _webhook(db_session, pid, notify_dividends=False)
    _seed_holding(db_session, pid)
    sent = AsyncMock()
    with patch("routers.dividend_calendar._next_dividend_info", _div_info(date(2026, 7, 14))), \
         patch("jobs.send_discord_notification", sent):
        announced = _run(dividend_exdate_pass(db_session, today=date(2026, 7, 12)))
    assert announced == []
    sent.assert_not_awaited()


def test_dividend_pass_skips_tickers_without_exdate(db_session, pid):
    _webhook(db_session, pid, notify_dividends=True)
    _seed_holding(db_session, pid)
    sent = AsyncMock()
    with patch("routers.dividend_calendar._next_dividend_info", _div_info(None)), \
         patch("jobs.send_discord_notification", sent):
        announced = _run(dividend_exdate_pass(db_session, today=date(2026, 7, 12)))
    assert announced == []
    sent.assert_not_awaited()
