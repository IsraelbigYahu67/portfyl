# Kickoff prompt: Secrets, jobs, and operational security for Portfyl (Workstream D)

> Scoped kickoff brief for a fresh Claude Code session, extracted from the
> master plan at
> `docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md` §9
> (Workstream D) and §8 (Background work / Secrets and observability). This
> is **not** itself the task-level implementation plan the master plan calls
> for — it's the scoping prompt to hand to `superpowers:writing-plans` (or
> `superpowers:brainstorming` first, if design questions come up) to produce
> that plan, then execute with `superpowers:subagent-driven-development` or
> `superpowers:executing-plans`.

Context: Portfyl's multi-user conversion has completed Workstream B
(PostgreSQL/Alembic foundation) and Workstream C (Firebase identity,
`User → Membership → Workspace` tenancy, UUID API IDs, forced RLS) — see
`docs/superpowers/plans/2026-09-01-portfyl-multiuser-foundation.md`. The
technical edition/capability boundary (Workstream A's coding half) is also
done — see `docs/superpowers/plans/2026-09-03-portfyl-edition-boundary.md`.
Workstream D is next in the master plan's dependency order (§10 Phase 1);
Workstream E (Stripe/billing) must not start before it.

Read the master plan before starting — it has the full constraints,
architecture (§8), and go/no-go checklist (§14) items this workstream must
satisfy.

## Goal

Encrypt broker/webhook/AI secrets at rest, replace the in-process background
job pollers with an externally-triggered, tenant-aware, idempotent mechanism
safe for a multi-instance Cloud Run deployment, and add the logging/health
observability the master plan requires before any billing work begins.

## Why this is urgent, not just future-proofing

`deploy/cloudrun.md:191` already deploys the service with
`--min-instances=0 --max-instances=5`. `backend/main.py:116-134`'s own
comment says: *"The app has no external scheduler, so asyncio tasks handle
the recurring work"* — `_start_background_pollers`
(`@app.on_event("startup")`, `main.py:162-206`) spawns three
`asyncio.create_task` loops (`_periodic_loop`, `main.py:138-159`, tracked in
`_BG_TASKS` at `135`) gated by `ALERT_POLLER_ENABLED` (`183`),
`BROKER_AUTOSYNC_ENABLED` (`188`), `DIVIDEND_NOTIFY_ENABLED` (`196`) —
all default-enabled (`"1"`).

At `max-instances=5`, every live instance runs its own copy of all three
loops: a burst of traffic can produce up to 5x duplicate broker syncs,
duplicate dividend-notification e-mails, and duplicate alert firing. At
`min-instances=0`, when Cloud Run scales to zero between requests, **no
scheduled job fires at all** until the next HTTP request cold-starts an
instance. Both are live correctness problems on the currently-deployed
config, not hypothetical scaling concerns — treat the job-duplication /
job-silence fix as this workstream's highest-priority deliverable.

## In scope

### 1. Encrypt secrets at rest

Three plaintext secret locations, confirmed by grep (no `encrypt`,
`decrypt`, `Fernet`, or `kms` hits anywhere in the repo today; no
`cryptography` or `google-cloud-kms` dependency in `backend/requirements.txt`,
which currently lists `fastapi, uvicorn, sqlalchemy, yfinance, pandas, numpy,
python-multipart, pydantic, httpx, tzdata, mcp, beautifulsoup4, alembic,
psycopg[binary], firebase-admin`):

- `BrokerConnection.api_key` / `.api_secret` — `backend/models.py:346-348`,
  plain `String` columns.
- `DiscordWebhook.webhook_url` — `backend/models.py:473`, plain `String`.
  Read/write round-trips plaintext through `backend/routers/discord.py`
  (`71`, `76-79`, `101-102`, `147`, `184`); the only existing "redaction" is
  cosmetic truncation for display (`discord.py:52`,
  `hook.webhook_url[:40] + "..."`), not encryption at rest.
- The AI assistant key (DeepSeek, not OpenAI/Anthropic) has no dedicated
  column — it's stored via the generic `UserSetting.value`
  (`backend/models.py:133-145`, a `Text` column) under
  `KEY_SETTING = "deepseek_api_key"` (`backend/routers/assistant.py:21`).
  Write: `assistant.py:212-228` (`set_user_setting(db,
  request_context.user.id, KEY_SETTING, api_key)`). Read: `assistant.py:198-209,
  263-264`. Only a `_key_preview` helper redacts it for API responses — not
  storage.

Deliverable (master plan §2 "Secrets are plaintext" + §8 "Secrets and
observability"): envelope encryption with a cloud KMS-managed key;
ciphertext and key version stored in the database; secrets removed from
logs, errors, analytics, and support exports; an explicit rotation and
disconnect flow; broker connection tests that never use real customer
credentials. Design whether this is one shared `EncryptedSecret` column type
reused across `BrokerConnection`, `DiscordWebhook`, and the assistant
setting, or three separate call sites against one KMS helper module — either
is acceptable, but don't leave any of the three unencrypted.

### 2. Replace in-process pollers with external, idempotent job triggering

`backend/jobs.py` (626 lines) already has the tenant-aware plumbing this
needs: `autosync_all_workspaces` (`596`), `dividend_notify_all_workspaces`
(`606`), `alert_check_all_workspaces` (`617`) each loop
`_active_workspace_ids(db)` (`552`) then call `_set_job_workspace_context(db,
workspace_id)` (`581`, sets `portfyl.workspace_id` for RLS) before running
that workspace's pass — this is a per-workspace RLS-scoped loop, not a
global query filtered in Python. Reuse this plumbing; the gap is *how it's
triggered*, not *how it scopes tenants*.

A partial precedent for the target shape already exists:
`POST /api/ibkr/scheduler-sync` (`backend/routers/ibkr.py:667-699`,
`include_in_schema=False`) is externally triggerable over HTTP, guarded by
`SCHEDULER_TOKEN` (`backend/auth.py:171`, checked via
`check_scheduler_token` / `hmac.compare_digest` at `174-179`), and already
calls into the same `_active_workspace_ids` / `_set_job_workspace_context`
helpers. `auth.py:169-170` has a comment left for exactly this workstream:
*"Cloud Scheduler keeps its separate machine credential until the jobs
workstream replaces the in-process scheduler architecture."* — but only
IBKR autosync has this endpoint today; alert-check and dividend-notify are
still asyncio-loop-only.

In scope:

- Add `scheduler-sync`-shaped external-trigger endpoints (or one shared
  endpoint with a job-name parameter) for alert-check and dividend-notify,
  mirroring the IBKR one's `SCHEDULER_TOKEN` auth.
- Add idempotency: a DB unique constraint or advisory lock per
  (job type, workspace, period) so an overlapping or retried external
  trigger can't double-run a pass. None of `sync_due` (`jobs.py:114`),
  `next_sync_run` (`131`), `mark_sync_ran` (`193`), or the dividend dedup
  table currently guard against *concurrent* duplicate triggers, only
  against re-running an already-completed period.
- Add bounded retries and a dead-letter/poison-job state for a pass that
  keeps failing — nothing like this exists today (`_periodic_loop`,
  `main.py:156-159`, just logs and waits for the next tick forever).
- Decide how local vs. cloud edition should behave, following the pattern
  in `backend/edition.py` (99 lines: `Edition` `StrEnum` `local`/`cloud`
  at `11-13`, `CapabilityClass` `StrEnum` at `16-20`, frozen `Capability`
  dataclass at `23-26`, `CAPABILITY_REGISTRY` built via `_capability()` at
  `36-59`, helpers `edition_from_env` / `edition_allows` /
  `available_capabilities` / `capability_payload` at `62-99`). The local
  edition is always single-instance self-hosted, so keeping
  `_start_background_pollers`'s in-process loops as its default is
  reasonable and shouldn't force a self-hosted owner to configure Cloud
  Scheduler. The cloud edition must default to external triggering only —
  design exactly how that's gated (env var read directly, or added to the
  edition registry) as part of the task-level plan, not this brief.
- Once external triggering is verified working and idempotent for all three
  job types, disable the in-process loops for the cloud edition (`deploy/
  cloudrun.md` will need a "configure Cloud Scheduler" section added
  alongside the existing deploy steps).

### 3. Structured logging and redaction

Only three `logging.getLogger` call sites exist in the whole backend:
`jobs.py:77` (`log = logging.getLogger("portfyl.jobs")`), `main.py:13,143`,
and `routers/portfolio.py:394`. There is no `logging.basicConfig` anywhere
and no correlation-ID / request-ID middleware — `main.py:52`'s
`CORSMiddleware` registration is the *only* middleware in the app. No
redaction logic exists.

Deliverable (master plan §8): structured logs carrying correlation IDs but
redacting secret values (broker keys, webhook URLs, the assistant API key —
all three from part 1 above); error monitoring that groups failures without
leaking private holdings by default; audit events recording security- and
financial-data-mutating actions.

### 4. Health checks

`GET /health` (`backend/main.py:111-113`) is static:

```python
@app.get("/health")
def health():
    return {"status": "ok"}
```

No dependency checks at all. Deliverable (master plan §8): distinguish web,
database, scheduler, broker, and market-data availability — decide the
response shape (e.g. per-dependency status map) as part of the task-level
plan.

## Explicitly out of scope for this task (separate future plans)

- Workstream A's remaining non-technical items (user interviews, commercial
  data-vendor quotes/rights, pricing-page validation) — unrelated to this
  workstream's code.
- Stripe/billing/trial/entitlements (Workstream E) — must not start before
  this workstream lands, per the master plan's dependency order.
- Onboarding/paid packaging UI (Workstream F).
- Don't change tenant-isolation or RLS behavior beyond what job idempotency
  requires — Workstream C's Alice/Bob matrix
  (`backend/tests/postgres/test_alice_bob_matrix.py`) must keep passing
  unmodified in intent.
- Don't relitigate the edition/capability registry's product classifications
  (`backend/edition.py`'s `CAPABILITY_REGISTRY`) — only extend it if strictly
  needed to gate in-process-vs-external job triggering per edition.

## Process

Per the master plan's own instructions: use `superpowers:writing-plans` (or
`superpowers:brainstorming` first if there are open design questions — e.g.
exact idempotency-lock mechanism, KMS provider/key layout, or the
in-process-vs-external edition gating) to turn this into a concrete,
reviewable task-level implementation plan before touching code, then execute
with `superpowers:subagent-driven-development` or
`superpowers:executing-plans`.

## Also update

- `CLAUDE.md`'s pending-work list once this lands (currently: "KMS envelope
  encryption for broker/AI secrets, an external scheduler replacing the
  in-process background jobs in `backend/jobs.py`, Stripe billing, and
  onboarding").
- `deploy/cloudrun.md`: add a Cloud Scheduler setup section once external
  triggering replaces the in-process pollers for the cloud edition.
- Master plan §14 go/no-go checklist items "Broker, AI, and webhook secrets
  are encrypted and absent from logs" and "Background jobs are external,
  tenant-aware, and idempotent" should be checked off only once this
  workstream's tests prove them.

## Line-number caveat

File line references above match the codebase as of 2026-09-03 (the day
this brief was written, immediately after Workstreams B/C and the edition
boundary landed). Re-check them before relying on exact line numbers if
meaningful time has passed or the files have since changed.
