# Cloud Run deploy — Neon PostgreSQL + Firebase identity, multi-instance

> Production domain routing, verified 2026-10-16: both `portfyl.com` and
> `app.portfyl.com` reach the `portfyl` service in project
> `portfyl-prod-f6shqb`, **europe-west1**, through the Cloudflare Worker
> `portfyl-beta-proxy` (`deploy/cloudflare/`). No Cloud Run domain mapping is
> in use; the old one in `portfyl-cloud-fstxby` is obsolete. Only the
> `app.portfyl.com` route sends the edge token, so `/api` on the apex fails
> closed with `403 untrusted_edge`.

The shared backend (this repo's `backend/`, with the built SPA baked in by the
root `Dockerfile`) runs on **Cloud Run**. The database is **Neon** (managed
serverless PostgreSQL) — there is no GCS-mounted SQLite volume and no
`--max-instances=1` constraint any more. PostgreSQL is single-writer-safe
across many concurrent instances, so the service scales normally.
Authentication is **Firebase** (verified e-mail identities); Portfyl itself
only stores opaque, revocable sessions (`backend/auth.py`) — there is no
shared `APP_PASSWORD` or `SESSION_SECRET` to configure any more.

This deploys into a GCP project you've already created (or a brand-new one —
see step 1). The only step you must do by hand (a browser + a payment card)
is **linking a billing account**; everything else is copy-paste `gcloud`
plus a few clicks in the Neon and Firebase consoles.

Decisions baked in here (see `docs/superpowers/plans/2026-09-01-portfyl-multiuser-foundation.md`
Task 11 and `docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md`):
request-based billing with **`--min-instances=0`** (scale to zero; accept a
few-second cold start) and an initial **`--max-instances=5`** (raise later if
traffic needs it — nothing here makes a higher number unsafe), a Cloud Run
**migration Job** that must succeed before every service deploy, Neon's
**pooled connection string** for the runtime `DATABASE_URL`, and its **direct
connection string** for scheduler `JOB_DATABASE_URL` sessions. The region below
is a variable, not baked in — pick whatever's closest to your users; for
Central Europe, GCP **`europe-west3`** (Frankfurt) paired with a Neon project
in AWS **`eu-central-1`** (also Frankfurt) keeps both legs of every request
in the same metro.

---

## 0. Fill these in once

PowerShell (your primary shell):

```powershell
$PROJECT_ID = "portfyl-cloud-xxxx"     # <- your GCP project id
$REGION     = "europe-west3"           # <- Frankfurt; e.g. europe-west1 (Belgium) or us-central1 also work
$SERVICE    = "portfyl"
$MIGRATE_JOB = "portfyl-migrate"
```

(Git Bash equivalent: `PROJECT_ID=portfyl-cloud-xxxx; REGION=europe-west3; SERVICE=portfyl; MIGRATE_JOB=portfyl-migrate`.)

---

## 1. Create the project and link billing

```powershell
gcloud projects create $PROJECT_ID
gcloud config set project $PROJECT_ID
```

**Link billing** (the one manual, card-gated step):

```powershell
gcloud billing accounts list          # copy the ACCOUNT_ID (looks like 0X0X0X-0X0X0X-0X0X0X)
gcloud billing projects link $PROJECT_ID --billing-account=ACCOUNT_ID
```

If `gcloud billing accounts list` is empty, create one at
<https://console.cloud.google.com/billing> (add a card), then re-run the link.

## 2. Enable the APIs

```powershell
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com cloudscheduler.googleapis.com cloudkms.googleapis.com iamcredentials.googleapis.com
```

Firebase Authentication is enabled and configured from the
[Firebase console](https://console.firebase.google.com/) against this same
GCP project (Firebase projects and GCP projects are the same resource) —
add the **Email/Password** sign-in provider there. No extra `gcloud services
enable` call is needed for Firebase Auth itself.

## 3. Create the Neon project and roles

Create a Neon project (pick the Neon region closest to `$REGION` — e.g.
AWS `eu-central-1`/Frankfurt for GCP `europe-west3`) at
<https://console.neon.tech>. Neon gives you one owner role (e.g.
`neondb_owner`) — it is **not** a Postgres superuser, but Neon *does*
provision it with `BYPASSRLS` (and `CREATEROLE`/`CREATEDB`) already, by
default, on every new project (verified directly against a real Neon
project on Postgres 18, 2026-09-03: `SELECT rolbypassrls FROM pg_roles
WHERE rolname = 'neondb_owner'` → `true`). **No `ALTER ROLE ... BYPASSRLS`
step is needed or possible** — Postgres 16+ actually refuses a role's own
attempt to `ALTER` an attribute it doesn't already independently hold, so
if your project's owner role is somehow missing it, granting it yourself
isn't an option; open a Neon support request instead of fighting Postgres's
privilege-escalation guard.

This is what makes the migration role usable at all — the migration role
must bypass RLS to create the policies and (later) to run the SQLite owner
import; `backend/alembic/versions/0002_tenant_rls.py` refuses to run as
`portfyl_runtime` and checks the connecting role has `BYPASSRLS` or
superuser (`_assert_migration_role` in
`backend/migrations/sqlite_to_postgres.py` enforces the same rule for the
data import). It's also exactly what `backend/tests/postgres/conftest.py`
sets up by hand for the local disposable test database, where nothing
provisions it automatically the way Neon does.

`0002_tenant_rls.py` itself creates the **`portfyl_runtime`** role (the one
every request runs as, `NOSUPERUSER NOBYPASSRLS`, no table ownership, no
schema-wide grants beyond exactly the tenant tables) — but it creates it
`NOLOGIN`, and the application issues no `SET ROLE`, so the deployed
service's `DATABASE_URL` must authenticate **directly as `portfyl_runtime`**.
PostgreSQL roles are cluster-wide, so another database in the same Neon
project may already have this role. On managed PostgreSQL the migration
validates that such an existing role is unprivileged; it does not attempt the
superuser-only `ALTER ROLE ... NOSUPERUSER/NOBYPASSRLS` operation. If the
validation reports unsafe attributes, stop and correct the role through the
provider instead of weakening the migration.
After running migrations once (step 5), give it login credentials:
Neon console → **Roles** → `portfyl_runtime` → **Reset password** (this only
adds `LOGIN` + a password; it does not touch `NOSUPERUSER`/`NOBYPASSRLS`/
`NOCREATEDB`/`NOCREATEROLE`).

For a brand-new Neon project this makes the first deployment a short loop:
create the migration secret/account from step 4, run step 5 once, return here
to reset the newly created runtime role's password, then create the runtime
and job secrets before step 6. Later deploys follow the numbered flow directly.

You now need **three** connection strings from Neon (Dashboard → Connection
Details):

- **Migration URL (direct/unpooled)** — role `neondb_owner`, used only by
  `alembic upgrade head` and the one-off SQLite importer. Never set as the
  running service's `DATABASE_URL`.
- **Runtime URL (pooled)** — role `portfyl_runtime`, set as the Cloud Run
  service's `DATABASE_URL` secret in step 4 and injected in step 6.
- **Job URL (direct/unpooled)** — the same `portfyl_runtime` role and
  database, but with the direct Neon hostname (no `-pooler`). It is injected
  as `JOB_DATABASE_URL` and used only by Cloud Scheduler endpoints. Their
  session-level advisory lock must survive commits inside a pass; Neon uses
  PgBouncer transaction pooling on pooled endpoints, where session-level
  advisory locks are unsupported.

## 4. Store secrets

There is no `APP_PASSWORD` or `SESSION_SECRET` to generate any more —
Firebase issues and verifies its own tokens. Store the three Neon connection
strings from step 3 as separate secrets (paste each URL at the prompt so it
never appears in shell history):

```powershell
gcloud secrets create portfyl-database-url --replication-policy=automatic
gcloud secrets versions add portfyl-database-url --data-file=- # paste the portfyl_runtime pooled URL, then Ctrl+Z, Enter

gcloud secrets create portfyl-migration-database-url --replication-policy=automatic
gcloud secrets versions add portfyl-migration-database-url --data-file=- # paste the direct neondb_owner URL, then Ctrl+Z, Enter

gcloud secrets create portfyl-job-database-url --replication-policy=automatic
gcloud secrets versions add portfyl-job-database-url --data-file=- # paste the direct portfyl_runtime URL (no -pooler), then Ctrl+Z, Enter

gcloud secrets create portfyl-edge-token --replication-policy=automatic
python -c "import secrets; print(secrets.token_urlsafe(32))" | gcloud secrets versions add portfyl-edge-token --data-file=-

gcloud secrets create portfyl-rate-limit-key-secret --replication-policy=automatic
python -c "import secrets; print(secrets.token_urlsafe(32))" | gcloud secrets versions add portfyl-rate-limit-key-secret --data-file=-

gcloud secrets create portfyl-account-fingerprint-key --replication-policy=automatic
python -c "import secrets; print(secrets.token_urlsafe(32))" | gcloud secrets versions add portfyl-account-fingerprint-key --data-file=-
```

Keep `portfyl-account-fingerprint-key` stable. Portfyl uses it to bind each
portfolio to one upstream Trading 212 account without storing that provider's
raw account ID; rotating it would make existing bindings unverifiable.

**Cloudflare must inject the edge token.** `PORTFYL_EDGE_TOKEN` (above) is
only half the contract — in the Cloudflare dashboard for portfyl.com,
create a Transform Rule (Rules → Transform Rules → Modify Request Header)
that runs on every request to the Cloud Run origin: **Set static** header
`X-Portfyl-Edge-Token` to the exact value stored in `portfyl-edge-token`,
overwriting any client-supplied value. Without this rule every request gets
403 `untrusted_edge` (see `backend/edge_trust.py`); a client-supplied
`X-Portfyl-Edge-Token` reaching the origin directly (bypassing Cloudflare)
must never be trusted, which is exactly why the middleware only accepts
this header, never falls back to anything else.

Two separate service accounts, so the *running service* can never read the
owner-level migration credential even via IAM (not just because
`DATABASE_URL` isn't set to it):

```powershell
gcloud iam service-accounts create portfyl-runtime --display-name="Portfyl Cloud Run runtime"
gcloud iam service-accounts create portfyl-migrator --display-name="Portfyl Alembic migration job"

gcloud secrets add-iam-policy-binding portfyl-database-url --member="serviceAccount:portfyl-runtime@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding portfyl-job-database-url --member="serviceAccount:portfyl-runtime@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding portfyl-edge-token --member="serviceAccount:portfyl-runtime@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding portfyl-rate-limit-key-secret --member="serviceAccount:portfyl-runtime@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding portfyl-account-fingerprint-key --member="serviceAccount:portfyl-runtime@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding portfyl-migration-database-url --member="serviceAccount:portfyl-migrator@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:portfyl-runtime@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/firebaseauth.admin"
```

Create the KMS key used for cloud-edition secret encryption and grant only the
runtime identity encrypt/decrypt access:

```powershell
gcloud kms keyrings create portfyl --location=$REGION
gcloud kms keys create secrets --keyring=portfyl --location=$REGION --purpose=encryption
$KMS_KEY = "projects/$PROJECT_ID/locations/$REGION/keyRings/portfyl/cryptoKeys/secrets"
gcloud kms keys add-iam-policy-binding secrets --keyring=portfyl --location=$REGION --member="serviceAccount:portfyl-runtime@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/cloudkms.cryptoKeyEncrypterDecrypter"
```

`portfyl-runtime` only ever gets the two `portfyl_runtime` database URLs plus
KMS encrypt/decrypt and **Firebase Authentication Admin** so
`firebase_admin.initialize_app()` can verify and revoke tokens using
Application Default Credentials — no key file is needed on Cloud Run.
`portfyl-migrator` only ever gets `portfyl-migration-database-url` (the
`neondb_owner` URL) — it's the service account the migration Job in step 5
runs as, and it never touches the deployed service.

## 5. Migrate before you deploy

Never let the web service start against a schema Alembic hasn't reached yet
— `backend/main.py`'s startup hook calls `assert_alembic_head()` and refuses
to serve traffic on a mismatch, but a migration Job run *before* the service
deploy keeps that from ever happening in normal operation:

```powershell
.\deploy\run-migrations.ps1 -ProjectId $PROJECT_ID -Region $REGION -Image "$REGION-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/${SERVICE}:latest" -ServiceAccount "portfyl-migrator@$PROJECT_ID.iam.gserviceaccount.com" -DatabaseUrlSecret "portfyl-migration-database-url"
```

The script deploys (or updates) a Cloud Run **Job** running `alembic -c
alembic.ini upgrade head` (the image's runtime `WORKDIR` is already
`/app/backend`, so no `backend/` prefix) against the image you're about to serve,
executes it, and waits — it exits non-zero (and prints where to find the
job's logs) if the migration fails, so a CI/CD pipeline or you, by hand,
should treat a non-zero exit here as a hard stop before step 6. Store the
`neondb_owner` migration URL as its own secret
(`portfyl-migration-database-url`) — keep it separate from the runtime
secret so the running service never holds owner-level credentials.

On the very first deploy, run `deploy/migrate-sqlite.ps1` once afterward (see
`docs/operations/sqlite-to-neon-migration.md`) to import the owner's existing
`portfyl.db`, then claim that migrated user by signing in with the matching
verified Firebase e-mail.

## 6. Deploy the service

Run from the **repo root** (where the `Dockerfile` is). `--source .` builds
the image in the cloud and pushes it to Artifact Registry; accept the offer
to create the `cloud-run-source-deploy` repo on the first run.

```powershell
gcloud run deploy $SERVICE --source . --region $REGION --allow-unauthenticated --service-account "portfyl-runtime@$PROJECT_ID.iam.gserviceaccount.com" --set-secrets="DATABASE_URL=portfyl-database-url:latest,JOB_DATABASE_URL=portfyl-job-database-url:latest,PORTFYL_EDGE_TOKEN=portfyl-edge-token:latest,RATE_LIMIT_KEY_SECRET=portfyl-rate-limit-key-secret:latest,PORTFYL_ACCOUNT_FINGERPRINT_KEY=portfyl-account-fingerprint-key:latest" --set-env-vars="PORTFYL_EDITION=cloud,PORTFYL_KMS_KEY_NAME=$KMS_KEY,RATE_LIMIT_GLOBAL_LIMIT=120,RATE_LIMIT_GLOBAL_WINDOW_SECONDS=60,RATE_LIMIT_AUTH_SESSION_LIMIT=10,RATE_LIMIT_AUTH_SESSION_WINDOW_SECONDS=60,RATE_LIMIT_BROKER_SYNC_LIMIT=5,RATE_LIMIT_BROKER_SYNC_WINDOW_SECONDS=60" --min-instances=0 --max-instances=5 --cpu=1 --memory=1Gi
```

Why these flags:
- `--set-secrets` injects both database URLs from Secret Manager at container
  start — neither is ever a plain `--set-env-vars` value or logged.
- `PORTFYL_KMS_KEY_NAME` is a resource name, not secret material. Missing KMS
  configuration fails closed when a cloud user first stores or reads a secret.
- `--allow-unauthenticated` = Cloud Run itself is public; Firebase-verified
  sessions are the real lock (there is no separate app-level password gate).
- `--max-instances=5`: safe to raise further at any time — PostgreSQL, unlike
  the old GCS-mounted SQLite file, has no single-writer constraint. Start
  conservative and watch Neon connection-pool usage before raising it a lot.
  Each instance opens at most `DB_POOL_SIZE + DB_MAX_OVERFLOW` (default
  10 + 5) connections to the pooled `DATABASE_URL` and fails a request after
  `DB_POOL_TIMEOUT` (default 10s) without a free one; tune them with
  `--update-env-vars` (`backend/database.py`'s `DatabaseSettings`).
- `--memory=1Gi` gives pandas/numpy/yfinance headroom.
- The eight `RATE_LIMIT_*` values are the spec's defaults, not
  evidence-based constants — the spec's own rollout gate requires a
  production-shaped load test before enforcement is trusted; raise any of
  them here (redeploy with `--update-env-vars`) if that load test or real
  traffic shows normal usage would otherwise trip a rule.

Optional: `--set-env-vars=FRONTEND_ORIGIN=https://your-extra-origin` if a
separately hosted frontend needs CORS beyond the same-origin SPA baked into
the image (see `backend/main.py`'s `_cors_origins`).

Optional: `--set-env-vars=SENTRY_DSN=https://<key>@<org>.ingest.sentry.io/<project>`
(or `--set-secrets` if you'd rather keep it out of plain env vars) turns on
backend error monitoring (`backend/error_monitoring.py`); unset, it's a
no-op. `SENTRY_ENVIRONMENT`/`SENTRY_RELEASE`/`SENTRY_TRACES_SAMPLE_RATE` are
optional overrides. The frontend side is separate: bake `VITE_SENTRY_DSN`
into the build (`frontend/src/errorMonitoring.js`, lazy-loaded, same no-op
default) since Vite env vars are compiled in, not read at Cloud Run runtime.

**Activation analytics (PostHog Cloud EU) — currently withheld, do not set
yet.** Like `VITE_SENTRY_DSN`, `VITE_POSTHOG_KEY` and `VITE_POSTHOG_HOST`
(must be exactly `https://eu.i.posthog.com`) are Vite build-time variables
baked into the frontend bundle by `npm run build:cloud`
(`frontend/src/analytics/AnalyticsProvider.jsx`'s `defaultAdapterFactory`) —
setting or changing a Cloud Run *service's* runtime `--set-env-vars` has no
effect on them at all, since Vite has already compiled them into static JS
by the time the container starts; they can only be changed by rebuilding
and redeploying the image. **Do not pass either variable as a build arg
yet**: per `docs/compliance/data-processing-inventory.md`'s analytics
baseline and `docs/operations/posthog-activation-analytics.md`'s production
blocker, both must stay unset in every deployed environment until the
public privacy notice/subprocessor disclosure for PostHog Cloud EU has
received qualified Czech/EU legal review and is published. Leaving them
unset is the current, correct state — `AnalyticsProvider.jsx` falls back to
a no-op adapter whenever the key is absent, so the consent banner still
renders but nothing is ever sent.

The command prints a **Service URL** (`https://portfyl-….a.run.app`) when
done.

**Broker integrations (optional secrets).** Both are read at runtime, so add
them after the first deploy with `--update-secrets`; never commit or log the
values.

- `PORTFYL_ETORO_APP_KEY`: Portfyl's own eToro Public API app key
  (`backend/routers/etoro.py`). Users still paste their personal Read key in
  Settings; this key identifies Portfyl to eToro. Unset, `/api/broker/etoro/*`
  reports "not configured" (status) and 503 (connect/sync); nothing else breaks.
- `OPENFIGI_API_KEY`: raises the OpenFIGI rate limit for ISIN → ticker lookups
  in broker imports (`backend/importers/openfigi.py`). Unset, imports still work
  on the anonymous limit; when OpenFIGI throttles or is down, the import
  preview returns 503 and the user retries later.

```powershell
gcloud secrets create portfyl-etoro-app-key --replication-policy=automatic
gcloud secrets versions add portfyl-etoro-app-key --data-file=- # paste the key, then Ctrl+Z, Enter
gcloud secrets add-iam-policy-binding portfyl-etoro-app-key --member="serviceAccount:portfyl-runtime@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
gcloud run services update $SERVICE --region $REGION --update-secrets="PORTFYL_ETORO_APP_KEY=portfyl-etoro-app-key:latest"
# Same pattern for OpenFIGI: secret portfyl-openfigi-api-key -> OPENFIGI_API_KEY.
```

## 7. Verify

Open the Service URL → register or sign in with Firebase → the dashboard
should load. Check Cloud Run logs for the `assert_alembic_head` startup line
if anything 500s immediately — that means step 5 didn't run against the
same database this service is now pointed at.

**Rate limiting deployment acceptance** (per the rate limiting spec):
- A direct request to the printed Cloud Run URL (bypassing Cloudflare) to
  any `/api/*` path must get 403 `untrusted_edge`, even when the request
  forges `CF-Connecting-IP` and/or `X-Forwarded-For` headers — the origin
  must never be reachable without Cloudflare's injected
  `X-Portfyl-Edge-Token`.
- The same request through the normal Cloudflare hostname (portfyl.com)
  must reach the API, and two requests with distinct real client IPs must
  not share a bucket (confirm via two different networks, or Cloudflare's
  own IP for a WARP/VPN client vs. a plain connection).
- After running `portfyl-rate-limit-cleanup` at least once (see section 9),
  `/health`'s `checks.scheduler.jobs.rate_limit_cleanup` must read `"ok"`
  with a recent `last_success_at`; leaving it un-run for over two hours
  must flip it to `"stale"` and `checks.scheduler.status` to `"degraded"`.
- Before flipping enforcement on for real traffic, run the spec's
  production-shaped load test (20 concurrent distinct-IP clients, a
  30-request burst behind one shared IP, concurrent requests against one
  workspace) and confirm every numeric gate in the spec's "Observability
  and rollout" section — this is an operational validation step, not
  something any automated test in this repo can substitute for.

## 8. Cost guards (one-time, recommended)

**Small budget alert** — via `gcloud` (or the console: Budgets & alerts →
Create budget → scope to this project → alert thresholds 50/90/100%):

```powershell
gcloud services enable billingbudgets.googleapis.com --project=$PROJECT_ID
gcloud billing accounts describe BILLING_ACCOUNT_ID --format="value(currencyCode)"   # budget-amount's currency MUST match this
gcloud billing budgets create --billing-account=BILLING_ACCOUNT_ID --display-name="Portfyl cloud budget alert" --budget-amount=25CZK --filter-projects="projects/$PROJECT_ID" --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0
```

`--budget-amount`'s currency must exactly match the billing account's own
currency (`billingbudgets.googleapis.com` rejects a mismatch with a generic
`INVALID_ARGUMENT`, no mention of currency in the error) — check with the
`describe` command above before picking an amount; a CZK-currency billing
account cannot take a `USD` budget.

**Artifact Registry — preserve deployable and rollback images**:

`deploy/ar-cleanup-policy.json` retains the five most recent versions, all
versions younger than seven days, and versions tagged with `production` or
`rollback` prefixes. Keep policies override deletion. The previous keep-one
policy left the running revision's source image unavailable on 2026-09-09.
After a successful deployment, tag its exact digest `production`; before
moving that tag on a later deployment, tag the previous production digest
`rollback`. Deploy using immutable digests and keep both tags current.

Use the **registry's region**, which may differ from the Cloud Run region
(current registry: `europe-west3`; service: `europe-west1`).

```powershell
gcloud artifacts repositories set-cleanup-policies cloud-run-source-deploy --project=$PROJECT_ID --location=$REGION --policy=deploy/ar-cleanup-policy.json --no-dry-run
```

`--dry-run` (and `--no-dry-run`) is a **persistent setting on the
repository**, not a one-time preview flag — omitting it entirely leaves
whatever dry-run state was last set (verified: a prior `--dry-run` call
stays in effect on every later call, including ones that only pass
`--policy`, until you explicitly pass `--no-dry-run`). Preview first with
`--dry-run --policy=...`, then apply for real with `--no-dry-run` (the
policy from the last `--policy=...` call stays applied either way).

## 9. Cloud Scheduler jobs (background work)

Cloud Run scales this service to multiple instances (step 6's
`--max-instances`); `backend/main.py` only runs its in-process
alerts/autosync/dividends pollers in the **local** edition (always
single-instance) for exactly that reason — an in-process timer here would
fire redundantly on every instance. `PORTFYL_EDITION=cloud` instead mounts
`backend/routers/internal_jobs.py`'s `/internal/jobs/{alerts,autosync,
dividends}` endpoints, which Cloud Scheduler calls on a cron schedule; a
Postgres advisory lock inside each endpoint makes an overlapping second
call a safe no-op instead of a duplicate run (see
`docs/superpowers/plans/2026-09-04-portfyl-secrets-jobs.md` Task 5).

A dedicated service account, `roles/run.invoker` only — it never touches
Secret Manager or the database directly, unlike `portfyl-runtime`/
`portfyl-migrator`:

```powershell
gcloud iam service-accounts create portfyl-scheduler --display-name="Portfyl Cloud Scheduler caller"
gcloud run services add-iam-policy-binding $SERVICE --region=$REGION --member="serviceAccount:portfyl-scheduler@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/run.invoker"
```

Give the running service its own identity (`PORTFYL_SERVICE_URL`) and the
expected caller identity (`PORTFYL_SCHEDULER_SERVICE_ACCOUNT`) so
`verify_scheduler_token` can check both the OIDC token's audience and its
`email` claim — redeploy step 6's command with these two vars added to
`--set-env-vars` once you know the Service URL it printed:

```powershell
gcloud run services update $SERVICE --region=$REGION --update-env-vars="PORTFYL_SERVICE_URL=https://portfyl-xxxxx.a.run.app,PORTFYL_SCHEDULER_SERVICE_ACCOUNT=portfyl-scheduler@$PROJECT_ID.iam.gserviceaccount.com"
```

Use `--update-env-vars` here: `--set-env-vars` replaces the whole environment
map and would remove the KMS settings from step 6.

Then create the six scheduler jobs. Cron expressions mirror today's
poller intervals except autosync: the old 60-second in-process heartbeat
only existed so `jobs.sync_due()` could catch a due schedule within a
minute — Cloud Scheduler's minimum useful resolution is coarser than that
and `sync_due()` already gates the real work, so an hourly trigger is
enough to catch every configured per-workspace daily-time/interval
schedule promptly without the wasted invocations a 1-minute cron would
cost. `portfyl-broker-backfill` is the exception -- it drains T212
`BrokerSyncRun` history backfills (docs/superpowers/plans/2026-09-20-t212-snapshot-first-sync.md,
Task 3), independent of auto_sync/schedule. Since 2026-10-27 it runs hourly
like the rest: a 1-minute cron kept the Neon compute awake around the clock
and exhausted the free 100 CU-hour quota (a freshly connected account's
history now waits up to an hour between steps). `alerts` runs hourly for the
same reason:

```powershell
gcloud scheduler jobs create http portfyl-alerts --location=$REGION --schedule="0 * * * *" --uri="https://portfyl-xxxxx.a.run.app/internal/jobs/alerts" --http-method=POST --oidc-service-account-email="portfyl-scheduler@$PROJECT_ID.iam.gserviceaccount.com" --oidc-token-audience="https://portfyl-xxxxx.a.run.app" --max-retry-attempts=3 --min-backoff=30s --max-backoff=300s

gcloud scheduler jobs create http portfyl-autosync --location=$REGION --schedule="0 * * * *" --uri="https://portfyl-xxxxx.a.run.app/internal/jobs/autosync" --http-method=POST --oidc-service-account-email="portfyl-scheduler@$PROJECT_ID.iam.gserviceaccount.com" --oidc-token-audience="https://portfyl-xxxxx.a.run.app" --max-retry-attempts=3 --min-backoff=30s --max-backoff=300s

gcloud scheduler jobs create http portfyl-dividends --location=$REGION --schedule="0 */12 * * *" --uri="https://portfyl-xxxxx.a.run.app/internal/jobs/dividends" --http-method=POST --oidc-service-account-email="portfyl-scheduler@$PROJECT_ID.iam.gserviceaccount.com" --oidc-token-audience="https://portfyl-xxxxx.a.run.app" --max-retry-attempts=3 --min-backoff=30s --max-backoff=300s

gcloud scheduler jobs create http portfyl-rate-limit-cleanup --location=$REGION --schedule="0 * * * *" --uri="https://portfyl-xxxxx.a.run.app/internal/jobs/rate_limit_cleanup" --http-method=POST --oidc-service-account-email="portfyl-scheduler@$PROJECT_ID.iam.gserviceaccount.com" --oidc-token-audience="https://portfyl-xxxxx.a.run.app" --max-retry-attempts=3 --min-backoff=30s --max-backoff=300s

gcloud scheduler jobs create http portfyl-account-deletion-cleanup --location=$REGION --schedule="17 3 * * *" --uri="https://portfyl-xxxxx.a.run.app/internal/jobs/account_deletion_cleanup" --http-method=POST --oidc-service-account-email="portfyl-scheduler@$PROJECT_ID.iam.gserviceaccount.com" --oidc-token-audience="https://portfyl-xxxxx.a.run.app" --max-retry-attempts=3 --min-backoff=30s --max-backoff=300s

gcloud scheduler jobs create http portfyl-broker-backfill --location=$REGION --schedule="0 * * * *" --uri="https://portfyl-xxxxx.a.run.app/internal/jobs/broker_backfill" --http-method=POST --oidc-service-account-email="portfyl-scheduler@$PROJECT_ID.iam.gserviceaccount.com" --oidc-token-audience="https://portfyl-xxxxx.a.run.app" --max-retry-attempts=3 --min-backoff=30s --max-backoff=300s
```

Verify: `gcloud scheduler jobs run portfyl-alerts --location=$REGION` should
return success and produce an `alerts pass: N event(s)` (or nothing, if
there was nothing to do) line in Cloud Run logs tagged with a `job-alerts-…`
correlation id; a bare `curl -X POST` to the same URL with no token must
get 401. For the overlap drill, deliberately hold the job's advisory lock from
a second direct PostgreSQL session while invoking the endpoint; the response
must be `{"job":"alerts","skipped":"already running"}` and Cloud Run must log
`alerts: skipped, already running`. Two merely rapid triggers are not a
deterministic test when an empty job completes in milliseconds.
For `portfyl-rate-limit-cleanup`, `gcloud scheduler jobs run
portfyl-rate-limit-cleanup --location=$REGION` should log a
`rate_limit_cleanup pass: 1 event(s)` line (or nothing, if nothing was
expired) tagged with a `job-rate_limit_cleanup-…` correlation id, and the
same overlap drill must produce
`{"job":"rate_limit_cleanup","skipped":"already running"}`.
Before enabling `portfyl-account-deletion-cleanup`, inspect production for due
requests without mutating them and test the purge state machine on disposable
fixtures. Its first forced run must report a healthy heartbeat in `/health`;
never infer completion from Scheduler's run acknowledgement alone.
For `portfyl-broker-backfill`, connect a disposable T212 demo account and
confirm `gcloud scheduler jobs run portfyl-broker-backfill --location=$REGION`
logs a `broker_backfill pass: N event(s)` line tagged with a
`job-broker_backfill-…` correlation id once a `BrokerSyncRun` exists (created
by a `POST /api/broker/trading212/sync` call, not by this job), and that
`GET /api/broker/trading212/history-status` eventually reports
`"state": "completed"` across several ticks without the browser staying open.

---

## Routine redeploy (current production layout)

Since 2026-10-11 production is the `portfyl` service in project
**`portfyl-prod-f6shqb`**, region **europe-west1**, behind
`app.portfyl.com` (Cloudflare Worker + Access). Images live in that
project's `europe-west1 .../cloud-run-source-deploy` Artifact Registry
repository, tagged with the short commit SHA; there is no `:latest`, so the
step 5 and step 6 commands above do not apply to a redeploy. Firebase Auth
and the KMS key stay in the old project `portfyl-cloud-fstxby`
(cross-project IAM); do not deploy anything to that project.

Build from a clean `git archive` of `main`, not the working tree. The four
`VITE_FIREBASE_*` values are compiled into the SPA at build time and
`.dockerignore` excludes `.env*`, so they must be passed as build args (an
image built without them serves a login page that cannot sign anyone in).
Use the same image digest for the migration Job and the service; existing
secrets and env vars persist because no `--set-*` flags are passed. Set the
gcloud configuration per shell, never with
`gcloud config configurations activate` (other sessions share the default
configuration, which still points at the old project):

```powershell
$env:CLOUDSDK_ACTIVE_CONFIG_NAME = "newgcp"
$PROJECT = "portfyl-prod-f6shqb"; $REGION = "europe-west1"
$SHA = git rev-parse --short main
$REPO = "$REGION-docker.pkg.dev/$PROJECT/cloud-run-source-deploy/portfyl"
$SRC = Join-Path $env:TEMP "portfyl-build-$SHA"
New-Item -ItemType Directory -Force $SRC | Out-Null
# Windows PowerShell 5.1 pipes native output as text and corrupts a tar stream,
# so write the archive to a file instead of piping `git archive | tar`.
git archive --format=tar -o "$SRC.tar" main
tar -x -f "$SRC.tar" -C $SRC
Remove-Item "$SRC.tar"
$fb = @{}
Get-Content frontend/.env.local | Where-Object { $_ -match '^(VITE_FIREBASE_\w+)=(.*)$' } | ForEach-Object { $fb[$Matches[1]] = $Matches[2].Trim().Trim('"') }
# A missing flag silently builds Google sign-in off; prod has it on, so require an explicit true/false.
if ($fb.VITE_FIREBASE_GOOGLE_SIGN_IN -notin @("true", "false")) { throw "frontend/.env.local needs VITE_FIREBASE_GOOGLE_SIGN_IN=true (or =false to turn Google sign-in off)" }
@"
steps:
- name: gcr.io/cloud-builders/docker
  args: ['build', '-t', '${REPO}:$SHA',
         '--build-arg', 'VITE_FIREBASE_API_KEY=$($fb.VITE_FIREBASE_API_KEY)',
         '--build-arg', 'VITE_FIREBASE_AUTH_DOMAIN=$($fb.VITE_FIREBASE_AUTH_DOMAIN)',
         '--build-arg', 'VITE_FIREBASE_PROJECT_ID=$($fb.VITE_FIREBASE_PROJECT_ID)',
         '--build-arg', 'VITE_FIREBASE_APP_ID=$($fb.VITE_FIREBASE_APP_ID)',
         '--build-arg', 'VITE_FIREBASE_GOOGLE_SIGN_IN=$($fb.VITE_FIREBASE_GOOGLE_SIGN_IN)',
         '.']
images: ['${REPO}:$SHA']
"@ | Set-Content -Encoding ascii (Join-Path $SRC "cloudbuild.yaml")
# cmd /c: gcloud streams build logs to stderr, which PowerShell would treat as an error.
cmd /c "gcloud builds submit --region=$REGION --project=$PROJECT --config=$SRC\cloudbuild.yaml $SRC"
$DIGEST = gcloud artifacts docker images describe "${REPO}:$SHA" --project $PROJECT --format "value(image_summary.digest)"
$IMAGE = "${REPO}@$DIGEST"
.\deploy\run-migrations.ps1 -ProjectId $PROJECT -Region $REGION -Image $IMAGE -ServiceAccount "portfyl-migrator@$PROJECT.iam.gserviceaccount.com" -DatabaseUrlSecret "portfyl-migration-database-url"
gcloud run deploy portfyl --image $IMAGE --region $REGION --project $PROJECT --quiet
```

Stop if the build or the migration Job fails. `app.portfyl.com` sits behind
Cloudflare Access and the `run.app` URL answers 403 without the edge token,
so verify a deploy by logging in through `app.portfyl.com` and by reading
the new revision's Cloud Run logs, not with an anonymous `curl`.

### Google sign-in

"Continue with Google" is off unless the image is built with
`VITE_FIREBASE_GOOGLE_SIGN_IN=true`. The redeploy above passes whatever
`frontend/.env.local` holds and stops if the line is missing, so the button
can no longer disappear by accident. Prod has had it on since 2026-10-13. See
`docs/superpowers/plans/2026-10-12-portfyl-google-sign-in.md`. To turn it on:

1. Check that the Firebase console prerequisites are in place in
   `portfyl-cloud-fstxby` (plan T0):
   - the Google provider is enabled;
   - `app.portfyl.com` is an Authorized domain;
   - "one account per e-mail address" is on;
   - the OAuth consent screen is configured;
   - every private tester is a consent-screen Test user, in addition to
     Cloudflare Access and `beta_invites`.
2. One time only, give the service the auth domain its CSP must admit for
   Firebase's popup. It must equal `VITE_FIREBASE_AUTH_DOMAIN`. Until it is
   set, the CSP keeps blocking Google's popup scripts:
   ```powershell
   gcloud run services update portfyl --region $REGION --project $PROJECT --update-env-vars="PORTFYL_FIREBASE_AUTH_DOMAIN=portfyl-cloud-fstxby.firebaseapp.com"
   ```
3. Add `VITE_FIREBASE_GOOGLE_SIGN_IN=true` to `frontend/.env.local`. The same
   line also enables the button in local dev. Then run the routine redeploy.
4. On `app.portfyl.com`, sign in with Google and check the browser console:
   there must be no Content-Security-Policy violations.

To roll back, remove the line or set it to `false` and redeploy. No data
changes are involved. Leaving `PORTFYL_FIREBASE_AUTH_DOMAIN` set is harmless.

## Ongoing rules

- Scheduler schedules, retry limits, and JSON health matching are versioned
  in `deploy/operations.json`; alert policy templates are in
  `deploy/monitoring-policies.json`. See
  `docs/operations/scheduler-monitoring.md` for verification and recovery.

- **Always migrate before you deploy** (step 5) — never redeploy the service
  image without first running `deploy/run-migrations.ps1` against the same
  database.
- **Redeploy after backend or frontend changes**: follow "Routine redeploy"
  above (secrets and other settings persist across redeploys unless you
  change them).
- **Back up / restore**: Neon takes continuous WAL-based backups
  automatically (point-in-time recovery); see
  `docs/operations/neon-backup-restore.md` for the recovery-branch drill and
  `deploy/validate-restore.py` for verifying a restored branch before you'd
  ever trust it.

## Notes / risks

- **Cold start**: the first request after idle spins the container up. The
  paid escape hatch is `--min-instances=1`, which you almost certainly don't
  want at low traffic.
- **Region**: whatever you pick for `$REGION`, keep the Cloud Run service and
  the Neon project in matching metros to minimize latency — `europe-west3`
  (GCP) + `eu-central-1` (Neon/AWS), both Frankfurt, is the pairing for a
  Central European audience.
- This is Phase 1 of the cloud edition. Paid checkout, onboarding, and the
  edition capability boundary are separate workstreams. Payments are currently
  deferred; the pricing page is comparison-only and Paddle is the likely future
  provider, not an implemented dependency —
  see `docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md`.
