# Onboarding Broker Connect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "Connect <broker>" in onboarding opens a connect step inside the onboarding card. The step gates on the Investor plan up front (with an in-place upgrade and a free file-import alternative), takes the API credentials, runs the first sync into the pending-import portfolio and lands on the Dashboard.

**Architecture:** This is a frontend-only change. The backend task only pins the existing contract with tests. A pure `ConnectStep` view renders inside `OnboardingView`, so the preview import-graph guard keeps holding. A `useOnboardingConnect` hook owns the plan check, the upgrade, the checkout return, connect → first sync → activate, and resume. `Onboarding.jsx` wires the hook to the URL (`?broker=<key>&step=connect`), to localStorage (the connect-step marker) and to analytics. The credential fields and key guides move into shared pure modules that both Settings and onboarding render.

**Tech Stack:** React 18, react-router-dom 7, @tanstack/react-query, axios, Vitest + Testing Library. The backend test uses pytest on the fast SQLite suite.

**Spec:** `docs/superpowers/specs/2026-11-14-onboarding-broker-connect-design.md`

## Global Constraints

- No free trial and no "first sync free". Plan limits, prices and the Pricing page do not change.
- Settings → Connections must look and behave exactly as today. Its existing tests pass unchanged.
- Onboarding never links to `/pricing`. The test `OnboardingView.test.jsx` "never links to pricing on any step" must also cover the connect step.
- eToro is paid-only. Its gated screen offers the upgrade, "Choose another broker" and "Look around with sample data (free)".
- Use the pending-import portfolio (`createPendingImportPortfolio`), never `createPortfolio`, for the broker path. It keeps its server name ("My portfolio"); no rename (decision for the spec's "builder's call").
- `OnboardingView.jsx` and everything it imports must never reach `src/api`, `src/App`, `src/analytics`, axios or firebase. `OnboardingPreview.test.jsx` walks that graph.
- Connect and sync calls from onboarding pass `suppressEntitlementPrompt: true`, so the global `UpgradePrompt` toast never fires from them.
- Billing on: reuse Pricing's consent sentence verbatim: "I want my subscription to start immediately. I understand that once it starts I lose my 14-day right of withdrawal for this digital service." The Upgrade button stays disabled until the box is ticked. The server stamps `consent_version` (`CHECKOUT_CONSENT_VERSION = "2026-10-28"`). The client sends none.
- Billing off: the upgrade calls `updateTestPlan("investor")`. It reuses Pricing's test-mode strings "Free plan switching during private testing" and "Use {plan} for testing".
- The connect-step marker expires after 24 h (`CONNECT_STEP_TTL_MS = 86_400_000`).
- All user copy is a double-quoted literal in `t("…")`. Every new string is translated in all 8 dictionaries (`cs de es fr it nl pl pt`). Strings that are no longer used are deleted from them.
- Follow `DESIGN.md`: tokens only (no hex, no legacy color classes), `card`, `btn-primary`/`btn-ghost`, 44 px touch targets.
- No change under `backend/alembic/`, the `requirements*` files or `package.json`.

## Review Focus

1. **A reload or closed tab after connect succeeded but before Dashboard.** Expected: the step re-opens, reads the broker status, never shows the form again and never calls `connect` twice. It syncs only if `last_synced_at` is empty, then activates and goes to the Dashboard. Pinned in Task 6 (`resumes a connected pending portfolio without connecting again`).
2. **Stripe returns to `/pricing?...` while the user has no active portfolio.** Expected: Onboarding (rendered at `/pricing` by `AppLayout`) moves to `/onboarding` with the params kept, confirms the session and reopens the connect step for the remembered broker. Pinned in Task 7 (`moves a checkout return from /pricing to the connect step`) and Task 6 (`confirms a successful checkout and shows the form`).
3. **A gated request slips through** (the plan changed in another tab, or a stale plan was cached) and connect returns the flat 403 `{code: "plan_upgrade_required"}`. Expected: the gated state, not "Failed to connect", and no toast. Pinned in Task 6 (`turns a plan_upgrade_required connect into the gated state`).
4. **IBKR or eToro sync writes rows, so activate answers 409** "Only an empty pending portfolio can be activated". Expected: success and the Dashboard, not an error. Pinned in Task 6 (`treats 409 on activate as success`) and in the backend contract in Task 1.
5. **The eToro server has no app key.** Expected: "temporarily unavailable" with the other choices, never a dead form. This covers both `status.configured === false` (pending portfolio exists) and connect answering 503 (no pending portfolio yet). Pinned in Task 6 (`shows eToro unavailable on 503`) and Task 5 (`unavailable` rendering).

---

## Before you start (orchestrator, once)

Work happens in the existing worktree `C:\Users\tomzo\claude\ptf\portfyl-onboarding-connect`, on branch `feat/onboarding-broker-connect`.

- [ ] Fast-forward to main: `git -C C:/Users/tomzo/claude/ptf/portfyl-onboarding-connect merge --ff-only main`. Expected: the branch moves from `0765cfb` to main's head (`137f520` or later).
- [ ] Commit the spec and this plan: `git add docs/superpowers/specs/2026-11-14-onboarding-broker-connect-design.md docs/superpowers/plans/2026-11-15-onboarding-broker-connect.md && git commit -m "docs(onboarding): broker connect spec and plan"`.
- [ ] Give each task of a parallel wave its own worktree off the integration branch: `git worktree add ../portfyl-obc-t<N> -b feat/onboarding-broker-connect-t<N> feat/onboarding-broker-connect`. After review, merge each into `feat/onboarding-broker-connect` and remove it. Run `npm ci` in each new worktree's `frontend/`.

**Waves** (tasks in one wave touch disjoint files):

| Wave | Tasks | Depends on |
|---|---|---|
| 1 | Task 1 (backend test), Task 2 (api + lib), Task 3 (edition manifests), Task 4 (shared forms) | — |
| 2 | Task 5 (ConnectStep view), Task 6 (hook) | 5 ← 4; 6 ← 2, 3 |
| 3 | Task 7 (Onboarding page wiring) | 5, 6 |
| 4 | Task 8 (translations, full verification, browser check) | all |

`src/i18n/messages.test.js` fails with "missing" keys from Task 4 until Task 8. Tasks 1–7 therefore run only their own test files, never the full `npm test`. Task 8 owns all 8 dictionaries, which are a hotspot.

---

### Task 1: Backend contract test — broker connect into a pending portfolio

The spec expects no backend change. This task proves it. If any assertion fails, stop and report: the fix must be minimal and reviewed separately.

**Files:**
- Create: `backend/tests/test_onboarding_broker_connect.py`

**Interfaces:**
- Consumes (existing):
  - `portfolio_activation.set_pending_portfolio` and `pending_portfolio(db, workspace_id, *, clean_stale=False, require_empty=True)`
  - The router functions for `POST /api/portfolios/pending-import`, `POST /api/portfolios/{id}/activate`, `GET /api/portfolios` and `POST /api/broker/trading212/connect`
  - The T212 client stubbing used by `tests/test_broker.py::TestDemoCleanupOnConnect`, plus the pending setup from `tests/test_portfolio_activation.py`
- Produces: nothing other tasks import.

- [ ] **Step 1: Write the tests**, calling router functions directly as `tests/helpers.py` does:
  - `test_t212_connect_accepts_empty_pending_portfolio`
    - Setup: create a pending portfolio through the pending-import router function, then connect T212 into it with a stubbed valid key.
    - Assert the `BrokerConnection.portfolio_id` equals the pending portfolio.
    - Assert `pending_portfolio(db, ws)` still returns it (no transactions). The name is still `"My portfolio"`, and `purge_demo_data` left it intact.
  - `test_activate_after_connect_without_transactions_succeeds`
    - Setup: as above, then activate.
    - Assert the response `activation_state == "active"`.
    - Assert `pending_portfolio(db, ws, require_empty=False) is None`.
  - `test_activate_after_broker_rows_conflicts_and_listing_reports_active`
    - Setup: a pending portfolio plus one `Transaction(source="ibkr", ...)` row.
    - Assert activate raises `HTTPException` with `status_code == 409` and `detail == "Only an empty pending portfolio can be activated"`.
    - Assert the portfolio list entry for it has `activation_state == "active"`.
- [ ] **Step 2: Run** `cd backend && python -m pytest tests/test_onboarding_broker_connect.py -v`. Expected: 3 passed. They pass on first run because they pin existing behaviour; a failure is a finding, not a red step.
- [ ] **Step 3: Commit** `test(onboarding): pin broker connect into a pending portfolio`

---

### Task 2: API options and pure onboarding-connect helpers

**Files:**
- Modify: `frontend/src/api.js` (broker functions, about lines 353–391)
- Create: `frontend/src/lib/onboardingConnect.js`
- Test: `frontend/src/api.brokerRequests.test.js` (extend) and `frontend/src/lib/onboardingConnect.test.js`

**Interfaces:**
- Produces, in `api.js`:
  - Each connect/sync function gets a trailing options object, read **by name only**. An event or mutation variable passed by mistake is then ignored. The functions:
    - `connectT212(apiKey, apiSecret, { suppressEntitlementPrompt = false } = {})`
    - `syncT212({ suppressEntitlementPrompt = false } = {})`
    - `connectIBKR(flexToken, queryId, { suppressEntitlementPrompt = false } = {})`
    - `syncIBKR({ suppressEntitlementPrompt = false } = {})`
    - `connectEtoro(userKey, { suppressEntitlementPrompt = false } = {})`
    - `syncEtoro({ suppressEntitlementPrompt = false } = {})`
  - Each passes `{ suppressEntitlementPrompt }` as the axios request config. Existing callers are unchanged.
- Produces, in `lib/onboardingConnect.js` (no imports from `api`, `App` or `analytics`):
  - `CONNECT_STEP_KEY = "portfyl_onboarding_connect"` and `CONNECT_STEP_TTL_MS = 86_400_000`
  - `rememberConnectStep(brokerKey: string, now = Date.now()): void` stores `JSON.stringify({ broker, at: now })`. It works only for a supported broker with `api: true` and swallows storage errors.
  - `connectStepBroker(now = Date.now()): string | null` returns the stored broker key. It removes the entry and returns null when it is invalid, unparseable, not an API broker, or older than the TTL.
  - `clearConnectStep(): void`
  - `readCheckoutReturn(searchParams: URLSearchParams): { outcome: "success" | "canceled", sessionId: string | null } | null`
  - `isPlanUpgradeRequired(error): boolean` checks `status === 403 && data.code === "plan_upgrade_required"` on a top-level `data`.
  - `apiErrorCode(error): string | null` returns `error?.response?.data?.detail?.code ?? null`, the billing errors' shape.
  - `syncImportedData(brokerKey, result): boolean` per broker:
    - `trading212`: `result.snapshot.positions > 0`
    - `ibkr`: `result.ledger.imported > 0`
    - `etoro`: `result.imported > 0`
    - Missing fields count as 0.

- [ ] **Step 1: Write failing tests**
  - In `api.brokerRequests.test.js`, following the existing `vi.spyOn(api, "post")` pattern:
    - `it("passes suppressEntitlementPrompt on onboarding connect and sync")`: `connectT212("k", "s", { suppressEntitlementPrompt: true })` → `post` called with `("/broker/trading212/connect", { api_key: "k", api_secret: "s" }, { suppressEntitlementPrompt: true })`. The same for `syncIBKR({ suppressEntitlementPrompt: true })` → `("/broker/ibkr/sync", <existing body>, { suppressEntitlementPrompt: true })`.
    - `it("ignores a non-options argument")`: `syncEtoro({ type: "click" })` → config `{ suppressEntitlementPrompt: false }`.
  - In `onboardingConnect.test.js`:
    - `remembers an API broker and reads it back`
    - `ignores a file-only broker` (`"xtb"` → null)
    - `expires the marker after 24 h`: write at `now = 0`, read at `86_400_001` → null and the key removed
    - `drops an unparseable marker`
    - `reads a success and a canceled checkout return`: `?checkout=success&session_id=cs_1` → `{ outcome: "success", sessionId: "cs_1" }`, and `?checkout=canceled` → `{ outcome: "canceled", sessionId: null }`
    - `ignores unknown checkout values`: `?checkout=weird` → null
    - `recognizes the flat entitlement 403`: also `false` when the code sits under `detail`
    - `reads a billing detail code`: `{ response: { data: { detail: { code: "workspace_owner_required" } } } }` → `"workspace_owner_required"`
    - `tells whether the first sync imported data`: one case per broker plus `{}` → false
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/api.brokerRequests.test.js src/lib/onboardingConnect.test.js`. Expected: FAIL (module missing, extra arg not passed).
- [ ] **Step 3: Implement** the signatures above.
- [ ] **Step 4: Run** the same command, plus `npx vitest run src/components/settings src/pages/Settings.sections.test.jsx src/hooks/useT212Sync.test.jsx`. Expected: all PASS.
- [ ] **Step 5: Commit** `feat(onboarding): connect-step marker and broker request options`

---

### Task 3: Edition manifest — onboarding plan

`fetchEditionPlanCapabilities` reads `/api/test-plans`, which is unmounted once billing is on. The gate must read `/api/billing/status` instead (spec "Knowing the plan").

**Files:**
- Modify: `frontend/src/editions/cloud.jsx` and `frontend/src/editions/local.jsx`
- Test: `frontend/src/edition.test.jsx`

**Interfaces:**
- Produces `fetchEditionOnboardingPlan(): Promise<OnboardingPlan>` in both manifests.
  - `OnboardingPlan` has the shape `{ brokerSync: boolean, billingEnabled: boolean, canManageBilling: boolean, investorMonthlyCents: number | null }`.
  - Cloud maps `fetchBillingStatus()`:
    - `brokerSync = capabilities.includes("broker_sync")`
    - `billingEnabled = !!billing_enabled`
    - `canManageBilling = !!can_manage_billing`
    - `investorMonthlyCents = prices?.monthly_cents?.investor ?? null`
  - Local resolves `{ brokerSync: true, billingEnabled: false, canManageBilling: false, investorMonthlyCents: null }` with no request.

- [ ] **Step 1: Write the failing test** `it("resolves the onboarding plan from billing status in cloud and allows everything locally")`.
  - Extend the existing `vi.mock("./api")` with `fetchBillingStatus: vi.fn(async () => ({ capabilities: ["portfolio_analytics"], billing_enabled: true, can_manage_billing: true, prices: { currency: "eur", monthly_cents: { investor: 599, pro: 999 } } }))`.
  - Assert cloud → `{ brokerSync: false, billingEnabled: true, canManageBilling: true, investorMonthlyCents: 599 }`.
  - Assert local → `{ brokerSync: true, billingEnabled: false, canManageBilling: false, investorMonthlyCents: null }`.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/edition.test.jsx`. Expected: FAIL (export missing).
- [ ] **Step 3: Implement** both exports. Leave `fetchEditionPlanCapabilities` untouched (out of scope; see the hand-off note at the end).
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(onboarding): edition-aware onboarding plan`

---

### Task 4: Shared credential forms and key guides

The spec leaves the shape of the reuse to the builder. Decision: share the **credential form** and the **guides**, not whole cards. Settings' T212 card stays in `Settings.jsx` (its tests and the `HistoryBackfillStatus` export are untouched) and renders the shared form. The new modules are pure, so the onboarding view can import them.

**Files:**
- Create: `frontend/src/components/settings/brokerCredentialForms.jsx` and `frontend/src/components/settings/BrokerKeyGuides.jsx`
- Modify:
  - `frontend/src/pages/Settings.jsx` (the T212 fields, about :260-276)
  - `frontend/src/components/settings/IBKRConnectionCard.jsx` (the fields at :235-250; the guide moves out and is re-exported)
  - `frontend/src/components/settings/EtoroConnectionCard.jsx` (the fields at :193-205; `KeyGuide` moves out)
- Test: `frontend/src/components/settings/brokerCredentialForms.test.jsx`

**Interfaces:**
- Produces, in `brokerCredentialForms.jsx` (imports only `react`, `lucide-react` and `../../i18n/I18nProvider`):
  - `EMPTY_CREDENTIALS = Object.freeze({ trading212: { apiKey: "", apiSecret: "" }, ibkr: { flexToken: "", queryId: "" }, etoro: { userKey: "" } })`
  - `credentialsComplete(brokerKey, values): boolean`: every field is non-empty after `trim()`.
  - The three forms are controlled: `({ values, onChange(nextValues), onSubmit(), busy = false, submitting = false })`.
    - `T212CredentialsForm` has values `{apiKey, apiSecret}`.
    - `IBKRCredentialsForm` has values `{flexToken, queryId}`.
    - `EtoroCredentialsForm` has values `{userKey}`.
  - Markup, ids, classes, labels, placeholders and aria-labels are moved **verbatim**, and the show/hide toggle state stays inside the form. The submit button is the existing `btn-primary` "Connect". It is disabled when `!credentialsComplete(...) || busy`, and shows the spinner when `submitting`.
- Produces, in `BrokerKeyGuides.jsx`: `IBKRFlexGuide` (moved) and `EtoroKeyGuide` (the moved eToro `KeyGuide`).
  - `IBKRConnectionCard.jsx` keeps `export { IBKRFlexGuide } from "./BrokerKeyGuides"`.
  - The cards keep their own state, trimming, mutations and success clearing. They pass `values` and `onChange` in.

- [ ] **Step 1: Write failing tests** in `brokerCredentialForms.test.jsx`:
  - `keeps Connect disabled until every field has text`: for each form, whitespace-only values leave it disabled; full values enable it.
  - `reports edits as whole value objects`: typing in the T212 secret calls `onChange({ apiKey: "k", apiSecret: "s" })` when the existing values are `{ apiKey: "k", apiSecret: "" }`.
  - `toggles the key visibility`: the "Show API key" button flips the input `type` from `password` to `text`.
  - `stays importable by the onboarding view`: read both new files with `?raw` and assert neither matches `/from "(\.\.\/)+(api|App)"|analytics/`.
  - `uses no legacy color classes` (`legacyColorClassesIn`) for both files.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/components/settings/brokerCredentialForms.test.jsx`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** the two modules and switch the three call sites to them.
- [ ] **Step 4: Run** `npx vitest run src/components/settings src/pages/Settings.sections.test.jsx src/components/import`. Expected: all PASS with the existing tests **unchanged**. If an existing test fails, the move was not verbatim: fix the move, not the test.
- [ ] **Step 5: Commit** `refactor(settings): share broker credential forms and key guides`

---

### Task 5: `ConnectStep` view inside `OnboardingView`

**Files:**
- Create: `frontend/src/components/onboarding/ConnectStep.jsx`
- Modify: `frontend/src/components/onboarding/OnboardingView.jsx`
- Test: `frontend/src/components/onboarding/ConnectStep.test.jsx`, and extend `OnboardingView.test.jsx`

**Interfaces:**
- Consumes (Task 4): `T212CredentialsForm`, `IBKRCredentialsForm`, `EtoroCredentialsForm`, `EMPTY_CREDENTIALS`, `IBKRFlexGuide` and `EtoroKeyGuide`, plus the existing `T212ApiGuide`.
- Produces `ConnectStep({ broker, connect, busy })`. `connect` is the `ConnectProps` object below, which Task 6/7 fill in:

  ```
  {
    phase: "loading" | "gated" | "form" | "connecting" | "syncing" | "unavailable" | "sync-failed" | "load-error",
    billingEnabled, canManageBilling, investorMonthlyCents,  // from OnboardingPlan; may be absent while loading
    notice: null | "canceled" | "processing",
    error: string | null,
    locked: boolean,              // the pending portfolio already holds a connection
    onSubmit(credentials), onUpgrade(), onImportFree(), onBack(), onChangeBroker(), onDemo(), onRecheck()
  }
  ```
- `OnboardingView` gets the new optional prop `connect = null`. When `connect` is set and the broker has `api: true`, it renders `<ConnectStep broker connect busy />` with `stepKey = "connect"` (`max-w-4xl` like the choices). Otherwise it behaves exactly as today. `OnboardingPreview` never passes `connect`.
- Owned by the view: the credential values (`useState(EMPTY_CREDENTIALS[broker.key])`) and the consent checkbox.
- Header: the existing `StepHeader` with eyebrow `t("Step 2 of 2 · {broker}")` and title `t("Connect {broker}")`.

Rendering per phase (new copy is exact; everything else reuses existing keys):

| phase | renders |
|---|---|
| `loading` | `role="status"`: "Checking your plan…" |
| `gated` | h2 "Automatic sync is part of Investor"; body "Connecting {broker} imports your history and keeps it up to date. It is part of the Investor plan for {price} a month." (`price` = `Intl.NumberFormat(language, {style:"currency", currency:"EUR"})` of cents/100). If cents is null, use "Connecting {broker} imports your history and keeps it up to date. It is part of the Investor plan." The upgrade block follows. Then: if `broker.fileKind`, a `btn-ghost` "Import your {broker} {fileKind} for free" → `onImportFree`; otherwise "Choose another broker" → `onChangeBroker` and "Look around with sample data (free)" → `onDemo`. |
| upgrade block | Billing off: notice title "Free plan switching during private testing", then `btn-primary` "Use {plan} for testing" with `plan: "Investor"`. Billing on + `canManageBilling`: the consent checkbox (Pricing's exact sentence), then `btn-primary` "Upgrade to Investor", disabled until ticked. Billing on + `!canManageBilling`: the text "Only the workspace owner can change the plan or manage billing." and no button. |
| `form` | the broker's guide (T212 → `T212ApiGuide`, IBKR → `IBKRFlexGuide`, eToro → `EtoroKeyGuide`), then its credentials form; Connect → `onSubmit(values)` |
| `connecting` | `role="status"` + spinner: "Connecting to {broker}…" |
| `syncing` | `role="status"` + spinner: "Importing your history from {broker}…" |
| `unavailable` | "Connecting eToro is temporarily unavailable. Choose another broker or look around with sample data.", then "Choose another broker" and "Look around with sample data (free)" |
| `sync-failed` / `load-error` | the `error` alert, then `btn-primary` "Try again" → `onRecheck` |

- Always: `error` renders as `role="alert"` (token classes as in Settings).
- Notices: `notice === "canceled"` shows "Checkout was cancelled. You have not been charged.". `notice === "processing"` shows "Your payment is being processed. Your plan will switch shortly." plus a `btn-ghost` "Check again" → `onRecheck`.
- Back: a `btn-ghost` "Back" → `onBack` shows only when `!locked` and the phase is not `connecting` or `syncing`.
- Busy: all buttons are disabled while `busy != null` or the phase is `connecting` or `syncing`.

- [ ] **Step 1: Write failing tests** in `ConnectStep.test.jsx`. Render through `OnboardingView` with `brokerKey` plus `connect`, with handlers as `vi.fn()`:
  - `shows the plan gate before any credential field`: phase `gated`, T212, billing off → heading "Automatic sync is part of Investor"; no "API key ID" label; "Use Investor for testing" calls `onUpgrade`; "Import your Trading 212 CSV for free" calls `onImportFree`.
  - `formats the Investor price`: `investorMonthlyCents: 599` → text contains `€5.99` (English).
  - `requires consent before checkout when billing is on`: the "Upgrade to Investor" button is disabled, ticking the consent checkbox enables it, and clicking calls `onUpgrade`.
  - `tells a non-owner who can upgrade`: `canManageBilling: false` → the owner sentence and no Upgrade button.
  - `offers eToro only the upgrade, another broker and the demo`: eToro gated → no "for free" button; "Choose another broker" → `onChangeBroker`; "Look around with sample data (free)" → `onDemo`.
  - `shows each broker's guide and form`: T212 → heading "How to connect Trading 212" plus label "API key ID"; IBKR → label "Flex Web Service token"; eToro → label "eToro API key". Connect calls `onSubmit` with the typed values object.
  - `shows progress without Back while connecting and syncing`: `syncing` → status "Importing your history from Interactive Brokers…" and no "Back" button.
  - `hides Back once the portfolio holds a connection`: `form` + `locked: true` → no "Back".
  - `renders unavailable, sync-failed and both notices`: "Try again" and "Check again" call `onRecheck`.
- [ ] **Step 2: Extend `OnboardingView.test.jsx`.** In "never links to pricing on any step", add `{ brokerKey: "trading212", connect: { phase: "gated", billingEnabled: true, canManageBilling: true, investorMonthlyCents: 599, notice: null, error: null, locked: false } }` to `steps`, with every handler as `noop`. Add `it("ignores connect for a file-only broker")`: `brokerKey: "xtb"` with `connect` set still shows "Import your XTB file".
- [ ] **Step 3: Run** `cd frontend && npx vitest run src/components/onboarding src/pages/OnboardingPreview.test.jsx`. Expected: the new tests FAIL. The preview import-graph test must stay green throughout.
- [ ] **Step 4: Implement** `ConnectStep.jsx` and the `connect` prop.
- [ ] **Step 5: Run** the same command. Expected: all PASS, including `legacyColorClassesIn` for `ConnectStep.jsx` (add that test).
- [ ] **Step 6: Commit** `feat(onboarding): connect step view with plan gate`

---

### Task 6: `useOnboardingConnect` hook

**Files:**
- Create: `frontend/src/hooks/useOnboardingConnect.js`
- Test: `frontend/src/hooks/useOnboardingConnect.test.jsx`

**Interfaces:**
- Consumes:
  - Task 2's `api.js` options, `clearConnectStep`, `rememberConnectStep`, `isPlanUpgradeRequired`, `apiErrorCode` and `syncImportedData`
  - Task 3's `fetchEditionOnboardingPlan` (import from `@edition-manifest`)
  - Existing `api.js` functions: `fetchT212Status`, `fetchIBKRStatus`, `fetchEtoroStatus`, `createPendingImportPortfolio`, `activatePortfolio`, `updateTestPlan`, `startCheckout` and `confirmCheckout`
  - `rememberIntendedBroker` and `getApiErrorMessage`
- Produces:

  ```
  useOnboardingConnect({
    broker,                 // SUPPORTED_BROKERS entry with api:true, or null → idle (phase "loading", no requests)
    pendingPortfolio,       // usePortfolio().pendingImportPortfolio
    setCurrentId,           // usePortfolio().setCurrentId
    checkoutReturn,         // readCheckoutReturn(...) result or null; handled once per value
    onCheckoutReturnHandled,// () => void; the page strips checkout/session_id from the URL
    onFinished,             // ({ imported: boolean }) => void | Promise<void>
  }) => { phase, plan, notice, error, locked, submit(credentials), upgrade(), recheck() }
  ```
  - `phase`, `notice`, `error` and `locked` match Task 5's `ConnectProps`.
  - `plan` is an `OnboardingPlan | null`.
  - `credentials` uses Task 4's value shapes.
  - Connect calls trim every field.

Behaviour (each async run carries a run counter; a stale run's result is dropped):

1. **Load.** Runs on mount and whenever `broker.key` changes, and on `recheck()`. It sets `phase = "loading"`, then works in order:
   1. **Checkout return.** When `checkoutReturn` is set and not yet handled:
      - `success` with a session id: read the plan. If `plan.billingEnabled`, call `confirmCheckout(sessionId)`. `checkout_status !== "complete"` or an error sets `notice = "processing"`. Then read the plan again.
      - `canceled`: set `notice = "canceled"`.
      - Then call `onCheckoutReturnHandled()` and `clearConnectStep()`.
   2. **Resume.** If `pendingPortfolio` exists, call `setCurrentId(pendingPortfolio.id)` and read the broker status.
      - `connected === true`: set `locked = true` and run **Finish**, syncing first only when `!status.last_synced_at`.
      - eToro with `!connected && configured === false`: `phase = "unavailable"`.
   3. **Plan.** `plan = await fetchEditionOnboardingPlan()`, then `phase = plan.brokerSync ? "form" : "gated"`.
   - Any error: `phase = "load-error"` and `error = t("We couldn't check your plan. Please try again.")`.
2. **`submit(credentials)`**
   - `phase = "connecting"`.
   - `pending = pendingPortfolio ?? await createPendingImportPortfolio()`, then `setCurrentId(pending.id)`.
   - Connect with `{ suppressEntitlementPrompt: true }`, then set `locked = true` and run **Finish** with a sync.
   - Errors before connect succeeded:
     - `isPlanUpgradeRequired` → re-read the plan and set `phase = "gated"`.
     - eToro with status 503 → `phase = "unavailable"`.
     - Anything else → `phase = "form"` and `error = getApiErrorMessage(err, t("Failed to connect"), t)`.
3. **Finish (`portfolioId`, `withSync`)**
   - If `withSync`: `phase = "syncing"`, then sync with `{ suppressEntitlementPrompt: true }`. There is no client timeout; T212 answers 202 at once.
   - `imported = syncImportedData(key, result)`, or `false` without a sync.
   - Then `activatePortfolio(portfolioId)`. A 409 counts as success.
   - Then `await onFinished({ imported })`.
   - Any error after connect succeeded: `phase = "sync-failed"` and `error = getApiErrorMessage(err, t("Sync failed"), t)`. `recheck()` then resumes through step 1.2, so connect is never called twice.
4. **`upgrade()`**
   - Billing off:
     - Call `updateTestPlan("investor")`, then `queryClient.invalidateQueries({ queryKey: ["plan-capabilities"] })`.
     - Re-read the plan and set the phase from it.
     - On error: `error = t("The plan could not be changed. Please try again.")`.
   - Billing on:
     - Call `rememberConnectStep(key)` and `rememberIntendedBroker(key)`.
     - `{ url } = await startCheckout("investor")`, then `window.location.assign(url)`.
     - On error:
       - `apiErrorCode === "workspace_owner_required"` → `error = t("Only the workspace owner can change the plan or manage billing.")`.
       - `"subscription_exists"` → `recheck()`.
       - Anything else → `error = t("The payment page could not be opened. Please try again.")`.

- [ ] **Step 1: Write failing tests** with `renderHook` inside a `QueryClientProvider`. Mock `../api`, `@edition-manifest` and `window.location.assign`:
  - `gates a plan without broker_sync before any credential request`: phase `gated`; no connect or status call.
  - `switches to Investor in test mode and shows the form`: `updateTestPlan("investor")` is called once, then the plan is re-read → phase `form`.
  - `starts checkout and remembers the step`: billing on → `startCheckout("investor")`; `assign` gets the url; `connectStepBroker()` and `intendedBroker()` both equal the key.
  - `maps workspace_owner_required to the owner message`
  - `confirms a successful checkout and shows the form`: `checkoutReturn {success, "cs_1"}` → `confirmCheckout("cs_1")`, `onCheckoutReturnHandled` called once, phase `form`, `notice` null.
  - `shows processing when the checkout is not complete yet`: `checkout_status: "open"` → `notice` "processing".
  - `shows the cancellation note and keeps the gate`: `canceled` → `notice` "canceled", phase `gated`, and no `confirmCheckout`.
  - `connects into the pending portfolio, syncs and finishes`:
    - Setup: IBKR with no pending portfolio.
    - `createPendingImportPortfolio` → `{id: "p1"}`, then `setCurrentId("p1")`.
    - Connect is called with `("tok", "123", { suppressEntitlementPrompt: true })`.
    - `syncIBKR` returns `{ ledger: { imported: 3 } }`.
    - Then `activatePortfolio("p1")` and `onFinished({ imported: true })`.
  - `finishes T212 right after the 202 snapshot`: sync `{ snapshot: { positions: 0 }, history: { status: "queued" } }` → `activatePortfolio` called, `onFinished({ imported: false })`.
  - `treats 409 on activate as success`
  - `resumes a connected pending portfolio without connecting again`: status `{ connected: true, last_synced_at: null }` → sync then finish; `connectT212` never called; `locked` true. With `last_synced_at` set → no sync either.
  - `turns a plan_upgrade_required connect into the gated state`: connect rejects with `{ response: { status: 403, data: { code: "plan_upgrade_required" } } }` → phase `gated`, `error` null.
  - `shows eToro unavailable on 503` and `shows eToro unavailable when the server has no app key` (`status.configured === false`)
  - `keeps the user on the form with the server's message when connect fails`: `detail: "Invalid API key"` → phase `form`, error "Invalid API key".
  - `offers a retry when the sync fails after connecting`: phase `sync-failed`; `recheck()` resumes via status and does not call connect.
  - `drops a late answer after the broker changed`: re-render with another broker before the plan resolves → phase follows only the new broker.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/hooks/useOnboardingConnect.test.jsx`. Expected: FAIL (module missing).
- [ ] **Step 3: Implement** the hook.
  - Use one `BROKER_CONNECTORS` map in the file, keyed `trading212 | ibkr | etoro`, with `{ status, connect(credentials, options), sync(options) }`.
  - Guard React StrictMode's double effect with the run counter, and with a ref holding the handled `checkoutReturn`, so `confirmCheckout` runs once.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(onboarding): connect, first sync and activation hook`

---

### Task 7: Wire the connect step into the Onboarding page

**Files:**
- Modify:
  - `frontend/src/pages/Onboarding.jsx`
  - `frontend/src/analytics/eventContract.js` (line 32)
  - `frontend/src/pages/OnboardingPreview.jsx` (`OUTCOMES.broker`)
- Test:
  - `frontend/src/pages/Onboarding.test.jsx`
  - `frontend/src/analytics/eventContract.test.js`
  - `frontend/src/pages/OnboardingPreview.test.jsx` (only if it asserts the old outcome text)

**Interfaces:**
- Consumes:
  - Task 6's `useOnboardingConnect`
  - Task 5's `connect` prop
  - Task 2's `rememberConnectStep`, `connectStepBroker`, `clearConnectStep` and `readCheckoutReturn`
- Produces `buildOnboardingActions({ beginImport, activate, openConnect })` with the keys `import`, `demo` and `broker`. `broker` is now `openConnect`. The `broker` and `portfolios` parameters and the `createPortfolio` / `uniquePortfolioName` imports go away.

Page rules:
- **Step:** `step = unsupportedName ? "unsupported" : broker ? (searchParams.get("step") === "connect" && broker.api ? "connect" : "choices") : "broker"`. The existing funnel effect reports it. Add `"connect"` to `onboardingSteps` in `eventContract.js`.
- **openConnect():** call `rememberConnectStep(broker.key)`, then set `step=connect` in the URL (push, keeping `broker`). No portfolio is created yet.
- **onBack:** call `clearConnectStep()` and delete `step` from the URL.
- **changeBroker()** also calls `clearConnectStep()`, and deletes `step`.
- **beginImport()** also calls `clearConnectStep()` (it is the "Import for free" path).
- **Restore after a closed tab:**
  - If the URL has no `broker` and there is no checkout return, the initial `remembered` becomes `connectStepBroker() ?? intendedBroker()`.
  - When it came from the connect-step marker, the mount effect also sets `step=connect`.
- **Checkout return:** `const [checkoutReturn] = useState(() => readCheckoutReturn(searchParams))`.
  - Stripe always returns to `/pricing`, and `AppLayout`'s `RouteBoundary key={pathname}` remounts Onboarding on a path change. So when `pathname !== "/onboarding"`, it navigates (replace) to `/onboarding?broker=<connectStepBroker() ?? intendedBroker()>&step=connect&checkout=<outcome>&session_id=<id>` and passes `checkoutReturn: null` to the hook.
  - With no remembered broker, it goes to `/onboarding` with only the checkout params removed.
  - At `/onboarding`, it passes `checkoutReturn` to the hook. `onCheckoutReturnHandled` deletes `checkout` and `session_id` (replace).
- **onFinished({ imported }):** in this order:
  1. `recordPortfolioCreated("broker")`
  2. `if (imported) recordPortfolioDataImported("broker")`
  3. `clearIntendedBroker()`
  4. `clearConnectStep()`
  5. `navigate(TRACKER_HOME)`
  6. `await refetchPortfolios()`

  This keeps today's navigate-before-refetch order.
- Pass `connect = step === "connect" ? { ...hook state, onSubmit: submit, onUpgrade: upgrade, onRecheck: recheck, onImportFree: () => beginImport(), onBack, onChangeBroker: () => changeBroker(null), onDemo: () => activate(createDemoPortfolio, TRACKER_HOME, "demo") } : null`. The hook gets `broker` only while `step === "connect"`, and `null` otherwise.
- **Preview `OUTCOMES.broker`** becomes `t("Asks for your {broker} {credential} right here, imports your history and opens the dashboard. Automatic sync is part of the Investor plan; a file import stays free.", { broker: broker.name, credential: t(broker.credential) })`. The null-broker branch becomes `t("Asks for your broker's API key right here, imports your history and opens the dashboard.")`.

- [ ] **Step 1: Update and write failing tests** in `Onboarding.test.jsx`:
  - Mocks: extend the `../api` mock with the functions the hook imports. Mock `@edition-manifest` (`fetchEditionOnboardingPlan`; default `brokerSync: true`, billing off). Add a `/pricing` route rendering `<Onboarding /><LocationProbe />`.
  - **Replace** "creates a portfolio named after the broker before opening its connection" with `opens the connect step in onboarding instead of Settings`: clicking "Connect Trading 212" puts `?broker=trading212&step=connect` in the location; the "API key ID" label is visible; `createPortfolio` and `createPendingImportPortfolio` are not called; there is no "Settings destination".
  - **Replace** "navigates before the portfolio refetch can unmount onboarding" (eToro) with the same assertion on the finish path: submit eToro credentials, `syncEtoro` → `{ imported: 2 }`, and "Dashboard destination" appears while `refetchPortfolios` is still pending.
  - **Replace** "clears the remembered broker after a broker connection portfolio" with `clears the remembered broker after the connection finishes`.
  - `connects, syncs and opens the dashboard`:
    - Setup: IBKR, then type the token and query id, then Connect.
    - `createPendingImportPortfolio` called once, `setCurrentId("pending-id")`, `activatePortfolio("pending-id")`.
    - `recordPortfolioCreated("broker")` and `recordPortfolioDataImported("broker")`.
    - `localStorage.getItem("portfyl_onboarding_connect")` is null.
    - "Dashboard destination".
  - `gates a Free workspace and imports for free instead`: plan `brokerSync: false` → "Automatic sync is part of Investor"; clicking "Import your Trading 212 CSV for free" → `/import?broker=trading212` and the marker is cleared.
  - `goes back from the connect step to the choices`: "Back" → `?broker=ibkr` without `step`, and "Step 2 of 2 · Interactive Brokers" choices are shown.
  - `reopens the connect step after a closed tab`: `rememberConnectStep("ibkr")` beforehand, then mount `/onboarding` with no params → location `?broker=ibkr&step=connect`.
  - `moves a checkout return from /pricing to the connect step`:
    - Setup: marker `trading212`, billing on.
    - Mount `/pricing?checkout=success&session_id=cs_1`.
    - The location ends at `/onboarding?broker=trading212&step=connect` without `checkout` or `session_id`; `confirmCheckout("cs_1")` is called exactly once.
  - Funnel: `reports the connect step` → events contain `["onboarding_step_viewed", { step: "connect" }]` after `choices`.
  - `wires exactly one action to every onboarding choice` now builds with `{ beginImport, activate, openConnect }`.
  - In `eventContract.test.js`, add `"connect"` to the accepted steps case, following the file's existing pattern.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/pages/Onboarding.test.jsx src/pages/OnboardingPreview.test.jsx src/analytics/eventContract.test.js`. Expected: the new and replaced tests FAIL.
- [ ] **Step 3: Implement** the page rules, the analytics step and the preview outcome.
- [ ] **Step 4: Run** the same command plus `npx vitest run src/components/onboarding src/hooks/useOnboardingConnect.test.jsx src/App.routing.test.jsx`. Expected: all PASS.
- [ ] **Step 5: Commit** `feat(onboarding): connect a broker inside onboarding`

---

### Task 8: Translations, full verification, browser check

**Files:**
- Modify: `frontend/src/i18n/messages/{cs,de,es,fr,it,nl,pl,pt}.js`
- Modify, only if the look changed beyond existing patterns: `DESIGN.md`

- [ ] **Step 1: Run** `cd frontend && npx vitest run src/i18n/messages.test.js`. Expected: FAIL. It lists the missing keys (every new string from Tasks 5–7) and the stale keys (the two old `OUTCOMES.broker` strings).
- [ ] **Step 2: Fix the dictionaries.** Add a natural translation of each missing key to all 8 dictionaries, keeping `{placeholders}` intact. Delete the stale keys. Czech uses informal "ty" like the existing onboarding strings, so check the neighbours in `cs.js`.
- [ ] **Step 3: Run** `npx vitest run src/i18n/messages.test.js`. Expected: PASS.
- [ ] **Step 4: Run the full suites**: `npm test`, `npm run test:cloud`, `npm run build` and `npm run build:cloud`. Also run `cd ../backend && python -m pytest tests/ --ignore=tests/postgres -q`. Expected: all green. Fix anything this branch broke.
- [ ] **Step 5: Re-integrate.** Run `git merge main` into `feat/onboarding-broker-connect`, then repeat Step 4.
- [ ] **Step 6: Browser check** (Playwright MCP) on an isolated instance:
  - Setup:
    - Use a dedicated database `portfyl_onb_connect`, migrated with `alembic upgrade head`.
    - Run the backend on `:8010` with `PORTFYL_EDITION=cloud` and billing off.
    - Run Vite on `:5183`, its `/api` proxy pointed at `:8010`.
  - Register a fresh Firebase test account. Pick Trading 212, then "Connect Trading 212", and check:
    - The gate is shown first.
    - "Use Investor for testing" turns it into the form.
    - Bad credentials show an inline alert and no toast.
    - Reloading keeps the step.
    - "Back" returns to the choices.
  - Repeat with eToro and check "Choose another broker" and the sample data.
  - Take screenshots at 375 px and desktop width, in light and dark themes, and compare against `DESIGN.md`.
  - A real broker key is optional. Without one, the connect → Dashboard path is covered by Task 6/7 tests.
- [ ] **Step 7: Commit** `i18n(onboarding): translate the connect step`, then hand off with superpowers:finishing-a-development-branch.

---

## Hand-off notes (outside this plan's scope)

- `editions/cloud.jsx`'s `fetchEditionPlanCapabilities` (Dashboard) reads `/api/test-plans`, which is unmounted once `PORTFYL_BILLING_ENABLED=1`. The Dashboard plan query will then fail. Fix it before payments go live, probably by reusing `fetchEditionOnboardingPlan`'s billing-status read.
- After an IBKR or eToro first sync, the pending marker row stays behind (activate answers 409 and nothing clears it). `GET /api/portfolios` ignores it, and the next `createPendingImportPortfolio` cleans it up. That is harmless, but a later backend tidy-up could clear it when a broker sync writes the first rows.
