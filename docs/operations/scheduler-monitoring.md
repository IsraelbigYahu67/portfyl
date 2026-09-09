# Scheduler and monitoring operations

## Configuration

Use `deploy/operations.json` for the five recurring jobs, UTC cron schedules,
five-minute attempt deadline, and bounded retries. Use
`deploy/monitoring-policies.json` for alert policies, substituting the created
uptime check ID for `__HEALTH_CHECK_ID__` and the operator notification-channel
resource name for `__NOTIFICATION_CHANNEL__` before submitting each policy
to the Monitoring API. The health-check template additionally needs an
`uptime_url` monitored resource with the actual project ID and origin host.

- Alerts: every 15 minutes.
- Autosync: hourly; existing plan gates and per-connection opt-in still apply.
- Dividends: every 12 hours; existing plan/notification preferences still apply.
- Expired rate-limit buckets: hourly, using the existing bounded cleanup.
- Due account deletion and technical retention cleanup: daily at 03:17 UTC.
  The job rechecks the explicit request, 30-day deadline, sole ownership, and
  Firebase identity state before deletion. It also applies the bounded periods
  in `docs/compliance/private-test-retention-policy.md`.

Scheduler calls the direct service origin, with Google OIDC audience equal
to the exact service URL and caller equal to the dedicated `portfyl-scheduler`
service account. It does not use the public Cloudflare Access login route.
The caller has service-scoped Run Invoker access and no database secret access.
The Cloud Scheduler service agent retains its existing serviceAgent role.

The application needs all three settings together:

- `PORTFYL_SERVICE_URL`: exact origin URL.
- `PORTFYL_SCHEDULER_SERVICE_ACCOUNT`: expected OIDC caller e-mail.
- `JOB_DATABASE_URL`: Secret Manager reference to a **direct/unpooled** Neon
  URL for `portfyl_runtime`, which must remain NOSUPERUSER/NOBYPASSRLS.

The direct connection is necessary for the session-level advisory lock.
Ordinary web requests retain their existing pooled database connection.
Never give the scheduler an owner/BYPASSRLS connection or a production edge
token. Change environment with update flags so other settings are preserved.

## Monitoring semantics

The dependency uptime check polls the already available origin `/health` over
verified HTTPS every five minutes, with a 30-second timeout. It requires
`$.status` to equal the JSON string `"ok"`. In the REST configuration, the
`content` field must therefore contain `"\"ok\""`, not plain `"ok"`.

The three policies cover:

1. Dependency health failing from at least two checkers for five minutes,
   or a series producing no observations for 15 minutes. Database failures and
   missing/stale job heartbeats are covered through the aggregate health status.
2. At least five HTTP 5xx responses in a five-minute aligned window across
   the `portfyl` Cloud Run service's revisions.
3. ERROR-or-higher Cloud Scheduler logs for `portfyl-*` jobs, with notification
   rate limiting of 15 minutes.

This solves the HTTP-200/degraded blind spot without changing `/health` into
a failing container startup/liveness probe when a background job is stale.
Do not use dependency health as a container liveness check: restarting all
web instances cannot fix a missing scheduler.

The uptime probe verifies origin application dependencies. It does not prove
the full authenticated browser journey through Cloudflare/Firebase. Preserve
the private Access gate and check the public login route separately.

## Verification

1. Run the migration job with the exact candidate image digest; require a
   successful execution before deploying the service.
2. After deployment, confirm the revision is Ready and has the expected image,
   secret references, OIDC caller, and audience.
3. Unauthenticated POSTs to `/internal/jobs/rate_limit_cleanup` and
   `/internal/jobs/account_deletion_cleanup` must return 401. Direct-origin
   `/api/auth/me` must still return 403.
4. Invoke each configured job through Cloud Scheduler's `jobs.run` API or
   `gcloud scheduler jobs run`. The immediate acknowledgement is not proof of
   successful execution: wait for the corresponding heartbeat and successful
   execution status/log. Respect existing broker/notification preferences.
5. Require `/health` JSON status `ok`, database `ok`, and all five job statuses
   `ok` with fresh timestamps. Also observe subsequent scheduled runs.
6. Inspect Monitoring time series for the exact uptime check ID. Require
   successful observations, not only accepted configuration. Confirm the
   notification channel and linked policies are enabled.
7. Record notification receipt separately: an enabled e-mail channel or a
   successful check alone does not prove delivery to the operator's inbox.

## Failure handling

- OIDC 401/403: check the caller and exact audience, service-agent permission,
  and service environment. Do not bypass endpoint authentication.
- Database/lock failure: check the runtime role, direct hostname, current
  schema, secret access and version; do not switch to an owner role.
- Stale heartbeat with successful HTTP acknowledgement: inspect actual job
  outcome and provider failures. Some per-workspace failures are isolated;
  a global heartbeat alone does not guarantee every broker connection synced.
- Missing source image: rebuild the reviewed source and run migrations from
  the new digest. Protect active/rollback digests with the registry tags below.
- Rollback: use an already verified revision/image, retain the database head
  compatibility check, and preserve scheduler identity/secrets. A failed
  candidate must not cause traffic to be moved to an unready revision.

## Artifact retention

`deploy/ar-cleanup-policy.json` keeps five recent image versions, seven days
of recent images, and tags prefixed `production` or `rollback`. On each
successful release, move the previous production digest to `rollback` before
tagging the new digest `production`. Keep tags are required even when the
service itself still runs: Cloud Run retaining an imported image does not
ensure the source remains available for a new migration job or redeployment.

## References

- [Cloud Scheduler OIDC authentication](https://docs.cloud.google.com/scheduler/docs/http-target-auth).
- [Uptime JSON response matching](https://docs.cloud.google.com/monitoring/uptime-checks/response-validation).
- [Monitoring policy examples](https://docs.cloud.google.com/monitoring/alerts/policies-in-json).
- [Artifact Registry cleanup policies](https://docs.cloud.google.com/artifact-registry/docs/repositories/cleanup-policy).
