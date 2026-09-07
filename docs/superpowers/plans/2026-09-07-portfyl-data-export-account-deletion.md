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

- [ ] Write failing tests for the required collections, public UUID
  relationships, cross-tenant exclusion, deterministic order, attachment
  headers, and secret exclusion.
- [ ] Run the focused tests and record the expected failure.
- [ ] Implement allow-listed serialization and the export endpoint.
- [ ] Run focused tests, the complete fast backend suite, and frontend suite.
- [ ] Commit the export slice.

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

- [ ] Write failing tests for role and sole-member checks, exact-name
  confirmation, verified matching identity, recent Firebase `auth_time`,
  idempotency, cancellation, and workspace isolation.
- [ ] Run the focused tests and record the expected failure.
- [ ] Implement the durable workspace-setting state machine, audit events, and
  backend re-authentication checks.
- [ ] Run focused tests, the complete fast backend suite, and frontend suite.
- [ ] Commit the verified scheduling slice.

### Task 3: Idempotent due-deletion execution

**Files:**
- Modify: `backend/account_deletion.py`
- Create: `backend/purge_account_deletions.py`
- Test: `backend/tests/test_account_deletion.py`

**Interfaces:**
- `purge_due_workspace_deletions(db, verifier, now=...) -> summary`
- `python backend/purge_account_deletions.py`

- [ ] Write failing tests proving future requests remain, due workspaces are
  purged, shared workspaces are preserved, other memberships keep the Portfyl
  and Firebase user, last-workspace deletion removes both, and repeats no-op.
- [ ] Run the focused tests and record the expected failure.
- [ ] Implement RLS-safe workspace enumeration, per-workspace deletion, Firebase
  identity removal, independent commits, and machine-readable CLI output.
- [ ] Run focused tests, the complete fast backend suite, and frontend suite.
- [ ] Commit the purge slice.

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

- [ ] Write failing component/API tests for download, password re-auth, typed
  confirmation, pending state, errors, and cancellation.
- [ ] Run focused frontend tests and record the expected failure.
- [ ] Implement API helpers, Firebase re-auth, and accessible Settings UI.
- [ ] Run focused tests, the complete fast backend suite, and frontend suite.
- [ ] Commit the frontend slice.

### Task 5: Compliance record and final verification

**Files:**
- Modify: `docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md`
- Modify: this plan

- [ ] Run the complete fast backend suite and frontend suite.
- [ ] Run local/cloud frontend builds and PostgreSQL integration tests if the
  disposable PostgreSQL service is available.
- [ ] Confirm the working tree does not include concurrent-session files.
- [ ] Check off the implemented export/deletion items and record verification.
- [ ] Commit documentation and verification results without pushing.
