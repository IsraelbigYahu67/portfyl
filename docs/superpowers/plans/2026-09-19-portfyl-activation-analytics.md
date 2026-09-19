# Portfyl Activation Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure the approved public-demo and registered-user activation funnels with PostHog Cloud EU's no-card free tier while sending nothing before consent and never capturing personal or financial portfolio data.

**Architecture:** A strict event-contract module sanitizes every capture. A consent-owned analytics provider dynamically imports PostHog only after accept/reject, selects persistent or cookieless behavior, and exposes a non-throwing API plus a deterministic memory adapter for tests. Feature hooks derive demo and registered activation locally from approved route/action milestones. Backend HTML security headers allow only the EU ingestion endpoints.

**Tech Stack:** React 18, `posthog-js`, Vite 6, Vitest 4, Testing Library, FastAPI/Starlette, pytest.

**Spec:** `docs/superpowers/specs/2026-09-19-portfyl-public-demo-activation-readability-design.md`

**Prerequisites:** Complete both the readability and public-demo plans first.

## Non-negotiable privacy contract

- Pending: do not download the PostHog SDK, initialize a client, queue an event, or write analytics storage.
- Rejected: initialize only after rejection, use `cookieless_mode: "on_reject"`, call the PostHog rejection/opt-out API, create no PostHog persistence or person profile, and capture only aggregate approved events.
- Accepted: use first-party cross-subdomain persistence scoped to `.portfyl.com`; identify only with the opaque internal user UUID.
- Never send e-mail, display name, Firebase UID/token, workspace name, portfolio ID, holdings/tickers from a real portfolio, balances, amounts, transactions, free text, URL query strings, or exception payloads.
- Disable autocapture, automatic pageview/pageleave, session replay, forms/text capture, heatmaps, surveys, dead-clicks, and PostHog exception capture.
- Product calls are non-throwing. Missing key, invalid configuration, script blocking, quota exhaustion, or endpoint blocking leaves the product fully functional.
- Production analytics stays disabled until privacy/subprocessor review is complete. Development and tests use no-op/memory adapters and never send live events.

---

## Task 1: Install PostHog and implement the strict event contract

**Files:**

- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/src/analytics/eventContract.js`
- Create: `frontend/src/analytics/eventContract.test.js`

**Allowed contract:**

| Event | Exact allowed properties |
|---|---|
| `landing_viewed` | `language`, `referrer_class`, `utm_source`, `utm_medium`, `utm_campaign` |
| `demo_started` | `language`, `entry_point` |
| `demo_page_viewed` | `demo_page`, `language` |
| `demo_stock_viewed` | `demo_symbol` |
| `demo_activation_reached` | `activation_path`, `distinct_demo_pages` |
| `signup_cta_clicked` | `source_surface`, `language` |
| `signup_started` | `source_surface`, `language` |
| `signup_completed` | `source_surface` |
| `portfolio_created` | `creation_path` |
| `portfolio_data_imported` | `source_type` |
| `dashboard_first_value_rendered` | `source_type` |
| `user_activation_reached` | `source_type` |

**Interfaces:**

- `ANALYTICS_EVENTS` is a frozen name map.
- `sanitizeEvent(name, properties, { strict = import.meta.env.DEV || import.meta.env.MODE === "test" } = {})` returns `{ name, properties }` or `null` in non-strict mode.
- Every string is trimmed and capped at 80 characters; UTM values are capped at 120. Numbers must be finite integers within their event-specific range.

- [ ] Run `cd frontend; npm install posthog-js --save` and confirm only `package.json`/lock dependency changes.
- [ ] Write table-driven tests for all 12 event names and every allowed property.
- [ ] Test that unknown event names, unknown properties, objects, arrays, non-finite numbers, and overlong values throw in strict mode.
- [ ] Test that unknown event names and invalid allowed-property values return `null` in `{ strict: false }`; unknown property names are removed while valid allowed properties remain.
- [ ] Add enum tests: `source_type` is only `demo|csv|broker`; `creation_path` is only `blank|demo|csv|broker`; `source_surface` is only `landing_hero|landing_closing|demo|direct`; `entry_point` is only `landing_hero|landing_closing|direct`; `demo_page` is only `overview|allocation|analytics|dividends|stock`; `activation_path` is only `three_pages|stock_after_page`; languages are `cs|en|de`; `distinct_demo_pages` is integer 2–5.
- [ ] Add source-safety tests that stringify the contract module and reject forbidden property words: `email`, `display_name`, `workspace_name`, `portfolio_id`, `balance`, `amount`, `holdings`, `transactions`.
- [ ] Run `npm test -- --run src/analytics/eventContract.test.js` and confirm failure because the module is absent.
- [ ] Implement the frozen schema as property validator functions; do not accept arbitrary property spreading at any layer.
- [ ] For `landing_viewed`, normalize referrer to one of `direct|search|social|referral|internal|unknown`; never retain the raw referrer URL.
- [ ] For UTM values, accept only the three named keys read from the current landing URL, remove them after sanitization, and never send the entire URL/search string.
- [ ] Re-run the focused tests and expect pass.
- [ ] Commit:

```powershell
git add frontend/package.json frontend/package-lock.json frontend/src/analytics/eventContract.js frontend/src/analytics/eventContract.test.js
git commit -m "feat: add strict activation event contract"
```

## Task 2: Implement consent persistence and analytics adapters

**Files:**

- Create: `frontend/src/analytics/consent.js`
- Create: `frontend/src/analytics/consent.test.js`
- Create: `frontend/src/analytics/analyticsClient.js`
- Create: `frontend/src/analytics/analyticsClient.test.js`

**Interfaces:**

- Consent states are exactly `pending`, `accepted`, `rejected`.
- Cookie name is `portfyl_analytics_consent`; production attributes are `Domain=.portfyl.com; Path=/; Max-Age=15552000; SameSite=Lax; Secure`. Localhost omits Domain/Secure.
- `createNoopAdapter()`, `createMemoryAdapter()`, and `loadPostHogAdapter(config)` expose async `init`, `capture`, `identify`, `reset`, and `shutdown` methods.
- `loadPostHogAdapter` is the only module allowed to contain `import("posthog-js")`.

- [ ] Write consent tests using a document-cookie shim for missing/invalid cookies, accepted/rejected round trips, production domain attributes, localhost attributes, and clearing the choice.
- [ ] Write client tests with an injected `importPostHog` spy proving pending never imports, accepted/rejected import once, missing key returns no-op, and import/init/capture failures resolve without throwing.
- [ ] Assert accepted config exactly includes:

```js
{
  api_host: "https://eu.i.posthog.com",
  ui_host: "https://eu.posthog.com",
  autocapture: false,
  capture_pageview: false,
  capture_pageleave: false,
  disable_session_recording: true,
  person_profiles: "identified_only",
  cross_subdomain_cookie: true,
  persistence: "localStorage+cookie",
  secure_cookie: true,
  cookieless_mode: "on_reject"
}
```

- [ ] Assert rejected config changes `persistence` to `memory`, never calls `identify`, and invokes PostHog's explicit rejection/opt-out method after init so `on_reject` enters cookieless capture.
- [ ] Assert no config enables surveys, heatmaps, exception capture, text capture, or session recording.
- [ ] Test the memory adapter's ordered event log, identified ID, reset count, and `clear()` helper.
- [ ] Run both focused test files and confirm failure.
- [ ] Implement cookie parsing/writing without localStorage fallback. The consent preference cookie is essential preference storage; no PostHog cookie/localStorage entry may exist in rejected mode.
- [ ] Implement `loadPostHogAdapter` with dependency injection for tests and a production dynamic import. Pass only the public project key and validated EU host.
- [ ] Wrap every adapter operation in `try/catch`; return `false` on adapter failure and never log event properties or user IDs.
- [ ] Re-run focused tests and expect pass.
- [ ] Commit:

```powershell
git add frontend/src/analytics/consent.js frontend/src/analytics/consent.test.js frontend/src/analytics/analyticsClient.js frontend/src/analytics/analyticsClient.test.js
git commit -m "feat: add consent-aware analytics adapters"
```

## Task 3: Add the global provider and localized consent/preferences UI

**Files:**

- Create: `frontend/src/analytics/AnalyticsProvider.jsx`
- Create: `frontend/src/analytics/AnalyticsProvider.test.jsx`
- Create: `frontend/src/analytics/ConsentBanner.jsx`
- Create: `frontend/src/analytics/AnalyticsPreferences.jsx`
- Create: `frontend/src/analytics/analyticsCopy.js`
- Modify: `frontend/src/Root.jsx`
- Modify: `frontend/src/pages/Welcome.jsx`
- Modify: `frontend/src/demo/DemoShell.jsx`
- Modify: `frontend/src/components/DataPrivacySettings.jsx`
- Modify: `frontend/src/components/DataPrivacySettings.test.jsx`

**Provider API:**

```js
const {
  consent, ready, capture, captureOnce, identify, reset,
  acceptAnalytics, rejectAnalytics, reopenAnalyticsPreferences
} = useAnalytics();
```

- `capture` always calls `sanitizeEvent` and never throws to callers.
- `captureOnce(scope, event, props)` uses an in-memory Set for rejected mode and a localStorage key only in accepted mode. The scope may contain opaque IDs locally but is never included in event properties.
- Pending captures are dropped, not queued for later replay.

- [ ] Write provider tests with an injected memory adapter factory for all three initial consent states.
- [ ] Prove pending renders children/banner but records no events and initializes no adapter; accepting/rejecting initializes exactly one adapter and future captures work.
- [ ] Prove changing accepted → rejected calls `shutdown/reset`, removes PostHog persistence via adapter reset, reinitializes cookieless, and preserves only the consent preference cookie.
- [ ] Prove `captureOnce` deduplicates by scope/event, a different scope captures, and `reset` clears only in-memory identity state, not the consent choice.
- [ ] Test Czech, English, and German banner text, separate essential/optional explanation, equally accessible Accept/Reject actions, visible keyboard focus, and preferences reopening.
- [ ] Run focused provider and DataPrivacySettings tests; confirm failure.
- [ ] Implement provider initialization in an effect keyed by consent/key/host. Cancel stale async initialization on consent changes and call adapter shutdown during cleanup.
- [ ] Read `VITE_POSTHOG_KEY` and `VITE_POSTHOG_HOST`; accept only `https://eu.i.posthog.com` in production. Missing/invalid config uses no-op with `ready=true` after a decision.
- [ ] Wrap the entire Root output in `AnalyticsProvider`, outside the Welcome/Demo/Tracker selection and outside AuthProvider. Do not move Firebase/auth into Root.
- [ ] Render `ConsentBanner` from the provider only while pending. Add `AnalyticsPreferences` access from Welcome footer, DemoShell, and the existing authenticated Data & Privacy settings section.
- [ ] Add exact localized meaning: essential storage keeps Portfyl working; optional analytics measures anonymous product use; rejecting does not reduce functionality; preference can be changed later.
- [ ] Run:

```powershell
cd frontend
npm test -- --run src/analytics/AnalyticsProvider.test.jsx src/components/DataPrivacySettings.test.jsx src/Root.test.jsx
npm run test:cloud -- --run src/analytics/AnalyticsProvider.test.jsx src/components/DataPrivacySettings.test.jsx src/Root.test.jsx
```

  Expect pass in both editions.
- [ ] Commit:

```powershell
git add frontend/src/analytics frontend/src/Root.jsx frontend/src/pages/Welcome.jsx frontend/src/demo/DemoShell.jsx frontend/src/components/DataPrivacySettings.jsx frontend/src/components/DataPrivacySettings.test.jsx
git commit -m "feat: add global analytics consent controls"
```

## Task 4: Instrument landing/demo events and derive demo activation

**Files:**

- Create: `frontend/src/analytics/useDemoAnalytics.js`
- Create: `frontend/src/analytics/useDemoAnalytics.test.jsx`
- Modify: `frontend/src/pages/Welcome.jsx`
- Modify: `frontend/src/pages/Welcome.test.jsx`
- Modify: `frontend/src/demo/DemoApp.jsx`
- Modify: `frontend/src/demo/DemoApp.test.jsx`
- Modify: `frontend/src/demo/pages/DemoStock.jsx`
- Modify: `frontend/src/demo/pages/DemoStock.test.jsx`

**Activation definition:** after `demo_started`, capture `demo_activation_reached` exactly once when (a) three distinct demo analysis pages have been viewed or (b) a stock detail is viewed after at least one non-stock demo page.

**Route mapping:** `/demo` → `overview`; `/demo/allocation` → `allocation`; `/demo/analytics` → `analytics`; `/demo/dividends` → `dividends`; valid stock route → `stock`.

- [ ] Test the hook with a memory adapter: duplicate routes do not increase the distinct count; overview→allocation→analytics emits `three_pages`; overview→stock emits `stock_after_page`; stock first does not activate; invalid stock does not emit; each session emits once.
- [ ] Assert `demo_stock_viewed.demo_symbol` accepts only the ten synthetic demo symbols. This is the only ticker-like analytics field and cannot receive real portfolio symbols.
- [ ] Add landing tests for one `landing_viewed` after analytics is ready and one `demo_started` with `entry_point="landing_hero"` when the hero demo CTA is clicked.
- [ ] Add demo shell tests for `demo_started` with `entry_point="direct"` when no landing marker exists, per-route `demo_page_viewed`, stock event, and registration CTA event `signup_cta_clicked { source_surface: "demo", language }`.
- [ ] Run focused tests and confirm failure.
- [ ] Implement `useDemoAnalytics({ page, symbol, language })` using route effects and provider `captureOnce`. Keep visited-page state in a hook ref owned by the mounted DemoApp; do not write visited pages to browser storage and never inspect real portfolio data.
- [ ] On an unmodified same-tab landing CTA click, capture `demo_started` with `captureOnce("public-demo-session", ...)`, use `history.pushState` to `/demo`, and dispatch `popstate` so Root swaps bundles without a reload. Preserve the normal anchor `href="/demo"`; modified clicks and open-in-new-tab remain native navigation and the demo records `entry_point="direct"`. The demo calls the same `captureOnce` scope, preventing a duplicate during same-tab navigation.
- [ ] Read only the initial landing UTM keys, sanitize through the contract, capture, then use `history.replaceState` to remove those UTM parameters while preserving other app-safe navigation state. Never capture raw referrer or URL.
- [ ] Instrument CTA click before navigation. If analytics is unavailable, navigation proceeds immediately.
- [ ] Run:

```powershell
cd frontend
npm run test:cloud -- --run src/analytics/useDemoAnalytics.test.jsx src/pages/Welcome.test.jsx src/demo/DemoApp.test.jsx src/demo/pages/DemoStock.test.jsx
```

  Expect pass.
- [ ] Commit:

```powershell
git add frontend/src/analytics/useDemoAnalytics.js frontend/src/analytics/useDemoAnalytics.test.jsx frontend/src/pages/Welcome.jsx frontend/src/pages/Welcome.test.jsx frontend/src/demo/DemoApp.jsx frontend/src/demo/DemoApp.test.jsx frontend/src/demo/pages/DemoStock.jsx frontend/src/demo/pages/DemoStock.test.jsx
git commit -m "feat: measure public demo activation"
```

## Task 5: Identify consented accounts and measure signup

**Files:**

- Modify: `frontend/src/auth/AuthProvider.jsx`
- Modify: `frontend/src/auth/AuthProvider.test.jsx`
- Modify: `frontend/src/pages/Register.jsx`
- Modify: `frontend/src/pages/AuthPages.test.jsx`

**Identity rules:**

- Identify only after consent is `accepted`, provider is ready, backend account payload has a stable opaque `user.id`, and a current workspace exists.
- Call `identify(String(user.id))` with no properties.
- Never identify cookieless/rejected traffic.
- Explicit logout/logout-all resets analytics. Workspace switch resets the anonymous adapter state and re-identifies the same opaque user after the switch; workspace ID is not sent.

- [ ] Extend AuthProvider tests with a mocked `useAnalytics`: accepted account load identifies once with only user ID; rejected/pending does not identify; consent accepted after account load identifies; logout/logout-all reset; workspace switch reset then identify.
- [ ] Add a negative assertion that serialized analytics mock calls contain neither `email`, `display_name`, workspace name, workspace ID, nor Firebase fields.
- [ ] Extend Register tests: route mount captures `signup_started` with source `demo` only when `?source=demo`; direct visits use `source_surface="direct"`; successful Firebase registration captures `signup_completed` before navigating to verification; failed registration does not capture completion.
- [ ] Run the two focused test files and confirm failure.
- [ ] Consume `useAnalytics` inside AuthProvider. Add an effect watching `ready`, `consent`, `user?.id`, and `currentWorkspace?.id`; the workspace ID may be a local effect dependency/scope but must not be an identify property.
- [ ] Call analytics reset in `clearAccount` only for explicit logout/logout-all/account transition. Do not reset merely because the initial `/me` request says unauthenticated; preserving a consented landing identity is required to join signup.
- [ ] In Register, derive source from a strict allowlist (`demo` or `direct`) and never forward arbitrary query parameters.
- [ ] Capture completion only after Firebase user creation succeeds and before verification navigation. Do not include e-mail or Firebase UID.
- [ ] Re-run focused tests and expect pass.
- [ ] Commit:

```powershell
git add frontend/src/auth/AuthProvider.jsx frontend/src/auth/AuthProvider.test.jsx frontend/src/pages/Register.jsx frontend/src/pages/AuthPages.test.jsx
git commit -m "feat: measure privacy-safe signup completion"
```

## Task 6: Measure portfolio data and registered activation

**Files:**

- Create: `frontend/src/analytics/activationState.js`
- Create: `frontend/src/analytics/activationState.test.js`
- Create: `frontend/src/analytics/useRegisteredActivation.js`
- Create: `frontend/src/analytics/useRegisteredActivation.test.jsx`
- Modify: `frontend/src/pages/Onboarding.jsx`
- Modify: `frontend/src/pages/Onboarding.test.jsx`
- Modify: `frontend/src/pages/Import.jsx`
- Modify: `frontend/src/pages/Import.test.jsx`
- Modify: `frontend/src/pages/Settings.jsx`
- Modify: `frontend/src/pages/Settings.sections.test.jsx`
- Modify: `frontend/src/pages/Dashboard.jsx`
- Modify: `frontend/src/pages/Dashboard.async.test.jsx`

**Hook API:**

```js
const {
  recordPortfolioCreated,       // ("blank"|"demo"|"csv"|"broker")
  recordPortfolioDataImported,  // ("demo"|"csv"|"broker")
  recordPopulatedDashboard      // ()
} = useRegisteredActivation();
```

**Local state:** accepted analytics uses `portfyl_activation_v1:<opaqueUserId>:<opaqueWorkspaceId>` with `{ sourceType, dataImported, dashboardRendered, activated }`. Rejected analytics uses an in-memory Map with the same logical scope and writes no activation state to browser storage. The key/state never leaves the browser and contains no portfolio ID or financial data.

- [ ] Unit-test accepted-state serialization, corrupted-state recovery, workspace isolation, persistence across analytics identity reset, rejected in-memory behavior, zero rejected-mode localStorage writes, and source enums.
- [ ] Hook-test the exact order: account/workspace + import source + populated dashboard emits `dashboard_first_value_rendered` then `user_activation_reached`; dashboard before import waits; duplicate renders emit neither again; a different workspace has a separate lifecycle.
- [ ] Assert all four output events contain only the contract properties and no local scope key.
- [ ] Extend Onboarding tests: blank emits only `portfolio_created {creation_path:"blank"}`; demo creation emits `portfolio_created {creation_path:"demo"}` and `portfolio_data_imported {source_type:"demo"}` after successful activation; pending CSV portfolio emits created/csv only after creation succeeds; failures emit nothing.
- [ ] Extend Import test: successful `commitImportCSV` emits `portfolio_data_imported {source_type:"csv"}` after commit success; preview/cancel/failure does not.
- [ ] Extend Settings test: a Trading 212 sync with imported count greater than zero emits broker import; zero-import and failed sync do not. Preserve existing dirty-file behavior by rebasing/merging intentionally in the clean worktree.
- [ ] Extend Dashboard async test: only a successful render with non-empty holdings and populated summary calls `recordPopulatedDashboard`; loading, error, or empty state does not.
- [ ] Run all named focused tests and confirm failure.
- [ ] Implement activationState with explicit parse validation and versioned key construction. Never enumerate or upload keys.
- [ ] Implement the hook using `useAuth` plus `useAnalytics`. If user/workspace is absent, methods safely return false.
- [ ] Wire event calls after successful mutations only. Do not put capture in generic button handlers before success.
- [ ] In Dashboard, use an effect keyed on boolean `hasPopulatedDashboard`, not full summary/holdings objects, to avoid render-driven duplication.
- [ ] Run:

```powershell
cd frontend
npm test -- --run src/analytics/activationState.test.js src/analytics/useRegisteredActivation.test.jsx src/pages/Onboarding.test.jsx src/pages/Import.test.jsx src/pages/Settings.sections.test.jsx src/pages/Dashboard.async.test.jsx
npm run test:cloud -- --run src/analytics/activationState.test.js src/analytics/useRegisteredActivation.test.jsx src/pages/Onboarding.test.jsx src/pages/Import.test.jsx src/pages/Settings.sections.test.jsx src/pages/Dashboard.async.test.jsx
```

  Expect pass in both editions.
- [ ] Commit:

```powershell
git add frontend/src/analytics/activationState.js frontend/src/analytics/activationState.test.js frontend/src/analytics/useRegisteredActivation.js frontend/src/analytics/useRegisteredActivation.test.jsx frontend/src/pages/Onboarding.jsx frontend/src/pages/Onboarding.test.jsx frontend/src/pages/Import.jsx frontend/src/pages/Import.test.jsx frontend/src/pages/Settings.jsx frontend/src/pages/Settings.sections.test.jsx frontend/src/pages/Dashboard.jsx frontend/src/pages/Dashboard.async.test.jsx
git commit -m "feat: measure registered portfolio activation"
```

## Task 7: Add a minimal HTML Content Security Policy

**Files:**

- Create: `backend/security_headers.py`
- Create: `backend/tests/test_security_headers.py`
- Modify: `backend/main.py`

**Policy:**

```text
default-src 'self';
script-src 'self';
style-src 'self' 'unsafe-inline';
img-src 'self' data: blob:;
font-src 'self' data:;
connect-src 'self' https://eu.i.posthog.com https://eu-assets.i.posthog.com https://*.googleapis.com https://*.firebaseio.com https://*.ingest.sentry.io;
object-src 'none';
base-uri 'self';
form-action 'self';
frame-ancestors 'none'
```

- [ ] Write unit tests around a small FastAPI fixture with `SecurityHeadersMiddleware`: HTML gets the exact normalized CSP; JSON/API and static image responses do not; any pre-existing CSP is replaced by the approved value; `X-Content-Type-Options: nosniff` and `Referrer-Policy: strict-origin-when-cross-origin` are present on HTML.
- [ ] Test `build_content_security_policy()` contains EU PostHog and does not contain US PostHog hosts, wildcard script sources, `unsafe-eval`, or `*` in `connect-src`.
- [ ] Run `cd backend; python -m pytest tests/test_security_headers.py -v` and confirm failure.
- [ ] Implement a Starlette `BaseHTTPMiddleware` which inspects the final `Content-Type`; add headers only when it starts with `text/html`.
- [ ] Add the middleware to `main.py` after GZip so it wraps rendered SPA HTML. Preserve the existing cloud gate, CORS, correlation, and compression behavior.
- [ ] Run the focused test and `python -m pytest tests/ -v --ignore=tests/postgres`; expect pass.
- [ ] Commit:

```powershell
git add backend/security_headers.py backend/tests/test_security_headers.py backend/main.py
git commit -m "security: restrict analytics connections in HTML CSP"
```

## Task 8: Document free-tier setup, privacy gate, funnels, and release verification

**Files:**

- Create: `docs/operations/posthog-activation-analytics.md`
- Create: `docs/operations/activation-analytics-browser-check.md`
- Modify: `docs/compliance/data-processing-inventory.md`
- Modify: `deploy/cloudrun.md`
- Modify: `.github/workflows/ci.yml` only if the final test commands are not already covered.

**Runbook contents:**

- One EU project, no payment card, production only.
- Recorded free allowance at design date: 1,000,000 analytics events/month, one project, one-year retention, unlimited members, 5,000 replays, 1,000,000 feature-flag requests, 100,000 exceptions, 1,500 surveys. Portfyl uses analytics events only; replay/surveys/flags/exceptions remain disabled.
- Environment: `VITE_POSTHOG_KEY=<public project token>` and `VITE_POSTHOG_HOST=https://eu.i.posthog.com` are build-time variables, not backend runtime secrets.
- No-card rule and desired quota behavior: ingestion stops at the free limit; product behavior is unaffected.

- [ ] Write the PostHog project setup steps: select EU region, create one production project, do not add billing method, copy project token, verify disabled features, add `portfyl.com` and `app.portfyl.com`, and restrict team membership.
- [ ] Document the exact 12-event allowlist and forbidden data list from this plan.
- [ ] Document three saved funnels exactly:
  1. landing → demo start → demo activation → signup CTA;
  2. signup CTA → signup start → signup complete;
  3. signup complete → portfolio data import → first populated dashboard → user activation.
- [ ] State that person-level cross-host/date conversion is valid only for accepted analytics; rejected cookieless traffic is aggregate and must not be interpreted as a persistent person.
- [ ] Add live-debugger verification: accept path, reject path, pending zero-request path, event property inspection, logout reset, workspace transition, blocked endpoint, invalid key, and free-limit behavior.
- [ ] Add first-month monitoring: weekly event volume, unexpected property audit, funnel sanity, consent split, quota remaining, and confirmation no payment card was added.
- [ ] Update the compliance inventory with PostHog Cloud EU as a processor/subprocessor, the exact approved data categories, consent basis subject to legal review, EU region, retention, and disabled capabilities.
- [ ] Add an explicit production blocker: do not provide the two Vite variables until the public privacy notice/subprocessor disclosure has received qualified Czech/EU legal review and is published. Do not invent legal text in this implementation.
- [ ] Update Cloud Run frontend-build documentation with the two Vite variables and note that changing runtime env alone cannot enable them because Vite compiles them.
- [ ] Complete the browser matrix at 390×844, 768×1024, 1024×768, and 1440×900 across landing, all demo routes, register, onboarding/import, dashboard, settings, and logout. Check Premium, Classic light, and Classic dark where available.
- [ ] In browser storage/network panels verify: pending makes no PostHog request/storage; rejected stores only consent preference and sends cookieless events; accepted creates first-party analytics persistence; no captured payload contains forbidden data; blocked PostHog does not change UI behavior.
- [ ] Run all release gates:

```powershell
Push-Location frontend
npm ci
npm test
npm run test:cloud
npm run audit:readability
npm run build
npm run build:cloud
Pop-Location

Push-Location backend
python -m pytest tests/ -v --ignore=tests/postgres
Pop-Location
```

  Run `python -m pytest tests/postgres/ -v` with `TEST_DATABASE_URL` configured because backend code changed. Expect every command to pass.
- [ ] Record exact test counts, build results, browser evidence paths, and any warnings in the browser-check document.
- [ ] Commit:

```powershell
git add docs/operations/posthog-activation-analytics.md docs/operations/activation-analytics-browser-check.md docs/compliance/data-processing-inventory.md deploy/cloudrun.md .github/workflows/ci.yml
git commit -m "docs: add activation analytics operations and privacy gate"
```

## Plan completion gate

- [ ] Run `git diff --check HEAD~8..HEAD` and expect no whitespace errors.
- [ ] Search production source with `rg -n "posthog|capture\(|identify\(" frontend/src backend` and confirm every capture flows through `AnalyticsProvider`/the strict contract and the only SDK import is in `analyticsClient.js`.
- [ ] Search with `rg -ni "email|display_name|workspace_name|portfolio_id|balance|amount|holdings|transactions" frontend/src/analytics` and inspect every match; event payload builders must contain none of those fields.
- [ ] Confirm the PostHog live debugger receives each approved event at most where expected, with no extra properties.
- [ ] Confirm no payment card is attached and production variables remain unset until the privacy gate is closed.
- [ ] Use `superpowers:verification-before-completion` and report actual command outputs before declaring the roadmap complete.
