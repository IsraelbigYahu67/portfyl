"""Background job passes, driven by the periodic pollers in main.py.

Each pass is a self-contained coroutine that takes a DB session and returns a
summary list (empty when nothing happened) — the same shape the price-alert
`run_check` uses, so main.py can run them all through one generic loop and the
tests can drive them synchronously with `asyncio.run`.

Three passes live here:

* :func:`autosync_tick` — the minutely scheduler gate around
  ``broker_autosync_pass``: reads the configured schedule (daily at HH:MM in
  the local timezone, or every N hours) from the AppSetting table and runs
  the pass only when due, persisting a last-run stamp so restarts and
  downtime catch up instead of double- or never-running.
* :func:`broker_autosync_pass` — syncs every broker connection whose
  ``auto_sync`` flag is on (Trading 212 and IBKR), and announces imports on the
  portfolio's Discord webhook when ``notify_trades`` is enabled. One failing
  connection never blocks the others.
* :func:`dividend_exdate_pass` — for every portfolio whose Discord webhook has
  ``notify_dividends`` on, looks up upcoming ex-dividend dates for open
  holdings and sends one digest per portfolio. A ``DividendNotification`` row
  per (portfolio, ticker, ex_date) guarantees each dividend is announced once,
  across ticks and restarts.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app_settings import get_setting, set_setting
from models import BrokerConnection, DiscordWebhook, DividendNotification, Transaction
from routers.discord import send_discord_notification

log = logging.getLogger("portfyl.jobs")

DIVIDEND_COLOR = 0x8B5CF6  # violet — matches the TTM/dividend accents in the UI
SYNC_COLOR = 0x059669      # green — same as trade notifications


# -------- Sync schedule ------------------------------------------------------
# The autosync poller in main.py ticks every minute and asks sync_due() whether
# the configured schedule (Settings -> Auto-sync schedule) says it's time.
# Config lives in the AppSetting table under these keys; timestamps are aware
# UTC; "daily" boundaries are computed in SYNC's local timezone.

SYNC_MODE_KEY = "broker_sync_mode"                  # "daily" | "interval"
SYNC_DAILY_TIME_KEY = "broker_sync_daily_time"      # "HH:MM" 24h local time
SYNC_INTERVAL_HOURS_KEY = "broker_sync_interval_hours"
SYNC_LAST_RUN_KEY = "broker_sync_last_run"          # ISO-8601 UTC

DEFAULT_SYNC_MODE = "daily"
DEFAULT_SYNC_DAILY_TIME = "02:00"
DEFAULT_SYNC_INTERVAL_HOURS = 6


def _daily_boundary(local_now: datetime, daily_time: str) -> datetime:
    """Most recent occurrence of `daily_time` at or before `local_now`, as an
    aware datetime in local tz. On DST spring-forward days a nonexistent wall
    time resolves via fold=0 (shifted forward), so the boundary still exists
    exactly once per day."""
    hh, mm = (int(p) for p in daily_time.split(":"))
    boundary = local_now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if boundary > local_now:
        boundary -= timedelta(days=1)
    return boundary


def sync_due(now: datetime, mode: str, daily_time: str, interval_hours: int,
             last_run: datetime | None, tz) -> bool:
    """Is a broker sync due? `now`/`last_run` are aware UTC datetimes.
    daily: due when the most recent daily_time boundary (in tz) hasn't been
    run yet — which is also the catch-up rule after downtime.
    interval: due when interval_hours have elapsed since last_run."""
    if last_run is None:
        return True
    if mode == "interval":
        return now - last_run >= timedelta(hours=interval_hours)
    boundary = _daily_boundary(now.astimezone(tz), daily_time)
    return last_run < boundary.astimezone(timezone.utc)


def next_sync_run(now: datetime, mode: str, daily_time: str, interval_hours: int,
                  last_run: datetime | None, tz) -> datetime | None:
    """Next scheduled run as aware UTC, for display. None = due right now
    (the poller will run it within a minute)."""
    if sync_due(now, mode, daily_time, interval_hours, last_run, tz):
        return None
    if mode == "interval":
        return last_run + timedelta(hours=interval_hours)
    nxt = _daily_boundary(now.astimezone(tz), daily_time) + timedelta(days=1)
    return nxt.astimezone(timezone.utc)


_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def sync_timezone() -> ZoneInfo:
    """Schedule timezone: BROKER_SYNC_TIMEZONE env var, else Europe/Prague.
    A bad env value falls back rather than killing the poller."""
    name = os.environ.get("BROKER_SYNC_TIMEZONE", "Europe/Prague")
    try:
        return ZoneInfo(name)
    except Exception:
        return ZoneInfo("Europe/Prague")


def load_sync_schedule(db: Session) -> dict:
    """Schedule config from AppSetting rows; anything missing or invalid
    silently falls back to the defaults (the poller must never crash on a
    hand-edited row)."""
    mode = get_setting(db, SYNC_MODE_KEY)
    if mode not in ("daily", "interval"):
        mode = DEFAULT_SYNC_MODE

    daily_time = get_setting(db, SYNC_DAILY_TIME_KEY) or DEFAULT_SYNC_DAILY_TIME
    if not _TIME_RE.match(daily_time):
        daily_time = DEFAULT_SYNC_DAILY_TIME

    raw_hours = get_setting(db, SYNC_INTERVAL_HOURS_KEY)
    try:
        interval_hours = int(raw_hours) if raw_hours else DEFAULT_SYNC_INTERVAL_HOURS
    except ValueError:
        interval_hours = DEFAULT_SYNC_INTERVAL_HOURS
    interval_hours = max(1, min(interval_hours, 168))

    last_run = None
    raw_last = get_setting(db, SYNC_LAST_RUN_KEY)
    if raw_last:
        try:
            last_run = datetime.fromisoformat(raw_last)
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)
        except ValueError:
            last_run = None

    return {"mode": mode, "daily_time": daily_time,
            "interval_hours": interval_hours, "last_run": last_run}


def mark_sync_ran(db: Session, when: datetime) -> None:
    set_setting(db, SYNC_LAST_RUN_KEY, when.isoformat())
    db.commit()


# -------- Broker auto-sync --------------------------------------------------

async def broker_autosync_pass(db: Session) -> list[dict]:
    """Sync every connection with auto_sync enabled. Returns one summary dict
    per attempted connection ({portfolio_id, broker, ok, imported | error})."""
    # Imported lazily: broker/ibkr import fx, market_data, httpx setup, etc.,
    # and jobs must stay importable in tests without that whole chain loading
    # at module import time.
    from routers.broker import sync_transactions
    from routers.ibkr import _run_ibkr_sync

    conns = db.query(BrokerConnection).filter(BrokerConnection.auto_sync == True).all()  # noqa: E712
    results: list[dict] = []
    for conn in conns:
        summary = {"portfolio_id": conn.portfolio_id, "broker": conn.broker, "ok": True}
        try:
            if conn.broker == "trading212":
                # sync_transactions is blocking (paginated httpx + yfinance
                # split lookups) — run it in a worker thread to keep the event
                # loop free, like alerts.run_check does for get_infos.
                r = await asyncio.to_thread(
                    sync_transactions, db, conn.portfolio_id, conn.owner_id or "default")
                summary["imported"] = r.get("total_imported", 0)
                detail = (f"{r.get('imported_orders', 0)} order(s), "
                          f"{r.get('imported_dividends', 0)} dividend(s)")
            elif conn.broker == "ibkr":
                r = await _run_ibkr_sync(db, conn.portfolio_id, conn.owner_id or "default")
                summary["imported"] = r.get("imported", 0)
                detail = f"{r.get('imported', 0)} trade(s)"
            else:
                continue  # unknown broker — nothing to do
        except Exception as e:
            db.rollback()
            summary.update(ok=False, error=str(e))
            log.warning("auto-sync failed for portfolio %s (%s): %s",
                        conn.portfolio_id, conn.broker, e)
            results.append(summary)
            continue

        if summary.get("imported"):
            hook = (db.query(DiscordWebhook)
                      .filter(DiscordWebhook.portfolio_id == conn.portfolio_id)
                      .first())
            if hook and hook.notify_trades:
                await send_discord_notification(
                    db, conn.portfolio_id,
                    f"🔄 Auto-sync: {summary['imported']} new transaction(s)",
                    f"{conn.broker} auto-sync imported {detail}.",
                    color=SYNC_COLOR,
                )
        results.append(summary)
    return results


async def autosync_tick(db: Session, now: datetime | None = None) -> list[dict]:
    """One poller tick: run broker_autosync_pass iff the configured schedule
    says a sync is due, then persist the run timestamp. Same (db) -> list shape
    as the other passes so main.py's _periodic_loop drives it directly.

    If the pass raises, last_run is NOT advanced — the next tick retries
    (per-connection failures are already contained inside the pass, so a
    whole-pass exception means something systemic like a dead DB)."""
    now = now or datetime.now(timezone.utc)
    s = load_sync_schedule(db)
    if not sync_due(now, s["mode"], s["daily_time"], s["interval_hours"],
                    s["last_run"], sync_timezone()):
        return []
    results = await broker_autosync_pass(db)
    mark_sync_ran(db, now)
    return results


# -------- Dividend ex-date notifications ------------------------------------

def _upcoming_dividends(db: Session, pid: int, today: date, lead_days: int) -> list[dict]:
    """Open holdings of `pid` whose next ex-date falls within [today, today+lead]."""
    # Lazy imports for the same reason as above (portfolio pulls market_data).
    from routers.dividend_calendar import _next_dividend_info
    from routers.portfolio import _build_holdings

    txns = (db.query(Transaction)
              .filter(Transaction.portfolio_id == pid)
              .order_by(Transaction.date)
              .all())
    if not txns:
        return []
    holdings = _build_holdings(txns)

    horizon = today + timedelta(days=lead_days)
    upcoming: list[dict] = []
    for ticker in sorted(holdings.keys()):
        info = _next_dividend_info(ticker)
        ex_raw = info.get("ex_date")
        if not ex_raw:
            continue
        try:
            ex = date.fromisoformat(ex_raw)
        except (TypeError, ValueError):
            continue
        if not (today <= ex <= horizon):
            continue
        shares = holdings[ticker].get("shares") or 0
        amount = info.get("amount_per_share")
        upcoming.append({
            "ticker": ticker,
            "ex_date": ex,
            "amount_per_share": amount,
            "shares": shares,
            "est_payment": round(shares * amount, 2) if amount else None,
        })
    return upcoming


async def dividend_exdate_pass(db: Session, today: date | None = None,
                               lead_days: int = 3) -> list[dict]:
    """Announce upcoming ex-dividend dates on each portfolio's Discord webhook.
    Returns the items announced this pass (empty when everything was already
    announced or nothing is upcoming)."""
    today = today or date.today()
    hooks = db.query(DiscordWebhook).filter(DiscordWebhook.notify_dividends == True).all()  # noqa: E712

    announced: list[dict] = []
    for hook in hooks:
        pid = hook.portfolio_id
        try:
            # Blocking yfinance I/O per holding — keep it off the event loop.
            upcoming = await asyncio.to_thread(_upcoming_dividends, db, pid, today, lead_days)
        except Exception as e:
            log.warning("dividend check failed for portfolio %s: %s", pid, e)
            continue

        fresh = []
        for item in upcoming:
            dup = (db.query(DividendNotification)
                     .filter(DividendNotification.portfolio_id == pid,
                             DividendNotification.ticker == item["ticker"],
                             DividendNotification.ex_date == item["ex_date"])
                     .first())
            if not dup:
                fresh.append(item)
        if not fresh:
            continue

        lines = []
        for item in fresh:
            per_share = (f" — ${item['amount_per_share']:,.4g}/sh" if item["amount_per_share"] else "")
            est = (f" (≈ ${item['est_payment']:,.2f} on {item['shares']:g} sh)"
                   if item["est_payment"] else "")
            lines.append(f"**{item['ticker']}** ex-dividend **{item['ex_date'].isoformat()}**{per_share}{est}")

        delivered = await send_discord_notification(
            db, pid,
            f"📅 {len(fresh)} upcoming ex-dividend date(s)",
            "\n".join(lines),
            color=DIVIDEND_COLOR,
        )
        if delivered is False:
            # Delivery failed: don't consume the one-shot dedup rows — the
            # next tick retries, otherwise the notification is lost forever.
            log.warning("dividend notification delivery failed for portfolio %s; will retry", pid)
            continue
        for item in fresh:
            db.add(DividendNotification(portfolio_id=pid, ticker=item["ticker"],
                                        ex_date=item["ex_date"]))
        db.commit()
        announced.extend({**i, "portfolio_id": pid, "ex_date": i["ex_date"].isoformat()} for i in fresh)
    return announced
