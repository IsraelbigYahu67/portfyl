# UX Plan 8: Assistant Privacy and Performance Closeout — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make portfolio sharing in Assistant explicit and server-enforced, cut the initial authenticated-shell JavaScript/CSS transfer by at least 30%, replace the global data sweep with bounded startup and intent prefetching, and close the eight-phase program with a complete local/cloud browser walkthrough.

**Architecture:** Extend `POST /api/assistant/chat` with a fail-safe `context_mode` contract and response provenance, then add a conversation-scoped consent flow that reuses the shared focus trap. Move authenticated routes behind stable `React.lazy` entries, keep edition-only loaders inside their build-time manifests, and use the same route loaders for navigation intent. Replace `AutoLoad` with three dashboard cache warms and a 150 ms stock-link intent coordinator. Measure the static initial entry graph from Vite's manifest before and after the performance changes; dynamic route chunks are excluded from the initial graph rather than renamed to disguise transfer size.

**Tech Stack:** FastAPI + Pydantic + SQLAlchemy, React 18, React Router 7, TanStack Query 5, Vite 6, Vitest/Testing Library, pytest, Node's `zlib`/test runner.

**Spec:** `docs/superpowers/specs/2026-09-13-portfyl-ux-product-coherence-design.md` (§4.3, §4.4, §11, §12, §13, §16)

**Branch:** `codex/ux-08-assistant-performance`
**Depends on:** Plan 7 (`codex/ux-07-product-flows`) merged into `codex/portfyl-ux-overhaul`
**Merges into:** `codex/portfyl-ux-overhaul`; the later integration PR to `main` requires owner approval after this plan's complete walkthrough.

This is the closeout phase. It consumes Plan 2's `AsyncSection`, Plan 3's `AppShell` and `useFocusTrap`, Plan 4's bounded collection routes, Plan 5's explicit screener job flow, Plan 6's final Dashboard query keys, and Plan 7's URL-backed Stock and Settings sections. In particular, preserve Plan 7's shared `components/ui/UrlTabs.jsx`, Stock coordinator in `pages/Stock.jsx`, tab components under `components/stock/`, and `?section=connections|preferences|notifications|data` Settings contract. Do not recreate any of those interfaces locally. Preserve the import preview/duplicate/undo workflow from `2026-09-07-portfyl-onboarding-import-safety-design.md` and the account export/deletion rules from `2026-09-07-portfyl-data-export-account-deletion-design.md` during final QA.

## Global constraints and release contracts

- `context_mode` has exactly two wire values: `none` and `portfolio_summary`. An omitted value is interpreted as `none`; an unknown value returns HTTP 422.
- The server, rather than UI copy, owns the privacy boundary. `_build_portfolio_context` is not called for `none`. `portfolio_summary` retains the existing workspace/portfolio-scoped snapshot and its existing caps of 25 open positions and 15 recent transactions.
- Consent is scoped to the current in-memory conversation. It is not persisted in localStorage, a user setting, the database, or a cookie. Starting a new conversation clears consent and makes the active mode visible again.
- The consent dialog names DeepSeek/the configured model and lists the categories sent: tickers, quantities, cost/prices and approximate values, and recent trade details. It states that market data may be delayed. The safe secondary action is exactly **Ask without portfolio data** and the explicit primary action is exactly **Share for this conversation**.
- The response envelope keeps the existing `reply` and `usage` fields for compatibility and adds `provider`, `context_mode`, and `context_as_of`. `context_as_of` is an ISO-8601 UTC timestamp only when a portfolio snapshot was built and is `null` for `none`. No prompt, portfolio snapshot, raw secret, or API key is returned.
- Every authenticated page route is lazy. Public auth pages may stay eager. Local-only Tax Report/Screener loaders exist only in `editions/local.jsx`; the cloud manifest and cloud chunks contain neither page.
- Route hover/focus preloads only that route's chunk. Stock-link hover/focus loads the Stock chunk immediately, then waits 150 ms before prefetching that ticker's Overview fundamentals and one-year history. Leaving/blurring before 150 ms performs no data request.
- Authenticated startup warms only `summary`, `holdings`, and default `performance` for the active currency. `PortfolioProvider`'s already-required `portfolios` query is the current-portfolio metadata warm. No startup code calls transactions, notes, watchlists, dividends, analytics, settings, fundamentals, or history endpoints.
- A portfolio switch continues to remove the entire query cache before the new ID becomes active. Currency/portfolio changes cancel pending intent timers and cancel/remove incompatible intent-prefetched queries. Market-global stock entries may be retained only when their query keys and request semantics are demonstrably independent of both scopes.
- The measured initial graph is the Vite `index.html` entry, all recursive static `imports`, and their JavaScript/CSS files. `dynamicImports`, fonts, images, and source maps are reported separately or excluded explicitly. The same script and gzip level are used before and after. Success requires both local and cloud combined initial JS+CSS gzip to be at most 70% of their Plan-7 baselines, and the report also compares against the specification's historical ~372 KB gzip figure.
- Keep the existing visual tokens and edition capability filtering. Add no router/state/component library, service worker, queue, or persistence migration.
- Use TDD: add a failing behavioral test before each behavioral change. Commit only the named files with explicit `git add` paths. Never reset, discard, or stage another worker's changes.

## Branch and status guard

Run before editing, after confirming Plan 7 is merged:

```powershell
$expectedBranch = 'codex/ux-08-assistant-performance'
$branch = (git branch --show-current).Trim()
if ($branch -ne $expectedBranch) { throw "Expected $expectedBranch, got $branch" }

git merge-base --is-ancestor codex/ux-07-product-flows HEAD
if ($LASTEXITCODE -ne 0) { throw 'Plan 7 is not an ancestor of this phase; stop and refresh the integration base.' }

git status --short
```

The status must be clean at the start. If it contains unexplained files, stop and identify their owner; do not clean or stage them. Before every commit, repeat `git status --short` and `git diff --check`.

## File structure

- Modify `backend/routers/assistant.py`.
- Create `backend/tests/test_assistant_context.py`.
- Modify `frontend/src/api.js`.
- Modify `frontend/src/pages/Assistant.jsx`.
- Create `frontend/src/pages/Assistant.privacy.test.jsx`.
- Create `frontend/src/components/AssistantContextDialog.jsx` and `.test.jsx`.
- Create `frontend/scripts/measure-initial-bundle.mjs` and `.test.mjs`; modify `frontend/package.json`.
- Create `frontend/src/routes/authenticatedRoutes.jsx` and `.test.jsx`.
- Create `frontend/src/components/layout/RouteFallback.jsx` and `.test.jsx`.
- Modify `frontend/src/App.jsx`, `frontend/src/App.routing.test.jsx`, `frontend/src/editions/local.jsx`, `frontend/src/editions/cloud.jsx`, and `frontend/src/edition.test.jsx`.
- Modify `frontend/src/components/layout/navigation.js`, `DesktopSidebar.jsx`, `MobileNavDrawer.jsx`, and their tests.
- Create `frontend/src/hooks/useStockIntentPrefetch.js` and `.test.jsx`.
- Modify `frontend/src/components/StockDetail.jsx`, `frontend/src/pages/Search.jsx`, `frontend/src/pages/Watchlists.jsx`, `frontend/src/api.js`, and focused page tests touched by Plan 7.
- Delete `frontend/src/components/AutoLoad.jsx`.
- Create `frontend/src/components/StartupPrefetch.jsx` and `.test.jsx`; modify `frontend/src/App.jsx`.
- Create `docs/superpowers/plans/ux-08-assistant-performance-verification.md`.

Plan 7 keeps `components/StockDetail.jsx` as the compatibility barrel for current named exports and creates `components/stock/StockOverviewTab.jsx`, `StockFinancialsTab.jsx`, `StockValuationTab.jsx`, `StockOwnershipTab.jsx`, and `StockFilingsTab.jsx`. Keep intent in the shared `TickerLink` export/barrel and the Overview query contract in `pages/Stock.jsx`; do not put parallel intent logic into the five tab components. If review changes that final Plan-7 ownership before merge, update the explicit paths in this plan and verification report before editing.

---

## Task 1: Add a reproducible initial-bundle measurement and capture the Plan-7 baseline

**Files:**
- Create: `frontend/scripts/measure-initial-bundle.mjs`
- Create: `frontend/scripts/measure-initial-bundle.test.mjs`
- Modify: `frontend/package.json`

**Interfaces:**
- Produces `collectInitialAssets(manifest, entry = "index.html")`, which recursively follows `imports` and collects entry/static JS and CSS while returning `dynamicImports` separately.
- CLI: `node scripts/measure-initial-bundle.mjs [dist-directory]`; reads `<dist>/.vite/manifest.json`, gzips each initial JS/CSS file with Node `zlib.gzipSync(..., { level: 9 })`, and writes a deterministic JSON report to stdout with per-asset raw/gzip bytes and totals.
- Produces package command `npm run measure:bundle`; it reads `frontend/dist` and never changes source files.

- [ ] **Step 1: Write the failing graph test**

Use a synthetic manifest with one entry, two recursive static imports, CSS at both levels, and two dynamic imports. Assert the collected initial set contains the entry/static JS and CSS exactly once and does not contain either dynamic chunk. Add a cycle/duplicate fixture so traversal cannot double-count a shared vendor chunk. Test deterministic lexical output order.

- [ ] **Step 2: Prove failure**

Run: `cd frontend && node --test scripts/measure-initial-bundle.test.mjs`

Expected: FAIL because the measurement module does not exist.

- [ ] **Step 3: Implement the graph collector and CLI**

Fail with a non-zero exit and a clear message when the manifest, `index.html` entry, or referenced asset is missing. Report at least:

```json
{
  "entry": "index.html",
  "initial_js_gzip_bytes": 0,
  "initial_css_gzip_bytes": 0,
  "initial_combined_gzip_bytes": 0,
  "initial_combined_gzip_kib": 0,
  "assets": [],
  "excluded_dynamic_imports": []
}
```

Do not count filenames or Vite chunk names as evidence of improvement; totals come from file bytes. Add `"measure:bundle": "node scripts/measure-initial-bundle.mjs dist"` to `package.json`.

- [ ] **Step 4: Verify the utility**

Run: `cd frontend && node --test scripts/measure-initial-bundle.test.mjs`

- [ ] **Step 5: Capture untouched Plan-7 local and cloud baselines before Task 2**

```powershell
cd frontend
npm run build -- --manifest
npm run measure:bundle | Tee-Object "$env:TEMP\portfyl-ux08-baseline-local.json"
npm run build:cloud -- --manifest
npm run measure:bundle | Tee-Object "$env:TEMP\portfyl-ux08-baseline-cloud.json"
```

Copy both totals, the complete Vite asset tables, the commit SHA, Node version, and commands into the Task 8 verification report. Compute each hard target as `floor(baseline_initial_combined_gzip_bytes * 0.70)`; do not substitute the older approximate 372 KB figure for the fresh Plan-7 baseline.

- [ ] **Step 6: Commit only the measurement harness**

```powershell
git add frontend/scripts/measure-initial-bundle.mjs frontend/scripts/measure-initial-bundle.test.mjs frontend/package.json
git commit -m "chore(perf): measure the initial Vite entry graph"
```

---

## Task 2: Enforce the Assistant context boundary in the backend

**Files:**
- Modify: `backend/routers/assistant.py`
- Create: `backend/tests/test_assistant_context.py`

**Interfaces:**
- `ChatRequest.context_mode: Literal["none", "portfolio_summary"] = "none"`.
- `_system_prompt(context: str | None)` returns a general Assistant prompt with no portfolio language/snapshot delimiter when context is `None`.
- Existing `POST /assistant/chat` response remains `{ reply, model, usage, ... }` and adds `provider: "deepseek"`, echoed validated `context_mode`, and `context_as_of: str | null`.

- [ ] **Step 1: Write failing contract tests**

Cover these cases in `test_assistant_context.py`:

1. `ChatRequest(messages=[...])` defaults `context_mode` to `none`.
2. An unknown mode fails Pydantic validation.
3. `_system_prompt(None)` contains no `PORTFOLIO SNAPSHOT`, active portfolio name, holding, or transaction language.
4. A direct async `chat` call with `none`, an encrypted test key, and mocked `_call_deepseek` never invokes a spied `_build_portfolio_context`; the provider receives only the general system prompt plus bounded chat history.
5. A `portfolio_summary` call invokes `_build_portfolio_context` exactly once for the injected, workspace-scoped `portfolio`, passes its snapshot only in the system message, and retains the existing 25-position/15-transaction caps.
6. Both modes return `provider`, `model`, `context_mode`, and `context_as_of`; `none` returns null while summary returns a parseable timezone-aware UTC timestamp.
7. The response object contains no `messages`, `prompt`, `portfolio_context`, API key, or secret fields.

Mock the provider call; tests must make no network request and must assert hosted-usage reservation behavior remains unchanged for BYOK and hosted paths.

- [ ] **Step 2: Prove failure**

Run: `cd backend && python -m pytest tests/test_assistant_context.py -v`

- [ ] **Step 3: Implement fail-safe request branching**

Import `Literal` and introduce `PROVIDER = "deepseek"`. Validate/filter history before any context build or hosted quota reservation, as today. Set `context_as_of = None`; only inside the exact `portfolio_summary` branch call `_build_portfolio_context(db, portfolio)` and capture `datetime.now(timezone.utc).isoformat()`. Pass `None` to `_system_prompt` for mode `none`.

Do not infer sharing from prompt text, prior messages, configuration, entitlement, or presence of a portfolio. Do not change `_build_portfolio_context`'s workspace/portfolio predicates or increase its caps.

- [ ] **Step 4: Verify backend compatibility**

Run:

```powershell
cd backend
python -m pytest tests/test_assistant_context.py tests/test_assistant.py tests/test_usage_quotas.py tests/test_plan_enforcement.py -v
```

- [ ] **Step 5: Commit**

```powershell
git add backend/routers/assistant.py backend/tests/test_assistant_context.py
git commit -m "feat(assistant): enforce explicit portfolio context modes"
```

---

## Task 3: Add conversation-scoped consent and truthful response details

**Files:**
- Modify: `frontend/src/api.js`
- Modify: `frontend/src/pages/Assistant.jsx`
- Create: `frontend/src/pages/Assistant.privacy.test.jsx`
- Create: `frontend/src/components/AssistantContextDialog.jsx`
- Create: `frontend/src/components/AssistantContextDialog.test.jsx`

**Interfaces:**
- `sendAssistantMessage(messages, contextMode = "none")` sends `{ messages, context_mode: contextMode }`.
- `AssistantContextDialog({ open, provider, model, onWithoutContext, onShare })` is a labelled modal `role="dialog"` backed by `useFocusTrap`.
- Assistant conversation state owns `requestedMode`, `consentedToPortfolioSummary`, pending text, messages, and response metadata. None is persisted.

- [ ] **Step 1: Write failing dialog accessibility tests**

Assert that the open dialog:

- names DeepSeek and the configured model;
- lists tickers, quantities, prices/values, recent trades, and delayed-market-data language;
- has the exact safe/primary button labels from the spec;
- traps Tab/Shift+Tab, closes to `none` on Escape, and restores focus to the send control;
- does not render when `open=false`.

Escape and backdrop dismissal must invoke `onWithoutContext`; they must never silently grant sharing.

- [ ] **Step 2: Write failing Assistant flow tests**

Cover:

1. New conversations visibly start in `none`; sending calls `sendAssistantMessage(messages, "none")` with no dialog.
2. Selecting `portfolio_summary` changes the visible active-mode label but the first send pauses before the API call and opens consent.
3. **Ask without portfolio data** sends the pending message with `none` and updates the mode indicator.
4. **Share for this conversation** sends with `portfolio_summary`; later sends in the same conversation do not ask again.
5. **New conversation** clears messages, response details, pending consent, and the grant; selecting summary and sending asks again.
6. Changing the mode back to `none` before send cannot attach summary context.
7. Response details display provider/model, `Portfolio summary shared` or `No portfolio data shared`, and the formatted `context_as_of` only when present.
8. UI copy no longer claims it is always aware of/can see the portfolio and never calls the response live, guaranteed, cited, or personalized financial advice.
9. API/config/loading/error behavior from `ResearchPages.async.test.jsx` remains intact.

- [ ] **Step 3: Prove failure**

Run: `cd frontend && npm test -- AssistantContextDialog.test.jsx Assistant.privacy.test.jsx ResearchPages.async.test.jsx`

- [ ] **Step 4: Implement the consent state machine**

Use a visible labelled choice beside the composer (`none` / `portfolio_summary`), not an implicit toggle hidden in Settings. Default `requestedMode` to `none`. When a summary send lacks this conversation's grant, retain the pending message and open the dialog without appending/sending it twice. The safe action switches mode to `none` and sends once; the share action records the in-memory grant and sends once with summary.

Store provider metadata on the assistant message object for rendering, but serialize only `{ role, content }` conversation history to the backend. Add a compact `<details>` below assistant responses. `context_as_of` is displayed through the shared date/time formatter if Plan 1 exposes one; otherwise add one shared formatter in `frontend/src/lib/format.js` with a focused test rather than calling `toLocaleString` in the page.

Keep the existing DeepSeek key configuration and hosted entitlement handling. Replace claims such as “aware of your active portfolio” and “I can see…” with conditional, factual copy.

- [ ] **Step 5: Verify both editions**

Run:

```powershell
cd frontend
npm test -- AssistantContextDialog.test.jsx Assistant.privacy.test.jsx ResearchPages.async.test.jsx
npm run test:cloud -- AssistantContextDialog.test.jsx Assistant.privacy.test.jsx ResearchPages.async.test.jsx
```

- [ ] **Step 6: Commit**

Include `frontend/src/lib/format.js` and its test only if Step 4 required a new shared timestamp formatter.

```powershell
git add frontend/src/api.js frontend/src/pages/Assistant.jsx frontend/src/pages/Assistant.privacy.test.jsx frontend/src/components/AssistantContextDialog.jsx frontend/src/components/AssistantContextDialog.test.jsx
# When changed in Step 4, also run:
git add frontend/src/lib/format.js frontend/src/lib/format.test.js
git commit -m "feat(assistant): require conversation-scoped portfolio consent"
```

---

## Task 4: Move authenticated routes behind edition-safe lazy loaders

**Files:**
- Create: `frontend/src/routes/authenticatedRoutes.jsx`
- Create: `frontend/src/routes/authenticatedRoutes.test.jsx`
- Create: `frontend/src/components/layout/RouteFallback.jsx`
- Create: `frontend/src/components/layout/RouteFallback.test.jsx`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/App.routing.test.jsx`
- Modify: `frontend/src/editions/local.jsx`
- Modify: `frontend/src/editions/cloud.jsx`
- Modify: `frontend/src/edition.test.jsx`

**Interfaces:**
- Each shared route entry is stable at module scope: `{ path, Component: lazy(loader), preload: loader }`.
- `SHARED_AUTHENTICATED_ROUTES` covers Dashboard, Allocation, Transactions, Import, Dividends, Analytics, Search, Stock, Watchlists, Assistant, Settings, and authenticated Onboarding where applicable after Plan 7.
- Edition entries retain `{ path, capability, Component, preload }`; each manifest defines its loader and `lazy(loader)` in the same edition file.
- `RouteFallback` renders a `role="status"`, an accessible “Loading page…” label, and a shell-sized skeleton without viewport overflow.

- [ ] **Step 1: Write failing registry/fallback tests**

Assert all authenticated paths have distinct loader functions, `preload()` returns the import promise, and route matching treats `/stock/AAPL` as `/stock/:ticker` without importing it during registry evaluation. Test that `RouteFallback` has a status name and stable minimum height.

Update routing tests to render through `<Suspense fallback={<RouteFallback />}>`, wait for the lazy Dashboard, and retain redirect/capability assertions. Add an assertion over `App.jsx?raw` or the registry source that no authenticated page has a static import in `App.jsx`.

- [ ] **Step 2: Add failing edition assertions**

Assert both manifests expose `preload` for each enabled route. In cloud mode, inspect cloud manifest/build sources and assert no import/load string for `TaxReport`, `Screener`, or `localApi`; in local mode assert those loaders resolve only when requested. Pricing remains cloud-only.

- [ ] **Step 3: Prove failure**

Run: `cd frontend && npm test -- authenticatedRoutes.test.jsx RouteFallback.test.jsx App.routing.test.jsx edition.test.jsx`

- [ ] **Step 4: Implement shared lazy routes and Suspense boundary**

Move the authenticated page import functions out of `App.jsx` into `authenticatedRoutes.jsx`. Keep `Login`, `Register`, `VerifyEmail`, and `ForgotPassword` eager. Render one shared `<Suspense>` around the authenticated route switch. Do not create lazy components inside `AppLayout` or `.map()`, because changing component identity remounts pages.

Onboarding occurs before `AppShell`; if it becomes lazy, give it the same `RouteFallback` inside `AuthGate`. The `/overview` and wildcard redirects stay eager route declarations.

- [ ] **Step 5: Implement edition-local loaders without breaking static exclusion**

In each manifest, define loader functions only for that edition. Example shape:

```jsx
const loadTaxReport = () => import("../pages/TaxReport");
const LazyTaxReport = lazy(loadTaxReport);

export const EDITION_ROUTES = Object.freeze([
  { path: "/tax-report", capability: "tax_report", Component: LazyTaxReport, preload: loadTaxReport },
]);
```

Do not import a combined registry containing local routes from the cloud manifest.

- [ ] **Step 6: Verify focused tests and builds**

```powershell
cd frontend
npm test -- authenticatedRoutes.test.jsx RouteFallback.test.jsx App.routing.test.jsx edition.test.jsx
npm run test:cloud -- authenticatedRoutes.test.jsx RouteFallback.test.jsx App.routing.test.jsx edition.test.jsx
npm run build -- --manifest
npm run build:cloud -- --manifest
```

Inspect each manifest: authenticated pages must appear as dynamic chunks, while local-only routes are absent from the cloud manifest and output. A chunk warning by itself is not acceptance; Task 8 evaluates measured initial bytes.

- [ ] **Step 7: Commit**

```powershell
git add frontend/src/routes/authenticatedRoutes.jsx frontend/src/routes/authenticatedRoutes.test.jsx frontend/src/components/layout/RouteFallback.jsx frontend/src/components/layout/RouteFallback.test.jsx frontend/src/App.jsx frontend/src/App.routing.test.jsx frontend/src/editions/local.jsx frontend/src/editions/cloud.jsx frontend/src/edition.test.jsx
git commit -m "perf(routes): lazy-load authenticated pages by edition"
```

---

## Task 5: Prefetch route chunks from explicit navigation intent

**Files:**
- Modify: `frontend/src/components/layout/navigation.js`
- Modify: `frontend/src/components/layout/DesktopSidebar.jsx`
- Modify: `frontend/src/components/layout/DesktopSidebar.test.jsx`
- Modify: `frontend/src/components/layout/MobileNavDrawer.jsx`
- Modify: `frontend/src/components/layout/MobileNavDrawer.test.jsx`
- Modify: `frontend/src/App.jsx`

**Interfaces:**
- `buildNavGroups(editionEntries, capabilities, sharedRoutes)` attaches the matching stable `preload` function to each visible shared/edition item.
- Desktop and mobile links invoke `preload` on `mouseenter` and keyboard `focus`; rejection is caught because navigation still owns error rendering.

- [ ] **Step 1: Write failing navigation tests**

Pass groups containing two items with separate `vi.fn(() => Promise.resolve())` preload functions. Assert hover/focus on item A invokes only A, no preload runs on initial render, capability-hidden edition entries cannot preload, and rejected preloads create no unhandled error or navigation failure. Retain active-state, drawer-close, and focus-restoration tests.

- [ ] **Step 2: Prove failure**

Run: `cd frontend && npm test -- navigation.test.js DesktopSidebar.test.jsx MobileNavDrawer.test.jsx`

- [ ] **Step 3: Wire route intent to the same loaders used by React.lazy**

Pass `SHARED_AUTHENTICATED_ROUTES` into `buildNavGroups` from `AppLayout`; do not duplicate import expressions in navigation components. Both presentations receive the same enriched group data. Call `Promise.resolve(preload()).catch(() => {})` from a small shared handler in `navigation.js` so both views have identical rejection behavior.

- [ ] **Step 4: Verify and commit**

```powershell
cd frontend
npm test -- navigation.test.js DesktopSidebar.test.jsx MobileNavDrawer.test.jsx App.routing.test.jsx edition.test.jsx
```

```powershell
git add frontend/src/components/layout/navigation.js frontend/src/components/layout/DesktopSidebar.jsx frontend/src/components/layout/DesktopSidebar.test.jsx frontend/src/components/layout/MobileNavDrawer.jsx frontend/src/components/layout/MobileNavDrawer.test.jsx frontend/src/App.jsx
git commit -m "perf(nav): preload lazy routes on hover and focus"
```

---

## Task 6: Prefetch Stock Overview only after 150 ms ticker intent

**Files:**
- Create: `frontend/src/hooks/useStockIntentPrefetch.js`
- Create: `frontend/src/hooks/useStockIntentPrefetch.test.jsx`
- Modify: `frontend/src/components/StockDetail.jsx` (or Plan 7's final shared `TickerLink` file)
- Modify: `frontend/src/pages/Search.jsx`
- Modify: `frontend/src/pages/Watchlists.jsx`
- Modify: `frontend/src/api.js`
- Modify focused Plan-7 Stock/Watchlists tests as required

**Interfaces:**
- `useStockIntentPrefetch(ticker)` returns `onMouseEnter`, `onMouseLeave`, `onFocus`, and `onBlur` props.
- Starting intent immediately calls the `/stock/:ticker` route's stable `preload` function and starts one 150 ms timer.
- When the timer fires, TanStack Query warms `['fundamentals', TICKER]` via `fetchFundamentals(TICKER, { signal, suppressEntitlementPrompt: true })` and `['history', TICKER, '1y']` via an extended `fetchHistory(TICKER, '1y', { signal, suppressEntitlementPrompt: true })`, both with the Stock page's five-minute stale time.

- [ ] **Step 1: Write failing fake-timer tests**

Assert:

1. render alone makes no loader/data request;
2. hover/focus starts the Stock chunk once immediately but no data before 149 ms;
3. exactly at 150 ms it prefetches the uppercase ticker's two exact query keys;
4. mouseleave/blur at 149 ms cancels both data requests;
5. duplicate mouseenter+focus does not create duplicate timers or fetches;
6. unmount, ticker change, portfolio change, and currency change clear the timer;
7. a scope change cancels tagged in-flight intent queries and removes only incompatible intent entries, without flushing unrelated fresh cache;
8. rejected background requests are silent in the UI and do not suppress a later foreground Stock error.

- [ ] **Step 2: Prove failure**

Run: `cd frontend && npm test -- useStockIntentPrefetch.test.jsx`

- [ ] **Step 3: Implement a single intent coordinator per shared link**

Use `useRef` for the timer and current scope, `useQueryClient`, `usePortfolio`, and `useCurrency`. Give prefetched queries metadata such as `{ intentPrefetch: true, portfolioId: currentId, currency }` so cleanup predicates are explicit. Pass TanStack's `signal` to Axios request config. Do not change foreground Stock query keys or stale times.

If fundamentals/history remain market-global and ignore portfolio/currency at the API boundary, document that compatibility in the hook test and retain those completed cache entries across scope changes; pending timers and in-flight requests still cancel. Never briefly expose data that does depend on the prior portfolio/currency.

- [ ] **Step 4: Put all ticker destinations through the shared link**

Enhance the existing `TickerLink` to forward intent handlers and arbitrary children/layout props, then replace the raw Stock links in Search and Watchlists. Preserve real anchor semantics, encoded uppercase symbols, middle-click/new-tab behavior, click propagation handling, and Plan 7's URL-backed Stock tabs.

- [ ] **Step 5: Verify focused flows**

Run the hook test plus the final Plan-7 tests for Search, Watchlists, and all Stock tabs. At minimum:

```powershell
cd frontend
npm test -- useStockIntentPrefetch.test.jsx ResearchPages.async.test.jsx
```

- [ ] **Step 6: Commit**

```powershell
git add frontend/src/hooks/useStockIntentPrefetch.js frontend/src/hooks/useStockIntentPrefetch.test.jsx frontend/src/components/StockDetail.jsx frontend/src/pages/Search.jsx frontend/src/pages/Watchlists.jsx frontend/src/api.js
git commit -m "perf(stock): prefetch overview data after ticker intent"
```

Adjust the explicit paths to Plan 7's extracted shared ticker-link/test files if applicable; never use `git add -A`.

---

## Task 7: Remove the global AutoLoad sweep and retain only bounded startup warms

**Files:**
- Delete: `frontend/src/components/AutoLoad.jsx`
- Create: `frontend/src/components/StartupPrefetch.jsx`
- Create: `frontend/src/components/StartupPrefetch.test.jsx`
- Modify: `frontend/src/App.jsx`

**Interfaces:**
- `StartupPrefetch` reads `ready/currentId` and currency, then calls `queryClient.prefetchQuery` only for:
  - `['summary', currency]` → `fetchSummary(currency)`;
  - `['holdings', currency]` → `fetchHoldings(currency)`;
  - `['performance', currency, 'All']` → `fetchPerformance(currency, 'all')`.
- `PortfolioProvider` remains the sole owner of `['portfolios']`; `StartupPrefetch` does not issue a duplicate metadata call.

- [ ] **Step 1: Write the failing allowlist test**

Mock every API function previously imported by `AutoLoad`. Mount with a ready portfolio and assert only summary, holdings, and default performance are warmed with their exact Dashboard keys/functions. Explicitly assert zero calls for fundamentals, history, transactions, all notes, watchlists, dividends/forecast, benchmark catalog/comparison, risk, correlation, T212 status, movers, earnings, sector breakdown, heatmap, and all-holdings.

Also assert an unready/missing portfolio performs no warm; a currency change uses new currency keys; a portfolio change does not reuse an incompatible portfolio-bound warm; and prefetch rejection does not render an error because each destination owns foreground errors.

- [ ] **Step 2: Prove failure**

Run: `cd frontend && npm test -- StartupPrefetch.test.jsx`

- [ ] **Step 3: Replace AutoLoad**

Delete its import and mount from `App.jsx`, add `StartupPrefetch`, and remove the old file. Do not retain the startup delay, sequential gap, holdings loop, or “rest of sidebar” queue under a new name. TanStack Query dedupes these exact keys when Dashboard is the active route.

- [ ] **Step 4: Add a static regression assertion**

In `StartupPrefetch.test.jsx`, inspect `StartupPrefetch.jsx?raw` or its mocked import surface and assert the forbidden expensive API names are absent. This prevents a later “small” addition from restarting the sweep without updating the allowlist test.

- [ ] **Step 5: Verify and commit**

```powershell
cd frontend
npm test -- StartupPrefetch.test.jsx Dashboard.async.test.jsx App.routing.test.jsx
```

```powershell
git add frontend/src/components/StartupPrefetch.jsx frontend/src/components/StartupPrefetch.test.jsx frontend/src/App.jsx
git rm frontend/src/components/AutoLoad.jsx
git commit -m "perf(startup): replace the global data sweep with dashboard warms"
```

---

## Task 8: Full gates, bundle acceptance, local/cloud browser matrix, and final report

**Files:**
- Create: `docs/superpowers/plans/ux-08-assistant-performance-verification.md`

- [ ] **Step 1: Run formatting/diff hygiene**

```powershell
git status --short
git diff --check
```

Confirm the diff contains no generated `dist`, manifest, baseline JSON, API key, cookies, screenshots with private data, or unrelated worker files.

- [ ] **Step 2: Run backend gates**

```powershell
cd backend
python -m pytest tests/ -v --ignore=tests/postgres
```

This phase changes an API contract but adds no migration, persistence, authentication, membership, workspace predicate, or RLS policy. The PostgreSQL/RLS suite remains mandatory in CI. When Docker is available for the final integration candidate, also run:

```powershell
docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait
cd backend
python -m pytest tests/postgres/ -v
```

Record whether the local PostgreSQL run occurred; never describe CI-only coverage as locally passed.

- [ ] **Step 3: Run complete frontend local/cloud gates**

```powershell
cd frontend
node --test scripts/measure-initial-bundle.test.mjs
npm test
npm run test:cloud
npm run build
npm run build:cloud
```

- [ ] **Step 4: Measure final bundles with the exact baseline method**

```powershell
cd frontend
npm run build -- --manifest
npm run measure:bundle | Tee-Object "$env:TEMP\portfyl-ux08-final-local.json"
npm run build:cloud -- --manifest
npm run measure:bundle | Tee-Object "$env:TEMP\portfyl-ux08-final-cloud.json"
```

For each edition, report baseline/final JS gzip, CSS gzip, combined gzip, byte delta, percentage delta, dynamic route chunks, and target. Pass only if:

```text
final_initial_combined_gzip_bytes <= floor(plan7_baseline_initial_combined_gzip_bytes * 0.70)
```

Also state the result relative to the historical ~372 KB gzip baseline. If either edition misses 30%, inspect the manifest/import graph and continue optimization (for example stable vendor chunks only when they reduce the actual initial graph). Do not waive, round into, or relabel the target.

- [ ] **Step 5: Start the phase worktree servers**

From the worktree, with a migrated disposable/local PostgreSQL database and a test account:

```powershell
cd backend
python -m uvicorn main:app --reload --port 8001
```

In a second shell:

```powershell
cd frontend
$env:VITE_API_PROXY_TARGET='http://localhost:8001'
npm run dev -- --port 5174
```

Use `http://localhost:5174`. Do not use an existing `:5173` tab from another checkout. For the cloud-edition browser check, stop the local frontend or use a third shell against the same phase backend:

```powershell
cd frontend
$env:VITE_API_PROXY_TARGET='http://localhost:8001'
npm exec vite -- --mode edition-cloud --port 5175
```

Use `http://localhost:5175` for cloud capability checks and record both ports.

- [ ] **Step 6: Complete the four-viewport route walkthrough**

At **390×844, 768×1024, 1024×768, and 1440×900**, exercise every available route in both relevant editions:

- public auth: Login, Register, Verify Email, Forgot Password; authenticated first-run Onboarding when a disposable empty workspace is available;
- shared: Dashboard, Allocation, Transactions, Import, Dividends, Analytics, Search, a Stock detail with all five Plan-7 URL tabs, Watchlists, Assistant, and all Plan-7 Settings URL sections;
- local-only: Screener and Tax Report;
- cloud-only: Plans, plus confirmation that Screener/Tax Report links/routes/assets are unavailable.

For each changed or representative async surface verify happy, loading, empty, and forced-error/retry states; URL reload/back/forward; keyboard navigation; route-heading focus; dialogs/drawers; no viewport horizontal overflow; and no unexpected console error or failed request. Preserve the bounded collection/job behaviors from phases 4–6.

- [ ] **Step 7: Verify Assistant privacy in the browser/network panel**

At every viewport:

1. Start a new conversation and confirm `No portfolio data` is visible.
2. Send once in `none`; inspect the request body for `context_mode: "none"` and response metadata for null `context_as_of`.
3. Select portfolio summary and send; confirm no request leaves before the dialog decision.
4. Use Escape/backdrop and **Ask without portfolio data**; each sends or resolves safely without granting sharing.
5. Reopen, choose **Share for this conversation**, and inspect that only `context_mode` plus bounded chat messages cross the browser/server boundary; the server-to-provider snapshot must not appear in the browser response.
6. Confirm later messages reuse the same conversation grant, changing to none works before send, and **New conversation** requires consent again.
7. Confirm response details identify DeepSeek/model/context time and no copy claims live data, citations, guarantees, or financial advice.
8. Repeat with BYOK/local and hosted/cloud configuration where available; secrets never appear in devtools responses or logs.

- [ ] **Step 8: Verify loading and intent behavior in DevTools**

On a cold authenticated load:

- the initial entry graph contains no eager authenticated page modules beyond the shell/auth foundation;
- network requests do not sweep holdings fundamentals/history, transactions, notes, watchlists, dividends, analytics, or settings;
- only portfolio metadata plus Dashboard summary/holdings/default performance may be warmed by startup (Dashboard itself may request its visible secondary widgets);
- hovering/focusing one nav link requests only its route chunk before navigation;
- focusing a ticker requests the Stock chunk immediately, makes no fundamentals/history request at 149 ms, then makes only that ticker's two requests after 150 ms;
- pointer leave/blur before the threshold makes neither data request;
- portfolio/currency changes cancel pending intent and never flash prior-scope values;
- direct deep-link and refresh show `RouteFallback`, then the correct page; an unavailable chunk produces the normal route/app error behavior rather than an unhandled rejection.

Test once with cache disabled and once with warm cache. Record request names and screenshots that contain only synthetic/test data.

- [ ] **Step 9: Write the closeout verification report**

Create `ux-08-assistant-performance-verification.md` with:

- branch SHA and Plan-7 baseline SHA;
- every command, exit code, and test count;
- local/cloud baseline and final bundle tables and exact percentage calculation;
- local/cloud manifest evidence for edition exclusion;
- pass/fail per route and viewport;
- Assistant request/response and consent evidence;
- cold/warm startup and intent request evidence;
- CI link/status, including PostgreSQL/RLS;
- all warnings, unresolved failures, and intentional deferrals.

There may be no silent deferral of the privacy boundary, 150 ms cancellation, AutoLoad removal, edition exclusion, four viewports, or 30% bundle target. If any hard criterion fails, keep the phase open and state it as failed.

- [ ] **Step 10: Commit the evidence**

```powershell
git add docs/superpowers/plans/ux-08-assistant-performance-verification.md
git commit -m "docs(ux): record assistant and performance closeout"
```

## Acceptance checklist

- [ ] Omitted Assistant mode is server-side `none`; invalid modes fail validation.
- [ ] The server builds no portfolio snapshot for `none` and retains 25-position/15-transaction caps for explicit summary mode.
- [ ] The first summary request in every conversation pauses for an accessible, truthful consent dialog; safe dismissal cannot grant sharing.
- [ ] Every send carries the visible mode, and every response exposes provider/model/mode/context timestamp without prompts or secrets.
- [ ] Starting a new conversation clears the in-memory grant; no consent persistence was added.
- [ ] All authenticated shared and edition routes are lazy; cloud output contains no Tax Report/Screener imports or chunks.
- [ ] Hover/focus warms exactly one route chunk; ticker data waits 150 ms and cancels before the threshold.
- [ ] `AutoLoad.jsx` and its holdings/sidebar sweep are gone; startup warming is restricted to summary, holdings, default performance, and already-required portfolio metadata.
- [ ] Scope changes cancel pending intent and prevent stale portfolio/currency data from appearing.
- [ ] Both local and cloud initial combined JS+CSS gzip are at least 30% below their freshly recorded Plan-7 baselines using the same manifest traversal.
- [ ] Backend fast suite, frontend local/cloud suites, local/cloud builds, and mandatory CI PostgreSQL/RLS gate are green.
- [ ] Every route passes the 390×844, 768×1024, 1024×768, and 1440×900 walkthrough with keyboard, async/error, URL, edition, console/network, and overflow checks.
- [ ] The final verification report contains commands, exit codes, bundle arithmetic, browser evidence, warnings, CI links, and no unreported deferrals.

## Self-review notes

- Assistant privacy is enforced twice: the UI requires a conversation grant, and the backend treats omission as `none` and conditionally avoids snapshot construction.
- The route registry owns both `React.lazy` and preloading functions, preventing loader drift. Edition loaders stay in their aliased manifests, preserving build-time exclusion.
- The stock intent delay is measured with fake timers and the browser network panel. Startup allowlist tests make reintroducing an all-page sweep an explicit contract change.
- The bundle gate measures the recursive static entry graph. Dynamic chunks improve startup only when they leave that graph, and the final byte totals decide acceptance.
- This plan adds no database schema/state, new provider, investment recommendation behavior, service worker, or speculative infrastructure.
