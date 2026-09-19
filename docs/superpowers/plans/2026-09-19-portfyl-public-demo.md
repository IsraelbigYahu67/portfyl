# Portfyl Public Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a cloud-only, anonymous, read-only demo at `portfyl.com/demo` with ten approved synthetic assets and five product experiences, without mounting authentication or making portfolio/backend market-data requests.

**Architecture:** `Root.jsx` classifies the marketing host and lazy-loads an isolated `DemoBootstrap` before `TrackerBootstrap`. `DemoBootstrap` owns a BrowserRouter, immutable validated fixture provider, and demo-only route tree. Demo pages compose existing presentational components, while data fetching, mutations, Firebase, and authenticated providers remain unreachable from the public bundle.

**Tech Stack:** React 18, React Router 7, Vite 6 cloud edition, Recharts 2, Vitest 4, Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-19-portfyl-public-demo-activation-readability-design.md`

**Prerequisite:** Complete `docs/superpowers/plans/2026-09-19-portfyl-readability-system.md` first.

## Fixed product decisions

- Routes: `/demo`, `/demo/allocation`, `/demo/analytics`, `/demo/dividends`, `/demo/stock/:ticker`.
- Assets: VUAA, MSFT, JPM, JNJ, XOM, PG, AMZN, CAT, NEE, PLD.
- Weights: 18%, 12%, 10%, 10%, 9%, 9%, 9%, 8%, 8%, 7% in the same order.
- VUAA display name is `Vanguard S&P 500 UCITS ETF`; do not imply a live exchange quote.
- Base fixture currency is USD, positions total USD 100,000, and cash is USD 5,000.
- Fixture `asOf` is `2026-09-18`; displayed values always disclose that they are synthetic and as-of that date.
- Registration CTA target is `${VITE_APP_ORIGIN || "https://app.portfyl.com"}/register?source=demo`.
- Omit all write controls and all links to Import, Settings, Transactions, Assistant, Watchlists, Options, Tax Report, and Screener.

---

## Task 1: Establish the cloud-only public route boundary

**Files:**

- Modify: `frontend/src/lib/routes.js`
- Modify: `frontend/src/Root.jsx`
- Modify: `frontend/src/Root.test.jsx`
- Create: `frontend/src/demo/DemoBootstrap.jsx`

**Interfaces:**

- `routes.js` exports `isDemoPath(pathname)` and `isTrackerHost(hostname)` in addition to existing exports.
- `isDemoPath` returns true only when `HAS_PUBLIC_HOME` and pathname matches `/demo` or begins `/demo/`.
- Root selection order is demo on a non-tracker host, public home, then tracker.

- [ ] Extend `Root.test.jsx` with cloud/local conditional cases for `/demo`, `/demo/allocation`, `/demolition`, and the hostname `app.portfyl.com`.
- [ ] Mock `./demo/DemoBootstrap` as `<div>Public demo</div>` and assert `/demo` renders it only in the cloud edition and only when the host is not `app.portfyl.com`.
- [ ] Assert `/demolition` and `app.portfyl.com/demo` render the protected tracker, and the public demo never appears.
- [ ] Run `cd frontend; npm test -- --run src/Root.test.jsx` and confirm failure because the demo classifier/bootstrap does not exist.
- [ ] Add pure helpers:

```js
export const isDemoPath = (pathname) =>
  HAS_PUBLIC_HOME && (pathname === "/demo" || pathname.startsWith("/demo/"));
export const isTrackerHost = (hostname) =>
  hostname.toLowerCase() === "app.portfyl.com";
```

- [ ] Create a temporary `DemoBootstrap` that renders `<main>Portfyl demo</main>`; it will be replaced in Task 3.
- [ ] In `Root.jsx`, add `const Demo = HAS_PUBLIC_HOME ? lazy(() => import("./demo/DemoBootstrap")) : null`; compute `showDemo` before `showWelcome`; use `demo`, `welcome`, or `tracker` as the RouteBoundary key.
- [ ] Preserve the `popstate` listener and lazy/Suspense fallback. Do not import DemoBootstrap synchronously.
- [ ] Run both editions:

```powershell
cd frontend
npm test -- --run src/Root.test.jsx
npm run test:cloud -- --run src/Root.test.jsx
```

  Expect local to route `/demo` to the tracker and cloud marketing host to route it to the demo.
- [ ] Commit:

```powershell
git add frontend/src/lib/routes.js frontend/src/Root.jsx frontend/src/Root.test.jsx frontend/src/demo/DemoBootstrap.jsx
git commit -m "feat: add isolated public demo boundary"
```

## Task 2: Build and validate the deterministic fixture

**Files:**

- Create: `frontend/src/demo/demoPortfolio.js`
- Create: `frontend/src/demo/validateDemoPortfolio.js`
- Create: `frontend/src/demo/validateDemoPortfolio.test.js`

**Data contract:**

```js
{
  version: 1,
  asOf: "2026-09-18",
  currency: "USD",
  cash: 5000,
  holdings: [{ symbol, name, sector, country, currency, assetType,
               weight, quantity, currentPrice, marketValue, averageCost,
               dayChange, dayChangePercent, dividendYield, fundamentals }],
  transactions: [{ id, date, symbol, type: "BUY", quantity, price, amount }],
  dividends: [{ id, date, symbol, amount, currency }],
  dividendTotal: 0,
  performance: [{ date, value, invested, pnl, pnl_pct, total_pnl, total_pnl_pct }],
  benchmarks: { sp500: [{ date, pct }] },
  benchmarkMeta: [{ key: "sp500", label: "S&P 500", color: "var(--chart-5)" }]
}
```

- [ ] Write validator tests asserting the exact symbol order, ten unique sectors/roles, exact weights summing to 100 within 0.01, position total 100,000 within one cent, non-zero cash, two years of weekly performance, and at least six dividend rows across four quarters.
- [ ] Add mutation tests that deep-clone the fixture and prove `assertDemoPortfolio` throws for: 9 holdings, duplicate symbol, duplicate/missing sector, weight mismatch, `NaN`, missing as-of, invalid date, missing history, quantity/transaction mismatch, and dividend-total mismatch.
- [ ] Run `cd frontend; npm test -- --run src/demo/validateDemoPortfolio.test.js` and confirm failure because both modules are absent.
- [ ] Define a `HOLDING_SEEDS` array with the fixed symbols, names, sectors, weights, and synthetic current prices. Use these sectors: Diversified ETF, Information Technology, Financials, Health Care, Energy, Consumer Staples, Consumer Discretionary, Industrials, Utilities, Real Estate.
- [ ] Calculate each `marketValue` as `weight * 1000`, each quantity as `marketValue / currentPrice`, and `averageCost` as 90% of current price. Create two staggered BUY lots per symbol whose quantities sum to the holding quantity within `0.00001` and whose amounts sum to a USD 90,000 portfolio cost basis within one cent. Round persisted monetary fields to cents and quantities to six decimals.
- [ ] Generate 105 Friday performance points ending `2026-09-18` with a deterministic formula and no randomness:

```js
const cycle = Math.sin(index / 7) * 900 + Math.cos(index / 13) * 450;
const value = round2(72000 + index * 310 + cycle);
const invested = round2(70000 + Math.floor(index / 13) * 2500);
```

  After generating the raw series, add one constant offset to every `value` so the final point equals USD 105,000 exactly; do not special-case only the last point. Derive all P&L fields from the adjusted value and invested amount. Generate the benchmark from `index * 0.21 + Math.sin(index / 9) * 1.8`.
- [ ] Add deterministic dividends for MSFT, JPM, JNJ, XOM, PG, NEE, and PLD across at least eight quarters. Export both rows and `dividendTotal = round2(sum(amount))`.
- [ ] Give every holding fundamentals needed by the stock view: `price`, `previousClose`, `marketCap`, `pe`, `forwardPe`, `eps`, `revenueGrowth`, `profitMargin`, `dividendYield`, `week52Low`, `week52High`, `nextEarnings`, and a two-sentence synthetic company description.
- [ ] Implement `assertDemoPortfolio(data)` as a pure function returning the original validated object. Every failure message names the broken invariant.
- [ ] Freeze the exported fixture recursively in development/test so demo components cannot mutate it.
- [ ] Run the focused tests and expect all to pass.
- [ ] Commit:

```powershell
git add frontend/src/demo/demoPortfolio.js frontend/src/demo/validateDemoPortfolio.js frontend/src/demo/validateDemoPortfolio.test.js
git commit -m "feat: add validated synthetic demo portfolio"
```

## Task 3: Add the read-only provider, shell, translations, and route tree

**Files:**

- Create: `frontend/src/demo/DemoDataContext.jsx`
- Create: `frontend/src/demo/DemoShell.jsx`
- Create: `frontend/src/demo/demoCopy.js`
- Create: `frontend/src/demo/DemoApp.jsx`
- Create: `frontend/src/demo/DemoApp.test.jsx`
- Modify: `frontend/src/demo/DemoBootstrap.jsx`

**Interfaces:**

- `DemoDataProvider({ children, value = demoPortfolio })` validates `value` once and exposes it through `useDemoData()`.
- `useDemoData()` throws `useDemoData must be used inside DemoDataProvider` outside the provider.
- `DemoApp` owns Routes; unknown `/demo/*` renders a branded unavailable/not-found state with a link to `/demo`.
- `demoCopy.js` contains Czech, English, and German strings selected by `LANGUAGE_KEY`; no network localization.

- [ ] Write routing tests for all five routes and an unknown child route. Initially use route placeholder headings supplied as test-only children or minimal page stubs inside the test mock.
- [ ] Assert the shell contains a navigation landmark, active-link state, synthetic-data disclosure, `asOf` date, link back to `/`, and registration CTA with `source=demo`.
- [ ] Assert no button/link text matches import, sync, edit, delete, settings, assistant, transaction, or refresh in Czech/English/German.
- [ ] Add an invalid-provider-value test that receives the branded `Demo unavailable` state through a local error boundary rather than a blank screen.
- [ ] Run `cd frontend; npm test -- --run src/demo/DemoApp.test.jsx` and confirm failure.
- [ ] Implement `DemoDataContext`, memoizing only the validated immutable value.
- [ ] Add exact shell translations for: Overview/Přehled/Übersicht; Allocation/Složení/Aufteilung; Analytics/Analytika/Analyse; Dividends/Dividendy/Dividenden; Synthetic demo/Syntetická ukázka/Synthetische Demo; Create account/Vytvořit účet/Konto erstellen; Back home/Zpět na web/Zur Startseite.
- [ ] Implement `DemoShell` with desktop and horizontally scrollable mobile nav, visible keyboard focus, and semantic typography from the readability plan.
- [ ] Implement lazy demo page imports in `DemoApp`; create temporary page modules with route headings if Tasks 4–6 have not yet created them, but include those temporary modules in this task's commit so the tree always builds.
- [ ] Replace temporary `DemoBootstrap` with:

```jsx
export default function DemoBootstrap() {
  return (
    <BrowserRouter>
      <DemoDataProvider><DemoApp /></DemoDataProvider>
    </BrowserRouter>
  );
}
```

- [ ] Run focused tests and `npm run build:cloud`; expect pass.
- [ ] Commit:

```powershell
git add frontend/src/demo
git commit -m "feat: add public demo shell and routing"
```

## Task 4: Implement Overview and Allocation from shared components

**Files:**

- Modify: `frontend/src/demo/pages/DemoOverview.jsx`
- Create: `frontend/src/demo/pages/DemoOverview.test.jsx`
- Modify: `frontend/src/demo/pages/DemoAllocation.jsx`
- Create: `frontend/src/demo/pages/DemoAllocation.test.jsx`

**Component mapping:**

- Overview uses `PortfolioHero`, `PerformanceChart`, `MetricCard`, and a semantic holdings table.
- Allocation uses `AllocationChart`, `AllocationBreakdownList`, and `KpiBox`.
- Pass `currency="USD"`; do not mount `useCurrency`, `usePortfolio`, React Query, or authenticated contexts.

- [ ] In Overview tests, render under `DemoDataProvider`/MemoryRouter and assert USD 105,000 net worth, ten holdings, VUAA and MSFT rows, chart accessible summary, and stock links under `/demo/stock/`.
- [ ] In Allocation tests, assert position weights total 100%, every approved asset is present in the textual breakdown, sector count is ten, and the pie chart has a text/table equivalent.
- [ ] Add a test that mocks `frontend/src/api.js` methods to throw on any call and asserts both pages still render. Also spy on `global.fetch` and assert it is not called.
- [ ] Run both tests and confirm failure while pages are placeholders.
- [ ] Derive Overview summary from fixture fields: `net_worth = 105000`, `total_value = 100000`, `cash = 5000`, `total_invested` from performance's final `invested`, `total_pnl` as position value minus cost basis, `total_dividends`, `holdings_count = 10`, and final weekly day change.
- [ ] Render the 24-month performance series and benchmark using props only. Keep benchmark controls local with `useState`; they may hide/show the fixed synthetic benchmark.
- [ ] Render a responsive holdings table with symbol, name, sector, value, weight, and signed P&L. Link each symbol/name to its demo stock route.
- [ ] Build Allocation rows for holdings, sectors, countries, currencies, and asset types. Only the holdings breakdown needs every symbol visible; provide local segmented controls for the other dimensions.
- [ ] Ensure all numbers use the semantic classes and all chart/text summaries use the same formatted values.
- [ ] Run focused tests and expect pass.
- [ ] Commit:

```powershell
git add frontend/src/demo/pages/DemoOverview.jsx frontend/src/demo/pages/DemoOverview.test.jsx frontend/src/demo/pages/DemoAllocation.jsx frontend/src/demo/pages/DemoAllocation.test.jsx
git commit -m "feat: add demo overview and allocation"
```

## Task 5: Implement Analytics and Dividends

**Files:**

- Modify: `frontend/src/demo/pages/DemoAnalytics.jsx`
- Create: `frontend/src/demo/pages/DemoAnalytics.test.jsx`
- Modify: `frontend/src/demo/pages/DemoDividends.jsx`
- Create: `frontend/src/demo/pages/DemoDividends.test.jsx`

**Displayed analytics:** total return, annualized return, volatility, Sharpe ratio, maximum drawdown, best month, worst month, and portfolio/benchmark performance.

- [ ] Add Analytics tests that assert all eight labels, finite formatted values, one signed return, benchmark legend, and an accessible summary/table.
- [ ] Add Dividends tests that assert total dividend income equals fixture `dividendTotal`, at least six rows, multiple payers, quarterly grouping, and a non-color-only year-over-year direction.
- [ ] Mock API/fetch as in Task 4 and confirm neither page makes a request.
- [ ] Run both tests and confirm failure.
- [ ] Create pure local derivations from the performance array: weekly returns, annualized return using 52 periods, annualized sample volatility, Sharpe with zero synthetic risk-free rate, running peak/drawdown, and calendar-month returns. Guard division by zero and require finite output.
- [ ] Display metric results with shared `MetricCard`/`KpiBox`; render performance with shared `PerformanceChart`.
- [ ] Aggregate dividends by symbol, quarter, and year. Render a quarterly bar/list view plus a complete dividend table sorted newest first.
- [ ] State that dividend events and returns are synthetic; do not present them as forecasts.
- [ ] Run focused tests and expect pass.
- [ ] Commit:

```powershell
git add frontend/src/demo/pages/DemoAnalytics.jsx frontend/src/demo/pages/DemoAnalytics.test.jsx frontend/src/demo/pages/DemoDividends.jsx frontend/src/demo/pages/DemoDividends.test.jsx
git commit -m "feat: add demo analytics and dividends"
```

## Task 6: Implement the stock detail route safely

**Files:**

- Modify: `frontend/src/demo/pages/DemoStock.jsx`
- Create: `frontend/src/demo/pages/DemoStock.test.jsx`

**Interfaces:**

- URL symbols are normalized with `decodeURIComponent(symbol).trim().toUpperCase()` and matched only against fixture holdings.
- Valid stock pages use shared `StockHeader` and `KpiBox`; they never mount `StockOverviewTab` or any query-owning tab.
- Invalid symbols render a not-found state and links back to `/demo` and `/demo/allocation`.

- [ ] Test all ten approved symbols with `it.each`, asserting the display name and synthetic disclosure.
- [ ] Test lowercase `msft` normalization and invalid/encoded symbols.
- [ ] Assert the page contains price, day change with sign, market cap, P/E, forward P/E, EPS, revenue growth, profit margin, dividend yield, 52-week range, next earnings, description, portfolio value, and portfolio weight.
- [ ] Assert no Add transaction, alert, note, refresh, import, edit, or AI action is present.
- [ ] Mock `../api`, React Query's query function boundary, and `global.fetch` to throw; assert render completes with zero calls.
- [ ] Run `cd frontend; npm test -- --run src/demo/pages/DemoStock.test.jsx` and confirm failure.
- [ ] Adapt the fixture holding into the `StockHeader` data shape with only static fields. If `StockHeader` requires an authenticated-only field, pass a neutral static value rather than changing the public route to use context.
- [ ] Compose sections with KpiBox and semantic tables; do not render authenticated StockDetail tabs.
- [ ] Add a compact holding-context card linking back to Allocation.
- [ ] Run focused test and expect pass.
- [ ] Commit:

```powershell
git add frontend/src/demo/pages/DemoStock.jsx frontend/src/demo/pages/DemoStock.test.jsx
git commit -m "feat: add read-only demo stock detail"
```

## Task 7: Add localized landing entry points

**Files:**

- Modify: `frontend/src/pages/welcomeCopy.js`
- Modify: `frontend/src/pages/Welcome.jsx`
- Modify: `frontend/src/pages/Welcome.css`
- Modify: `frontend/src/pages/Welcome.test.jsx`

**Copy contract:**

- Czech: `Vyzkoušet živé demo`; English: `Try the live demo`; German: `Live-Demo ausprobieren`.
- FAQ answer no longer says public access is unavailable; it states that the demo is synthetic and account-free.

- [ ] Update Welcome tests for all languages to assert an above-the-fold `/demo` link and retain the screenshot-preview link as the secondary CTA.
- [ ] Replace the old test that every landing link is hash-only with a narrower assertion: navigation links are hashes, demo is `/demo`, and no external link is introduced.
- [ ] Assert the demo CTA remains a normal anchor so open-in-new-tab and keyboard navigation work.
- [ ] Run `cd frontend; npm test -- --run src/pages/Welcome.test.jsx` and confirm failure.
- [ ] Add `demoCta` and revised FAQ copy to all three language objects.
- [ ] Add the CTA beside the existing preview CTA in the hero and once in the closing section. Keep one primary visual hierarchy and a visible focus state.
- [ ] Update CSS responsively without lowering the typography floors established by the readability plan.
- [ ] Run the focused test and expect pass.
- [ ] Commit:

```powershell
git add frontend/src/pages/welcomeCopy.js frontend/src/pages/Welcome.jsx frontend/src/pages/Welcome.css frontend/src/pages/Welcome.test.jsx
git commit -m "feat: link landing page to public demo"
```

## Task 8: Prove public isolation, edition behavior, and production builds

**Files:**

- Create: `frontend/src/demo/demoIsolation.test.jsx`
- Create: `docs/operations/public-demo-release-check.md`
- Modify: `frontend/vite.config.js` only if a test-only chunk assertion requires existing Vite configuration; do not merge demo and tracker chunks.

- [ ] In `demoIsolation.test.jsx`, use `vi.resetModules()` and mocks that throw during import for `../TrackerBootstrap`, `../auth/firebase`, and `../api`; dynamically import Root at `/demo` in cloud mode and assert the demo renders. This proves the route boundary, not only zero runtime calls.
- [ ] Add a fixture-wide render test that walks `/demo`, the three analysis child routes, `/demo/dividends`, and all ten stock URLs without console errors or unhandled promise rejections.
- [ ] Assert every rendered demo route includes the synthetic/as-of disclosure and registration CTA.
- [ ] Assert all mutation verbs/controls remain absent across the route walk.
- [ ] Run `npm run test:cloud -- --run src/demo` and expect pass.
- [ ] Run `npm run build:cloud`, inspect `dist/assets`, and record that demo and tracker are separate lazy chunks in the release checklist.
- [ ] Run local `npm test -- --run src/Root.test.jsx` and `npm run build`; confirm local `/demo` remains within the tracker boundary and the build succeeds.
- [ ] Write the release checklist covering all five route types, 390×844/768×1024/1024×768/1440×900 viewports, keyboard traversal, unknown route behavior, no page-level horizontal scroll, no network calls beyond static assets, source maps/console, and Premium/Classic light/Classic dark.
- [ ] Run the full frontend gates:

```powershell
cd frontend
npm test
npm run test:cloud
npm run audit:readability
npm run build
npm run build:cloud
```

  Expect every command to pass. Record test totals and built demo/tracker chunk names in the handoff.
- [ ] Commit:

```powershell
git add frontend/src/demo/demoIsolation.test.jsx docs/operations/public-demo-release-check.md
git commit -m "test: verify public demo isolation and release gates"
```

## Plan completion gate

- [ ] Run `git diff --check HEAD~8..HEAD` and expect no whitespace errors.
- [ ] Confirm the approved asset list and weights exactly match the fixed product decisions above.
- [ ] Confirm browser network inspection shows no `/api`, Firebase, Yahoo, or live market-data request from any demo route.
- [ ] Continue with `docs/superpowers/plans/2026-09-19-portfyl-activation-analytics.md` only after this plan is green.
