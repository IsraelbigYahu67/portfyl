"""Tests for the background job passes (jobs.py): broker auto-sync and
dividend ex-date notifications. Network and Discord are always patched."""

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import asyncio
import pytest
from datetime import date
from unittest.mock import patch, AsyncMock

from models import BrokerConnection, DiscordWebhook, DividendNotification
from jobs import broker_autosync_pass, dividend_exdate_pass
from tests.helpers import TEST_WORKSPACE_ID, make_txn


@pytest.fixture(autouse=True)
def _no_sync_tz_env(monkeypatch):
    """Schedule tests assume the Europe/Prague default; keep the suite hermetic."""
    monkeypatch.delenv("BROKER_SYNC_TIMEZONE", raising=False)


def _run(coro):
    return asyncio.run(coro)


def _connect(db, pid, broker="trading212", auto_sync=True, workspace_id=TEST_WORKSPACE_ID):
    conn = BrokerConnection(workspace_id=workspace_id, portfolio_id=pid, broker=broker,
                            api_key="k" * 20, api_secret="", environment="live",
                            auto_sync=auto_sync)
    db.add(conn)
    db.commit()
    return conn


def _webhook(db, pid, workspace_id=TEST_WORKSPACE_ID, **flags):
    hook = DiscordWebhook(workspace_id=workspace_id, portfolio_id=pid,
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
        results = _run(broker_autosync_pass(db_session, TEST_WORKSPACE_ID))
    assert results == []
    sync.assert_not_called()


def test_autosync_syncs_t212_and_notifies(db_session, pid):
    _connect(db_session, pid, auto_sync=True)
    _webhook(db_session, pid, notify_trades=True)
    sent = AsyncMock()
    fake = {"imported_orders": 2, "imported_dividends": 1, "total_imported": 3, "errors": []}
    with patch("routers.broker.sync_transactions", return_value=fake) as sync, \
         patch("jobs.send_discord_notification", sent):
        results = _run(broker_autosync_pass(db_session, TEST_WORKSPACE_ID))
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
        results = _run(broker_autosync_pass(db_session, TEST_WORKSPACE_ID))
    assert results[0]["imported"] == 0
    sent.assert_not_awaited()


def test_autosync_respects_notify_trades_flag(db_session, pid):
    _connect(db_session, pid, auto_sync=True)
    _webhook(db_session, pid, notify_trades=False)
    sent = AsyncMock()
    fake = {"imported_orders": 5, "imported_dividends": 0, "total_imported": 5, "errors": []}
    with patch("routers.broker.sync_transactions", return_value=fake), \
         patch("jobs.send_discord_notification", sent):
        _run(broker_autosync_pass(db_session, TEST_WORKSPACE_ID))
    sent.assert_not_awaited()


def test_autosync_one_failure_does_not_block_others(db_session, default_portfolio):
    from models import Portfolio
    p2 = Portfolio(workspace_id=default_portfolio.workspace_id, name="Second")
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
        results = _run(broker_autosync_pass(db_session, TEST_WORKSPACE_ID))

    assert calls == [default_portfolio.id, p2.id]  # both attempted
    assert [r["ok"] for r in results] == [False, True]
    assert "T212 down" in results[0]["error"]


def test_autosync_ibkr_uses_ibkr_sync(db_session, pid):
    _connect(db_session, pid, broker="ibkr", auto_sync=True)
    ibkr_sync = AsyncMock(return_value={"imported": 4})
    with patch("routers.ibkr._run_ibkr_sync", ibkr_sync), \
         patch("jobs.send_discord_notification", AsyncMock()):
        results = _run(broker_autosync_pass(db_session, TEST_WORKSPACE_ID))
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
        _run(broker_autosync_pass(db_session, TEST_WORKSPACE_ID))
    assert seen["on_loop"] is False


def test_scheduler_sync_respects_auto_sync_flag(db_session, default_portfolio):
    # The external Cloud Scheduler entrypoint must honor the same per-connection
    # opt-in as the in-process poller — otherwise turning auto-sync off in
    # Settings silently keeps syncing on scheduler deployments.
    from models import Portfolio
    from routers.ibkr import scheduler_sync

    p2 = Portfolio(workspace_id=default_portfolio.workspace_id, name="Second")
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
    with patch("jobs._next_dividend_info", _div_info(date(2026, 7, 14))), \
         patch("jobs.send_discord_notification", sent):
        announced = _run(dividend_exdate_pass(db_session, TEST_WORKSPACE_ID, today=today, lead_days=3))
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
    with patch("jobs._next_dividend_info", _div_info(date(2026, 7, 14))), \
         patch("jobs.send_discord_notification", sent):
        first = _run(dividend_exdate_pass(db_session, TEST_WORKSPACE_ID, today=today, lead_days=3))
        second = _run(dividend_exdate_pass(db_session, TEST_WORKSPACE_ID, today=today, lead_days=3))
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
    with patch("jobs._next_dividend_info", _div_info(date(2026, 7, 22))), \
         patch("jobs.send_discord_notification", sent):
        announced = _run(dividend_exdate_pass(db_session, TEST_WORKSPACE_ID, today=today, lead_days=3))
    assert announced == []
    sent.assert_not_awaited()
    # A past ex-date must not be announced either.
    with patch("jobs._next_dividend_info", _div_info(date(2026, 7, 10))), \
         patch("jobs.send_discord_notification", sent):
        announced = _run(dividend_exdate_pass(db_session, TEST_WORKSPACE_ID, today=today, lead_days=3))
    assert announced == []


def test_dividend_pass_respects_notify_dividends_flag(db_session, pid):
    _webhook(db_session, pid, notify_dividends=False)
    _seed_holding(db_session, pid)
    sent = AsyncMock()
    with patch("jobs._next_dividend_info", _div_info(date(2026, 7, 14))), \
         patch("jobs.send_discord_notification", sent):
        announced = _run(dividend_exdate_pass(db_session, TEST_WORKSPACE_ID, today=date(2026, 7, 12)))
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

    with patch("jobs._next_dividend_info", probing_info), \
         patch("jobs.send_discord_notification", AsyncMock()):
        _run(dividend_exdate_pass(db_session, TEST_WORKSPACE_ID, today=date(2026, 7, 12)))
    assert seen["on_loop"] is False


def test_dividend_dedup_not_written_when_delivery_fails(db_session, pid):
    # A failed Discord post must not consume the one-shot dedup row — the next
    # tick has to retry, otherwise the notification is lost forever.
    _webhook(db_session, pid, notify_dividends=True)
    _seed_holding(db_session, pid)
    today = date(2026, 7, 12)
    with patch("jobs._next_dividend_info", _div_info(date(2026, 7, 14))), \
         patch("jobs.send_discord_notification", AsyncMock(return_value=False)):
        announced = _run(dividend_exdate_pass(db_session, TEST_WORKSPACE_ID, today=today, lead_days=3))
    assert announced == []
    assert db_session.query(DividendNotification).count() == 0

    # Webhook back up: the same dividend is announced and deduped normally.
    with patch("jobs._next_dividend_info", _div_info(date(2026, 7, 14))), \
         patch("jobs.send_discord_notification", AsyncMock(return_value=True)):
        announced = _run(dividend_exdate_pass(db_session, TEST_WORKSPACE_ID, today=today, lead_days=3))
    assert len(announced) == 1
    assert db_session.query(DividendNotification).count() == 1


def test_dividend_pass_skips_tickers_without_exdate(db_session, pid):
    _webhook(db_session, pid, notify_dividends=True)
    _seed_holding(db_session, pid)
    sent = AsyncMock()
    with patch("jobs._next_dividend_info", _div_info(None)), \
         patch("jobs.send_discord_notification", sent):
        announced = _run(dividend_exdate_pass(db_session, TEST_WORKSPACE_ID, today=date(2026, 7, 12)))
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


def test_daily_dst_gap_time_fires_once_not_repeatedly():
    # 2026-03-29: Prague skips 02:00->03:00. A daily_time of 02:30 is inside
    # the gap; its boundary resolves to 01:30 UTC. Before that instant the
    # sync must NOT be due (the old code re-fired every tick here), at/after
    # it exactly one run happens.
    ran_yesterday = datetime(2026, 3, 28, 1, 35, tzinfo=timezone.utc)
    before = datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc)
    assert sync_due(before, "daily", "02:30", 6, ran_yesterday, PRAGUE) is False
    at = datetime(2026, 3, 29, 1, 31, tzinfo=timezone.utc)
    assert sync_due(at, "daily", "02:30", 6, ran_yesterday, PRAGUE) is True
    # once run at `at`, later ticks are not due
    later = datetime(2026, 3, 29, 1, 45, tzinfo=timezone.utc)
    assert sync_due(later, "daily", "02:30", 6, at, PRAGUE) is False


def test_daily_dst_fall_back_ambiguous_time_fires_once():
    # 2026-10-25: Prague repeats 02:00-03:00 (CEST->CET). 02:30 is ambiguous;
    # fold=0 picks the first occurrence (00:30 UTC). Exactly one fire per day.
    ran_yesterday = datetime(2026, 10, 24, 0, 35, tzinfo=timezone.utc)
    now = datetime(2026, 10, 25, 2, 0, tzinfo=timezone.utc)
    assert sync_due(now, "daily", "02:30", 6, ran_yesterday, PRAGUE) is True
    assert sync_due(now, "daily", "02:30", 6, now, PRAGUE) is False


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


# -------- schedule config persistence ----------------------------------------

from app_settings import set_workspace_setting
from jobs import (SYNC_MODE_KEY, SYNC_DAILY_TIME_KEY, SYNC_INTERVAL_HOURS_KEY,
                  SYNC_LAST_RUN_KEY, load_sync_schedule, mark_sync_ran, sync_timezone)


def test_sync_timezone_default_and_override(monkeypatch):
    monkeypatch.delenv("BROKER_SYNC_TIMEZONE", raising=False)
    assert sync_timezone().key == "Europe/Prague"
    monkeypatch.setenv("BROKER_SYNC_TIMEZONE", "America/New_York")
    assert sync_timezone().key == "America/New_York"
    monkeypatch.setenv("BROKER_SYNC_TIMEZONE", "Not/AZone")
    assert sync_timezone().key == "Europe/Prague"  # bad value falls back


def test_load_schedule_defaults_on_empty_db(db_session):
    s = load_sync_schedule(db_session, TEST_WORKSPACE_ID)
    assert s == {"mode": "daily", "daily_time": "02:00",
                 "interval_hours": 6, "last_run": None}


def test_load_schedule_falls_back_on_garbage(db_session):
    set_workspace_setting(db_session, TEST_WORKSPACE_ID, SYNC_MODE_KEY, "weekly")
    set_workspace_setting(db_session, TEST_WORKSPACE_ID, SYNC_DAILY_TIME_KEY, "25:99")
    set_workspace_setting(db_session, TEST_WORKSPACE_ID, SYNC_INTERVAL_HOURS_KEY, "lots")
    set_workspace_setting(db_session, TEST_WORKSPACE_ID, SYNC_LAST_RUN_KEY, "yesterday-ish")
    db_session.commit()
    s = load_sync_schedule(db_session, TEST_WORKSPACE_ID)
    assert s == {"mode": "daily", "daily_time": "02:00",
                 "interval_hours": 6, "last_run": None}


def test_load_schedule_reads_valid_values(db_session):
    set_workspace_setting(db_session, TEST_WORKSPACE_ID, SYNC_MODE_KEY, "interval")
    set_workspace_setting(db_session, TEST_WORKSPACE_ID, SYNC_DAILY_TIME_KEY, "04:30")
    set_workspace_setting(db_session, TEST_WORKSPACE_ID, SYNC_INTERVAL_HOURS_KEY, "12")
    db_session.commit()
    s = load_sync_schedule(db_session, TEST_WORKSPACE_ID)
    assert (s["mode"], s["daily_time"], s["interval_hours"]) == ("interval", "04:30", 12)


def test_mark_sync_ran_roundtrip(db_session):
    when = datetime(2026, 7, 13, 0, 5, tzinfo=timezone.utc)
    mark_sync_ran(db_session, TEST_WORKSPACE_ID, when)
    assert load_sync_schedule(db_session, TEST_WORKSPACE_ID)["last_run"] == when


def test_load_schedule_treats_naive_last_run_as_utc(db_session):
    set_workspace_setting(db_session, TEST_WORKSPACE_ID, SYNC_LAST_RUN_KEY, "2026-07-13T00:05:00")
    db_session.commit()
    assert load_sync_schedule(db_session, TEST_WORKSPACE_ID)["last_run"] == \
        datetime(2026, 7, 13, 0, 5, tzinfo=timezone.utc)


def test_schedule_is_isolated_per_workspace(db_session):
    from uuid import uuid4
    from models import Workspace

    other_workspace_id = uuid4()
    db_session.add(Workspace(id=other_workspace_id, name="Other workspace"))
    db_session.flush()

    set_workspace_setting(db_session, TEST_WORKSPACE_ID, SYNC_MODE_KEY, "interval")
    set_workspace_setting(db_session, other_workspace_id, SYNC_MODE_KEY, "daily")
    db_session.commit()

    assert load_sync_schedule(db_session, TEST_WORKSPACE_ID)["mode"] == "interval"
    assert load_sync_schedule(db_session, other_workspace_id)["mode"] == "daily"


# -------- autosync_tick -------------------------------------------------------

from jobs import autosync_tick


def test_tick_skips_when_not_due(db_session):
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    mark_sync_ran(db_session, TEST_WORKSPACE_ID, now - timedelta(hours=1))  # ran after today's 02:00 boundary
    with patch("jobs.broker_autosync_pass", new=AsyncMock()) as p:
        out = _run(autosync_tick(db_session, TEST_WORKSPACE_ID, now=now))
    assert out == []
    p.assert_not_awaited()
    # last_run untouched
    assert load_sync_schedule(db_session, TEST_WORKSPACE_ID)["last_run"] == now - timedelta(hours=1)


def test_tick_runs_pass_and_marks_ran_when_due(db_session):
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    mark_sync_ran(db_session, TEST_WORKSPACE_ID, now - timedelta(days=1))
    results = [{"portfolio_id": 1, "broker": "trading212", "ok": True, "imported": 2}]
    with patch("jobs.broker_autosync_pass", new=AsyncMock(return_value=results)) as p:
        out = _run(autosync_tick(db_session, TEST_WORKSPACE_ID, now=now))
    p.assert_awaited_once()
    assert out == results
    assert load_sync_schedule(db_session, TEST_WORKSPACE_ID)["last_run"] == now


def test_tick_marks_ran_even_when_no_connections(db_session):
    # An empty pass still consumes the boundary — no minute-by-minute retries.
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    with patch("jobs.broker_autosync_pass", new=AsyncMock(return_value=[])):
        out = _run(autosync_tick(db_session, TEST_WORKSPACE_ID, now=now))
    assert out == []
    assert load_sync_schedule(db_session, TEST_WORKSPACE_ID)["last_run"] == now


def test_tick_does_not_advance_last_run_when_pass_raises(db_session):
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    stamped = now - timedelta(days=1)
    mark_sync_ran(db_session, TEST_WORKSPACE_ID, stamped)
    with patch("jobs.broker_autosync_pass", new=AsyncMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(RuntimeError):
            _run(autosync_tick(db_session, TEST_WORKSPACE_ID, now=now))
    assert load_sync_schedule(db_session, TEST_WORKSPACE_ID)["last_run"] == stamped
