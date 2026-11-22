---
type: hub
layer: ops
tags: [arch/hub]
generated: false
---
# Deploy and operations

The cloud edition runs on Google Cloud Run (the container), Neon (managed PostgreSQL) and Cloudflare (domain, DNS and an edge proxy for portfyl.com). One multi-stage `Dockerfile` builds the React app and the Python backend into a single image. The local edition does not use any of this: the owner starts it on Windows with `start.bat`. The step-by-step runbook is `deploy/cloudrun.md`, and it is long, so this hub only shows how the pieces fit.

## How it works
- Build: [[Dockerfile]] has two stages. Stage 1 (`node:22-alpine`) runs `npm run build:cloud`, which also prerenders the public pages. Stage 2 (`python:3.14-slim`) installs the hashed `requirements.lock`, copies the backend and drops the built SPA at `frontend/dist`. It always declares `PORTFYL_EDITION=cloud`. Firebase web config comes in as build args because `.env*` is excluded from the build context.
- Deploy order matters: first run the Cloud Run migration job with [[deploy.run-migrations (ps1)]] (it runs `alembic upgrade head` and waits), and only when it exits 0 deploy the service revision. See "Migrate before you deploy" in [[deploy.cloudrun (md)]]. A frontend-only redeploy path exists: [[deploy.Dockerfile (frontend-overlay)]] with [[deploy.cloudbuild-frontend-overlay (yaml)]].
- Database: Neon, reached only through `DATABASE_URL` (stored in Secret Manager, never baked into the image). Neon keeps continuous backups; recovery is by branching at a past time, verified with [[deploy.validate-restore (py)]]. See [[operations/neon-backup-restore]].
- Edge: Cloudflare sits in front. A Worker proxy ([[deploy.cloudflare (folder)]]) adds a secret `X-Portfyl-Edge-Token` only on allowed hostnames, and the backend rejects `/api` calls without it ([[edge_trust]], [[cloud_gate]]).
- Background jobs: Cloud Scheduler calls `/internal/jobs/*` ([[routers.internal_jobs]]) on the cron schedules in [[deploy.operations (json)]] (alerts, autosync, broker backfill, dividends, rate-limit cleanup, account-deletion cleanup, billing reconcile). See [[Jobs and Cloud Scheduler]].
- Monitoring: an uptime check on `/livez` and alert policies are defined in [[deploy.operations (json)]] and [[deploy.monitoring-policies (json)]]. `/livez` is cheap; `/health` checks the database and job heartbeats ([[main]]). Optional Sentry error reporting lives in [[error_monitoring]].
- Cleanup: [[deploy.ar-cleanup-policy (json)]] limits old container images in Artifact Registry.
- Local development: [[start (bat)]] starts Docker Desktop if needed, brings up the dev PostgreSQL ([[deploy.docker-compose.postgres-dev (yml)]], host port 15432), creates the `uv` virtualenv, and launches backend (port 8000) and frontend (port 5173). It sets `PORTFYL_EDITION=local` unless it is already set.
- Beta access helpers: [[deploy.manage-beta-tester (ps1)]] and [[manage_beta]].
- Payments stay off until `PORTFYL_BILLING_ENABLED=1`; see the Stripe section of [[deploy.cloudrun (md)]] and [[Billing and Stripe]].

## Key code
- [[Dockerfile]]: image build.
- [[deploy.cloudrun (md)]]: the full runbook (project setup, secrets, deploy, verify, scheduler, Stripe, trial, bot check).
- [[deploy.run-migrations (ps1)]]: migration job.
- [[deploy.operations (json)]]: scheduler and uptime check definitions.
- [[deploy.monitoring-policies (json)]]: alert policies.
- [[deploy.validate-restore (py)]]: restore validation.
- [[start (bat)]]: local dev launcher.
- [[github.workflows.ci (yml)]]: CI checks run before merge.
- [[main]]: `/livez`, `/health` and the job heartbeat limits.

## Related hubs
- [[Portfyl]], [[Database and migrations]], [[Jobs and Cloud Scheduler]], [[Secrets and security]], [[Testing]], [[Billing and Stripe]], [[Edition boundary]], [[Emails]]

## Docs
- [[operations/scheduler-monitoring]]: scheduler and monitoring operations.
- [[operations/neon-backup-restore]]: PITR restore drill.
- [[operations/sqlite-to-neon-migration]]: one-off owner data import.
- [[operations/security-incident-response]]: what to do in a security incident.
- [[operations/private-beta-access]]: how private beta admission works.
- [[superpowers/plans/2026-10-11-portfyl-gcp-trial-migration]]: moving prod to the new GCP project.
