# Portfyl API Rate Limiting Design

## Status

Approved in conversation on 2026-09-05.

## Goal

Close the last open Phase 1 item ("configure ... rate limits") from the SaaS
master plan by bounding abusive or runaway request volume against the cloud
API. Cloud Run runs multiple stateless instances with no Redis in the stack,
so the limiter must share state through the one thing every instance already
has: PostgreSQL.

## Explicitly out of scope

Password entry, registration, and password reset never reach the Portfyl
backend — `frontend/src/auth/firebase.js` calls the Firebase Auth SDK directly
from the browser, and Firebase applies its own (undocumented, non-configurable)
anti-abuse throttling to sign-in attempts and a published daily quota to
password-reset e-mails. This design adds nothing there; it only covers traffic
that reaches `backend/main.py`. The only auth-adjacent surface this design
touches is `/api/auth/session` (the token-exchange call *after* Firebase has
already verified a password), because that endpoint calls the Firebase Admin
SDK's `verify_id_token` and provisions database rows on every hit.

## Edition scope

Cloud only. Local is a single self-hosted owner instance with no external
threat model, matching how `tax_report`/`screener` and other cloud-only
concerns are already gated by `Edition` in `main.py`. The whole subsystem
(table population, middleware, dependency, cleanup job) is inert in local.

## Data model

New migration `0012_rate_limit_buckets.py` adds:

```text
rate_limit_buckets
  key          text primary key   -- "{rule}:{identity}:{window_index}"
  count        integer not null default 0
  expires_at   timestamptz not null
```

A single composite text `key` (rather than separate rule/identity/window
columns) keeps the increment a one-row upsert with no secondary index, and
keeps the cleanup query a single `expires_at` range scan. This is a deliberate
new table, not a reuse of `UsageCounter`: `UsageCounter`/`UsageReservation`
exist for monthly billing-quota accounting with reservation/finalization
semantics, which is a different concern from short-window abuse throttling and
would be actively misleading to overload for this purpose.

Increment is one round trip, race-free without advisory locks, and portable to
both the Postgres cloud database and the SQLite fast-test fixture (both
support `ON CONFLICT ... DO UPDATE ... RETURNING` in the versions this project
already requires):

```sql
INSERT INTO rate_limit_buckets (key, count, expires_at)
VALUES (:key, 1, :expires_at)
ON CONFLICT (key) DO UPDATE
  SET count = rate_limit_buckets.count + 1
RETURNING count;
```

Windows are fixed (not sliding): `window_index = floor(now / window_seconds)`
folded into the key, so a bucket's `expires_at` never needs updating after
creation — it is set once from the window's own boundary. This matches the
precision-vs-simplicity level this codebase already accepts for period-based
counting (`UsageCounter.period_start`/`period_end` are fixed windows too, not
a sliding log).

## `backend/rate_limit.py`

- `RateLimitExceeded(Exception)` carrying `retry_after_seconds: int`, with a
  registered handler (`app.add_exception_handler`) returning a 429 with a
  `Retry-After` header — the same shape as `EntitlementDenied` and
  `RequestContextError` already use in `main.py`.
- `client_ip(request: Request) -> str`: `CF-Connecting-IP` header, else the
  last hop of `X-Forwarded-For`, else `request.client.host`. Documented as
  best-effort, not a security boundary — spoofing it only lets a caller reset
  their own bucket, it cannot bypass session/CSRF authentication or reach
  another workspace's data.
- `check_rate_limit(db, *, rule: str, identity: str, limit: int, window_seconds: int) -> None`:
  runs the upsert above and raises `RateLimitExceeded` when the returned count
  exceeds `limit`.
- `rate_limit(rule: str, *, by: Literal["ip", "workspace"]) -> Callable`: a
  dependency factory in the same shape as `entitlements.require_capability`.
  `by="ip"` depends only on `Request` (no session required — this is the mode
  `/api/auth/session` uses, since no workspace exists before that call
  succeeds). `by="workspace"` additionally depends on `get_request_context`
  and resolves `identity` from `RequestContext.workspace.id` (the mode broker
  sync and assistant chat use, since both already require an authenticated
  session).
- Every limit and window is read from an environment variable with a coded
  default (e.g. `RATE_LIMIT_GLOBAL_PER_MINUTE`, `RATE_LIMIT_AUTH_SESSION_PER_MINUTE`,
  `RATE_LIMIT_BROKER_SYNC_PER_MINUTE`, `RATE_LIMIT_ASSISTANT_CHAT_PER_MINUTE`),
  matching the existing tunable-via-env-var convention
  (`DIVIDEND_NOTIFY_INTERVAL_SECONDS`, `BROKER_AUTOSYNC_ENABLED`, ...).

## Enforcement points

1. **Global default** — an `@app.middleware("http")` function registered only
   when `PORTFYL_EDITION is Edition.CLOUD`, wrapping every `/api/*` request,
   keyed by `client_ip`. On a limit hit it returns a `JSONResponse(429, ...)`
   directly (a raw ASGI-style ordering issue: code raised from *inside* an
   `@app.middleware("http")` function itself, as opposed to from
   `call_next()`, does not pass through `add_exception_handler` handlers, so
   the middleware constructs the response itself rather than raising).
   Default: 120 requests/minute/IP.
2. **Targeted, tighter limits** via `Depends(rate_limit("<rule>"))` added
   alongside each route's existing dependencies:
   - `/api/auth/session` — per-IP (10/min default): bounds Firebase
     token-verification and identity-provisioning abuse.
   - `/api/broker/trading212/sync`, `/api/ibkr/sync`, the Polymarket sync
     endpoint — per-workspace (5/min default): bounds external broker/API
     quota burn from a single tenant.
   - `/api/assistant/chat` — per-workspace (20/min default): bounds server
     load from one workspace even though the AI key itself is BYOK.

Global and targeted limits are independent and both apply — the targeted
dependency does not replace the middleware's blanket check on the same
request.

## Cleanup

A new `rate_limit_cleanup` recurring job registered in the existing
Cloud-Scheduler-driven `internal_jobs.py`/`jobs.py` pattern (the same place
`billing`'s heartbeat lives today per `RECURRING_JOB_NAMES`), deleting rows
where `expires_at < now()`. No new infrastructure, no new scheduling
mechanism, health-check coverage falls out of the existing job-freshness
pattern in `main.py`'s `/health`.

## Testing

- Fast suite: boot the cloud edition app (existing `_reload_main` pattern from
  `tests/test_internal_jobs.py`/`tests/test_edition_routes.py`), fire N+1
  rapid requests against a targeted route and against the global default,
  assert the 429 body and `Retry-After` header on the (N+1)th, and assert the
  local edition never enforces either layer (no middleware registered, no
  429 regardless of request volume).
- PostgreSQL suite: two concurrent sessions incrementing the same bucket key
  never lose an increment (proves the upsert is race-free under a real
  transactional database, which SQLite's single-writer fast suite cannot
  prove).
- Migration upgrade/downgrade check for `0012_rate_limit_buckets`.

## Non-goals

- Anything touching Firebase-side login/registration/password-reset
  throttling (out of scope; see above).
- Redis, Cloudflare edge rate-limiting rules, or any other new piece of
  infrastructure.
- Per-user (as opposed to per-workspace) granularity for authenticated
  limits — a workspace is the existing tenancy/billing unit everywhere else
  in this codebase, and splitting rate limits to a finer grain than that would
  be inconsistent with how quotas are already modeled.
- Sliding-window or leaky-bucket precision — fixed windows match the
  precision level this codebase already accepts for period-based counting.
- Rate-limiting the OIDC-authenticated `/internal/jobs/*` Cloud Scheduler
  endpoints — those already have their own auth/lock/idempotency model and
  are never reached by ordinary customer traffic.
