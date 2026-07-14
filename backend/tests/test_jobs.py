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


def test_autosync_t212_sync_runs_off_event_loop(db_session, pid):
    # sync_transactions does blocking HTTP; it must run in a worker thread,
    # never directly on the event loop — a direct call froze every concurrent
    # request for the duration of the sync.
    _connect(db_session, pid, auto_sync=True)
    seen = {}

    def probing_sync(db, pid_, owner):
        try:
            asyncio.get_running_loop()
            seen["on_loop"] = True
        except RuntimeError:
            seen["on_loop"] = False
        return {"imported_orders": 0, "imported_dividends": 0, "total_imported": 0, "errors": []}

    with patch("routers.broker.sync_transactions", side_effect=probing_sync):
        _run(broker_autosync_pass(db_session))
    assert seen["on_loop"] is False


def test_scheduler_sync_respects_auto_sync_flag(db_session, default_portfolio):
    # The external Cloud Scheduler entrypoint must honor the same per-connection
    # opt-in as the in-process poller — otherwise turning auto-sync off in
    # Settings silently keeps syncing on scheduler deployments.
    from models import Portfolio
    from routers.ibkr import scheduler_sync

    p2 = Portfolio(name="Second")
    db_session.add(p2)
    db_session.commit()
    _connect(db_session, default_portfolio.id, broker="ibkr", auto_sync=True)
    _connect(db_session, p2.id, broker="ibkr", auto_sync=False)

    ibkr_sync = AsyncMock(return_value={"imported": 1})
    with patch("routers.ibkr._run_ibkr_sync", ibkr_sync), \
         patch("routers.ibkr.check_scheduler_token", return_value=True):
        _run(scheduler_sync(db=db_session, x_scheduler_token="tok", token=None))

    ibkr_sync.assert_awaited_once()
    assert ibkr_sync.await_args.args[1] == default_portfolio.id


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


def test_dividend_lookup_runs_off_event_loop(db_session, pid):
    # _next_dividend_info does blocking yfinance I/O per holding — the pass
    # must push the whole lookup into a worker thread, off the event loop.
    _webhook(db_session, pid, notify_dividends=True)
    _seed_holding(db_session, pid)
    seen = {}

    def probing_info(ticker):
        try:
            asyncio.get_running_loop()
            seen["on_loop"] = True
        except RuntimeError:
            seen["on_loop"] = False
        return {"ticker": ticker, "ex_date": None, "amount_per_share": None}

    with patch("routers.dividend_calendar._next_dividend_info", probing_info), \
         patch("jobs.send_discord_notification", AsyncMock()):
        _run(dividend_exdate_pass(db_session, today=date(2026, 7, 12)))
    assert seen["on_loop"] is False


def test_dividend_dedup_not_written_when_delivery_fails(db_session, pid):
    # A failed Discord post must not consume the one-shot dedup row — the next
    # tick has to retry, otherwise the notification is lost forever.
    _webhook(db_session, pid, notify_dividends=True)
    _seed_holding(db_session, pid)
    today = date(2026, 7, 12)
    with patch("routers.dividend_calendar._next_dividend_info", _div_info(date(2026, 7, 14))), \
         patch("jobs.send_discord_notification", AsyncMock(return_value=False)):
        announced = _run(dividend_exdate_pass(db_session, today=today, lead_days=3))
    assert announced == []
    assert db_session.query(DividendNotification).count() == 0

    # Webhook back up: the same dividend is announced and deduped normally.
    with patch("routers.dividend_calendar._next_dividend_info", _div_info(date(2026, 7, 14))), \
         patch("jobs.send_discord_notification", AsyncMock(return_value=True)):
        announced = _run(dividend_exdate_pass(db_session, today=today, lead_days=3))
    assert len(announced) == 1
    assert db_session.query(DividendNotification).count() == 1


def test_dividend_pass_skips_tickers_without_exdate(db_session, pid):
    _webhook(db_session, pid, notify_dividends=True)
    _seed_holding(db_session, pid)
    sent = AsyncMock()
    with patch("routers.dividend_calendar._next_dividend_info", _div_info(None)), \
         patch("jobs.send_discord_notification", sent):
        announced = _run(dividend_exdate_pass(db_session, today=date(2026, 7, 12)))
    assert announced == []
    sent.assert_not_awaited()


# -------- sync_due / next_sync_run ------------------------------------------

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from jobs import sync_due, next_sync_run

PRAGUE = ZoneInfo("Europe/Prague")
# 2026-07-13 is CEST (UTC+2): the 02:00 local boundary is 00:00 UTC.


def test_daily_due_when_never_ran():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    assert sync_due(now, "daily", "02:00", 6, None, PRAGUE) is True


def test_daily_not_due_after_todays_run():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    last = datetime(2026, 7, 13, 0, 5, tzinfo=timezone.utc)  # ran just after 02:00 local
    assert sync_due(now, "daily", "02:00", 6, last, PRAGUE) is False


def test_daily_due_once_boundary_crossed():
    # Ran yesterday; now it's 03:00 local today — today's boundary has passed.
    now = datetime(2026, 7, 13, 1, 0, tzinfo=timezone.utc)
    last = datetime(2026, 7, 12, 0, 5, tzinfo=timezone.utc)
    assert sync_due(now, "daily", "02:00", 6, last, PRAGUE) is True


def test_daily_not_due_before_todays_boundary():
    # 01:30 local on the 13th — most recent boundary is yesterday's, already ran.
    now = datetime(2026, 7, 12, 23, 30, tzinfo=timezone.utc)
    last = datetime(2026, 7, 12, 0, 10, tzinfo=timezone.utc)
    assert sync_due(now, "daily", "02:00", 6, last, PRAGUE) is False


def test_daily_catches_up_after_downtime():
    # App was down for three days: first check after boot must fire.
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    last = datetime(2026, 7, 10, 0, 5, tzinfo=timezone.utc)
    assert sync_due(now, "daily", "02:00", 6, last, PRAGUE) is True


def test_daily_dst_spring_forward_fires_once():
    # 2026-03-29: Prague jumps 02:00 CET -> 03:00 CEST; 02:00 does not exist.
    # The boundary resolves to 01:00 UTC. Ran yesterday -> due; ran today -> not.
    now = datetime(2026, 3, 29, 8, 0, tzinfo=timezone.utc)
    ran_yesterday = datetime(2026, 3, 28, 1, 30, tzinfo=timezone.utc)
    ran_today = datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc)
    assert sync_due(now, "daily", "02:00", 6, ran_yesterday, PRAGUE) is True
    assert sync_due(now, "daily", "02:00", 6, ran_today, PRAGUE) is False


def test_interval_due_when_never_ran():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    assert sync_due(now, "interval", "02:00", 6, None, PRAGUE) is True


def test_interval_due_after_elapsed():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    assert sync_due(now, "interval", "02:00", 6, now - timedelta(hours=7), PRAGUE) is True
    assert sync_due(now, "interval", "02:00", 6, now - timedelta(hours=5), PRAGUE) is False


def test_next_run_none_when_due_now():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    assert next_sync_run(now, "daily", "02:00", 6, None, PRAGUE) is None


def test_next_run_daily_is_next_boundary():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    last = datetime(2026, 7, 13, 0, 5, tzinfo=timezone.utc)
    nxt = next_sync_run(now, "daily", "02:00", 6, last, PRAGUE)
    assert nxt == datetime(2026, 7, 14, 0, 0, tzinfo=timezone.utc)  # 02:00 CEST tomorrow


def test_next_run_interval_is_last_plus_interval():
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    last = now - timedelta(hours=2)
    nxt = next_sync_run(now, "interval", "02:00", 6, last, PRAGUE)
    assert nxt == last + timedelta(hours=6)
