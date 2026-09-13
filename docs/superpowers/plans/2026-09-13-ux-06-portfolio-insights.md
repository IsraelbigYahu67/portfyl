# UX Plan 6: Portfolio Insight Decisions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Dashboard, Allocation, and Analytics distinct decision-making purposes, a deliberate hierarchy, and non-visual explanations of every changed chart.

**Architecture:** Derive attention signals and allocation categories with pure client helpers over existing API payloads. Reshape page composition without adding backend endpoints: Dashboard prioritizes value/performance/concentration/attention, Allocation owns composition, and Analytics owns comparative risk and relationships.

**Tech Stack:** React 18, TanStack Query, React Router, Recharts, Vitest/Testing Library.

**Spec:** `docs/superpowers/specs/2026-09-13-portfyl-ux-product-coherence-design.md` (§10.1–§10.3, §13)

## Global Constraints

- Consume Plan 1 formatters and dividend/tax trust fields; do not restate financial values with page-local helpers.
- Consume Plan 2 `AsyncSection`, Plan 3 `AppShell`/navigation, Plan 4 `groupPositions(holdings, 7)`, `AllocationBarList`, and `topAbsoluteCorrelationPairs`, and Plan 5's screener jobs unchanged.
- Dashboard order is portfolio hero → performance → concentration/holdings → alerts/upcoming events → top movers; insider activity is below and collapsed by default.
- Dashboard alerts are deterministic: single-position concentration above 25%, dividend `income_status === "review"`, incomplete tax FX in the local edition, and earnings/dividend events within 14 calendar days.
- Allocation owns composition and offers Position, Sector, Asset type, and Currency categories. Account appears only when the payload actually provides an account dimension.
- Allocation charts show at most seven named segments plus Other. Full breakdown lists every item with label, value, and percentage. Active is default; sold positions are separate.
- Analytics owns comparative risk/relationships. Remove Sector Allocation, Country Exposure, and Asset Type Breakdown from Analytics.
- Correlation remains top ten pairs by default with an explicit maximum of 12 matrix selections from Plan 4.
- Color is not the only status signal; every changed chart gets a visible summary or table/list equivalent.
- Use current tokens and components; no new chart/UI/state dependency.
- Work on `codex/ux-06-portfolio-insights` after Plan 5 merges; target `codex/portfyl-ux-overhaul`, never `main`.

Run before editing:

```powershell
$branch = (git branch --show-current).Trim()
if ($branch -eq 'main') { throw 'Refusing to work on main' }
git status --short
```

## File Structure

- Create `frontend/src/lib/portfolioAlerts.js` + tests: deterministic attention signals.
- Modify edition manifests/local API: local tax completeness signal without bundling local code into cloud.
- Create `frontend/src/components/DashboardAttention.jsx` + tests.
- Modify `Dashboard.jsx`/`DashboardGrid.jsx` + tests: hierarchy, migration, keyboard controls.
- Create `frontend/src/lib/allocationBreakdown.js` + tests and `AllocationBreakdownList.jsx` + tests.
- Modify `Allocation.jsx`: category/active-sold composition.
- Create `frontend/src/components/ui/ChartSummary.jsx` + tests.
- Modify `Analytics.jsx` + tests: risk-first composition and remove allocation duplicates.

---

## Task 1: Pure portfolio attention-signal derivation

**Files:**
- Create: `frontend/src/lib/portfolioAlerts.js`
- Create: `frontend/src/lib/portfolioAlerts.test.js`

**Interfaces:**
- Produces: `derivePortfolioAlerts({ holdings, dividends, taxReport, earnings, today }) -> Array<{ id, severity, title, detail, to }>`.

- [ ] **Step 1: Write failing tests**

```js
import { derivePortfolioAlerts } from "./portfolioAlerts";

it("creates a concentration alert above 25 percent", () => {
  const alerts = derivePortfolioAlerts({ holdings: [{ ticker: "AAPL", weight: 25.1 }], today: "2026-09-13" });
  expect(alerts).toContainEqual(expect.objectContaining({ id: "concentration-AAPL", to: "/allocation", severity: "warning" }));
});

it("includes dividend review, missing tax FX, and events in the next 14 days", () => {
  const alerts = derivePortfolioAlerts({
    dividends: [{ ticker: "BAD", income_status: "review", warnings: ["provider_fields_disagree"], ex_date: "2026-09-20" }],
    taxReport: { summary: { fx_complete: false } },
    earnings: [{ ticker: "MSFT", date: "2026-09-27" }],
    today: "2026-09-13",
  });
  expect(alerts.map((a) => a.id)).toEqual(expect.arrayContaining(["dividend-review-BAD", "tax-fx", "dividend-event-BAD", "earnings-MSFT"]));
});

it("excludes events outside the window and produces stable order", () => {
  const alerts = derivePortfolioAlerts({ earnings: [{ ticker: "LATE", date: "2026-09-28" }], today: "2026-09-13" });
  expect(alerts).toEqual([]);
});
```

- [ ] **Step 2: Prove failure**

Run: `cd frontend && npm test -- portfolioAlerts.test.js`

- [ ] **Step 3: Implement deterministic rules**

Use date-only arithmetic at UTC midnight to avoid timezone shifts. Sort severity `critical`, `warning`, `info`, then date/id. Exact alert routes: concentration `/allocation`, dividend `/dividends`, tax `/tax-report`, earnings `/`.

```js
const DAY = 86_400_000;
const parseDay = (iso) => iso ? Date.parse(`${iso}T00:00:00Z`) : NaN;
const within = (iso, today, days) => {
  const delta = (parseDay(iso) - parseDay(today)) / DAY;
  return Number.isFinite(delta) && delta >= 0 && delta <= days;
};
```

Deduplicate a reviewed dividend that is also upcoming into two signals because one concerns estimate quality and the other an event; IDs must remain unique.

- [ ] **Step 4: Verify and commit**

Run: `cd frontend && npm test -- portfolioAlerts.test.js`

```powershell
git add frontend/src/lib/portfolioAlerts.js frontend/src/lib/portfolioAlerts.test.js
git commit -m "feat(dashboard): derive deterministic portfolio attention signals"
```

## Task 2: Edition-safe tax completeness signal

**Files:**
- Modify: `frontend/src/editions/localApi.js`
- Modify: `frontend/src/editions/local.jsx`
- Modify: `frontend/src/editions/cloud.jsx`
- Modify: `frontend/src/edition.test.jsx`

**Interfaces:**
- Produces from both manifests: `fetchEditionDashboardSignals() -> Promise<{ taxReport: object | null }>`; local calls the local Tax Report helper, cloud resolves `{ taxReport: null }` without importing local API code.

- [ ] **Step 1: Add failing edition assertions**

In local-mode tests mock the local tax request and assert the manifest export returns it. In cloud-mode assertions inspect the built/imported cloud manifest and assert it returns null and `frontend/src/editions/localApi.js` is not imported.

- [ ] **Step 2: Prove failure**

Run: `cd frontend && npm test -- edition.test.jsx && npm run test:cloud -- edition.test.jsx`

- [ ] **Step 3: Add symmetric manifest exports**

```js
// local.jsx
import { fetchLocalTaxReport } from "./localApi";
export const fetchEditionDashboardSignals = async () => ({ taxReport: await fetchLocalTaxReport() });

// cloud.jsx
export const fetchEditionDashboardSignals = async () => ({ taxReport: null });
```

If the local helper is currently named `fetchTaxReport`, export it from `localApi.js` as `fetchLocalTaxReport` and update existing local consumers in the same commit; do not move it into shared `api.js`.

- [ ] **Step 4: Verify both editions and commit**

Run: `cd frontend && npm test -- edition.test.jsx && npm run test:cloud -- edition.test.jsx && npm run build:cloud`

```powershell
git add frontend/src/editions/localApi.js frontend/src/editions/local.jsx frontend/src/editions/cloud.jsx frontend/src/edition.test.jsx
git commit -m "feat(editions): expose local-only dashboard tax completeness signal"
```

## Task 3: Dashboard attention surface and deliberate order

**Files:**
- Create: `frontend/src/components/DashboardAttention.jsx`
- Create: `frontend/src/components/DashboardAttention.test.jsx`
- Modify: `frontend/src/pages/Dashboard.jsx`
- Modify: `frontend/src/pages/Dashboard.async.test.jsx`

**Interfaces:**
- Consumes: `derivePortfolioAlerts`, `fetchEditionDashboardSignals`, existing holdings/dividends/earnings queries.
- Produces: `DashboardAttention({ alerts, isLoading, error, onRetry })`.

- [ ] **Step 1: Write failing component/page tests**

```jsx
it("renders named alert links and an all-clear state", () => {
  const { rerender } = render(<DashboardAttention alerts={[{ id: "x", severity: "warning", title: "Concentration", detail: "AAPL is 30%", to: "/allocation" }]} />);
  expect(screen.getByRole("link", { name: /concentration/i })).toHaveAttribute("href", "/allocation");
  rerender(<DashboardAttention alerts={[]} />);
  expect(screen.getByText(/nothing needs attention/i)).toBeInTheDocument();
});
```

At page level assert headings appear in DOM order: Portfolio value, Performance, Concentration, Needs attention, Top movers, Insider activity.

- [ ] **Step 2: Prove failure**

Run: `cd frontend && npm test -- DashboardAttention.test.jsx Dashboard.async.test.jsx`

- [ ] **Step 3: Implement and compose**

Use an ordered list; every item has icon plus severity text, title/detail, and a real `<Link>`. Add Dashboard queries for dividends and edition signals with independent `AsyncSection`s and derive alerts with the current date. Replace “Portfolio Overview” with `<h1 tabIndex={-1}>Dashboard</h1>`.

Place the widgets in this fixed non-edit order: performance; a two-column concentration block containing holdings + heatmap; attention block containing alerts + earnings; movers; `<details>` insider activity with summary `Insider activity (1Y)` closed by default.

- [ ] **Step 4: Verify and commit**

Run: `cd frontend && npm test -- DashboardAttention.test.jsx Dashboard.async.test.jsx`

```powershell
git add frontend/src/components/DashboardAttention.jsx frontend/src/components/DashboardAttention.test.jsx frontend/src/pages/Dashboard.jsx frontend/src/pages/Dashboard.async.test.jsx
git commit -m "feat(dashboard): prioritize performance concentration and attention"
```

## Task 4: Accessible Dashboard customization and stored-layout migration

**Files:**
- Modify: `frontend/src/components/DashboardGrid.jsx`
- Create: `frontend/src/components/DashboardGrid.test.jsx`

**Interfaces:**
- Produces: labelled `Move up`, `Move down`, `Hide`, `Restore`, and `Reset` controls; unknown stored IDs are discarded once.

- [ ] **Step 1: Write failing keyboard/control tests**

Seed localStorage with `['retired-widget','movers','performance']`. Render the grid and assert the retired item is absent. Click `Move performance up`, assert DOM order and stored value change; click `Hide movers`, then `Restore movers`, and assert focusable named buttons exist. Assert mobile/non-edit rendering is always one DOM column/order even if grid layout coordinates exist.

- [ ] **Step 2: Prove failure**

Run: `cd frontend && npm test -- DashboardGrid.test.jsx`

- [ ] **Step 3: Implement order-first persistence**

Add `ORDER_KEY = "sb_dashboard_widget_order_v2"`. Normalize stored IDs with:

```js
export function normalizeWidgetOrder(stored, knownIds) {
  const valid = (Array.isArray(stored) ? stored : []).filter((id, index, all) => knownIds.includes(id) && all.indexOf(id) === index);
  return [...valid, ...knownIds.filter((id) => !valid.includes(id))];
}
```

Render labelled buttons in edit chrome; disable Move up/down at boundaries. Drag completion updates the same logical order. Hide removes only visibility; Restore inserts according to the normalized default order. Keep desktop resize/drag optional; hide editing controls below `lg` with a visible note that ordering follows the saved sequence.

- [ ] **Step 4: Verify and commit**

Run: `cd frontend && npm test -- DashboardGrid.test.jsx`

```powershell
git add frontend/src/components/DashboardGrid.jsx frontend/src/components/DashboardGrid.test.jsx
git commit -m "feat(dashboard): add keyboard-equivalent layout controls and migration"
```

## Task 5: Allocation category derivation and full breakdown

**Files:**
- Create: `frontend/src/lib/allocationBreakdown.js`
- Create: `frontend/src/lib/allocationBreakdown.test.js`
- Create: `frontend/src/components/AllocationBreakdownList.jsx`
- Create: `frontend/src/components/AllocationBreakdownList.test.jsx`
- Modify: `frontend/src/pages/Allocation.jsx`
- Create: `frontend/src/pages/Allocation.decisions.test.jsx`

**Interfaces:**
- Produces: `allocationRows({ category, holdings, breakdown }) -> Array<{ name, value, weight }>` and `boundedAllocationRows(rows, maxNamed = 7)`; `AllocationBreakdownList({ rows, currency })`.

- [ ] **Step 1: Write failing helper/component tests**

```js
it.each([
  ["sector", "sectors"], ["asset_type", "asset_types"], ["currency", "currencies"],
])("maps %s to its API dimension", (category, key) => {
  const breakdown = { [key]: [{ name: "One", value: 70, weight: 70 }, { name: "Two", value: 30, weight: 30 }] };
  expect(allocationRows({ category, holdings: [], breakdown })).toEqual(breakdown[key]);
});

it("bounds eight rows to seven plus Other while the list retains all eight", () => {
  const rows = Array.from({ length: 8 }, (_, i) => ({ name: `R${i}`, value: 8 - i, weight: 20 - i }));
  expect(boundedAllocationRows(rows)).toHaveLength(8);
  expect(allocationRows({ category: "sector", breakdown: { sectors: rows } })).toHaveLength(8);
});
```

Component tests assert sorted listitems expose label, formatted value, and percentage; page tests assert category tabs and active/sold separation.

- [ ] **Step 2: Prove failure**

Run: `cd frontend && npm test -- allocationBreakdown.test.js AllocationBreakdownList.test.jsx Allocation.decisions.test.jsx`

- [ ] **Step 3: Implement helpers**

For `position`, map active holdings to ticker/value/weight. For API dimensions, clone/sort the matching array. `boundedAllocationRows` sorts descending, returns all rows when ≤7, otherwise seven plus `{ name: "Other", value: sum, weight: sum, items: rest }` rounded to two decimals.

- [ ] **Step 4: Reshape Allocation**

Use a labelled `SegmentedControl` (Position, Sector, Asset type, Currency; Account only if `breakdown.accounts` exists). The selected category controls the one donut and the full list. Keep `AllocationBarList` as the Position implementation or adapt it to call `AllocationBreakdownList`; do not maintain two sorting algorithms.

Add `Active positions` / `Sold positions` tabs. Active owns chart/list. Sold renders a separate disclosure/table using `closed === true`, never chart slices. Add summary copy: largest category and top-three combined weight.

- [ ] **Step 5: Verify and commit**

Run: `cd frontend && npm test -- allocationBreakdown.test.js AllocationBarList.test.jsx AllocationBreakdownList.test.jsx Allocation.decisions.test.jsx positionsPie.test.js`

```powershell
git add frontend/src/lib/allocationBreakdown.js frontend/src/lib/allocationBreakdown.test.js frontend/src/components/AllocationBreakdownList.jsx frontend/src/components/AllocationBreakdownList.test.jsx frontend/src/pages/Allocation.jsx frontend/src/pages/Allocation.decisions.test.jsx frontend/src/components/AllocationBarList.jsx
git commit -m "feat(allocation): make composition categories bounded and decision-focused"
```

## Task 6: Shared chart summary and Analytics risk-first composition

**Files:**
- Create: `frontend/src/components/ui/ChartSummary.jsx`
- Create: `frontend/src/components/ui/ChartSummary.test.jsx`
- Modify: `frontend/src/components/ui/index.js`
- Modify: `frontend/src/pages/Analytics.jsx`
- Create: `frontend/src/pages/Analytics.decisions.test.jsx`

**Interfaces:**
- Produces: `ChartSummary({ title, children })`, a visible `<details>` text/table alternative tied to its chart by accessible name.

- [ ] **Step 1: Write failing tests**

```jsx
it("renders a named disclosure with supplied non-visual data", () => {
  render(<ChartSummary title="Performance chart data"><table><tbody><tr><td>Portfolio</td><td>12%</td></tr></tbody></table></ChartSummary>);
  expect(screen.getByRole("group", { name: "Performance chart data" })).toHaveTextContent("Portfolio12%");
});
```

Analytics test resolves metrics/comparison/correlation and asserts risk metrics precede benchmark comparison, strongest correlations remain, every section displays period/data-loaded context, and headings `Sector Allocation`, `Country Exposure`, `Asset Type Breakdown` are absent.

- [ ] **Step 2: Prove failure**

Run: `cd frontend && npm test -- ChartSummary.test.jsx Analytics.decisions.test.jsx`

- [ ] **Step 3: Implement summary and reshape Analytics**

`ChartSummary` uses `<details role="group" aria-label={title}>` and a visible `View data summary` summary. In Analytics remove `fetchSectorBreakdown`, its query, and all three allocation blocks. Order: page purpose/period+benchmark controls; risk overview; benchmark comparison; risk-adjusted returns/drawdown; strongest correlation pairs; advanced matrix.

Use TanStack query `dataUpdatedAt` to render `Period: {period} · Data loaded {format time}` per data block. Add `ChartSummary` tables for benchmark chart and correlation pairs. Metric cards keep their existing info text and add period context in `sub` where absent.

- [ ] **Step 4: Add summaries to changed Dashboard/Allocation charts**

In Dashboard performance and heatmap/concentration, and Allocation donut, add a `ChartSummary` containing the exact values already used by the visual. Reuse the same derived arrays; do not recompute a second data source.

- [ ] **Step 5: Verify and commit**

Run: `cd frontend && npm test -- ChartSummary.test.jsx Analytics.decisions.test.jsx Dashboard.async.test.jsx Allocation.decisions.test.jsx`

```powershell
git add frontend/src/components/ui/ChartSummary.jsx frontend/src/components/ui/ChartSummary.test.jsx frontend/src/components/ui/index.js frontend/src/pages/Analytics.jsx frontend/src/pages/Analytics.decisions.test.jsx frontend/src/pages/Dashboard.jsx frontend/src/pages/Allocation.jsx
git commit -m "feat(insights): focus Analytics on comparative risk with chart summaries"
```

## Task 7: Phase verification and browser matrix

**Files:**
- Create: `docs/superpowers/plans/ux-06-portfolio-insights-verification.md`

- [ ] **Step 1: Run frontend gates**

```powershell
cd frontend
npm test
npm run test:cloud
npm run build
npm run build:cloud
```

- [ ] **Step 2: Browser matrix**

At 390×844, 768×1024, 1024×768, and 1440×900 verify Dashboard order, independent failure recovery, keyboard Move/Hide/Restore, collapsed insider activity, alerts and links; Allocation category/state behavior, seven-plus-Other and complete text list; Analytics risk-first order, no allocation duplicates, top-ten correlations and max-12 matrix; chart summaries; no overflow/console/network regressions.

- [ ] **Step 3: Record and commit evidence**

```powershell
git add docs/superpowers/plans/ux-06-portfolio-insights-verification.md
git commit -m "docs(ux): record portfolio-insights phase verification"
```

## Self-review notes

- Dashboard §10.1 maps to Tasks 1–4; Allocation §10.2 to Task 5; Analytics §10.3 to Task 6.
- Tax completeness crosses editions only through symmetric manifest exports, preserving cloud static exclusion.
- No backend transport, schema, queue, or page purpose outside these three routes is introduced.
