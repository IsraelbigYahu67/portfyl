# Portfyl Secrets, Jobs & Operational Security Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Workstream D of the SaaS master plan — envelope-encrypted
broker/AI/webhook secrets, an external scheduler that replaces the in-process
background pollers for the cloud edition, idempotent/retry-bounded jobs, a
connection-level dead-letter state, redacted structured logging, an audit
trail for security-sensitive mutations, and a health check that distinguishes
subsystem availability. This unblocks Workstream E (Stripe billing, trial,
entitlements) and onboarding, which the master plan forbids starting before D
lands.

**Architecture:** A backend-owned `SecretCipher` abstraction picks a Google
Cloud KMS-backed implementation in the cloud edition and a local
Fernet-keyed implementation in the local edition/tests, mirroring the
existing `DatabaseSettings.from_env`/edition-registry pattern of fail-closed
config selection. Broker credentials, the Discord webhook URL, and the
DeepSeek AI key move from plaintext columns/settings to
`(ciphertext, key_version)` pairs. The three in-process `asyncio` pollers in
`backend/main.py` remain for the local edition (always single-instance) but
are replaced in the cloud edition by authenticated internal HTTP endpoints
that Cloud Scheduler invokes on a cron schedule using an OIDC identity token;
a Postgres advisory lock inside each endpoint makes concurrent/duplicate
invocations across Cloud Run instances a safe no-op instead of a double-run.
Per-connection consecutive-failure tracking gives broker autosync a
dead-letter state without a new subsystem. A new `AuditLog` table records
security-sensitive mutations; `/health` reports per-subsystem status.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16,
`google-cloud-kms`, `cryptography` (Fernet), Google Cloud Scheduler + IAM
OIDC tokens, Cloud Run, pytest, Testcontainers/Docker Compose.

**Spec:** `docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md`
(§8 "Background work" / "Secrets and observability", §9 "Workstream D").

## Global Constraints

- Implement only Workstream D: encrypted secrets, external cloud scheduling,
  job idempotency/retries/dead-letter, log redaction, audit log, and health
  checks. Do not add Stripe, billing, trials, plan entitlements, or
  onboarding UI — those are Workstream E and explicitly blocked until this
  plan's definition of done is met.
- `PORTFYL_EDITION` continues to gate behavior exactly as `backend/edition.py`
  already does; do not introduce a third value or bypass the fail-closed
  parse.
- The local edition keeps its existing in-process `asyncio` pollers in
  `backend/main.py` — it is always single-instance, so an external scheduler
  buys it nothing and would add operational surface the owner doesn't need.
  Only the cloud edition switches to Cloud Scheduler-driven internal
  endpoints.
- Every secret at rest (broker `api_key`/`api_secret`, Discord
  `webhook_url`, the DeepSeek AI key) is stored only as
  `(ciphertext, key_version)`; no code path re-introduces a plaintext
  column or setting value for these.
- Decrypted secret values must never be logged, included in exception
  messages, returned in full by any API response, or embedded in audit-log
  metadata. Existing masked-preview behavior (e.g. `_key_preview` in
  `assistant.py`) is the pattern to extend, not replace.
- Background job passes keep the existing per-workspace RLS-context
  discipline in `backend/jobs.py` (`_set_job_workspace_context`,
  `_active_workspace_ids`) unchanged; this plan adds an outer idempotency/
  auth layer, not a new tenancy model.
- Internal scheduler endpoints are not mounted under `/api` and must reject
  any request that isn't a verified Cloud Scheduler OIDC token for the
  dedicated `portfyl-scheduler` service account — no shared static secret,
  no unauthenticated fallback.
- A duplicate/concurrent invocation of the same job must be a safe no-op
  (advisory lock skip), never a duplicate sync, duplicate notification, or
  crash.
- Migrating existing plaintext secret columns to ciphertext must not lose
  data or require customers to reconnect brokers; use an expand → backfill →
  contract migration sequence, rehearsed like the existing SQLite→Postgres
  importer.
- Existing repository changes must be preserved; do not touch Tax
  Report/Screener, billing, or onboarding surfaces.
- PostgreSQL integration tests require Docker Desktop or an explicit
  disposable `TEST_DATABASE_URL`; never replace them with SQLite-only
  assertions, especially for the advisory-lock and RLS-context behavior.

## File responsibility map

- `backend/secrets_crypto.py` (new): `SecretCipher` protocol, KMS and local
  Fernet implementations, edition-aware factory.
- `backend/models.py`: `BrokerConnection`/`DiscordWebhook` ciphertext
  columns, failure-tracking columns, new `AuditLog`/`JobRun` models.
- `backend/alembic/versions/`: expand/contract migrations for the secret
  columns and the new tables.
- `backend/migrations/encrypt_existing_secrets.py` (new): one-off backfill
  CLI, mirroring `sqlite_to_postgres.py`'s rehearsable-importer shape.
- `backend/app_settings.py`: `get_user_secret`/`set_user_secret` wrappers
  around the existing `UserSetting` KV store.
- `backend/routers/broker.py`, `backend/routers/ibkr.py`,
  `backend/routers/discord.py`, `backend/routers/assistant.py`: encrypt on
  write, decrypt on use, masked previews on read.
- `backend/jobs.py`: per-connection consecutive-failure tracking and
  auto-disable.
- `backend/main.py`: edition-conditional poller startup; mounts the new
  internal jobs router only in the cloud edition; expanded `/health`.
- `backend/routers/internal_jobs.py` (new): OIDC-verified job-trigger
  endpoints with advisory-lock idempotency.
- `backend/audit.py` (new): `record_audit_event` helper and call sites.
- `backend/logging_setup.py` (new): correlation-ID + secret-redaction log
  configuration, imported from `main.py`.
- `deploy/cloudrun.md`: `portfyl-scheduler` service account, Cloud Scheduler
  job creation commands, KMS key/keyring provisioning.
- `backend/tests/`, `backend/tests/postgres/`: unit and integration coverage
  for all of the above.

---

### Task 1: Envelope-encryption primitives

**Files:**
- Create: `backend/secrets_crypto.py`
- Modify: `backend/requirements.txt` (`google-cloud-kms>=2.24`,
  `cryptography>=43`)
- Modify: `backend/tests/conftest.py` (set a fixed `PORTFYL_LOCAL_SECRET_KEY`
  for the fast suite, matching the existing `DATABASE_URL`/`PORTFYL_TESTING`
  `setdefault` pattern)
- Create: `backend/tests/test_secrets_crypto.py`

**Interfaces:**
```python
@dataclass(frozen=True)
class EncryptedValue:
    ciphertext: bytes
    key_version: str

class SecretCipher(Protocol):
    def encrypt(self, plaintext: str) -> EncryptedValue: ...
    def decrypt(self, value: EncryptedValue) -> str: ...

def build_secret_cipher(env: Mapping[str, str], edition: Edition) -> SecretCipher: ...
```

- [ ] **Step 1: Write failing cipher tests**

Cover: round-trip encrypt/decrypt for `LocalFernetCipher`; two encryptions of
the same plaintext produce different ciphertext (nonce/IV freshness);
`build_secret_cipher` raises `RuntimeError` in the cloud edition when
`PORTFYL_KMS_KEY_NAME` is unset (fail-closed, same shape as
`DatabaseSettings.from_env`); `build_secret_cipher` picks the local cipher in
the local edition even if a KMS var happens to be set; `KmsEnvelopeCipher`
round-trips against a stubbed `google.cloud.kms` client (inject the client,
don't hit real GCP in unit tests).

- [ ] **Step 2: Run the focused tests and verify the missing interface fails**

Run: `cd backend && python -m pytest tests/test_secrets_crypto.py -v`

Expected: collection fails because `secrets_crypto` does not exist.

- [ ] **Step 3: Implement `LocalFernetCipher`, `KmsEnvelopeCipher`, and the factory**

`LocalFernetCipher` derives its key from `PORTFYL_LOCAL_SECRET_KEY` (a
base64 Fernet key; fail closed with a clear message telling the operator how
to generate one if missing) and reports `key_version="local:v1"`.
`KmsEnvelopeCipher` wraps `google.cloud.kms.KeyManagementServiceClient`,
calling `encrypt`/`decrypt` against `PORTFYL_KMS_KEY_NAME`
(`projects/*/locations/*/keyRings/*/cryptoKeys/*`) and using the response's
resolved crypto key version resource name as `key_version` — this is
Cloud KMS's own envelope-encryption implementation (local DEK generation is
unnecessary at these payload sizes; note this as a deliberate simplification,
not a scope cut, per the plan's Architecture section). `build_secret_cipher`
branches on `edition_from_env`/passed `Edition` exactly like
`DatabaseSettings.from_env` branches on `PORTFYL_TESTING`.

- [ ] **Step 4: Run the cipher tests**

Run: `cd backend && python -m pytest tests/test_secrets_crypto.py -v`

Expected: all pass, including the fail-closed and freshness assertions.

- [ ] **Step 5: Commit Task 1**

```bash
git add backend/secrets_crypto.py backend/requirements.txt backend/tests/conftest.py backend/tests/test_secrets_crypto.py
git commit -m "feat(secrets): add KMS/local envelope-encryption cipher"
```

---

### Task 2: Encrypt broker connection credentials

**Files:**
- Modify: `backend/models.py` (`BrokerConnection`)
- Create: `backend/alembic/versions/0004_broker_secret_columns_expand.py`
- Create: `backend/migrations/encrypt_existing_secrets.py`
- Create: `backend/alembic/versions/0005_broker_secret_columns_contract.py`
- Modify: `backend/routers/broker.py`, `backend/routers/ibkr.py`,
  `backend/jobs.py`
- Create: `backend/tests/test_broker_secrets.py`
- Create: `backend/tests/postgres/test_secret_migration.py`

**Interfaces:**
- `BrokerConnection.api_key_ciphertext: bytes`,
  `.api_key_key_version: str`, `.api_secret_ciphertext: bytes | None`,
  `.api_secret_key_version: str | None` replace `api_key`/`api_secret`.
- `broker.py`/`ibkr.py` gain `_decrypt_connection_credentials(conn) -> (api_key, api_secret)`
  and encrypt on every create/update path.
- API responses for a broker connection return `api_key_preview` (e.g.
  `sk_***last4`) instead of the raw value, never the ciphertext or plaintext.

- [ ] **Step 1: Write failing model/router tests for encrypted storage**

Assert: creating a `BrokerConnection` persists no plaintext anywhere on the
row (inspect the raw columns, not just the ORM property); the API response
for a created/listed connection contains a masked preview, never the full
key; `sync_transactions`/`_run_ibkr_sync` still work end-to-end when given a
connection whose credentials only exist as ciphertext (decrypt happens
inside the sync path); `broker_autosync_pass` in `jobs.py` decrypts
correctly for a workspace's connections.

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `cd backend && python -m pytest tests/test_broker_secrets.py -v`

- [ ] **Step 3: Add the expand migration and update the model**

`0004_broker_secret_columns_expand.py` adds the four nullable ciphertext/
key-version columns alongside the existing `api_key`/`api_secret` (additive,
non-breaking). Update `BrokerConnection` to expose both the legacy plaintext
columns (still present, not yet dropped) and the new ones during this task;
routers write to the new columns only.

- [ ] **Step 4: Implement encrypt-on-write and decrypt-on-use in the routers and jobs**

Update every `BrokerConnection` create/update path in `broker.py`/`ibkr.py`
to call `build_secret_cipher(...).encrypt(...)` before persisting, and every
sync path (including `jobs.broker_autosync_pass`) to decrypt just before use
and never retain the plaintext beyond the immediate broker call. Add the
masked-preview serializer field.

- [ ] **Step 5: Write the backfill script and its rehearsal test**

`backend/migrations/encrypt_existing_secrets.py` is a standalone CLI
(argparse, `--dry-run` default, `--apply` to write) that reads every
`BrokerConnection`/`DiscordWebhook` row still carrying a plaintext value,
encrypts it with the configured cipher, and writes the ciphertext columns —
mirroring `sqlite_to_postgres.py`'s dry-run/apply/reconciliation-report
shape. `tests/postgres/test_secret_migration.py` seeds plaintext rows against
a disposable PostgreSQL database, runs the script, and asserts every row now
has ciphertext that decrypts back to the original value and that dry-run
made no writes.

- [ ] **Step 6: Add the contract migration**

`0005_broker_secret_columns_contract.py` makes the ciphertext/key-version
columns non-nullable and drops `api_key`/`api_secret`. This migration is the
one operators run only after confirming the backfill script's
reconciliation report shows zero remaining plaintext rows — document that
sequencing at the top of the migration file and in
`docs/operations/sqlite-to-neon-migration.md`.

- [ ] **Step 7: Run focused, broker, ibkr, and jobs suites**

Run: `cd backend && python -m pytest tests/test_broker_secrets.py tests/test_broker.py tests/test_ibkr.py tests/test_jobs.py -v`

Run: `docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait && cd backend && python -m pytest tests/postgres/test_secret_migration.py -v`

- [ ] **Step 8: Commit Task 2**

```bash
git add backend/models.py backend/alembic/versions/0004_broker_secret_columns_expand.py backend/alembic/versions/0005_broker_secret_columns_contract.py backend/migrations/encrypt_existing_secrets.py backend/routers/broker.py backend/routers/ibkr.py backend/jobs.py backend/tests/test_broker_secrets.py backend/tests/postgres/test_secret_migration.py
git commit -m "feat(secrets): encrypt broker credentials at rest"
```

---

### Task 3: Encrypt the AI key and the Discord webhook URL

**Files:**
- Modify: `backend/app_settings.py`
- Modify: `backend/routers/assistant.py`
- Modify: `backend/models.py` (`DiscordWebhook`)
- Create/modify migrations analogous to Task 2 for `discord_webhooks`
  (`0006_discord_webhook_secret_columns_expand.py`,
  `0007_discord_webhook_secret_columns_contract.py`)
- Modify: `backend/routers/discord.py`, `backend/jobs.py`
  (`send_discord_notification` call sites)
- Modify: `backend/tests/test_assistant.py`, create
  `backend/tests/test_discord_secrets.py`

**Interfaces:**
- `app_settings.get_user_secret(db, user_id, key) -> str | None` and
  `set_user_secret(db, user_id, key, plaintext) -> None`, storing the
  cipher's `EncryptedValue` JSON-encoded inside the existing `UserSetting.value`
  string column (no schema change needed there).
- `DiscordWebhook.webhook_url_ciphertext`/`.webhook_url_key_version` replace
  `webhook_url`, following the same expand/backfill/contract sequence as
  Task 2 (reuse `encrypt_existing_secrets.py`, extended to cover this table).

- [ ] **Step 1: Write failing tests**

Assert: `set_user_secret`/`get_user_secret` round-trip and the raw
`UserSetting.value` never contains the plaintext DeepSeek key; the existing
`_key_preview` masking in `assistant.py` still works against the decrypted
value; creating a `DiscordWebhook` persists no plaintext URL on the row;
`send_discord_notification` still posts successfully when given a webhook
whose URL only exists as ciphertext.

- [ ] **Step 2: Run and verify failure**

Run: `cd backend && python -m pytest tests/test_assistant.py tests/test_discord_secrets.py -v`

- [ ] **Step 3: Implement `get_user_secret`/`set_user_secret` and wire `assistant.py`**

Replace the two plaintext `get_user_setting`/`set_user_setting(KEY_SETTING, ...)`
call sites in `assistant.py` with the secret variants.

- [ ] **Step 4: Add `DiscordWebhook` ciphertext columns, update `discord.py`/`jobs.py`, extend the backfill script and contract migration**

Same expand → backfill → contract sequence as Task 2, extending
`encrypt_existing_secrets.py` to also cover `discord_webhooks`.

- [ ] **Step 5: Run assistant, discord, and jobs suites plus the extended backfill rehearsal**

Run: `cd backend && python -m pytest tests/test_assistant.py tests/test_discord_secrets.py tests/test_discord.py tests/test_jobs.py -v`

Run the PostgreSQL backfill rehearsal from Task 2, now covering both tables.

- [ ] **Step 6: Commit Task 3**

```bash
git add backend/app_settings.py backend/routers/assistant.py backend/routers/discord.py backend/models.py backend/alembic/versions/0006_discord_webhook_secret_columns_expand.py backend/alembic/versions/0007_discord_webhook_secret_columns_contract.py backend/migrations/encrypt_existing_secrets.py backend/jobs.py backend/tests/test_assistant.py backend/tests/test_discord_secrets.py
git commit -m "feat(secrets): encrypt the AI key and Discord webhook URL"
```

---

### Task 4: Redacted structured logging

**Files:**
- Create: `backend/logging_setup.py`
- Modify: `backend/main.py` (call `configure_logging()` at import time,
  before the existing `yfinance` logger tweak)
- Create: `backend/tests/test_logging_setup.py`

**Interfaces:**
- `configure_logging() -> None`: installs a `logging.Filter` that redacts
  known secret-shaped substrings (broker API keys/secrets, Discord webhook
  URLs, the DeepSeek key, session cookie/CSRF token values) from every log
  record's message and args, and injects a request/job correlation ID
  (`contextvars`-based, set by request middleware and by `_periodic_loop`/the
  new internal-jobs router) into a `correlation_id` `LogRecord` attribute
  used by the formatter.

- [ ] **Step 1: Write failing redaction tests**

Feed representative log lines (containing a fake broker secret, a fake
Discord webhook URL, a fake session cookie value) through the configured
filter/formatter and assert the secret substrings never appear in the
rendered output, while non-secret context (workspace id, job name, error
type) still does. Assert a request handled through a `TestClient` call and a
job pass invoked with a given correlation id both surface that id in the
emitted record.

- [ ] **Step 2: Run and verify failure**

Run: `cd backend && python -m pytest tests/test_logging_setup.py -v`

- [ ] **Step 3: Implement `configure_logging`, wire it into `main.py`, and thread correlation IDs through `_periodic_loop` and the jobs module**

- [ ] **Step 4: Run the logging suite plus the full fast backend suite (regression check for any test asserting on log text)**

Run: `cd backend && python -m pytest tests/test_logging_setup.py tests/ -v --ignore=tests/postgres`

- [ ] **Step 5: Commit Task 4**

```bash
git add backend/logging_setup.py backend/main.py backend/jobs.py backend/tests/test_logging_setup.py
git commit -m "feat(observability): redact secrets and add correlation IDs to logs"
```

---

### Task 5: External scheduler for the cloud edition

**Files:**
- Create: `backend/routers/internal_jobs.py`
- Modify: `backend/main.py` (edition-conditional poller startup; mount the
  new router only when `PORTFYL_EDITION is Edition.CLOUD`)
- Create: `backend/tests/test_internal_jobs.py`
- Create: `backend/tests/postgres/test_job_advisory_lock.py`
- Modify: `deploy/cloudrun.md` (service account, Cloud Scheduler job
  creation)

**Interfaces:**
- `POST /internal/jobs/{name}` for `name in {"alerts", "autosync",
  "dividends"}`, each running the corresponding `jobs.*_all_workspaces`
  pass exactly once per accepted call.
- `verify_scheduler_token(authorization: str) -> None` (raises 401/403):
  verifies a Google-signed OIDC ID token via
  `google.oauth2.id_token.verify_oauth2_token`, checking `aud` equals the
  deployed service URL and the token's service-account email equals
  `PORTFYL_SCHEDULER_SERVICE_ACCOUNT`.
- `with_job_lock(db: Session, job_name: str) -> AbstractContextManager[bool]`:
  wraps `pg_try_advisory_lock(hashtext(:job_name))`/`pg_advisory_unlock`;
  yields whether the lock was acquired.

- [ ] **Step 1: Write failing endpoint and advisory-lock tests**

Endpoint tests (fast suite, `TestClient`, edition forced to cloud): a request
with no/garbage `Authorization` header gets 401; a request with a token whose
`aud` or service-account email doesn't match gets 403 (stub
`verify_oauth2_token` — never call Google in unit tests); a verified request
triggers exactly one pass and returns a summary; the router is entirely
absent (404, not just unauthorized) when the app is built with
`PORTFYL_EDITION=local`, and the in-process pollers are absent when built
with `cloud`. Advisory-lock tests (`tests/postgres/`, real PostgreSQL): two
concurrent sessions calling `with_job_lock` for the same `job_name`
serialize — the second either blocks-and-then-runs-after or is told the lock
is held (pick and assert the non-blocking "skip" semantics the endpoint
actually uses); two different `job_name`s never contend.

- [ ] **Step 2: Run and verify failure**

Run: `cd backend && python -m pytest tests/test_internal_jobs.py -v`

- [ ] **Step 3: Implement the router, token verification, and advisory-lock helper; flip poller startup in `main.py` on edition**

`main.py`'s `_start_background_pollers` startup hook only registers the
`asyncio` tasks when `PORTFYL_EDITION is Edition.LOCAL`; the cloud edition
instead includes `internal_jobs.router` (no `/api` prefix, no
`get_request_context` dependency — it has its own auth). A skipped-lock
response returns `200 {"skipped": "already running"}` so Cloud Scheduler
does not treat a concurrent invocation as a failure worth retrying.

- [ ] **Step 4: Run endpoint tests, then the advisory-lock integration test against disposable PostgreSQL**

Run: `cd backend && python -m pytest tests/test_internal_jobs.py -v`

Run: `docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait && cd backend && python -m pytest tests/postgres/test_job_advisory_lock.py -v`

- [ ] **Step 5: Document and script the Cloud Scheduler + IAM setup**

Add to `deploy/cloudrun.md`, following the existing
`portfyl-runtime`/`portfyl-migrator` two-service-account pattern: create
`portfyl-scheduler` with `roles/run.invoker` on the service (nothing else —
it never touches Secret Manager or the database directly), and three
`gcloud scheduler jobs create http` commands (cron expressions matching
today's poller intervals: alerts every 15 min, autosync every 1 min heartbeat
— or note that Cloud Scheduler's minimum resolution makes a 1-minute
heartbeat wasteful and the autosync job should instead run on the coarsest
schedule that still satisfies every configured per-workspace schedule, e.g.
hourly, since `jobs.sync_due` already gates the actual work — document
whichever choice is made and why), each with
`--oidc-service-account-email=portfyl-scheduler@...` and
`--oidc-token-audience` set to the Cloud Run service URL, and bounded retry
config (`--max-retry-attempts`, `--min-backoff`, `--max-backoff`).

- [ ] **Step 6: Commit Task 5**

```bash
git add backend/routers/internal_jobs.py backend/main.py backend/tests/test_internal_jobs.py backend/tests/postgres/test_job_advisory_lock.py deploy/cloudrun.md
git commit -m "feat(jobs): replace cloud in-process pollers with Cloud Scheduler-driven internal endpoints"
```

---

### Task 6: Per-connection dead-letter state

**Files:**
- Modify: `backend/models.py` (`BrokerConnection`:
  `consecutive_failures`, `needs_attention`, `last_error`)
- Create: `backend/alembic/versions/0008_broker_connection_failure_tracking.py`
- Modify: `backend/jobs.py` (`broker_autosync_pass`)
- Modify: `backend/routers/broker.py` (surface the flag; allow the user to
  clear it by fixing/re-testing the connection)
- Modify frontend: wherever broker connections are listed
  (`frontend/src/pages/Settings.jsx` or equivalent broker-connections panel)
  to show a "needs attention" indicator
- Create: `backend/tests/test_broker_dead_letter.py`

**Interfaces:**
- `BrokerConnection.consecutive_failures: int` (default 0),
  `.needs_attention: bool` (default `False`), `.last_error: str | None`.
- `broker_autosync_pass` increments/resets `consecutive_failures` per
  connection each pass, sets `needs_attention = True` and turns off
  `auto_sync` once a threshold (`BROKER_AUTOSYNC_FAILURE_THRESHOLD`, default
  5) is reached, and resets both on the next successful sync.

- [ ] **Step 1: Write failing tests**

A connection that fails every pass for `threshold` consecutive passes ends
up with `needs_attention=True` and `auto_sync=False`, and does not get
retried by subsequent passes (it's excluded from the `auto_sync == True`
query already). A connection that fails once then succeeds keeps
`auto_sync=True` and resets `consecutive_failures` to 0. Re-enabling
`auto_sync` through the existing update endpoint clears `needs_attention`
and `consecutive_failures`.

- [ ] **Step 2: Run and verify failure**

Run: `cd backend && python -m pytest tests/test_broker_dead_letter.py -v`

- [ ] **Step 3: Add the migration, update `broker_autosync_pass`, and surface the flag in `broker.py`'s serializer and update endpoint**

- [ ] **Step 4: Add the frontend indicator and a focused Vitest case**

- [ ] **Step 5: Run backend and frontend suites**

Run: `cd backend && python -m pytest tests/test_broker_dead_letter.py tests/test_jobs.py -v`

Run: `cd frontend && npm test`

- [ ] **Step 6: Commit Task 6**

```bash
git add backend/models.py backend/alembic/versions/0008_broker_connection_failure_tracking.py backend/jobs.py backend/routers/broker.py backend/tests/test_broker_dead_letter.py frontend/src
git commit -m "feat(jobs): auto-disable and flag repeatedly failing broker connections"
```

---

### Task 7: Audit log and expanded health check

**Files:**
- Create: `backend/audit.py`
- Modify: `backend/models.py` (`AuditLog`)
- Create: `backend/alembic/versions/0009_audit_log.py`
- Modify: `backend/routers/auth.py` (session create/revoke/logout-all),
  `backend/routers/broker.py` (connection create/delete/credential
  rotation), `backend/routers/assistant.py` (AI key set/clear),
  `backend/routers/discord.py` (webhook create/delete)
- Modify: `backend/routers/settings.py` (add a paginated
  `GET /api/settings/audit-log`)
- Modify: `backend/main.py` (`/health`)
- Create: `backend/tests/test_audit.py`, `backend/tests/test_health.py`

**Interfaces:**
- `AuditLog(id, public_id, workspace_id nullable, actor_user_id, action: str,
  target_type: str | None, target_id: str | None, metadata: JSON,
  created_at)`. RLS-scoped like every other tenant table for workspace-scoped
  events; user-level events (e.g. login from a new device) carry
  `workspace_id=None` and are scoped by `actor_user_id` instead — the same
  dual-scope precedent `UserSetting`/`WorkspaceSetting` already establishes.
- `record_audit_event(db, *, actor_user_id, action, workspace_id=None,
  target_type=None, target_id=None, metadata=None) -> None`. `metadata` must
  never contain a secret value — reuse Task 4's redaction helper as a guard
  in `record_audit_event` itself (belt-and-suspenders with the logging
  filter), not just trust callers.
- `/health` returns `{"status": "ok"|"degraded", "checks": {"database":
  ..., "scheduler": ..., ...}}` — `database` runs `SELECT 1`; `scheduler`
  reports whether the last successful pass per job (from the timestamps
  already tracked by `mark_sync_ran`/dividend dedup rows, or a lightweight
  new `JobRun` last-success table if those don't cover alerts) was recent
  enough; existing broker/market-data reachability checks are best-effort
  and never make `/health` itself slow or flaky (bounded timeout, cached
  result).

- [ ] **Step 1: Write failing tests**

`record_audit_event` persists a row with the given fields and rejects (or
strips, per the chosen design — decide and document in the docstring) any
metadata value matching the redaction patterns from Task 4. Each modified
router call site produces exactly one audit row with the expected `action`
string on the relevant mutation (session login, session revoke, logout-all,
broker connection create/delete, AI key set/clear, webhook create/delete).
`GET /api/settings/audit-log` returns only the calling workspace's/user's
own events (Alice cannot see Bob's), paginated. `/health` returns `status:
"ok"` with all checks green in the normal case, and `"degraded"` with the
specific failing check named when the database ping fails (simulate via a
broken session).

- [ ] **Step 2: Run and verify failure**

Run: `cd backend && python -m pytest tests/test_audit.py tests/test_health.py -v`

- [ ] **Step 3: Implement `AuditLog`, `record_audit_event`, the migration, and every call site**

- [ ] **Step 4: Implement the expanded `/health` and the audit-log read endpoint**

- [ ] **Step 5: Run focused, auth, broker, assistant, discord, and settings suites, plus the PostgreSQL Alice/Bob matrix (new audit-log isolation cases folded into the existing matrix module)**

Run: `cd backend && python -m pytest tests/test_audit.py tests/test_health.py tests/test_auth.py tests/test_broker.py tests/test_assistant.py tests/test_discord.py tests/test_settings.py -v`

Run: `docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait && cd backend && python -m pytest tests/postgres/ -v`

- [ ] **Step 6: Commit Task 7**

```bash
git add backend/audit.py backend/models.py backend/alembic/versions/0009_audit_log.py backend/routers/auth.py backend/routers/broker.py backend/routers/assistant.py backend/routers/discord.py backend/routers/settings.py backend/main.py backend/tests/test_audit.py backend/tests/test_health.py backend/tests/postgres
git commit -m "feat(security): add audit log and subsystem-aware health check"
```

---

### Task 8: Full verification and plan record

**Files:**
- Modify: `docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md`
  (check off Workstream D in §9's checklist once verified)
- Modify: `CLAUDE.md` (update the "still pending" sentence once D lands)
- Modify: `docs/operations/sqlite-to-neon-migration.md` (note the secret
  backfill/contract-migration sequencing added in Tasks 2-3)

- [ ] **Step 1: Run the complete fast backend suite**

Run: `cd backend && python -m pytest tests/ -v --ignore=tests/postgres`

Expected: 0 failed, 0 skipped (record the pass count, matching the "648
passed" precedent recorded for the multiuser-foundation plan).

- [ ] **Step 2: Run the complete PostgreSQL integration suite**

Run: `docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait && cd backend && python -m pytest tests/postgres/ -v`

- [ ] **Step 3: Run the frontend suite and both edition builds**

Run: `cd frontend && npm test && npm run build && npm run build:cloud`

- [ ] **Step 4: Rehearse the secret backfill end to end on a disposable database**

Seed plaintext-era rows (via the pre-contract-migration schema, or a
generated fixture), run `encrypt_existing_secrets.py --dry-run` then
`--apply`, apply the contract migrations, and confirm the app still
decrypts every value correctly and no plaintext survives anywhere in the
database.

- [ ] **Step 5: Manually verify the Cloud Scheduler path against a real (non-production) Cloud Run deployment**

Deploy to a scratch Cloud Run service with `PORTFYL_EDITION=cloud`, create
the three Cloud Scheduler jobs from Task 5 pointed at it, trigger each
manually (`gcloud scheduler jobs run`), and confirm: a verified call
succeeds and runs the pass; an unauthenticated `curl` to the same endpoint
gets 401; two rapid manual triggers of the same job show the second as
skipped in the logs, not a duplicate run.

- [ ] **Step 6: Update plan records and commit**

```bash
git add docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md CLAUDE.md docs/operations/sqlite-to-neon-migration.md
git commit -m "docs(secrets): record Workstream D completion"
```

## Definition of done

- [ ] No broker, AI, or webhook secret exists in plaintext anywhere in the
  database, application logs, error monitoring, or API responses.
- [ ] The cloud edition runs with zero in-process background pollers; every
  scheduled pass is triggered externally and rejects unauthenticated
  callers.
- [ ] Concurrent/duplicate job invocations are provably safe no-ops
  (advisory-lock test passes).
- [ ] A broker connection that fails repeatedly stops retrying silently and
  is visibly flagged to the user.
- [ ] Security-sensitive mutations (session lifecycle, credential
  create/delete/rotate, AI key set/clear, webhook create/delete) produce an
  audit-log row visible only to the owning user/workspace.
- [ ] `/health` distinguishes database, scheduler freshness, and other
  subsystem availability.
- [ ] Complete fast backend suite, PostgreSQL integration suite, frontend
  suite, and both edition builds pass.
- [ ] The master plan's Workstream D checklist item is checked off with this
  plan's file referenced.
