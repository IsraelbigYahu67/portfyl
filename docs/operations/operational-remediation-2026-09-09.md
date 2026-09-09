# Scheduler and monitoring remediation — 2026-09-09

This follows the [operational verification](operational-verification-2026-09-09.md).
The original findings are retained as historical evidence. This work restores
the recurring jobs, adds bounded account-deletion and data-retention execution,
sets up monitoring, verifies alert delivery, and repairs deployment-image
retention. It does not close the product, legal, or human-response launch gates.

## Deployed configuration

- Project/service/region: `portfyl-cloud-fstxby` / `portfyl` / `europe-west1`.
- Initial scheduler/monitoring Cloud Build:
  `1b71a191-5977-46f2-bbb7-9009b4e0c3eb`, SUCCESS at
  `2026-09-09T10:25:25.472355Z`, built from the reviewed repository source.
- Initial image digest:
  `sha256:22aac969362ad3736ea66cd583c6b99dc2686791f857496291997a8f6e25b840`.
- Initial migration execution: `portfyl-migrate-pwjm6`, successful at
  `2026-09-09T10:27:23.852256Z`, before the service deployment.
- Initial service revision: `portfyl-00005-xjq`.
- The deletion/retention release used successful Cloud Build
  `c969d487-2bac-4fed-992b-d5e1364327b8`, migration execution
  `portfyl-migrate-255p4` (completed `2026-09-09T15:40:34.529256Z`), and
  revision `portfyl-00006-knb`.
- A final dependency-remediation build
  `6b0d44d2-4ac9-4fb3-9a95-b8a631c5cfe8` completed successfully at
  `2026-09-09T15:59:52.983906Z`. Its immutable digest is
  `sha256:03c097f5080c8da24b4fd162820713a207c31eccbfd91f6c589f441535b7e20e`.
  Revision `portfyl-00007-99q` serves 100% of traffic from that digest.
- `JOB_DATABASE_URL` references the new `portfyl-job-database-url` secret.
  The direct Neon connection was verified as `portfyl_runtime` with neither
  superuser nor BYPASSRLS. The web database connection remains pooled.
- Added exact service URL and scheduler caller environment variables, while
  preserving existing edition, Firebase/KMS, trusted-edge, and rate-limit config.
- Created `portfyl-scheduler` with service-scoped Run Invoker. No database or
  Secret Manager permissions were granted to that caller. Only the runtime
  service account received access to the new job-connection secret.

## Scheduled jobs

All five jobs are enabled, use UTC, Google OIDC for the dedicated caller,
a 300-second attempt deadline, and at most three retries with 30–300-second
backoff. The versioned configuration is [operations.json](../../deploy/operations.json).

| Job | Schedule | Latest verified successful heartbeat (UTC) |
| --- | --- | --- |
| `portfyl-alerts` | Every 15 minutes | 16:00:03 |
| `portfyl-autosync` | Hourly | 16:00:05 |
| `portfyl-dividends` | Every 12 hours | 15:15:30 |
| `portfyl-rate-limit-cleanup` | Hourly | 16:00:04 |
| `portfyl-account-deletion-cleanup` | Daily at 03:17 | 16:01:24 |

Initial forced-run acknowledgements arrived before execution; the first short
verification window expired. The jobs then executed successfully. A successful
`jobs.run` API response alone was not accepted as completion evidence.

At `2026-09-09T16:01:24Z`, `/health` reported overall, database, scheduler,
and all five individual jobs `ok`. An unauthenticated cleanup POST with a body
returned 401, and direct-origin `/api/auth/me` still returned 403.

At preflight there were no configured Discord webhooks or broker connections
with auto-sync enabled. Plan checks and per-connection opt-in remain in place;
job success does not mean that a real broker transfer or customer notification
was exercised. The new daily cleanup rechecks the 30-day deletion grace period,
shared ownership, and Firebase identity before purging. It also removes bounded
batches of expired sessions, finalized usage reservations, terminal outbox
records, and old dividend-notification deduplication rows. Its live verification
scanned two workspaces and purged none; every retention category deleted zero
rows, as expected from the production preflight.

## Monitoring

- Uptime check: `portfyl-dependency-health-7NZKnYKEAMc`.
- Polls the origin `/health` over verified HTTPS every five minutes and requires
  JSON `$.status` to equal `"ok"`; HTTP 200 alone is insufficient.
- Enabled e-mail channel: `Portfyl operator`, using the previously approved
  private-test contact. Channel resource ID: `1302112073120385231`.
- Enabled policies:
  - `5370109422852485196`: unavailable/degraded dependency health or missing
    uptime observations.
  - `5360306657618571882`: at least five HTTP 5xx in a five-minute window.
  - `18444966715642255253`: Cloud Scheduler ERROR logs for `portfyl-*`.
- Policy templates are in
  [monitoring-policies.json](../../deploy/monitoring-policies.json), with
  resource placeholders rather than credentials or a hard-coded e-mail.

Monitoring recorded `check_passed=false` from all six checker locations during
the initial degraded state, despite `/health` returning HTTP 200. It then
recorded `check_passed=true` from `apac-singapore` at `10:31:40Z`, retrieved
at `10:32:05Z`, after all job heartbeats became healthy. This verifies both
failure detection and recovery through the actual Google checker; other
locations still had older observations at that instant.

Delivery was then tested with a temporary, exact-name Scheduler job targeting a
nonexistent internal endpoint. Scheduler recorded status code 9 for its run at
`2026-09-09T15:45:37.945880Z`, and the operator Gmail inbox received the
matching `Portfyl scheduler execution error` alert naming that job. The
temporary job was deleted immediately after receipt; the five production jobs
remained enabled.

## Deployment repair

The prior service's tag `private-test-plans-20260908-v2` and its digest were
absent from Artifact Registry. The first migration-job deployment therefore
failed with image-not-found; production traffic stayed on the healthy old
revision. The registry policy deleted any version older than zero seconds
except the newest single version, consistent with the loss of deployability.

Rebuilt the source, passed migrations, and deployed immutable digests. The
final digest is tagged `production`; the preceding working digest is tagged
`rollback`. The replacement registry policy,
previewed and then activated in `europe-west3`, keeps five recent versions,
seven days of recent images, and `production`/`rollback` tag prefixes. This
retains reusable release artifacts; it does not restore the old missing image.
Before a later release, move the current production digest to `rollback`.

Build uploads now exclude `*.log` in `.gcloudignore`; local operational logs
must not become part of a Cloud Build source archive. The final frontend
dependency lock resolved the 14 npm audit findings reported by the preceding
build. Its clean Cloud Build install audited 380 packages with zero findings.

## Verification and remaining boundaries

- Local and cloud frontend tests: **28 files / 151 tests passed** in each mode.
- Frontend dependency audit: **0 vulnerabilities** after a clean install.
- Python requirements audit: `pip-audit` found **0 known vulnerabilities**.
- Cloud production build: passed within Cloud Build.
- Backend fast suite: **584 passed**, 109 warnings.
- Full disposable PostgreSQL/RLS suite: **326 passed**, 10 warnings. Docker was
  started for this follow-up, and the disposable container/network were removed
  after the run.
- Migration completed and all five production job heartbeats are healthy.
- Scheduler execution logs explicitly recorded HTTP 200 for all five jobs;
  their API statuses were success (empty protobuf status, equivalent to code 0).
- Trusted-edge rejection and internal-job authentication remain effective.
- Private Cloudflare Access configuration was not changed.
- The private-test retention baseline is recorded in
  [private-test-retention-policy.md](../compliance/private-test-retention-policy.md).
  The six-hour Neon history is accepted only for the current private test.
- No payment or public-access configuration was introduced, and the verified
  cleanup runs did not delete any production workspace or retained row.

The original four jobs remained healthy from the first 10:30 UTC verification
through the 16:00 UTC checks. The new cleanup also completed twice. Continued
observation is routine operations rather than evidence claimed in advance.

Still open: an operator-attended incident exercise, a separately approved
public-beta recovery objective, controller/legal/public support decisions,
commercial market-data rights, product interviews, and private-beta evidence.
The automated technical incident rehearsal, including an isolated Secret
Manager version-rotation and old-version rejection check, is recorded in
[incident-tabletop-2026-09-09.md](incident-tabletop-2026-09-09.md); it does not
claim human attendance or a legal notification decision.

See [scheduler and monitoring runbook](scheduler-monitoring.md) for exact
checks, failure handling, and image-tag maintenance.
