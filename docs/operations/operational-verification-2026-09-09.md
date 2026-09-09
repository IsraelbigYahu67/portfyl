# Portfyl operational verification — 2026-09-09

> Follow-up: the missing Scheduler and monitoring configuration was repaired
> later the same day; all five job heartbeats became healthy, including the
> new due-deletion and bounded-retention cleanup. See
> [remediation evidence](operational-remediation-2026-09-09.md). The findings
> below preserve the original pre-remediation snapshot.

**Result: recovery verification PASS; overall operational readiness FAIL.**
The current private-test deployment serves requests and its database can be
restored with real portfolio data. Scheduled work and monitoring are not
configured in the deployed region. This report does not authorize public
access or claim that the private-beta launch gates are complete.

## Scope and method

- Inspected GCP project `portfyl-cloud-fstxby`, Cloud Run service `portfyl`,
  region `europe-west1`, using authenticated gcloud and Monitoring API reads.
- Inspected Neon project `little-bird-92332879` through its API and read-only
  PostgreSQL transactions. Production inspection used one repeatable-read
  snapshot with an owner role that can see all tenant rows.
- Probed the public hostname, direct-origin API, and dependency health.
- Created and validated a separate Neon recovery branch from an explicit WAL
  position, then booted the real cloud backend against the recovery branch.
- No production database writes, service redeployments, scheduler invocations,
  notifications, Access-policy changes, or production cutover were performed.
  The recovery smoke test wrote its rate-limit bucket only to the recovery branch.

## Live findings

| Check | Observed result | Assessment |
| --- | --- | --- |
| Cloud Run readiness | `portfyl-00004-kjd`; Ready/ConfigurationsReady/RoutesReady true; 100% traffic | PASS |
| Cloudflare private entry | `https://portfyl.com/` returns HTTP 302 | Consistent with private Access login; authenticated browser journey not tested here |
| Direct-origin API | `/api/auth/me` returns HTTP 403 | PASS: trusted-edge gate rejects direct unauthenticated origin access |
| Database dependency | `/health` reports database `ok` | PASS |
| Overall dependency health | HTTP 200 with JSON `status=degraded` | FAIL: checking HTTP status alone would miss this failure |
| Recurring jobs | `alerts`, `autosync`, `dividends`, `rate_limit_cleanup` all have missing heartbeats | FAIL |
| Cloud Scheduler | Job list empty in `europe-west1` | FAIL |
| Scheduler runtime configuration | `JOB_DATABASE_URL`, `PORTFYL_SERVICE_URL`, and `PORTFYL_SCHEDULER_SERVICE_ACCOUNT` absent from service environment | FAIL: creating cron entries alone is insufficient |
| Cloud Run Jobs | Job list empty in `europe-west1` | No currently configured migration/purge job in this region; historical executions do not establish current automation |
| Monitoring alert policies | Empty list, Monitoring API HTTP 200 | FAIL |
| Uptime checks | Empty list, Monitoring API HTTP 200 | FAIL |
| Notification channels | Empty list, Monitoring API HTTP 200 | FAIL; delivery cannot be exercised |
| Neon history | `history_retention_seconds=21600` (6 hours), PostgreSQL 18, `aws-eu-central-1` | Verified configuration; adequacy is not approved |
| Logging `_Default` | Global bucket ACTIVE, retention 30 days | Verified configuration |
| Logging `_Required` | Global bucket ACTIVE, locked, retention 400 days | Verified configuration |
| Current-revision errors | No matching HTTP 5xx or severity ERROR+ entries in bounded 7-day queries (limit 1,000) | Positive observation, not an uptime/SLO guarantee; older revisions have errors |

The empty scheduler list and missing heartbeats mean automated broker sync,
price/dividend checks, and rate-limit expiry cleanup cannot be treated as
operational. The workspace-deletion purge command exists in the repository,
but automated production execution was not established by this audit.

## Recovery evidence

- Source branch: `main` / `br-icy-poetry-b1p4g4w1`.
- Baseline snapshot: `2026-09-09T10:07:31.066603+00:00`.
- Recovery WAL position: `0/387CD48`.
- Recovery branch: `restore-drill-2026-09-09` /
  `br-twilight-block-b1yrvpgi`.
- Baseline file: `docs/operations/control-files/prod-20260909.json`, ignored by
  git because it contains exact aggregate counts and financial control totals.
- Source had transactions and 12 nonempty application tables. No raw holdings,
  transactions, credentials, or exact customer totals appear in this report.
- Recovery validation completed at `2026-09-09T10:08:06.506026+00:00`:
  Alembic head `0012_rate_limit_buckets`, all validator-listed tenant tables
  with forced RLS and policies, runtime role present without superuser or
  BYPASSRLS, and every captured table count/transaction control total matched.
- Runtime-role read check: unscoped portfolios were invisible; selecting the
  sampled workspace context exposed exactly its expected portfolio count.
  This is a recovery smoke check, not a substitute for the full Alice/Bob suite.
- Real backend boot against the branch completed successfully. `/` returned
  200; `/health` reported database `ok`; direct `/api/auth/me` returned 403;
  a locally simulated trusted-edge request returned 401 with
  `authentication_required`. No production edge credential was used.
- End-to-end smoke completed at `2026-09-09T10:09:36.692444+00:00`, about
  2 minutes 6 seconds after the baseline. This is observed drill elapsed time,
  including troubleshooting, not a promised incident RTO or a production failover.
- The CLI capture and validation paths also exited 0 against a fresh
  post-smoke branch baseline. This second baseline only validates the CLI;
  the original source-to-restore comparison above is the recovery evidence.
- The isolated branch was deleted after verification; a subsequent Neon branch
  listing contained only `main`. Production remained on `main`. The drill
  credential file was removed locally.

The initial branch-create request with explicit compute tuning returned HTTP
412. After confirming no branch had been created, creation with project-default
compute settings succeeded. The local deployment dotenv migration URL also
failed to connect; the current Neon API connection URI worked. Refresh local
deployment credentials before relying on that dotenv file in a future incident.

## Validator correction and tests

`deploy/validate-restore.py` now rejects a missing `portfyl_runtime` role.
Previously the missing-role flags contained false superuser/BYPASSRLS values,
which could pass validation. Capture and validation now enforce a read-only,
repeatable-read transaction so counts and financial totals use one snapshot.

- Focused restore-validator tests: **12 passed**.
- Complete fast backend suite: **578 passed**, 109 existing deprecation/ORM
  warnings, 22.90 seconds.
- Real Neon PostgreSQL capture/validation and runtime-role smoke: passed.
- Full disposable PostgreSQL test suite was not run: Docker engine was not
  available. Its destructive fixtures were never pointed at either production
  or the recovery branch.
- Frontend was unchanged; frontend tests/builds were not rerun.

## Remaining actions in priority order

1. **Restore scheduled operations.** Configure the direct job database
   connection and scheduler OIDC identity/audience; recreate the four jobs;
   verify successful heartbeats and failure visibility. Broker and notification
   jobs may contact providers/send messages, so their live execution is a
   separate remediation step, not part of this read-only production audit.
2. **Add monitoring and delivery.** Check the JSON health status, not only
   HTTP 200; cover missing/stale job heartbeats, 5xx, and availability. Establish
   the operator notification channel and verify actual delivery. A public
   Access-login response alone does not prove application availability.
3. **Complete retention operations.** Decide the required recovery window and
   compare it with the observed six hours. Approve a retention schedule for
   sessions, audits, usage reservations, notification history, diagnostics,
   and incident/support records, then implement bounded cleanup. Observed
   provider defaults are not an approved retention policy.
4. **Verify deletion execution.** Schedule the existing due-deletion command
   with appropriate identity, monitoring, and recovery/deletion safeguards;
   test it on disposable fixtures before allowing production deletions.
5. **Repair deployment reproducibility.** Refresh stale local connection
   configuration and re-establish the migration-job deployment path.
6. **Run an operator-attended incident tabletop.** Exercise a cross-tenant
   incident and credential compromise using the incident playbook. This
   recovery drill supplies restore evidence but does not close the human
   incident-response/notification exercise.

## API references

- [Neon branch creation](https://api-docs.neon.tech/reference/createprojectbranch)
  and [connection URI retrieval](https://api-docs.neon.tech/reference/getconnectionuri).
- [Neon project configuration](https://api-docs.neon.tech/reference/getproject)
  and [branch deletion](https://api-docs.neon.tech/reference/deleteprojectbranch).
- [Cloud Monitoring API](https://docs.cloud.google.com/monitoring/docs/apis).
