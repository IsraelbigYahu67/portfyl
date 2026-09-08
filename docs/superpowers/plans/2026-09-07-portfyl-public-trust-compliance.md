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

### Task 3b: Record the private-test legal boundary

**Files:**
- Create: `docs/compliance/private-test-legal-status.md`
- Modify: `docs/compliance/data-processing-inventory.md`
- Modify: `docs/operations/security-incident-response.md`

- [x] Record the Czech, free, no-payment, owner-only private-test boundary.
- [x] Record `tom.zoubek@gmail.com` as the approved privacy, support, and
      security contact for this stage.
- [x] Record the active Cloudflare Access exact-email control; allow
      individually approved private testers while forbidding public sign-up
      and broad domain/group rules before the launch gate closes.
- [x] Record that no 18+ restriction is intended without claiming the current
      product is ready for minors.
- [x] Define the minor/child, retention, processor, market-data, controller,
      legal-review, drill, and restore prerequisites that remain open.

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

- Controller/legal entity name, legal form, postal address, and registration
  details. The jurisdiction is confirmed as the Czech Republic.
- `tom.zoubek@gmail.com` is verified as the private-test privacy, support, and
  security contact; dedicated public channels remain an optional launch
  decision.
- Production Neon PITR retention value.
- Final legal bases, retention schedule, consumer terms, and counsel review.
- Contracted commercial market-data provider and transfer terms.
- A reviewed child/minor access model, because an 18+ restriction is not
  intended.

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

## Private-test boundary verification (2026-09-08)

- The operator confirmed the Czech, owner-only, free private-test boundary,
  the contact address, and that no 18+ restriction is intended.
- Cloudflare Access remains the release control; public legal routes and
  external users remain blocked by the recorded launch gate.
- `git diff --check` reported no whitespace error; the existing Windows
  LF-to-CRLF working-copy advisory remains non-fatal.
- No legal identity, public terms, privacy notice, processor contract, or
  qualified legal approval was fabricated or implied.
