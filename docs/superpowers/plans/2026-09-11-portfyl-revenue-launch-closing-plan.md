# Portfyl → Revenue-Generating SaaS: Consolidated Closing Plan

**Status date:** 2026-09-11

**Relationship to existing docs:** This is not a new spec — it is a synthesis.
Portfyl already has an unusually thorough paper trail spread across five
documents:

- `docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md` — the
  master spec (market research, tier design, architecture, go/no-go
  checklist). **Read this first for the "why."**
- `docs/superpowers/plans/2026-09-05-portfyl-plans-without-payments.md` +
  `docs/superpowers/specs/2026-09-05-portfyl-plans-without-payments-design.md`
  — records that Stripe was built, verified (803 backend tests), and then
  **deliberately retired before activation** on 2026-09-05. This was a
  sequencing decision ("don't wire a payment provider before the legal/data
  groundwork exists"), not a technical failure. Nothing here needs to be
  "fixed" — it needs a provider decision and a fresh integration.
- `docs/superpowers/plans/2026-09-07-portfyl-public-trust-compliance.md` +
  `docs/compliance/private-test-legal-status.md` (**last reviewed
  2026-09-11**) — the authoritative, current public-launch legal gate. Treat
  the checklist in that file as ground truth over anything below that
  conflicts with it.
- `docs/research/market-data-vendor-requirements-2026-09-07.md` — a
  ready-to-send RFI package (shortlist: EODHD, Twelve Data, Tiingo; a drafted
  but unsent enquiry email) for commercial market-data rights.

This document's job: pull those five threads plus the engineering/ops reality
(verified 2026-09-11 by direct code inspection) into **one ordered sequence of
physical next actions**, distinguishing what needs an engineer from what only
needs the founder (you) to make a decision, sign a contract, or send an email.

## 0. TL;DR — what is actually stopping money from arriving today

Nothing technical. The entitlement/plan-tier engine
(`backend/plans.py`, `backend/entitlements.py`) already enforces Free /
Investor / Pro limits correctly and is provider-neutral by design. The five
real blockers, in the order they naturally unlock each other, are:

1. **No legal entity/controller identity is on file** — blocks publishing any
   privacy notice, ToS, or invoice.
2. **No commercial market-data licence** — blocks legally charging for
   anything that touches fundamentals/prices for paid tiers (current
   `yfinance` path is personal/research-use only).
3. **No payment provider is chosen or integrated** — Stripe code was retired;
   Paddle is only a "likely" candidate, never decided.
4. **No public legal pages exist** (ToS/Privacy/Subprocessors/Support/Security)
   and no Czech counsel review has happened.
5. **No paying-customer support/observability surface exists** — no error
   tracking, no status page, no support channel beyond one personal inbox.

Everything else (CI, unified beta invites, lifecycle emails, market
validation) matters but doesn't block the first euro from landing — it
blocks *safely scaling past a handful of founder-approved testers*.

## 1. Confirmed current state (verified 2026-09-11)

**Done and solid:**
- Multi-tenant Postgres foundation, forced RLS, Firebase identity, UUID
  public IDs, encrypted secrets, external Cloud Scheduler jobs — Workstreams
  B/C/D (done, per project `CLAUDE.md` and dated plan docs).
- Edition boundary (`backend/edition.py`) **and** a full Free/Investor/Pro
  plan-tier engine (`backend/plans.py`, `backend/entitlements.py` — including
  an idempotent `UsageCounter`/`UsageReservation` quota system). This is
  more complete than most pre-revenue SaaS codebases get; it's genuinely
  ready to be wired to a real payment provider without redesign.
- Unified onboarding, duplicate-aware CSV import with 24h undo.
- Production ops maturity: Neon PITR restore drill, dependency audit,
  credential drills, uptime/dependency/5xx/Scheduler-error monitoring with a
  real alert-delivery test, an incident-response process **and** a completed
  tabletop rehearsal (`docs/operations/incident-tabletop-2026-09-09.md`).
- `portfyl.com` public marketing landing (CZ/EN/DE) is live in production;
  the actual app at `app.portfyl.com` is double-gated (Cloudflare Access
  exact-email allowlist + application-level `beta_invites` table) for a
  private, invite-only, **free, no-payment** test.
- A private-test legal compliance record
  (`docs/compliance/private-test-legal-status.md`) with a named, dated
  public-launch gate checklist — this is the single most load-bearing
  document for everything in §2 below.
- A ready-to-send commercial market-data RFI package with a vendor shortlist
  and drafted enquiry email, deliberately left unsent pending your say-so.

**Done since this plan was first written (2026-09-11, same day):**
- CI (`.github/workflows/ci.yml`): fast backend suite, Postgres/RLS
  integration matrix, frontend Vitest × 2 editions, both production builds.
  All four verified green locally end-to-end. Fixing this also surfaced and
  fixed a real pre-existing test-isolation bug
  (`backend/tests/postgres/test_rate_limit_postgres.py` left the shared test
  database one migration behind head after its own downgrade/upgrade
  round-trip) that would have made the new CI order-dependently flaky from
  day one.
- A Stripe-reuse assessment for §5.1's decision, appended to
  `docs/operations/billing-verification-2026-09-05.md`: roughly 90% of the
  retired implementation (schema, entitlements wiring, trial logic, the
  already-tested founder-price-lock mechanism) is provider-agnostic; only the
  ~350-line Stripe gateway module is provider-specific.
- `deploy/manage-beta-tester.ps1` now writes `beta_invites` **and** the
  Cloudflare Access policy from one invocation (falls back to the old
  DB-only behavior with a warning if `CLOUDFLARE_ACCOUNT_ID`/
  `CLOUDFLARE_API_TOKEN` aren't set). The add/remove/dedup logic is unit
  -verified; the live Cloudflare API round-trip is not yet — run it once with
  `-WhatIf`, then once for real on a throwaway address, before trusting it.

**Deliberately not done (by design, not by accident):**
- Payment/checkout/webhooks/subscriptions/trials — Stripe was built, tested,
  and retired 2026-09-05. Paddle is the leading candidate but not chosen.
- Public ToS/Privacy/Subprocessors/Support/Security pages — deliberately
  gated behind the legal-entity and counsel-review blockers in
  `private-test-legal-status.md`, not forgotten.
- Any error tracking (Sentry or equivalent), status page, support-ticket
  tool, or admin dashboard for tenant/subscription management.
- Any transactional/lifecycle email provider (welcome, trial-ending,
  payment-failed, receipt). `backend/notifications.py` only defines a
  generic `send()` protocol — no SMTP/SendGrid/Postmark/Resend backend is
  wired up.
- Workstream A external validation: 10-15 target-user interviews and
  pricing validation — pure business-development work, not started.

## 2. The critical path to legally taking money (do in this order)

Each step names the concrete next physical action and who does it.

### 2.1 Register/confirm the controller identity (you)
`private-test-legal-status.md`'s public-launch gate item 1 is unchecked:
*"Confirm the controller's full legal name, legal form, postal address,
registration identifiers (if any), and service address."* Nothing legal can
be published until this exists. Decide now: sole trader (OSVČ) vs s.r.o. —
this also determines your VAT-registration threshold and how much of the
EU VAT/OSS burden a Merchant-of-Record payment provider needs to absorb for
you (see §5.1). This has no engineering dependency; it blocks everything
else in this section.

### 2.2 Get the commercial market-data licence in writing
The package is done — send it. `docs/research/market-data-vendor-requirements-2026-09-07.md`
has the exact drafted (unsent) enquiry text and a vendor response matrix.
- [ ] Send the enquiry to **EODHD** and **Twelve Data** (the doc's
      recommendation); include **Tiingo** only for European-fundamentals
      comparison.
- [ ] Get written answers against every row of the "Exact rights Portfyl
      needs in writing" table — a "standard terms" or blank answer does not
      close this gate.
- [ ] Re-check the €4.99/€7.99 price points once quotes land — the doc
      explicitly flags they may be below the viable floor once
      exchange/per-user/commercial-display fees are added. Adjust price,
      feature scope, or delay level (not the licensed rights) if so.
- [ ] Once a vendor is contracted, replace `yfinance` calls that serve
      **cloud paid-tier** features (fundamentals, DCF inputs, calendars,
      benchmarks) with the licensed feed. Local edition can keep `yfinance`
      since it's the owner's personal, non-commercial use.

### 2.3 Choose and integrate a payment provider
Open decision, not yet made (§5.2 below has the tradeoffs).
- [x] Reuse assessment of the retired Stripe implementation done — see the
      2026-09-11 section of `docs/operations/billing-verification-2026-09-05.md`.
      ~90% (schema, entitlements wiring, trials, founder-price-lock) is
      reusable regardless of which provider wins; only the gateway module
      is provider-specific.

Once the provider decision (§5.1) is made:
- [ ] Build checkout, webhook handling (signature verification +
      idempotency — this is an explicit unchecked go/no-go item in the
      master spec), subscription lifecycle (create/upgrade/downgrade/cancel),
      and trial-expiry downgrade behaviour on top of the **existing**
      `plans.py`/`entitlements.py` — do not redesign those, they're
      provider-neutral by construction.
- [ ] Implement the founder-price-lock mechanism from the master spec (early
      continuously-subscribed customers keep their signup price) as an
      actual stored attribute on the subscription record, not just a promise
      in copy.
- [ ] Add billing-recovery/dunning handling (payment-failed retries, grace
      period, forced downgrade on exhaustion) — flagged open in master spec
      Phase 2.
- [ ] Retire the `/api/test-plans` private-tester entitlement switch
      (`backend/routers/test_plans.py`) from any public-facing path once
      real checkout exists — keep it only as an internal QA tool, and make
      sure it can no longer silently grant paid entitlements to a real
      customer workspace.
- [ ] Wire a transactional email provider (Postmark or Resend are simplest
      for a solo operator) for receipts, payment-failed notices, and
      trial-ending warnings — there is currently no such integration
      anywhere in the codebase.

### 2.4 Publish the legal pages
`docs/superpowers/plans/2026-09-07-portfyl-public-trust-compliance.md` Task 4
already lists the exact files to create
(`frontend/src/pages/{Privacy,Terms,Subprocessors,Support,Security}.jsx` from
one shared `frontend/src/legal/trustContent.js` content source) and the exact
gate: *"Obtain and record the controller identity, working contacts, approved
legal bases, retention values, provider regions/DPA links, and reviewed legal
copy"* before writing a single test or line of that code. In practice:
- [ ] Finish §2.1 (controller identity) and §2.2 (data vendor + its DPA/SCC
      terms) — those feed directly into this page's content.
- [ ] Get qualified Czech legal review of the privacy notice and consumer
      terms (`private-test-legal-status.md` explicitly requires this before
      any paid offering — EU distance-selling and consumer pre-contract
      information rules apply once money changes hands).
- [ ] Decide and implement the minor/child access model
      (`private-test-legal-status.md` §"Children and minors" — Czech Act
      No. 110/2019 Coll. §7 sets a 15-year consent threshold if you rely on
      consent for a minor; decide now whether under-18 signup is even
      offered at first launch to sidestep this entirely).
- [ ] Only then implement and ship the pages, gated behind the same review
      process the doc already defines.

### 2.5 Flip the pricing page live and widen access
Only after 2.1-2.4:
- [ ] Replace the current comparison-only `Pricing.jsx` dialog ("payments
      are not available yet") with real checkout CTAs.
- [ ] Widen `beta_invites`/Cloudflare Access from named private testers
      toward the Phase 4/5 rollout the master spec already defines (see §4).

## 3. Parallel/supporting workstreams (not blocking first revenue, but block *safely scaling* it)

These can run alongside §2, roughly in priority order:

1. ~~**CI/CD**~~ — done, see above. Note the workflow only runs on push/PR to
   `main`; nothing in this session pushed it there yet.
2. **Support & observability for paying customers** — add error tracking
   (Sentry is the standard choice), a public status page, a real support
   channel beyond the founder's personal Gmail (a shared inbox or a
   lightweight helpdesk), and an internal admin view for looking up a
   tenant's subscription/plan state without a database console. None of
   this exists today (verified by direct grep — zero Sentry/APM SDK, zero
   support-ticket integration).
3. ~~**Unify the beta-invite mechanism.**~~ — done, see above. Still needs one
   supervised live test against the real Cloudflare API before relying on it
   for a real invite/revoke.
4. **Workstream A external validation** — schedule the 10-15 target-user
   interviews and pricing validation the master spec's §9 still marks open.
   This can and should run *before* finalizing 2.3's exact price points,
   since the vendor-quote outcome in §2.2 already threatens the headline
   €4.99/€7.99 prices — validate willingness-to-pay at the *real* cost
   basis, not the aspirational one.
5. **Unit economics** — once §2.2's data-vendor cost and Cloud
   Run/Neon per-tenant hosting cost are both known numbers, build the actual
   LTV/CAC/margin model. The master spec's go/no-go checklist has this as an
   explicit unchecked item; it should gate whether Free-tier limits are
   generous enough to be a loss leader or need tightening.
6. **Retention/backup policy review for production** — the private-test PITR
   window (6 hours) and retention schedule are explicitly scoped to the
   *private test only*; `private-test-legal-status.md` says the public
   adequacy of these settings is still an open review item, not something to
   silently carry into GA.

## 4. Mapped against the master spec's phased rollout (§10)

| Phase | Spec status (2026-09-01, as amended) | What's left |
|---|---|---|
| Phase 0 — validation & licensing | Unchecked | §2.2 (data licence), Workstream A interviews (§3.4) |
| Phase 1 — SaaS foundation | ✅ Done | Nothing — this is the tenancy/RLS/edition work, verified complete |
| Phase 2 — monetization & onboarding | Plan/entitlement/onboarding ✅; lifecycle emails, billing recovery, privacy/terms/support surfaces ❌ | §2.3 (emails, dunning), §2.4 (legal pages) |
| Phase 3 — paid value & trust | Unchecked | Depends entirely on §2.3 (real billing) landing first |
| Phase 4 — private beta | Mostly unchecked except restore drill | §3.3 (unify invites), gather usage evidence once real testers are paying-eligible |
| Phase 5 — public founder launch | Unchecked | Everything above, plus §2.5 |

The go/no-go checklist (master spec §14) has ~11 of 17 items checked; the
remaining six map directly onto: written market-data rights (§2.2), webhook
safety (§2.3), trial-expiry behaviour (§2.3), founder-pricing subscription
tests (§2.3), privacy/terms/support/cancellation flows (§2.4), and validated
unit economics (§3.5).

## 5. Open decisions that need you, not an engineer

### 5.1 Payment provider: Paddle vs. re-adopting Stripe
- **Paddle** acts as Merchant of Record: it handles EU VAT/OSS registration,
  invoicing, and tax remittance on your behalf, at a materially higher
  per-transaction fee. This is almost certainly *why* the master spec names
  it as the likely choice for a solo Czech-based founder — it removes a real
  legal/admin burden, not just an integration preference.
- **Stripe** is cheaper per transaction but makes *you* the merchant of
  record: you'd need to register for EU VAT OSS yourself, issue compliant
  invoices, and handle tax remittance — on top of everything in §2.1/§2.4.
  The retired implementation (commit `230338d`, 803 tests passing) is a real
  asset if you go this way; it wasn't abandoned for a technical reason.
- Recommendation: unless you already have (or are getting) an accountant
  comfortable running EU OSS VAT for a micro-SaaS, Paddle's MoR model is the
  lower-total-effort path for a one-person operation. Confirm this against
  your actual accounting setup before committing engineering time.

### 5.2 Legal entity type (OSVČ vs s.r.o.)
Affects liability exposure, VAT registration threshold, and how invoices are
issued. This should be settled with a Czech accountant/lawyer before §2.1 is
closed, since it's also a prerequisite for the privacy-notice controller
identity.

### 5.3 Sequencing: charge before or after Workstream A interviews?
The master spec's pricing (€4.99/€7.99) is explicitly an unvalidated
hypothesis, and §2.2's vendor quotes may force a price change anyway. Running
the 10-15 user interviews (§3.4) in parallel with §2.1-2.2, and finalizing
prices only once both the interviews and the vendor quotes are in, avoids
publishing a price you have to walk back post-launch.

### 5.4 How wide to open the private beta before flipping on payments
Current beta is capped at named individual testers. Decide a target beta
size and duration (the RFI doc assumed 20-50 users) before widening access —
this number also directly affects what commercial tier a market-data vendor
quotes you.

## 6. What's left, in order (updated 2026-09-11, after CI/Stripe-review/beta-invite work)

Everything an engineer/agent could do without a founder decision or an
external party is now done (§1's "Done since this plan was first written").
Everything below is yours — see also the chat message this section
accompanies for the same sequence with less cross-referencing.

1. **Decide legal entity type** (OSVČ vs s.r.o., §5.2) and start
   registration. Longest lead time of anything on this list — start first,
   ideally with a Czech accountant.
2. **Send the two market-data RFI emails** (§2.2) to EODHD and Twelve Data —
   the text is already written in
   `docs/research/market-data-vendor-requirements-2026-09-07.md`. A
   five-minute action with a multi-week reply lag — send today, in parallel
   with #1.
3. **Schedule 3-5 Workstream A user interviews** (§3.4) — also long lead
   time, and directly informs whether the €4.99/€7.99 prices survive contact
   with reality once #2's quotes land.
4. **Decide Paddle vs. Stripe** (§5.1) — the reuse assessment you need for
   this is already written; it's now purely your call on VAT/OSS
   administrative burden vs. per-transaction fee.
5. Once #1 and #2 have real answers: **finish the legal pages** (§2.4) with
   a Czech lawyer, then **build the payment integration** (§2.3) against
   whichever provider #4 chose.
6. **Run the one live-credential smoke test** the beta-invite script and CI
   both still need: a real `-WhatIf` then real invite/revoke against
   Cloudflare, and a push of `.github/workflows/ci.yml` to `main` so it
   actually starts gating PRs.
7. Only after 1-6: flip the pricing page live and widen beta access (§2.5).
