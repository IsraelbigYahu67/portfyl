# Cloud Run deploy — Neon PostgreSQL + Firebase identity, multi-instance

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
**migration Job** that must succeed before every service deploy, and Neon's
**pooled connection string** for the runtime `DATABASE_URL`. The region below
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
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com
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
After running migrations once (step 6), give it login credentials:
Neon console → **Roles** → `portfyl_runtime` → **Reset password** (this only
adds `LOGIN` + a password; it does not touch `NOSUPERUSER`/`NOBYPASSRLS`/
`NOCREATEDB`/`NOCREATEROLE`).

You now have **two** connection strings from Neon (Dashboard → Connection
Details), both **pooled** (`-pooler` in the hostname, which Neon's PgBouncer
requires anyway for Cloud Run's many short-lived connections):

- **Migration URL** — role `neondb_owner`, used only by `alembic upgrade
  head` and the one-off SQLite importer. Never set as the running service's
  `DATABASE_URL`.
- **Runtime URL** — role `portfyl_runtime`, set as the Cloud Run service's
  `DATABASE_URL` secret in step 5.

## 4. Store secrets

There is no `APP_PASSWORD` or `SESSION_SECRET` to generate any more —
Firebase issues and verifies its own tokens. Store the two Neon connection
strings from step 3 as separate secrets (paste each URL at the prompt so it
never appears in shell history):

```powershell
gcloud secrets create portfyl-database-url --replication-policy=automatic
gcloud secrets versions add portfyl-database-url --data-file=- # paste the portfyl_runtime pooled URL, then Ctrl+Z, Enter

gcloud secrets create portfyl-migration-database-url --replication-policy=automatic
gcloud secrets versions add portfyl-migration-database-url --data-file=- # paste the neondb_owner pooled URL, then Ctrl+Z, Enter
```

Two separate service accounts, so the *running service* can never read the
owner-level migration credential even via IAM (not just because
`DATABASE_URL` isn't set to it):

```powershell
gcloud iam service-accounts create portfyl-runtime --display-name="Portfyl Cloud Run runtime"
gcloud iam service-accounts create portfyl-migrator --display-name="Portfyl Alembic migration job"

gcloud secrets add-iam-policy-binding portfyl-database-url --member="serviceAccount:portfyl-runtime@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"
gcloud secrets add-iam-policy-binding portfyl-migration-database-url --member="serviceAccount:portfyl-migrator@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $PROJECT_ID --member="serviceAccount:portfyl-runtime@$PROJECT_ID.iam.gserviceaccount.com" --role="roles/firebaseauth.admin"
```

`portfyl-runtime` only ever gets `portfyl-database-url` (the `portfyl_runtime`
role's URL) plus **Firebase Authentication Admin** so
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
gcloud run deploy $SERVICE --source . --region $REGION --allow-unauthenticated --service-account "portfyl-runtime@$PROJECT_ID.iam.gserviceaccount.com" --set-secrets="DATABASE_URL=portfyl-database-url:latest" --min-instances=0 --max-instances=5 --cpu=1 --memory=1Gi
```

Why these flags:
- `--set-secrets` injects `DATABASE_URL` from Secret Manager at container
  start — it is never a plain `--set-env-vars` value and is never logged.
- `--allow-unauthenticated` = Cloud Run itself is public; Firebase-verified
  sessions are the real lock (there is no separate app-level password gate).
- `--max-instances=5`: safe to raise further at any time — PostgreSQL, unlike
  the old GCS-mounted SQLite file, has no single-writer constraint. Start
  conservative and watch Neon connection-pool usage before raising it a lot.
- `--memory=1Gi` gives pandas/numpy/yfinance headroom.

Optional: `--set-env-vars=FRONTEND_ORIGIN=https://your-extra-origin` if a
separately hosted frontend needs CORS beyond the same-origin SPA baked into
the image (see `backend/main.py`'s `_cors_origins`).

The command prints a **Service URL** (`https://portfyl-….a.run.app`) when
done.

## 7. Verify

Open the Service URL → register or sign in with Firebase → the dashboard
should load. Check Cloud Run logs for the `assert_alembic_head` startup line
if anything 500s immediately — that means step 5 didn't run against the
same database this service is now pointed at.

## 8. Cost guards (one-time, recommended)

**$1 budget alert** — easiest in the console:
<https://console.cloud.google.com/billing> → Budgets & alerts → Create budget
→ scope to this project → amount **$1** → alert thresholds 50/90/100%.

**Artifact Registry — keep only the latest image**:

```powershell
gcloud artifacts repositories set-cleanup-policies cloud-run-source-deploy --location=$REGION --policy=deploy/ar-cleanup-policy.json
```

(Add `--dry-run` to preview first.)

---

## Ongoing rules

- **Always migrate before you deploy** (step 5) — never redeploy the service
  image without first running `deploy/run-migrations.ps1` against the same
  database.
- **Redeploy after backend changes**: re-run the step 6 command (secrets and
  other settings persist across redeploys unless you change them; `--source .`
  rebuilds).
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
- This is Phase 1 of the cloud edition. Billing (Stripe), onboarding, and the
  edition capability boundary are separate, not-yet-implemented workstreams —
  see `docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md`.
