# Onboarding: connect a broker inside onboarding, with a plan gate

Date: 2026-11-14 · Status: draft for approval · Edition: cloud (local has every
capability, so the gate never shows there)

## Intent

Today a new user who picks "Connect <broker>" in onboarding gets an empty
portfolio and is thrown into Settings → Connections
(`Onboarding.jsx:30-34`). Onboarding ends abruptly, the user lands on a page
full of unrelated settings, and on the Free plan the connect call then fails
with a 403 (`broker_sync` needs Investor; Free has 0 broker connections) that
the user sees only as "Failed to connect".

The founder wants the API-key connection to be **a step of onboarding
itself**: the user stays in the onboarding frame, enters the key there, and
after a successful connection lands on the **Dashboard**. Because API sync is
a paid feature, the step must say so up front and offer the upgrade right
there, with a free alternative.

## Goals

- Picking "Connect <broker>" opens a **connect step inside onboarding**
  (same card/frame, Back returns to the choices) instead of navigating to
  Settings.
- A workspace without `broker_sync` sees, **before** being asked for a key:
  "Automatic connection is part of Investor (EUR 5.99/month)" with
  - **Upgrade to Investor** → pays → comes back to the same connect step;
  - **Import a file for free instead** → the existing import path
    (`beginImport`), when the broker has a file format.
- A workspace with `broker_sync` sees the credential form for that broker,
  with the existing how-to guide (T212ApiGuide / IBKRFlexGuide / eToro).
- On successful connect: run the first sync, then land on the Dashboard
  (`TRACKER_HOME`) with the new portfolio active.

## Non-goals

- No free trial, no "first sync free" (decided 2026-11-14: option A).
- No change to plan limits, prices or the Pricing page.
- No change to how Settings → Connections works for existing users (it keeps
  its cards; we only reuse them).
- No backend changes are expected (see Approach). If the builder finds one is
  required, it must stay minimal and go through the normal review.

## Anti-goals (would be a failure even if it "works")

- The user types an API key and only **then** learns it needs a paid plan.
- The user pays and lands on the Pricing page / Dashboard with an empty
  portfolio, having to find the connection form on their own.
- A Free user is left at a dead end with no way forward.
- Onboarding links to `/pricing` (existing test
  `OnboardingView.test.jsx:114-121` forbids it; the upgrade is in-place).

## Decisions made

- **Approach A** (founder, 2026-11-14): paid gate inside onboarding, free
  alternative is file import. **eToro is paid-only** (founder: "eToro se
  holt bude muset platit") — it has no file format, so its gated screen
  offers only the upgrade and "Choose another broker" / "Explore with sample
  data" (the existing demo choice).
- The connect step is a **step in the onboarding card, not a pop-up modal**
  (my call: the founder asked for it to feel like part of onboarding;
  a step keeps Back/stepper behaviour and works on mobile).

## Approaches considered

1. **Gate inside onboarding (chosen).** Described below. Honest, matches the
   no-trial decision, frontend-only.
2. **First sync free, automatic sync paid.** Better conversion and covers
   eToro, but needs a new one-shot backend mode, decisions about stored
   credentials, and more surface. Rejected for now.
3. **Free trial.** Rejected by an earlier product decision (no trials).

## How it works (design)

### Steps

Existing steps: `broker` (pick broker) → `choices` (connect / import / demo)
→ (`unsupported`). New step: **`connect`**, reached from `choices` when the
user clicks "Connect <broker>". It is in the URL as `?broker=<key>&step=connect`
so a reload, and the return from Stripe, come back to it. The funnel event
`ONBOARDING_STEP_VIEWED` gets the new value `"connect"`.

The `connect` step has two states, decided by the workspace's plan:

- **gated** — `broker_sync` not in capabilities. Shows the plan message, the
  upgrade action, and (if `broker.fileKind`) "Import <fileKind> for free".
- **form** — shows the broker's credential form + guide.

### Knowing the plan

Use `GET /api/billing/status` (`fetchBillingStatus`): `capabilities` includes
`broker_sync` → form, otherwise gated. It works with billing on and off
(`/api/test-plans` is unmounted when billing is on, so don't rely on it for
the gate). `billing_enabled` decides which upgrade path to use.

### Upgrade path

- **Billing off** (now): "Upgrade to Investor" calls `updateTestPlan("investor")`
  (the existing no-payment switch), refetches billing status, and the step
  turns into the form. Label it so it is clear no payment happens (reuse the
  Pricing page's test-mode wording).
- **Billing on**: the step shows the same immediate-start / 14-day withdrawal
  consent checkbox as Pricing (same text, same `consent_version`) and the
  button is disabled until it is ticked; then `startCheckout("investor")` and
  `window.location.assign(url)`.
  - Before leaving, remember the broker (`rememberIntendedBroker`) and that
    the user was on the connect step (the URL alone is lost because Stripe's
    `success_url` is hardcoded to `/pricing?checkout=success&session_id=…`).
  - On return, the user still has **no active portfolio** (see below), so
    `AppLayout` renders Onboarding at **any** path, including `/pricing`.
    Onboarding must therefore handle `?checkout=success&session_id=…` itself:
    call `confirmCheckout(sessionId)` (applies the subscription
    synchronously), strip the params, refetch billing status, and restore
    the connect step for the remembered broker. `checkout=canceled` restores
    the gated connect step with a short "Payment was cancelled" note. If
    `checkout_status` is not `complete`, show "Your payment is being
    processed" with a retry/refresh, as Pricing does.
  - Only workspace owners can check out (`workspace_owner_required`); a new
    user is always the owner of their first workspace, but show the error
    text if it happens.

### The portfolio

Do **not** create a normal portfolio when the user clicks Connect (today's
`createPortfolio`). Use the **pending-import portfolio**
(`createPendingImportPortfolio`), exactly like the import path:

- It keeps `activePortfolios` empty, so Onboarding stays mounted through the
  Stripe round-trip and any reload (`App.jsx:435`).
- `pending_portfolio()` (`backend/portfolio_activation.py`) treats a pending
  portfolio as pending **only while it is empty**; once the first sync writes
  transactions it becomes a normal active portfolio automatically.
- If the connection succeeds but the account has no transactions yet, call
  `activatePortfolio(pending.id)` before leaving. If that returns 409 "Only an
  empty pending portfolio can be activated", a sync already wrote data and the
  portfolio is active — treat it as success.
- Name: the pending portfolio is created as "My portfolio"; renaming it to the
  broker's name (as today, `uniquePortfolioName`) is the builder's call.
- `setCurrentId(pending.id)` before connecting, so the axios interceptor sends
  this portfolio's `portfolio_id`. The builder must confirm the three connect
  endpoints accept a pending portfolio (they use `require_portfolio`).

### Connect, first sync, Dashboard

On submit: connect (`connectT212` / `connectIBKR` / `connectEtoro`), then
start the first sync (`syncT212` / `syncIBKR` / `syncEtoro`) — today no card
syncs automatically after connect. Show a progress state ("Importing your
history from <broker>…"). The brokers differ (my call, from the code):

- **Trading 212**: `/sync` answers 202 at once with a cash/positions
  snapshot and hands history to the `broker_backfill` job
  (`backend/routers/broker.py:665-766`); no transactions exist yet. Do not
  wait for history: after the 202, activate the (still empty) pending
  portfolio and go to the Dashboard, where the existing snapshot positions
  and `HistoryBackfillStatus` show progress. So for T212 `activatePortfolio`
  is the **normal** path, not an edge case.
- **IBKR / eToro**: `/sync` is synchronous (`ibkr.py:769-777`,
  `etoro.py:298-330`). Wait for it with the progress state (no client
  timeout that abandons it), then activate if it wrote nothing.
- In both cases the 409 "Only an empty pending portfolio can be activated"
  on activate means data already arrived and the portfolio is active —
  success.
- `recordPortfolioDataImported("broker")`: when the IBKR/eToro sync inserted
  rows, or the T212 snapshot has at least one position (builder's call on
  the exact signal).
- Then `refetchPortfolios()`, `recordPortfolioCreated("broker")`,
  `clearIntendedBroker()`, clear the connect-step marker,
  `navigate(TRACKER_HOME)` — same navigate-before-refetch order as today.

### Resume and re-entry (my calls)

Reloads, a closed tab or the Stripe round-trip can leave the pending
portfolio already holding a live connection with no transactions
(Onboarding stays mounted). On entering the connect step, read the broker's
status for the pending portfolio (`/broker/<broker>/status`-style calls the
cards already make): if it is connected, skip the form and go straight to
"sync (if not yet) → activate → Dashboard". Never call `connect` twice.
Once the pending portfolio holds a connection, **Back / Change broker /
demo** are not offered from the connect step (one broker per portfolio; the
pending portfolio is the only one, `portfolios.py:223-225`) — the user
finishes into the Dashboard and can add more from Settings.

### Edition and the global upsell toast (my calls)

- `/api/billing/status` is mounted only in cloud (`backend/main.py:173-176`).
  Read plan capabilities through an edition-manifest function like the
  existing `fetchEditionPlanCapabilities` (`editions/cloud.jsx:29`): local
  returns "everything allowed" (no gate), cloud returns
  `fetchBillingStatus()` (capabilities + `billing_enabled` + prices).
- Onboarding's connect/sync calls pass `suppressEntitlementPrompt` so the
  global `UpgradePrompt` toast (`api.js:151-155`) never fires from them; the
  step shows its own gated state instead.
- Add `"connect"` to `onboardingSteps` in `analytics/eventContract.js:32`,
  or the funnel event is dropped.
- The pending marker keeps `kind: "csv_import"`
  (`portfolio_activation.py:16`); it is only a schema tag and
  `pending_portfolio()` does not care how the portfolio gets filled. The
  builder confirms T212 connect's `purge_demo_data` /
  `_bind_verified_account` behave on an empty pending portfolio (a test
  covers it).

### Connect-step marker lifetime (my call)

Stored next to `signupIntent` with a timestamp; cleared on finishing, on
"Import for free", on Back before connecting, and after a checkout return is
handled (success or cancel). Ignored if older than 24 h, so an abandoned
checkout never strands the user on the step.
- Connect errors show inline in the step (`role="alert"`). Note the 403
  entitlement body is top-level (`{code: "plan_upgrade_required", …}`), not
  under `detail`, so `getApiErrorMessage` shows only "Failed to connect"; if a
  gated request slips through, map `plan_upgrade_required` to the gated state.
- eToro: if `EtoroConnectionCard` reports the server has no app key
  (`configured === false`), the step says eToro connection is temporarily
  unavailable and offers the other choices.

### Reusing the forms

IBKR and eToro cards (`components/settings/IBKRConnectionCard.jsx`,
`EtoroConnectionCard.jsx`) are self-contained; the Trading 212 form is inline
in `Settings.jsx` (`ConnectionsSettings`, ~:244-297) and must be extracted
into its own component used by both Settings and onboarding. The onboarding
step needs a slimmer variant (credential fields + guide + submit; no
disconnect/status/sync-now chrome) and an `onConnected` callback. Whether
that is a `variant="onboarding"` prop on the cards or a shared inner form
component is the builder's call; Settings must look and behave exactly as
today.

### Preview and tests

- `OnboardingPreview` reuses `OnboardingView`; the new step must stay inert
  there (no API or analytics calls), as the existing preview tests require.
- Update `Onboarding.test.jsx` (broker path no longer navigates to Settings;
  new step value in the funnel), `OnboardingView.test.jsx` (connect step,
  gated vs form, still no `/pricing` link), `Settings.sections.test.jsx`
  (T212 extraction), and add tests for: gated → test-plan upgrade → form;
  checkout return (`success`, `canceled`, not complete); connect → sync →
  Dashboard; empty account → activate; 409-on-activate treated as success.
- Copy is translated into all 9 languages (`messages.test.js` enforces it).
- Follow `DESIGN.md` for the new step's look.

## Left to the builder

Component structure for the slim form, the sync wait threshold, portfolio
naming, exact copy, and how the "connect step" marker survives the Stripe
round-trip (storage key alongside `signupIntent`, or a field in it).

## Related

- Architecture: [[Onboarding and CSV import]] · [[Broker importers and sync]] · [[Billing and Stripe]]
- Code: [[hooks.useOnboardingConnect]] · [[lib.onboardingConnect]] · [[routers.broker]] · [[entitlements]] · [[pages.Onboarding]] · [[broker_connections (table)]] · [[plans]]
