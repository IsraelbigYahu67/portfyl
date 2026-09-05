# Portfyl API Rate Limiting Design

## Status

Approved in conversation on 2026-09-05 and revised after an
implementation-readiness review on the same date. This revision is the source
of truth for the implementation plan.

## Goal and protection boundary

Close the last open Phase 1 item ("configure ... rate limits") from the SaaS
master plan by bounding abusive or runaway request volume against the cloud
API. Cloud Run runs multiple stateless instances with no Redis in the stack,
so application-level limits share state through the one thing every instance
already has: PostgreSQL.

This is a cost and application-abuse guard, not volumetric DDoS protection.
Every checked request still reaches Cloud Run and causes a database write.
Cloudflare edge rate limiting remains the appropriate future layer for
absorbing high-volume traffic before it reaches the application, but is not a
dependency of this phase.

## Explicitly out of scope

Password entry, registration, and password reset never reach the Portfyl
backend: `frontend/src/auth/firebase.js` calls the Firebase Auth SDK directly
from the browser, and Firebase applies its own anti-abuse controls and quotas.
This design adds nothing there; it only covers traffic that reaches
`backend/main.py`.

The only auth-adjacent surface covered here is `/api/auth/session`, the token
exchange after Firebase has already verified an identity. That endpoint calls
the Firebase Admin SDK's `verify_id_token` and provisions database rows on
every hit, so it needs its own application-side limit.

Also out of scope:

- Redis or another shared rate-limit service.
- Sliding-window, token-bucket, or leaky-bucket precision.
- Per-user limits for authenticated operations; the workspace is Portfyl's
  existing tenancy and billing unit.
- Rate limiting `/internal/jobs/*`. Those endpoints use Google OIDC,
  PostgreSQL advisory locks, and idempotent job semantics and are not reachable
  through the customer API surface.

## Edition scope

Cloud only. Local is a single self-hosted owner instance with no external
threat model. The edge check, limiter middleware, targeted dependencies, and
cleanup scheduling are not registered in local. The mapped table still exists
in a migrated local database because both editions share one Alembic history,
but local request and job paths never read or write it.

## Trusted edge and client identity

An IP limit is meaningful only if callers cannot choose the IP header. The
current public Cloud Run origin and Uvicorn's permissive forwarded-header
configuration do not provide that guarantee by themselves.

The cloud deployment therefore adds an origin-auth contract:

1. Secret Manager stores a random `PORTFYL_EDGE_TOKEN` with no coded default.
2. Cloudflare overwrites any client-supplied value and injects the token into
   `X-Portfyl-Edge-Token` only on origin requests. The browser never receives
   or sends this header.
3. A cloud-only middleware requires exactly one header value and verifies it
   with `hmac.compare_digest()` for `/api` and `/api/*` before rate-limit state
   is touched. A missing, duplicated, or invalid token returns 403 with
   `{"code":"untrusted_edge"}`. `/health`, static assets, and the separately
   OIDC-authenticated `/internal/jobs/*` routes are not subject to this check.
4. `PORTFYL_EDGE_TOKEN` is required at cloud startup. Cloud must fail startup
   if it is absent or blank; local does not read it.

Only after the edge token succeeds may `client_ip(request)` trust
`CF-Connecting-IP`. It must:

- accept exactly one stripped header value;
- parse and canonicalize it with `ipaddress.ip_address()` so equivalent IPv6
  spellings share one identity;
- reject an absent, malformed, comma-separated, or overlong value with 400 and
  `{"code":"invalid_client_ip"}`;
- never fall back to `X-Forwarded-For` or `request.client.host` in cloud.

The limiter never stores the raw IP or workspace ID. It computes a stable
bucket key with HMAC-SHA256 over a length-delimited encoding of
`version`, `rule`, canonical `identity`, and `window_index`. A separate
Secret Manager secret, `RATE_LIMIT_KEY_SECRET`, is required at cloud startup
and is never logged. Rotation may reset active buckets once, which is an
acceptable and documented operational effect. Keeping it separate from the
edge token allows either secret to rotate independently.

## Data model

Migration `0012_rate_limit_buckets.py` and a corresponding
`models.RateLimitBucket` mapping add:

```text
rate_limit_buckets
  key          varchar(64) primary key  -- lowercase HMAC-SHA256 hex digest
  count        integer not null default 0 check (count >= 0)
  expires_at   timestamptz not null

index ix_rate_limit_buckets_expires_at (expires_at)
```

The opaque composite digest keeps the increment a one-row upsert, bounds the
indexed key length regardless of attacker input, and avoids retaining raw IP
addresses or workspace identifiers in the database and its backups. The
`expires_at` index supports bounded cleanup without scanning the entire live
table. Incrementing `count` does not change `expires_at`.

This is deliberately not a reuse of `UsageCounter` or `UsageReservation`.
Those tables provide monthly billing-quota accounting with
reservation/finalization semantics; short-window abuse throttling is a
different concern.

`rate_limit_buckets` is global infrastructure state, not tenant-owned domain
data. It does not use RLS and must be explicitly documented as an exception to
the tenant-table matrix. Migration `0012` grants
`SELECT, INSERT, UPDATE, DELETE` to `portfyl_runtime`; no other application
role receives new privileges.

## Fixed-window algorithm and transaction boundary

Windows are fixed:

```text
window_index = floor(now_utc_epoch_seconds / window_seconds)
expires_at   = epoch + ((window_index + 1) * window_seconds)
```

One aware UTC timestamp is captured per check and is used for the index,
expiry, and `Retry-After`. The clock is an injectable dependency in tests.
Fixed windows deliberately permit a boundary burst of up to twice the nominal
limit, for example requests immediately before and after a minute boundary.
That trade-off is accepted for this phase.

The increment is one race-free round trip:

```sql
INSERT INTO rate_limit_buckets (key, count, expires_at)
VALUES (:key, 1, :expires_at)
ON CONFLICT (key) DO UPDATE
  SET count = CASE
    WHEN rate_limit_buckets.count < :limit_plus_one
      THEN rate_limit_buckets.count + 1
    ELSE rate_limit_buckets.count
  END
RETURNING count, expires_at;
```

The limiter owns a new short-lived `SessionLocal` transaction for every
check. It must never use a route's `Depends(get_db)` session. The required
order is:

1. open the limiter session;
2. execute the upsert and capture the decision;
3. commit and close the limiter transaction;
4. only then raise `RateLimitExceeded` or allow the route to continue.

This ensures a later route rollback cannot erase the count, an over-limit
decision is committed before its exception is raised, and a slow broker or AI
request does not hold the bucket row lock for its full duration. A transaction
that cannot commit is not a successful check.

The global middleware runs the synchronous SQLAlchemy check through
Starlette/FastAPI's threadpool so it never blocks the async event loop.
Targeted dependencies are ordinary synchronous `def` dependencies, which
FastAPI likewise runs in its dependency threadpool.

Limiter database errors fail closed in cloud. They produce 503 with
`{"code":"rate_limiter_unavailable"}` and `Retry-After: 1`, and emit a
structured error log without the bucket key or identity. This is consistent
with the rest of the cloud API being database-dependent and avoids silently
dropping the abuse guard during a partial database failure.

The upsert is portable to PostgreSQL and the SQLite fast-test fixture; the
versions already required by this project support
`ON CONFLICT ... DO UPDATE ... RETURNING`.

## `backend/rate_limit.py`

The module owns these public units:

- `RateLimitRule`: immutable validated configuration containing `name`,
  `limit`, and `window_seconds`.
- `RateLimitExceeded(Exception)`: carries the rule name and
  `retry_after_seconds`.
- `client_ip(request: Request) -> str`: validates and canonicalizes the trusted
  `CF-Connecting-IP` value under the edge contract above.
- `consume_rate_limit(*, rule: RateLimitRule, identity: str) -> None`: hashes
  the bucket identity, performs and commits the isolated upsert, then raises
  when the committed count exceeds the limit.
- `rate_limit(rule_name: str, *, by: Literal["ip", "workspace"]) -> Callable`:
  a dependency factory shaped like `entitlements.require_capability`.

`by="ip"` depends only on `Request` and is used by `/api/auth/session`, where
no workspace exists yet. `by="workspace"` additionally depends on
`get_request_context` and uses `RequestContext.workspace.id` as the identity.
The dependency must run after authentication/context resolution. Requests
that fail authentication are still covered by the global IP middleware but do
not consume a workspace bucket.

## Configuration

Rules are declared centrally; route decorators contain rule names, never
literal numeric limits. Each rule has an explicit limit and window variable:

| Rule | Limit variable | Window variable | Default |
| --- | --- | --- | --- |
| `global` | `RATE_LIMIT_GLOBAL_LIMIT` | `RATE_LIMIT_GLOBAL_WINDOW_SECONDS` | 120 / 60 s |
| `auth_session` | `RATE_LIMIT_AUTH_SESSION_LIMIT` | `RATE_LIMIT_AUTH_SESSION_WINDOW_SECONDS` | 10 / 60 s |
| `broker_sync` | `RATE_LIMIT_BROKER_SYNC_LIMIT` | `RATE_LIMIT_BROKER_SYNC_WINDOW_SECONDS` | 5 / 60 s |
| `assistant_chat` | `RATE_LIMIT_ASSISTANT_CHAT_LIMIT` | `RATE_LIMIT_ASSISTANT_CHAT_WINDOW_SECONDS` | 20 / 60 s |

All values are parsed once at application startup and must be positive
integers. Zero, negative, blank, non-integer, or unknown rule configuration is
a startup error in cloud; there is no magic zero-means-disabled behavior.
Local does not parse these variables. The Cloud Run runbook lists every
variable and both required secrets.

## Enforcement and counting semantics

### Global default

A cloud-only HTTP middleware checks `global` for `/api` and `/api/*`, keyed by
canonical client IP. It runs after edge authentication and before routing.
It counts every non-OPTIONS request regardless of its eventual status,
including malformed, unauthenticated, forbidden, and unknown API requests.
CORS preflight `OPTIONS` requests are excluded so browsers do not spend a
bucket entry before the actual request.

### Targeted limits

The following route dependencies apply in addition to the global middleware:

- `/api/auth/session`: `auth_session`, per IP.
- `/api/broker/trading212/sync`: `broker_sync`, per workspace.
- `/api/broker/ibkr/sync`: `broker_sync`, per workspace.
- `/api/broker/polymarket/sync`: `broker_sync`, per workspace.
- `/api/assistant/chat`: `assistant_chat`, per workspace.

Global and targeted buckets are independent. A targeted dependency never
replaces the global check. Once the targeted check commits, the request counts
even if the downstream provider fails or the route transaction rolls back;
attempted external quota/cost consumption is what the limit bounds.

### Response contract and middleware ordering

An exceeded limit returns:

```text
HTTP 429
Content-Type: application/json
Retry-After: <integer seconds, minimum 1>

{"code":"rate_limit_exceeded","rule":"<public rule name>"}
```

`Retry-After` is `max(1, ceil(expires_at - captured_now))`. Rule names are
controlled constants and may be returned; identities and bucket keys never
are. Both 429 and limiter-generated 400/403/503 responses use
`Cache-Control: no-store`.

The effective middleware stack, from outermost to innermost, is correlation
ID, CORS, trusted-edge verification, global rate limiting, and routing. This
ensures direct 400, 403, 429, and 503 responses receive the expected
`Access-Control-Allow-Origin` headers and edge/limiter logs retain the request
correlation ID. The effective behavior is verified end to end rather than
inferred from decorator registration order.

## Cleanup and operational integration

A cloud-only `rate_limit_cleanup` recurring job follows the existing
Cloud-Scheduler-driven `internal_jobs.py`/`jobs.py` pattern and uses the same
non-blocking advisory-lock wrapper as the other recurring jobs.

- Schedule: hourly.
- Expired predicate: `expires_at <= now_utc`.
- Batch size: 10,000 rows.
- Maximum per invocation: 100,000 rows; remaining backlog is handled by later
  invocations and produces a structured warning log.
- Job freshness threshold in `/health`: two hours.

Implementation must explicitly:

- add `rate_limit_cleanup` to `RECURRING_JOB_NAMES`;
- add the internal job endpoint and `_JOB_MAX_AGES` entry;
- add the fourth Cloud Scheduler command and verification step to
  `deploy/cloudrun.md`;
- update `EXPECTED_ALEMBIC_HEAD`, schema/runtime-role tests, and restore
  validation's expected table inventory.

Cleanup health coverage does not arise automatically from registration; all
of the integration points above are required acceptance criteria.

## Observability and rollout

Emit these structured events using controlled rule names:

- `rate_limit_exceeded` at INFO with rule and retry-after seconds;
- `rate_limit_error` at ERROR with rule and exception type;
- `rate_limit_cleanup` at INFO with deleted-row and remaining-backlog counts.

Do not add one application log per allowed check; Uvicorn's access log already
covers accepted requests and logging every successful limiter write would
needlessly multiply production log volume. Cloud Monitoring log-based metrics
may be built from the three controlled events above.

Never log raw IPs, workspace IDs, HMAC bucket keys, edge tokens, or key
secrets. Existing correlation IDs remain available for request-level tracing.

Before enabling production enforcement, run a production-shaped load test
through Cloudflare against one Cloud Run instance in the deployment region.
It must include a captured normal SPA startup fan-out, 20 concurrent clients
with distinct IPs, a 30-request burst behind one shared IP, and concurrent
requests against one workspace. Compare the same workload with limiter checks
disabled in the test harness and record p50/p95 latency, SQLAlchemy pool wait,
PostgreSQL lock wait, and database write rate.

The rollout gate is: no SQLAlchemy pool timeout, no failed request below its
configured limit, no PostgreSQL lock wait above one second, less than 50 ms of
added p95 latency for the distinct-IP workload, and less than 250 ms of added
p95 latency for the shared-IP burst. The initial limits are defaults to
validate, not evidence-based constants; raise them before rollout if captured
normal Portfyl traffic can reach them. This phase is not complete if the
global middleware exhausts the current per-instance database pool
(`pool_size=5`, `max_overflow=2`) or misses any rollout gate.

## Testing

### Fast suite

- Cloud startup fails when either required secret or any rule configuration is
  invalid; local startup ignores all limiter configuration.
- Edge token is required for cloud `/api/*`; untrusted requests create no
  bucket. Valid edge traffic accepts canonical IPv4 and IPv6 and rejects
  malformed, comma-separated, and overlong client IP values.
- With small test limits and an injected clock, the Nth request succeeds and
  N+1 returns the exact 429 body and `Retry-After`; repeated denied requests
  remain denied.
- Bucket state persists when the downstream route performs no commit, rolls
  back, or raises an exception.
- Fixed-window boundary and minimum-one-second `Retry-After` behavior are
  deterministic.
- Distinct IPs and workspaces use distinct buckets; the three broker routes
  intentionally share one workspace `broker_sync` bucket.
- OPTIONS is not counted; failed and unknown non-OPTIONS API requests are.
- Direct middleware responses retain CORS and `Cache-Control: no-store`.
- Local edition registers neither enforcement layer nor cleanup and never
  touches `rate_limit_buckets`, regardless of request volume.
- Cleanup deletes expired rows only, respects its batch/invocation bounds, and
  records job success.

### PostgreSQL suite

- Several independent sessions concurrently consuming one bucket produce the
  exact final count with no lost increments. Each worker commits its isolated
  transaction; the test must not rely on SQLite's single-writer behavior or a
  fixture SAVEPOINT that hides real commit boundaries.
- A slow simulated downstream handler does not retain a lock on the bucket
  row after its limiter dependency returns.
- The real `portfyl_runtime` role has exactly the intended table privileges;
  the global table is documented and tested as a deliberate non-RLS exception.
- Migration `0012_rate_limit_buckets` upgrades and downgrades cleanly,
  including its index, check constraint, and grants.

### Deployment acceptance

- A direct request to the public Cloud Run URL without the Cloudflare-injected
  token cannot reach `/api/*`, even with forged `CF-Connecting-IP` and
  `X-Forwarded-For` headers.
- The normal Cloudflare hostname reaches the API and produces independent
  buckets for two canonical client IPs.
- The cleanup Scheduler job can be invoked with valid OIDC, a bare invocation
  is rejected, and `/health` reports stale cleanup after the two-hour limit.
- The production-shaped load test satisfies the numeric latency, pool, and
  lock gates in the observability section before enforcement is declared
  complete.
