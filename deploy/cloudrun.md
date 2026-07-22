# Phase 1 — Deploy the shared backend to Cloud Run

The single shared backend (this repo's `backend/`, with the desktop SPA baked in by
the root `Dockerfile`) runs on **Cloud Run**, with the SQLite DB living on a
**Cloud Storage (GCS) volume** — so the app works with the desktop PC powered off.

This deploys into a **brand-new GCP project**. The only steps you must do by hand
(a browser + a payment card) are **linking a billing account**; everything else is
copy-paste `gcloud`.

Decisions baked in here (see the mobile-app plan): region **us-central1** (keeps GCS
5 GB + egress inside Google's always-free tier → ~0 Kč), **`--max-instances=1`**
(SQLite is single-writer — this is load-bearing, never raise it), `--min-instances=0`
(scale to zero; accept a few-second cold start), a **$1 budget alert**, and an
Artifact Registry **keep-1-image** cleanup policy.

---

## 0. Fill these in once

Pick a **globally-unique** project id (lowercase, digits, hyphens; 6–30 chars).

PowerShell (your primary shell):

```powershell
$PROJECT_ID = "portfyl-cloud-xxxx"     # <- choose a unique id
$BUCKET     = "$PROJECT_ID-db"         # bucket name = project id + -db (also globally unique)
$REGION     = "us-central1"
$SERVICE    = "portfyl"
```

(Git Bash equivalent: `PROJECT_ID=portfyl-cloud-xxxx; BUCKET=$PROJECT_ID-db; REGION=us-central1; SERVICE=portfyl`.)

The `$VAR` references in the commands below expand the same way in both shells; only
the assignment lines above differ.

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

If `gcloud billing accounts list` is empty, you have no billing account yet — create
one at <https://console.cloud.google.com/billing> (add a card), then re-run the link.
Cloud Run + GCS **require** billing enabled; usage here bills ~0 Kč, but a card must
be on file.

## 2. Enable the APIs

```powershell
gcloud services enable run.googleapis.com storage.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com
```

## 3. Create the DB bucket and upload the current database

`backend/portfyl.db` is the source of truth (portfolio 1 "zubik", ~0.4 MB). Upload it
once so the cloud app starts with your real data.

```powershell
gcloud storage buckets create gs://$BUCKET --location=$REGION --uniform-bucket-level-access
gcloud storage cp backend/portfyl.db gs://$BUCKET/portfyl.db
```

## 4. Deploy

Run from the **repo root** (where the `Dockerfile` is). `--source .` builds the image
in the cloud (no local Docker needed) and pushes it to Artifact Registry. On the first
run it will offer to create the `cloud-run-source-deploy` repo — accept.

Pick a real password and generate a signing secret first:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"   # -> use as SESSION_SECRET
```

Then deploy (replace `APP_PASSWORD` and `SESSION_SECRET`; keep the password
**comma-free** — commas are the env-var delimiter):

```powershell
gcloud run deploy $SERVICE --source . --region $REGION --allow-unauthenticated --add-volume=name=db,type=cloud-storage,bucket=$BUCKET --add-volume-mount=volume=db,mount-path=/data --set-env-vars=DATABASE_PATH=/data/portfyl.db,APP_PASSWORD=CHOOSE_A_PASSWORD,SESSION_SECRET=PASTE_THE_GENERATED_SECRET --min-instances=0 --max-instances=1 --cpu=1 --memory=1Gi
```

Why these flags:
- `--add-volume … type=cloud-storage` + `--add-volume-mount … mount-path=/data` mounts
  the bucket at `/data`; `DATABASE_PATH=/data/portfyl.db` points SQLite at it
  (`database.py` builds `sqlite:////data/portfyl.db`).
- `APP_PASSWORD` set → the app's password gate uses it **and** flips the session cookie
  to `Secure` (auth.py). `SESSION_SECRET` signs the session — a random per-deploy value.
- `--allow-unauthenticated` = Cloud Run itself is public; the app's own password gate is
  the real lock. `--memory=1Gi` gives pandas/numpy/yfinance headroom for the startup
  FX backfill.

The command prints a **Service URL** (`https://portfyl-….a.run.app`) when done.

## 5. Verify

Open the Service URL in a desktop browser → you should hit the Portfyl login → sign in
with `APP_PASSWORD` → the dashboard numbers should match your local app. If login works
and data loads, the GCS-mounted DB is wired correctly.

## 6. Cost guards (one-time, recommended)

**$1 budget alert** — easiest in the console:
<https://console.cloud.google.com/billing> → Budgets & alerts → Create budget → scope to
this project → amount **$1** → alert thresholds 50/90/100%.

**Artifact Registry — keep only the latest image** (older build layers otherwise
accumulate). After the first successful deploy the repo exists; apply a cleanup policy:

```powershell
gcloud artifacts repositories set-cleanup-policies cloud-run-source-deploy --location=$REGION --policy=deploy/ar-cleanup-policy.json
```

(Policy file lives alongside this doc: `deploy/ar-cleanup-policy.json`. Add `--dry-run`
to preview what it would delete first.)

---

## Ongoing rules (important)

- **The cloud UI is now the only DB writer.** Once the cloud DB is live, stop importing
  CSVs into the local `start.bat` app — that would fork the database. The desktop
  "app" from now on is just the Cloud Run URL in a browser (the desktop SPA is baked
  into the image). `start.bat` stays for development only.
- **Back up the DB periodically** (it's your only copy of the portfolio):

  ```powershell
  gcloud storage cp gs://$BUCKET/portfyl.db ./backups/portfyl-$(Get-Date -Format yyyyMMdd).db
  ```

- **Redeploy after backend changes**: re-run the step-4 command (env vars persist across
  redeploys unless you change them; `--source .` rebuilds).

## Notes / risks

- **SQLite on GCS FUSE**: fine for this single-user, single-instance, tiny-DB case — the
  app uses the default rollback-journal (no WAL/shared-memory files, which FUSE can't
  do). `--max-instances=1` guarantees a single writer; **never raise it** without moving
  off SQLite. Each commit re-uploads the small DB file to GCS (sub-second at ~0.4 MB).
- **Cold start**: the first request after idle spins the container up and runs the
  startup FX backfill — a few seconds. Acceptable at $0. The paid escape hatch is
  `--min-instances=1` (~$10+/mo), which you almost certainly don't want.
- **Region**: keep `us-central1`. A European region (e.g. `europe-west3`) would push GCS
  storage/egress out of the always-free tier and start costing a little.
- This is Phase 1 only. Phase 2 (bearer-token `/api/auth/login` + Capacitor CORS origins)
  is what the native Android app needs on top of this; it flows to Cloud Run on the next
  `gcloud run deploy`.
