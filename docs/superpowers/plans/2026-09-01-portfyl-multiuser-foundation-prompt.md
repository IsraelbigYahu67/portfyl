# Kickoff prompt: Multi-user foundation for Portfyl (Workstreams B + C)

> Scoped kickoff brief for a fresh Claude Code session, extracted from the
> master plan at
> `docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md`. This is
> **not** itself the task-level implementation plan the master plan calls
> for — it's the scoping prompt to hand to `superpowers:writing-plans` (or
> `superpowers:brainstorming` first, if design questions come up) to produce
> that plan, then execute with `superpowers:subagent-driven-development` or
> `superpowers:executing-plans`.

Context: Portfyl is being converted from a single-user self-hosted app into a
multi-user product. The full spec is
`docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md` — read it
before starting for full context on constraints, target architecture, and
later workstreams (billing, edition boundary, onboarding) that are explicitly
OUT of scope for this task.

Target deployment (adjust the plan's generic "PostgreSQL"/"Cloud Run" tech
stack to this specific choice): Google Cloud Run (backend + built frontend,
one container, request-based billing, min-instances=0) + Neon (managed
serverless PostgreSQL, replacing Cloud SQL in the master plan's wording) +
Cloudflare (domain registrar + DNS for portfyl.com). No GCS-mounted SQLite, no
Cloud SQL.

## Goal

Make the backend and frontend actually multi-user: real accounts, isolated
tenants, and a PostgreSQL database — with no billing, edition boundary, or
onboarding work yet (those are separate future task-level plans per the
master plan's own workstream decomposition).

## In scope: Workstream B (PostgreSQL foundation)

- Replace `backend/database.py`'s SQLite engine with PostgreSQL (Neon
  connection string via env var).
- Replace the imperative `_ensure_*`/`_backfill_*` startup migrations in
  `main.py` with Alembic migrations.
- Migrate `backend/models.py` schema to Postgres-compatible types/constraints.
- Write a rehearsed migration path from the existing SQLite data (the owner's
  real `portfyl.db`) to Postgres — a real data migration, not just schema.
- Postgres removes the single-writer constraint that currently pins Cloud Run
  to `--max-instances=1` (`deploy/cloudrun.md:146-149`) — update the Cloud Run
  deploy config to allow multiple instances once this lands.
- Confirm/configure Neon's point-in-time recovery and document a tested
  restore procedure.

## In scope: Workstream C (identity, workspaces, tenant isolation)

- Replace `backend/auth.py`'s `DEFAULT_OWNER_ID = "default"` sentinel
  (`backend/auth.py:28`, returned from `get_current_user()` at lines 56-63)
  with real user registration, verified e-mail, password reset, strong
  password hashing (or a managed identity provider), and server-side
  revocable sessions (logout from all devices). OAuth and MFA are explicit
  follow-ups, not required now.
- Introduce the `User → Membership → Workspace` model from the master plan
  (§8): Workspace becomes the tenant that owns portfolios, watchlists,
  alerts, settings. Give every existing solo installation one workspace + one
  owner membership — migrate the current owner's data, don't lose it.
- Scope every object lookup by workspace: fix
  `backend/routers/portfolios.py` (list at lines 49-50, update/delete around
  72-91, `require_portfolio()` at 175-191), `backend/routers/watchlists.py`
  (global list at 80-83), and `backend/app_settings.py` (key-only query at
  15-24) — none of these currently filter by owner/workspace.
- Replace global uniqueness with composite tenant-scoped uniqueness:
  `Portfolio.name` (`backend/models.py:14`), `Watchlist.name`
  (`backend/models.py:53`) → `(workspace_id, name)`; `AppSetting.key`
  (`backend/models.py:227`) → `(user_id, key)` or workspace-scoped, with
  personal vs. shared settings distinguished.
- Expose non-sequential UUID/ULID identifiers on public API responses instead
  of raw sequential IDs.
- Add PostgreSQL row-level security as defense in depth on tenant tables.
- Frontend: update session/account state, login/registration flow, and any
  place that assumes a single implicit account.
- Write a systematic Alice/Bob cross-tenant test matrix: prove one user
  cannot read, list, update, delete, or enumerate another user's portfolios,
  watchlists, settings, or alerts. No multi-user beta may ship without this
  passing (master plan §14 go/no-go item).

## Explicitly out of scope for this task (separate future plans)

- Stripe/billing/trial/entitlements (Workstream E).
- Local/cloud edition boundary and the `tax_report`/`screener` local-only
  capability registry (Workstream A) — don't remove or hide these features
  yet, just don't make cross-tenant access to them worse.
- Onboarding/paid packaging UI (Workstream F).
- KMS-encrypted secrets and external job scheduler (Workstream D) —
  background jobs can stay as-is for this task; if you touch them, make sure
  they carry workspace/tenant identity.

## Process

Per the master plan's own instructions: use `superpowers:writing-plans` (or
`superpowers:brainstorming` first if there are open design questions) to turn
this into a concrete, reviewable task-level implementation plan before
touching code, then execute with `superpowers:subagent-driven-development` or
`superpowers:executing-plans`.

## Also update

- `CLAUDE.md` and the master plan's Tech Stack references: replace the
  Cloud SQL wording with Neon, and note that Cloud Run no longer needs
  `--max-instances=1` once Postgres lands.

## Line-number caveat

File line references above match the codebase as of 2026-09-01 (the day the
master plan and this brief were written). Re-check them before relying on
exact line numbers if meaningful time has passed or the files have since
changed.
