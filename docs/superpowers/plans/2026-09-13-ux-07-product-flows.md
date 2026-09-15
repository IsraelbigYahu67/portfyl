# UX Plan 7: Product Flows — Implementation Plan

> **For agentic workers:** Execute this plan task by task. Use a failing focused test before each behavioral change, keep commits at the boundaries shown below, and record the final browser evidence. Do not combine this phase with Plan 8.

**Goal:** Turn Stock Detail, Watchlists, Import/Onboarding, and Settings into coherent, URL-stable workflows whose data loading, mutations, destructive actions, and narrow-screen behavior are explicit.

**Architecture:** Add one shared accessible URL-tab primitive. Split the stock report into five route-local tab components and split its expensive market-data request by view while keeping the legacy full fundamentals response compatible. Keep watchlist operations on the existing APIs but add deterministic client sorting, confirmations, toasts, and optimistic rollback. Make Settings a four-section route and move the existing appearance/currency and destructive portfolio controls into their intended sections. Represent an onboarding CSV portfolio as a workspace-scoped pending activation marker in the existing `workspace_settings` table; successful import activates it in the same transaction, so cancellation cannot expose a blank portfolio.

**Tech stack:** FastAPI, SQLAlchemy 2.0, React 18, TanStack Query, React Router 7, Vitest/Testing Library, pytest, Playwright browser QA.

**Spec:** `docs/superpowers/specs/2026-09-13-portfyl-ux-product-coherence-design.md` (§6, §10.4–§10.7, §13)

**Branch:** `codex/ux-07-product-flows`

**Base and target:** Start only after Plan 6 is merged into `codex/portfyl-ux-overhaul`; the PR targets `codex/portfyl-ux-overhaul`, never `main`.

## Dependencies and scope boundary

- Consume Plan 2's `AsyncSection` and error-message contract, Plan 3's responsive `AppShell`, navigation groups, focus trap and `ConfirmDialog`, Plan 4's `Pagination`, and Plan 6's shared formatting/chart-summary work. Extend those APIs instead of copying them.
- Preserve the approved preview → commit → 24-hour undo protocol from `docs/superpowers/specs/2026-09-07-portfyl-onboarding-import-safety-design.md`. The frontend continues to render backend duplicate/reconciliation decisions; it does not recompute them.
- Preserve `sb_theme_style`, `sb_theme`, `sb_palette`, `sb_currency`, `sb_stock_report_sections`, and all other established storage keys. Moving a control must not reset its value.
- Preserve the static local/cloud boundary. Tax Report and Screener stay absent from cloud. This phase introduces no runtime dependency and no new table or Alembic revision.
- The Settings Data section created here is the stable insertion point for Plan 8's assistant context preference. Plan 7 does not add Assistant consent, prompt disclosure, or context-mode behavior.
- Keep the legacy no-`view` `GET /api/market/fundamentals/{ticker}` response for compatibility. The new SPA stops using the full response, but removing it is outside this phase.
- Do not redesign price-alert persistence, import reconciliation, account deletion, broker entitlements, or Stock valuation methodology.

## Worktree and branch guard

Create the phase worktree from the fetched integration head. Replace the sample path with an unused sibling directory:

```powershell
git fetch origin codex/portfyl-ux-overhaul
git worktree add ..\portfyl-ux-07 -b codex/ux-07-product-flows origin/codex/portfyl-ux-overhaul
cd ..\portfyl-ux-07

$branch = (git branch --show-current).Trim()
if ($branch -ne 'codex/ux-07-product-flows') {
  throw "Expected codex/ux-07-product-flows, found $branch"
}
if ($branch -eq 'main') { throw 'Refusing to work on main' }

$expectedBase = (git rev-parse origin/codex/portfyl-ux-overhaul).Trim()
$actualBase = (git merge-base HEAD origin/codex/portfyl-ux-overhaul).Trim()
if ($actualBase -ne $expectedBase) {
  throw 'Plan 7 must start from the current integration HEAD after Plan 6 is merged'
}

$dirty = git status --porcelain
if ($dirty) {
  $dirty
  throw 'Refusing to start with unexplained worktree changes'
}
git status --short --branch
```

Before every commit, inspect `git status --short` and `git diff --check`. Never use `git add -A`, reset somebody else's changes, or stage the verification file before its task.

## Planned file map

**Shared URL state**

- Create `frontend/src/components/ui/UrlTabs.jsx` and `UrlTabs.test.jsx`.
- Modify `frontend/src/components/ui/index.js`.

**Stock Detail**

- Modify `backend/routers/market.py`, `backend/routers/portfolio.py`, `backend/tests/test_market.py`, and Plan 4's existing `backend/tests/test_transactions_page.py`.
- Modify `frontend/src/api.js` and `frontend/src/pages/Stock.jsx`.
- Create `frontend/src/pages/Stock.tabs.test.jsx`.
- Create `frontend/src/components/stock/StockHeader.jsx`, `StockOverviewTab.jsx`, `StockFinancialsTab.jsx`, `StockValuationTab.jsx`, `StockOwnershipTab.jsx`, and `StockFilingsTab.jsx`.
- Create `frontend/src/components/stock/StockOverviewTab.test.jsx` and `StockTabQueries.test.jsx`.
- Modify `frontend/src/components/StockDetail.jsx` and the existing `StockDetail.*.test.{js,jsx}` files only as imports move; retain its public named exports as compatibility re-exports.
- Modify `frontend/src/hooks/useStockReportConfig.js` and create `useStockReportConfig.test.js` for the one-time tab migration.

**Watchlists**

- Modify `frontend/src/pages/Watchlists.jsx` and `frontend/src/api.js` only if a typed helper signature needs adjustment.
- Create `frontend/src/pages/Watchlists.flows.test.jsx`.
- Create `frontend/src/components/watchlists/WatchlistEmptyState.jsx`, `WatchlistEmptyState.test.jsx`, `WatchlistCard.jsx`, and `WatchlistCard.test.jsx`.

**Settings and destructive management**

- Modify `frontend/src/pages/Settings.jsx` and create `frontend/src/pages/Settings.sections.test.jsx`.
- Create `frontend/src/components/settings/SettingsSectionNav.jsx`, `SettingsSectionNav.test.jsx`, `PreferencesSettings.jsx`, `PreferencesSettings.test.jsx`, `PortfolioDataManagement.jsx`, and `PortfolioDataManagement.test.jsx`.
- Modify `frontend/src/components/DataPrivacySettings.jsx`, `DataPrivacySettings.test.jsx`, `frontend/src/components/layout/DesktopSidebar.jsx`, and `DesktopSidebar.test.jsx`.
- Modify `frontend/src/pages/Onboarding.jsx` for the direct Connections URL.

**Import and pending activation**

- Create `backend/portfolio_activation.py` and `backend/tests/test_portfolio_activation.py`.
- Modify `backend/routers/portfolios.py`, `backend/routers/portfolio.py`, `backend/account_export.py`, `backend/tests/test_onboarding.py`, `backend/tests/test_import_workflow.py`, `backend/tests/test_account_export.py`, and `backend/tests/postgres/matrix_cases.py`.
- Modify `frontend/src/App.jsx`, `frontend/src/App.routing.test.jsx`, `frontend/src/api.js`, `frontend/src/pages/Onboarding.jsx`, `Onboarding.test.jsx`, `frontend/src/pages/Import.jsx`, and `Import.test.jsx`.

**Evidence**

- Create `docs/superpowers/plans/ux-07-product-flows-verification.md` only in the final task.

If a named test file has been consolidated on the integration branch, put the assertions in the closest current test file and record that substitution in the verification note. Do not invent a second implementation of an existing helper.

---

## Task 1: Shared accessible URL tabs

**Files:**

- Create: `frontend/src/components/ui/UrlTabs.jsx`
- Create: `frontend/src/components/ui/UrlTabs.test.jsx`
- Modify: `frontend/src/components/ui/index.js`

**Interface:**

```jsx
<UrlTabs
  ariaLabel="Stock sections"
  items={[{ value: "overview", label: "Overview", panelId: "stock-overview-panel" }]}
  value={activeTab}
  onChange={setActiveTab}
/>
```

The primitive owns tab roles and roving focus, not URL parsing. Its caller owns `URLSearchParams` and panel rendering. Every changed page renders one `tabpanel` with `aria-labelledby` pointing to the selected tab.

- [ ] Write failing tests for `tablist`, named `tab`s, `aria-selected`, one `tabIndex=0`, ArrowLeft/ArrowRight wrap, Home/End, click selection, focus movement, and no selection callback for disabled tabs.
- [ ] Run `cd frontend && npm test -- UrlTabs.test.jsx` and capture the expected failure.
- [ ] Implement with real `<button type="button" role="tab">` controls and stable IDs derived from `idPrefix`; do not synthesize keyboard clicks or add a dependency.
- [ ] Export `UrlTabs` from `components/ui/index.js`.
- [ ] Run `npm test -- UrlTabs.test.jsx`.

```powershell
git add frontend/src/components/ui/UrlTabs.jsx frontend/src/components/ui/UrlTabs.test.jsx frontend/src/components/ui/index.js
git commit -m "feat(ui): add accessible URL tab controls"
```

## Task 2: Stock data contracts that load by active tab

**Files:**

- Modify: `backend/routers/market.py`
- Modify: `backend/routers/portfolio.py`
- Modify: `backend/tests/test_market.py`
- Modify: `backend/tests/test_transactions_page.py`
- Modify: `frontend/src/api.js`

**Market contract:** extend the existing endpoint additively:

```text
GET /api/market/fundamentals/{ticker}?view=overview
GET /api/market/fundamentals/{ticker}?view=financials
GET /api/market/fundamentals/{ticker}?view=valuation
GET /api/market/fundamentals/{ticker}?view=ownership
```

Omitting `view` retains the complete legacy payload. Reject an unknown view with 422. Each view returns `ticker`, `name`, `currency`, source/freshness metadata, plus only its view fields:

- `overview`: quote/change, company identity, description, 52-week/50-day/200-day values, market cap, beta, and the small KPI subset;
- `financials`: annual/quarterly statements, TTM, analyst estimates needed by the growth charts, and dividend-history inputs;
- `valuation`: ratios, sector medians, analyst rating/targets, valuation model and valuation-history inputs;
- `ownership`: base ownership and yfinance insider transactions.

Refactor the current builder into internal per-view helpers so an overview request does not fetch statements, ownership, analyst estimates, or valuation data. Cache by `(ticker, view)`; never slice the old full payload after paying for all upstream calls. Keep best-effort null behavior and the five-year average P/E methodology.

**Portfolio context contract:** extend Plan 4's paged transactions endpoint with optional exact `ticker` filtering:

```text
GET /api/portfolio/transactions/page?ticker=AAPL&sort=-date&offset=0&limit=1
```

Normalize the filter with `strip().upper()`, apply it as `Transaction.ticker == ticker`, and combine it with existing `q`, type, sort, workspace, and portfolio predicates. This is additive; existing calls are unchanged.

**Frontend helpers:**

```js
fetchStockView(ticker, view, requestConfig = {})
fetchTransactionsPage({ offset, limit, q, type, ticker, sort })
```

- [ ] Add failing backend tests proving each view contains its allowed keys, excludes an unrelated heavy key, and invokes only the relevant mocked upstream builders. Assert no-`view` compatibility and 422 for an unknown value.
- [ ] Add failing transaction-page tests for exact ticker matching, case normalization, combined filters, newest-first `limit=1`, portfolio isolation, and a ticker owned by another workspace returning zero rows.
- [ ] Implement the minimum refactor and API helpers.
- [ ] Run:

```powershell
cd backend
python -m pytest tests/test_market.py tests/test_transactions_page.py -v
cd ..\frontend
npm test -- api.auth.test.js
```

```powershell
git add backend/routers/market.py backend/routers/portfolio.py backend/tests/test_market.py backend/tests/test_transactions_page.py frontend/src/api.js
git commit -m "feat(stock): load market data by research view"
```

## Task 3: Five URL-backed Stock Detail tabs

**Files:**

- Modify: `frontend/src/pages/Stock.jsx`
- Create: `frontend/src/pages/Stock.tabs.test.jsx`
- Create: `frontend/src/components/stock/StockHeader.jsx`
- Create: `frontend/src/components/stock/StockOverviewTab.jsx`
- Create: `frontend/src/components/stock/StockFinancialsTab.jsx`
- Create: `frontend/src/components/stock/StockValuationTab.jsx`
- Create: `frontend/src/components/stock/StockOwnershipTab.jsx`
- Create: `frontend/src/components/stock/StockFilingsTab.jsx`
- Create: `frontend/src/components/stock/StockOverviewTab.test.jsx`
- Create: `frontend/src/components/stock/StockTabQueries.test.jsx`
- Modify: `frontend/src/components/StockDetail.jsx`
- Modify: `frontend/src/hooks/useStockReportConfig.js`
- Create: `frontend/src/hooks/useStockReportConfig.test.js`
- Modify as needed: existing `frontend/src/components/StockDetail.*.test.{js,jsx}` imports

**URL contract:** `/stock/:ticker` and missing/invalid `?tab=` resolve to `overview`. Valid values are exactly `overview`, `financials`, `valuation`, `ownership`, and `filings`. Selecting a tab pushes `?tab=value`; browser back/forward and reload restore it without losing unrelated search parameters. Canonicalize an invalid value with `replace` so history is not polluted.

**Query contract:**

- always load `fetchStockView(ticker, "overview")` for the header and lightweight overview identity;
- mount/load `financials`, `valuation`, and `ownership` view queries only when that tab is active (`enabled: activeTab === value`);
- mount existing Shibui filing queries only in `StockFilingsTab` and ownership/insider/political queries only in their owning active tab;
- load one-year history, holdings, and exact latest transaction only for Overview;
- use distinct keys `['stock-view', ticker, view]`, `['history', ticker, '1y']`, `['holdings', currency]`, and `['transactions-page', { ticker, sort: '-date', limit: 1 }]` so portfolio/currency switching follows the existing cache isolation rules.

**Tab ownership:**

- Overview: shared header, quote and chart, `Your position`, key KPIs, company description, notes from the most recent transaction/trade-note payload, and the most recent transaction.
- Financials: annual/quarterly statements, growth, margins, earnings recap, and dividend history.
- Valuation: ratios, analyst estimates/targets, valuation models, and valuation history.
- Ownership: ownership breakdown, institutional/beneficial ownership, insider activity, insider transaction pagination, and political trades.
- Filings: SEC/Shibui filings and any capability-backed filing content, with its own unavailable/error state.

`Your position` derives from the exact ticker row in existing holdings plus the latest exact-ticker transaction. It displays shares, average cost (`avg_price`), market value, signed unrealized P&L and percentage, portfolio weight, and latest transaction date/type/shares/price. For an unowned researched symbol it says `You do not currently own {ticker}` and still shows research content. Do not fabricate zero values. Use shared money/date formatters and words/icons in addition to gain/loss color.

Move the large JSX sections into the named tab files. `Stock.jsx` owns URL state and query composition only. Leave `frontend/src/components/StockDetail.jsx` as a compatibility barrel for `useStockDetail`, `TickerLink`, and the named exports consumed by current tests/pages; remove the old `StockOverview` monolith after all call sites are migrated.

`useStockReportConfig` performs one non-destructive migration: map each previously hidden section to its owning tab and store hidden tab preferences only if every meaningful section in that tab was hidden. Preserve the old key for rollback compatibility and do not let legacy section order override the fixed five-tab order.

- [ ] Write failing page tests for default/explicit/invalid tab URLs, click navigation, popstate/back behavior, one panel, keyboard arrows, and header persistence.
- [ ] Write query tests proving inactive view functions are never called, changing tabs triggers only the selected request, returning to a fresh cached tab does not refetch, ticker changes create new keys, and every query has an independent `AsyncSection` retry.
- [ ] Write Overview tests for owned/unowned states and all seven position/latest-transaction values.
- [ ] Move sections without changing their calculations, labels, provenance, pagination, or existing component assertions.
- [ ] Run:

```powershell
cd frontend
npm test -- Stock.tabs.test.jsx StockOverviewTab.test.jsx StockTabQueries.test.jsx useStockReportConfig.test.js
npm test -- StockDetail.financialGrowth.test.jsx StockDetail.divgrowth.test.jsx StockDetail.ownership.test.jsx StockDetail.insiderPagination.test.jsx StockDetail.insiderFilter.test.js
```

```powershell
git add frontend/src/pages/Stock.jsx frontend/src/pages/Stock.tabs.test.jsx frontend/src/components/stock frontend/src/components/StockDetail.jsx frontend/src/components/StockDetail.*.test.js frontend/src/components/StockDetail.*.test.jsx frontend/src/hooks/useStockReportConfig.js frontend/src/hooks/useStockReportConfig.test.js
git commit -m "feat(stock): split research into URL-backed tabs"
```

## Task 4: Watchlist quick start, controls, and mutation feedback

**Files:**

- Modify: `frontend/src/pages/Watchlists.jsx`
- Create: `frontend/src/pages/Watchlists.flows.test.jsx`
- Create: `frontend/src/components/watchlists/WatchlistEmptyState.jsx`
- Create: `frontend/src/components/watchlists/WatchlistEmptyState.test.jsx`
- Create: `frontend/src/components/watchlists/WatchlistCard.jsx`
- Create: `frontend/src/components/watchlists/WatchlistCard.test.jsx`

**Behavior:**

- With zero lists, explain that a watchlist tracks researched symbols without adding them to a portfolio. Autofocus a labelled ticker autocomplete. Selecting a valid result creates `My watchlist` and adds the symbol using the existing mutations; if list creation succeeds but item addition fails, keep the created list visible and show an actionable retry error.
- Each non-empty list has a labelled local search input and sort select with deterministic values `ticker`, `change_desc`, `change_asc`, and `market_cap_desc`. Search matches ticker and quote name case-insensitively. Stable sort null quote values last, with ticker as tie-breaker.
- Every row remains a real stock link and exposes signed daily change. Remove is inline but opens the shared accessible `ConfirmDialog` naming both ticker and list.
- Item removal is optimistic: `onMutate` cancels `['watchlists']`, snapshots cache, removes the item and decrements count; `onError` restores the snapshot and announces failure; `onSettled` invalidates. Tests must cover rollback and a second list remaining unchanged.
- Create, quick-start add, ordinary add, remove, list delete, and alert mutations announce success through the existing Toast and failure through an alert/live region. Replace every `window.confirm` call.
- Match price-alert status to ticker and display Active/Triggered text when present. Fetch `['discord-webhook']` and cached capabilities. Disable alert creation when Discord is disconnected or `notification_integrations` is unavailable, show the reason next to the control, and provide a real link to `/settings?section=notifications`.
- Loading/error/empty states remain independent: a webhook-status failure disables alert creation but does not hide watchlists; watchlist failure uses `AsyncSection` retry; alert failure is not rendered as `No alerts yet`.

- [ ] Write failing helper/component/page tests for empty autofocus, autocomplete quick start, search, all sorts, null-last behavior, named confirmation, optimistic disappearance, rollback, success/failure announcements, alert status, and the Notifications link.
- [ ] Prove failure with `cd frontend && npm test -- WatchlistEmptyState.test.jsx WatchlistCard.test.jsx Watchlists.flows.test.jsx`.
- [ ] Extract the components, retaining one query/cache owner in the page. Do not add a global state store.
- [ ] Run the focused tests plus `npm test -- ResearchPages.async.test.jsx`.

```powershell
git add frontend/src/pages/Watchlists.jsx frontend/src/pages/Watchlists.flows.test.jsx frontend/src/components/watchlists
git commit -m "feat(watchlists): make tracking and alerts actionable"
```

## Task 5: Four URL-addressable Settings sections and preference relocation

**Files:**

- Modify: `frontend/src/pages/Settings.jsx`
- Create: `frontend/src/pages/Settings.sections.test.jsx`
- Create: `frontend/src/components/settings/SettingsSectionNav.jsx`
- Create: `frontend/src/components/settings/SettingsSectionNav.test.jsx`
- Create: `frontend/src/components/settings/PreferencesSettings.jsx`
- Create: `frontend/src/components/settings/PreferencesSettings.test.jsx`
- Modify: `frontend/src/components/layout/DesktopSidebar.jsx`
- Modify: `frontend/src/components/layout/DesktopSidebar.test.jsx`
- Modify: `frontend/src/pages/Onboarding.jsx`

**URL contract:** `?section=connections` is the default; valid sections are `connections`, `preferences`, `notifications`, and `data`. Unknown values replace to Connections. Preserve unrelated search parameters. Desktop renders a narrow `<nav aria-label="Settings sections">` with real links; below `lg`, render a labelled native select or horizontally scrollable `UrlTabs`. Back/forward/reload restore the section and focus its `<h2 tabIndex={-1}>` after in-app selection.

**Section ownership:**

- Connections: current Trading 212 status/connect/sync/disconnect UI and `SyncScheduleSettings`.
- Preferences: Theme style (Classic/Premium), Light/Dark/System appearance, accent palette, and USD/CZK display currency, using the existing `usePalette`/`useCurrency` context setters and storage keys.
- Notifications: `DiscordSettings` and explanatory notification-destination copy.
- Data & Privacy: `PortfolioDataManagement` from Task 6 plus existing `DataPrivacySettings`. Its composition must accept additional children or a named slot so Plan 8 can add Assistant context preferences without changing section routing.

Mount only the selected section, so opening Connections does not fire Discord/deletion queries and opening Preferences fires no network query. `status.connected` from `/broker/trading212/status` is the sole source of connection truth; imported transactions never produce a connected badge.

Remove palette/theme/currency controls and their imports from `DesktopSidebar`. It retains navigation, portfolio switching, account menu, and provider/freshness attribution. Preserve the visible currency rate/unavailable explanation inside Preferences.

Update onboarding's broker destination to `/settings?section=connections`.

- [ ] Write failing settings tests for all direct URLs, invalid fallback, desktop/narrow chooser, keyboard operation, history/reload, section-only query mounting, and imported portfolio + `connected:false` rendering `Not connected`.
- [ ] Write preference tests that seed every existing storage key/context value, change each control, and assert the same setter/key semantics and accessible names.
- [ ] Update sidebar tests to assert preference controls are absent while navigation, portfolio, and account controls remain.
- [ ] Run:

```powershell
cd frontend
npm test -- SettingsSectionNav.test.jsx PreferencesSettings.test.jsx Settings.sections.test.jsx DesktopSidebar.test.jsx Onboarding.test.jsx
```

```powershell
git add frontend/src/pages/Settings.jsx frontend/src/pages/Settings.sections.test.jsx frontend/src/components/settings/SettingsSectionNav.jsx frontend/src/components/settings/SettingsSectionNav.test.jsx frontend/src/components/settings/PreferencesSettings.jsx frontend/src/components/settings/PreferencesSettings.test.jsx frontend/src/components/layout/DesktopSidebar.jsx frontend/src/components/layout/DesktopSidebar.test.jsx frontend/src/pages/Onboarding.jsx
git commit -m "feat(settings): add URL sections and move preferences"
```

## Task 6: Move destructive portfolio management into Data & Privacy

**Files:**

- Create: `frontend/src/components/settings/PortfolioDataManagement.jsx`
- Create: `frontend/src/components/settings/PortfolioDataManagement.test.jsx`
- Modify: `frontend/src/components/DataPrivacySettings.jsx`
- Modify: `frontend/src/components/DataPrivacySettings.test.jsx`
- Modify: `frontend/src/pages/Settings.jsx`
- Modify: `frontend/src/pages/Import.jsx`
- Modify: `frontend/src/pages/Import.test.jsx`

`PortfolioDataManagement` owns `clearAllTransactions` for the current portfolio. It states the portfolio name and consequences, uses `useConfirm({ danger: true, confirmLabel: 'Clear portfolio' })`, invalidates all portfolio-derived and import-undo keys after success, and announces success/failure. It never deletes the portfolio record, broker credentials, workspace, or another portfolio's cache/data.

Remove the Clear portfolio button, mutation, icon, and confirmation copy from Import. Import contains a neutral link to `/settings?section=data` after a completed import only when management is relevant; destructive management must not compete with source selection.

Because `DataPrivacySettings` is touched, bring its custom typed-confirmation dialog up to the phase accessibility floor: use the existing `useFocusTrap`, Escape close, initial focus, and focus restoration; associate both title and description; keep exact workspace-name/password requirements and the 30-day deletion contract unchanged.

- [ ] Write failing tests that Import has no Clear action; Settings Data has it; cancel leaves data untouched; confirm calls the existing scoped API once; failure remains visible; success invalidates `transactions-page`, holdings, summary, performance, dividends, tax/analytics, portfolios, and import-undo caches.
- [ ] Extend deletion-dialog tests for initial focus, Tab containment, Escape, and restoration to the opener.
- [ ] Run `cd frontend && npm test -- PortfolioDataManagement.test.jsx DataPrivacySettings.test.jsx Import.test.jsx Settings.sections.test.jsx`.

```powershell
git add frontend/src/components/settings/PortfolioDataManagement.jsx frontend/src/components/settings/PortfolioDataManagement.test.jsx frontend/src/components/DataPrivacySettings.jsx frontend/src/components/DataPrivacySettings.test.jsx frontend/src/pages/Settings.jsx frontend/src/pages/Import.jsx frontend/src/pages/Import.test.jsx
git commit -m "feat(settings): move destructive data controls to privacy"
```

## Task 7: Pending onboarding activation and explicit import stages

**Files:**

- Create: `backend/portfolio_activation.py`
- Create: `backend/tests/test_portfolio_activation.py`
- Modify: `backend/routers/portfolios.py`
- Modify: `backend/routers/portfolio.py`
- Modify: `backend/account_export.py`
- Modify: `backend/tests/test_onboarding.py`
- Modify: `backend/tests/test_import_workflow.py`
- Modify: `backend/tests/test_account_export.py`
- Modify: `backend/tests/postgres/matrix_cases.py`
- Modify: `frontend/src/api.js`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/App.routing.test.jsx`
- Modify: `frontend/src/pages/Onboarding.jsx`
- Modify: `frontend/src/pages/Onboarding.test.jsx`
- Modify: `frontend/src/pages/Import.jsx`
- Modify: `frontend/src/pages/Import.test.jsx`

### Backend pending-activation contract

Use the existing `WorkspaceSetting` table with one internal key, `onboarding_pending_portfolio`. Store a versioned JSON value containing the workspace-scoped portfolio public UUID and `kind: "csv_import"`. Centralize read/write/clear logic in `backend/portfolio_activation.py`; every lookup includes workspace and portfolio predicates and callers own the transaction.

Add:

```text
POST /api/portfolios/pending-import
POST /api/portfolios/{portfolio_id}/activate
```

- `pending-import` is CSRF- and portfolio-capacity-protected. If the marker identifies an existing empty pending portfolio in the same workspace, return it idempotently. Otherwise create `My portfolio` (using the normal unique-name suffix rule), set the marker, and return `{..., activation_state: "pending_import"}` in one transaction.
- `list_portfolios` serializes `activation_state` as `active` or `pending_import`. A malformed/stale marker fails closed as no pending state and is cleaned only within an owned transaction.
- `activate` requires the marked portfolio, verifies it is empty, clears the marker, records `onboarding.portfolio.activated` with kind `blank`, and returns the active serialization. It is the explicit `Start with a blank portfolio` action, not an automatic result of cancelling an import.
- A successful non-no-op CSV commit clears the matching marker and records activation in the same database transaction as inserted rows and the undo snapshot. A failed preview/commit or cancelled frontend flow leaves the marker intact. An unrelated portfolio import cannot clear it.
- Pending records count toward entitlement capacity, cannot appear in the normal portfolio switcher, and remain available to the onboarding Import route after reload. The broker and demo paths keep their current atomic behavior.
- Exclude `onboarding_pending_portfolio` from customer export exactly as `import_undo:` internal recovery settings are excluded. Workspace deletion removes it through the existing cascade.
- Add both endpoints to the PostgreSQL tenant/CSRF matrix. Alice cannot read, activate, import into, or replace Bob's pending portfolio.

No model or migration change is allowed. If the integration branch no longer has `WorkspaceSetting`, stop and redesign in a separate reviewed spec instead of adding a column ad hoc.

### Frontend route and flow contract

`PortfolioProvider` exposes `activePortfolios`, `pendingImportPortfolio`, and the full server list. `AppLayout` behaves as follows:

- no active portfolio + no matching pending route: render Onboarding;
- no active portfolio + pending portfolio + `/import`: render the focused Import workflow without normal portfolio navigation;
- one or more active portfolios: render the normal shell and exclude pending records from `PortfolioSwitcher`.

Onboarding's Import choice calls `createPendingImportPortfolio`, selects its UUID, refetches the portfolio list, and navigates to `/import`. Re-entering the flow reuses the same pending record. Add a separate, secondary `Start with a blank portfolio` action that calls activate and then enters Dashboard.

Import uses an explicit state machine with these visible stages and a labelled ordered stepper:

1. `Select source` — file/dropzone, format guidance, append/replace choice;
2. `Preview changes` — backend counts, warnings, bounded row sample;
3. `Confirm import` — effective mode, removals/duplicates/projected total, explicit commit button;
4. `Result / Undo` — imported/skipped/removed counts, undo expiry/status, View portfolio action.

Changing the file or replace mode invalidates the preview and returns to Select. `Cancel preview` returns to Select without a mutation. `Leave import` returns an onboarding user to Onboarding while preserving the hidden pending record; it never activates it. Successful commit renders Result before refetching the portfolio list; `View portfolio` then refetches, selects the activated portfolio, and navigates to Dashboard. On reload after success, the persisted undo status still appears on the normal Import page.

Each stage has independent pending/error text. Commit drift 409 returns to Preview with `The portfolio changed. Preview the file again.` Undo conflict/expiry remains distinct. Preserve Trading 212 mandatory replacement and all duplicate/notes warnings.

- [ ] Write failing backend tests for idempotent pending creation, capacity, marker serialization, explicit blank activation, import activation atomicity, failed commit persistence, unrelated-portfolio protection, internal export exclusion, and audit metadata.
- [ ] Write failing routing tests for pending reload, hidden switcher record, focused Import availability, Leave import returning to onboarding, explicit blank activation, and successful commit transition.
- [ ] Extend Import tests to assert step names/order, no commit before preview, mode/file invalidation, confirmation summary, result, persisted undo, cancellation without activation, and 409 recovery.
- [ ] Implement the helper/endpoints first, then frontend state/routing, then the stage presentation.
- [ ] Run focused gates:

```powershell
cd backend
python -m pytest tests/test_portfolio_activation.py tests/test_onboarding.py tests/test_import_workflow.py tests/test_account_export.py -v
cd ..\frontend
npm test -- App.routing.test.jsx Onboarding.test.jsx Import.test.jsx Settings.sections.test.jsx
```

```powershell
git add backend/portfolio_activation.py backend/routers/portfolios.py backend/routers/portfolio.py backend/account_export.py backend/tests/test_portfolio_activation.py backend/tests/test_onboarding.py backend/tests/test_import_workflow.py backend/tests/test_account_export.py backend/tests/postgres/matrix_cases.py frontend/src/api.js frontend/src/App.jsx frontend/src/App.routing.test.jsx frontend/src/pages/Onboarding.jsx frontend/src/pages/Onboarding.test.jsx frontend/src/pages/Import.jsx frontend/src/pages/Import.test.jsx
git commit -m "feat(onboarding): activate portfolios only after a chosen outcome"
```

## Task 8: Full phase gates and browser matrix

**File:**

- Create: `docs/superpowers/plans/ux-07-product-flows-verification.md`

### Automated local and cloud gates

Run from the phase worktree and record command, exit code, test count, and warnings:

```powershell
cd backend
python -m pytest tests/ -v --ignore=tests/postgres

cd ..\frontend
npm test
npm run test:cloud
npm run build
npm run build:cloud
```

Because Task 7 changes workspace-scoped persistence behavior and CSRF/tenant routes, PostgreSQL is a local go/no-go gate when Docker is available and remains mandatory in CI:

```powershell
docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait
cd backend
python -m pytest tests/postgres/ -v
```

Do not mark the phase verified when local/cloud tests or either production build fails. If Docker is unavailable, record that fact and the required CI PostgreSQL job URL; do not describe the database gate as waived.

### Worktree browser servers

Use the phase worktree, not an already-open `:5173` server from another checkout:

```powershell
# terminal 1, from <phase-worktree>\backend
python -m uvicorn main:app --reload --port 8001

# terminal 2, from <phase-worktree>\frontend
$env:VITE_API_PROXY_TARGET='http://localhost:8001'
npm run dev -- --port 5174
```

Exercise 390×844, 768×1024, 1024×768, and 1440×900. At every viewport assert no page-level horizontal overflow, no clipped primary action, no unexpected console error, and no failed request except the deliberately forced error.

**Stock Detail matrix:**

- direct-load, reload, tab click, keyboard arrows/Home/End, browser back/forward, and invalid-tab canonicalization;
- Overview owned and unowned symbols; all position values and latest transaction; chart/text equivalent;
- all five tabs with happy, loading, empty/unavailable, and forced-error/retry states;
- Network panel proves no inactive financials/valuation/ownership/filings request; switching tabs starts only its request;
- ownership pagination/filter survives within the tab and resets correctly on ticker change.

**Watchlists matrix:**

- zero-list autocomplete is initially focused and can quick-start a list;
- populated list search and every sort at mobile and desktop widths;
- remove confirmation keyboard flow, optimistic success, and forced rollback failure;
- disconnected Discord and missing capability each show a reason and `/settings?section=notifications`; connected state allows alert creation;
- mutation successes/failures are announced and back navigation from a stock returns to the prior filtered list.

**Import/Onboarding matrix:**

- new workspace starts Import, cancels preview, leaves, reloads, and resumes without exposing a blank portfolio in the switcher;
- explicit blank setup activates; demo and broker paths still route correctly;
- native append, duplicate-only, Trading 212 mandatory replace, validation error, commit drift, success/result, undo success, expired/conflicted undo;
- stepper/current-step announcement and keyboard-only file/control flow.

**Settings matrix:**

- direct/reload/back/forward for all four section URLs and invalid-section fallback;
- desktop side navigation and narrow chooser; one selected section and correct focus;
- preference changes persist after reload and the desktop sidebar no longer duplicates them;
- CSV data with no broker connection remains `Not connected`;
- Discord state and deep link from Watchlists;
- clear-portfolio and workspace-deletion dialogs: cancel, Escape, trapped/restored focus, forced API error, successful invalidation.

Run one cloud-edition browser pass for Stock, Watchlists, Import, and all Settings sections. Confirm capability-denied controls explain their state and local-only navigation/code remains absent. Run one local-edition pass to confirm the same shared flows and no regression to local capability entries.

### Record and commit evidence

The verification file must contain commit SHA, worktree ports, edition, account/workspace used, viewport-by-viewport results, screenshots/paths, console/network observations, automated command results, PostgreSQL/CI link, and any unresolved warning or intentional Plan 8 deferral.

```powershell
git add docs/superpowers/plans/ux-07-product-flows-verification.md
git commit -m "docs(ux): record product-flows phase verification"
```

## Acceptance criteria

- [ ] `/stock/:ticker?tab=` supports exactly five accessible, URL-backed tabs; reload and history restore selection.
- [ ] Stock loads only lightweight Overview plus the active tab's data, and the legacy full endpoint remains compatible.
- [ ] `Your position` is complete for owned symbols, truthful for unowned symbols, and uses an exact latest-ticker transaction.
- [ ] `Stock.jsx` is a coordinator; large research sections live in named tab components without breaking existing calculations/tests.
- [ ] Watchlists have an add-ticker-first empty state, search, deterministic sort, confirmed inline removal, optimistic rollback, and explicit mutation feedback.
- [ ] Price alerts expose status and a reasoned Notifications deep link when Discord/capability is unavailable.
- [ ] Import presents Select → Preview → Confirm → Result/Undo and retains every approved duplicate/replacement/undo safeguard.
- [ ] Cancelling/leaving onboarding import never activates or exposes a blank portfolio; successful import and explicit blank setup are the only activation outcomes covered here.
- [ ] Settings exposes Connections, Preferences, Notifications, and Data & Privacy through stable URLs and mounts only the active section.
- [ ] Theme/appearance/accent/currency exist in Preferences with unchanged storage semantics and are removed from the desktop sidebar.
- [ ] Clear portfolio exists only under Data & Privacy and all destructive dialogs meet the focus/confirmation contract.
- [ ] Trading 212 connection truth comes only from broker status, never inferred CSV contents.
- [ ] No new database table/migration or frontend runtime dependency is introduced; workspace/RLS/CSRF boundaries remain green.
- [ ] Focused tests, full fast backend suite, local/cloud frontend suites, both builds, PostgreSQL gate, and the four-viewport browser matrix are recorded and pass.

## Review and merge

Inspect the final scope before pushing:

```powershell
git status --short --branch
git diff --check origin/codex/portfyl-ux-overhaul...HEAD
git diff --stat origin/codex/portfyl-ux-overhaul...HEAD
```

Push `codex/ux-07-product-flows` and open its PR against `codex/portfyl-ux-overhaul`. Required CI includes the PostgreSQL tenant-isolation job and both frontend editions. Merge only after review and green checks. Plan 8 starts from the new integration HEAD after this phase is merged.

## Self-review notes

- Stock §10.4 maps to Tasks 2–3; Watchlists §10.5 to Task 4; Import/Onboarding §10.6 to Tasks 6–7; Settings §10.7 and the deferred sidebar requirement from Plan 3 map to Tasks 5–6.
- The pending marker uses established workspace-scoped storage to meet the cancellation contract without a migration. It is hidden customer-internal state, capacity-counted, and covered by PostgreSQL tenant/CSRF tests.
- Plan 8 may add Assistant context preferences inside the Data section and lazy-load these route/tab components. It must preserve the URL values and component boundaries defined here.
