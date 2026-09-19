# Portfyl Readability System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make critical financial values, labels, tables, and charts readable in Premium, Classic light, Classic dark, the public landing page, and every application area without redesigning the product.

**Architecture:** Move appearance values into a side-effect-free token module, enforce contrast in unit tests, and expose five semantic typography classes that presentation components consume. Fix shared components before page-level outliers. A deterministic audit script prevents new sub-floor critical text classes while explicit tests cover theme colors and chart defaults.

**Tech Stack:** React 18, Vite 6, Tailwind CSS 3, Recharts 2, Vitest 4, Testing Library, Node 20.

**Spec:** `docs/superpowers/specs/2026-09-19-portfyl-public-demo-activation-readability-design.md`

## Global constraints

- Financial headline values are at least 16 px.
- Ordinary numeric values in cards, lists, tables, chart legends, and chart axes are at least 14 px.
- Secondary non-critical metadata is at least 12 px.
- Critical values, input values, actions, axes, and legends are never below 12 px.
- Normal text contrast is at least 4.5:1. Large text and meaningful non-text UI/chart elements are at least 3:1.
- Use `font-variant-numeric: tabular-nums` for comparable financial values.
- Gains/losses retain an explicit sign or word; color cannot be the only signal.
- Do not shrink mobile text to solve overflow. Wrap, stack, abbreviate units, or add bounded horizontal scrolling.
- Preserve all existing data fetching, mutations, routing, edition filtering, and formatting semantics.
- Do not modify user-owned dirty files in the original checkout. Execute this plan in a clean worktree.

---

## Task 1: Extract theme tokens and test the full contrast matrix

**Files:**

- Create: `frontend/src/lib/themeTokens.js`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/lib/contrast.js`
- Modify: `frontend/src/lib/contrast.test.js`

**Interfaces:**

- `themeTokens.js` exports `PALETTES`, `DARK_SURFACES`, `LIGHT_TOKENS`, `NEU_TOKENS`, `GLASS_CHART`, and `THEME_CONTRAST_PAIRS`.
- `contrast.js` exports `parseColor(color, backdrop)`, `contrastRatio(foreground, background)`, and the existing public exports unchanged.
- `App.jsx` imports tokens; `usePalette`, `resolveDark`, and rendered behavior remain unchanged.

- [ ] Add a failing test in `frontend/src/lib/contrast.test.js` which imports `THEME_CONTRAST_PAIRS` and checks every `kind: "text"` pair against `4.5` and every `kind: "nonText"` pair against `3`.

```js
import { THEME_CONTRAST_PAIRS } from "./themeTokens";

it.each(THEME_CONTRAST_PAIRS)("$theme $name meets contrast", ({ foreground, background, minimum }) => {
  expect(contrastRatio(foreground, background)).toBeGreaterThanOrEqual(minimum);
});
```

- [ ] Add cases proving `contrastRatio` resolves `rgba(...)` over a supplied opaque backdrop and rejects unsupported CSS variables with a clear error.
- [ ] Run `cd frontend; npm test -- --run src/lib/contrast.test.js` and confirm failure because `themeTokens.js` and RGBA compositing do not exist.
- [ ] Create `themeTokens.js` by moving the five constants out of `App.jsx` without changing values yet.
- [ ] Add semantic fields to each appearance: `textPrimary`, `textSecondary`, `textTertiary`, `chartAxis`, `chartGrid`, `focus`, `gain`, and `loss`. Use opaque resolved colors in `THEME_CONTRAST_PAIRS`, including Premium text over `#F3E8DA`, Classic light text over `#FFFFFF`, and Classic dark text over `#131B2E`.
- [ ] Implement color parsing for `#rgb`, `#rrggbb`, and `rgb/rgba`; composite an alpha foreground channel-by-channel with `round(alpha * fg + (1-alpha) * bg)` before calculating luminance.
- [ ] Adjust only semantic color values that fail the matrix. Keep brand hues and layout unchanged.
- [ ] Replace the constant definitions in `App.jsx` with imports from `./lib/themeTokens` and keep `export { NEU_TOKENS } from "./lib/themeTokens"` for existing imports.
- [ ] Run `cd frontend; npm test -- --run src/lib/contrast.test.js src/edition.test.jsx` and expect all tests to pass.
- [ ] Run `cd frontend; npm run build; npm run build:cloud` and expect both builds to succeed.
- [ ] Commit:

```powershell
git add frontend/src/lib/themeTokens.js frontend/src/lib/contrast.js frontend/src/lib/contrast.test.js frontend/src/App.jsx
git commit -m "refactor: centralize accessible theme tokens"
```

## Task 2: Add semantic financial typography primitives

**Files:**

- Modify: `frontend/src/index.css`
- Modify: `frontend/src/components/MetricCard.jsx`
- Modify: `frontend/src/components/MetricCard.test.jsx`
- Modify: `frontend/src/components/ui/KpiBox.jsx`
- Modify: `frontend/src/components/ui/KpiBox.test.jsx`
- Modify: `frontend/src/components/ui/DeltaPill.jsx`
- Modify: `frontend/src/components/ui/SectionHeader.jsx`
- Modify: `frontend/src/components/ui/ChartSummary.jsx`
- Modify: `frontend/src/components/ui/ChartSummary.test.jsx`
- Modify: `frontend/src/components/AllocationBreakdownList.jsx`
- Modify: `frontend/src/components/AllocationBreakdownList.test.jsx`
- Modify: `frontend/src/components/ui/primitives.test.jsx`

**Interfaces:**

- Global semantic classes are exactly `.financial-headline`, `.financial-data`, `.financial-meta`, `.data-label`, and `.chart-label`.
- Components retain their current props and DOM roles.
- `DeltaPill` keeps `size="sm"`, but its smallest rendered text is 12 px.

- [ ] Add assertions to the existing component tests for the exact semantic classes: MetricCard value uses `financial-headline`; KpiBox value uses `financial-data` unless its existing prominent variant uses `financial-headline`; ChartSummary table cells use `financial-data`; AllocationBreakdownList values use `financial-data`; SectionHeader eyebrow uses `data-label`; DeltaPill uses `financial-meta`.
- [ ] Add a CSS source test to `primitives.test.jsx` which reads `src/index.css` and asserts the five class selectors exist with `font-size: 1rem`, `0.875rem`, `0.75rem`, `0.75rem`, and `0.75rem` respectively. Resolve the file with `new URL("../../index.css", import.meta.url)`.
- [ ] Run `cd frontend; npm test -- --run src/components/MetricCard.test.jsx src/components/ui/KpiBox.test.jsx src/components/ui/ChartSummary.test.jsx src/components/AllocationBreakdownList.test.jsx src/components/ui/primitives.test.jsx` and confirm the new assertions fail.
- [ ] Add these declarations under `@layer components` in `index.css`:

```css
.financial-headline { font-size: 1rem; line-height: 1.35; font-weight: 650; color: var(--ink); font-variant-numeric: tabular-nums; }
.financial-data { font-size: 0.875rem; line-height: 1.4; color: var(--ink); font-variant-numeric: tabular-nums; }
.financial-meta { font-size: 0.75rem; line-height: 1.4; color: var(--muted); font-variant-numeric: tabular-nums; }
.data-label { font-size: 0.75rem; line-height: 1.4; font-weight: 600; color: var(--muted); letter-spacing: 0.04em; }
.chart-label { font-size: 0.75rem; line-height: 1.4; color: var(--muted); font-variant-numeric: tabular-nums; }
```

- [ ] Replace `text-[10px]`, `text-[11px]`, `text-xs`, and opacity-based numeric text inside the named shared components with the semantic classes. Keep explanatory prose at `text-sm` or larger.
- [ ] Ensure tooltip bodies and formula notes in `MetricCard` are at least `text-xs`; the primary number remains `financial-headline`.
- [ ] Ensure positive/negative output in `DeltaPill` always includes the formatted sign already supplied by the component; add a test for `+` and `−`/`-` if absent.
- [ ] Run the same focused test command and expect all tests to pass.
- [ ] Commit:

```powershell
git add frontend/src/index.css frontend/src/components/MetricCard.jsx frontend/src/components/MetricCard.test.jsx frontend/src/components/ui frontend/src/components/AllocationBreakdownList.jsx frontend/src/components/AllocationBreakdownList.test.jsx
git commit -m "feat: add semantic financial typography"
```

## Task 3: Standardize chart axes, legends, grids, and summaries

**Files:**

- Modify: `frontend/src/lib/chartTheme.js`
- Create: `frontend/src/lib/chartTheme.test.js`
- Modify: `frontend/src/components/PerformanceChart.jsx`
- Modify: `frontend/src/components/AllocationChart.jsx`
- Modify: `frontend/src/components/BreakdownChart.jsx`
- Modify: `frontend/src/components/CashBalanceChart.jsx`
- Modify: `frontend/src/components/Heatmap.jsx`
- Modify: `frontend/src/components/HeroSparkline.jsx`

**Interfaces:**

- `chartTheme.js` exports `AXIS_TICK_STYLE`, `LEGEND_TEXT_STYLE`, `GRID_STROKE`, `SERIES_STYLES`, and its existing exports.
- `AXIS_TICK_STYLE.fontSize` and `LEGEND_TEXT_STYLE.fontSize` are `12`.
- `SERIES_STYLES` supplies both color and a distinguishable `strokeDasharray`/marker combination for multi-series charts.

- [ ] Add `chartTheme.test.js` asserting the two font sizes are at least 12, grid opacity/stroke is present, and every adjacent series in `SERIES_STYLES` differs by more than color.
- [ ] Add source-level assertions that each named chart imports at least one shared chart theme constant and no longer contains `fontSize: 10` or `fontSize: 11`.
- [ ] Run `cd frontend; npm test -- --run src/lib/chartTheme.test.js` and confirm failure because the exports do not exist.
- [ ] Add the constants to `chartTheme.js`; use CSS variables (`var(--muted)`, `var(--hairline)`, `var(--chart-N)`) rather than raw gray colors.
- [ ] Apply `AXIS_TICK_STYLE` to every visible X/Y axis tick and `LEGEND_TEXT_STYLE` to custom/default legend content in the six charts.
- [ ] Apply `GRID_STROKE` to Cartesian/polar grids and make important reference lines at least 1 CSS px with 3:1 contrast against their chart surface.
- [ ] Apply `SERIES_STYLES` to benchmark/comparison lines in `PerformanceChart`; portfolio and benchmark must differ in dash/marker as well as hue.
- [ ] Keep `HeroSparkline` intentionally label-free but give its meaningful line a 2 px minimum stroke.
- [ ] Confirm every complex chart continues to render its `ChartSummary` or accessible table; add the summary where one is missing.
- [ ] Run `cd frontend; npm test -- --run src/lib/chartTheme.test.js src/components/ui/ChartSummary.test.jsx` and expect pass.
- [ ] Commit:

```powershell
git add frontend/src/lib/chartTheme.js frontend/src/lib/chartTheme.test.js frontend/src/components/PerformanceChart.jsx frontend/src/components/AllocationChart.jsx frontend/src/components/BreakdownChart.jsx frontend/src/components/CashBalanceChart.jsx frontend/src/components/Heatmap.jsx frontend/src/components/HeroSparkline.jsx
git commit -m "feat: standardize accessible chart styling"
```

## Task 4: Audit Dashboard, Allocation, and Analytics

**Files:**

- Modify: `frontend/src/pages/Dashboard.jsx`
- Modify: `frontend/src/pages/Dashboard.async.test.jsx`
- Modify: `frontend/src/pages/Allocation.jsx`
- Modify: `frontend/src/pages/Allocation.decisions.test.jsx`
- Modify: `frontend/src/pages/Analytics.jsx`
- Modify: `frontend/src/pages/Analytics.decisions.test.jsx`
- Modify: `frontend/src/pages/Analytics.async.test.jsx`
- Modify: `frontend/src/components/PortfolioHero.jsx`
- Modify: `frontend/src/components/PortfolioHero.test.jsx`
- Modify: `frontend/src/components/AllocationBarList.jsx`

**Page checklist:**

- Dashboard: portfolio value/P&L headlines, mover values, insider table headers and values, benchmark selector, attention cards.
- Allocation: allocation weights, target/deviation values, sector/country/currency summaries, legends.
- Analytics: return/risk metrics, correlation/heatmap labels, benchmark data, period controls, explanatory metadata.

- [ ] Add assertions to the listed tests that representative headline values use `financial-headline`, ordinary financial cells use `financial-data`, metadata uses `financial-meta`, and actionable period/benchmark controls are never `text-[10px]` or `text-[11px]`.
- [ ] Add a Dashboard assertion that positive/negative results include a sign or wording independent of the gain/loss class.
- [ ] Run the three page test files plus `PortfolioHero.test.jsx` and confirm the new assertions fail.
- [ ] Replace size/opacity utilities on critical values with the semantic classes. Remove combinations such as `text-muted/50` and `opacity-50` from readable data; use `text-muted` and semantic hierarchy instead.
- [ ] Keep dense tables within their container using `overflow-x-auto` on a wrapper and `min-w-*` on the table; do not reduce financial cells below 14 px.
- [ ] Update `PortfolioHero` secondary numeric values from 12 px to `financial-data`; keep labels as `data-label`/`financial-meta`.
- [ ] Update `AllocationBarList` percentage/value output to `financial-data` and text labels to at least 12 px.
- [ ] Run:

```powershell
cd frontend
npm test -- --run src/pages/Dashboard.async.test.jsx src/pages/Allocation.decisions.test.jsx src/pages/Analytics.decisions.test.jsx src/pages/Analytics.async.test.jsx src/components/PortfolioHero.test.jsx
```

  Expect all focused tests to pass.
- [ ] Commit:

```powershell
git add frontend/src/pages/Dashboard.jsx frontend/src/pages/Dashboard.async.test.jsx frontend/src/pages/Allocation.jsx frontend/src/pages/Allocation.decisions.test.jsx frontend/src/pages/Analytics.jsx frontend/src/pages/Analytics.decisions.test.jsx frontend/src/pages/Analytics.async.test.jsx frontend/src/components/PortfolioHero.jsx frontend/src/components/PortfolioHero.test.jsx frontend/src/components/AllocationBarList.jsx
git commit -m "fix: improve core portfolio data readability"
```

## Task 5: Audit income, ledger, cash, watchlist, and options pages

**Files:**

- Modify: `frontend/src/pages/Dividends.jsx`
- Modify: `frontend/src/pages/Dividends.growth.test.jsx`
- Modify: `frontend/src/pages/Dividends.trust.test.jsx`
- Modify: `frontend/src/pages/Transactions.jsx`
- Modify: `frontend/src/pages/Transactions.page.test.jsx`
- Modify: `frontend/src/pages/Cash.jsx`
- Modify: `frontend/src/pages/Cash.test.jsx`
- Modify: `frontend/src/pages/Watchlists.jsx`
- Modify: `frontend/src/pages/Watchlists.flows.test.jsx`
- Modify: `frontend/src/components/watchlists/WatchlistCard.jsx`
- Modify: `frontend/src/components/watchlists/WatchlistCard.test.jsx`
- Modify: `frontend/src/pages/Options.jsx`
- Modify: `frontend/src/components/OptionsCalendar.jsx`
- Create: `frontend/src/components/OptionsCalendar.test.jsx`

**Page checklist:** amount, yield, strike, premium, P&L, balance, price, percentage, table cell, calendar value, and chart label are `financial-data` or `financial-headline`; dates/status/source notes may use `financial-meta`; buttons and inputs remain at least 12 px.

- [ ] Add one representative semantic-class assertion for every page/component listed above. In `OptionsCalendar.test.jsx`, render a week containing an option and assert strike/premium text has `financial-data` and no element uses `text-[9px]`, `text-[10px]`, or `text-[11px]`.
- [ ] Run all listed focused tests and confirm failure.
- [ ] Apply the semantic classes to every critical number. Replace 9–11 px calendar text with 12 px metadata or 14 px values.
- [ ] For narrow calendars/tables, allow horizontal scrolling inside the card and keep the page itself free from horizontal overflow.
- [ ] Ensure table headers are at least 12 px and sorting/filtering controls retain visible focus styles.
- [ ] Ensure gain/loss values preserve explicit signs in Watchlists and Options.
- [ ] Re-run the focused tests and expect pass.
- [ ] Commit:

```powershell
git add frontend/src/pages/Dividends.jsx frontend/src/pages/Dividends.growth.test.jsx frontend/src/pages/Dividends.trust.test.jsx frontend/src/pages/Transactions.jsx frontend/src/pages/Transactions.page.test.jsx frontend/src/pages/Cash.jsx frontend/src/pages/Cash.test.jsx frontend/src/pages/Watchlists.jsx frontend/src/pages/Watchlists.flows.test.jsx frontend/src/components/watchlists frontend/src/pages/Options.jsx frontend/src/components/OptionsCalendar.jsx frontend/src/components/OptionsCalendar.test.jsx
git commit -m "fix: raise readability across portfolio workflows"
```

## Task 6: Audit stock and research surfaces

**Files:**

- Modify: `frontend/src/components/StockDetail.jsx`
- Modify: `frontend/src/components/StockDetail.*.test.*`
- Modify: `frontend/src/components/stock/StockHeader.jsx`
- Modify: `frontend/src/components/stock/StockHeader.test.jsx`
- Modify: `frontend/src/components/stock/StockDataTab.jsx`
- Modify: `frontend/src/components/stock/StockFilingsTab.jsx`
- Modify: `frontend/src/components/stock/StockFinancialsTab.jsx`
- Modify: `frontend/src/components/stock/StockOverviewTab.jsx`
- Modify: `frontend/src/components/stock/StockOverviewTab.test.jsx`
- Modify: `frontend/src/components/stock/StockOwnershipTab.jsx`
- Modify: `frontend/src/components/stock/StockValuationTab.jsx`
- Modify: `frontend/src/components/stock/StockTabQueries.test.jsx`
- Modify: `frontend/src/pages/Stock.jsx`
- Modify: `frontend/src/pages/Stock.tabs.test.jsx`
- Modify: `frontend/src/pages/Search.jsx`
- Modify: `frontend/src/pages/Screener.jsx`
- Modify: `frontend/src/pages/Screener.test.jsx`
- Modify: `frontend/src/pages/TaxReport.jsx`
- Modify: `frontend/src/pages/TaxReport.*.test.jsx`

- [ ] Add semantic-class assertions for StockHeader price/change, overview KPI values, financial-statement cells, valuation metrics, ownership percentages, Search result prices, Screener numeric columns, and Tax Report monetary columns.
- [ ] Run the stock, screener, and tax focused tests using Vitest globs and confirm at least one new assertion fails.
- [ ] Convert critical values to `financial-headline`/`financial-data`; convert timestamps, filing types, and source notes to `financial-meta`.
- [ ] Keep dense statement/report tables horizontally scrollable with a readable 14 px numeric minimum.
- [ ] Make tabs, pagination, and filter controls at least 12 px with visible focus outlines.
- [ ] Verify every stock gain/loss value contains a sign or explicit word independent of color.
- [ ] Run:

```powershell
cd frontend
npm test -- --run src/components/StockDetail.divgrowth.test.jsx src/components/StockDetail.financialGrowth.test.jsx src/components/StockDetail.insiderPagination.test.jsx src/components/StockDetail.ownership.test.jsx src/components/stock/StockHeader.test.jsx src/components/stock/StockOverviewTab.test.jsx src/components/stock/StockTabQueries.test.jsx src/pages/Stock.tabs.test.jsx src/pages/Screener.test.jsx src/pages/TaxReport.pagination.test.jsx src/pages/TaxReport.precision.test.jsx
```

  Expect pass.
- [ ] Commit:

```powershell
git add frontend/src/components/StockDetail.jsx frontend/src/components/StockDetail.*.test.* frontend/src/components/stock frontend/src/pages/Stock.jsx frontend/src/pages/Stock.tabs.test.jsx frontend/src/pages/Search.jsx frontend/src/pages/Screener.jsx frontend/src/pages/Screener.test.jsx frontend/src/pages/TaxReport.jsx frontend/src/pages/TaxReport.*.test.jsx
git commit -m "fix: improve stock and research readability"
```

## Task 7: Audit shell, account, setup, and public surfaces

**Files:**

- Modify: `frontend/src/components/layout/DesktopSidebar.jsx`
- Modify: `frontend/src/components/layout/DesktopSidebar.test.jsx`
- Modify: `frontend/src/components/layout/MobileNavDrawer.jsx`
- Modify: `frontend/src/components/layout/MobileNavDrawer.test.jsx`
- Modify: `frontend/src/components/layout/MobileTopBar.jsx`
- Modify: `frontend/src/components/AccountMenu.jsx`
- Modify: `frontend/src/pages/Login.jsx`
- Modify: `frontend/src/pages/Register.jsx`
- Modify: `frontend/src/pages/ForgotPassword.jsx`
- Modify: `frontend/src/pages/VerifyEmail.jsx`
- Modify: `frontend/src/pages/AuthPages.test.jsx`
- Modify: `frontend/src/pages/Onboarding.jsx`
- Modify: `frontend/src/pages/Onboarding.test.jsx`
- Modify: `frontend/src/pages/Import.jsx`
- Modify: `frontend/src/pages/Import.test.jsx`
- Modify: `frontend/src/pages/Settings.jsx`
- Modify: `frontend/src/pages/Settings.sections.test.jsx`
- Modify: `frontend/src/pages/Pricing.jsx`
- Modify: `frontend/src/pages/Pricing.test.jsx`
- Modify: `frontend/src/pages/Assistant.jsx`
- Modify: `frontend/src/pages/Assistant.privacy.test.jsx`
- Modify: `frontend/src/pages/Welcome.css`
- Modify: `frontend/src/pages/Welcome.test.jsx`

- [ ] Add source/DOM assertions that navigation labels, input text, form errors, plan prices, import preview numbers, settings values, assistant metadata, and landing screenshot labels obey the 12/14 px floors.
- [ ] Run the focused tests for all named surfaces and confirm new assertions fail.
- [ ] Replace 8–11 px landing preview text with 12 px metadata or 14 px financial values. If a preview no longer fits, enlarge its panel, shorten the label, or hide non-critical decoration at the smallest breakpoint.
- [ ] Replace sub-12 px shell badges/metadata with `financial-meta`/`data-label`; keep main navigation and form controls `text-sm` or larger.
- [ ] Remove opacity from important auth/import/settings messages and use semantic muted text instead.
- [ ] Preserve the existing localized copy and all auth/import/settings behavior.
- [ ] Run:

```powershell
cd frontend
npm test -- --run src/components/layout/DesktopSidebar.test.jsx src/components/layout/MobileNavDrawer.test.jsx src/pages/AuthPages.test.jsx src/pages/Onboarding.test.jsx src/pages/Import.test.jsx src/pages/Settings.sections.test.jsx src/pages/Pricing.test.jsx src/pages/Assistant.privacy.test.jsx src/pages/Welcome.test.jsx
```

  Expect pass.
- [ ] Commit:

```powershell
git add frontend/src/components/layout frontend/src/components/AccountMenu.jsx frontend/src/pages/Login.jsx frontend/src/pages/Register.jsx frontend/src/pages/ForgotPassword.jsx frontend/src/pages/VerifyEmail.jsx frontend/src/pages/AuthPages.test.jsx frontend/src/pages/Onboarding.jsx frontend/src/pages/Onboarding.test.jsx frontend/src/pages/Import.jsx frontend/src/pages/Import.test.jsx frontend/src/pages/Settings.jsx frontend/src/pages/Settings.sections.test.jsx frontend/src/pages/Pricing.jsx frontend/src/pages/Pricing.test.jsx frontend/src/pages/Assistant.jsx frontend/src/pages/Assistant.privacy.test.jsx frontend/src/pages/Welcome.css frontend/src/pages/Welcome.test.jsx
git commit -m "fix: improve shell and public surface readability"
```

## Task 8: Add a deterministic readability regression audit

**Files:**

- Create: `frontend/scripts/audit-readability.mjs`
- Create: `frontend/scripts/audit-readability.test.mjs`
- Modify: `frontend/package.json`
- Modify: `.github/workflows/ci.yml`
- Create: `docs/operations/readability-browser-check.md`

**Interfaces:**

- `npm run audit:readability` exits non-zero with `path:line` for forbidden critical-size patterns.
- The scanner checks `.jsx`, `.js`, and `.css` under `src` and ignores tests, `sr-only`, decorative sparkline SVG, and an explicit path/token allowlist stored in the script.

- [ ] Write Node tests using a temporary directory: one fixture containing `className="financial-data text-[10px]"` must fail; one containing `className="financial-meta"` must pass; a deliberately allowlisted decorative case must pass.
- [ ] Run `cd frontend; node --test scripts/audit-readability.test.mjs` and confirm failure because the script does not exist.
- [ ] Implement exported `auditReadability(root)` and a CLI entry point. Flag `text-[8px]` through `text-[11px]` and CSS `font-size` below `12px`; print every violation before setting `process.exitCode = 1`.
- [ ] Keep the allowlist exact and documented as `{ path, token, reason }` objects; do not allowlist whole directories.
- [ ] Add `"audit:readability": "node scripts/audit-readability.mjs src"` to `package.json`.
- [ ] Run `npm run audit:readability`; fix every unapproved result in production source. Do not add an allowlist entry for a financial value, input, action, axis, or legend.
- [ ] Add the audit command to the frontend CI job after tests and before the build.
- [ ] Write the browser checklist with the four viewports (390×844, 768×1024, 1024×768, 1440×900), three appearances, representative page list, computed font/contrast checks, keyboard focus, chart summaries, and no page-level horizontal scrolling.
- [ ] Run:

```powershell
cd frontend
node --test scripts/audit-readability.test.mjs
npm run audit:readability
npm test
npm run test:cloud
npm run build
npm run build:cloud
```

  Expect all commands to pass. Record test counts and build output in the implementation handoff.
- [ ] Commit:

```powershell
git add frontend/scripts/audit-readability.mjs frontend/scripts/audit-readability.test.mjs frontend/package.json frontend/package-lock.json .github/workflows/ci.yml docs/operations/readability-browser-check.md
git commit -m "test: enforce readability regression gates"
```

## Plan completion gate

- [ ] Run `git status --short` and confirm only intended plan changes are present.
- [ ] Run `git diff --check HEAD~8..HEAD` and expect no whitespace errors.
- [ ] Confirm every item in `docs/operations/readability-browser-check.md` manually before release; automated source scanning does not replace computed browser contrast verification.
- [ ] Continue with `docs/superpowers/plans/2026-09-19-portfyl-public-demo.md` only after this plan is green.
