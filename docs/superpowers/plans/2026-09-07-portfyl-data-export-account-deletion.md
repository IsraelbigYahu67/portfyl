# Portfyl Data Export and Account Deletion Implementation Plan

**Goal:** Implement plan-independent, workspace-scoped JSON export and a
verified 30-day deletion workflow for both Portfyl editions.

**Architecture:** Add an account router below the existing settings router,
build exports from explicit workspace-filtered queries and public UUID
relationships, persist pending deletion state in the existing RLS-protected
workspace settings table, and execute due deletions through an idempotent
standalone cleanup command. Firebase password sign-in supplies a fresh backend-
verified re-authentication token.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, PostgreSQL forced RLS, Firebase Admin,
React 18, TanStack Query, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-09-07-portfyl-data-export-account-deletion-design.md`

## Global Constraints

- Do not modify files owned by the concurrent rate-limiting session.
- Export and deletion are available on Free, paid, and local editions without
  entitlement or quota checks.
- Trial or plan state must never schedule or execute data deletion.
- Every application query has an explicit workspace predicate in addition to
  PostgreSQL RLS.
- Export no secrets, ciphertext, key version, session material, raw integer
  key, or broker error text.
- Never delete a workspace with more than one active member.
- Preserve the full grace window on repeated schedule requests.
- Run `cd backend && python -m pytest tests/ --ignore=tests/postgres -v` and
  `cd frontend && npm test` before every commit.

---

### Task 1: Versioned workspace JSON export

**Files:**
- Create: `backend/workspace_export.py`
- Create: `backend/routers/account.py`
- Modify: `backend/routers/settings.py`
- Test: `backend/tests/test_account_export.py`

**Interfaces:**
- `build_workspace_export(db, context, exported_at=...) -> dict`
- `GET /api/settings/account/export`

- [x] Write failing tests for the required collections, public UUID
  relationships, cross-tenant exclusion, deterministic order, attachment
  headers, and secret exclusion.
- [x] Run the focused tests and record the expected failure.
- [x] Implement allow-listed serialization and the export endpoint.
- [x] Run focused tests, the complete fast backend suite, and frontend suite.
- [x] Commit the export slice.

### Task 2: Verified grace-period state machine

**Files:**
- Create: `backend/account_deletion.py`
- Modify: `backend/firebase_identity.py`
- Modify: `backend/routers/account.py`
- Test: `backend/tests/test_account_deletion.py`
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- `GET/POST/DELETE /api/settings/account/deletion`
- `schedule_workspace_deletion`, `cancel_workspace_deletion`, and
  `get_workspace_deletion`

- [x] Write failing tests for role and sole-member checks, exact-name
  confirmation, verified matching identity, recent Firebase `auth_time`,
  idempotency, cancellation, and workspace isolation.
- [x] Run the focused tests and record the expected failure.
- [x] Implement the durable workspace-setting state machine, audit events, and
  backend re-authentication checks.
- [x] Run focused tests, the complete fast backend suite, and frontend suite.
- [x] Commit the verified scheduling slice.

### Task 3: Idempotent due-deletion execution

**Files:**
- Modify: `backend/account_deletion.py`
- Create: `backend/purge_account_deletions.py`
- Test: `backend/tests/test_account_deletion.py`

**Interfaces:**
- `purge_due_workspace_deletions(db, verifier, now=...) -> summary`
- `python backend/purge_account_deletions.py`

- [x] Write failing tests proving future requests remain, due workspaces are
  purged, shared workspaces are preserved, other memberships keep the Portfyl
  and Firebase user, last-workspace deletion removes both, and repeats no-op.
- [x] Run the focused tests and record the expected failure.
- [x] Implement RLS-safe workspace enumeration, per-workspace deletion, Firebase
  identity removal, independent commits, and machine-readable CLI output.
- [x] Run focused tests, the complete fast backend suite, and frontend suite.
- [x] Commit the purge slice.

### Task 4: Settings data-and-privacy UI

**Files:**
- Modify: `frontend/src/api.js`
- Modify: `frontend/src/auth/firebase.js`
- Create: `frontend/src/components/DataPrivacySettings.jsx`
- Create: `frontend/src/components/DataPrivacySettings.test.jsx`
- Modify: `frontend/src/pages/Settings.jsx`

**Interfaces:**
- Export helper returns the JSON blob and filename from response headers.
- Firebase helper performs a fresh e-mail/password sign-in and always signs
  the in-memory Firebase client back out.
- Settings renders export, schedule, pending-deadline, and cancel states.

- [x] Write failing component/API tests for download, password re-auth, typed
  confirmation, pending state, errors, and cancellation.
- [x] Run focused frontend tests and record the expected failure.
- [x] Implement API helpers, Firebase re-auth, and accessible Settings UI.
- [x] Run focused tests, the complete fast backend suite, and frontend suite.
- [x] Commit the frontend slice.

### Task 5: Compliance record and final verification

**Files:**
- Modify: `docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md`
- Modify: this plan

- [x] Run the complete fast backend suite and frontend suite.
- [x] Run local/cloud frontend builds and PostgreSQL integration tests if the
  disposable PostgreSQL service is available.
- [x] Confirm the working tree does not include concurrent-session files.
- [x] Check off the implemented export/deletion items and record verification.
- [x] Commit documentation and verification results without pushing.

## Verification record (2026-09-07)

Schema version `2` follow-up (2026-09-07) extends the portable bundle to the
remaining user-provided workspace data: custom benchmarks/components, options,
broker balances, Polymarket positions, trade notes, cash-interest settings,
notification preferences/history, and safe preference allow-lists. It retains
public-ID relationships and excludes Discord/AI secrets, deletion state,
operational schedule state, raw internal keys, and cross-tenant rows.
Focused export tests: `6 passed`; complete fast backend: `547 passed`;
PostgreSQL privacy/RLS: `2 passed`; frontend local: `26` files / `142` tests.

- Fast backend: `546 passed`.
- PostgreSQL integration: `321 passed`, including real HTTP/RLS isolation for
  the export and deletion-status endpoints.
- Frontend local: `26` files / `142` tests passed.
- Frontend cloud: `26` files / `142` tests passed.
- Local and cloud Vite production builds both succeeded. The existing bundle
  size advisory remains unchanged and is non-fatal.
- Focused backend: export `5 passed`; scheduling/auth `20 passed`; cleanup/auth/
  CLI `28 passed`.
- Focused frontend: Data & privacy UI `3 passed`.
- `EXPECTED_ALEMBIC_HEAD` remains `0012_rate_limit_buckets`; no new model,
  table, or migration was required because pending deletion state uses the
  existing RLS-protected `workspace_settings` table.
- Concurrent rate-limiting files and the pre-existing untracked local logs/dev
  compose file were not staged or modified by this work. No push was made.
