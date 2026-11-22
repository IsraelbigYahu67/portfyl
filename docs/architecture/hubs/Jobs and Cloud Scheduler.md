---
type: hub
layer: backend
tags: [arch/hub]
generated: false
---
# Jobs and Cloud Scheduler

Some work has to happen without a user clicking: checking price alerts, syncing brokers, sending dividend notices, cleaning old data, reconciling Stripe. In the local edition `main.py` runs these as in-process timers. In the cloud edition Cloud Run has several instances, and an in-process timer would fire on every one of them, so Google Cloud Scheduler calls HTTP endpoints instead, and a PostgreSQL advisory lock makes sure only one run happens at a time. The job code itself is the same in both editions.

## How it works
- **Local edition.** `main.py` starts periodic loops for alerts, autosync (60 second heartbeat), broker backfill and dividends, only when the edition is local.
- **Cloud edition.** [[routers.internal_jobs]] is mounted only in cloud and lives outside `/api`, so it has no cookie or CSRF. Every call must carry a Google-signed OIDC token for the dedicated scheduler service account (`PORTFYL_SERVICE_URL`, `PORTFYL_SCHEDULER_SERVICE_ACCOUNT`). There is no shared static secret.
- **One run at a time.** `with_job_lock` takes a non-blocking, session-level advisory lock on its own non-pooled connection. A second overlapping call returns `skipped: already running`. Jobs use `JOB_DATABASE_URL`, which must be the direct (not `-pooler`) database URL, because pooled connections cannot hold such a lock.
- **Job endpoints** (all `POST /internal/jobs/<name>`): `alerts`, `autosync`, `dividends`, `broker_backfill`, `rate_limit_cleanup`, `account_deletion_cleanup`, `billing_reconcile`. The passes live in [[jobs]], except `billing_reconcile`, which is `billing_reconcile_pass` in [[billing_sync]].
- **Schedules** (UTC, in `deploy/operations.json`): hourly for alerts, autosync, broker_backfill and rate_limit_cleanup; every 12 hours for dividends; daily 03:17 for account_deletion_cleanup (which also runs [[data_retention]] and the trial-record purge); daily 04:43 for billing_reconcile. Retries are bounded (3 retries, 5 minute deadline).
- **Never block the event loop.** SQLAlchemy is synchronous, so endpoints and job runners are plain `def`. Passes that mix `await` and database work run through [[private_loop]] `run_on_private_loop`, a fresh event loop in the worker thread. It raises if called from a running loop.
- **Per-workspace passes.** Passes list active workspaces and set the RLS context for each one (see [[Tenancy and RLS]], [[0003_job_workspace_enumeration]]). In cloud, each workspace is also checked against its plan (see [[entitlements]]), so a Free workspace is skipped for broker sync and notifications.
- **Heartbeat.** After a clean pass, `mark_job_succeeded` stores the time in [[job_runs (table)]]. `/health` compares those times with `_JOB_MAX_AGES` in [[main]] and reports a stale job. Failed passes never update it.
- **Dead-letter state.** A broker connection that fails every pass `BROKER_AUTOSYNC_FAILURE_THRESHOLD` times (default 5) in a row stops retrying: auto-sync turns off and `needs_attention` turns on until the user fixes credentials. History backfill runs retry with exponential backoff (1 minute doubling, capped at 1 hour) and stop after `BROKER_BACKFILL_MAX_RETRIES` (default 8). See [[broker_sync_runs (table)]] and [[Broker importers and sync]].
- **Backfill wake-up.** The hourly backfill tick is too slow for a Trading 212 history import, so [[backfill_trigger]] enqueues Cloud Tasks that call the same endpoint right after a run is created and again when a rate limit resets. It does nothing locally and its failures are swallowed.
- **Notification outbox.** [[notifications]] delivers due rows of [[notification_outbox (table)]] per workspace with retry and backoff (at most 5 attempts).

## Key code
- [[routers.internal_jobs]]: auth, advisory lock, job endpoints
- [[jobs]]: alerts, autosync, dividends, backfill, cleanup passes, heartbeat
- [[private_loop]]: `run_on_private_loop`
- [[backfill_trigger]]: Cloud Tasks wake-up for history backfill
- [[notifications]]: outbox delivery
- [[billing_sync]]: daily `billing_reconcile_pass`
- [[purge_account_deletions]]: command twin of the deletion cleanup
- [[data_retention]]: retention sweep inside the daily job
- [[demo_cleanup]]: sample data removal
- [[main]]: local pollers and `/health` job ages
- [[deploy.operations (json)]]: scheduler definitions
- [[deploy.monitoring-policies (json)]]: alert policies

## Data
- [[job_runs (table)]], [[notification_outbox (table)]], [[broker_sync_runs (table)]], [[rate_limit_buckets (table)]]

## Related hubs
- [[Deploy and operations]]
- [[Tenancy and RLS]]
- [[Broker importers and sync]]
- [[Alerts and integrations]]
- [[Billing and Stripe]]
- [[Account deletion and data lifecycle]]
- [[Secrets and security]]
- [[Backend]]
- [[Portfyl]]

## Docs
- [[operations/scheduler-monitoring]]: schedules, monitoring and the `/livez` and `/health` split
- [[superpowers/specs/2026-09-03-portfyl-job-triggering-design]]: why Cloud Scheduler plus an advisory lock
- [[superpowers/plans/2026-10-11-portfyl-gcp-trial-migration]]: production move that affects the job setup
- [[deploy.cloudrun (md)]]: runbook, including scheduler setup
