# Portfyl Multi-user Foundation Design

**Status:** Approved in conversation on 2026-09-01

**Source brief:** `docs/superpowers/plans/2026-09-01-portfyl-multiuser-foundation-prompt.md`

**Master specification:** `docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md`

## Goal

Deliver Workstreams B and C from the master plan: move the cloud runtime from
SQLite to Neon PostgreSQL, replace startup schema mutation with Alembic,
migrate the existing owner's real SQLite data, introduce verified accounts and
revocable sessions, make `Workspace` the tenant, and prove tenant isolation at
both the application and PostgreSQL RLS layers.

This foundation must preserve all existing portfolio data and behavior while
allowing multiple stateless Cloud Run instances.

## Scope boundary

This design includes only:

- PostgreSQL, Alembic, SQLite-to-PostgreSQL data migration, Neon recovery, and
  multi-instance Cloud Run configuration;
- Firebase Authentication / Google Cloud Identity Platform for e-mail
  identity, plus Portfyl-owned revocable sessions;
- `User -> Membership -> Workspace` ownership;
- tenant-aware API, jobs that are touched by this migration, caches, imports,
  settings, alerts, and frontend account/workspace state;
- UUID public API identifiers and PostgreSQL row-level security;
- systematic Alice/Bob isolation tests.

The following remain separate future workstreams and must not be introduced by
this implementation:

- Stripe, plans, trials, billing, quotas, and entitlements;
- the `local`/`cloud` edition capability boundary, onboarding, packaging, and
  marketing;
- OAuth, MFA, invitations, and multi-member workspace management UI;
- KMS encryption and replacement of the existing scheduler/job architecture.

Existing plaintext secrets are isolated by tenant in this workstream but are
not redesigned; Workstream D remains responsible for encrypting them.

## Architectural decisions

### Managed identity, Portfyl-owned authorization

Firebase Authentication / Google Cloud Identity Platform owns credentials,
e-mail verification, and password-reset delivery. Portfyl never receives or
stores a password hash. OAuth and MFA providers remain disabled for this
workstream.

Portfyl remains the source of truth for application users, sessions,
memberships, workspaces, roles, and access to financial data. A Firebase UID is
an external identity key on a Portfyl `User`; it is not used as a tenant key or
as a public resource identifier.

### Opaque, database-backed sessions

After Firebase verifies an e-mail/password login, the browser sends a short-
lived Firebase ID token to `POST /api/auth/session`. The backend verifies the
token with the Firebase Admin SDK and requires `email_verified=true`. It then
creates or resolves the Portfyl user and issues a cryptographically random
opaque session token.

Only a SHA-256 digest of that token is stored in `auth_sessions`. The raw token
is sent in an `HttpOnly`, `Secure`, `SameSite=Lax` cookie. Each request resolves
the digest to a non-expired, non-revoked session. Logout revokes the current
row; logout-all revokes every Portfyl session for the user and calls Firebase's
refresh-token revocation API.

State-changing cookie-authenticated requests require a session-bound CSRF
token in `X-CSRF-Token`. The readable token returned by the session/bootstrap
API is held in memory by the frontend and never persisted to local storage.

### Workspace is the tenant

The trusted request context is:

```text
Verified Firebase identity (login only)
  -> Portfyl User
    -> AuthSession
      -> Membership
        -> Workspace
          -> every financial object
```

Every new account receives one personal workspace and one owner membership in
the same transaction that first provisions the Portfyl user. The schema allows
multiple memberships and workspaces, but invitation flows and role-management
UI are deferred.

The frontend sends the selected workspace's public UUID in
`X-Workspace-ID`. The backend treats it as untrusted and accepts it only after
finding an active membership for the authenticated user. When a user has
exactly one workspace the backend may infer it if the header is absent. With
multiple memberships, an absent header returns a structured 400 response.

### Public UUIDs, stable internal keys

Identity and tenancy tables use UUID primary keys. Existing high-volume domain
tables retain their integer primary keys for joins and migration simplicity,
but every API-visible entity receives a unique UUID `public_id` generated with
UUIDv4.

API fields keep their existing names such as `id` and `portfolio_id`, but their
values become UUID strings. Raw integer primary or foreign keys are never
serialized or accepted as route/query identifiers. This minimizes frontend
shape changes while eliminating sequential enumeration.

## Data model

### Identity and tenancy tables

- `users`: UUID `id`, unique `firebase_uid`, unique normalized `email`, display
  name, `email_verified_at`, timestamps, and disabled timestamp.
- `workspaces`: UUID `id`, UUID `public_id`, name, timestamps, and archived
  timestamp.
- `memberships`: UUID `id`, `user_id`, `workspace_id`, role, status, and
  timestamps; unique on `(user_id, workspace_id)`. This workstream provisions
  only the `owner` role.
- `auth_sessions`: UUID `id`, `user_id`, unique token digest, CSRF digest,
  creation/expiry/last-seen/revocation timestamps, and optional user-agent
  metadata. It contains no raw token.
- `user_settings`: `user_id`, key, value, timestamps; unique on
  `(user_id, key)`.
- `workspace_settings`: `workspace_id`, key, value, timestamps; unique on
  `(workspace_id, key)`.
- `data_migration_runs`: source fingerprint, target workspace, status, counts,
  timestamps, and validation report. It prevents accidental duplicate imports.

### Tenant-owned domain tables

Every tenant-owned table receives a non-null indexed `workspace_id`, including
portfolio children. Keeping the tenant key on child rows makes authorization
auditable and permits direct, efficient RLS policies without join-dependent
policy logic.

The affected set is:

- portfolios and transactions;
- watchlists and watchlist items;
- custom benchmarks and benchmark components;
- broker connections and broker balances;
- options trades and Polymarket positions;
- Discord webhooks, price alerts, and dividend-notification dedup rows;
- trade notes and cash-interest rates.

System benchmark presets remain readable across workspaces through an explicit
`is_preset` RLS exception and remain immutable through application
authorization. Tenant-created benchmarks always carry `workspace_id`.

Existing `owner_id` sentinel columns are removed after their data has been
backfilled to `workspace_id`. Tenant root uniqueness becomes:

- `portfolios(workspace_id, name)`;
- `watchlists(workspace_id, name)`;
- user or workspace setting key uniqueness on its owning table.

Child uniqueness constraints continue to include their parent identifier and,
where useful for validation/query plans, `workspace_id`.

### Personal and workspace settings

Current assistant model/key settings become personal `user_settings`; current
sync schedule and execution timestamps become `workspace_settings`. The
classification is centralized so new keys must declare one scope. Callers must
pass an authenticated user or workspace context; key-only lookup APIs are
removed.

## Database and migration architecture

### Runtime database

`DATABASE_URL` is the single runtime database setting and must contain a
PostgreSQL URL in deployed environments. Neon supplies the pooled connection
URL. SQLAlchemy uses PostgreSQL-safe pool health checks, bounded pool sizes,
and connection recycling suitable for Cloud Run scale-to-zero.

SQLite remains supported only as the legacy migration source and for narrow
cross-dialect unit tests. PostgreSQL integration and security tests run against
a real disposable PostgreSQL database.

### Alembic ownership

Alembic becomes the only schema owner. The initial PostgreSQL revision creates
the complete current schema plus identity, workspace, public UUID, tenant key,
indexes, constraints, and migration-audit tables. A following revision enables
and forces RLS and installs policies/grants so schema and security changes are
reviewable separately.

`Base.metadata.create_all()` and all `_ensure_*` / `_backfill_*` startup
mutations are removed from `main.py`. Application startup checks that the
database is reachable and at the expected Alembic head; it never mutates the
schema.

The deployment sequence runs `alembic upgrade head` as a one-off Cloud Run Job
using the same image before shifting web traffic.

### SQLite data migration

A separate CLI reads a copy of the owner's `portfyl.db` and writes to an empty,
already-migrated PostgreSQL database. It accepts explicit source path, target
URL, and legacy owner e-mail. It never runs automatically during web startup.

The import performs one transaction and:

1. fingerprints the SQLite file and rejects an already successful import;
2. creates a pending-claim user for the normalized owner e-mail, one workspace,
   and one owner membership;
3. copies every current table in dependency order while preserving integer
   relationships and generating deterministic-per-run public UUID mappings;
4. assigns the workspace to every copied tenant row;
5. classifies current app settings into user/workspace settings;
6. resets PostgreSQL identity sequences;
7. validates table counts, foreign-key integrity, uniqueness, and transaction
   control totals;
8. stores the validation report and commits only if every invariant passes.

The pending user is bound to a Firebase UID only when a successfully verified
Firebase login presents the exact normalized legacy owner e-mail. A mismatch
cannot claim the imported workspace.

The migration supports `--dry-run` and machine-readable validation output. A
rehearsal uses a copy of the real SQLite database and a disposable PostgreSQL
database before the production import.

## Request authorization and RLS

### Application dependency

One cached FastAPI dependency owns the request database session and resolves:

- the opaque session cookie;
- the non-revoked Portfyl user;
- the requested workspace and active membership;
- a typed `RequestContext(user_id, workspace_id, membership_role)`.

It sets transaction-local PostgreSQL variables through parameterized
`set_config()` calls before tenant queries execute. Portfolio resolution accepts
a public UUID and queries `(workspace_id, public_id)` together. Downstream
routers receive an authorized portfolio object/context rather than an unchecked
integer.

All direct model queries in routers, imports, alerts, assistant settings,
background functions touched by this workstream, and per-process caches are
audited. Cache keys that depend on customer data include `workspace_id` and the
resource public UUID.

### PostgreSQL RLS

RLS is enabled and forced on every tenant-owned table. Policies compare the
row's `workspace_id` with transaction-local `portfyl.workspace_id`. Membership
and personal-setting policies compare `user_id` with
`portfyl.user_id`. Missing or malformed context matches no private rows.

The migration owner role owns schema changes. The runtime app role is a
separate non-owner role without `BYPASSRLS`. Deployment documentation includes
the Neon role/grant setup and verifies the runtime URL does not use the owner
role.

Application filters remain mandatory even with RLS. RLS is defense in depth,
not a replacement for returning deterministic 404 responses and for keeping
queries efficient.

### Error contract

- Missing, expired, or revoked session: 401 `authentication_required`.
- Firebase e-mail not verified during session creation: 403
  `email_verification_required`.
- Missing workspace when more than one is available: 400
  `workspace_required`.
- Workspace without membership and every foreign object lookup: 404
  `resource_not_found`, preventing membership/resource enumeration.
- Duplicate tenant-scoped names: 409 with the existing user-facing behavior.
- Invalid or missing CSRF token on state change: 403 `csrf_failed`.

## Frontend design

The React application adds an `AuthProvider` above the existing portfolio
provider. It loads `/api/auth/me`, owns the user/workspace/CSRF state, and clears
the React Query cache whenever identity or workspace changes.

Firebase's browser SDK powers `/login`, `/register`, `/verify-email`, and
`/forgot-password`. A successful verified login exchanges the Firebase ID
token for the Portfyl HttpOnly session cookie and then discards Firebase client
persistence. The browser never stores a Portfyl session token.

Axios sends `X-CSRF-Token` on mutations and `X-Workspace-ID` after workspace
bootstrap. Portfolio selection continues to use the existing context, but
stores/reads UUID strings rather than coercing identifiers with `Number()`.

An account menu exposes current e-mail, logout, and logout-all. Workspace
switching state is implemented even though each launch account initially owns
only one workspace. Existing application pages remain unchanged except where
integer identifiers or implicit-account assumptions must be removed.

## Testing strategy

### Test layers

- Existing fast unit tests remain and are adapted to explicit user/workspace
  fixtures.
- PostgreSQL integration tests run Alembic against a disposable database and
  prove constraints, UUID defaults, migration head, and RLS behavior.
- FastAPI integration tests use the actual dependency/middleware chain rather
  than calling router functions directly.
- Firebase verification is replaced at the narrow external boundary with
  complete verified/unverified token fixtures; authorization, sessions, and
  tenant data use real application code and PostgreSQL.
- Frontend Vitest tests cover account bootstrap, auth routes, UUID portfolio
  state, workspace headers, CSRF headers, and cache clearing.

### Alice/Bob matrix

For portfolios, transactions/imports, watchlists/items, user/workspace
settings, and price alerts, tests create Alice and Bob with separate workspaces
and assert:

- list endpoints return only the caller's rows;
- known foreign UUIDs cannot be read;
- known foreign UUIDs cannot be updated or deleted;
- child identifiers cannot bypass a workspace-owned parent;
- duplicate names are permitted across tenants but rejected within one tenant;
- guessed/random UUIDs and real foreign UUIDs produce indistinguishable 404s;
- unscoped SQL through the runtime role cannot read or mutate another
  workspace because RLS blocks it;
- imports, alert evaluation, settings, and cache keys retain tenant identity.

No multi-user beta is considered safe until the complete matrix passes on
PostgreSQL.

## Deployment and recovery

Cloud Run continues to serve the built frontend and FastAPI backend from one
container, with request-based billing and `min-instances=0`. The SQLite GCS
mount and `DATABASE_PATH` are removed. The previous single-writer
`--max-instances=1` restriction is replaced by a configurable multi-instance
limit, documented initially as five instances to cap cost while proving scale.

Runtime configuration includes the Neon pooled `DATABASE_URL`, Firebase web
configuration at frontend build time, Firebase project ID, cookie settings,
and Google Application Default Credentials for the Admin SDK. Secrets are not
committed.

The Neon runbook records the configured PITR retention available to the actual
project, creates a recovery branch at a selected pre-incident timestamp,
validates Alembic revision and business control totals against that branch, and
switches traffic only after validation. The quarterly drill restores to a new
branch/database; it never overwrites production in place.

Repository automation provides the commands and validation script. The first
production-like restore drill requires access to the real Neon project and its
safe recovery branch, and its timestamp/result are recorded in the runbook.

## Rollout sequence

1. Add PostgreSQL dependencies, Alembic environment, and disposable PostgreSQL
   test harness.
2. Define the final schema and RLS migrations.
3. Build and rehearse the SQLite data importer.
4. Add Firebase token exchange and Portfyl-owned revocable sessions.
5. Introduce request user/workspace context and migrate every backend query,
   cache, import, setting, and alert path.
6. Replace public integer identifiers with UUIDs throughout API and frontend.
7. Implement frontend registration/session/account/workspace state.
8. Run the full Alice/Bob and RLS matrix plus legacy migration rehearsal.
9. Update Cloud Run, Neon PITR/restore, migration, and operator documentation.

Every implementation task follows test-first red/green/refactor cycles. No
traffic migration occurs until schema migration, data reconciliation, auth,
tenant isolation, RLS, and restore checks have passed.
