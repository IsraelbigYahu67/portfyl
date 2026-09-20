# External, Idempotent Job Triggering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Portfyl's in-process asyncio job pollers with an external,
idempotent, tenant-aware HTTP trigger safe for a multi-instance,
scale-to-zero Cloud Run deployment — fixing a live duplicate-run/silent-loss
bug — while consolidating the existing IBKR-only scheduler precedent instead
of leaving a second, inconsistent mechanism alongside it.

**Architecture:** A new `job_runs` table gives per-(job, workspace, period)
idempotency and dead-lettering via one unique-constraint claim. The three
existing `jobs.py` `*_all_workspaces` functions wrap each workspace's pass
with a claim/finish pair, so both the in-process poller (local edition) and
a new shared HTTP trigger (`POST /api/jobs/run`, cloud edition) go through
the same protected path. `/api/ibkr/scheduler-sync` is removed — its
IBKR-only, schedule-blind behavior is superseded by the schedule-aware
`autosync` job, which already covers IBKR + Trading212.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, PostgreSQL (forced RLS), Alembic,
pytest (fast SQLite suite + `tests/postgres/` PostgreSQL integration suite).

**Spec:** `docs/superpowers/specs/2026-09-03-portfyl-job-triggering-design.md`

## Global Constraints

- Every write to a tenant table must happen with `portfyl.workspace_id` set
  via `_set_job_workspace_context` (`backend/jobs.py`) — reassert it
  immediately after any `db.commit()`, including the new claim/finish
  commits this plan adds.
- `job_runs` uses the **same** per-workspace RLS tenant policy as every
  other `_WORKSPACE_TABLES` entry (`backend/alembic/versions/0002_tenant_rls.py`)
  — no new RLS bypass or exception.
- Don't change `sync_due`/`load_sync_schedule`'s per-workspace daily/interval
  scheduling semantics (`backend/jobs.py`) — the claim is an additional
  concurrency guard layered on top, not a replacement.
- Fast unit suite (from `backend/`): `python -m pytest tests/ -v` (add
  `--ignore=tests/postgres` if running everything). Requires
  `backend/requirements-dev.txt` installed.
- Postgres integration suite (from `backend/`, needs Docker Desktop —
  `docker compose -f ../deploy/docker-compose.postgres-test.yml up -d --wait`
  — or an explicit `TEST_DATABASE_URL` containing `test` in the DB name):
  `python -m pytest tests/postgres/ -v`.
- Run both suites before every commit in this plan that touches backend
  code; commit after each task once its own suite (fast, Postgres, or both)
  passes.

---

## Task 1: `job_runs` table

**Files:**
- Modify: `backend/models.py` (append `JobRun`)
- Create: `backend/alembic/versions/0004_job_runs.py`
- Modify: `backend/tests/postgres/test_rls.py` (`RLS_TABLES` set, line 24)

**Interfaces:**
- Produces: `models.JobRun` (`id`, `workspace_id`, `job_name`, `period_start`,
  `status`, `attempt_count`, `last_error`, `started_at`, `finished_at`) and
  the `job_runs` table with a `uq_job_run_period` unique constraint on
  `(job_name, workspace_id, period_start)` — Task 2 builds the claim SQL
  against this exact shape.

- [ ] **Step 1: Add `job_runs` to the RLS assertion set (expect it to fail)**

In `backend/tests/postgres/test_rls.py`, add `"job_runs"` to the `RLS_TABLES`
set (line 24, alphabetically after `"discord_webhooks"` is fine — the set is
unordered, just add it anywhere in the literal):

```python
RLS_TABLES = {
    "workspaces",
    "memberships",
    "user_settings",
    "workspace_settings",
    "data_migration_runs",
    "portfolios",
    "transactions",
    "watchlists",
    "watchlist_items",
    "benchmarks",
    "benchmark_components",
    "broker_connections",
    "broker_balances",
    "options_trades",
    "polymarket_positions",
    "discord_webhooks",
    "trade_notes",
    "cash_interest_rates",
    "dividend_notifications",
    "price_alerts",
    "job_runs",
}
```

- [ ] **Step 2: Run the Postgres RLS test to confirm it fails**

Run (from `backend/`, with the disposable Postgres test DB up):
`python -m pytest tests/postgres/test_rls.py::test_all_tenant_tables_enable_and_force_rls -v`
Expected: FAIL — `job_runs` isn't a real table yet, so the query returns
fewer rows than `RLS_TABLES` and the `==` assertion fails.

- [ ] **Step 3: Add the `JobRun` model**

Append to the end of `backend/models.py` (after the `PriceAlert` class):

```python
class JobRun(Base):
    __tablename__ = "job_runs"
    __table_args__ = (
        UniqueConstraint("job_name", "workspace_id", "period_start",
                          name="uq_job_run_period"),
        CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'dead_letter')",
            name="ck_job_runs_status",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = _workspace_id()
    job_name = Column(String, nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    status = Column(String, nullable=False, server_default="running")
    attempt_count = Column(Integer, nullable=False, server_default="1")
    last_error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
```

No `public_id` — this table is never serialized to a client, unlike every
other model in this file.

- [ ] **Step 4: Write the migration**

Create `backend/alembic/versions/0004_job_runs.py`:

```python
"""Add job_runs: idempotency/dead-letter tracking for external job triggering.

Revision ID: 0004_job_runs
Revises: 0003_job_workspace_enumeration
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_job_runs"
down_revision: Union[str, Sequence[str], None] = "0003_job_workspace_enumeration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_WORKSPACE_SETTING = (
    "NULLIF(current_setting('portfyl.workspace_id', true), '')::uuid"
)


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("job_name", sa.String(), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="running"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'succeeded', 'failed', 'dead_letter')",
            name="ck_job_runs_status",
        ),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_name", "workspace_id", "period_start", name="uq_job_run_period"),
    )
    op.create_index(op.f("ix_job_runs_workspace_id"), "job_runs", ["workspace_id"], unique=False)

    op.execute('GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "job_runs" TO portfyl_runtime')
    op.execute("GRANT USAGE, SELECT ON SEQUENCE job_runs_id_seq TO portfyl_runtime")

    op.execute('ALTER TABLE "job_runs" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "job_runs" FORCE ROW LEVEL SECURITY')
    op.execute(f"""
        CREATE POLICY job_runs_tenant_policy ON job_runs
        USING (workspace_id = {_WORKSPACE_SETTING})
        WITH CHECK (workspace_id = {_WORKSPACE_SETTING})
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS job_runs_tenant_policy ON job_runs")
    op.execute('ALTER TABLE "job_runs" NO FORCE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "job_runs" DISABLE ROW LEVEL SECURITY')
    op.execute("REVOKE USAGE, SELECT ON SEQUENCE job_runs_id_seq FROM portfyl_runtime")
    op.execute('REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE "job_runs" FROM portfyl_runtime')
    op.drop_index(op.f("ix_job_runs_workspace_id"), table_name="job_runs")
    op.drop_table("job_runs")
```

- [ ] **Step 5: Apply the migration to your local Postgres and re-run the test**

Run (from `backend/`, `DATABASE_URL` pointed at your local dev Postgres or
the disposable test DB): `alembic upgrade head`, then:
`python -m pytest tests/postgres/test_rls.py::test_all_tenant_tables_enable_and_force_rls -v`
Expected: PASS.

(The `postgres_engine` session fixture in `tests/postgres/conftest.py` runs
`alembic upgrade head` itself against the disposable test DB on every test
session, so a plain `python -m pytest tests/postgres/ -v` also picks up the
new migration automatically — the manual `alembic upgrade head` above is
only needed if you're pointed at a different, persistent local DB.)

- [ ] **Step 6: Run the full Postgres suite to confirm nothing else regressed**

Run: `python -m pytest tests/postgres/ -v`
Expected: PASS (all tests, including the pre-existing ones).

- [ ] **Step 7: Commit**

```bash
git add backend/models.py backend/alembic/versions/0004_job_runs.py backend/tests/postgres/test_rls.py
git commit -m "feat(jobs): add job_runs table for idempotent job triggering"
```

---

## Task 2: Period bucketing + claim/finish helpers

**Files:**
- Modify: `backend/jobs.py` (add constants, `_env_int`, `_period_start`,
  `_claim_job_run`, `_finish_job_run`)
- Create: `backend/tests/test_job_scheduling.py` (fast, pure-function tests)
- Create: `backend/tests/postgres/test_job_runs.py` (Postgres claim/finish tests)

**Interfaces:**
- Consumes: `models.JobRun` / `job_runs` table (Task 1).
- Produces: `jobs.MAX_JOB_ATTEMPTS_PER_PERIOD` (int), `jobs.JOB_RUN_STALE_AFTER`
  (`timedelta`), `jobs.JOB_PERIOD_SECONDS` (`dict[str, Callable[[], int]]`,
  keys `"alert_check"`/`"autosync"`/`"dividend_notify"`),
  `jobs._period_start(now: datetime, job_name: str) -> datetime`,
  `jobs._claim_job_run(db, job_name: str, workspace_id: UUID, now: datetime) -> tuple[int, int] | None`
  (returns `(run_id, attempt_count)` or `None` if this period is already
  claimed), `jobs._finish_job_run(db, run_id: int, status: str, error: str | None = None) -> None`
  — Task 3 wraps the three `*_all_workspaces` functions with these.

- [ ] **Step 1: Write the failing fast test for `_period_start`**

Create `backend/tests/test_job_scheduling.py`:

```python
"""Fast, DB-free tests for jobs.py's period-bucketing math."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime, timezone

from jobs import JOB_PERIOD_SECONDS, _period_start


def test_period_start_floors_to_the_bucket_boundary(monkeypatch):
    monkeypatch.delenv("AUTOSYNC_TRIGGER_INTERVAL_SECONDS", raising=False)
    now = datetime(2026, 1, 1, 12, 7, 30, tzinfo=timezone.utc)  # 300s bucket -> :05:00
    assert _period_start(now, "autosync") == datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc)


def test_period_start_respects_env_override(monkeypatch):
    monkeypatch.setenv("AUTOSYNC_TRIGGER_INTERVAL_SECONDS", "60")
    now = datetime(2026, 1, 1, 12, 7, 30, tzinfo=timezone.utc)
    assert _period_start(now, "autosync") == datetime(2026, 1, 1, 12, 7, 0, tzinfo=timezone.utc)


def test_job_period_seconds_has_exactly_the_three_job_types():
    assert set(JOB_PERIOD_SECONDS) == {"alert_check", "autosync", "dividend_notify"}
```

- [ ] **Step 2: Run it to verify it fails**

Run (from `backend/`): `python -m pytest tests/test_job_scheduling.py -v`
Expected: FAIL — `_period_start` / `JOB_PERIOD_SECONDS` don't exist yet
(`ImportError`).

- [ ] **Step 3: Add the constants and `_period_start` to `jobs.py`**

In `backend/jobs.py`, change the `typing` import at the top (currently
`from typing import Any`) to:

```python
from typing import Any, Callable
```

Then add, right after the `SYNC_COLOR` constant (after line 80):

```python
# -------- External job triggering: idempotency + dead-lettering ------------
# See docs/superpowers/specs/2026-09-03-portfyl-job-triggering-design.md.

MAX_JOB_ATTEMPTS_PER_PERIOD = 3
JOB_RUN_STALE_AFTER = timedelta(minutes=10)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except ValueError:
        return default


JOB_PERIOD_SECONDS: dict[str, Callable[[], int]] = {
    "alert_check": lambda: _env_int("ALERT_CHECK_INTERVAL_SECONDS", 900),
    "autosync": lambda: _env_int("AUTOSYNC_TRIGGER_INTERVAL_SECONDS", 300),
    "dividend_notify": lambda: _env_int("DIVIDEND_NOTIFY_INTERVAL_SECONDS", 43200),
}


def _period_start(now: datetime, job_name: str) -> datetime:
    """The start of `now`'s bucket for `job_name`, sized by that job's
    configured trigger interval. Two claims for the same (job, workspace)
    within the same bucket are the same idempotency key."""
    bucket = JOB_PERIOD_SECONDS[job_name]()
    epoch = now.timestamp()
    return datetime.fromtimestamp((epoch // bucket) * bucket, tz=timezone.utc)
```

- [ ] **Step 4: Run the fast test again to verify it passes**

Run: `python -m pytest tests/test_job_scheduling.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing Postgres tests for claim/finish**

Create `backend/tests/postgres/test_job_runs.py`:

```python
"""Postgres tests for job_runs claim/finish idempotency and dead-lettering
(backend/jobs.py's _claim_job_run/_finish_job_run) -- see
docs/superpowers/specs/2026-09-03-portfyl-job-triggering-design.md.

Reuses the seeding/session fixtures from test_job_workspace_isolation.py
rather than duplicating them -- see that module's docstring for why
runtime_job_session (real commits) is required here, not runtime_session
(savepoint-based, would give a false pass on the claim's own db.commit())."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from jobs import (
    JOB_RUN_STALE_AFTER,
    MAX_JOB_ATTEMPTS_PER_PERIOD,
    _claim_job_run,
    _finish_job_run,
    _set_job_workspace_context,
)
from tests.postgres.test_job_workspace_isolation import (
    _owner_session,
    runtime_job_session,
    single_workspace,
)


NOW = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def test_second_claim_in_same_period_is_rejected(single_workspace, runtime_job_session: Session):
    ws, _ = single_workspace
    _set_job_workspace_context(runtime_job_session, ws.id)
    first = _claim_job_run(runtime_job_session, "autosync", ws.id, NOW)
    _set_job_workspace_context(runtime_job_session, ws.id)
    second = _claim_job_run(runtime_job_session, "autosync", ws.id, NOW)

    assert first is not None
    assert second is None


def test_new_period_allows_a_fresh_claim(single_workspace, runtime_job_session: Session):
    ws, _ = single_workspace
    _set_job_workspace_context(runtime_job_session, ws.id)
    first = _claim_job_run(runtime_job_session, "autosync", ws.id, NOW)
    later = NOW + timedelta(minutes=5)  # default autosync bucket is 300s
    _set_job_workspace_context(runtime_job_session, ws.id)
    second = _claim_job_run(runtime_job_session, "autosync", ws.id, later)

    assert first is not None and second is not None
    assert second[0] != first[0]


def test_finish_succeeded_persists_status(
    postgres_engine, single_workspace, runtime_job_session: Session,
):
    ws, _ = single_workspace
    _set_job_workspace_context(runtime_job_session, ws.id)
    run_id, _ = _claim_job_run(runtime_job_session, "autosync", ws.id, NOW)
    _set_job_workspace_context(runtime_job_session, ws.id)
    _finish_job_run(runtime_job_session, run_id, "succeeded")

    with _owner_session(postgres_engine) as db:
        row = db.execute(
            text("SELECT status, finished_at FROM job_runs WHERE id = :id"), {"id": run_id}
        ).one()
        assert row.status == "succeeded"
        assert row.finished_at is not None


def test_repeated_failures_reach_dead_letter_within_one_period(
    single_workspace, runtime_job_session: Session,
):
    ws, _ = single_workspace
    last_status = None
    for _ in range(MAX_JOB_ATTEMPTS_PER_PERIOD):
        _set_job_workspace_context(runtime_job_session, ws.id)
        claim = _claim_job_run(runtime_job_session, "autosync", ws.id, NOW)
        assert claim is not None
        run_id, attempt = claim
        _set_job_workspace_context(runtime_job_session, ws.id)
        last_status = "dead_letter" if attempt >= MAX_JOB_ATTEMPTS_PER_PERIOD else "failed"
        _finish_job_run(runtime_job_session, run_id, last_status, error="boom")

    assert last_status == "dead_letter"
    _set_job_workspace_context(runtime_job_session, ws.id)
    assert _claim_job_run(runtime_job_session, "autosync", ws.id, NOW) is None


def test_stale_running_row_can_be_reclaimed(
    postgres_engine, single_workspace, runtime_job_session: Session,
):
    ws, _ = single_workspace
    _set_job_workspace_context(runtime_job_session, ws.id)
    claim = _claim_job_run(runtime_job_session, "autosync", ws.id, NOW)
    assert claim is not None
    run_id, attempt = claim

    # Simulate a crashed worker: back-date started_at past the staleness
    # window without ever calling _finish_job_run.
    with _owner_session(postgres_engine) as db:
        db.execute(
            text("UPDATE job_runs SET started_at = :ts WHERE id = :id"),
            {"ts": NOW - JOB_RUN_STALE_AFTER - timedelta(minutes=1), "id": run_id},
        )
        db.commit()

    _set_job_workspace_context(runtime_job_session, ws.id)
    reclaimed = _claim_job_run(runtime_job_session, "autosync", ws.id, NOW)
    assert reclaimed is not None
    assert reclaimed == (run_id, attempt + 1)
```

- [ ] **Step 6: Run the Postgres tests to verify they fail**

Run: `python -m pytest tests/postgres/test_job_runs.py -v`
Expected: FAIL — `_claim_job_run` / `_finish_job_run` don't exist yet.

- [ ] **Step 7: Add `_claim_job_run` and `_finish_job_run` to `jobs.py`**

Add directly after `_period_start` (from Step 3):

```python
def _claim_job_run(db: Session, job_name: str, workspace_id: UUID, now: datetime) -> tuple[int, int] | None:
    """Atomically claim workspace_id's job_name pass for now's period.
    Returns (job_runs.id, attempt_count) to finish later, or None if another
    run already owns this period (running-and-not-stale, succeeded, or
    dead-lettered). Commits immediately so a concurrent claimant sees the
    committed 'running' row and is rejected rather than blocking on the row
    lock for the duration of the pass -- callers must reassert
    _set_job_workspace_context before their next DB operation."""
    period_start = _period_start(now, job_name)
    stale_cutoff = now - JOB_RUN_STALE_AFTER
    row = db.execute(text("""
        INSERT INTO job_runs (workspace_id, job_name, period_start, status, attempt_count, started_at)
        VALUES (:workspace_id, :job_name, :period_start, 'running', 1, :now)
        ON CONFLICT (job_name, workspace_id, period_start) DO UPDATE
        SET status = 'running', attempt_count = job_runs.attempt_count + 1, started_at = :now
        WHERE job_runs.status = 'failed' AND job_runs.attempt_count < :max_attempts
           OR (job_runs.status = 'running' AND job_runs.started_at < :stale_cutoff)
        RETURNING id, attempt_count
    """), {"workspace_id": str(workspace_id), "job_name": job_name,
           "period_start": period_start, "now": now,
           "max_attempts": MAX_JOB_ATTEMPTS_PER_PERIOD, "stale_cutoff": stale_cutoff}).first()
    db.commit()
    return (row.id, row.attempt_count) if row else None


def _finish_job_run(db: Session, run_id: int, status: str, error: str | None = None) -> None:
    db.execute(text("""
        UPDATE job_runs SET status = :status, last_error = :error, finished_at = :now
        WHERE id = :id
    """), {"status": status, "error": error, "now": datetime.now(timezone.utc), "id": run_id})
    db.commit()
```

`_rls_enforced` is deliberately NOT checked here (unlike
`_set_job_workspace_context`) — `job_runs` only exists under PostgreSQL
(the migration in Task 1), and these two functions are only ever called
from the `*_all_workspaces` wrappers Task 3 adds, which are themselves only
exercised against PostgreSQL in `tests/postgres/`.

- [ ] **Step 8: Run the Postgres tests again to verify they pass**

Run: `python -m pytest tests/postgres/test_job_runs.py -v`
Expected: PASS.

- [ ] **Step 9: Run both full suites to confirm nothing else regressed**

Run: `python -m pytest tests/ --ignore=tests/postgres -v` and
`python -m pytest tests/postgres/ -v`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add backend/jobs.py backend/tests/test_job_scheduling.py backend/tests/postgres/test_job_runs.py
git commit -m "feat(jobs): add period-bucketed claim/finish idempotency helpers"
```

---

## Task 3: Wire claim/finish into the three `*_all_workspaces` functions

**Files:**
- Modify: `backend/jobs.py` (`autosync_all_workspaces`,
  `dividend_notify_all_workspaces`, `alert_check_all_workspaces`)
- Modify: `backend/tests/postgres/test_job_workspace_isolation.py` (fixture
  swap on one existing test — see Step 1)

**Interfaces:**
- Consumes: `jobs._claim_job_run` / `jobs._finish_job_run` (Task 2).
- Produces: `autosync_all_workspaces`, `dividend_notify_all_workspaces`, and
  `alert_check_all_workspaces` all now commit mid-pass (previously only
  `autosync_all_workspaces` and `dividend_notify_all_workspaces` did, via
  the passes they call — `alert_check_all_workspaces` did not). Task 4's
  HTTP endpoint calls these three functions directly with no other change.

- [ ] **Step 1: Fix a real fixture-choice regression before it becomes a false pass**

`backend/tests/postgres/test_job_workspace_isolation.py`'s
`test_alert_check_all_workspaces_processes_both_workspaces_without_leaking`
currently uses `runtime_session` (the savepoint-based fixture) because, per
that file's module docstring, `alert_check_all_workspaces` "never commits
mid-pass." After this task, it will (via `_claim_job_run`/`_finish_job_run`).
`runtime_session`'s `.commit()` operates on a nested SAVEPOINT and never
really ends the outer Postgres transaction — the transaction-local
`portfyl.workspace_id` GUC the claim depends on wouldn't actually reset
there, which is exactly the false-negative failure mode Bug 2's tests in
this same file already document. Fix the test *first*, before Step 2 makes
the underlying claim exist, so you can see the difference:

Change the test's signature and the comment above it from:

```python
# ---------------------------------------------------------------------------
# Bug 1 (black box) + cross-tenant isolation: alert_check_all_workspaces
# never commits mid-pass, so runtime_session (savepoint-based) is fine here.
# ---------------------------------------------------------------------------


def test_alert_check_all_workspaces_processes_both_workspaces_without_leaking(
    postgres_engine: Engine, workspace_pair, runtime_session: Session,
):
```

to:

```python
# ---------------------------------------------------------------------------
# Bug 1 (black box) + cross-tenant isolation. alert_check_all_workspaces now
# commits mid-pass too (the job_runs claim/finish pair added for external job
# triggering -- see docs/superpowers/specs/2026-09-03-portfyl-job-triggering-design.md),
# so this needs runtime_job_session (real commits), not runtime_session
# (savepoint-based -- see the module docstring's "Why this file defines its
# own runtime_job_session fixture" section for why that would be a false
# pass here). Ordering note from the module docstring applies: workspace_pair
# must stay listed before runtime_job_session.
# ---------------------------------------------------------------------------


def test_alert_check_all_workspaces_processes_both_workspaces_without_leaking(
    postgres_engine: Engine, workspace_pair, runtime_job_session: Session,
):
```

And, in the test body itself, change the one remaining `runtime_session`
reference:

```python
        fired = asyncio.run(alert_check_all_workspaces(runtime_session))
```

to:

```python
        fired = asyncio.run(alert_check_all_workspaces(runtime_job_session))
```

Nothing else in the body changes — the `postgres_engine`/`_owner_session`
seeding above it and the `fired_tickers` assertion below it stay as they are.

- [ ] **Step 2: Run the affected test to confirm it still passes on old code**

Run: `python -m pytest tests/postgres/test_job_workspace_isolation.py::test_alert_check_all_workspaces_processes_both_workspaces_without_leaking -v`
Expected: PASS (the fixture swap alone doesn't change behavior yet — this
just proves `runtime_job_session` is a safe drop-in before you add commits
that depend on it).

- [ ] **Step 3: Wrap `autosync_all_workspaces`**

In `backend/jobs.py`, replace:

```python
async def autosync_all_workspaces(db: Session, now: datetime | None = None) -> list[dict]:
    """Poller entry point for broker auto-sync: explicit per-workspace tick
    across every active workspace."""
    results: list[dict] = []
    for workspace_id in _active_workspace_ids(db):
        _set_job_workspace_context(db, workspace_id)
        results.extend(await autosync_tick(db, workspace_id, now=now))
    return results
```

with:

```python
async def autosync_all_workspaces(db: Session, now: datetime | None = None) -> list[dict]:
    """Poller entry point for broker auto-sync: explicit per-workspace tick
    across every active workspace, one job_runs claim per workspace so an
    overlapping in-process tick or external trigger retry can't double-run
    the same workspace's pass within one period."""
    now = now or datetime.now(timezone.utc)
    results: list[dict] = []
    for workspace_id in _active_workspace_ids(db):
        _set_job_workspace_context(db, workspace_id)
        claim = _claim_job_run(db, "autosync", workspace_id, now)
        if claim is None:
            continue
        run_id, attempt = claim
        _set_job_workspace_context(db, workspace_id)
        try:
            passed = await autosync_tick(db, workspace_id, now=now)
        except Exception as e:
            _set_job_workspace_context(db, workspace_id)
            status = "dead_letter" if attempt >= MAX_JOB_ATTEMPTS_PER_PERIOD else "failed"
            _finish_job_run(db, run_id, status, error=str(e))
            log.exception("autosync pass failed for workspace %s", workspace_id)
            continue
        _set_job_workspace_context(db, workspace_id)
        _finish_job_run(db, run_id, "succeeded")
        results.extend(passed)
    return results
```

- [ ] **Step 4: Wrap `dividend_notify_all_workspaces`**

Replace:

```python
async def dividend_notify_all_workspaces(db: Session, today: date | None = None,
                                         lead_days: int = 3) -> list[dict]:
    """Poller entry point for ex-dividend notifications: explicit per-workspace
    pass across every active workspace."""
    results: list[dict] = []
    for workspace_id in _active_workspace_ids(db):
        _set_job_workspace_context(db, workspace_id)
        results.extend(await dividend_exdate_pass(db, workspace_id, today=today, lead_days=lead_days))
    return results
```

with:

```python
async def dividend_notify_all_workspaces(db: Session, today: date | None = None,
                                         lead_days: int = 3,
                                         now: datetime | None = None) -> list[dict]:
    """Poller entry point for ex-dividend notifications: explicit per-workspace
    pass across every active workspace, job_runs-claimed the same way as
    autosync_all_workspaces (see its docstring)."""
    now = now or datetime.now(timezone.utc)
    results: list[dict] = []
    for workspace_id in _active_workspace_ids(db):
        _set_job_workspace_context(db, workspace_id)
        claim = _claim_job_run(db, "dividend_notify", workspace_id, now)
        if claim is None:
            continue
        run_id, attempt = claim
        _set_job_workspace_context(db, workspace_id)
        try:
            passed = await dividend_exdate_pass(db, workspace_id, today=today, lead_days=lead_days)
        except Exception as e:
            _set_job_workspace_context(db, workspace_id)
            status = "dead_letter" if attempt >= MAX_JOB_ATTEMPTS_PER_PERIOD else "failed"
            _finish_job_run(db, run_id, status, error=str(e))
            log.exception("dividend-notify pass failed for workspace %s", workspace_id)
            continue
        _set_job_workspace_context(db, workspace_id)
        _finish_job_run(db, run_id, "succeeded")
        results.extend(passed)
    return results
```

- [ ] **Step 5: Wrap `alert_check_all_workspaces`**

Replace:

```python
async def alert_check_all_workspaces(db: Session) -> list[dict]:
    """Poller entry point for price alerts: explicit per-workspace check
    across every active workspace."""
    from routers.alerts import run_check  # lazy: avoids importing market_data/discord at module load

    results: list[dict] = []
    for workspace_id in _active_workspace_ids(db):
        _set_job_workspace_context(db, workspace_id)
        results.extend(await run_check(db, workspace_id))
    return results
```

with:

```python
async def alert_check_all_workspaces(db: Session, now: datetime | None = None) -> list[dict]:
    """Poller entry point for price alerts: explicit per-workspace check
    across every active workspace, job_runs-claimed the same way as
    autosync_all_workspaces (see its docstring)."""
    from routers.alerts import run_check  # lazy: avoids importing market_data/discord at module load

    now = now or datetime.now(timezone.utc)
    results: list[dict] = []
    for workspace_id in _active_workspace_ids(db):
        _set_job_workspace_context(db, workspace_id)
        claim = _claim_job_run(db, "alert_check", workspace_id, now)
        if claim is None:
            continue
        run_id, attempt = claim
        _set_job_workspace_context(db, workspace_id)
        try:
            fired = await run_check(db, workspace_id)
        except Exception as e:
            _set_job_workspace_context(db, workspace_id)
            status = "dead_letter" if attempt >= MAX_JOB_ATTEMPTS_PER_PERIOD else "failed"
            _finish_job_run(db, run_id, status, error=str(e))
            log.exception("alert-check pass failed for workspace %s", workspace_id)
            continue
        _set_job_workspace_context(db, workspace_id)
        _finish_job_run(db, run_id, "succeeded")
        results.extend(fired)
    return results
```

- [ ] **Step 6: Add an idempotency regression test for the wrapped functions**

Append to `backend/tests/postgres/test_job_runs.py`:

```python
from unittest.mock import AsyncMock, patch

from jobs import alert_check_all_workspaces


async def _run_twice(coro_fn, *args, **kwargs):
    first = await coro_fn(*args, **kwargs)
    second = await coro_fn(*args, **kwargs)
    return first, second


def test_alert_check_all_workspaces_skips_a_second_call_in_the_same_period(
    single_workspace, runtime_job_session: Session,
):
    # alert_check_all_workspaces does `from routers.alerts import run_check`
    # as a fresh local import on every call (see its lazy-import comment in
    # jobs.py) -- patch it at its origin, routers.alerts.run_check, not on
    # the jobs module, or the patch never takes effect.
    import asyncio
    ws, _ = single_workspace
    fake_run_check = AsyncMock(return_value=[{"ticker": "AAPL"}])
    with patch("routers.alerts.run_check", fake_run_check):
        first, second = asyncio.run(_run_twice(
            alert_check_all_workspaces, runtime_job_session, now=NOW))

    assert first == [{"ticker": "AAPL"}]
    assert second == []  # second call's claim for the same period is rejected
    assert fake_run_check.await_count == 1
```

- [ ] **Step 7: Run the new test to verify it passes**

Run: `python -m pytest tests/postgres/test_job_runs.py::test_alert_check_all_workspaces_skips_a_second_call_in_the_same_period -v`
Expected: PASS.

- [ ] **Step 8: Run the full Postgres suite to confirm no regressions**

Run: `python -m pytest tests/postgres/ -v`
Expected: PASS — in particular
`test_job_workspace_isolation.py`'s existing Bug 1/Bug 2 tests, which now
exercise the claim-wrapped functions, must still pass unmodified in intent.

- [ ] **Step 9: Commit**

```bash
git add backend/jobs.py backend/tests/postgres/test_job_workspace_isolation.py backend/tests/postgres/test_job_runs.py
git commit -m "feat(jobs): claim/finish-wrap the three *_all_workspaces entry points"
```

---

## Task 4: `POST /api/jobs/run` endpoint

**Files:**
- Create: `backend/routers/scheduler.py`
- Modify: `backend/main.py` (import + mount)
- Create: `backend/tests/postgres/test_scheduler_router.py`
- Create: `backend/tests/test_scheduler_registry.py` (fast, no DB)

**Interfaces:**
- Consumes: `jobs.alert_check_all_workspaces` / `autosync_all_workspaces` /
  `dividend_notify_all_workspaces` (Task 3), `auth.check_scheduler_token`
  (already exists, `backend/auth.py:174`).
- Produces: `scheduler.router` (mounted at `/api`, giving
  `POST /api/jobs/run?job=<name>`), `scheduler.JOB_REGISTRY`
  (`dict[str, Callable]`, keys `"alert_check"`/`"autosync"`/`"dividend_notify"`)
  — Task 7's deploy docs reference this path and its three `job` values.

- [ ] **Step 1: Write the failing Postgres tests for the endpoint**

Create `backend/tests/postgres/test_scheduler_router.py`:

```python
"""Postgres tests for POST /api/jobs/run (backend/routers/scheduler.py)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from database import get_db
from routers import scheduler


@pytest.fixture
def scheduler_client(postgres_engine) -> TestClient:
    app = FastAPI()
    app.include_router(scheduler.router, prefix="/api")

    def override_get_db():
        with Session(postgres_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client


def test_missing_token_is_rejected(scheduler_client):
    with patch("routers.scheduler.check_scheduler_token", return_value=False):
        response = scheduler_client.post("/api/jobs/run", params={"job": "alert_check"})
    assert response.status_code == 403


def test_valid_token_but_unknown_job_is_rejected(scheduler_client):
    with patch("routers.scheduler.check_scheduler_token", return_value=True):
        response = scheduler_client.post("/api/jobs/run", params={"job": "not_a_real_job"})
    assert response.status_code == 400


def test_valid_token_and_job_dispatches_and_returns_200(scheduler_client):
    fake = AsyncMock(return_value=[{"ticker": "AAPL"}])
    with patch("routers.scheduler.check_scheduler_token", return_value=True), \
         patch.dict(scheduler.JOB_REGISTRY, {"alert_check": fake}):
        response = scheduler_client.post(
            "/api/jobs/run",
            params={"job": "alert_check"},
            headers={"X-Scheduler-Token": "irrelevant-because-mocked"},
        )
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok", "job": "alert_check", "events": 1, "results": [{"ticker": "AAPL"}],
    }
    fake.assert_awaited_once()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/postgres/test_scheduler_router.py -v`
Expected: FAIL — `routers.scheduler` doesn't exist yet (`ImportError`).

- [ ] **Step 3: Create `backend/routers/scheduler.py`**

```python
"""Machine entrypoint for external job triggering (Cloud Scheduler in the
cloud edition). Consolidates alert-check, broker-autosync, and
dividend-notify behind one SCHEDULER_TOKEN-authed endpoint; supersedes the
old IBKR-only /api/ibkr/scheduler-sync -- see
docs/superpowers/specs/2026-09-03-portfyl-job-triggering-design.md."""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from auth import check_scheduler_token
from database import get_db
from jobs import (
    alert_check_all_workspaces,
    autosync_all_workspaces,
    dividend_notify_all_workspaces,
)

router = APIRouter(prefix="/jobs", tags=["scheduler"])

JOB_REGISTRY: dict[str, Callable[[Session], Awaitable[list[dict]]]] = {
    "alert_check": alert_check_all_workspaces,
    "autosync": autosync_all_workspaces,
    "dividend_notify": dividend_notify_all_workspaces,
}


@router.post("/run", include_in_schema=False)
async def run_job(
    job: str = Query(...),
    db: Session = Depends(get_db),
    x_scheduler_token: str | None = Header(default=None),
    token: str | None = Query(default=None),
):
    """token (query param) exists only as a manual-testing fallback --
    Cloud Scheduler always sends X-Scheduler-Token as a header."""
    if not check_scheduler_token(x_scheduler_token or token or ""):
        raise HTTPException(status_code=403, detail="Invalid or missing scheduler token")
    fn = JOB_REGISTRY.get(job)
    if fn is None:
        raise HTTPException(status_code=400, detail=f"Unknown job: {job}")
    results = await fn(db)
    return {"status": "ok", "job": job, "events": len(results), "results": results}
```

- [ ] **Step 4: Mount the router in `main.py`**

In `backend/main.py`, add `scheduler` to the router import (line 17):

```python
from routers import portfolio, market, analytics, broker, portfolios, watchlists, benchmarks, ibkr, options, polymarket, discord, notes, assistant, cash, alerts, settings, capabilities, scheduler, auth as auth_router
```

Then add, right after the `app.include_router(settings.router, ...)` block
(after line 108):

```python
app.include_router(scheduler.router, prefix="/api")
```

- [ ] **Step 5: Run the Postgres tests again to verify they pass**

Run: `python -m pytest tests/postgres/test_scheduler_router.py -v`
Expected: PASS.

- [ ] **Step 6: Add a fast test for the job registry's keys**

Create `backend/tests/test_scheduler_registry.py`:

```python
"""Fast, DB-free test that the scheduler's job registry names exactly the
three jobs the rest of the system (Cloud Scheduler config, docs) expects."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routers.scheduler import JOB_REGISTRY


def test_job_registry_has_exactly_the_three_job_types():
    assert set(JOB_REGISTRY) == {"alert_check", "autosync", "dividend_notify"}
```

Run: `python -m pytest tests/test_scheduler_registry.py -v`
Expected: PASS.

- [ ] **Step 7: Run the full Postgres suite**

Run: `python -m pytest tests/postgres/ -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/routers/scheduler.py backend/main.py backend/tests/postgres/test_scheduler_router.py backend/tests/test_scheduler_registry.py
git commit -m "feat(jobs): add POST /api/jobs/run external trigger endpoint"
```

---

## Task 5: Remove `/api/ibkr/scheduler-sync` (consolidation)

**Files:**
- Modify: `backend/routers/ibkr.py` (delete the endpoint + prune imports)
- Modify: `backend/tests/test_jobs.py` (delete the now-obsolete test, add a
  one-line regression check)
- Modify: `backend/tests/postgres/test_scheduler_router.py` (404 check)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — this task only removes surface area. Coverage for
  "external trigger respects the auto_sync flag" continues to come from
  `test_autosync_skips_connections_without_flag` (`backend/tests/test_jobs.py:49`),
  which now indirectly covers the `autosync` job too since
  `autosync_all_workspaces` → `autosync_tick` → `broker_autosync_pass` is
  the same code path for both the in-process poller and the new HTTP trigger.

- [ ] **Step 1: Delete the obsolete fast unit test**

In `backend/tests/test_jobs.py`, delete
`test_scheduler_sync_respects_auto_sync_flag` (lines 154-176 as of this
plan's writing — find it by name, not line number, since earlier steps in
this plan haven't touched this file). Replace it with:

```python
def test_scheduler_sync_endpoint_is_removed():
    # Consolidated into POST /api/jobs/run?job=autosync (see
    # docs/superpowers/specs/2026-09-03-portfyl-job-triggering-design.md) --
    # broker_autosync_pass already covers both trading212 and ibkr, and
    # already respects the per-connection auto_sync flag (see
    # test_autosync_skips_connections_without_flag above).
    import routers.ibkr as ibkr_module
    assert not hasattr(ibkr_module, "scheduler_sync")
```

- [ ] **Step 2: Run it to verify it fails**

Run (from `backend/`): `python -m pytest tests/test_jobs.py::test_scheduler_sync_endpoint_is_removed -v`
Expected: FAIL — `scheduler_sync` still exists on `routers.ibkr`.

- [ ] **Step 3: Remove the endpoint from `backend/routers/ibkr.py`**

Delete the `scheduler_sync` route entirely — everything from the blank line
before `@router.post("/scheduler-sync", include_in_schema=False)` through
the end of the file (the function is the last thing in the file).

- [ ] **Step 4: Prune now-unused imports in `backend/routers/ibkr.py`**

`Header`, `Query`, `JSONResponse`, and `check_scheduler_token` were used
*only* inside the endpoint just removed. Change:

```python
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from datetime import datetime, date
from collections import defaultdict
from uuid import UUID
import asyncio
import json
import httpx
import xml.etree.ElementTree as ET

from database import get_db
from models import BrokerConnection, OptionsTrade, BrokerBalance, Portfolio
from tenancy import RequestContext, require_csrf, require_portfolio
from auth import check_scheduler_token
```

to:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, date
from collections import defaultdict
from uuid import UUID
import asyncio
import json
import httpx
import xml.etree.ElementTree as ET

from database import get_db
from models import BrokerConnection, OptionsTrade, BrokerBalance, Portfolio
from tenancy import RequestContext, require_csrf, require_portfolio
```

(`UUID` stays — it's used elsewhere in this file, e.g. `_run_ibkr_sync`'s
`workspace_id: UUID` parameter.)

- [ ] **Step 5: Run the fast test again to verify it passes**

Run: `python -m pytest tests/test_jobs.py::test_scheduler_sync_endpoint_is_removed -v`
Expected: PASS.

- [ ] **Step 6: Add the 404 regression test to the Postgres suite**

Append to `backend/tests/postgres/test_scheduler_router.py`:

```python
def test_ibkr_scheduler_sync_route_no_longer_exists(postgres_engine):
    from routers import ibkr

    app = FastAPI()
    app.include_router(ibkr.router, prefix="/api")

    def override_get_db():
        with Session(postgres_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        response = client.post("/api/broker/ibkr/scheduler-sync")
    assert response.status_code == 404
```

- [ ] **Step 7: Run both fast and Postgres suites in full**

Run: `python -m pytest tests/ --ignore=tests/postgres -v` and
`python -m pytest tests/postgres/ -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/routers/ibkr.py backend/tests/test_jobs.py backend/tests/postgres/test_scheduler_router.py
git commit -m "refactor(jobs): remove /api/ibkr/scheduler-sync, superseded by /api/jobs/run"
```

---

## Task 6: Edition-aware in-process poller defaults

**Files:**
- Modify: `backend/main.py` (`_start_background_pollers`)
- Modify: `backend/tests/test_edition_routes.py` (two new tests)

**Interfaces:**
- Consumes: `edition.Edition` (already imported in `main.py`).
- Produces: `main._poller_env_default(edition: Edition) -> str` — a pure
  function, so tests don't need to trigger the FastAPI startup event.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_edition_routes.py`:

```python
def test_poller_env_default_is_enabled_for_local():
    import main

    assert main._poller_env_default(main.Edition.LOCAL) == "1"


def test_poller_env_default_is_disabled_for_cloud():
    import main

    assert main._poller_env_default(main.Edition.CLOUD) == "0"
```

- [ ] **Step 2: Run them to verify they fail**

Run (from `backend/`): `python -m pytest tests/test_edition_routes.py::test_poller_env_default_is_enabled_for_local -v`
Expected: FAIL — `AttributeError: module 'main' has no attribute '_poller_env_default'`.

- [ ] **Step 3: Add `_poller_env_default` and use it in `backend/main.py`**

Add, right before the `_BG_TASKS: list = []` line:

```python
def _poller_env_default(edition: Edition) -> str:
    """The in-process pollers' default enabled/disabled state per edition:
    local is always single-instance self-hosted (safe to default on); cloud
    is multi-instance/scale-to-zero and must default to external triggering
    only (see POST /api/jobs/run in routers/scheduler.py). Always
    explicitly overridable via the env vars below."""
    return "1" if edition is Edition.LOCAL else "0"
```

Then change the three `os.environ.get(..., "1")` calls inside
`_start_background_pollers`:

```python
    if os.environ.get("ALERT_POLLER_ENABLED", _poller_env_default(PORTFYL_EDITION)) == "1":
```

```python
    if os.environ.get("BROKER_AUTOSYNC_ENABLED", _poller_env_default(PORTFYL_EDITION)) == "1":
```

```python
    if os.environ.get("DIVIDEND_NOTIFY_ENABLED", _poller_env_default(PORTFYL_EDITION)) == "1":
```

- [ ] **Step 4: Run the tests again to verify they pass**

Run: `python -m pytest tests/test_edition_routes.py -v`
Expected: PASS (all tests in the file, including the pre-existing ones —
`_reload_main`'s `finally: _reload_main(monkeypatch, "local")` in
`test_cloud_edition_omits_owner_only_routes_from_openapi_and_dispatch`
still leaves the process on the local edition afterward, unaffected by this
change).

- [ ] **Step 5: Run the full fast suite**

Run: `python -m pytest tests/ --ignore=tests/postgres -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/tests/test_edition_routes.py
git commit -m "feat(edition): default in-process job pollers off for cloud"
```

---

## Task 7: Deploy docs, auth.py comment, CLAUDE.md

**Files:**
- Modify: `deploy/cloudrun.md`
- Modify: `backend/auth.py` (comment only, lines 169-170)
- Modify: `CLAUDE.md`

No tests — documentation only. This task has no code to verify by running,
so there's no TDD cycle; just make the edits and read them back for
accuracy against the endpoint/env-var names Tasks 4 and 6 actually landed.

- [ ] **Step 1: Update the `auth.py` comment**

Change:

```python
# Cloud Scheduler keeps its separate machine credential until the jobs
# workstream replaces the in-process scheduler architecture.
SCHEDULER_TOKEN = os.getenv("SCHEDULER_TOKEN")
```

to:

```python
# Shared secret between Cloud Scheduler and POST /api/jobs/run
# (routers/scheduler.py) -- see deploy/cloudrun.md's "Configure Cloud
# Scheduler" section for how it's provisioned.
SCHEDULER_TOKEN = os.getenv("SCHEDULER_TOKEN")
```

- [ ] **Step 2: Add the Cloud Scheduler section to `deploy/cloudrun.md`**

Insert a new `## 9. Configure Cloud Scheduler` section between the end of
`## 8. Cost guards (one-time, recommended)` (after the `--dry-run`/
`--no-dry-run` paragraph, before the `---` that precedes `## Ongoing rules`):

```markdown
## 9. Configure Cloud Scheduler

Job triggering is external, not in-process, in the cloud edition (see
`docs/superpowers/specs/2026-09-03-portfyl-job-triggering-design.md`) --
`ALERT_POLLER_ENABLED`/`BROKER_AUTOSYNC_ENABLED`/`DIVIDEND_NOTIFY_ENABLED`
default to `"0"` for `PORTFYL_EDITION=cloud`. Without the three jobs below
configured, alerts, broker autosync, and dividend notifications never run.

Generate and store the scheduler token — a shared secret between Cloud
Scheduler and `POST /api/jobs/run` (`backend/auth.py`'s
`check_scheduler_token`):

```powershell
gcloud secrets create portfyl-scheduler-token --replication-policy=automatic
# generate one: [Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Max 256 }))
gcloud secrets versions add portfyl-scheduler-token --data-file=- # paste the generated token, then Ctrl+Z, Enter
gcloud secrets add-iam-policy-binding portfyl-scheduler-token --member="serviceAccount:portfyl-runtime@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
```

Attach it to the running service:

```powershell
gcloud run services update $SERVICE --region $REGION --update-secrets="SCHEDULER_TOKEN=portfyl-scheduler-token:latest"
```

Three Cloud Scheduler jobs, one per job type, each `POST`ing to
`/api/jobs/run?job=<name>` with the token as a header (the endpoint also
accepts a `token` query param, but that's a manual-testing fallback only —
never use it here, since query params can end up in logs):

```powershell
$SERVICE_URL = gcloud run services describe $SERVICE --region $REGION --format="value(status.url)"
$SCHEDULER_TOKEN = gcloud secrets versions access latest --secret=portfyl-scheduler-token

gcloud scheduler jobs create http portfyl-alert-check --location=$REGION --schedule="*/15 * * * *" --uri="$SERVICE_URL/api/jobs/run?job=alert_check" --http-method=POST --headers="X-Scheduler-Token=$SCHEDULER_TOKEN"
gcloud scheduler jobs create http portfyl-autosync --location=$REGION --schedule="*/5 * * * *" --uri="$SERVICE_URL/api/jobs/run?job=autosync" --http-method=POST --headers="X-Scheduler-Token=$SCHEDULER_TOKEN"
gcloud scheduler jobs create http portfyl-dividend-notify --location=$REGION --schedule="0 6 * * *" --uri="$SERVICE_URL/api/jobs/run?job=dividend_notify" --http-method=POST --headers="X-Scheduler-Token=$SCHEDULER_TOKEN"
```

Cron intervals match the `job_runs` period-bucket sizes
(`ALERT_CHECK_INTERVAL_SECONDS`=900, `AUTOSYNC_TRIGGER_INTERVAL_SECONDS`=300,
`DIVIDEND_NOTIFY_INTERVAL_SECONDS`=43200 by default). If you override one of
those env vars, update the matching job's `--schedule` to stay roughly in
sync — the idempotency claim makes a too-frequent schedule harmless (extra
calls within a period are just skipped), but a too-infrequent one means
that job effectively runs less often than you think.

The service is already `--allow-unauthenticated` (step 6), so Cloud
Scheduler doesn't need its own OIDC identity to call it — `X-Scheduler-Token`
is the only auth this endpoint checks.
```

- [ ] **Step 3: Update `CLAUDE.md`'s pending-work list**

In the root `CLAUDE.md`, in the "In-progress: multi-user SaaS conversion"
section, change:

```
What's
**still pending**: Workstream A's external product/data validation and
commercial market-data rights, KMS envelope encryption for broker/AI
secrets, an external scheduler replacing the in-process background jobs in
`backend/jobs.py`, Stripe billing, and onboarding. Don't jump ahead to
billing/onboarding work before secrets/jobs land,
```

to:

```
What's
**still pending**: Workstream A's external product/data validation and
commercial market-data rights, KMS envelope encryption for broker/AI
secrets, structured logging/redaction and dependency-aware health checks,
Stripe billing, and onboarding. External job triggering (Cloud Scheduler
replacing the in-process pollers, `POST /api/jobs/run`) is done — see
`docs/superpowers/specs/2026-09-03-portfyl-job-triggering-design.md`. Don't
jump ahead to billing/onboarding work before secrets/observability land,
```

- [ ] **Step 4: Commit**

```bash
git add deploy/cloudrun.md backend/auth.py CLAUDE.md
git commit -m "docs(jobs): document Cloud Scheduler setup, update pending-work list"
```

---

## After all tasks: finishing the branch

Once Tasks 1-7 are complete and both suites pass in full, use
`superpowers:finishing-a-development-branch` to verify and integrate —
per this repo's `CLAUDE.md`, run `cd backend && python -m pytest tests/ -v`
(fast suite) and `python -m pytest tests/postgres/ -v` (Postgres suite,
requires Docker Desktop or `TEST_DATABASE_URL`) one more time as the final
check before deciding how to merge.
