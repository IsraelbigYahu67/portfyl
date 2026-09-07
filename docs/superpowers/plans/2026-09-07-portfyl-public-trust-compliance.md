# Portfyl Public Trust and Compliance Implementation Plan

**Goal:** Establish an evidence-backed compliance baseline now and define the
safe publication gate for Portfyl's public privacy, terms, subprocessor,
support, and security surfaces.

**Architecture:** Keep implemented-system evidence in a versioned data-
processing inventory and incident playbook. Public React routes are a later
slice gated on reviewed operator identity, contacts, retention, and legal text;
they must never ship with fabricated placeholders.

**Tech Stack:** Markdown operational records, FastAPI/SQLAlchemy evidence,
React/Vite route tests, pytest, Vitest.

**Spec:**
`docs/superpowers/specs/2026-09-07-portfyl-public-trust-compliance-design.md`

## Global constraints

- Preserve existing user and concurrent-session changes.
- Describe current behaviour separately from proposed policy.
- Do not mark a legal/compliance checklist item complete without evidence.
- Do not publish personal contact information or an unverified mailbox.
- Do not claim commercial rights to Yahoo/yfinance or another provider.
- Cloud trust copy must never advertise Tax Report or Screener.
- No raw financial data or credentials in analytics, logs, or incident records.

### Task 1: Reconcile the master plan

**Files:**
- Modify: `docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md`

- [x] Compare the master checklist with completed focused plans and commits.
- [x] Mark the edition boundary, provider-neutral plan enforcement, pricing
      comparison, secrets/jobs, rate limiting, EU deploy, export, and deletion
      accurately without closing monitoring, restore, licensing, or legal work.
- [x] Replace active Stripe/trial wording where it incorrectly describes the
      current non-payment roadmap.

### Task 2: Implement the technical compliance record

**Files:**
- Create: `docs/compliance/data-processing-inventory.md`
- Create: `docs/operations/security-incident-response.md`

- [x] Inventory identity, workspace, financial, settings, credentials,
      notifications, usage/rate-limit, audit, job, and migration data.
- [x] Map storage, external recipients, encryption, export, deletion, and known
      retention behaviour.
- [x] Record unresolved operator decisions explicitly instead of inventing
      retention periods.
- [x] Define severity, containment, evidence minimization, recovery,
      notification assessment, support verification, and drill records.

### Task 3: Prepare the market-data due-diligence package

**Files:**
- Create: `docs/research/market-data-vendor-requirements-2026-09-07.md`

- [x] Enumerate the exact cloud data fields and usage patterns requiring
      commercial rights.
- [x] Define a comparable vendor response matrix covering display,
      redistribution, caching, derived analytics, history, exchanges, regions,
      DPA/SCC terms, rate limits, SLA, and price.
- [x] Record a shortlist and public evidence without treating public pricing as
      contractual permission.
- [ ] Leave sending requests and accepting terms for explicit owner authority.

### Task 3a: Close the workspace export coverage gap

**Files:**
- Modify: `backend/workspace_export.py`
- Modify: `backend/tests/test_account_export.py`
- Modify: privacy/export design and compliance inventory

- [x] Write a failing test for custom benchmarks, options, broker balances,
      Polymarket positions, trade notes, cash-interest settings, notification
      preferences/history, and safe workspace/user preferences.
- [x] Bump the export schema version and add explicitly workspace-scoped,
      deterministic, public-ID-only serializers.
- [x] Prove Discord/AI secrets, deletion state, raw internal keys, and
      cross-tenant rows remain excluded.
- [x] Run focused, fast, and PostgreSQL isolation tests plus frontend tests.

### Task 4: Add public trust routes after operator/legal inputs

**Files (anticipated):**
- Create: `frontend/src/legal/trustContent.js`
- Create: `frontend/src/pages/Privacy.jsx`
- Create: `frontend/src/pages/Terms.jsx`
- Create: `frontend/src/pages/Subprocessors.jsx`
- Create: `frontend/src/pages/Support.jsx`
- Create: `frontend/src/pages/Security.jsx`
- Modify: cloud route manifest and public/authenticated navigation surfaces
- Test: public route, link, content, and edition-claim tests

- [ ] Obtain and record the controller identity, working contacts, approved
      legal bases, retention values, provider regions/DPA links, and reviewed
      legal copy.
- [ ] Write failing route/link/content tests.
- [ ] Implement accessible public pages from one content source.
- [ ] Run local/cloud frontend tests and production builds.
- [ ] Obtain final legal approval before production deployment.

### Task 5: Verification and review cadence

- [x] Run the complete fast backend and frontend suites before the documentation
      commit.
- [ ] Review the inventory after every provider, schema, integration, logging,
      analytics, export, or deletion change.
- [ ] Run a tabletop security/privacy incident drill and record the outcome.
- [ ] Revisit the public-page gate after the market-data and operator inputs are
      resolved.

## Current publication blockers

- Controller/legal entity details and jurisdiction.
- Verified privacy/support/security contact channels.
- Production Neon PITR retention value.
- Final legal bases, retention schedule, consumer terms, and counsel review.
- Contracted commercial market-data provider and transfer terms.

## Verification record (2026-09-07)

- Fast backend suite: `546 passed`.
- Frontend local suite: `26` files / `142` tests passed.
- Export-v2 follow-up: focused export `6 passed`; fast backend `547 passed`;
  PostgreSQL privacy/RLS `2 passed`; frontend local `26` files / `142` tests
  passed.
- `git diff --check` reported no whitespace error; the existing Windows
  LF-to-CRLF working-copy advisory remains non-fatal.
- No production configuration, provider account, e-mail, contract, or legal
  acceptance was changed by this documentation slice.
