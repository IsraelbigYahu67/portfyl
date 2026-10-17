# Portfyl

Portfolio analytics for a Trading 212 / IBKR investor. Import broker CSVs (or
sync via API), then view performance, allocation, dividends, options, tax
reports, and an AI assistant across one or more portfolios. Now multi-tenant
(Firebase-verified identities, workspace-scoped PostgreSQL data) —
**a multi-user SaaS conversion is in progress**, with tenant isolation and the
edition boundary and first-run onboarding done, while paid checkout remains deferred; see below.
(Formerly "Snowball Analytics" — some internal identifiers still carry the
`sb_` prefix for backwards compatibility; see the naming notes below.)

## In-progress: multi-user SaaS conversion

Portfyl is being converted from a single-user self-hosted app into a two-edition
product. Full spec, market research, architecture, tier pricing, and phased
rollout plan:
**`docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md`** — read it
before starting any auth, tenancy, database, or billing work.

- `PORTFYL_EDITION=local` — the owner's private instance. Keeps Tax Report and
  Screener. No billing.
- `PORTFYL_EDITION=cloud` — multi-tenant SaaS with Free / Investor EUR 4.99 /
  Pro EUR 7.99 plans. Paid checkout and trials are not active; the pricing page
  lets authorized private testers switch workspace entitlements without
  payment. This test selection creates no purchase or subscription. Paddle is
  the likely future payment provider but is not implemented. Tax Report and
  Screener are **permanently excluded from cloud** — not deferred, a deliberate
  product decision (see plan §2, §7, §12).
- **Workstreams B (PostgreSQL/Alembic foundation), C (Firebase identity,
  `User → Membership → Workspace` tenancy, UUID API IDs, forced PostgreSQL
  RLS), and D (KMS/Fernet encrypted secrets, external Cloud Scheduler jobs,
  redacted logging, dead-letter state, audit log, and subsystem health) are
  DONE** — see
  `docs/superpowers/plans/2026-09-01-portfyl-multiuser-foundation.md` for the
  B/C record and `docs/superpowers/plans/2026-09-04-portfyl-secrets-jobs.md`
  for D. The **technical edition/capability boundary is also
  DONE** — see `docs/superpowers/plans/2026-09-03-portfyl-edition-boundary.md`.
  Cloud does not register or bundle Tax Report/Screener; local keeps both.
  **Everything in the rest of this file now describes
  that implemented state**, not the old single-user SQLite one. What's
  **still pending**: Workstream A's external product/data validation and
  commercial market-data rights, and a future paid checkout. Empty workspaces
  now receive unified demo/import/broker onboarding, and CSV imports require a
  duplicate-aware preview before commit with a guarded 24-hour undo point. Don't
  reintroduce single-user/`owner_id="default"`/SQLite-primary
  assumptions anywhere in this codebase — that state is gone, not deferred.
- Deploy stack for the cloud edition: **Google Cloud Run + Neon (managed
  PostgreSQL) + Cloudflare** (domain + DNS for portfyl.com) — see
  `deploy/cloudrun.md` for the runbook, `docs/operations/sqlite-to-neon-migration.md`
  for the one-off owner data import, and
  `docs/operations/neon-backup-restore.md` for the PITR restore drill.
- The kickoff prompt for the now-completed Workstreams B + C work is at
  `docs/superpowers/plans/2026-09-01-portfyl-multiuser-foundation-prompt.md`
  (historical reference — useful for *why* a given file looks the way it
  does, not a to-do list).

## Frontend changes: read `DESIGN.md` first

**Before making any frontend change** — new or edited page, component, chart,
color, spacing, animation, theme token or CSS — read **`DESIGN.md`** in the
repo root and follow it. It is the source of truth for the live look: the warm
organic palette (including the exact chart series colors and their order),
rounded shapes, Clay depth/shadows, typography floors, hover/motion rules
(`hover-pop-zone`, `pie-pop`, the sliding `SegmentedControl`) and a checklist.
Do not hardcode hex colors or invent new chart colors; use the tokens it names.
If your change alters the look (palette, radii, motion), update `DESIGN.md` in
the same change. The older `.stitch/DESIGN.md` is historical (periwinkle
mockup) and does not override it.

## Stack

- **Backend**: FastAPI + SQLAlchemy 2.0, **PostgreSQL (Neon in prod) via
  Alembic** — there is no SQLite runtime path any more except the
  `PORTFYL_TESTING=1` in-memory fixture the fast unit suite uses (see
  `backend/database.py`'s `DatabaseSettings.from_env`, which fails closed on
  a non-PostgreSQL `DATABASE_URL` otherwise). Market data via `yfinance`;
  `pandas`/`numpy` for calcs; `httpx` for outbound calls.
- **Frontend**: React 18 + Vite 6, TailwindCSS, `recharts`, `@tanstack/react-query`,
  `axios`, `react-router-dom` 7. SPA in `frontend/src` (pages + components).
  Visual design: see **`DESIGN.md`** (warm organic Premium/Clay palette plus
  the Classic themes). Token source of truth is `frontend/src/lib/themeTokens.js`
  (applied by `App.jsx`'s `applyAppearance`) and `frontend/src/index.css`.
- **Deploy**: multi-stage `Dockerfile` → Cloud Run (multi-instance; PostgreSQL
  has no single-writer constraint). Database is Neon, reached via
  `DATABASE_URL` — nothing DB-related is baked into the image or mounted as a
  volume. See `deploy/cloudrun.md`.

## Run it

- **Dev (Windows)**: `start.bat` bootstraps the backend venv with **uv** on first
  run (`uv venv .venv --python 3.12`, then
  `uv pip install --require-hashes -r requirements.lock`),
  launches backend (`uvicorn main:app --reload`, port **8000**) + frontend
  (`npm run dev`, port **5173**) and opens the browser. Use **http://localhost:5173**
  — Vite proxies `/api` → :8000. (Install uv from
  https://docs.astral.sh/uv/ if the bootstrap step errors out.) A local
  `DATABASE_URL` pointing at PostgreSQL is required — see
  `backend/alembic.ini` / `alembic upgrade head`.
- **Backend only**: activate the `.venv` uv created, then from `backend/`,
  `python -m uvicorn main:app --reload --port 8000`.
- **Python runtime & dependency lock**: production runs `python:3.14-slim` and
  `node:22-alpine` (`Dockerfile`); CI runs the backend jobs as a matrix on
  Python **3.12** (dev) and **3.14** (prod) and the frontend on Node 22. Dev
  stays on 3.12 until the matrix has been green for two weeks, then `start.bat`
  and CI move to 3.14 (plan R2). `backend/requirements.txt` and
  `requirements-dev.txt` are the input specs (lower bounds only);
  `backend/requirements.lock` / `requirements-dev.lock` are the universal,
  hashed lock (valid on 3.12 and 3.14) that the Dockerfile, CI and `start.bat`
  install with `--require-hashes`. After changing a spec file, or to pick up
  newer versions, regenerate from the repo root (dev lock second, it is
  constrained to the prod lock) and commit both:
  `uv pip compile backend/requirements.txt --universal --generate-hashes --python-version 3.12 -o backend/requirements.lock`
  then
  `uv pip compile backend/requirements-dev.txt --universal --generate-hashes --python-version 3.12 -c backend/requirements.lock -o backend/requirements-dev.lock`
  (add `--upgrade` to the first to bump pins). The `backend-lock` CI job fails
  when the committed locks no longer match the specs. `requirements*.txt` and
  `requirements*.lock` are a **hotspot**: only one task at a time may change
  them (see "Parallel session safety").
- **Prod build**: `npm run build` emits `frontend/dist`, which FastAPI serves as a
  same-origin local-edition SPA; `npm run build:cloud` emits the cloud edition.
  The Dockerfile always uses the cloud build. See the SPA fallback at the
  bottom of `main.py`.
- **Login**: Firebase Authentication verifies identity, by e-mail/password or
  by a Google **popup**. Never use a redirect: `inMemoryPersistence` cannot
  survive one. Portfyl then issues its own opaque, revocable session
  (`backend/auth.py`, `backend/routers/auth.py`). There is no shared
  `APP_PASSWORD`/`SESSION_SECRET` any more. Unauthenticated `/api` calls get
  401, and the SPA routes to `/login`/`/register` (`frontend/src/auth/`).
  Two settings control the Google button: the build flag
  `VITE_FIREBASE_GOOGLE_SIGN_IN=true`, and the runtime
  `PORTFYL_FIREBASE_AUTH_DOMAIN`, which the CSP in `security_headers.py`
  needs. See `docs/superpowers/plans/2026-10-12-portfyl-google-sign-in.md`
  and the "Google sign-in" section of `deploy/cloudrun.md`.

## Architecture & conventions (read before editing)

- **All API routes are under `/api`** (mounted with that prefix in `main.py`).
  Routers live in `backend/routers/`: portfolio(s), market, analytics, broker,
  ibkr, watchlists, benchmarks, options, polymarket, discord, notes, assistant.
- **Portfolio scoping is implicit.** The axios interceptor in `frontend/src/api.js`
  auto-injects `portfolio_id` (a UUID `public_id`, not an integer) from the
  active portfolio into every request — call sites never pass it.
  **Exceptions**: prefixes in `PORTFOLIO_AGNOSTIC_PREFIXES` (`/portfolios`,
  `/market`, `/watchlists`, `/settings`, `/auth`, `/capabilities`,
  `/test-plans`) must NOT receive it. If you add a cross-portfolio endpoint,
  add its prefix there or it will 404/mis-route.
  The same interceptor also attaches `X-Workspace-ID` (once a workspace is
  resolved) and `X-CSRF-Token` (on mutating methods) — see `AuthProvider`
  (`frontend/src/auth/AuthProvider.jsx`) and `configureRequestContext` in `api.js`.
- **Every request is workspace-scoped, not single-owner.** `backend/tenancy.py`'s
  `get_request_context()` resolves the opaque session cookie, the `X-Workspace-ID`
  header, and the caller's `Membership` into a `RequestContext`; routers use
  `require_portfolio()` (or an equivalent workspace-filtered query) instead of a
  global owner sentinel. **All public API IDs are UUID `public_id` values** —
  raw integer primary/foreign keys are never accepted or serialized (see
  `backend/models.py`). PostgreSQL **row-level security is forced** on every
  tenant table (`backend/alembic/versions/0002_tenant_rls.py`) as defense in
  depth on top of these application-level predicates — both layers are
  mandatory; RLS does not replace the application check, and vice versa.
- **Edition availability is backend-owned and fail-closed.** `backend/edition.py`
  is the central capability registry. `PORTFYL_EDITION` must be exactly
  `local` or `cloud`; `start.bat` declares local and the Docker image declares
  cloud. `backend/routers/local_features.py` is mounted only in local, while
  Vite resolves `@edition-manifest` to `frontend/src/editions/local.jsx` or
  `cloud.jsx` at build time. Shared UI additionally reads `/api/capabilities`.
  Never re-add Tax Report/Screener to shared routers, `App.jsx`, `Sidebar.jsx`,
  or `api.js`.
- **DB migrations are Alembic, run explicitly — never at web startup.**
  `backend/main.py`'s startup hook only *asserts* the DB's `alembic_version`
  matches the code's expected head (`database.py`'s `assert_alembic_head`) and
  fails closed on a mismatch; it performs no `CREATE TABLE`/`ALTER TABLE`
  itself. **Every change under `backend/alembic/versions/` must update
  `backend/database.py`'s `EXPECTED_ALEMBIC_HEAD` to the exact current
  `alembic heads` revision in the same change.** A migration is not complete
  until Alembic has exactly one head, that head equals the constant, and backend
  startup passes `assert_alembic_head()`. Run `cd backend && alembic upgrade
  head` (see `backend/alembic.ini`) with the migration-owner credential, never
  the restricted runtime credential, after adding a migration. Run the Cloud
  Run migration Job (`deploy/run-migrations.ps1`) before every service deploy
  — see `deploy/cloudrun.md`. Never commit, deploy, or report migration work
  complete while the two revisions differ.
- **Never run database work on the event loop.** SQLAlchemy is synchronous
  here, so an endpoint or dependency that touches a `Session` is a plain
  `def` (FastAPI runs it in the threadpool); an `async def` one froze the
  whole Cloud Run instance on 2026-10-11. Async helpers shared with the job
  passes (`alerts.run_check`, `ibkr._run_ibkr_sync`, the `jobs.py` passes)
  are driven from sync code via `private_loop.run_on_private_loop`. Call
  `database.release_connection` before slow outbound calls.
  `tests/test_event_loop_not_blocked.py` enforces this.
- **Money / FX**: transactions carry `fx_to_czk`; values are normalized to **CZK**.
  Missing rates are backfilled at startup via `fx.bulk_fetch_fx`. Preserve this
  when touching valuation/performance code.
- **Valuation uses the 5-year average P/E, not the current P/E.** This is a
  deliberate methodology choice for fair-value / valuation calcs.
- **yfinance is noisy.** "possibly delisted" / "no earnings dates" errors are
  expected for thin tickers; logging is suppressed to CRITICAL and missing data
  is handled with empty/null checks. Don't "fix" these by adding noise back.

## Gotchas

- Build artifacts (`frontend/dist`, `node_modules`, `__pycache__`, `*.db`, `.venv`)
  are **git-ignored** — don't commit them. (They were tracked in an earlier import
  and scrubbed on export; see `.gitignore`.)
- Pages: `frontend/src/pages/` (Dashboard, Allocation, Analytics, Dividends,
  Options, Polymarket, Screener, TaxReport, Transactions,
  Watchlists, Import, Settings, Stock, Search, Assistant, PlatformLanding).
  Reusable charts/widgets in `frontend/src/components/`.
- Sample import data: `sample_portfolio.csv` at the project root.

## Naming (Snowball → Portfyl)

The product was renamed from "Snowball Analytics" to **Portfyl**. User-visible
strings are all Portfyl, but `sb_*` localStorage keys (theme/palette/currency
prefs, `sb_portfolio_id`) deliberately keep the old prefix because renaming
them would silently drop existing users' preferences/selection — don't
"finish" the rename on these. The old shared-password auth (the `sb_session`
cookie, the `snowball.auth` logger name, the `snowball-dev` dev-password
fallback) is gone, not renamed — it was fully replaced by Firebase identity
plus Portfyl's own opaque sessions (`__Host-portfyl_session` /
`portfyl_session`, `backend/auth.py`) in the multi-user conversion.

## Tests

### Backend (`backend/tests/`)

- **Fast unit suite** (`backend/tests/*.py`, not the `postgres/` subdir): runs
  against an in-memory SQLite session under the explicit `PORTFYL_TESTING=1`
  test-only switch (`tests/conftest.py` sets it, and `DATABASE_URL`, via
  `setdefault` before anything imports `database.py`) — most tests call
  router functions directly (see `tests/helpers.py`), bypassing HTTP/session
  middleware entirely; a few build a real `TestClient` app (e.g.
  `tests/postgres/conftest.py`'s `matrix_client`) for full-stack cases. Run
  from `backend/`: `python -m pytest tests/ -v` (or add `--ignore=tests/postgres`
  to skip the suite below).
- **PostgreSQL integration suite** (`backend/tests/postgres/`): exercises
  real Alembic migrations, forced RLS, and the complete Alice/Bob tenant
  isolation matrix (`docs/security/tenant-isolation-matrix.md`) against a
  disposable PostgreSQL 16 database — **this is the beta go/no-go gate**, not
  optional coverage. Requires Docker Desktop
  (`docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait`)
  or an explicit disposable `TEST_DATABASE_URL` (must contain `test` in the
  database name — `tests/postgres/conftest.py` refuses anything else). Run:
  `cd backend && python -m pytest tests/postgres/ -v`. Never replace these
  with SQLite-only assertions — RLS and real-role behavior don't exist in
  SQLite.
- **Neither pytest nor the PostgreSQL-test extras are in `requirements.txt`**
  — install the hashed lock `backend/requirements-dev.lock` into the venv
  (`uv pip install --require-hashes -r requirements-dev.lock`, which includes
  the runtime lock) before running either suite. Run the fast suite on both 3.12
  and 3.14 (`uv venv --python 3.14`) when touching dependencies — CI does.

### Frontend (`frontend/src/**/*.test.{js,jsx}`)

- **Vitest** suite, configured in `vite.config.js`'s `test` block
  (`environment: "jsdom"`, `setupFiles: "./src/test/setup.js"`). Uses
  `@testing-library/react` + `@testing-library/jest-dom`.
- Run from `frontend/`: `npm test` for a single run, `npm run test:watch` for
  watch mode.
- 11 test files exist today, e.g. `src/pages/Overview.test.jsx`,
  `src/components/ui/primitives.test.jsx`, `src/lib/format.test.js` — a
  reasonable starting point for existing patterns.
- Run `npm test`, `npm run test:cloud`, `npm run build`, and
  `npm run build:cloud` for edition-sensitive frontend changes. For ordinary
  shared UI changes, the local test/build pair remains the minimum.

## Verifying UI changes

Playwright MCP is installed. To check a frontend change, ensure a local
`DATABASE_URL` (PostgreSQL, migrated to head) is set and the dev servers are
running (`start.bat`), then drive **http://localhost:5173** — register or log
in with a Firebase test account — and screenshot/inspect rather than guessing
from the diff.

## Parallel session safety

Every plan must be built so multiple agent sessions can work in this
repository concurrently without blocking or corrupting each other:

1. **Isolated work areas.** Each session uses its own git branch (or git
   worktree) and never commits directly to the shared integration branch.
   Migrations and resource-mutating steps are isolated or explicitly ordered
   in the plan (per-session DB names, distinct ports) so sessions never write
   the same resource at the same time.
2. **Disjoint files per task.** Split the plan into independent tasks that
   touch disjoint sets of files. Shared hotspots — `backend/database.py`
   (`EXPECTED_ALEMBIC_HEAD`), `backend/alembic/versions/`, `.env`/config,
   lockfiles (`requirements*.txt`, `requirements*.lock`, `package.json`) — are owned by at most one
   concurrent task; tasks that need them are sequenced into later waves, not
   run in parallel.
3. **No shared resource-mutating steps.** Dev servers (backend :8000,
   frontend :5173), the test-postgres container, `alembic upgrade head`, and
   the Cloud Run migration Job against shared Neon are resource-mutating:
   each session runs them on its own instance (distinct ports/DB names) or
   the steps are explicitly sequenced in the plan. Never apply migrations to
   a database another session is actively using without coordination.
4. **Produce forward-compatible migrations.** Cloud Run serves the cloud
   edition from multiple instances, so every migration must be safe to apply
   while older instances are still running (no destructive in-place column
   changes; expand-then-migrate). Sequence any destructive step as a separate,
   explicitly-ordered follow-up wave.
5. **Re-integrate and re-verify before done.** After merging/rebasing shared
   upstream changes, re-run the affected verification (tests, `alembic heads`
   vs `EXPECTED_ALEMBIC_HEAD`, lint/test suites) and fix conflicts caused by
   concurrent sessions locally before reporting a task complete.
