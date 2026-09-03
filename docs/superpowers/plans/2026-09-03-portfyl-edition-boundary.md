# Portfyl Edition and Capability Boundary Implementation Plan

**Goal:** Produce explicit `local` and `cloud` editions from one codebase while
making Tax Report and Screener impossible to expose in the cloud API or cloud
frontend build.

**Scope:** This plan implements only the technical edition/capability boundary
from Workstream A. Commercial data contracts, user interviews, pricing tests,
Stripe entitlements, KMS, and external jobs remain separate workstreams.

**Architecture:** A backend-owned capability registry classifies every current
product surface as `local_only`, `cloud_free`, `cloud_investor`, or
`cloud_pro`. `PORTFYL_EDITION` is validated at backend startup. Local-only API
routes live in a dedicated router registered only in `local`. Vite selects one
of two edition manifests at build time, so the cloud dependency graph contains
neither the Tax Report nor Screener page. The authenticated UI also consumes a
fail-closed capabilities endpoint so a mismatched local frontend cannot expose
features against a cloud backend.

## Constraints

- Accepted backend editions are exactly `local` and `cloud`; missing or unknown
  values fail startup.
- Local development and tests set `local` explicitly. The production container
  sets `cloud` explicitly for both frontend build and backend runtime.
- Cloud OpenAPI contains neither `/api/analytics/tax-report` nor
  `/api/market/screener`; direct requests return 404.
- Cloud frontend routes and navigation contain neither `/tax-report` nor
  `/screener`, and the cloud bundle does not import their page modules.
- `tax_report` and `screener` are permanently `local_only`.
- Classification is not plan enforcement. Investor/Pro enforcement belongs to
  Workstream E and must compose after edition availability.
- Existing tenant checks and UUID behavior remain unchanged.

## Task 1: Central backend edition registry

**Files:**

- Create `backend/edition.py`
- Create `backend/routers/capabilities.py`
- Create `backend/tests/test_edition.py`
- Modify `backend/tests/conftest.py`

- [x] Define strict edition parsing and the four capability classifications.
- [x] Classify current product surfaces in one immutable registry.
- [x] Return only edition-available capabilities from `/api/capabilities` so a
      cloud response does not advertise local-only features.
- [x] Test missing/unknown configuration, local/cloud allowance, and endpoint
      payloads.

## Task 2: Backend route isolation

**Files:**

- Create `backend/routers/local_features.py`
- Modify `backend/routers/analytics.py`
- Modify `backend/routers/market.py`
- Modify `backend/main.py`
- Create `backend/tests/test_edition_routes.py`

- [x] Remove Tax Report and Screener decorators from shared routers.
- [x] Register those handlers through the dedicated local-only router.
- [x] Validate `PORTFYL_EDITION` during `main.py` import and include the router
      only for `local`.
- [x] Reload/boot both editions and assert local positive behavior plus cloud
      OpenAPI/direct-URL negative behavior.

## Task 3: Frontend build and runtime boundary

**Files:**

- Create `frontend/edition.config.js`
- Create `frontend/src/editions/local.jsx`
- Create `frontend/src/editions/cloud.jsx`
- Modify `frontend/vite.config.js`
- Modify `frontend/package.json`
- Modify `frontend/src/api.js`
- Modify `frontend/src/App.jsx`
- Modify `frontend/src/components/Sidebar.jsx`
- Create `frontend/src/edition.test.jsx`
- Modify `Dockerfile`
- Modify `start.bat`

- [x] Resolve the edition-specific manifest through a Vite alias and reject
      missing/unknown build editions.
- [x] Keep local-only page imports solely in the local manifest.
- [x] Fetch backend capabilities after authentication and hide local-only
      navigation/routes until the server explicitly enables them.
- [x] Add explicit local/cloud build commands; make Docker build cloud and
      local startup local.
- [x] Test both manifests, runtime filtering, and strict build configuration.

## Task 4: Verification and plan record

- [x] Run focused backend edition tests.
- [x] Run the complete fast backend suite.
- [x] Run the frontend Vitest suite.
- [x] Build both local and cloud frontend editions.
- [x] Check the cloud output for Tax Report/Screener module and route leakage.
- [x] Run `git diff --check` and update the multiuser/master-plan completion
      record without marking external commercial-validation items complete.

## Completion record (2026-09-03)

- Backend edition tests: 9 passed.
- Complete backend suite, including disposable PostgreSQL 16 and the Alice/Bob
  RLS matrix: 657 passed, 0 failed.
- Local frontend: 133 tests passed; production build succeeded.
- Cloud frontend: 133 tests passed; production build succeeded.
- Cloud bundle scan found no `tax-report`, `tax_report`, or `screener` strings.
- `git diff --check` reported no whitespace errors (only the repository's
  normal Windows LF/CRLF conversion notices).
