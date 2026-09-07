# Portfyl Data Export and Account Deletion Design

## Status

Approved by the implementation request on 2026-09-07.

## Goal

Give every authenticated Portfyl user a machine-readable export of the active
workspace and a verified, reversible workspace-deletion workflow. Both
features are available in the local and cloud editions and never depend on a
paid plan, trial state, or quota.

## Product behaviour

- Settings offers a JSON download for the active workspace. The download is
  available while a deletion request is in its grace period.
- The export contains a versioned manifest, workspace and membership metadata,
  portfolios, transactions, watchlists and their items, price alerts, and
  broker-connection metadata.
- Broker credentials, encrypted credential bytes, encryption key versions,
  session tokens, CSRF material, and raw internal integer keys never appear in
  the export. Relationships use public UUIDs.
- Deletion is workspace-scoped. It is available only to the sole active owner;
  deleting a shared workspace is refused rather than destroying another
  member's data.
- Scheduling deletion requires the exact workspace name, the current Portfyl
  session and CSRF token, and a fresh Firebase e-mail/password sign-in. The
  backend verifies the returned Firebase ID token, its UID/e-mail, verified
  e-mail state, and a recent `auth_time` claim.
- A request starts a 30-day grace period. During the grace period the workspace
  remains usable, export remains available, and the request can be cancelled.
- The due-deletion cleanup is idempotent and rechecks sole ownership before it
  deletes anything. Deleting the workspace cascades through all tenant-owned
  rows. Membership disappears with the workspace. If the requesting user has
  no other membership, their Firebase identity and Portfyl user/session rows
  are also removed; otherwise their other workspaces and account remain.
- Trial expiration and plan changes do not create, advance, or execute a
  deletion request. Only an explicit verified request can do so.

## API

The new `backend/routers/account.py` router is nested under the already-mounted
settings router, producing these portfolio-agnostic paths:

- `GET /api/settings/account/export` returns an attachment with media type
  `application/json` and schema version `1`.
- `GET /api/settings/account/deletion` returns the active request and deadline,
  or `scheduled: false`.
- `POST /api/settings/account/deletion` verifies re-authentication and schedules
  deletion. Repeating it returns the existing deadline instead of shortening
  the grace period.
- `DELETE /api/settings/account/deletion` cancels a pending request.

GET routes use `get_request_context`; mutations use `require_csrf`. Every query
also contains an explicit workspace predicate even though forced PostgreSQL
RLS applies the same scope.

## Export schema

The top-level object is:

```json
{
  "schema_version": 1,
  "exported_at": "2026-09-07T12:00:00+00:00",
  "workspace": {},
  "membership": {},
  "portfolios": [],
  "transactions": [],
  "watchlists": [],
  "alerts": [],
  "broker_connections": []
}
```

Rows are ordered deterministically. Nested records contain only scalar JSON
values; dates and datetimes use ISO 8601 strings. Portfolio and watchlist
relationships are public UUIDs so the bundle is portable without exposing
database primary keys.

Broker metadata is deliberately allow-listed: public ID, public portfolio ID,
broker, environment, auto-sync/attention state, last sync, CSV coverage, and
creation time. Error text and every credential-related column are excluded.

## Deletion persistence and execution

The pending request is a versioned JSON value in the existing
`workspace_settings` row keyed by `privacy.workspace_deletion`. This table is
already workspace-scoped, forced through RLS, and deleted with its workspace.
Using it avoids a redundant schema and migration while retaining durable state
in PostgreSQL and the local edition.

`account_deletion.py` owns parsing, scheduling, cancellation, due-time checks,
and purge execution. A standalone `purge_account_deletions.py` command is the
external scheduler/local-operator entry point. It uses the repository's
existing narrowly-scoped job enumeration flag only to list active workspace
IDs, then resets RLS context to one workspace before reading or deleting it.
It commits each successfully purged workspace independently so one failed
identity deletion does not roll back unrelated tenants.

The command is safe to run repeatedly. Missing requests, future deadlines,
malformed state, and newly shared workspaces are skipped. A workspace that has
become shared is never deleted automatically.

## Audit and retention

Scheduling and cancellation create workspace audit events in the same
transaction as the state change. Final tenant deletion also deletes those
workspace audit rows; Portfyl does not silently retain a shadow copy of erased
financial data. Infrastructure backups expire according to the separately
documented managed-database retention policy and are not restored selectively
to recreate an erased account.

## Frontend

Settings gains a Data and privacy card. Export is a direct browser download.
Deletion uses an accessible confirmation dialog showing the workspace name,
30-day deadline, and the fact that access continues during grace. The user
types the exact workspace name and password; the password goes only to
Firebase, while Portfyl receives the fresh ID token. Pending state replaces the
form with the deadline and a cancellation control.

## Verification

- Backend tests prove workspace isolation, public-ID relationships, stable JSON
  serialization, and the absence of every secret-shaped broker field/value.
- Backend tests prove owner/sole-member enforcement, re-auth identity and
  freshness checks, idempotent scheduling, cancellation, grace timing,
  cross-workspace preservation, and due purge behaviour.
- Frontend tests prove download behaviour, password re-auth, typed
  confirmation, pending state, and cancellation.
- The complete fast backend and frontend suites run before each commit.

## Non-goals

- Exporting third-party market-data cache or derived quote/fundamental data.
- Deleting a shared workspace or transferring workspace ownership.
- Shortening deletion because a trial or subscription expires.
- Retaining erased financial records for product analytics.
- Changing the current Alembic head or any rate-limiting work owned by the
  concurrent implementation session.
