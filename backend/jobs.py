"""Background job passes, driven by the periodic pollers in main.py.

Each per-workspace pass is a self-contained coroutine that takes a DB session
plus an explicit `workspace_id` and returns a summary list (empty when
nothing happened) — the same shape the price-alert `run_check` uses, so
tests can drive them synchronously with `asyncio.run`.

Three per-workspace passes live here:

* :func:`autosync_tick` — the minutely scheduler gate around
  ``broker_autosync_pass``: reads the configured schedule (daily at HH:MM in
  the local timezone, or every N hours) from that workspace's settings and
  runs the pass only when due, persisting a last-run stamp so restarts and
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

None of the three ever scans across workspaces on their own -- each is a pure
function of the `workspace_id` it's given, application-filtering every query
by it. The actual customer-wide sweep the in-process pollers need is an
*explicit* iteration owned by this module: :func:`autosync_all_workspaces`,
:func:`dividend_notify_all_workspaces`, and :func:`alert_check_all_workspaces`
enumerate every active workspace (via :func:`_active_workspace_ids`, whose own
docstring covers how it does that under forced RLS) and reset the RLS context
to it before invoking that workspace's tenant work, so a background job
session (which, like a request session, runs under the RLS-forced
`portfyl_runtime` role) can never see -- let alone act on -- another
workspace's rows.

`set_config(..., true)` (the RLS context set by :func:`_set_job_workspace_context`)
is transaction-local: it reverts the instant the current transaction commits
or rolls back. `broker_autosync_pass` and `dividend_exdate_pass` both commit
more than once *within* a single workspace's pass (once per broker connection
/ once per Discord webhook, respectively) -- every DB operation after one of
those internal commits, for the remainder of that same workspace's pass, must
reassert the context via :func:`_set_job_workspace_context` before touching
the database again. Both passes (and `mark_sync_ran`, called after
`broker_autosync_pass` returns) do this at each such site; when adding a new
commit inside either pass's per-item loop, reassert the context immediately
afterward too.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import pandas as pd
import yfinance as yf
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session

from app_settings import get_workspace_setting, set_workspace_setting
from models import (
    BrokerConnection,
    BrokerPosition,
    BrokerSyncRun,
    DiscordWebhook,
    DividendNotification,
    JobRun,
    Portfolio,
    Transaction,
    Workspace,
)
from routers.discord import send_discord_notification
from ticker_map import yf_symbol

log = logging.getLogger("portfyl.jobs")

DIVIDEND_COLOR = 0x8B5CF6  # violet — matches the TTM/dividend accents in the UI
SYNC_COLOR = 0x059669      # green — same as trade notifications

# Dead-letter threshold: a connection failing every pass this many times in
# a row stops retrying silently -- broker_autosync_pass turns auto_sync off
# and needs_attention on instead (see models.BrokerConnection).
BROKER_AUTOSYNC_FAILURE_THRESHOLD = int(os.environ.get("BROKER_AUTOSYNC_FAILURE_THRESHOLD", 5))

RECURRING_JOB_NAMES = (
    "alerts",
    "autosync",
    "dividends",
    "rate_limit_cleanup",
    "account_deletion_cleanup",
    "broker_backfill",
)

# broker_backfill's per-tick budget: how many due BrokerSyncRuns one pass
# claims across a workspace. Deliberately small -- each run's own
# advance_run bound (t212_sync.DEFAULT_MAX_PAGES_PER_STREAM) already limits
# the work per run, and a minutely job has the next tick to keep going.
BROKER_BACKFILL_MAX_RUNS_PER_WORKSPACE = 5

# One pass keeps advancing a run (each step is at most
# t212_sync.DEFAULT_MAX_PAGES_PER_STREAM pages per stream) until it finalizes,
# is rate limited, loses its lease, hits the step cap or the shared time
# budget. Without this a 7-page history needed three minutely ticks.
BROKER_BACKFILL_DRAIN_SECONDS = 40.0
BROKER_BACKFILL_MAX_STEPS_PER_RUN = 12

# A history run failing with a transient error (network, timeout, 5xx, DB) is
# retried with exponential backoff: 1, 2, 4 ... minutes, capped at an hour. The
# BROKER_BACKFILL_MAX_RETRIES-th consecutive failure stops the run (failed).
# retry_count resets after any step that completes without an exception.
BROKER_BACKFILL_MAX_RETRIES = int(os.environ.get("BROKER_BACKFILL_MAX_RETRIES", 8))
BROKER_BACKFILL_BACKOFF_BASE_SECONDS = 60
BROKER_BACKFILL_BACKOFF_MAX_SECONDS = 3600


def backfill_backoff_seconds(retry_count: int) -> int:
    """How long a run with `retry_count` consecutive failures stays unclaimed."""
    if retry_count <= 0:
        return 0
    return min(
        BROKER_BACKFILL_BACKOFF_MAX_SECONDS,
        BROKER_BACKFILL_BACKOFF_BASE_SECONDS * 2 ** min(retry_count - 1, 20),
    )


def mark_job_succeeded(
    db: Session,
    job_name: str,
    when: datetime | None = None,
) -> JobRun:
    """Persist the last fully successful pass for operational health checks.

    The caller owns the commit.  Failed passes never call this function, so a
    stale timestamp reliably means the scheduler or the job body needs
    attention rather than merely that an invocation was attempted.
    """
    if job_name not in RECURRING_JOB_NAMES:
        raise ValueError(f"Unknown recurring job: {job_name}")
    row = db.scalar(select(JobRun).where(JobRun.job_name == job_name))
    succeeded_at = when or datetime.now(timezone.utc)
    if row is None:
        row = JobRun(job_name=job_name, last_success_at=succeeded_at)
        db.add(row)
    else:
        row.last_success_at = succeeded_at
    db.flush()
    return row


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
    time resolves via fold=0 (shifted forward): the wall-clock comparison
    above still picks a boundary, but its UTC instant can land in the future
    relative to `local_now` (e.g. "02:30" -> 01:30 UTC while it's only 01:05
    UTC) — callers must not treat that boundary as already passed without
    checking the actual UTC instant (see sync_due's `<= now` guard)."""
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
    boundary_utc = _daily_boundary(now.astimezone(tz), daily_time).astimezone(timezone.utc)
    # A daily_time inside the DST spring-forward gap converts to a UTC instant
    # that can still be in the future ("02:30" -> 01:30 UTC while now is 01:05);
    # without the `<= now` guard the sync would re-fire every tick until then.
    return boundary_utc <= now and last_run < boundary_utc


def next_sync_run(now: datetime, mode: str, daily_time: str, interval_hours: int,
                  last_run: datetime | None, tz) -> datetime | None:
    """Next scheduled run as aware UTC, for display. None = due right now
    (the poller will run it within a minute)."""
    if sync_due(now, mode, daily_time, interval_hours, last_run, tz):
        return None
    if mode == "interval":
        return last_run + timedelta(hours=interval_hours)
    # Display-only: for a daily_time inside the spring-forward gap this shows
    # tomorrow's boundary while the actual (deferred) fire still happens later
    # today, once the gap's UTC instant arrives — a one-hour, once-a-year cosmetic
    # mismatch, not a correctness issue (sync_due is what gates the real run).
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


def load_sync_schedule(db: Session, workspace_id: UUID) -> dict:
    """This workspace's schedule config; anything missing or invalid silently
    falls back to the defaults (the poller must never crash on a hand-edited
    row)."""
    mode = get_workspace_setting(db, workspace_id, SYNC_MODE_KEY)
    if mode not in ("daily", "interval"):
        mode = DEFAULT_SYNC_MODE

    daily_time = get_workspace_setting(db, workspace_id, SYNC_DAILY_TIME_KEY) or DEFAULT_SYNC_DAILY_TIME
    if not _TIME_RE.match(daily_time):
        daily_time = DEFAULT_SYNC_DAILY_TIME

    raw_hours = get_workspace_setting(db, workspace_id, SYNC_INTERVAL_HOURS_KEY)
    try:
        interval_hours = int(raw_hours) if raw_hours else DEFAULT_SYNC_INTERVAL_HOURS
    except ValueError:
        interval_hours = DEFAULT_SYNC_INTERVAL_HOURS
    interval_hours = max(1, min(interval_hours, 168))

    last_run = None
    raw_last = get_workspace_setting(db, workspace_id, SYNC_LAST_RUN_KEY)
    if raw_last:
        try:
            last_run = datetime.fromisoformat(raw_last)
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=timezone.utc)
        except ValueError:
            last_run = None

    return {"mode": mode, "daily_time": daily_time,
            "interval_hours": interval_hours, "last_run": last_run}


def mark_sync_ran(db: Session, workspace_id: UUID, when: datetime) -> None:
    # broker_autosync_pass (called by autosync_tick just before this) commits
    # -- and on a per-connection failure, rolls back -- one or more times
    # internally; either ends the transaction and drops the transaction-local
    # `portfyl.workspace_id` set for this workspace's pass. Reassert it here
    # so this upsert doesn't run RLS-context-less and fail its WITH CHECK.
    _set_job_workspace_context(db, workspace_id)
    set_workspace_setting(db, workspace_id, SYNC_LAST_RUN_KEY, when.isoformat())
    db.commit()


# -------- Broker auto-sync --------------------------------------------------

async def broker_autosync_pass(
    db: Session,
    workspace_id: UUID,
    max_connections: int | None = None,
) -> list[dict]:
    """Sync every connection in `workspace_id` with auto_sync enabled. Returns
    one summary dict per attempted connection
    ({portfolio_id, broker, ok, imported | error})."""
    # Imported lazily: broker/ibkr import fx, market_data, httpx setup, etc.,
    # and jobs must stay importable in tests without that whole chain loading
    # at module import time.
    from routers.broker import sync_transactions
    from routers.ibkr import _run_ibkr_sync
    from routers.etoro import etoro_sync

    all_connections = db.query(BrokerConnection).filter(
        BrokerConnection.workspace_id == workspace_id,
    ).order_by(BrokerConnection.created_at, BrokerConnection.id).all()
    if max_connections is not None:
        all_connections = all_connections[:max_connections]
    conns = [connection for connection in all_connections if connection.auto_sync]
    results: list[dict] = []
    for conn in conns:
        # sync_transactions/_run_ibkr_sync commit internally (and on failure,
        # this loop rolls back below) -- either ends the transaction and
        # drops the transaction-local `portfyl.workspace_id` set for this
        # pass. Reassert it at the top of every connection's iteration so a
        # prior connection's commit/rollback never leaves this one -- or the
        # Discord lookup further down in the same iteration -- running
        # RLS-context-less.
        _set_job_workspace_context(db, workspace_id)
        summary = {"portfolio_id": conn.portfolio_id, "broker": conn.broker, "ok": True}
        try:
            if conn.broker == "trading212":
                # sync_transactions is a route handler whose `portfolio`
                # parameter is normally filled by the require_portfolio
                # dependency; a job has no request, so resolve the authorized
                # Portfolio here -- explicitly filtered by this pass's
                # workspace -- and pass it positionally. The third parameter is
                # only the CSRF gate (`_context`), which does not apply to a
                # machine-driven pass.
                portfolio = db.query(Portfolio).filter(
                    Portfolio.workspace_id == workspace_id,
                    Portfolio.id == conn.portfolio_id,
                ).first()
                if portfolio is None:
                    continue  # dangling connection — nothing to sync
                # The foreground sync fetches only the current account
                # snapshot and creates/resumes a history run. It still uses
                # blocking httpx, so keep it off the event loop; the dedicated
                # broker_backfill pass advances the returned run later.
                r = await asyncio.to_thread(
                    sync_transactions, db, portfolio, None)
                snapshot = r.get("snapshot") or {}
                history = r.get("history") or {}
                summary.update(
                    imported=0,
                    snapshot_status=snapshot.get("status"),
                    history_status=history.get("status"),
                    history_run_id=history.get("run_id"),
                )
                detail = "current snapshot"
            elif conn.broker == "ibkr":
                r = await _run_ibkr_sync(db, workspace_id, conn.portfolio_id)
                ledger = r.get("ledger") or {}
                ledger_imported = ledger.get("imported", 0)
                summary["imported"] = r.get("imported", 0) + ledger_imported
                detail = f"{r.get('imported', 0)} option trade(s)"
                if ledger_imported:
                    detail += f" and {ledger_imported} stock/cash transaction(s)"
                if ledger.get("status") == "needs_review":
                    # The sync succeeded but flagged the statement for the
                    # user; keep that flag (and its message) below.
                    summary["needs_review"] = True
            elif conn.broker == "etoro":
                # A plain def with a blocking httpx client: keep it off the
                # event loop, like the Trading 212 snapshot above.
                r = await asyncio.to_thread(
                    etoro_sync, db, workspace_id, conn.portfolio_id)
                summary["imported"] = r.get("imported", 0)
                detail = f"{summary['imported']} transaction(s)"
                if r.get("status") == "needs_review":
                    summary["needs_review"] = True
            else:
                continue  # unknown broker — nothing to do
        except Exception as e:
            db.rollback()
            # rollback expires `conn` -- reassert the RLS context before
            # touching its attributes again, same discipline as every other
            # post-commit/rollback access in this module.
            _set_job_workspace_context(db, workspace_id)
            summary.update(ok=False, error=str(e))
            log.warning("auto-sync failed for portfolio %s (%s): %s",
                        conn.portfolio_id, conn.broker, e)
            conn.consecutive_failures = (conn.consecutive_failures or 0) + 1
            conn.last_error = str(e)[:500]
            if conn.consecutive_failures >= BROKER_AUTOSYNC_FAILURE_THRESHOLD:
                conn.needs_attention = True
                conn.auto_sync = False
                log.warning(
                    "auto-sync disabled for portfolio %s (%s) after %d consecutive failures",
                    conn.portfolio_id, conn.broker, conn.consecutive_failures,
                )
            db.commit()
            results.append(summary)
            continue

        # The sync above committed internally, dropping the context set at
        # the top of this iteration -- restore it before the Discord lookup.
        _set_job_workspace_context(db, workspace_id)
        if summary.get("needs_review"):
            conn.consecutive_failures = 0
        elif conn.consecutive_failures or conn.needs_attention:
            conn.consecutive_failures = 0
            conn.needs_attention = False
            conn.last_error = None
        if summary.get("imported"):
            hook = (db.query(DiscordWebhook)
                      .filter(DiscordWebhook.workspace_id == workspace_id,
                              DiscordWebhook.portfolio_id == conn.portfolio_id)
                      .first())
            if hook and hook.notify_trades:
                await send_discord_notification(
                    db, workspace_id, conn.portfolio_id,
                    f"🔄 Auto-sync: {summary['imported']} new transaction(s)",
                    f"{conn.broker} auto-sync imported {detail}.",
                    color=SYNC_COLOR,
                )
        results.append(summary)
    return results


# -------- Broker history backfill (T212 snapshot-first sync, Task 3) -------
# Distinct from broker_autosync_pass above: this drains BrokerSyncRun rows
# that already exist (created by routers.broker.sync_transactions via
# t212_sync.claim_or_create_run), independent of auto_sync and the user's
# sync schedule -- a manually-triggered initial backfill keeps progressing
# even with auto_sync off and no schedule due (plan §5.4), and this job never
# creates a run itself.

async def _advance_until_blocked(
    db: Session, run, workspace_id: UUID, base: str, api_headers: dict, *, deadline: float,
):
    """Advance `run` repeatedly. Only a step that ended `fetching` (neither
    rate limited nor finished) is followed by another one; the run is re-claimed
    each time because advance_run releases its lease. Returns the last step's
    state with the staged counts of all steps summed."""
    import t212_sync

    run_id = run.id
    lease_token = run.lease_token
    totals = {"orders": 0, "dividends": 0, "cash": 0}
    steps = 0
    while True:
        result = await asyncio.to_thread(
            t212_sync.advance_run,
            db, run, base, api_headers,
            lease_token=lease_token,
            reassert_context=lambda: _set_job_workspace_context(db, workspace_id),
        )
        steps += 1
        totals["orders"] += result.orders_staged
        totals["dividends"] += result.dividends_staged
        totals["cash"] += result.cash_staged
        if (
            result.state != "fetching"
            or steps >= BROKER_BACKFILL_MAX_STEPS_PER_RUN
            or time.monotonic() >= deadline
        ):
            break
        _set_job_workspace_context(db, workspace_id)
        reclaimed = t212_sync.claim_lease(db, run_id, workspace_id)
        if reclaimed is None:
            break  # another worker took the run; it carries on from the checkpoint
        run, lease_token = reclaimed, reclaimed.lease_token
    return replace(
        result,
        orders_staged=totals["orders"],
        dividends_staged=totals["dividends"],
        cash_staged=totals["cash"],
    )


def _in_backoff(retry_count: int | None, updated_at: datetime | None, now: datetime) -> bool:
    delay = backfill_backoff_seconds(retry_count or 0)
    if not delay or updated_at is None:
        return False
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return now < updated_at + timedelta(seconds=delay)


def _reload_run(db: Session, workspace_id: UUID, run_id: int):
    """Re-read a run after a rollback/commit dropped the RLS context."""
    _set_job_workspace_context(db, workspace_id)
    return db.query(BrokerSyncRun).filter(
        BrokerSyncRun.workspace_id == workspace_id, BrokerSyncRun.id == run_id,
    ).first()


def _fail_run_credentials(db: Session, workspace_id: UUID, run_id: int) -> None:
    """Trading 212 refused the key: end the run for good and tell the user, via
    the connection's needs_attention/last_error, to reconnect."""
    import t212_sync

    run = _reload_run(db, workspace_id, run_id)
    if run is None:
        return
    run.state = "failed"
    run.last_error = t212_sync.HISTORY_CREDENTIALS_ERROR
    run.lease_token = None
    run.lease_expires_at = None
    connection = db.query(BrokerConnection).filter(
        BrokerConnection.workspace_id == workspace_id,
        BrokerConnection.id == run.connection_id,
    ).first()
    if connection is not None:
        connection.needs_attention = True
        connection.last_error = t212_sync.CONNECTION_CREDENTIALS_ERROR
    db.commit()


def _park_run_for_review(
    db: Session, workspace_id: UUID, run_id: int, exc: ValueError,
) -> None:
    """finalize_run raised a ValueError on the staged data. Re-running would
    fail the same way, so park the run in needs_review (history_run_decision
    then blocks new automatic runs until an explicit retry). review_details
    holds the stream, date and error type only -- never the raw payload."""
    import t212_sync

    run = _reload_run(db, workspace_id, run_id)
    if run is None:
        return
    when = getattr(exc, "when", None)
    run.state = "needs_review"
    run.last_error = t212_sync.HISTORY_DATA_ERROR
    run.review_details = [{
        "fill_type": t212_sync.REVIEW_INVALID_DATA,
        "ticker": None,
        "date": when.date().isoformat() if when else None,
        "stream": getattr(exc, "stream", None),
        "error_type": getattr(exc, "error_type", type(exc).__name__),
    }]
    run.lease_token = None
    run.lease_expires_at = None
    db.commit()


def _record_transient_failure(db: Session, workspace_id: UUID, run_id: int) -> str:
    """Count a transient failure; stop the run once retries are exhausted.
    Returns the public error message."""
    import t212_sync

    run = _reload_run(db, workspace_id, run_id)
    if run is None:
        return t212_sync.HISTORY_RETRY_ERROR
    run.retry_count = (run.retry_count or 0) + 1
    if run.retry_count >= BROKER_BACKFILL_MAX_RETRIES:
        run.state = "failed"
        run.last_error = t212_sync.HISTORY_RETRY_EXHAUSTED_ERROR
        run.lease_token = None
        run.lease_expires_at = None
    else:
        run.last_error = t212_sync.HISTORY_RETRY_ERROR
    error = run.last_error
    db.commit()
    return error


def _reset_retry_count(db: Session, workspace_id: UUID, run_id: int) -> None:
    _set_job_workspace_context(db, workspace_id)
    db.execute(
        update(BrokerSyncRun)
        .where(BrokerSyncRun.workspace_id == workspace_id, BrokerSyncRun.id == run_id)
        .values(retry_count=0)
    )
    db.commit()


async def broker_backfill_pass(
    db: Session,
    workspace_id: UUID,
    *,
    max_runs: int = BROKER_BACKFILL_MAX_RUNS_PER_WORKSPACE,
    drain_seconds: float = BROKER_BACKFILL_DRAIN_SECONDS,
    deadline: float | None = None,
) -> list[dict]:
    """Claim and advance up to `max_runs` due BrokerSyncRuns in this
    workspace. A run whose lease is currently held by another live worker
    (t212_sync.claim_lease returns None) is skipped this tick, not retried
    inline -- the next tick picks it up once the lease expires or the other
    worker finishes."""
    import t212_sync

    # Callers (broker_backfill_all_workspaces below, or a test driving this
    # pass directly) may hand this a session with no RLS context set yet --
    # this query must never run context-less under forced RLS (see this
    # module's docstring on why every per-workspace pass reasserts context
    # at each site that could run after a prior commit dropped it).
    _set_job_workspace_context(db, workspace_id)
    now = datetime.now(timezone.utc)
    if deadline is None:
        deadline = time.monotonic() + drain_seconds
    # A run in its retry backoff window is filtered out here, before
    # claim_lease: claiming bumps updated_at, which is the backoff's clock.
    # The filter runs before the max_runs cut so waiting runs take no slot.
    candidates = db.execute(
        select(BrokerSyncRun.id, BrokerSyncRun.retry_count, BrokerSyncRun.updated_at)
        .where(
            BrokerSyncRun.workspace_id == workspace_id,
            BrokerSyncRun.state.in_(("pending", "fetching", "waiting_rate_limit", "finalizing")),
        )
        .order_by(BrokerSyncRun.created_at)
    ).all()
    due_run_ids = [
        run_id for run_id, retry_count, updated_at in candidates
        if not _in_backoff(retry_count, updated_at, now)
    ][:max_runs]

    results: list[dict] = []
    for run_id in due_run_ids:
        # claim_lease's FOR UPDATE SKIP LOCKED (and every query below) needs
        # this workspace's RLS context freshly set -- a prior iteration's
        # advance_run call committed (possibly many times), each of which
        # drops the transaction-local context.
        _set_job_workspace_context(db, workspace_id)
        run = t212_sync.claim_lease(db, run_id, workspace_id)
        if run is None:
            continue  # leased by another live worker, or the run is gone

        if run.state == "waiting_rate_limit":
            reset_candidates = [
                r for r in (
                    run.orders_rate_limit_reset_at,
                    run.dividends_rate_limit_reset_at,
                    run.cash_rate_limit_reset_at,
                )
                if r is not None
            ]
            reset_at = max(reset_candidates) if reset_candidates else None
            if reset_at is not None:
                if reset_at.tzinfo is None:
                    reset_at = reset_at.replace(tzinfo=timezone.utc)
                if reset_at > now:
                    run.lease_token = None
                    run.lease_expires_at = None
                    db.commit()  # release the row lock without advancing
                    continue

        connection = db.query(BrokerConnection).filter(
            BrokerConnection.workspace_id == workspace_id,
            BrokerConnection.id == run.connection_id,
        ).first()
        if (
            connection is None
            or not run.account_fingerprint
            or run.account_fingerprint != connection.account_fingerprint
            or connection.credential_generation != run.credential_generation
        ):
            # The connection was disconnected, or credentials were rotated
            # after this run started -- a stale-generation worker must never
            # commit further progress under superseded credentials.
            # Read the public id before committing: the commit drops the
            # transaction-local RLS context, so a lazy reload of the expired
            # row would find nothing under forced RLS.
            cancelled_id = str(run.public_id)
            run.state = "cancelled"
            db.commit()
            results.append({"run_id": cancelled_id, "state": "cancelled"})
            continue

        portfolio = db.query(Portfolio).filter(
            Portfolio.workspace_id == workspace_id,
            Portfolio.id == run.portfolio_id,
        ).first()
        if (
            portfolio is None
            or portfolio.t212_account_fingerprint != run.account_fingerprint
        ):
            cancelled_id = str(run.public_id)  # before the commit; see above
            run.state = "cancelled"
            db.commit()
            results.append({"run_id": cancelled_id, "state": "cancelled"})
            continue

        base = t212_sync._t212_base(connection.environment or "live")
        api_headers = t212_sync._t212_headers(connection.api_key, connection.api_secret or "")
        lease_token = run.lease_token
        public_id = str(run.public_id)
        portfolio_public_id = str(portfolio.public_id)
        prior_retries = run.retry_count or 0
        try:
            if run.state == "finalizing":
                result = t212_sync.RunAdvanceResult(
                    state="finalizing",
                    orders_staged=0,
                    dividends_staged=0,
                    rate_limited_streams=(),
                )
            else:
                # advance_run is blocking (paginated httpx) -- run it in a worker
                # thread to keep the event loop free, like broker_autosync_pass
                # does for sync_transactions above.
                result = await _advance_until_blocked(
                    db, run, workspace_id, base, api_headers, deadline=deadline,
                )
            state = result.state
            if state == "finalizing":
                try:
                    finalized = await asyncio.to_thread(
                        t212_sync.finalize_run, db, run, portfolio,
                    )
                except ValueError as exc:
                    # Deterministic: the staged data itself cannot be imported.
                    db.rollback()
                    _park_run_for_review(db, workspace_id, run_id, exc)
                    # Same prefix as t212_sync's blocked-run line: the operator
                    # alert in deploy/monitoring-policies.json matches it.
                    when = getattr(exc, "when", None)
                    log.warning(
                        "T212 history needs review: run=%s portfolio=%s data error "
                        "%s in %s stream on %s",
                        public_id, portfolio_public_id,
                        getattr(exc, "error_type", type(exc).__name__),
                        getattr(exc, "stream", None) or "?",
                        when.date().isoformat() if when else "?",
                    )
                    results.append({
                        "run_id": public_id,
                        "state": "needs_review",
                        "error": t212_sync.HISTORY_DATA_ERROR,
                    })
                    continue
                state = "needs_review" if finalized.needs_review else "completed"
            if prior_retries:
                _reset_retry_count(db, workspace_id, run_id)
            results.append({
                "run_id": public_id,
                "state": state,
                "orders_staged": result.orders_staged,
                "dividends_staged": result.dividends_staged,
                "cash_staged": result.cash_staged,
                "rate_limited_streams": list(result.rate_limited_streams),
            })
        except Exception as e:
            db.rollback()
            if t212_sync.is_credentials_rejection(e):
                _fail_run_credentials(db, workspace_id, run_id)
                error = t212_sync.HISTORY_CREDENTIALS_ERROR
            else:
                error = _record_transient_failure(db, workspace_id, run_id)
            log.warning(
                "broker_backfill failed for run %s (%s)",
                public_id,
                type(e).__name__,
            )
            results.append({
                "run_id": public_id,
                "error": error,
            })
    return results


async def broker_backfill_all_workspaces(
    db: Session, *, drain_seconds: float = BROKER_BACKFILL_DRAIN_SECONDS,
) -> list[dict]:
    """Poller entry point for T212 history backfill: explicit per-workspace
    pass across every active workspace (see this module's docstring on why
    only functions in this section are allowed to iterate every tenant).
    One drain deadline is shared by every workspace: the cloud job runs them
    all in a single request that must finish within the scheduler deadline."""
    import backfill_trigger

    deadline = time.monotonic() + drain_seconds
    results: list[dict] = []
    next_due: datetime | None = None
    for workspace_id in _active_workspace_ids(db):
        _set_job_workspace_context(db, workspace_id)
        results.extend(await broker_backfill_pass(db, workspace_id, deadline=deadline))
        if backfill_trigger.enabled():
            _set_job_workspace_context(db, workspace_id)
            due = broker_backfill_next_due(db, workspace_id)
            if due is not None and (next_due is None or due < next_due):
                next_due = due
    if next_due is not None:
        # Cloud only (see backfill_trigger): wake this job again when the
        # earliest unfinished run is due instead of at the next hourly tick.
        db.commit()  # end the read transaction before the outbound call
        now = datetime.now(timezone.utc)
        at = max(next_due, now + timedelta(seconds=backfill_trigger.MIN_CONTINUATION_SECONDS))
        if at <= now + timedelta(seconds=backfill_trigger.MAX_CONTINUATION_SECONDS):
            await asyncio.to_thread(backfill_trigger.request_backfill, at=at)
    return results


def broker_backfill_next_due(
    db: Session, workspace_id: UUID, *, now: datetime | None = None,
) -> datetime | None:
    """When this workspace's earliest unfinished history run can next make
    progress: its latest rate-limit reset while waiting on Trading 212, the
    end of its retry backoff, otherwise `now`. None when no run is open.
    Mirrors the due checks in broker_backfill_pass."""
    now = now or datetime.now(timezone.utc)
    runs = db.execute(
        select(
            BrokerSyncRun.state,
            BrokerSyncRun.retry_count,
            BrokerSyncRun.updated_at,
            BrokerSyncRun.orders_rate_limit_reset_at,
            BrokerSyncRun.dividends_rate_limit_reset_at,
            BrokerSyncRun.cash_rate_limit_reset_at,
        ).where(
            BrokerSyncRun.workspace_id == workspace_id,
            BrokerSyncRun.state.in_(("pending", "fetching", "waiting_rate_limit", "finalizing")),
        )
    ).all()
    earliest: datetime | None = None
    for state, retry_count, updated_at, *resets in runs:
        due = now
        delay = backfill_backoff_seconds(retry_count or 0)
        if delay and updated_at is not None:
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            due = max(due, updated_at + timedelta(seconds=delay))
        if state == "waiting_rate_limit":
            resets = [r if r.tzinfo else r.replace(tzinfo=timezone.utc) for r in resets if r]
            if resets:
                due = max(due, max(resets))
        if earliest is None or due < earliest:
            earliest = due
    return earliest


async def autosync_tick(
    db: Session,
    workspace_id: UUID,
    now: datetime | None = None,
    minimum_interval_hours: int | None = None,
    max_connections: int | None = None,
) -> list[dict]:
    """One workspace's poller tick: run broker_autosync_pass iff that
    workspace's configured schedule says a sync is due, then persist the run
    timestamp for that workspace.

    If the pass raises, last_run is NOT advanced — the next tick retries
    (per-connection failures are already contained inside the pass, so a
    whole-pass exception means something systemic like a dead DB)."""
    now = now or datetime.now(timezone.utc)
    s = load_sync_schedule(db, workspace_id)
    if minimum_interval_hours is not None and s["mode"] == "interval":
        s["interval_hours"] = max(s["interval_hours"], minimum_interval_hours)
    if not sync_due(now, s["mode"], s["daily_time"], s["interval_hours"],
                    s["last_run"], sync_timezone()):
        return []
    if max_connections is None:
        results = await broker_autosync_pass(db, workspace_id)
    else:
        results = await broker_autosync_pass(
            db, workspace_id, max_connections=max_connections
        )
    mark_sync_ran(db, workspace_id, now)
    return results


def _next_dividend_info(symbol: str) -> dict[str, Any]:
    """Best-effort fetch of next dividend for a single ticker.

    Returns:
        ex_date:   expected next ex-dividend date (or last known)
        pay_date:  expected next pay date (or None)
        amount:    latest dividend per share
        frequency: 'monthly', 'quarterly', 'semi-annual', 'annual', or 'unknown'
        yield_pct: trailing dividend yield percent
    """
    try:
        stock = yf.Ticker(yf_symbol(symbol))
        info = stock.info or {}
    except Exception:
        return {"ticker": symbol, "ex_date": None, "amount": None, "error": "yfinance unavailable"}

    # yfinance dividend yield — >=0.2.44 returns percent directly
    div_yield = info.get("dividendYield")
    if div_yield is not None:
        try:
            div_yield = round(float(div_yield), 2)
        except (TypeError, ValueError):
            div_yield = None

    # Trailing annual dividend rate
    div_rate = info.get("dividendRate")
    if div_rate is not None:
        try:
            div_rate = round(float(div_rate), 2)
        except (TypeError, ValueError):
            div_rate = None

    # Pull the dividend history to find the most recent dividend and estimate
    # ex-date / pay-date for the next one.
    ex_date: date | None = None
    pay_date_val: date | None = None
    amount: float | None = None
    frequency = "unknown"

    try:
        hist = stock.dividends
        if hist is not None and not hist.empty:
            # hist index is the ex-date
            last_ex = hist.index[-1]
            amount = float(hist.iloc[-1])

            if hasattr(last_ex, "date"):
                ex_date = last_ex.date()
            elif hasattr(last_ex, "strftime"):
                ex_date = pd.Timestamp(last_ex).date()

            # Estimate frequency from the gap between the last two dividends
            if len(hist) >= 2:
                gap = (hist.index[-1] - hist.index[-2]).days
                if gap < 50:
                    frequency = "monthly"
                elif gap < 100:
                    frequency = "quarterly"
                elif gap < 250:
                    frequency = "semi-annual"
                else:
                    frequency = "annual"
            elif div_rate and amount and amount > 0:
                implied_payments = round(div_rate / amount)
                if implied_payments >= 10:
                    frequency = "monthly"
                elif implied_payments >= 3:
                    frequency = "quarterly"
                elif implied_payments >= 1:
                    frequency = "annual"

            # Estimate next ex-date: last ex-date + gap days
            if ex_date and len(hist) >= 2:
                gap = (hist.index[-1] - hist.index[-2]).days
                next_ex_est = ex_date + timedelta(days=gap)
                # Only show dates in the forward-looking window
                if next_ex_est > date.today():
                    ex_date = next_ex_est

            # Estimate pay date from calendar if available
            try:
                cal = stock.calendar
                if cal is not None:
                    if isinstance(cal, dict):
                        raw_pay = cal.get("Dividend Date")
                    elif isinstance(cal, pd.DataFrame) and not cal.empty:
                        cal_dict = cal.to_dict()
                        raw_pay = None
                        for key, col in cal_dict.items():
                            val = list(col.values())
                            if val and isinstance(val[0], (pd.Timestamp, pd.datetime)):
                                raw_pay = val[0]
                                break
                            elif val:
                                raw_pay = val[0]
                    else:
                        raw_pay = None
                    if raw_pay is not None:
                        pay_date_val = pd.Timestamp(raw_pay).date()
            except Exception:
                pass
    except Exception:
        pass

    # Fallback amount from yfinance rate if history is empty
    if amount is None and div_rate is not None:
        amount = round(div_rate / 4, 4) if frequency == "quarterly" else round(div_rate, 4)

    return {
        "ticker": symbol,
        "ex_date": ex_date.isoformat() if ex_date else None,
        "pay_date": pay_date_val.isoformat() if pay_date_val else None,
        "amount_per_share": round(amount, 4) if amount is not None else None,
        "frequency": frequency,
        "trailing_yield_pct": div_yield,
        "dividend_rate_annual": div_rate,
    }


# -------- Dividend ex-date notifications ------------------------------------

def _upcoming_dividends(db: Session, workspace_id: UUID, pid: int, today: date, lead_days: int) -> list[dict]:
    """Open holdings of `pid` whose next ex-date falls within [today, today+lead]."""
    # Lazy import for the same reason as above (portfolio pulls market_data).
    from routers.portfolio import _build_holdings
    from t212_sync import is_snapshot_fresh

    connection = db.query(BrokerConnection).filter(
        BrokerConnection.workspace_id == workspace_id,
        BrokerConnection.portfolio_id == pid,
        BrokerConnection.broker == "trading212",
    ).first()
    shares_by_ticker: dict[str, float] = {}
    if connection and is_snapshot_fresh(connection.positions_snapshot_at):
        # A successful empty snapshot means no current shares; never resurrect
        # old ledger holdings for notifications in that case.
        positions = db.query(BrokerPosition).filter(
            BrokerPosition.workspace_id == workspace_id,
            BrokerPosition.portfolio_id == pid,
            BrokerPosition.broker == "trading212",
        ).all()
        for position in positions:
            shares_by_ticker[position.ticker] = shares_by_ticker.get(position.ticker, 0) + position.quantity
    else:
        txns = (db.query(Transaction)
                  .filter(Transaction.workspace_id == workspace_id,
                          Transaction.portfolio_id == pid)
                  .order_by(Transaction.date)
                  .all())
        if not txns:
            return []
        shares_by_ticker = {
            ticker: holding.get("shares") or 0
            for ticker, holding in _build_holdings(txns).items()
        }

    horizon = today + timedelta(days=lead_days)
    upcoming: list[dict] = []
    for ticker in sorted(shares_by_ticker):
        shares = shares_by_ticker[ticker]
        if shares <= 0:
            continue
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
        amount = info.get("amount_per_share")
        upcoming.append({
            "ticker": ticker,
            "ex_date": ex,
            "amount_per_share": amount,
            "shares": shares,
            "est_payment": round(shares * amount, 2) if amount else None,
        })
    return upcoming


async def dividend_exdate_pass(db: Session, workspace_id: UUID, today: date | None = None,
                               lead_days: int = 3) -> list[dict]:
    """Announce upcoming ex-dividend dates on each of `workspace_id`'s
    portfolios' Discord webhooks. Returns the items announced this pass
    (empty when everything was already announced or nothing is upcoming)."""
    today = today or date.today()
    hooks = db.query(DiscordWebhook).filter(
        DiscordWebhook.workspace_id == workspace_id,
        DiscordWebhook.notify_dividends == True,  # noqa: E712
    ).all()

    announced: list[dict] = []
    for hook in hooks:
        # A prior webhook's dedup-row commit below ends the transaction and
        # drops the transaction-local `portfyl.workspace_id` set for this
        # pass -- reassert it at the top of every webhook's iteration so the
        # next one's queries never run RLS-context-less.
        _set_job_workspace_context(db, workspace_id)
        pid = hook.portfolio_id
        try:
            # Blocking yfinance I/O per holding — keep it off the event loop.
            upcoming = await asyncio.to_thread(_upcoming_dividends, db, workspace_id, pid, today, lead_days)
        except Exception as e:
            log.warning("dividend check failed for portfolio %s: %s", pid, e)
            continue

        fresh = []
        for item in upcoming:
            dup = (db.query(DividendNotification)
                     .filter(DividendNotification.workspace_id == workspace_id,
                             DividendNotification.portfolio_id == pid,
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
            db, workspace_id, pid,
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
            db.add(DividendNotification(workspace_id=workspace_id, portfolio_id=pid,
                                        ticker=item["ticker"], ex_date=item["ex_date"]))
        db.commit()
        announced.extend({**i, "portfolio_id": pid, "ex_date": i["ex_date"].isoformat()} for i in fresh)
    return announced


# -------- Explicit multi-workspace iteration (poller entry points) ---------
# Background jobs run on a plain SessionLocal() session (see main.py) -- the
# same RLS-forced `portfyl_runtime` role a request session uses. Unlike a
# request, a job has no signed-in user or X-Workspace-ID header to derive a
# workspace from, so *this* module owns the only place allowed to iterate
# every tenant: each function below enumerates active workspaces explicitly,
# resets the RLS context to exactly one of them, and only then invokes that
# workspace's tenant work above. None of the per-workspace passes above ever
# do this iteration themselves.


def _rls_enforced(db: Session) -> bool:
    """`set_config`/RLS only exist under PostgreSQL. The fast unit test suite
    (tests/test_jobs.py and friends) drives broker_autosync_pass,
    dividend_exdate_pass, and mark_sync_ran directly against an in-memory
    SQLite session -- which has no such function and no row-level security
    to scope in the first place -- so every context-setting call below is a
    deliberate no-op there. Postgres integration tests (tests/postgres/)
    exercise the real behavior against the RLS-forced `portfyl_runtime` role."""
    return db.get_bind().dialect.name == "postgresql"


def _active_workspace_ids(db: Session) -> list[UUID]:
    """Every workspace a job pass should consider. Note: this one query is
    necessarily a cross-tenant enumeration -- it's the sole intended
    exception to "every query carries a workspace_id predicate" the rest of
    this module (and the app) follows.

    Under forced RLS the `workspace_tenant_policy` on `workspaces` only ever
    lets a row through once `portfyl.workspace_id` is set to that exact row's
    id -- useless for picking which workspace to set it to in the first
    place. Migration 0003_job_workspace_enumeration adds a second, additive,
    SELECT-only policy (`workspace_job_enumeration_policy`) gated on a
    separate `portfyl.job_context` flag; Postgres combines permissive
    policies for the same command with OR, so this only ever *adds*
    visibility for this one SELECT, and only while the flag below is set --
    it never weakens per-request tenant isolation (no HTTP handler sets the
    flag) and never grants INSERT/UPDATE/DELETE on `workspaces`."""
    if not _rls_enforced(db):
        return list(db.scalars(
            select(Workspace.id).where(Workspace.archived_at.is_(None))
        ).all())
    db.execute(text("SELECT set_config('portfyl.job_context', 'true', true)"))
    try:
        return list(db.scalars(
            select(Workspace.id).where(Workspace.archived_at.is_(None))
        ).all())
    finally:
        db.execute(text("SELECT set_config('portfyl.job_context', '', true)"))


def _set_job_workspace_context(db: Session, workspace_id: UUID) -> None:
    """Scope this session to exactly one workspace for the duration of the
    current transaction. Every table a job pass touches (price_alerts,
    discord_webhooks, broker_connections, dividend_notifications,
    transactions, workspace_settings) is RLS-gated on portfyl.workspace_id
    only -- jobs have no authenticated user, so unlike
    tenancy.get_request_context there is no portfyl.user_id to set."""
    if not _rls_enforced(db):
        return
    db.execute(
        text("SELECT set_config('portfyl.workspace_id', :value, true)"),
        {"value": str(workspace_id)},
    )


async def autosync_all_workspaces(db: Session, now: datetime | None = None) -> list[dict]:
    """Poller entry point for broker auto-sync: explicit per-workspace tick
    across every active workspace."""
    results: list[dict] = []
    for workspace_id in _active_workspace_ids(db):
        _set_job_workspace_context(db, workspace_id)
        minimum_interval = None
        max_connections = None
        from edition import Edition, edition_from_env
        edition = edition_from_env(os.environ)
        if edition is Edition.CLOUD:
            from entitlements import resolve_entitlements
            access = resolve_entitlements(
                db, edition=edition, workspace_id=workspace_id, env=os.environ
            )
            if "broker_sync" not in access.capabilities:
                continue
            minimum_interval = access.limits.autosync_min_hours
            max_connections = access.limits.broker_connections
        results.extend(await autosync_tick(
            db,
            workspace_id,
            now=now,
            minimum_interval_hours=minimum_interval,
            max_connections=max_connections,
        ))
    return results


async def dividend_notify_all_workspaces(db: Session, today: date | None = None,
                                         lead_days: int = 3) -> list[dict]:
    """Poller entry point for ex-dividend notifications: explicit per-workspace
    pass across every active workspace."""
    results: list[dict] = []
    for workspace_id in _active_workspace_ids(db):
        _set_job_workspace_context(db, workspace_id)
        from edition import Edition, edition_from_env
        edition = edition_from_env(os.environ)
        if edition is Edition.CLOUD:
            from entitlements import resolve_entitlements
            access = resolve_entitlements(
                db, edition=edition, workspace_id=workspace_id, env=os.environ
            )
            if "notification_integrations" not in access.capabilities:
                continue
        results.extend(await dividend_exdate_pass(db, workspace_id, today=today, lead_days=lead_days))
    return results


async def alert_check_all_workspaces(db: Session) -> list[dict]:
    """Poller entry point for price alerts: explicit per-workspace check
    across every active workspace."""
    from routers.alerts import run_check  # lazy: avoids importing market_data/discord at module load

    results: list[dict] = []
    for workspace_id in _active_workspace_ids(db):
        _set_job_workspace_context(db, workspace_id)
        max_alerts = None
        allow_external_notifications = True
        from edition import Edition, edition_from_env
        edition = edition_from_env(os.environ)
        if edition is Edition.CLOUD:
            from entitlements import resolve_entitlements
            access = resolve_entitlements(
                db, edition=edition, workspace_id=workspace_id, env=os.environ
            )
            max_alerts = access.limits.alerts
            allow_external_notifications = "notification_integrations" in access.capabilities
        results.extend(await run_check(
            db,
            workspace_id,
            max_alerts=max_alerts,
            allow_external_notifications=allow_external_notifications,
        ))
    return results


async def rate_limit_cleanup_pass(
    db: Session,
    now: datetime | None = None,
    *,
    batch_size: int = 10_000,
    max_rows: int = 100_000,
) -> list[dict]:
    """Delete expired rate_limit_buckets rows in bounded batches. Global,
    non-tenant infrastructure state -- unlike every other pass in this
    module, this one never enumerates or scopes by workspace (see
    models.RateLimitBucket and docs/security/tenant-isolation-matrix.md's
    "Non-tenant infrastructure tables" section). Returns one summary dict
    (not one per deleted row -- there is no meaningful per-row "event" here)
    so _run_job's len(happened) still logs a truthy 1 when work occurred."""
    from models import RateLimitBucket

    cutoff = now or datetime.now(timezone.utc)
    deleted_total = 0
    while deleted_total < max_rows:
        remaining_budget = max_rows - deleted_total
        this_batch = batch_size if batch_size < remaining_budget else remaining_budget
        keys = db.scalars(
            select(RateLimitBucket.key)
            .where(RateLimitBucket.expires_at <= cutoff)
            .limit(this_batch)
        ).all()
        if not keys:
            break
        db.execute(delete(RateLimitBucket).where(RateLimitBucket.key.in_(keys)))
        db.commit()
        deleted_total += len(keys)
        if len(keys) < this_batch:
            break

    remaining = db.scalar(
        select(func.count()).select_from(RateLimitBucket).where(RateLimitBucket.expires_at <= cutoff)
    ) or 0
    # The spec's dedicated "rate_limit_cleanup" structured observability
    # event -- always emitted (not gated on remaining > 0), since this is a
    # low-frequency (hourly) job where "ran, nothing to clean" is itself
    # useful signal, unlike the generic per-check logs this module avoids.
    log.info("rate_limit_cleanup deleted=%d remaining_backlog=%d", deleted_total, remaining)
    return [{"deleted": deleted_total}] if deleted_total else []


async def account_deletion_cleanup_pass(
    db: Session,
    now: datetime | None = None,
    *,
    identity_admin=None,
) -> list[dict]:
    """Execute explicit workspace-deletion requests whose grace period ended.

    The underlying state machine rechecks sole ownership, commits each
    workspace independently, deletes the Firebase identity only after its last
    workspace, and is safe to retry. Any per-workspace failure keeps this
    recurring job's heartbeat stale so monitoring and Scheduler retries expose
    the incomplete pass.
    """
    from account_deletion import purge_due_workspace_deletions
    from data_retention import cleanup_retained_operational_data
    from firebase_identity import FirebaseIdentityVerifier

    summary = purge_due_workspace_deletions(
        db,
        identity_admin or FirebaseIdentityVerifier(),
        now=now,
    )
    retention = cleanup_retained_operational_data(db, now=now)
    log.info(
        "account_deletion_cleanup scanned=%d purged=%d not_due=%d shared=%d invalid=%d errors=%d",
        summary["scanned"],
        summary["purged"],
        summary["not_due"],
        summary["shared"],
        summary["invalid"],
        summary["errors"],
    )
    log.info(
        "data_retention_cleanup auth_sessions=%d usage_reservations=%d "
        "notification_outbox=%d dividend_notifications=%d broker_sync_events=%d",
        retention["auth_sessions"],
        retention["usage_reservations"],
        retention["notification_outbox"],
        retention["dividend_notifications"],
        retention["broker_sync_events"],
    )
    if summary["errors"]:
        raise RuntimeError(
            f"account deletion cleanup completed with {summary['errors']} error(s)"
        )
    return [{"purged": summary["purged"]}] if summary["purged"] else []
