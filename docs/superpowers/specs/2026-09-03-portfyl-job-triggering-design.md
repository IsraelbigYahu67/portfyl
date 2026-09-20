# External, idempotent job triggering — Design

> Sub-project 1 of Workstream D (see
> `docs/superpowers/plans/2026-09-03-portfyl-secrets-jobs-prompt.md`). Scope:
> replace the in-process asyncio job pollers with an externally-triggerable,
> idempotent, tenant-aware mechanism safe for a multi-instance, scale-to-zero
> Cloud Run deployment. Secrets encryption and structured logging/health
> checks are separate sub-projects (2 and 3) and out of scope here.

## Problem

`deploy/cloudrun.md` runs the service at `--min-instances=0 --max-instances=5`.
`backend/main.py`'s `_start_background_pollers` (`@app.on_event("startup")`)
spawns three `asyncio.create_task` loops — alert-check, broker autosync,
dividend-notify — on every instance. At 5 instances this produces up to 5x
duplicate broker syncs, dividend e-mails, and alert fires; at 0 instances,
nothing fires between requests. This is a live correctness bug on the
currently-deployed config.

A partial precedent already exists: `POST /api/ibkr/scheduler-sync`
(`backend/routers/ibkr.py:667`), `SCHEDULER_TOKEN`-authed
(`backend/auth.py:171-180`), but IBKR-only, runs unconditionally (ignores
each workspace's configured sync schedule), and is not wired into any Cloud
Scheduler job today (`deploy/` has no reference to it).

## Decisions

- **Consolidate, don't duplicate.** `POST /api/ibkr/scheduler-sync` is
  removed. The new `autosync` job (below) already covers IBKR + Trading212
  via `broker_autosync_pass` and respects each workspace's configured
  schedule — it supersedes the IBKR-only endpoint rather than living
  alongside it.
- **One shared trigger endpoint**, not three. Less duplicated auth/response
  handling; one idempotency code path all three job types share.
- **Idempotency and dead-lettering share one mechanism**: a `job_runs`
  table keyed `(job_name, workspace_id, period_start)`. A unique-constraint
  claim (`INSERT ... ON CONFLICT DO UPDATE ... RETURNING`) is both the
  concurrency guard the brief asks for and the attempt-count/dead-letter
  state — no separate advisory lock.
- **The claim wraps the per-workspace call inside the existing
  `*_all_workspaces` functions** (`jobs.py`), not the new HTTP endpoint.
  This means the local edition's in-process pollers get the same
  idempotency protection for free (defense in depth against an overlapping
  tick), and the external trigger and the in-process poller share one code
  path with no duplicated locking logic.
- **Edition gating stays in `main.py`**, not `edition.py`. The existing
  `ALERT_POLLER_ENABLED` / `BROKER_AUTOSYNC_ENABLED` / `DIVIDEND_NOTIFY_ENABLED`
  env vars keep working exactly as before, but their *default* becomes
  edition-aware (`"1"` for local, `"0"` for cloud) instead of hardcoded
  `"1"`. `edition.py`'s `CAPABILITY_REGISTRY` classifies product surfaces
  for plan enforcement — a different concern from deployment topology — and
  is not touched.

## Data model

New table `job_runs` (migration `0004_job_runs.py`, following the
`0002_tenant_rls.py` / `0003_job_workspace_enumeration.py` pattern —
created with forced RLS and a standard `workspace_id`-scoped tenant policy
identical to the other `_WORKSPACE_TABLES` entries; granted to
`portfyl_runtime` the same way):

```python
class JobRun(Base):
    __tablename__ = "job_runs"
    __table_args__ = (
        UniqueConstraint("job_name", "workspace_id", "period_start",
                          name="uq_job_run_period"),
    )

    id = Column(Integer, primary_key=True, index=True)
    workspace_id = _workspace_id()
    job_name = Column(String, nullable=False)          # "alert_check" | "autosync" | "dividend_notify"
    period_start = Column(DateTime(timezone=True), nullable=False)
    status = Column(String, nullable=False, default="running")  # running | succeeded | failed | dead_letter
    attempt_count = Column(Integer, nullable=False, default=1)
    last_error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
```

No `public_id` — this is an internal-only table, never serialized to a
client.

## Claim/finish helpers (`backend/jobs.py`)

```python
MAX_JOB_ATTEMPTS_PER_PERIOD = 3
JOB_RUN_STALE_AFTER = timedelta(minutes=10)

JOB_PERIOD_SECONDS = {
    "alert_check": lambda: _env_int("ALERT_CHECK_INTERVAL_SECONDS", 900),
    "autosync": lambda: _env_int("AUTOSYNC_TRIGGER_INTERVAL_SECONDS", 300),
    "dividend_notify": lambda: _env_int("DIVIDEND_NOTIFY_INTERVAL_SECONDS", 43200),
}

def _period_start(now: datetime, job_name: str) -> datetime:
    bucket = JOB_PERIOD_SECONDS[job_name]()
    epoch = now.timestamp()
    return datetime.fromtimestamp((epoch // bucket) * bucket, tz=timezone.utc)

def _claim_job_run(db: Session, job_name: str, workspace_id: UUID, now: datetime) -> int | None:
    """Atomically claim this workspace's job_name pass for now's period.
    Returns the job_runs.id to finish later, or None if another run already
    owns this period (running and not stale, succeeded, or dead-lettered)."""
    period_start = _period_start(now, job_name)
    stale_cutoff = now - JOB_RUN_STALE_AFTER
    row = db.execute(text("""
        INSERT INTO job_runs (workspace_id, job_name, period_start, status, attempt_count, started_at)
        VALUES (:workspace_id, :job_name, :period_start, 'running', 1, :now)
        ON CONFLICT (job_name, workspace_id, period_start) DO UPDATE
        SET status = 'running', attempt_count = job_runs.attempt_count + 1, started_at = :now
        WHERE job_runs.status = 'failed' AND job_runs.attempt_count < :max_attempts
           OR (job_runs.status = 'running' AND job_runs.started_at < :stale_cutoff)
        RETURNING id
    """), {"workspace_id": str(workspace_id), "job_name": job_name,
           "period_start": period_start, "now": now,
           "max_attempts": MAX_JOB_ATTEMPTS_PER_PERIOD, "stale_cutoff": stale_cutoff}).first()
    db.commit()
    return row.id if row else None

def _finish_job_run(db: Session, run_id: int, status: str, error: str | None = None) -> None:
    db.execute(text("""
        UPDATE job_runs SET status = :status, last_error = :error, finished_at = :now
        WHERE id = :id
    """), {"status": status, "error": error, "now": datetime.now(timezone.utc), "id": run_id})
    db.commit()
```

`_claim_job_run` commits immediately after claiming so a concurrent
claimant (a different Cloud Run instance, or an overlapping in-process tick)
sees the committed `running` row and is rejected by the `WHERE` clause
rather than blocking on the row lock for the duration of the pass.

On a failing attempt, `_finish_job_run` is called with `status="failed"` if
`attempt_count < MAX_JOB_ATTEMPTS_PER_PERIOD`, else `"dead_letter"` — the
caller checks the row's `attempt_count` (returned alongside `id`, or
re-queried) to decide which. Since `period_start` moves forward every job
run, a `dead_letter` in one period doesn't block retries in the next; a
permanently-broken connection just keeps failing (and getting logged) once
per period rather than being retried in a tight loop within one.

Every one of `autosync_all_workspaces`, `dividend_notify_all_workspaces`,
`alert_check_all_workspaces` wraps its per-workspace call:

```python
async def autosync_all_workspaces(db: Session, now: datetime | None = None) -> list[dict]:
    results: list[dict] = []
    now = now or datetime.now(timezone.utc)
    for workspace_id in _active_workspace_ids(db):
        _set_job_workspace_context(db, workspace_id)
        run_id = _claim_job_run(db, "autosync", workspace_id, now)
        if run_id is None:
            continue
        _set_job_workspace_context(db, workspace_id)  # the claim's own commit dropped it
        try:
            results.extend(await autosync_tick(db, workspace_id, now=now))
        except Exception as e:
            _set_job_workspace_context(db, workspace_id)
            attempt = db.execute(text("SELECT attempt_count FROM job_runs WHERE id = :id"),
                                  {"id": run_id}).scalar()
            status = "dead_letter" if attempt >= MAX_JOB_ATTEMPTS_PER_PERIOD else "failed"
            _finish_job_run(db, run_id, status, error=str(e))
            log.exception("autosync pass failed for workspace %s", workspace_id)
            continue
        _set_job_workspace_context(db, workspace_id)
        _finish_job_run(db, run_id, "succeeded")
    return results
```

(`dividend_notify_all_workspaces` and `alert_check_all_workspaces` follow
the identical shape, substituting their own pass call and job name.)

## HTTP trigger

New `backend/routers/scheduler.py`:

```python
JOB_REGISTRY: dict[str, Callable[[Session], Awaitable[list[dict]]]] = {
    "alert_check": alert_check_all_workspaces,
    "autosync": autosync_all_workspaces,
    "dividend_notify": dividend_notify_all_workspaces,
}

@router.post("/jobs/run", include_in_schema=False)
async def run_job(
    job: str = Query(...),
    db: Session = Depends(get_db),
    x_scheduler_token: str | None = Header(default=None),
    token: str | None = Query(default=None),
):
    if not check_scheduler_token(x_scheduler_token or token or ""):
        raise HTTPException(status_code=403, detail="Invalid or missing scheduler token")
    fn = JOB_REGISTRY.get(job)
    if fn is None:
        raise HTTPException(status_code=400, detail=f"Unknown job: {job}")
    results = await fn(db)
    return {"status": "ok", "job": job, "events": len(results), "results": results}
```

Mounted in `main.py` alongside the other routers. Always returns 200 for a
valid job name + valid token — per-workspace failures are captured in
`job_runs` and logged, not surfaced as an HTTP error, so a Cloud Scheduler
retry (itself just another claim attempt against the same `period_start`)
never conflicts with the idempotency mechanism above.

## Edition gating (`backend/main.py`)

```python
def _poller_env_default(edition: Edition) -> str:
    return "1" if edition is Edition.LOCAL else "0"
```

Each of the three `os.environ.get("..._ENABLED", "1")` calls in
`_start_background_pollers` becomes
`os.environ.get("..._ENABLED", _poller_env_default(PORTFYL_EDITION))`.
`_poller_env_default` is a plain function so the fast unit suite can assert
`_poller_env_default(Edition.CLOUD) == "0"` and
`_poller_env_default(Edition.LOCAL) == "1"` without booting the app.

## Deploy

`deploy/cloudrun.md` gets a new "Configure Cloud Scheduler" section: three
Cloud Scheduler jobs, each `POST`ing to
`https://<service-url>/api/jobs/run?job=<name>` with header
`X-Scheduler-Token: <SCHEDULER_TOKEN>`, cron matching the period sizes above
(alert_check every 15 min, autosync every 5 min, dividend_notify daily).
The existing "Cloud Scheduler keeps its separate machine credential" comment
at `auth.py:169-170` is updated to reflect that this workstream is what it
was waiting for.

## Out of scope (this sub-project)

- Secrets encryption (sub-project 2).
- Structured logging/redaction and `/health` dependency checks (sub-project 3)
  — `job_runs` is designed so a later health check can query it (e.g. "any
  `dead_letter` or stale `running` row in the last period"), but wiring that
  up is deferred.
- Changing `sync_due`/`load_sync_schedule`'s per-workspace daily/interval
  scheduling semantics — unchanged; the claim is an additional concurrency
  guard layered on top, not a replacement.
- Alice/Bob tenant isolation behavior — `job_runs` reuses the standard
  per-workspace RLS policy already proven by that suite; no new bypass.

## Testing

**Fast unit suite** (`backend/tests/`): `_period_start` bucketing math,
`_poller_env_default` for both editions, `JOB_REGISTRY` contains exactly the
three expected keys.

**Postgres suite** (`backend/tests/postgres/`):
- `job_runs` has forced RLS and the standard tenant policy (extend the
  existing RLS assertion helper if one covers all `_WORKSPACE_TABLES`).
- Two concurrent claims for the same `(job_name, workspace_id, period_start)`
  — via two separate sessions/connections — result in exactly one non-`None`
  claim.
- A claim that fails `MAX_JOB_ATTEMPTS_PER_PERIOD` times within one period
  ends in `status="dead_letter"`; a new period resets it.
- `POST /api/jobs/run` without a valid token returns 403; an unknown `job`
  returns 400; a valid call with a valid token runs and returns 200.
- `POST /api/ibkr/scheduler-sync` returns 404 (removed).
