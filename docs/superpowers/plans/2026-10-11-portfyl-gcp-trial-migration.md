# Portfyl → new Google Cloud account (free-trial credits) Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> **Status (2026-10-16): Waves 0–3 DONE — all production traffic (portfyl.com and app.portfyl.com) and the scheduler run from `portfyl-prod-f6shqb`. Wave 4 decommission DONE 2026-10-18 (see Task 8). Open: day-75 checklist (upgrade to paid by 2026-12-26, `min-instances` back to 0), optional Wave 5 and Track S.**

**Goal:** Run the production Portfyl cloud edition (portfyl.com / app.portfyl.com) from a brand-new Google Cloud account that holds the USD 300 / 90-day free-trial credit, and use the credit on one-off work that leaves no standing cost.

**Architecture:** Stand up a full second copy of the GCP side (Cloud Run service + migration Job, Scheduler, Secret Manager, Artifact Registry) in a new project, dark-test it against the *same* Neon database, then flip traffic by changing one URL in the Cloudflare Worker. Firebase Auth and the Cloud KMS key stay in the old project in phase 1 (cross-project IAM) so no user, password or encrypted secret has to move. Experiments live in a separate, deletable sandbox project.

**Tech Stack:** gcloud, Cloud Run, Cloud Scheduler, Secret Manager, Artifact Registry, Cloud KMS, Firebase Admin (ADC), Neon PostgreSQL (unchanged), Cloudflare Worker `portfyl-beta-proxy` + Access.

**Spec:** `deploy/cloudrun.md` (runbook; sections 1–9 are reused verbatim with new `$PROJECT_ID`), `docs/operations/private-beta-access.md` (Worker/Access topology), `docs/superpowers/plans/2026-09-04-portfyl-secrets-jobs.md` (KMS/jobs).

## Decisions (confirmed by the owner 2026-10-11)

1. New Google account: `support@portfyl.com` (holds the USD 300 trial).
2. **Variant A:** Firebase Auth and the Cloud KMS key stay in the old project `portfyl-cloud-fstxby`; the new project borrows them via cross-project IAM. Wave 5 (full move) stays optional. Consequence: the old project and its billing account must stay alive; `support@portfyl.com` is also made Owner of the old project so Portfyl does not depend on a single Google account.
3. The `portfyl.com` apex is served through the Cloudflare Worker, not a Cloud Run domain mapping.
4. Region stays europe-west1 (open: europe-west3 later).

## Progress log

**2026-10-16 — Wave 3 step 3 (apex) done.**
- Found `portfyl.com` returning 500: the old project's domain mapping still pointed at the old service, whose instances no longer start (Cloud Run: "instance could not start successfully", startup TCP probe failed). Most likely cause: its old image fails `assert_alembic_head()` now that the shared Neon database has newer migrations, so the apex has probably been down since shortly after the 2026-10-11 cutover.
- Added the Worker route `portfyl.com/*` to `portfyl-beta-proxy` (version `43bc9c11-2719-4f69-9d4e-583ad4603d82`). The Worker now sends the edge token only for `app.portfyl.com`, so apex `/api` keeps failing closed exactly as before. No DNS change was needed (the apex records are proxied, so the Worker route takes precedence over the Google origin).
- Checks: apex `/`, `/demo`, `/logo.png`, `/assets/*`, `/landing/*.png` → 200; apex `/api/*`, `/dashboard`, `/register` → 302 to the path-scoped Access app; `app.portfyl.com` unchanged (302 to Access). HTML is byte-identical to the origin.
- The old domain mapping `portfyl.com` in `portfyl-cloud-fstxby` is now unused; delete it with the rest of Wave 4.
- Not migration-related: the browser console shows the theme pre-paint inline script in `frontend/index.html` blocked by the CSP `script-src`.

**2026-10-11 evening — Wave 3 Stage A done** (app.portfyl.com Worker repointed, old Scheduler jobs paused, new ones resumed; Firebase login and cross-project KMS verified). Since then the new service was redeployed several times from `main` and `portfyl-broker-backfill` was added; see `deploy/cloudrun.md` "Routine redeploy".

**2026-10-11 — Waves 0–2 done, Wave 3 (cutover) NOT started. Production untouched.**
- New project `portfyl-prod-f6shqb`, billing `01FE9A-51DB4B-1D4009` (CZK), credit 6436 CZK expires **2027-01-10**, upgrade-to-paid deadline **2026-12-26**; budget alert 600 CZK gross.
- Secrets copied byte-exact (REST/base64; gcloud CLI piping on Windows corrupts CR/LF — never use it for secrets). Service accounts runtime/migrator/scheduler created.
- Old project: new runtime SA granted KMS encrypt/decrypt (key is in **europe-west3**), `firebaseauth.admin`; `support@portfyl.com` is Owner (invited via console).
- Image copied by digest `sha256:9893791338d3d07b749a50a1b7c9c62125873803a53de89fb68efaa78ee4d5b3` (prod revision `portfyl-00014-dl7`, tag c905e49) to `europe-west1-docker.pkg.dev/portfyl-prod-f6shqb/cloud-run-source-deploy/portfyl`. Temporary reader grant on the old repo was revoked.
- Migration Job `portfyl-migrate` ran OK (no-op). Service `portfyl` revision `portfyl-00001-lt2` at `https://portfyl-812512242326.europe-west1.run.app` (matches `PORTFYL_SERVICE_URL`). Extra env: `GOOGLE_CLOUD_PROJECT=portfyl-cloud-fstxby`; `identitytoolkit.googleapis.com` enabled in the new project.
- Dark checks passed: direct origin and forged headers → 403 `untrusted_edge`; with edge token `/api/capabilities` 200 (edition cloud), `/api/auth/me` 401; `/health` identical to prod (DB ok).
- Scheduler: **prod only has 5 jobs** (alerts `*/15`, autosync hourly, dividends 12h, rate-limit-cleanup hourly, account-deletion-cleanup daily). `portfyl-broker-backfill` from runbook §9 does **not exist in prod**, which is why `/health` shows `broker_backfill: stale` in both. Mirrored the 5 jobs in the new project, all **PAUSED**. Decide separately whether to add backfill.
- Not yet verified (needs a real login at cutover with instant rollback): Firebase login on the new service, broker-secret decryption via the cross-project KMS key.

## Global Constraints

- Current prod: project `portfyl-cloud-fstxby`, service `portfyl` in **europe-west1**, images in europe-west3 Artifact Registry, gcloud account `tom.zoubek@gmail.com`, billing account `01951C-ABDF80-E73236`.
- `PORTFYL_ACCOUNT_FINGERPRINT_KEY` must be **copied, never regenerated** (runbook §4: rotating it makes existing T212 account bindings unverifiable).
- `PORTFYL_EDGE_TOKEN` must be **copied** so the Cloudflare Worker secret stays valid.
- Migrations run through the migration Job *before* any service deploy; `EXPECTED_ALEMBIC_HEAD` must equal `alembic heads` (CLAUDE.md). This plan adds **no** migration.
- The new service and the old service share one Neon database; both must never run Scheduler jobs at the same time (duplicate Discord alerts / syncs even though advisory locks prevent overlapping runs).
- Free-trial limits (Google docs): no GPUs, no quota-increase requests, no Marketplace purchases, some premium partner models may not be payable with credit; the trial billing account **stops all resources when credit is exhausted or after 90 days unless upgraded to a paid account** (upgrading keeps unused credit until it expires).
- Parallel-session safety: one branch/worktree per session; Wave 1+ are `gcloud` operations on the *new* project only; repo edits are confined to the files named per task (no `database.py`, no `alembic/versions/`, no lockfiles).

## Review Focus

1. **Encrypted broker keys unreadable after move** — KMS ciphertext stored in `broker_*_ciphertext` columns is bound to the old key; a new key in the new project returns a decrypt error on first broker sync. Expect: phase 1 keeps the old key via cross-project IAM; phase 2 re-encrypts before the old project is deleted.
2. **Firebase token verification uses the wrong project** — `firebase_admin.initialize_app()` (backend/firebase_identity.py:30) takes the project from the runtime environment; on the new Cloud Run it would silently become the *new* project and every login would 401. Expect: `GOOGLE_CLOUD_PROJECT=<old firebase project>` set explicitly and a post-deploy login test.
3. **Double scheduler** — both projects' Scheduler jobs firing against one Neon DB. Expect: new jobs created then paused, old jobs paused at cutover, resumed in that order.
4. **Trial cliff** — day 90 stops the new project and portfyl.com goes down. Expect: upgrade to paid no later than day 75, `min-instances` back to 0, budget alerts live.
5. **Direct-origin bypass** — new `*.run.app` URL must still return 403 `untrusted_edge` without the edge token (runbook §7).

---

## Wave 0 — Manual, owner only (browser + card)

### Task 0: Sign-in and billing
**Files:** none (account state only)
**Produces:** `NEW_ACCOUNT` (gcloud credential), `NEW_BILLING_ID`, `NEW_PROJECT_ID`.

- [ ] **Step 1:** Confirm the new Google account's trial is active: console.cloud.google.com → Billing → note the credit amount, currency and **expiry date**; put `expiry − 15 days` in a calendar as "UPGRADE GCP".
- [ ] **Step 2:** `gcloud auth login` (browser) with the new account. Verify: `gcloud auth list` shows both accounts; do **not** change the active account yet.
- [ ] **Step 3:** Use a named configuration so the two accounts can never be mixed in one shell:
  ```powershell
  gcloud config configurations create newgcp
  gcloud config set account NEW_ACCOUNT_EMAIL
  gcloud billing accounts list    # copy NEW_BILLING_ID
  ```
- [ ] **Step 4:** Add the old account as `roles/owner` on the new project after Task 1 (rollback access if the new account is lost).

## Wave 1 — Empty infrastructure in the new project (no production impact)

### Task 1: Project, APIs, budgets
**Files:** none in repo; follow `deploy/cloudrun.md` §0–2, §8.
- [ ] **Step 1:** `$PROJECT_ID="portfyl-prod-<random>"`, `$REGION="europe-west1"` (keep identical to prod so Cloud Run URLs/latency behave the same; moving to europe-west3 next to Neon is a separate optimisation).
- [ ] **Step 2:** Create project, link `NEW_BILLING_ID`, enable the §2 API list **plus** `billingbudgets.googleapis.com`.
- [ ] **Step 3:** Budget alert at ~25 USD with 50/90/100 % thresholds on the new billing account (currency must match the account; see §8).
- [ ] **Step 4:** Verify `gcloud billing projects describe $PROJECT_ID` → `billingEnabled: true`.

### Task 2: Secrets (copied, not regenerated)
**Files:** none in repo.
- [ ] **Step 1:** For each of the six secrets in runbook §4, pipe old → new without printing:
  ```powershell
  gcloud secrets create portfyl-edge-token --project=$NEW --replication-policy=automatic
  gcloud secrets versions access latest --secret=portfyl-edge-token --project=portfyl-cloud-fstxby | gcloud secrets versions add portfyl-edge-token --project=$NEW --data-file=-
  ```
  Repeat for `portfyl-database-url`, `portfyl-job-database-url`, `portfyl-migration-database-url`, `portfyl-rate-limit-key-secret`, `portfyl-account-fingerprint-key`.
- [ ] **Step 2:** Create `portfyl-runtime`, `portfyl-migrator`, `portfyl-scheduler` service accounts and the same `secretAccessor` bindings as §4/§9 (migrator → only the migration URL).
- [ ] **Step 3:** Verify with `gcloud secrets list --project=$NEW` (6 entries) and `versions list` (1 enabled version each).

### Task 3: Cross-project access to old KMS key and old Firebase
- [ ] **Step 1:** On the **old** project grant the **new** runtime SA:
  ```powershell
  gcloud kms keys add-iam-policy-binding secrets --keyring=portfyl --location=<KEY_LOCATION> --project=portfyl-cloud-fstxby --member="serviceAccount:portfyl-runtime@$NEW.iam.gserviceaccount.com" --role="roles/cloudkms.cryptoKeyEncrypterDecrypter"
  gcloud projects add-iam-policy-binding portfyl-cloud-fstxby --member="serviceAccount:portfyl-runtime@$NEW.iam.gserviceaccount.com" --role="roles/firebaseauth.admin"
  ```
  (**Done 2026-10-11:** the real key location is **europe-west3** (`projects/portfyl-cloud-fstxby/locations/europe-west3/keyRings/portfyl/cryptoKeys/secrets`), not europe-west1. Use `--location=europe-west3` above and `<KEY_LOCATION>` = `europe-west3` in Task 4. Both grants applied and verified.)
- [ ] **Step 2:** Verify with `gcloud kms keys get-iam-policy` that only the old runtime SA and the new runtime SA are bound.
- [ ] **Step 3 (BLOCKED for gcloud — `SOLO_MUST_INVITE_OWNERS`; must be done in the console by invitation: IAM & Admin → Grant access → `support@portfyl.com` → Owner, then accept the e-mail invitation):** Make `support@portfyl.com` Owner of the old project so it never depends on one Google account: `gcloud projects add-iam-policy-binding portfyl-cloud-fstxby --member="user:support@portfyl.com" --role="roles/owner"` (run as `tom.zoubek@gmail.com`; the owner confirms before this runs). Verify with `gcloud projects get-iam-policy`.

## Wave 2 — Deploy dark and test

### Task 4: Image, migration Job, service (no traffic yet)
**Files:** none unless the build needs `VITE_FIREBASE_*` args (unchanged in phase 1 — same Firebase project).
- [ ] **Step 1:** Copy the *current prod digest* instead of building new code, so behaviour is identical: `gcloud artifacts docker images copy` old digest → new Artifact Registry (or `gcloud builds submit` from the same git SHA). Record the digest.
- [ ] **Step 2:** `deploy/run-migrations.ps1` against the new project's Job (no-op: Neon is already at head). Must exit 0.
- [ ] **Step 3:** Deploy the service per runbook §6 with these deltas in `--set-env-vars`: `GOOGLE_CLOUD_PROJECT=portfyl-cloud-fstxby` and `PORTFYL_KMS_KEY_NAME=projects/portfyl-cloud-fstxby/locations/<KEY_LOCATION>/keyRings/portfyl/cryptoKeys/secrets`. Nothing routes to the new URL yet, so this is safe.
- [ ] **Step 4:** Set `PORTFYL_SERVICE_URL` and `PORTFYL_SCHEDULER_SERVICE_ACCOUNT` (runbook §9) to the **new** URL.

### Task 5: Dark verification (done *before* cutover)
- [ ] **Step 1:** Direct `curl https://<new>.run.app/api/auth/me` → **403 untrusted_edge**.
- [ ] **Step 2:** Add a *test* Worker route (or temporary staging hostname) pointing at the new URL with the edge token; sign in with the owner account → dashboard loads (proves Firebase project + RLS + Neon).
- [ ] **Step 3:** Open Settings / trigger a broker sync → stored broker secret decrypts (proves cross-project KMS). Any `Could not decrypt` / KMS 403 = stop.
- [ ] **Step 4:** Create the six Scheduler jobs from runbook §9, then immediately `gcloud scheduler jobs pause` each. Run one manually (`jobs run portfyl-alerts`) and check `/health`.

## Wave 3 — Cutover (maintenance window, ~15 min)

### Task 6: Flip traffic
**Files:** Modify `deploy/cloudflare/portfyl-beta-proxy.js` / `wrangler.jsonc` (upstream URL only); Modify `deploy/cloudrun.md` header + "Routine redeploy" block (new project id); Modify `docs/operations/private-beta-access.md` (service URL mention).
- [x] **Step 1:** Pause the six **old** Scheduler jobs.
- [x] **Step 2:** Update the Worker's upstream to the new Cloud Run URL; deploy with wrangler (see `deploy/cloudflare/README.md`). Check `app.portfyl.com` → Access login → 200, unauthenticated `/api/auth/me` → 401 (expected).
- [x] **Step 3:** `portfyl.com` apex currently uses a Cloud Run **domain mapping** in the old project. Preferred: serve the apex through the same Worker (removes the Google-managed-cert + Search Console ownership dependency on the new Google account). Fallback: recreate the mapping in the new project (needs domain verification by the new account).
- [x] **Step 4:** Resume the six **new** Scheduler jobs; force-run one; confirm `/health` `checks.scheduler.status` = ok within the hour.
- [x] **Step 5:** Cloudflare cache purge for `/` and `/landing/*` if assets differ (see 2026-09-11 note in `docs/operations/2026-09-10-public-landing.md`).
- [x] **Step 6:** Commit only the three files above on branch `chore/gcp-new-account`; do not touch `database.py` or migrations.

### Rollback (any time before Task 8)
Point the Worker back to the old URL, pause new jobs, resume old jobs. The old service is untouched until Task 8.

## Wave 4 — Decommission old compute (≥ 7 days after cutover)

### Task 7: Watch period
- [ ] Daily: Cloud Run error logs, `/health`, Neon connection count, billing report of the new account (credit burn per day).

### Task 8: Shrink the old project
**2026-10-18 DONE (owner OK):** monitoring recreated in the new project first (it had not been migrated: e-mail channel, uptime check `portfyl-dependency-health-NmUTTRmllrI`, the 3 policies from `deploy/monitoring-policies.json`). Then deleted in the old project: Cloud Run `portfyl` (europe-west1 + europe-west3), domain mapping `portfyl.com`, the 5 Scheduler jobs, Cloud Run jobs `portfyl-beta-admin` + `portfyl-migrate` (x2), the Artifact Registry repo (whole repo, no rollback tag kept: the new project holds its own images and the old service no longer exists to roll back to), the uptime check and its alert policy (the 5xx and scheduler policies are left disabled). Last real user traffic on the old service was 2026-10-16 16:34 UTC. `deploy/manage-beta-tester.ps1` now targets the new project. Still open: old project's budget alert (~5 USD).
- [x] Delete old Cloud Run services (europe-west1 and europe-west3), old Scheduler jobs, old Artifact Registry repo (keep one rollback image tag for 14 days). **Keep** the project (Firebase Auth + KMS key still live there) and its billing account; set its budget alert to ~5 USD.

## Wave 5 — Phase 2 (optional, before trial day 75): fully leave the old project

### Task 9: Re-encrypt secrets and (optionally) move Firebase Auth
**Files:** Create `deploy/reencrypt-secrets.py` (one-off: reads `*_ciphertext` + `*_key_version`, decrypts with old key, encrypts with new key, writes back in one transaction per workspace under the migration role). Test: `backend/tests/test_reencrypt_secrets.py` using the fake-KMS-client pattern from `backend/tests/test_secrets_crypto.py`.
- [ ] Write failing test (fake old/new cipher; plaintext preserved, `key_version` updated), implement, run `python -m pytest tests/test_reencrypt_secrets.py -v` from `backend/`.
- [ ] Firebase move is **optional** and the riskier half: `firebase auth:export` + `auth:import` with the old project's scrypt hash parameters preserves UIDs but changes `VITE_FIREBASE_*` (frontend rebuild), authorized domains and API key. Only do it if the old project must be deleted; otherwise leave Auth where it is (free).

## Day-75 checklist (always)
- [ ] Billing → upgrade the new account to paid (unused credit is kept).
- [ ] `gcloud run services update portfyl --min-instances=0` if raised during the credit period.
- [ ] Budget alert still attached; delete the sandbox project (below).

---

# Track S — One-off credit spending (independent of Waves 0–5)

All experiments run in **`portfyl-sandbox-<random>`**, linked to the same trial billing account, with its own budget. Deleting the project (`gcloud projects delete`) removes every resource, so there is no tail cost. Never put these in the production project.

| # | Idea | Why it fits Portfyl | Est. credit use | Tail cost after deletion |
|---|------|---------------------|-----------------|--------------------------|
| S1 | **Production-shaped load test** (k6/Locust in a Cloud Run Job, 20 distinct-IP clients, burst behind one IP) | Runbook §7 lists it as an unmet gate before rate limits are trusted | < USD 5 | 0 |
| S2 | **Security sweep**: OWASP ZAP baseline + authenticated scan against a staging copy, plus the Alice/Bob isolation matrix on a throw-away Postgres | Matches the cybersecurity focus; beta go/no-go | < USD 10 | 0 |
| S3 | **Gemini on Vertex AI as LLM-judge** over several hundred assistant Q&A prompts (grounding, hallucination, Czech quality) | One-off evaluation of the in-app assistant without spending Anthropic budget | USD 10–40 | 0 |
| S4 | **Off-provider backup**: nightly `pg_dump` of Neon to a GCS bucket with 30-day lifecycle delete | Second copy outside Neon PITR | < USD 1 / month | ~USD 0.1–0.5 / month if kept (delete bucket otherwise) |
| S5 | **`min-instances=1` on prod for the trial period** (no cold starts for beta testers) | Better first impression during invites | ≈ USD 10–13 / month (estimate) | Revert to 0 on day 75 or it becomes a standing cost |
| S6 | **Disaster-recovery drill** end-to-end (restore Neon branch → `deploy/validate-restore.py` → staging service on it) | `docs/operations/neon-backup-restore.md` drill, proves the new project can recover | < USD 3 | 0 |

**Do not spend credit on:** GPUs (blocked on trial), committed-use discounts, Cloud SQL/Memorystore (Neon is the DB), load balancers/Cloud Armor (standing hourly cost), Marketplace products, Claude via Vertex AI (partner models may not be payable by trial credit — verify in Billing → Credits before relying on it).

## Realistic running cost after credits (production project)
Scale-to-zero Cloud Run (free tier ≈ 2 M requests, 180 k vCPU-s, 360 k GiB-s per month — verify on the pricing page), 6 Scheduler jobs (3 free, ~USD 0.1 each beyond), 6 secrets (~USD 0.4), 1 KMS key (~USD 0.06), small Artifact Registry. Expected single-digit USD per month — to be confirmed from the first 30 days of the new account's billing report, not guaranteed. Note `portfyl-broker-backfill` fires every minute (~43 k requests/month), well inside the free request tier.

## Self-review
- Coverage: new project, billing, secrets, KMS, Firebase, Worker/Cloudflare, scheduler, rollback, trial expiry, credit ideas, sandbox isolation — each has a task.
- Placeholders: `NEW_ACCOUNT_EMAIL`, `NEW_BILLING_ID`, `$NEW`, `<KEY_LOCATION>` are real unknowns resolved in Tasks 0/3, not TODOs.
- Decided: variant A (Firebase + KMS stay), apex via Worker, account `support@portfyl.com`. Still open: region europe-west1 vs. europe-west3 (default: keep europe-west1).
