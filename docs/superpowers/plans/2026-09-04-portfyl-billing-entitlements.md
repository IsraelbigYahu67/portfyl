# Portfyl Workstream E: Billing, Trial, Entitlements, and Quotas

> **Status:** Approved and implemented locally 2026-09-04. The Stripe sandbox
> and scratch Cloud Run/Neon rehearsals remain required before this workstream
> can be marked complete or billing can be enabled.
>
> **Parent specification:**
> `docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md`, especially
> sections 5, 6, 8, 9, 12, and 14.

## Goal

Implement the cloud-edition monetization boundary: a seven-day no-card Pro
trial that starts only after successful real-data activation, monthly and
annual Investor/Pro subscriptions managed through Stripe Checkout and the
Stripe Customer Portal, replay-safe subscription reconciliation, continuous
founder pricing, deterministic downgrade behavior, and server-enforced
capability/resource/usage limits.

The local edition must continue to work without Stripe configuration, network
calls, plan checks, or quotas. Tax Report and Screener remain local-only and
must still be rejected by the edition boundary before billing is considered.

## Current state and prerequisites

- Workstreams B/C/D and the technical edition boundary are complete.
- `Workspace` is the authorization and billing tenant; users reach it through
  `Membership`.
- PostgreSQL RLS is forced for every tenant table. The fast test suite uses the
  explicit `PORTFYL_TESTING=1` SQLite fixture only.
- Cloud jobs are invoked through authenticated internal Cloud Scheduler
  endpoints and protected by per-job PostgreSQL advisory locks.
- Secrets and logs already have KMS/envelope-encryption and redaction support.
- `backend/edition.py` classifies cloud features, but currently treats every
  cloud classification as edition-available; no plan enforcement exists.
- There is no Stripe SDK, billing router, subscription model, usage model, or
  pricing/upgrade UI. Migration head is `0009_audit_log`.
- Firebase login already rejects unverified e-mail identities, so a request
  context with `email_verified_at` is the minimum identity prerequisite for
  trial activation.
- Workstream A's external commercial market-data rights and product/pricing
  validation remain launch blockers. This workstream must not imply that the
  application is ready to accept public payments.

## Decisions to approve

### 1. Split edition availability from plan access

`edition.py` remains the immutable product-surface registry. A new
`entitlements.py` module owns cloud plan resolution and limits. Access is
always evaluated in this order:

```text
edition allows capability
        -> effective cloud plan allows capability
        -> resource is writable under the plan limit
        -> period usage can be atomically reserved
```

An unknown capability, plan, resource limit, price key, or usage metric fails
closed. The frontend renders the result but is never an authorization source.

### 2. Trial is an internal grant, not a Stripe subscription

The no-card trial does not create a Stripe Customer or Subscription. It is a
single internal Pro grant with explicit `started_at`/`ends_at` timestamps. It
starts only after a successful import that persists at least one real row or a
broker connection that has passed its credential test and persisted.

This avoids selecting a monthly/annual paid product before the user has made a
purchase choice, prevents a Stripe outage from breaking first-value
activation, and prevents abandoned trials from creating remote billing
objects. Stripe Checkout creates the first paid subscription when the user
chooses a plan and interval.

One trial is allowed per verified identity. The durable uniqueness key is an
HMAC-SHA256 fingerprint of the normalized verified e-mail, keyed by
`PORTFYL_TRIAL_IDENTITY_KEY`; raw e-mail is not duplicated into the trial
table. One workspace can also receive at most one trial. The fingerprint is
retained when an account is deleted only if the final privacy/retention policy
approved in Workstream F permits it; until that policy is approved, public
billing launch remains blocked.

The trial grants Pro capabilities but has its own tighter hosted-AI allowance
of 15 successful messages for the whole trial.

### 3. Stripe is authoritative for paid lifecycle; PostgreSQL is the local
projection used for request-time authorization

Checkout success redirects never grant access. Signed Stripe events are
recorded in a durable inbox by event ID and processed idempotently. Processing
retrieves the current Customer/Subscription from Stripe and projects that
canonical state into PostgreSQL, so duplicate and out-of-order events converge
to the same result.

The webhook endpoint performs signature verification against the untouched
raw request body, records only minimal event metadata, and returns promptly.
An externally invoked `billing` job retries pending inbox rows and performs a
periodic reconciliation sweep. Full event payloads, billing addresses, card
data, and invoice contents are not persisted by Portfyl.

### 4. Founder pricing is the immutable subscribed Stripe Price ID

The application has a versioned, backend-owned price catalog. Each configured
entry maps `(plan, interval, price_version)` to one immutable Stripe Price ID.
The active public generation is selected by configuration. A Subscription row
pins its original `stripe_price_id`, `price_version`, and interval for its
continuous lifetime.

Payment failure starts a 14-day grace window and does not change that pin.
Payment recovery clears the grace state. A voluntary cancellation retains the
pin only until the already-paid period ends; a later new Checkout session uses
the then-current public generation. Existing Stripe Price objects are archived
at most, never edited or deleted.

### 5. Downgrades keep data and make deterministic excess objects read-only

Downgrade and trial expiry never delete data. For count-limited resource
classes, the oldest objects by `(created_at, id)` remain writable up to the
effective limit and later objects become read-only. Reads, export, deletion,
and account-deletion workflows remain available for all objects. Creation,
updates that increase usage, automatic jobs, and paid computations are denied
server-side with stable machine-readable errors.

For aggregate limits such as active positions and transactions, imports and
manual writes preflight the final state in the same transaction. A delete or
other mutation that reduces usage is always allowed.

### 6. Application counters, not Stripe meters, enforce launch quotas

Stripe prices are fixed recurring prices. Product usage is tracked in
PostgreSQL because the initial quotas affect product access rather than the
invoice amount. Usage reservation is atomic and idempotent across Cloud Run
instances. Provider failures release a reservation; successful expensive calls
consume it exactly once.

Exact hosted-market-data quotas stay configurable and disabled until
Workstream A has approved commercial rights. The schema and enforcement API
are delivered now without representing `yfinance` as a licensed cloud source.

### 7. Billing UI uses Stripe-hosted surfaces

Portfyl owns the pricing comparison and current-plan summary. Stripe Checkout
collects payment, billing address, tax location, and optional VAT ID. Stripe's
Customer Portal owns payment-method changes, invoices, subscription switching,
and cancellation. The portal is configured for end-of-period downgrades and
cancellation. Entitlements change only after webhook/reconciliation state
arrives.

### 8. Transactional e-mail is an outbox boundary in E

E creates durable, deduplicated trial/billing notification intents for trial
activation, day three, day six, payment failure, grace expiry, and
cancellation. A small transport interface and fake transport are covered by
tests. Selecting and configuring the production e-mail vendor, templates,
consent wording, and localization remain part of the separately listed
Phase-2 lifecycle-e-mail work and are a public-launch gate; no vendor is
silently selected in this workstream.

## Canonical launch plan catalog

The backend catalog starts with the master-plan values below. `None` means no
product count limit, not an unlimited promise for variable-cost services.
Configurable high/fair-use values must have finite production configuration
before launch.

| Rule | Free | Investor | Pro | Trial override |
|---|---:|---:|---:|---:|
| Portfolios | 1 | 5 | 15 | Pro |
| Active positions | 15 | None | None | Pro |
| Transactions | 250 | None | None | Pro |
| Broker connections | 0 | 2 | 5 | Pro |
| Automatic sync | disabled | daily | every ~6 h | Pro |
| Watchlists | 1 | 5 | configured finite high limit | Pro |
| Watchlist symbols | 15 | configured finite limit | configured finite high limit | Pro |
| Alerts | 3 | 20 | 100 | Pro |
| Hosted AI successful messages | 0 | 0 (BYOK only) | 100/month | 15/trial |
| Hosted research/quotes | configured | configured | configured | configured |

The existing `alerts` classification must change from `cloud_investor` to
`cloud_free`, because the approved tier table gives Free three alerts. The
assistant surface must be split into `assistant_byok` (Investor) and
`assistant_hosted` (Pro); the current `assistant` key can remain a compatibility
alias only during the migration and must not accidentally grant hosted usage.
Options and Polymarket need endpoint-level summary versus advanced
capabilities rather than one whole-router Pro gate. Similar endpoint-level
separation applies to basic versus complete analytics, dividends, benchmarks,
and research.

## Stable interfaces

### Billing and trial models

- `BillingCustomer(workspace_id unique, stripe_customer_id unique,
  created_at, updated_at)`.
- `Subscription(public_id, workspace_id, stripe_subscription_id unique,
  stripe_price_id, plan, billing_interval, price_version, status,
  current_period_start, current_period_end, cancel_at_period_end,
  payment_failed_at, grace_ends_at, ended_at, created_at, updated_at)`.
  Historical rows remain after cancellation. PostgreSQL permits at most one
  non-ended subscription per workspace.
- `TrialGrant(public_id, workspace_id unique, activated_by_user_id nullable,
  identity_fingerprint unique, activation_kind, started_at, ends_at,
  created_at)`.
- `StripeEvent(stripe_event_id primary/unique, event_type, object_id,
  livemode, status, attempts, last_error, received_at, processed_at,
  next_attempt_at)`. No full payload.
- `BillingAction(public_id, workspace_id, actor_user_id, idempotency_key,
  action, request_fingerprint, stripe_object_id, response_url_expires_at,
  created_at)`, unique on `(workspace_id, idempotency_key)`.
- `UsageCounter(workspace_id, metric, period_start, period_end, used,
  updated_at)`, unique on `(workspace_id, metric, period_start)`.
- `UsageReservation(public_id, workspace_id, counter_id, metric, idempotency_key,
  amount, status, created_at, finalized_at)`, unique on
  `(workspace_id, metric, idempotency_key)`.
- `NotificationOutbox(public_id, workspace_id, user_id, kind,
  deduplication_key unique, payload, status, attempts, next_attempt_at,
  sent_at, last_error, created_at)`. Payload contains template variables only,
  never credentials or portfolio contents.

All workspace-owned models carry application predicates and forced RLS. The
webhook/scheduler system role may enumerate billing inbox rows only through
the same narrowly scoped background-job pattern already used in Workstream D.

### Entitlement API

`backend/entitlements.py` exposes:

- `PlanTier(FREE, INVESTOR, PRO)` and `BillingInterval(MONTH, YEAR)`.
- `EffectiveEntitlements(plan, source, effective_until, in_grace,
  cancel_at_period_end, capabilities, limits, usage)`.
- `resolve_entitlements(db, *, edition, context, now=None)`.
- `require_capability(capability_key)` as a FastAPI dependency factory.
- `require_resource_write(resource_key, resource_id=None)` for deterministic
  read-only overflow enforcement.
- `check_aggregate_limit(...)` for transaction/import final-state validation.
- `reserve_usage(...)`, `finalize_usage(...)`, and `release_usage(...)`.

Local returns an explicit unmetered local entitlement result and never queries
billing tables. Cloud defaults safely to Free if there is no active trial or
qualifying paid subscription.

### Cloud API

The cloud-only router exposes:

- `GET /api/billing/entitlements` — current effective plan, source, expiry,
  grace/cancellation state, capability keys, limits, and usage remaining.
- `GET /api/billing/prices` — public plan/interval/amount/currency metadata;
  never secret keys or arbitrary Stripe object enumeration.
- `POST /api/billing/checkout` — owner-only, CSRF-protected, accepts a catalog
  `plan`, `interval`, and an `Idempotency-Key`; returns a Stripe-hosted URL.
- `POST /api/billing/portal` — owner-only and CSRF-protected; returns a
  short-lived Stripe-hosted portal URL.
- `POST /api/billing/webhook` — cloud-only, no user session or CSRF; verifies
  `Stripe-Signature` against the raw body before inserting an inbox row.

Local OpenAPI contains none of these routes. Unknown price IDs received from
Stripe are quarantined and degrade to Free rather than being inferred from
metadata supplied by a client.

### Error contract

Plan denials are JSON responses with HTTP 403:

```json
{
  "code": "plan_upgrade_required",
  "capability": "portfolio_analytics",
  "plan": "free",
  "required_plan": "investor"
}
```

Quota/read-only variants use `quota_exceeded` or `resource_read_only` and add
`resource`/`metric`, `limit`, and `used`. They never disclose another
workspace's usage or resource existence.

## Task plan

### Implementation record (2026-09-04)

The repository implementation now includes the versioned backend catalog,
migration `0010_billing_entitlements`, forced-RLS billing/trial/usage/outbox
models, entitlement and deterministic downgrade enforcement, activation-based
trial grants, Stripe Checkout/Portal and signed webhook inbox, canonical
reconciliation and scheduler pass, atomic hosted-AI reservations, lifecycle
notification intents, cloud-only pricing/upgrade UI, secret redaction, and a
read-only Stripe catalog verifier.

Local verification completed:

- backend fast suite: **479 passed**;
- disposable PostgreSQL suite: **323 passed**, including migration
  upgrade/downgrade, forced RLS, tenancy, and concurrent final-quota/idempotency
  tests;
- frontend local edition: **136 passed** and production build succeeded;
- frontend cloud edition: **136 passed** and production build succeeded;
- local production bundle contains no pricing/billing/upgrade UI strings.

Still external and therefore deliberately not represented as complete:

- Stripe sandbox Checkout/Portal, CLI replay, test-clock dunning, cancellation,
  and v1-to-v2 resubscription rehearsal;
- scratch Cloud Run + Neon billing-scheduler OIDC/advisory-lock rehearsal;
- production transactional-email transport and onboarding CAPTCHA/App Check;
- Workstream A commercial market-data rights and the master-plan legal/tax
  launch gates.

### Task 1: Freeze the plan/price/limit configuration and tests

**Files:**

- Create `backend/billing_config.py`.
- Modify `backend/edition.py`.
- Create `backend/tests/test_billing_config.py`.
- Modify `backend/tests/test_edition.py`.
- Modify deployment environment documentation/examples.

- [ ] Write tests for exact Free/Investor/Pro limits, finite configurable
  fair-use limits, immutable unique Stripe Price IDs, current price generation,
  strict plan/interval parsing, the Free alerts correction, and split assistant
  capabilities.
- [ ] Require all Stripe secrets and price IDs only when cloud billing endpoints
  are enabled. Local startup must succeed with none of them.
- [ ] Use non-secret public amount/currency metadata for display; never derive
  access from client-supplied amount or Stripe metadata.
- [ ] Run `python -m pytest tests/test_billing_config.py tests/test_edition.py -v`.
- [ ] Commit Task 1 separately.

### Task 2: Add billing, trial, event-inbox, usage, and outbox schema

**Files:**

- Modify `backend/models.py`.
- Create `backend/alembic/versions/0010_billing_entitlements.py`.
- Modify `backend/alembic/versions/0002_tenant_rls.py` only if the migration
  helper cannot safely apply the existing policy template from the new head.
- Create `backend/tests/test_billing_schema.py`.
- Modify PostgreSQL schema/RLS/runtime-role tests.

- [ ] Write failing fast model/constraint tests and PostgreSQL tests for forced
  RLS, tenant isolation, unique trial claims, one active subscription per
  workspace, event replay uniqueness, usage uniqueness, and system-job access.
- [ ] Add explicit check constraints for plans, intervals, event/outbox states,
  positive reservation amounts, non-negative counters, and timestamp ordering.
- [ ] Ensure raw Stripe event bodies and billing/card details have no column.
- [ ] Verify upgrade/downgrade on a disposable PostgreSQL database and update
  schema snapshots.
- [ ] Commit Task 2 separately.

### Task 3: Implement the effective-entitlement engine

**Files:**

- Create `backend/entitlements.py`.
- Create `backend/tests/test_entitlements.py`.
- Modify `backend/routers/capabilities.py` only to keep edition and plan payloads
  unambiguous.

- [ ] Test local bypass with no Stripe/billing configuration or billing-table
  query.
- [ ] Test cloud Free fallback, active trial Pro access, exact trial expiry,
  active paid plans, cancellation through paid period end, 14-day `past_due`
  grace, grace expiry, paused/unpaid/canceled states, and timezone boundaries.
- [ ] Test edition-first rejection of Tax Report/Screener for every plan.
- [ ] Test every capability in the registry has one explicit minimum plan or an
  explicit local-only classification; no default allow path exists.
- [ ] Add the authenticated entitlement endpoint after the engine is green.
- [ ] Commit Task 3 separately.

### Task 4: Enforce feature gates and deterministic resource limits

**Files:**

- Modify all affected routers under `backend/routers/` (`portfolios`,
  `portfolio`, `broker`, `ibkr`, `analytics`, `benchmarks`, `watchlists`,
  `alerts`, `assistant`, `market`, `options`, `polymarket`, and dividend
  endpoints).
- Modify `backend/jobs.py` so automatic sync frequency and notification work
  re-evaluate entitlements for each workspace.
- Create `backend/tests/test_plan_enforcement.py`.
- Extend existing focused router/job tests and the PostgreSQL Alice/Bob matrix.

- [ ] Inventory every API operation against the tier table before changing
  dependencies. Record endpoint-level basic/complete/advanced capability
  mappings in the test module.
- [ ] Write tests for portfolio, transaction, active-position, broker,
  watchlist/symbol, alert, benchmark, analytics, sync, options, Polymarket,
  dividend, research, and BYOK-assistant rules.
- [ ] Prove overflow objects remain readable/exportable/deletable but cannot be
  updated or used by automatic/paid jobs after downgrade.
- [ ] Preflight CSV imports in the same transaction; a rejected import cannot
  partially replace or append data.
- [ ] Prove Alice's denial cannot reveal Bob's resource or usage, and all limits
  remain correct under concurrent PostgreSQL writes.
- [ ] Run the complete fast suite and affected PostgreSQL matrix.
- [ ] Commit Task 4 separately.

### Task 5: Activate and expire the one-time no-card trial

**Files:**

- Create `backend/trials.py`.
- Modify the successful real-data commit paths in
  `backend/routers/portfolio.py` and broker-connection routers.
- Modify `backend/routers/internal_jobs.py` and `backend/jobs.py` for trial and
  notification maintenance.
- Create `backend/tests/test_trials.py`.
- Extend import, broker, auth, audit, and PostgreSQL concurrency tests.

- [ ] Test that account creation, empty/failed import, manual transaction, and
  failed broker validation do not start the clock.
- [ ] Test that the first successful persisted real-data import or validated
  broker connection starts exactly one seven-day grant for a verified user.
- [ ] Make activation an atomic insert with uniqueness handling so concurrent
  activation attempts cannot extend or duplicate a trial.
- [ ] Test identity fingerprint normalization without exposing raw e-mail and
  ensure the HMAC key is required only for cloud trial activation.
- [ ] Emit one audit event and deduplicated activation/day-three/day-six outbox
  rows; expiry creates no deletion or mutation of customer financial data.
- [ ] Add bounded per-identity/IP activation rate limiting using the existing
  external request path. CAPTCHA/App Check integration is completed with the
  onboarding flow before public launch and is not simulated by a hidden bypass.
- [ ] Commit Task 5 separately.

### Task 6: Add the Stripe adapter, Checkout, and Customer Portal

**Files:**

- Add a pinned-compatible `stripe` dependency to backend requirements.
- Create `backend/stripe_service.py`.
- Create `backend/routers/billing.py` and mount it only in cloud.
- Create `backend/tests/test_billing_checkout.py`.
- Extend edition/OpenAPI, CSRF, ownership, logging-redaction, and audit tests.

- [ ] Define a small adapter protocol and fake implementation so no unit test
  calls Stripe.
- [ ] Test owner-only Checkout/Portal creation, unsupported plan/interval,
  duplicate idempotency keys, mismatched payload reuse, absent configuration,
  Stripe timeouts/errors, and cross-workspace probes.
- [ ] Create/reuse one Stripe Customer per workspace with server-owned metadata
  and API idempotency keys.
- [ ] Create subscription-mode Checkout only from the backend catalog, with
  automatic tax, required billing address, address update, tax-ID collection,
  one line item, safe allow-listed success/cancel URLs, and no Checkout trial.
- [ ] Configure short-lived Customer Portal sessions on demand. Portal changes
  never directly mutate local entitlements.
- [ ] Redact Stripe keys/signatures and avoid logging hosted session URLs.
- [ ] Commit Task 6 separately.

### Task 7: Build the replay-safe webhook inbox and reconciliation job

**Files:**

- Extend `backend/routers/billing.py`.
- Create `backend/billing_reconciliation.py`.
- Modify `backend/routers/internal_jobs.py`, `backend/jobs.py`, and health
  scheduler freshness configuration.
- Create `backend/tests/test_stripe_webhooks.py` and
  `backend/tests/test_billing_reconciliation.py`.
- Add PostgreSQL replay/concurrency tests.

- [ ] Verify signatures over exact raw bytes; missing/invalid signatures return
  400 without inserting an event.
- [ ] Insert event ID/type/object ID/livemode once and return 2xx for replay.
  Reject a livemode mismatch and unknown/unmapped prices fail closed.
- [ ] Process only the required subscription/invoice/customer events. Retrieve
  current remote state instead of assuming event order.
- [ ] Test duplicate delivery, two different event IDs for the same
  object/type, reversed delivery, worker crash after insert, retry backoff,
  poison quarantine, and two concurrent workers.
- [ ] Project active/trialing/past_due/paused/unpaid/canceled states, paid-period
  end, scheduled cancellation, payment failure/recovery, and price changes.
- [ ] Add a `billing` Cloud Scheduler job under the existing OIDC and advisory
  lock boundary. Reconcile remote/local active subscriptions periodically so a
  missed webhook self-heals.
- [ ] Surface inbox/reconciliation freshness in `/health` without exposing
  customer IDs.
- [ ] Commit Task 7 separately.

### Task 8: Prove founder pricing and downgrade lifecycle

**Files:**

- Extend billing service/reconciliation code and tests.
- Create `backend/tests/test_founder_pricing.py`.
- Create a Stripe catalog/bootstrap verification script under `deploy/` that
  reads configuration and verifies immutable remote Products/Prices without
  deleting or editing them.
- Update `deploy/cloudrun.md`.

- [ ] Test monthly/annual v1 subscriptions pin their exact price generation.
- [ ] Change the active catalog to v2 and prove continuous v1 subscriptions,
  including payment-failure recovery inside 14 days, keep v1.
- [ ] Prove voluntary cancellation retains access only to period end and later
  resubscription uses v2.
- [ ] Prove grace expiry downgrades to Free without deleting data and a later
  delayed paid event/reconciliation safely restores the pinned paid access.
- [ ] Document Stripe Dashboard dunning, portal end-of-period downgrade/
  cancellation, automatic-tax registration prerequisites, invoice e-mails, and
  the rule that legacy Price IDs are never edited/deleted.
- [ ] Commit Task 8 separately.

### Task 9: Enforce hosted usage quotas atomically

**Files:**

- Extend `backend/entitlements.py` and `backend/routers/assistant.py`.
- Add a cloud hosted-AI secret/config path without changing encrypted BYOK
  storage.
- Add quota hooks to the eventually licensed market-data adapter, disabled by
  default until Workstream A approval.
- Create `backend/tests/test_usage_quotas.py` and extend assistant tests.
- Add PostgreSQL concurrency tests.

- [ ] Test trial 15-total, Pro 100/calendar-month, Investor BYOK-only, Free no
  assistant, Pro BYOK not consuming hosted quota, boundary reset, and status
  payload remaining counts.
- [ ] Atomically reserve by caller idempotency key before a hosted request;
  finalize only success and release provider/validation failures.
- [ ] Prove concurrent final allowance requests cannot exceed the limit and a
  retry cannot double-charge.
- [ ] Keep all variable-cost limits finite/configurable in cloud production;
  local remains unmetered.
- [ ] Commit Task 9 separately.

### Task 10: Add pricing, billing, trial, and upgrade UI

**Files:**

- Modify `frontend/src/api.js` (billing routes are portfolio-agnostic).
- Extend `frontend/src/auth/AuthProvider.jsx` or add an entitlement provider.
- Create `frontend/src/pages/Pricing.jsx` and billing components in Settings.
- Add shared `UpgradePrompt`/read-only indicators and trial/grace banners.
- Modify cloud edition routes/navigation only; local must not import or
  advertise billing UI.
- Add focused Vitest coverage.

- [ ] Render backend price metadata and applicable-tax wording without Tax
  Report/Screener claims or the word unlimited for variable-cost features.
- [ ] Support monthly/annual selection, Checkout redirect, Portal redirect,
  current plan, trial countdown, cancellation-at-period-end, payment/grace
  warning, usage remaining, and stable denial-to-upgrade prompts.
- [ ] Show excess downgraded objects as readable/read-only and keep delete/export
  actions available.
- [ ] Treat Checkout success as pending until entitlement refetch confirms the
  paid projection.
- [ ] Test cloud routes/direct URLs and both local/cloud bundles. Prove the local
  build contains no billing/pricing messaging and still works without Stripe.
- [ ] Commit Task 10 separately.

### Task 11: Notification outbox, operations, and full verification

**Files:**

- Create `backend/notifications.py` with a provider-neutral transport.
- Extend cloud jobs/internal endpoints and focused tests.
- Update `deploy/cloudrun.md`, environment/secret setup, monitoring guidance,
  and Stripe webhook/CLI/test-clock runbook.
- Update the parent plan and `CLAUDE.md` only after all gates pass.

- [ ] Test deduplicated notification scheduling, retries, terminal failure,
  no-secret payload/log behavior, and safe operation with no production e-mail
  transport selected.
- [ ] Run the complete fast backend suite with zero unexpected skips.
- [ ] Run the complete disposable-PostgreSQL suite, including RLS, replay,
  quota concurrency, and migration downgrade/upgrade.
- [ ] Run all frontend tests plus local and cloud builds.
- [ ] Use a Stripe sandbox, Stripe CLI webhook forwarding, and test clocks to
  verify Checkout, paid activation, monthly/annual plans, duplicate/reversed
  events, portal change, failed payment, recovery inside grace, grace expiry,
  cancellation, and resubscription to a new price generation.
- [ ] Rehearse the cloud `billing` scheduler endpoint with OIDC and advisory-lock
  contention against a non-production Cloud Run + disposable Neon deployment.
- [ ] Confirm logs contain no Stripe API key, webhook secret/signature, hosted
  session URL, customer e-mail/address, card data, or full webhook payload.
- [ ] Record exact test counts and external rehearsal evidence.
- [ ] Mark Workstream E complete only when all definition-of-done items below
  pass; production payment acceptance remains blocked by the master-plan launch
  gates outside E.
- [ ] Commit Task 11 separately.

## Definition of done

- [ ] Local starts, builds, and passes tests with no Stripe/trial configuration
  and no billing routes or UI.
- [ ] Cloud defaults to Free and enforces every capability/resource/usage rule
  on the backend.
- [ ] Tax Report and Screener are rejected before entitlement evaluation and
  remain absent from cloud OpenAPI, routes, navigation, pricing, and bundles.
- [ ] Exactly one verified-identity trial starts only after successful real-data
  activation, lasts seven days, grants Pro except the 15-message trial AI cap,
  and expires without deleting data.
- [ ] Checkout supports configured monthly and annual Investor/Pro prices;
  Portal supports billing history, payment details, plan changes, and
  end-of-period cancellation.
- [ ] Checkout redirects cannot grant access; only reconciled signed Stripe
  state can grant paid access.
- [ ] Duplicate, out-of-order, delayed, and concurrent Stripe events converge
  without duplicating/corrupting subscription state.
- [ ] A continuous subscription keeps its immutable price generation through
  renewal and the 14-day failed-payment grace; post-cancellation resubscription
  uses the current generation.
- [ ] Downgrade/trial expiry retains all data, makes deterministic excess
  objects read-only, and keeps delete/export available.
- [ ] Hosted usage reservations cannot exceed quotas or double-charge retries
  under real PostgreSQL concurrency.
- [ ] Billing/trial mutations are auditable; secrets, signatures, hosted URLs,
  webhook payloads, and private billing details are absent from logs and app
  responses except the one-time redirect URL returned to its authenticated
  initiator.
- [ ] Complete backend, PostgreSQL, and frontend suites and both edition builds
  pass; sandbox Stripe and scratch-cloud rehearsals are recorded.

## External implementation references

- Stripe subscriptions and lifecycle webhooks:
  https://docs.stripe.com/billing/subscriptions/webhooks
- Stripe no-payment-method trials (used as policy background; Portfyl's trial
  grant is intentionally internal):
  https://docs.stripe.com/billing/subscriptions/trials
- Stripe webhook signature, duplicate, retry, and event-order requirements:
  https://docs.stripe.com/webhooks
- Stripe idempotent requests:
  https://docs.stripe.com/api/idempotent_requests
- Stripe Customer Portal:
  https://docs.stripe.com/customer-management/integrate-customer-portal
- Stripe automatic tax in Checkout:
  https://docs.stripe.com/tax/checkout
