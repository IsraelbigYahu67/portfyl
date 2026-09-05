# Billing verification — 2026-09-05

> **Historical record:** The Stripe runtime verified here was retired later on
> 2026-09-05 before payment activation. Its outstanding sandbox gate was
> intentionally canceled, not completed. Portfyl now exposes a comparison-only
> pricing page and no payment or automatic-trial runtime.

At the time of this verification, Workstream E remained **incomplete** because
the real Stripe sandbox lifecycle rehearsal had not passed. The implementation
was then retired, so that external gate was canceled rather than completed.
This record distinguishes the automated tests, infrastructure checks, and the
external payment checks that were outstanding at retirement.

## Code and regression found

Baseline: `230338d` (`feat: implement billing entitlements and Stripe lifecycle`).
Verification/fix branch: `codex/billing-verification`.

A real Cloud Scheduler call to `/internal/jobs/billing` returned HTTP 500:
`ValueError: Unknown recurring job: billing`. The endpoint called
`mark_job_succeeded()` after its pass, but `RECURRING_JOB_NAMES` omitted
`billing`. This affected even a safely disabled billing configuration.

Added `billing` to that registry and an endpoint regression test that runs the
real disabled-billing pass and verifies a persisted `JobRun` heartbeat. The
test first failed with the exact cloud error before the one-line fix.

## Automated verification

| Check | Result |
| --- | --- |
| Initial fast backend suite | 479 passed; 43.87 s |
| Initial PostgreSQL integration suite | 323 passed; 48.35 s |
| Final complete backend suite, including the new regression | **803 passed, no failures or skips; 60.01 s** |
| Frontend local edition | 25 files / 136 tests passed |
| Frontend cloud edition | 25 files / 136 tests passed |
| Local Vite production build | Passed |
| Cloud Vite production build | Passed |
| Cloud bundle inspection | No `Tax Report`, `/tax-report`, or `/screener`; contains `Plan & Billing` |
| Local bundle inspection | Contains local tools; no `Plan & Billing`, `Compare plans`, `Upgrade required`, or `/billing/checkout` |

Commands run from `backend/`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests --ignore=tests/postgres -q -ra
$env:TEST_DATABASE_URL='postgresql+psycopg://portfyl_test@127.0.0.1:55442/portfyl_test'
.\.venv\Scripts\python.exe -m pytest tests/postgres -q -ra
.\.venv\Scripts\python.exe -m pytest tests/test_internal_jobs.py::TestJobEndpointsRunExactlyOnePass::test_billing_endpoint_persists_a_successful_heartbeat -q
.\.venv\Scripts\python.exe -m pytest tests -q -ra
```

Frontend commands: `npm test`, `npm run test:cloud`, `npm run build`, and
`npm run build:cloud`. A separate local output directory was then built to
inspect both edition bundles without overwriting the cloud output.

The integration database was a newly initialized local PostgreSQL 16.15
cluster, bound only to `127.0.0.1:55442`, using a disposable `portfyl_test`
database. Production URLs were never supplied to pytest. Docker Desktop
failed to start because of its `dockerInference` socket; automatic approval
review rejected the attempted Docker process/socket repair. Standalone
PostgreSQL binaries from EDB provided the independent test runtime instead.

Existing non-fatal warnings: FastAPI startup/shutdown deprecations,
`datetime.utcnow()` deprecations, one SQLAlchemy identity-map warning in the
CSV replace test, and Vite's large-chunk warning.

## Neon and Cloud Run rehearsal

Project/region: `portfyl-cloud-fstxby` / `europe-west3`.
Temporary service/job prefix: `portfyl-billcheck-0905`.
Isolated empty Neon database: `portfyl_billing_verify_20260905_test`.
The service used its own Google runtime/scheduler identities and a dedicated
Secret Manager entry containing only the scratch database connection.

Neon migrations passed: `upgrade head` → `downgrade 0009_audit_log` →
`upgrade head` (`0010_billing_entitlements`). No production schema or
application data was migrated or changed.

Initial image build: `5350d9e2-92dc-4e10-a4df-9e774c0915e0`.
Heartbeat-fix image build: `22cb24d9-256a-4f40-a0e4-aa40a5b3fcb6`.

Post-fix revision: `portfyl-billcheck-0905-00003-rsb`.
Verified image digest:
`sha256:5ccb58da678e994bb5bbeea600e86bf82951b9afd84e9d0562317becdfed09f5`.

- No Authorization header: HTTP 401.
- Invalid bearer token: HTTP 403.
- A real Google-signed OIDC token for the dedicated scheduler identity was
  accepted. IAM propagation initially delayed token generation; the declared
  temporary token-creator binding subsequently took effect.
- While a separate direct PostgreSQL connection held the `billing` advisory
  lock, the HTTP response was exactly
  `{"job":"billing","skipped":"already running"}`.
- After releasing the lock, the response was
  `{"job":"billing","events":0}`. No HTTP 500 occurred in this successful
  post-fix request.
- A real Cloud Scheduler HTTP/OIDC invocation succeeded at
  `2026-09-05T10:08:59.583803Z`.
- A scan of 200 scratch-service Cloud Logging entries found no PostgreSQL URL,
  Neon hostname, Stripe secret-key prefix, webhook-secret prefix, or hosted
  Checkout-session URL. The expected lock-skip log was present.

**Scope:** This infrastructure rehearsal deliberately used
`PORTFYL_BILLING_ENABLED=0` and an empty database. It proves the deployed
endpoint, OIDC, lock contention, heartbeat, and Scheduler wiring. It does
**not** prove enabled Stripe reconciliation or the payment lifecycle.

The scratch Cloud Scheduler job, Cloud Run service, Secret Manager secret,
both temporary service accounts (including the temporary token-creator
binding), isolated empty Neon database, and both scratch image versions were
removed after verification. A final inventory showed only the pre-existing
`portfyl` service and its two database secrets.

## Canceled Stripe gate (historical)

The user confirmed no Stripe key has been configured. Neither the project
environment files, process environment, nor project Secret Manager contained
the required Stripe sandbox configuration. No real Stripe payment API calls
were made, and payment acceptance was not enabled.

The following checks were still required under the retired design:

- Verify the four Investor/Pro monthly/annual EUR Prices and Customer Portal.
- Forward signed webhooks with Stripe CLI and complete Checkout activation.
- Use test clocks to exercise renewal, failed payment, recovery during the
  grace period, grace expiry, cancellation, and resubscription to a new price
  generation.
- Replay duplicate and reversed events and verify the resulting subscription
  and entitlement projection against Stripe's actual state.
- Inspect logs during those payment scenarios for secret and customer-data
  leakage.

The mocked Stripe unit tests do not replace these external checks.
