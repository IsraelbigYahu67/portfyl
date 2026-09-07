# Portfyl Onboarding and Import Safety Implementation Plan

**Goal:** Let a new user reach demo or real portfolio value without support,
and make every CSV mutation previewable, duplicate-aware, reconcilable, and
recoverable for 24 hours.

**Architecture:** Add an empty-workspace onboarding surface and an atomic demo
factory to the existing portfolio API. Extract CSV parsing/state comparison
into a focused import workflow, require a deterministic preview before commit,
and keep one compressed, workspace-scoped pre-import snapshot per portfolio in
the existing settings table. Restore only when the post-import state has not
drifted.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, pandas, PostgreSQL forced RLS, React 18,
TanStack Query, Vitest, pytest.

**Spec:**
`docs/superpowers/specs/2026-09-07-portfyl-onboarding-import-safety-design.md`

## Global constraints

- Do not modify files reserved by the concurrent rate-limiting session,
  including `backend/models.py`, `backend/database.py`, `backend/main.py`, and
  its 0012 migration.
- Preserve the actual Alembic head `0012_rate_limit_buckets`; this slice adds no
  schema.
- Keep import and demo activation available in local and cloud; CSV import is
  available on Free and never starts a trial.
- Use both application workspace predicates and existing forced RLS.
- Never accept or serialize raw integer database IDs.
- Preview is read-only; commit and undo are CSRF-protected and atomic.
- Keep only one undo point per portfolio for 24 hours and fail closed on drift.
- Do not push or deploy; create local commits only.
- Preserve unrelated untracked files and user changes.

### Task 1: Specify the protocol and lock current behaviour

**Files:**
- Create: `docs/superpowers/specs/2026-09-07-portfyl-onboarding-import-safety-design.md`
- Create: `docs/superpowers/plans/2026-09-07-portfyl-onboarding-import-safety.md`
- Test: `backend/tests/test_import_workflow.py`

- [x] Inspect current CSV, portfolio, tenancy, quota, app-shell, and migration
      behaviour.
- [x] Define canonical duplicate identity, preview/commit drift protection,
      reconciliation counts, and guarded undo semantics.
- [x] Write failing pure workflow tests before extraction.

### Task 2: Implement read-only preview and duplicate reconciliation

**Files:**
- Create: `backend/import_workflow.py`
- Modify: `backend/routers/portfolio.py`
- Create/modify: focused backend tests

- [x] Extract bounded CSV parsing/normalization without changing Trading 212
      losslessness rules.
- [x] Add stable transaction fingerprints and collapse exact in-file repeats.
- [x] Compare the unique import with the current portfolio for append/replace
      and return a bounded preview payload.
- [x] Add `POST /portfolio/import-csv/preview` and prove it performs no writes.
- [x] Run focused tests to green.

### Task 3: Require previewed commit and add guarded undo

**Files:**
- Create: `backend/import_undo.py`
- Modify: `backend/routers/portfolio.py`
- Modify: `backend/tests/test_t212_import.py`
- Create/modify: focused import tests

- [ ] Write failing tests for changed-file/current-state rejection, exact
      duplicate skipping, atomic replacement, snapshot retention, expiry,
      conflict, one-shot restore, and trade-note restoration.
- [ ] Add commit, undo-status, and undo endpoints with CSRF dependencies.
- [ ] Persist compressed snapshots under an internal workspace-setting key and
      record bounded audit metadata only.
- [ ] Retire the direct mutating HTTP route while preserving normalization test
      coverage through an internal helper.
- [ ] Run focused tests to green.

### Task 4: Add atomic demo and empty-workspace onboarding

**Files:**
- Modify: `backend/routers/portfolios.py`
- Create/modify: focused portfolio tests
- Create: `frontend/src/pages/Onboarding.jsx`
- Create: `frontend/src/pages/Onboarding.test.jsx`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/api.js`

- [ ] Write failing backend tests for deterministic demo rows, tenant scope,
      plan limits, atomicity, and refusal in a non-empty workspace.
- [ ] Implement `POST /portfolios/demo` and reuse ordinary plan enforcement.
- [ ] Write failing frontend tests for the three onboarding paths and errors.
- [ ] Render onboarding whenever the selected workspace has no portfolios;
      create/select an empty portfolio before import or broker setup.
- [ ] Run focused backend/frontend tests to green.

### Task 5: Replace one-click import UI with preview/commit/undo

**Files:**
- Modify: `frontend/src/pages/Import.jsx`
- Create: `frontend/src/pages/Import.test.jsx`
- Modify: `frontend/src/api.js`

- [ ] Write failing UI tests proving commit is unavailable before preview and
      reconciliation/removal/duplicate counts are visible afterward.
- [ ] Add the preview/review/commit state machine and explicit replacement
      confirmation.
- [ ] Show undo availability after commit and handle expiry/conflict without
      claiming current data was changed.
- [ ] Invalidate all derived and portfolio-count queries after commit/undo.
- [ ] Run focused and full frontend tests.

### Task 6: Tenant verification and plan reconciliation

**Files:**
- Modify: PostgreSQL privacy/matrix tests only if the new routes require cases
- Modify: `docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md`
- Modify: this plan

- [ ] Prove Alice cannot preview, commit, inspect, or undo against Bob's
      portfolio through application scoping and forced RLS.
- [ ] Run the complete fast backend suite and frontend suite.
- [ ] Run relevant PostgreSQL RLS tests and both local/cloud frontend builds.
- [ ] Mark the unified onboarding and import preview/duplicate/reconciliation/
      undo P0 items complete only with recorded passing evidence.
- [ ] Commit the completed slice locally without pushing.
