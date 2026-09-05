# Portfyl Plans Without Payments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Stripe and automatic trials while retaining a static cloud pricing page and provider-neutral server-side Free-plan enforcement.

**Architecture:** Move plan policy into `backend/plans.py`, make cloud entitlement resolution deterministically Free, and delete every payment-provider entry point. Keep generic usage and notification persistence, dropping only provider/trial tables through a new migration. Render pricing entirely from frontend constants and make paid CTAs open a transparent informational dialog.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, React 18, TanStack Query removal from the pricing page, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-09-05-portfyl-plans-without-payments-design.md`

## Global Constraints

- Preserve the existing Free, Investor, and Pro prices, features, capabilities, and resource limits.
- Cloud workspaces resolve to Free; local remains unrestricted.
- No Stripe SDK, secret, endpoint, scheduled job, model, table, or frontend call remains in active code or deployment instructions.
- No successful import or broker connection starts a trial.
- Historical verification documents remain available and are marked superseded instead of rewritten as if the old work never happened.
- Preserve unrelated working-tree changes under `docs/research/`.

---

### Task 1: Provider-neutral plans and Free-only cloud resolution

**Files:**
- Create: `backend/plans.py`
- Delete: `backend/billing_config.py`
- Modify: `backend/entitlements.py`
- Modify imports in affected routers and tests.
- Test: `backend/tests/test_plans.py`
- Test: `backend/tests/test_entitlements.py`

**Interfaces:**
- Produces: `PlanTier`, `PlanLimits`, `MINIMUM_PLAN`, `plan_limits()`, and `plan_allows()` from `plans.py`.
- Produces: `resolve_entitlements(..., edition=Edition.CLOUD, ...)` returning `source="free"` without database access.

- [ ] Write tests importing provider-neutral plan policy from `plans` and proving cloud resolution remains Free even when the database object raises on access.
- [ ] Run the focused tests and confirm they fail because `plans.py` does not exist and cloud resolution still queries payment tables.
- [ ] Move only plan policy into `plans.py`; remove subscription/trial lookups from `entitlements.py` and update imports.
- [ ] Run the focused tests and confirm they pass.

### Task 2: Remove Stripe and trial runtime entry points

**Files:**
- Delete: `backend/stripe_service.py`
- Delete: `backend/billing_reconciliation.py`
- Delete: `backend/billing_jobs.py`
- Delete: `backend/trials.py`
- Delete: `backend/routers/billing.py`
- Delete: `deploy/verify-stripe-catalog.py`
- Modify: `backend/main.py`
- Modify: `backend/jobs.py`
- Modify: `backend/routers/internal_jobs.py`
- Modify: `backend/routers/{portfolio,broker,ibkr,polymarket}.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_edition_routes.py`
- Test: `backend/tests/test_internal_jobs.py`

**Interfaces:**
- Cloud OpenAPI exposes no `/api/billing/*` path.
- Internal jobs expose alerts, autosync, and dividends, not billing.

- [ ] Change route/job tests first so they require payment APIs and the billing job endpoint to be absent.
- [ ] Run focused route/job tests and confirm they fail against the current runtime.
- [ ] Remove payment/trial imports, route mounts, job registration, activation calls, SDK dependency, and provider files.
- [ ] Run focused route/job and affected import/broker tests and confirm they pass.

### Task 3: Remove provider/trial persistence safely

**Files:**
- Create: `backend/alembic/versions/0011_remove_payment_runtime.py`
- Modify: `backend/database.py`
- Modify: `backend/models.py`
- Modify: `backend/tests/test_billing_schema.py` (rename to `test_plan_schema.py`)
- Modify: `backend/tests/postgres/conftest.py`
- Modify: `backend/tests/postgres/test_rls.py`
- Modify: `backend/tests/postgres/test_runtime_role.py`
- Modify: `deploy/validate-restore.py`
- Delete provider lifecycle tests that no longer describe supported behaviour.

**Interfaces:**
- Alembic head is `0011_remove_payment_runtime`.
- Retained plan infrastructure maps only `UsageCounter`, `UsageReservation`, and `NotificationOutbox`.

- [ ] Write schema tests proving provider/trial model names are absent and generic usage/outbox constraints remain.
- [ ] Run them and confirm failure while the old models still exist.
- [ ] Remove provider/trial models, add the reversible drop migration, update the expected head and tenant table fixtures.
- [ ] Remove tests dedicated to deleted Stripe/trial lifecycle behaviour and adapt hosted-AI tests to the Free-only cloud state.
- [ ] Run the backend fast suite and migration upgrade/downgrade checks.

### Task 4: Static, transparent pricing UI

**Files:**
- Modify: `frontend/src/pages/Pricing.jsx`
- Modify: `frontend/src/pages/Pricing.test.jsx`
- Modify: `frontend/src/api.js`
- Modify: `frontend/src/editions/cloud.jsx`
- Modify: `frontend/src/edition.test.jsx`

**Interfaces:**
- `Pricing` requires no API or QueryClient.
- A paid-plan CTA opens an accessible dialog containing `Payments are not available yet` and never performs a network request.

- [ ] Replace the existing pricing test with failing tests for static prices, upfront availability copy, dialog open/close, and absence of billing-management/Stripe text.
- [ ] Run the focused Vitest file and confirm the expected failures.
- [ ] Implement the static catalogue and dialog, remove billing API helpers, and rename cloud navigation to `Plans`.
- [ ] Run focused and complete local/cloud frontend tests.

### Task 5: Deployment and project documentation

**Files:**
- Modify: `deploy/cloudrun.md`
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md`
- Modify: `docs/superpowers/plans/2026-09-04-portfyl-billing-entitlements.md`
- Modify: `docs/operations/billing-verification-2026-09-05.md`

**Interfaces:**
- Active documentation contains no instruction to configure or deploy Stripe.
- Historical billing documents prominently state that the Stripe implementation was retired before activation.

- [ ] Remove payment secrets, environment variables, webhook, catalogue, and billing scheduler commands from the active Cloud Run runbook.
- [ ] Update the repository status and master plan to say paid checkout is deferred and Paddle is only a likely future provider.
- [ ] Add superseding notes to historical Workstream E documents without deleting their evidence.
- [ ] Search active code/deployment files for Stripe and trial runtime references; resolve every non-historical result.
- [ ] Run full backend tests, PostgreSQL tests when the disposable database is available, both frontend test modes, and both production builds.
