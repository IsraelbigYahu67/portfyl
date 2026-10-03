"""Postgres regression tests for the two Critical bugs found in Task 7's
background-job workspace enumeration (backend/jobs.py):

  * Bug 1 -- `_active_workspace_ids()` queried `workspaces` with no RLS
    context set. Under the forced `workspace_tenant_policy` on that table,
    that predicate is never true, so the query returned zero rows, always --
    none of the `*_all_workspaces` poller entry points ever processed a
    single workspace. Fixed by migration 0003_job_workspace_enumeration
    (an additive, SELECT-only `workspace_job_enumeration_policy`) plus the
    `portfyl.job_context` flag `_active_workspace_ids` now sets around its
    query.
  * Bug 2 -- `set_config(..., true)` (is_local) is transaction-local: it
    reverts the instant the current transaction commits. broker_autosync_pass
    and dividend_exdate_pass both commit more than once *within* a single
    workspace's pass (once per broker connection / once per Discord webhook),
    so any DB operation after one of those internal commits ran with no RLS
    context and silently saw nothing. Fixed by reasserting
    `_set_job_workspace_context` at each such site in jobs.py.

SQLite (the fast unit test suite in tests/test_jobs.py) has no RLS at all, so
neither bug is visible there -- these tests must run against real Postgres,
as the real `portfyl_runtime` role (NOBYPASSRLS), for the bugs to be
observable at all.

--- Why this file defines its own `runtime_job_session` fixture -----------

The obvious choice is the `runtime_session` fixture in conftest.py -- and it
*is* used below wherever a test only needs to run as `portfyl_runtime` (no
internal commit involved). But `runtime_session` binds its ORM Session to a
Connection that already has an external transaction open
(`connection.begin()`, before the Session exists). SQLAlchemy 2.0's default
`join_transaction_mode` ("conditional_savepoint") makes that Session's own
`.commit()` operate on a SAVEPOINT nested inside the still-open outer
transaction -- so calling `.commit()` from code under test never actually
ends the real Postgres transaction. Verified empirically against the
disposable DB: a `set_config('x', 'y', true)` issued through such a session
is still readable *after* `session.commit()` returns, and a row inserted and
"committed" that way is invisible to a second, independent connection. That
makes `runtime_session` (and `postgres_session`) structurally *incapable* of
reproducing Bug 2 -- the transaction-local GUC it relies on never actually
resets there, so a test built on it would pass identically before and after
the fix (a false negative).

Bug 2 only manifests when `db.commit()` is a real transaction boundary,
exactly like production's poller sessions (`main.py`'s `_periodic_loop` does
`db = SessionLocal()` -- a Session bound to the bare engine, no pre-opened
transaction). `runtime_job_session` below reproduces that: a bare Connection
(no `.begin()` first) with a *session-level* `SET ROLE` (unlike `SET LOCAL
ROLE`, this survives a real commit -- also verified empirically), so
`broker_autosync_pass`/`dividend_exdate_pass`'s internal commits really end
the Postgres transaction and really drop the transaction-local
`portfyl.workspace_id` GUC. Because those commits are real, this fixture,
unlike `runtime_session`, cannot roll back after itself -- data is seeded and
torn down through dedicated fixtures (`single_workspace` / `workspace_pair`)
using explicit, really-committed owner-role sessions, the same way
`tenant_rows` in test_watchlist_settings_alert_tenancy.py already does and
for the same reason.

Ordering note: `single_workspace`/`workspace_pair` MUST be listed *before*
`runtime_session`/`runtime_job_session` in every test's parameter list.
pytest tears down same-scope fixtures in LIFO order of setup, and setup
follows declaration order for independent fixtures -- so listing the seed
fixture first means it's torn down *last*, i.e. only after
runtime_session/runtime_job_session's own teardown has ended (rolled back or
already-committed-and-closed) its transaction. Getting this backwards
deadlocks: the seed fixture's cleanup DELETE would try to lock rows that
runtime_session's still-open transaction has not yet released (verified the
hard way -- see git history of this file if you're wondering why this
comment is so insistent).
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Callable
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, delete, select, text
from sqlalchemy.orm import Session, sessionmaker

from app_settings import get_workspace_setting
from jobs import (
    SYNC_LAST_RUN_KEY,
    _active_workspace_ids,
    alert_check_all_workspaces,
    autosync_all_workspaces,
    broker_backfill_all_workspaces,
    broker_backfill_pass,
    dividend_notify_all_workspaces,
)
from models import (
    BrokerConnection,
    BrokerSyncEvent,
    BrokerSyncRun,
    DiscordWebhook,
    DividendNotification,
    Portfolio,
    PriceAlert,
    Transaction,
    Workspace,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def runtime_job_session(postgres_engine: Engine) -> Session:
    """See the module docstring for why this differs from `runtime_session`.
    Runs as the real, NOBYPASSRLS `portfyl_runtime` role, with a
    session-level (non-LOCAL) `SET ROLE` so it survives the real commits
    broker_autosync_pass/dividend_exdate_pass issue internally."""
    connection = postgres_engine.connect()
    connection.execute(text("SET ROLE portfyl_runtime"))
    connection.commit()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()
    try:
        yield session
    finally:
        session.close()
        try:
            connection.execute(text("RESET ROLE"))
            connection.commit()
        finally:
            connection.close()


def _owner_session(postgres_engine: Engine) -> Session:
    """Unrestricted (BYPASSRLS-equivalent, disposable-DB owner) session, used
    only for seeding/cleaning up rows and for asserting on persisted state --
    never for exercising the behavior under test."""
    return Session(postgres_engine, expire_on_commit=False)


def _delete_workspaces(postgres_engine: Engine, workspace_ids: list[UUID]) -> None:
    """Every table under test cascades from `workspaces.id` (ON DELETE
    CASCADE), so deleting the workspace rows cleans up everything this file
    seeds (portfolios, broker connections, webhooks, alerts, transactions,
    dividend notifications, workspace settings)."""
    with _owner_session(postgres_engine) as db:
        db.execute(delete(Workspace).where(Workspace.id.in_(workspace_ids)))
        db.commit()


def _seed_workspace(postgres_engine: Engine, *, name: str) -> tuple[Workspace, Portfolio]:
    with _owner_session(postgres_engine) as db:
        workspace = Workspace(name=name)
        db.add(workspace)
        db.flush()
        portfolio = Portfolio(workspace_id=workspace.id, name="Default", is_default=True)
        db.add(portfolio)
        db.commit()
        db.refresh(workspace)
        db.refresh(portfolio)
        return workspace, portfolio


@pytest.fixture
def single_workspace(postgres_engine: Engine):
    """One really-committed workspace + default portfolio. See the module
    docstring's "Ordering note" -- list this before runtime_session /
    runtime_job_session in any test's parameters."""
    ws, pf = _seed_workspace(postgres_engine, name=f"job-isolation-{uuid4().hex}")
    try:
        yield ws, pf
    finally:
        _delete_workspaces(postgres_engine, [ws.id])


@pytest.fixture
def workspace_pair(postgres_engine: Engine):
    """Two independent really-committed workspaces, each with a default
    portfolio. Same ordering requirement as `single_workspace`."""
    ws_a, pf_a = _seed_workspace(postgres_engine, name=f"job-isolation-a-{uuid4().hex}")
    ws_b, pf_b = _seed_workspace(postgres_engine, name=f"job-isolation-b-{uuid4().hex}")
    try:
        yield (ws_a, pf_a), (ws_b, pf_b)
    finally:
        _delete_workspaces(postgres_engine, [ws_a.id, ws_b.id])


# ---------------------------------------------------------------------------
# Bug 1: workspace enumeration under forced RLS
# ---------------------------------------------------------------------------


def test_active_workspace_ids_returns_real_workspaces_under_runtime_role(
    workspace_pair, runtime_session: Session,
):
    """`_active_workspace_ids()` must actually see the workspaces that exist
    -- pre-fix this returned [] unconditionally under the forced
    `workspace_tenant_policy` (no context is set yet; that's the whole point
    of this query), regardless of how many active workspaces exist."""
    (ws_a, _), (ws_b, _) = workspace_pair
    ids = set(_active_workspace_ids(runtime_session))
    assert ws_a.id in ids
    assert ws_b.id in ids


def test_active_workspace_ids_excludes_archived_workspaces(
    postgres_engine: Engine, workspace_pair, runtime_session: Session,
):
    # Two seeded workspaces, only one archived: an empty result (e.g. the
    # pre-fix zero-enumeration bug) would make "archived not in ids" true
    # for the wrong reason, so this also asserts the *other* one IS present
    # -- otherwise this test can't actually distinguish the two bugs.
    (ws_archived, _), (ws_active, _) = workspace_pair
    with _owner_session(postgres_engine) as db:
        row = db.get(Workspace, ws_archived.id)
        row.archived_at = datetime.now(timezone.utc)
        db.commit()

    ids = set(_active_workspace_ids(runtime_session))
    assert ws_archived.id not in ids
    assert ws_active.id in ids


# ---------------------------------------------------------------------------
# Bug 1 (black box) + cross-tenant isolation: alert_check_all_workspaces
# never commits mid-pass, so runtime_session (savepoint-based) is fine here.
# ---------------------------------------------------------------------------


def test_alert_check_all_workspaces_processes_both_workspaces_without_leaking(
    postgres_engine: Engine, workspace_pair, runtime_session: Session,
):
    (ws_a, pf_a), (ws_b, pf_b) = workspace_pair
    with _owner_session(postgres_engine) as db:
        db.add(PriceAlert(workspace_id=ws_a.id, portfolio_id=pf_a.id, ticker="AAPL",
                          direction="above", target_price=100.0, enabled=True, status="active"))
        db.add(PriceAlert(workspace_id=ws_b.id, portfolio_id=pf_b.id, ticker="MSFT",
                          direction="above", target_price=100.0, enabled=True, status="active"))
        db.commit()

    quotes = {
        "AAPL": {"currentPrice": 999.0, "regularMarketPrice": 999.0, "currency": "USD"},
        "MSFT": {"currentPrice": 999.0, "regularMarketPrice": 999.0, "currency": "USD"},
    }
    sent = AsyncMock(return_value=None)
    with patch("routers.alerts.market_data.get_infos", return_value=quotes), \
         patch("routers.alerts.send_discord_notification", sent):
        fired = asyncio.run(alert_check_all_workspaces(runtime_session))

    fired_tickers = {row["ticker"] for row in fired}
    # Bug 1, black-box: pre-fix, _active_workspace_ids() returned [] so this
    # whole set would be empty regardless of the seeded alerts. Also a basic
    # cross-tenant sanity check: neither workspace's alert is missing, and
    # nothing extra leaked in for either.
    assert fired_tickers == {"AAPL", "MSFT"}


# ---------------------------------------------------------------------------
# Bug 2: broker_autosync_pass -- a workspace with 2+ auto-sync connections.
# ---------------------------------------------------------------------------


def test_autosync_all_workspaces_processes_every_connection_despite_internal_commits(
    postgres_engine: Engine, single_workspace, runtime_job_session: Session,
):
    """Two auto-sync connections (trading212 + ibkr) on one workspace, one
    Discord webhook with notify_trades on. sync_transactions/_run_ibkr_sync
    commit internally in production -- simulated here with a real
    `db.commit()` inside the fakes, so the RLS context genuinely resets
    between connections just like it does for real. The T212 foreground pass
    now queues history instead of importing ledger rows, while IBKR still
    notifies immediately. The important regression is that both connections
    remain visible after either internal commit."""
    ws, pf = single_workspace
    with _owner_session(postgres_engine) as db:
        db.add(BrokerConnection(workspace_id=ws.id, portfolio_id=pf.id, broker="trading212",
                                api_key="k" * 20, api_secret="", environment="live", auto_sync=True))
        db.add(BrokerConnection(workspace_id=ws.id, portfolio_id=pf.id, broker="ibkr",
                                api_key="k" * 20, api_secret="q", environment="live", auto_sync=True))
        db.add(DiscordWebhook(workspace_id=ws.id, portfolio_id=pf.id,
                              webhook_url="https://discord.com/api/webhooks/1/x",
                              notify_trades=True, notify_dividends=False, notify_milestones=True))
        db.commit()

    sync_calls: list[str] = []

    def fake_sync_transactions(db, portfolio, _context):
        sync_calls.append("trading212")
        # sync_transactions commits internally in production -- reproduce
        # that real transaction boundary here, on the session under test.
        db.commit()
        return {
            "snapshot": {"status": "ready"},
            "history": {"run_id": "run-1", "status": "pending", "complete": False},
        }

    def fake_run_ibkr_sync(db, workspace_id, portfolio_id):
        sync_calls.append("ibkr")
        db.commit()
        return {"imported": 1}

    notified: list[str] = []

    async def fake_notify(db, workspace_id, portfolio_id, title, description, color=0):
        notified.append(title)
        return True

    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    with patch("routers.broker.sync_transactions", side_effect=fake_sync_transactions), \
         patch("routers.ibkr._run_ibkr_sync", AsyncMock(side_effect=fake_run_ibkr_sync)), \
         patch("jobs.send_discord_notification", side_effect=fake_notify):
        asyncio.run(autosync_all_workspaces(runtime_job_session, now=now))

    assert sorted(sync_calls) == ["ibkr", "trading212"]
    # T212 has no finalized ledger delta to announce in the foreground pass;
    # the IBKR import still proves the post-commit webhook lookup is scoped.
    assert len(notified) == 1

    # mark_sync_ran's WorkspaceSetting upsert runs after broker_autosync_pass
    # returns -- pre-fix it would run RLS-context-less too (and, being a
    # write against a forced-RLS WITH CHECK table, raise instead of silently
    # no-op'ing). Confirm it actually persisted.
    with _owner_session(postgres_engine) as db:
        assert get_workspace_setting(db, ws.id, SYNC_LAST_RUN_KEY) == now.isoformat()


# ---------------------------------------------------------------------------
# Bug-2-shaped regression, new job: jobs.broker_backfill_pass /
# t212_sync.advance_run commit a real transaction boundary after every page
# (T212 snapshot-first sync plan, 2026-09-20, Task 3, §5.4) -- the same
# failure class Bug 2 above was about, for a brand-new job/table pair added
# after that fix already existed. Proves broker_backfill_pass's own
# `_set_job_workspace_context` reassertion (passed into advance_run as
# `reassert_context`) actually keeps every page's staging query and
# checkpoint write inside the right tenant's RLS context, using the real
# `advance_run` (network mocked, not the function itself) so its genuine
# multi-commit sequence runs against the real forced-RLS `portfyl_runtime`
# role.
# ---------------------------------------------------------------------------


def _t212_page_response(items, next_page_path=None):
    response = MagicMock(status_code=200, headers={})
    response.json.return_value = {"items": items, "nextPagePath": next_page_path}
    return response


def test_broker_backfill_pass_stages_every_page_despite_internal_commits(
    postgres_engine: Engine, single_workspace, runtime_job_session: Session,
):
    ws, pf = single_workspace
    with _owner_session(postgres_engine) as db:
        # `pf` is detached (its seeding session is closed), so assigning to it
        # would never reach the database; persist the binding explicitly.
        db.query(Portfolio).filter(Portfolio.id == pf.id).update(
            {"t212_account_fingerprint": "single-account-fingerprint"}, synchronize_session=False,
        )
        conn = BrokerConnection(workspace_id=ws.id, portfolio_id=pf.id, broker="trading212",
                                api_key="k" * 20, api_secret="", environment="live",
                                account_fingerprint="single-account-fingerprint")
        db.add(conn)
        db.flush()
        run = BrokerSyncRun(
            workspace_id=ws.id, portfolio_id=pf.id, connection_id=conn.id, broker="trading212",
            account_fingerprint=conn.account_fingerprint,
            credential_generation=conn.credential_generation, mode="incremental", state="pending",
        )
        db.add(run)
        db.commit()
        conn_id, run_id = conn.id, run.id

    # Two pages of orders (forces >=2 internal commits inside one advance_run
    # call: page-1 checkpoint, page-2 completion), one empty page of
    # dividends. If RLS context is lost after the first commit, the second
    # page's stage_events INSERT is rejected by the forced WITH CHECK policy
    # instead of silently landing in the wrong tenant.
    page1 = _t212_page_response(
        [{"order": {"id": "o1"}, "fill": {"id": "f1"}}],
        "/equity/history/orders?cursor=next",
    )
    page2 = _t212_page_response([{"order": {"id": "o2"}, "fill": {"id": "f2"}}], None)
    empty_dividends = _t212_page_response([], None)
    calls = {"orders": 0}

    def fake_get(url, headers=None, params=None, timeout=None):
        if "dividends" in url or "transactions" in url:
            return empty_dividends
        calls["orders"] += 1
        return page1 if calls["orders"] == 1 else page2

    with patch("t212_sync.httpx.get", side_effect=fake_get):
        results = asyncio.run(broker_backfill_pass(runtime_job_session, ws.id))

    assert len(results) == 1
    assert results[0]["state"] == "completed"
    assert results[0]["orders_staged"] == 2

    with _owner_session(postgres_engine) as db:
        run_row = db.get(BrokerSyncRun, run_id)
        assert run_row.state == "completed"
        assert run_row.orders_loaded == 2
        events = db.query(BrokerSyncEvent).filter(BrokerSyncEvent.run_id == run_id).all()
        assert {e.provider_event_id for e in events} == {"fill:f1", "fill:f2"}
        assert all(e.workspace_id == ws.id for e in events)


def test_broker_backfill_imports_cash_events_under_forced_rls(
    postgres_engine: Engine, single_workspace, runtime_job_session: Session,
):
    """Plan 2026-10-03: the cash stream stages, finalizes and inserts its ledger
    row inside the owning workspace, and the widened stream CHECK accepts it."""
    from models import Transaction

    ws, pf = single_workspace
    with _owner_session(postgres_engine) as db:
        db.query(Portfolio).filter(Portfolio.id == pf.id).update(
            {"t212_account_fingerprint": "single-account-fingerprint"}, synchronize_session=False,
        )
        conn = BrokerConnection(workspace_id=ws.id, portfolio_id=pf.id, broker="trading212",
                                api_key="k" * 20, api_secret="", environment="live",
                                account_fingerprint="single-account-fingerprint")
        db.add(conn)
        db.flush()
        run = BrokerSyncRun(
            workspace_id=ws.id, portfolio_id=pf.id, connection_id=conn.id, broker="trading212",
            account_fingerprint=conn.account_fingerprint,
            credential_generation=conn.credential_generation, mode="initial", state="pending",
        )
        db.add(run)
        db.commit()
        run_id = run.id

    empty = _t212_page_response([], None)
    cash = _t212_page_response([
        {"type": "DEPOSIT", "amount": 3200.0, "currency": "CZK",
         "reference": "c1", "dateTime": "2026-03-01T10:00:00.000Z"},
        {"type": "TRANSFER", "amount": -200.0, "currency": "CZK",
         "reference": "c2", "dateTime": "2026-03-02T10:00:00.000Z"},
    ], None)

    def fake_get(url, headers=None, params=None, timeout=None):
        return cash if "transactions" in url else empty

    with patch("t212_sync.httpx.get", side_effect=fake_get), \
            patch("t212_sync.bulk_fetch_fx", return_value={}):
        results = asyncio.run(broker_backfill_pass(runtime_job_session, ws.id))

    assert results[0]["state"] == "completed"
    assert results[0]["cash_staged"] == 2

    with _owner_session(postgres_engine) as db:
        rows = db.query(Transaction).filter(
            Transaction.workspace_id == ws.id, Transaction.source_event_stream == "cash",
        ).order_by(Transaction.date).all()
        assert [(r.type, r.amount, r.currency) for r in rows] == [
            ("deposit", 3200.0, "CZK"), ("withdrawal", 200.0, "CZK"),
        ]
        assert db.get(BrokerSyncRun, run_id).cash_loaded == 2


def test_broker_backfill_reports_a_cancelled_run_after_its_credentials_rotated(
    postgres_engine: Engine, single_workspace, runtime_job_session: Session,
):
    """A run whose connection rotated credentials mid-flight is cancelled by
    the job. Reporting it must not re-read the row after the commit: the
    commit drops the transaction-local RLS context, so a lazy reload under
    forced RLS finds no row and raises ObjectDeletedError."""
    ws, pf = single_workspace
    with _owner_session(postgres_engine) as db:
        db.query(Portfolio).filter(Portfolio.id == pf.id).update(
            {"t212_account_fingerprint": "rotated-account-fingerprint"}, synchronize_session=False,
        )
        conn = BrokerConnection(workspace_id=ws.id, portfolio_id=pf.id, broker="trading212",
                                api_key="k" * 20, api_secret="", environment="live",
                                account_fingerprint="rotated-account-fingerprint")
        db.add(conn)
        db.flush()
        run = BrokerSyncRun(
            workspace_id=ws.id, portfolio_id=pf.id, connection_id=conn.id, broker="trading212",
            account_fingerprint=conn.account_fingerprint,
            credential_generation=conn.credential_generation, mode="incremental", state="pending",
        )
        db.add(run)
        db.flush()
        conn.credential_generation = conn.credential_generation + 1  # rotated after the run began
        db.commit()
        run_id, run_public_id = run.id, str(run.public_id)

    with patch("t212_sync.httpx.get", side_effect=AssertionError("a cancelled run must not call T212")):
        results = asyncio.run(broker_backfill_pass(runtime_job_session, ws.id))

    assert results == [{"run_id": run_public_id, "state": "cancelled"}]
    with _owner_session(postgres_engine) as db:
        assert db.get(BrokerSyncRun, run_id).state == "cancelled"


def test_one_active_run_per_connection_is_enforced_at_the_database_level(
    postgres_engine: Engine, single_workspace,
):
    """Migration 0015's partial unique index is the backstop behind
    t212_sync.claim_or_create_run's idempotent read-then-insert -- a second,
    non-terminal run for the same connection must be rejected by the
    database itself even if application logic is bypassed entirely (e.g. a
    genuine concurrent double-click both passing the initial SELECT)."""
    from sqlalchemy.exc import IntegrityError

    ws, pf = single_workspace
    with _owner_session(postgres_engine) as db:
        conn = BrokerConnection(workspace_id=ws.id, portfolio_id=pf.id, broker="trading212",
                                api_key="k" * 20, api_secret="", environment="live")
        db.add(conn)
        db.flush()
        conn_id, generation = conn.id, conn.credential_generation
        db.add(BrokerSyncRun(
            workspace_id=ws.id, portfolio_id=pf.id, connection_id=conn_id, broker="trading212",
            credential_generation=generation, mode="incremental", state="fetching",
        ))
        db.commit()

        db.add(BrokerSyncRun(
            workspace_id=ws.id, portfolio_id=pf.id, connection_id=conn_id, broker="trading212",
            credential_generation=generation, mode="incremental", state="pending",
        ))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    # A terminal-state existing run does not block a new one (matches
    # claim_or_create_run's own application-level check).
    with _owner_session(postgres_engine) as db:
        db.query(BrokerSyncRun).filter(BrokerSyncRun.workspace_id == ws.id).update(
            {"state": "completed"}, synchronize_session=False,
        )
        db.commit()
        db.add(BrokerSyncRun(
            workspace_id=ws.id, portfolio_id=pf.id, connection_id=conn_id, broker="trading212",
            credential_generation=generation, mode="incremental", state="pending",
        ))
        db.commit()  # does not raise


def test_broker_backfill_all_workspaces_advances_both_tenants_without_leaking(
    postgres_engine: Engine, workspace_pair, runtime_job_session: Session,
):
    (ws_a, pf_a), (ws_b, pf_b) = workspace_pair
    run_ids = {}
    with _owner_session(postgres_engine) as db:
        for label, ws, pf in (("a", ws_a, pf_a), ("b", ws_b, pf_b)):
            fingerprint = f"{label}-account-fingerprint"
            db.query(Portfolio).filter(Portfolio.id == pf.id).update(
                {"t212_account_fingerprint": fingerprint}, synchronize_session=False,
            )
            conn = BrokerConnection(workspace_id=ws.id, portfolio_id=pf.id, broker="trading212",
                                    api_key=f"{label}-key" * 4, api_secret="", environment="live",
                                    account_fingerprint=fingerprint)
            db.add(conn)
            db.flush()
            run = BrokerSyncRun(
                workspace_id=ws.id, portfolio_id=pf.id, connection_id=conn.id, broker="trading212",
                account_fingerprint=conn.account_fingerprint,
                credential_generation=conn.credential_generation, mode="incremental", state="pending",
            )
            db.add(run)
            db.flush()
            run_ids[label] = run.id
        db.commit()

    empty = _t212_page_response([], None)
    with patch("t212_sync.httpx.get", return_value=empty):
        results = asyncio.run(broker_backfill_all_workspaces(runtime_job_session))

    result_run_ids = {r["run_id"] for r in results}
    with _owner_session(postgres_engine) as db:
        run_a = db.get(BrokerSyncRun, run_ids["a"])
        run_b = db.get(BrokerSyncRun, run_ids["b"])
        assert str(run_a.public_id) in result_run_ids
        assert str(run_b.public_id) in result_run_ids
        assert run_a.state == "completed"
        assert run_b.state == "completed"


# ---------------------------------------------------------------------------
# Bug 2: dividend_exdate_pass -- a workspace with 2+ dividend-enabled hooks.
# ---------------------------------------------------------------------------


def _div_info_for(ex_date: date, amount: float = 0.25) -> Callable[[str], dict]:
    def _fn(ticker: str) -> dict:
        return {"ticker": ticker, "ex_date": ex_date.isoformat(),
                "amount_per_share": amount, "frequency": "quarterly"}
    return _fn


def test_dividend_notify_all_workspaces_announces_every_webhook_despite_internal_commits(
    postgres_engine: Engine, single_workspace, runtime_job_session: Session,
):
    """Two portfolios in one workspace, each with its own dividend-enabled
    Discord webhook and its own holding. dividend_exdate_pass's own dedup-row
    commit (once per webhook, after a successful announce) is the real
    internal commit under test here -- no mocking of the commit itself is
    needed, only of yfinance and Discord delivery. Pre-fix, the second
    webhook's `_upcoming_dividends` -> `Transaction` query runs RLS-context-less
    after the first webhook's commit and silently returns no holdings, so its
    dividend is never announced."""
    ws, pf1 = single_workspace
    with _owner_session(postgres_engine) as db:
        pf2 = Portfolio(workspace_id=ws.id, name="Second", is_default=False)
        db.add(pf2)
        db.flush()
        db.add(DiscordWebhook(workspace_id=ws.id, portfolio_id=pf1.id,
                              webhook_url="https://discord.com/api/webhooks/1/a",
                              notify_trades=False, notify_dividends=True, notify_milestones=True))
        db.add(DiscordWebhook(workspace_id=ws.id, portfolio_id=pf2.id,
                              webhook_url="https://discord.com/api/webhooks/1/b",
                              notify_trades=False, notify_dividends=True, notify_milestones=True))
        db.add(Transaction(workspace_id=ws.id, portfolio_id=pf1.id, ticker="AAPL", name="AAPL",
                           type="buy", shares=10.0, price=100.0, currency="USD", date=date(2024, 1, 15)))
        db.add(Transaction(workspace_id=ws.id, portfolio_id=pf2.id, ticker="MSFT", name="MSFT",
                           type="buy", shares=5.0, price=200.0, currency="USD", date=date(2024, 1, 15)))
        db.commit()
        pf2_id = pf2.id

    today = date(2026, 7, 12)
    ex_date = date(2026, 7, 14)

    with patch("jobs._next_dividend_info", _div_info_for(ex_date)), \
         patch("jobs.send_discord_notification", AsyncMock(return_value=True)):
        announced = asyncio.run(dividend_notify_all_workspaces(
            runtime_job_session, today=today, lead_days=3))

    announced_portfolios = {item["portfolio_id"] for item in announced}
    # The regression: pre-fix this is {pf1.id} only.
    assert announced_portfolios == {pf1.id, pf2_id}

    with _owner_session(postgres_engine) as db:
        rows = db.scalars(
            select(DividendNotification).where(DividendNotification.workspace_id == ws.id)
        ).all()
        assert {(r.portfolio_id, r.ticker) for r in rows} == {(pf1.id, "AAPL"), (pf2_id, "MSFT")}
