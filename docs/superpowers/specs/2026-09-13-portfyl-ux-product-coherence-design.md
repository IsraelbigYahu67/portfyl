# Portfyl UX Reliability and Product Coherence Overhaul — Design Specification

**Date:** 2026-09-13  
**Status:** Awaiting owner review  
**Planning branch:** `codex/portfyl-ux-overhaul`  
**Implementation base:** `codex/portfyl-ux-overhaul`  
**Scope:** Existing `portfyl` repository, local and cloud editions

## 1. Purpose

Portfyl already has broad portfolio-management functionality and a coherent visual
foundation. The next release should make that functionality trustworthy, legible,
responsive, and predictable before adding more breadth. This program addresses the
highest-risk data defects first, then removes structural UX debt, and finally reshapes
the most important pages around decisions users need to make.

The work will be delivered as eight independently reviewable implementation plans.
Every implementation branch will be based on the integration branch above, never on
`main`, and will merge back into the integration branch only after its own tests and
review pass. `main` remains untouched until the whole program is accepted.

## 2. Evidence from the product audit

The audit covered every route reachable from the current Chrome session at
`http://localhost:5173`: Dashboard, Overview, Allocation, Transactions, Search,
stock detail, Watchlists, Import, Dividends, Analytics, Settings, Assistant, Tax
Report, Screener, portfolio switching, and account controls. Static source inspection
covered the corresponding React pages, shared components, API client, FastAPI routers,
test suites, edition manifests, and CI workflow.

The following observations are the design inputs for this program:

1. **Financial data can look authoritative when it is internally inconsistent.** The
   Dividends page displayed payment dates before their ex-dividend dates and an
   implausible annual distribution estimate. The API currently combines independent
   Yahoo Finance fields without recording freshness, confidence, or validation state.
2. **Tax-lot rounding can manufacture misleading rows.** Tiny FIFO residuals are
   rounded to zero shares and zero monetary values while retaining a non-zero gain
   percentage.
3. **Network failures often render as legitimate empty portfolios.** Most major pages
   read `isLoading` but not `isError`; a failed query is therefore indistinguishable
   from “no data.”
4. **The platform selector models a product that does not exist yet.** A CSV-backed
   portfolio with useful data can still produce “No platforms connected yet” because
   the screen treats a Trading 212 connection as the definition of a platform. Core
   portfolio routes are unnecessarily gated behind `sb_platform`.
5. **The shell is desktop-only.** A fixed 232 px sidebar, `h-screen`, and a separately
   scrolling main region cause narrow-screen overflow and create multiple scroll
   owners.
6. **Navigation contains too many equal-weight destinations.** Dashboard, Overview,
   and Allocation overlap; appearance and currency controls consume permanent sidebar
   space; capabilities are mixed with ordinary portfolio navigation.
7. **Large collections are rendered eagerly.** The Transactions endpoint calls
   `.all()` and the page renders the entire result. Tax lots, sold positions, insider
   rows, and correlation matrices also grow without presentation limits.
8. **The yfinance screener blocks a request while hundreds of external calls finish.**
   It returns at most 50 rows after scanning a universe, offers no progress, and its
   range helper excludes missing values even when the user did not set that filter.
9. **Key pages are organized around available widgets rather than user decisions.**
   Dashboard gives all widgets similar weight, Allocation can produce an unreadable
   many-slice donut, Analytics repeats allocation content, and Stock Detail is a very
   long undifferentiated page.
10. **Important product flows need clearer outcomes.** Watchlists lack a useful empty
    state, Import gives destructive management too much prominence, and Settings mixes
    connections, display, notifications, and privacy controls.
11. **Assistant privacy copy is incomplete.** The UI says an API key is sent to the
    provider but does not plainly disclose that portfolio positions and recent
    transactions are also included in the model prompt.
12. **Startup work is disproportionate.** `AutoLoad` prefetches fundamentals and one
    year of history for every holding. `App.jsx` eagerly imports all route pages. The
    baseline production build emits an application chunk above 1.1 MB uncompressed.
13. **Accessibility coverage is inconsistent.** Search, settings controls, icon-only
    buttons, custom modals, clickable rows, charts, and drag-only dashboard controls
    have missing names, focus behavior, keyboard equivalents, or non-visual summaries.

## 3. Existing decisions that remain authoritative

This specification extends the repository's approved work; it does not replace it.

- The premium theme, design tokens, typography, shared UI primitives, and Stock Detail
  KPI treatment from `2026-08-30-portfyl-premium-redesign-design.md` remain in force.
  New components must consume the existing tokens instead of introducing a second
  visual system.
- The safe import workflow from
  `2026-09-07-portfyl-onboarding-import-safety-design.md` remains in force: preview,
  duplicate detection, activation, and undo behavior must be preserved.
- Public trust, export, deletion, telemetry, and account controls already delivered
  from the September compliance specifications remain in force.
- The separate `portfyl-mobile` specification remains a separate product. This
  program makes the current web app usable at narrow viewports but does not create a
  PWA, duplicate its backend, or claim feature parity with that standalone mobile app.
- Local/cloud edition boundaries remain intact. Tax Report and the yfinance Screener
  stay local-only unless an existing capability manifest explicitly enables them.
- Paid checkout, new broker integrations, investment advice, tax filing, real-time
  streaming quotes, and a full Czech/English language switch are out of scope.

## 4. Program goals and measurable release criteria

### 4.1 Data trust

- No dividend row may present a payment date earlier than the ex-dividend date as a
  valid event.
- Dividend estimates that fail the documented plausibility checks must be labelled for
  review and excluded from aggregate projected income.
- Every dividend estimate exposes provider and retrieval timestamp in its API payload;
  the page explains that projected income is an estimate.
- No tax-lot row may visually show zero quantity and zero basis/proceeds alongside a
  non-zero percentage.
- Tax summaries must reconcile against their detailed rows within one cent per
  currency after documented rounding.

### 4.2 State clarity and accessibility

- Every primary page has distinct loading, error, empty, and populated states.
- Every error state includes a useful message and a retry action unless retry is not
  safe for that operation.
- At 390, 768, 1024, and 1440 CSS pixels, primary navigation remains reachable and no
  page creates viewport-level horizontal scrolling.
- All interactive controls are keyboard reachable, visibly focusable, and have an
  accessible name. Dialog focus is trapped and restored. Route changes focus the new
  page heading.
- Charts have a text summary or tabular alternative; color is never the only signal for
  gain/loss or status.

### 4.3 Scale and responsiveness

- Transactions initially render at most 50 records and use server-side pagination and
  filtering. A normal portfolio must not create thousands of table nodes on first
  render.
- Screener job creation returns within two seconds under normal local conditions and
  then exposes queued/running/completed/failed/cancelled state and numeric progress.
- Startup prefetch performs no per-holding fundamentals/history sweep. Stock-detail
  data is prefetched only after explicit hover, focus, or navigation intent.
- The combined gzip size required for the authenticated shell plus its initial route is
  at least 30% lower than the 2026-09-13 local baseline of approximately 372 KB.
- Both local and cloud production builds remain green. A performance improvement in
  one edition may not pull a local-only module into the cloud bundle.

### 4.4 Product coherence

- Authenticated users with a portfolio land directly on Dashboard regardless of broker
  connection status.
- Navigation contains named groups and one source of truth shared by desktop and
  mobile treatments.
- Overview is removed from primary navigation; `/overview` is a compatibility redirect
  to Dashboard.
- Dashboard, Allocation, Analytics, Stock Detail, Watchlists, Import, and Settings each
  have a single documented user purpose and do not duplicate another page's primary
  visualization.
- The Assistant cannot send portfolio context unless the request explicitly identifies
  the selected context mode, and the user sees what that mode means before sending.

## 5. Design principles

1. **Trust before polish.** Incorrect-looking financial information blocks visual
   refinement of the same surface.
2. **Errors are not empty states.** “No data exists” and “data could not be loaded” are
   separate domain states throughout the product.
3. **Progressive disclosure.** The default view answers the common question; dense
   tables and advanced matrices remain available one interaction deeper.
4. **One source of truth.** Navigation definitions, numeric/date formatting, async-state
   rendering, and pagination controls are shared rather than reimplemented by pages.
5. **Responsive, not reduced.** Narrow screens preserve tasks and data, but change the
   presentation from wide tables and fixed rails to drawers, cards, or reduced columns.
6. **Reversible delivery.** Every phase is isolated, reviewed, and testable before it
   becomes part of the integration branch.
7. **No speculative infrastructure.** In-process jobs and current libraries are enough
   for this local-first product; Redis, Celery, a second design system, and a new state
   manager are not introduced.

## 6. Target information architecture

The authenticated shell has one navigation model in
`frontend/src/components/layout/navigation.js`. Desktop renders it in the existing
sidebar treatment; viewports below the Tailwind `lg` breakpoint render a top bar and a
modal drawer. Capability filtering occurs before either renderer receives the groups.

The target groups are:

| Group | Destinations | Notes |
|---|---|---|
| Portfolio | Dashboard, Allocation, Transactions | The three core portfolio tasks. |
| Research | Search, Screener, Watchlists | Screener appears only when its edition/capability enables it. |
| Insights | Dividends, Analytics, Tax Report | Tax Report remains local-only. |
| Assistant | AI Assistant | A standalone group because of its distinct privacy boundary. |
| System | Import, Settings, capability-specific tools | Import is a workflow, not a broker platform. |

Specific routing decisions:

- Remove `PlatformProvider`, the `sb_platform` gate, and `PlatformLanding` from the
  authenticated route decision. An authenticated user with no portfolio still sees the
  existing Onboarding flow; a user with a portfolio sees Dashboard.
- Trading 212 is represented under **Settings → Connections**, not as a platform that
  owns the rest of the application.
- Keep edition-provided routes and navigation entries, but merge them into the group
  declared by their manifest metadata. Until manifests expose a group field, the
  adapter assigns existing edition entries to `System` or `Research` explicitly.
- Remove Overview from the navigation. Keep `/overview` as `<Navigate replace>` to
  `TRACKER_HOME` for bookmarks. Remove `Overview.jsx` and `fetchOverview` only after a
  repository-wide reference scan proves they have no remaining consumers.
- Move style, appearance, accent, and display-currency controls from the bottom of the
  sidebar into **Settings → Preferences**. The sidebar retains portfolio switching,
  account menu, and compact provider/freshness attribution.

## 7. Shared shell, state, and presentation contracts

### 7.1 App shell

Create `frontend/src/components/layout/AppShell.jsx` as the only owner of authenticated
page layout. It receives already-filtered navigation groups and renders:

- `DesktopSidebar` at `lg` and above;
- `MobileTopBar` plus `MobileNavDrawer` below `lg`;
- one `<main id="main-content">` with natural document scrolling;
- a skip link targeting `#main-content`;
- a route-announcement/focus component that moves focus to the page's `<h1
  tabIndex="-1">` after pathname changes without stealing focus on in-page updates.

`h-screen`, `max-h-screen`, and nested main scrolling are removed. The shell uses
`min-h-dvh`; main padding is responsive (`p-4 sm:p-6`). The drawer is a labelled modal
dialog, closes on Escape and route change, traps Tab/Shift+Tab, returns focus to its
trigger, and prevents background scrolling while open.

### 7.2 Async states

Add two shared modules:

- `frontend/src/lib/apiError.js` exports
  `getApiErrorMessage(error, fallback = "We couldn't load this data.")`. It understands
  FastAPI string details, validation arrays, network failures, timeouts, and ordinary
  JavaScript errors without displaying raw stack traces.
- `frontend/src/components/ui/AsyncSection.jsx` receives `isLoading`, `error`,
  `onRetry`, `loading`, `isEmpty`, `empty`, and `children`. Precedence is loading →
  error → empty → content. It composes the existing `ErrorState`, `EmptyState`, and
  Skeleton primitives rather than restyling them.

Page-level queries use `AsyncSection` around the page body. Independent dashboard and
analytics queries use one boundary per widget so one provider failure does not erase
healthy data. Mutations continue to use toasts and inline form errors; the shared query
boundary is not used to hide a failed destructive mutation.

Skeletons reserve the final component's approximate height. A page must not replace a
large table or chart with a single short “Loading…” line. Empty-state actions point to
an existing working route or control.

### 7.3 Collection controls

Add `frontend/src/components/ui/Pagination.jsx` with an exact contract:

```jsx
<Pagination
  offset={offset}
  limit={limit}
  total={total}
  onOffsetChange={setOffset}
  ariaLabel="Transactions pages"
/>
```

Allowed page sizes are 25, 50, and 100; the default is 50. The component renders item
range, Previous/Next, numbered pages when there are at most seven, and an accessible
page-size selector. Changing filter, sort, tab, year, or portfolio resets offset to
zero. URL search parameters retain shareable collection state on Transactions,
Screener, and Tax Report.

### 7.4 Formatting and provenance

All new financial and date formatting goes through `frontend/src/lib/format.js`.
English remains the interface language in this program. Currency uses the appropriate
locale (`cs-CZ` for CZK, `en-US` for USD); dates use explicit short and long helpers;
quantities preserve up to eight fractional digits without displaying meaningless
trailing zeroes. Values whose non-zero magnitude rounds below one cent render as
`<$0.01`, `>-$0.01`, `<0,01 Kč`, or `>-0,01 Kč`, never as an exact zero.

This centralization is localization readiness, not a language switch. New user-facing
copy must be valid UTF-8 and must not introduce hand-built currency symbols or ambiguous
numeric dates.

## 8. Data trust design

### 8.1 Dividend normalization

`GET /api/portfolio/dividends` remains the endpoint to avoid an unnecessary migration,
but its rows gain additive provenance and validation fields. Existing fields remain
available for one compatibility cycle.

Each row contains:

```json
{
  "ticker": "MSFT",
  "name": "Microsoft Corporation",
  "shares": 10.5,
  "currency": "USD",
  "dividend_rate": 3.32,
  "dividend_yield": 0.72,
  "annual_income": 34.86,
  "ex_date": "2026-08-20",
  "pay_date": "2026-09-10",
  "date_status": "complete",
  "income_status": "estimated",
  "warnings": [],
  "source": "yahoo_finance",
  "as_of": "2026-09-13T10:30:00Z"
}
```

The exact enums are:

- `date_status`: `complete`, `ex_date_only`, `pay_date_only`, `unavailable`,
  `inconsistent`;
- `income_status`: `estimated`, `unavailable`, `review`;
- warning values: `pay_date_before_ex_date`, `non_positive_rate`,
  `implausible_implied_yield`, `provider_fields_disagree`.

Validation rules are deterministic:

1. Non-finite or non-positive rates are treated as unavailable.
2. If both dates exist and `pay_date < ex_date`, return `pay_date: null`, set
   `date_status: inconsistent`, and add `pay_date_before_ex_date`.
3. If rate and a positive current/regular market price exist, calculate implied annual
   yield. A value above 35% sets `income_status: review`, adds
   `implausible_implied_yield`, and sets `annual_income: null` so it cannot contaminate
   the total.
4. If both a provider yield and implied yield exist and differ by more than five
   percentage points **and** more than 50% relative to the smaller positive value, set
   `income_status: review`, add `provider_fields_disagree`, and exclude annual income
   from the aggregate.
5. `as_of` is generated once per endpoint response so all rows in one response share a
   timestamp. A failed ticker remains omitted as today, but the response also exposes a
   top-level `unavailable_tickers` count after the compatibility cycle introduces a
   response envelope.

The first implementation keeps the array response and additive row fields. Moving to a
top-level envelope is explicitly deferred because it would break existing consumers
without improving the first trust fix.

The Dividends page separates **Estimated annual income** from **Known dates**. It never
calls an event “upcoming” unless a valid ex-date is today or later. Rows with uncertain
dates appear under “Date unavailable or needs review,” and rows with `income_status:
review` show a warning rather than an annual dollar amount. A compact disclosure names
Yahoo Finance, displays `as_of`, and says estimates are not guaranteed payments.

### 8.2 FIFO precision and tax presentation

Tax-lot arithmetic keeps full floating-point precision until serialization. Introduce
`LOT_EPSILON = 1e-8` in `backend/routers/analytics.py`. `_consume_fifo` clamps a lot's
remaining quantity and the sale remainder to exact zero when their absolute value is at
or below that threshold, and never emits a matched quantity at or below it.

Serialized gain rows use:

- shares rounded to eight decimal places;
- cost basis, proceeds, and gain rounded to six decimal places;
- `gain_pct: null` when absolute cost basis is below `0.005` in its native currency;
- summary calculations from unrounded internal values, rounded only in the response.

The Tax Report formats tiny non-zero quantities and money with the shared formatting
rules. A null gain percentage renders an em dash with the accessible explanation
“Percentage is not meaningful for a basis below one cent.” CSV export retains the
serialized precision and never substitutes a live CZK rate for the trade-date FX fields.

Backend tests cover fractional buys, split-adjusted lots, multi-lot sells, quantities on
both sides of `LOT_EPSILON`, missing FX, and one-cent reconciliation between detailed
rows and summaries. No legal threshold or exemption rule changes in this program.

## 9. Collection and long-running work design

### 9.1 Transactions

Keep `GET /api/portfolio/transactions` for compatibility. Add:

`GET /api/portfolio/transactions/page?offset=0&limit=50&q=&type=&sort=-date`

The response is:

```json
{
  "items": [],
  "total": 677,
  "offset": 0,
  "limit": 50
}
```

Rules:

- `offset >= 0`; `limit` is 25, 50, or 100; invalid values return HTTP 422.
- `q` case-insensitively matches ticker and notes; `type` accepts the existing
  transaction types; omitted filters do not constrain results.
- `sort` accepts `date`, `-date`, `ticker`, `-ticker`, `type`, and `-type`; default is
  `-date` with ID as a deterministic secondary key.
- Filtering, count, sorting, offset, and limit occur in SQL and remain portfolio- and
  owner-scoped before pagination.
- The existing unpaged endpoint stays covered by compatibility tests but is no longer
  called by the SPA or startup prefetcher.

Transactions uses URL-backed filter/type/sort/page state, preserves the existing add,
delete, and note mutations, returns to the nearest valid page after deletion, and
invalidates only affected transaction-page queries plus dependent summaries.

### 9.2 Other large views

- Tax Report paginates each tab client-side at 50 rows because calculation and CSV
  export require the complete report payload. Tab/year/page live in URL parameters.
- Allocation shows the largest seven slices plus an `Other` slice in the chart and a
  sorted bar list for the full breakdown. Active positions are the default; sold
  positions are a separate disclosure, not mixed into the chart.
- Stock Detail paginates insider tables at 25 rows within their tab.
- Analytics displays the ten strongest absolute correlation pairs first. The complete
  matrix is an advanced disclosure limited to at most 12 explicitly selected holdings;
  selection beyond 12 is disabled with an explanation.
- Virtualization is not introduced in the first pass. Pagination bounds the DOM and is
  simpler to test, print, navigate with a keyboard, and preserve in URLs.

### 9.3 Screener jobs

The Shibui database path remains synchronous because it is one bounded query. The
yfinance universe path moves to an authenticated in-process job service in
`backend/services/screener_jobs.py`; no queue service or database table is added.

The API is:

- `POST /api/market/screener/jobs` with a JSON body containing the current universe,
  filters, and sort fields. Returns HTTP 202.
- `GET /api/market/screener/jobs/{job_id}?offset=0&limit=50` for status and paged
  results.
- `DELETE /api/market/screener/jobs/{job_id}` to request cancellation.

Creation/status payloads use this contract:

```json
{
  "job_id": "uuid",
  "status": "running",
  "progress": {"completed": 143, "total": 503, "percent": 28},
  "result": {"items": [], "total": 0, "offset": 0, "limit": 50},
  "unavailable_count": 4,
  "error": null,
  "created_at": "2026-09-13T10:00:00Z",
  "expires_at": "2026-09-13T10:30:00Z"
}
```

Statuses are exactly `queued`, `running`, `completed`, `failed`, and `cancelled`.
`result` is null before completion; `error` is a safe user-facing message only for a
failed job. Jobs are bound to the authenticated user identity on the server, never to a
client-supplied owner ID. Unknown, expired, or other-user IDs return 404.

The registry permits one active yfinance scan process-wide and queues later distinct
requests. An identical request fingerprint from the same user reuses its active or
unexpired completed job. Each future completion increments progress under a lock.
Cancellation stops scheduling/collecting additional work where possible; it does not
claim that an already-running external call was killed. Completed/failed/cancelled jobs
expire after 30 minutes; registry cleanup also enforces a maximum of 20 retained jobs.

Missing-value semantics are fixed independently: `_in_range(None, None, None)` returns
`True`; a missing value fails only when at least one bound for that metric is present.
The synchronous legacy yfinance GET remains temporarily available and deprecated, but
the SPA no longer calls it.

The Screener page creates a job, polls every second while queued/running, pauses polling
when the tab is hidden, resumes on visibility, exposes Cancel and Retry, and renders
results through shared pagination. Navigating away does not cancel automatically; a
return within the TTL reconnects to the job ID stored in session storage.

## 10. Page-level product design

### 10.1 Dashboard

Dashboard answers four questions in this order:

1. What is the portfolio worth and how did it change today?
2. How has it performed over the selected period and benchmark?
3. Where is risk concentrated?
4. What needs attention next?

The default layout is a fixed responsive sequence: portfolio hero; performance chart;
concentration/holdings; alerts and upcoming events; top movers. Insider activity moves
below these sections and is collapsed by default. Alerts are derived from existing
data: concentration above a documented threshold, dividend data marked for review,
missing FX needed for tax, and upcoming earnings/dividend dates. An alert links to the
surface where the user can understand it.

Customization remains optional on desktop. Dragging is retained, but every widget also
has labelled Move up, Move down, Hide, and Restore controls. Mobile always renders a
single column using the persisted order. Saved layouts containing retired widget IDs
are migrated once and unknown IDs are ignored safely.

### 10.2 Allocation

Allocation owns composition analysis. It provides category selection (sector, asset
type, currency, and account when supported), a seven-plus-Other chart, a sorted bar
breakdown, concentration callouts, and an active/sold switch. It does not repeat the
performance or correlation views. Each chart segment and bar is represented in a text
list with label, value, and percentage.

### 10.3 Analytics

Analytics owns comparative risk and relationship analysis. Its top layer is risk
metrics and benchmark comparison. Sector allocation is removed because Allocation owns
that question. Correlation defaults to the strongest pairs; the matrix is advanced and
selection-limited as defined above. Every metric includes a short plain-language
definition and its period/data-as-of context.

### 10.4 Stock Detail

The existing long page is split into route-local tabs while preserving `/stock/:ticker`:

- **Overview:** quote, chart, “Your position,” key KPIs, notes, and recent transaction;
- **Financials:** statements, growth, margins, and dividend history;
- **Valuation:** ratios, estimates, DCF/valuation tools already supported;
- **Ownership:** ownership, institutional data, and insider activity;
- **Filings:** filings and related capability-backed content.

The selected tab uses `?tab=` so reload/back/forward work. “Your position” contains
shares, average cost, market value, unrealized P&L, portfolio weight, and the most recent
transaction, with an empty treatment for unowned researched symbols. Data queries are
enabled only for the active tab except lightweight Overview data. Large sections move
from `StockDetail.jsx` into named tab components; the route page coordinates state but
does not continue growing as one multi-thousand-line component.

### 10.5 Watchlists

The empty state explains the benefit and focuses an add-ticker autocomplete. A watchlist
with items provides search, sort, an inline remove action with accessible confirmation,
and an optional alert status. Controls that require Discord or another missing
connection are disabled with a reason and a direct link to Settings → Notifications.
Success and failure of every mutation are explicit; optimistic removal rolls back on
failure.

### 10.6 Import and onboarding

The existing preview/commit/undo contract remains. The Import page presents the flow as
Select source → Preview changes → Confirm import → Result/Undo. “Clear portfolio” and
other destructive data management move to Settings → Data & Privacy and require the
existing confirmation pattern. Import cancellation does not leave a newly created
blank portfolio: onboarding keeps the portfolio in its existing pending activation
state until a blank setup or successful import explicitly activates it.

### 10.7 Settings

Settings uses four URL-addressable sections:

- `?section=connections`: Trading 212 and any capability-provided integrations;
- `?section=preferences`: theme style, appearance, accent, display currency;
- `?section=notifications`: Discord and future notification destinations;
- `?section=data`: export, deletion, destructive portfolio management, privacy, and
  assistant context preference.

Desktop uses a narrow section nav plus a readable content column; narrow viewports use
a select or horizontal tab list. Existing backend behavior and compliance warnings are
preserved. Settings never displays a successful connection state merely because a
portfolio contains imported CSV data.

## 11. Assistant privacy contract

The Assistant supports two explicit request modes:

- `none`: send the user's message and conversation context, but no portfolio data;
- `portfolio_summary`: also send up to 25 positions and 15 recent transactions, using
  the exact server-side scope already implemented.

Every chat request includes `context_mode`; the backend defaults an omitted value to
`none`. The server builds portfolio context only for `portfolio_summary`. Client copy
must list the categories shared—tickers, quantities, prices/values, and recent trade
details—name the configured model provider, and explain that market data may be delayed.

Before the first `portfolio_summary` request, the UI displays a consent dialog with
**Ask without portfolio data** as the safe secondary action and **Share for this
conversation** as the explicit primary action. Consent is conversation-scoped by
default. Settings may remember a preferred mode, but opening a new conversation still
shows the active mode beside the composer and allows changing it before send.

Assistant responses add metadata:

```json
{
  "answer": "...",
  "model": "configured-model-name",
  "provider": "deepseek",
  "context_mode": "portfolio_summary",
  "context_as_of": "2026-09-13T10:30:00Z"
}
```

No raw prompt, secret, or API key is returned. The UI displays provider/model and
context timestamp in a compact details disclosure. It does not describe the response as
live, guaranteed, personalized financial advice, or a source-backed answer unless the
backend actually provides citations.

## 12. Performance and loading strategy

### 12.1 Route loading

Convert authenticated page imports in `App.jsx` to `React.lazy` with a shared route
fallback that matches page-shell dimensions. Auth pages may remain eager if splitting
them does not improve authenticated startup. Edition manifests must preserve static
build-time exclusion so local-only route code is absent from cloud output.

The build task records before/after Vite asset tables in its implementation notes and
checks the 30% combined-gzip target. Large libraries may be split into stable vendor
chunks when that improves caching, but chunk naming is not used to hide an unchanged
initial transfer.

### 12.2 Prefetching

Replace the global `AutoLoad` sweep with deliberate intent:

- On authenticated startup, prefetch only Dashboard summary, holdings, default-period
  performance, and current portfolio metadata.
- Prefetch the next route chunk on navigation-link hover/focus.
- Prefetch stock Overview fundamentals/history on ticker-link hover/focus after a short
  150 ms intent delay; cancel the timer when intent ends before it fires.
- Never prefetch fundamentals and history for every holding.
- Do not preload Transactions, Dividends, Analytics, Settings, or all trade notes until
  the user expresses route intent.
- Portfolio or currency changes cancel in-flight intent timers and remove incompatible
  cache entries using the existing portfolio-isolation rules.

### 12.3 Worktree browser ports

`frontend/vite.config.js` reads the optional `VITE_API_PROXY_TARGET`, defaulting to
`http://localhost:8000`, while retaining port 5173 as the default. This allows the main
checkout and implementation worktree to be tested side by side:

```powershell
# Worktree backend
python -m uvicorn main:app --reload --port 8001

# Worktree frontend
$env:VITE_API_PROXY_TARGET='http://localhost:8001'
npm run dev -- --port 5174
```

The implementation plans will state the correct working directory for both commands.
The currently open `:5173` tab continues to show whichever checkout started that
process; switching Git branches does not magically change an already running server.

## 13. Accessibility acceptance details

The implementation plans apply these requirements to every changed surface:

- Inputs have programmatically associated labels; placeholder text is not a label.
- Icon-only buttons have a stable accessible name and visible tooltip where meaning is
  not obvious.
- Clickable table rows are replaced by real links/buttons within cells; no `<tr
  onClick>` is treated as a control.
- Dialogs have role, accessible title/description, Escape close where safe, initial
  focus, focus trap, and focus restoration.
- Destructive actions require the existing `ConfirmDialog`; they are never a single
  icon click with no named confirmation.
- Tabs implement `tablist`, `tab`, `tabpanel`, `aria-selected`, keyboard arrows, and
  URL synchronization.
- Loading indicators use `role="status"` without repeatedly announcing skeleton cells;
  errors use an appropriate alert or live region once.
- Tables preserve real header associations and captions, and responsive card
  alternatives expose the same labels.
- Gain/loss includes signs or words in addition to color. Warning/review states include
  an icon and text.
- Motion respects the existing `prefers-reduced-motion` guard.

Automated component tests assert roles, names, keyboard operation, and focus movement.
The phase QA checklist also requires a keyboard-only walkthrough and browser
accessibility-tree inspection at desktop and 390 px width.

## 14. Delivery architecture: eight plans

The plans are executed in this order. Each row names its required branch and dependency.

| Order | Plan | Branch | Depends on | Primary result |
|---:|---|---|---|---|
| 1 | Data trust: dividends and tax precision | `codex/ux-01-data-trust` | integration base | Validated/provenance-aware dividends and reconciling FIFO presentation. |
| 2 | Platform removal and async-state foundation | `codex/ux-02-platform-state` | plan 1 merged | Direct Dashboard routing, worktree proxy support, shared async/error contracts. |
| 3 | Responsive shell, navigation, and accessibility | `codex/ux-03-responsive-a11y` | plan 2 merged | One navigation source, desktop/mobile shell, focus/dialog/chart accessibility floor. |
| 4 | Scalable collections | `codex/ux-04-scalable-collections` | plan 3 merged | Transaction API pagination and bounded Tax/Allocation/Analytics/insider views. |
| 5 | Non-blocking screener | `codex/ux-05-screener-jobs` | plan 4 merged | Owned in-process jobs, progress/cancel/retry, correct missing-value filters. |
| 6 | Dashboard, Allocation, and Analytics decisions | `codex/ux-06-portfolio-insights` | plans 1–5 merged | Clear hierarchy, distinct page purposes, accessible summaries. |
| 7 | Stock, Watchlists, Import, and Settings flows | `codex/ux-07-product-flows` | plan 6 merged | Tabbed stock research and coherent operational workflows. |
| 8 | Assistant privacy and performance closeout | `codex/ux-08-assistant-performance` | plan 7 merged | Explicit context modes, truthful copy, lazy routes, intent prefetch, final QA. |

Plans 1–8 are deliberately stacked rather than merged independently into `main`.
Later plans may depend on components introduced earlier. The integration branch is the
single source of truth; task branches are short-lived review branches.

## 15. Git and review workflow

For every plan, the executor must:

1. Fetch and create a dedicated worktree from the current integration-branch HEAD.
2. Run this guard before editing:

   ```powershell
   $branch = (git branch --show-current).Trim()
   if ($branch -eq 'main') { throw 'Refusing to work on main' }
   git status --short
   ```

3. Stop if the worktree contains unexplained changes that overlap the plan. Never
   discard, reset, or stage another person's work.
4. Implement in the plan's task order with a failing test before each behavioral
   change, then the minimum implementation, then focused verification.
5. Commit small coherent steps using the exact files named by the plan. Never use
   `git add -A`.
6. Push the task branch and open a pull request targeting
   `codex/portfyl-ux-overhaul`, not `main`. The repository's CI runs for every pull
   request regardless of target branch.
7. Merge only after review and green required checks. Delete only that task worktree
   after its branch is safely merged.

The final integration pull request targets `main` only after all eight phase acceptance
checklists pass and the owner approves the complete browser walkthrough.

## 16. Test strategy

### 16.1 Baseline recorded on 2026-09-13

The isolated planning worktree passed:

- backend fast suite: 584 tests passed;
- frontend local suite: 31 files / 164 tests passed;
- frontend cloud suite: 31 files / 164 tests passed;
- local production build: passed, with the documented large-chunk warning;
- cloud production build: passed, with the documented large-chunk warning.

The PostgreSQL/RLS suite is provided by CI and remains a mandatory merge check. The
warning emitted by the intentional `useAuth` provider test is baseline console output,
not a failing test.

### 16.2 Phase gates

Every plan contains focused test commands for each task. Before its pull request, it
must also run:

```powershell
# backend, when any backend code or API contract changed
cd backend
python -m pytest tests/ -v --ignore=tests/postgres

# frontend, every phase
cd ..\frontend
npm test
npm run test:cloud
npm run build
npm run build:cloud
```

Backend database, auth, owner scoping, migrations, or RLS changes additionally require
the PostgreSQL suite locally when Docker is available and always in CI. A phase that
does not touch backend state may rely on the CI PostgreSQL check but may not waive it.

### 16.3 Browser matrix

Each phase's changed routes are exercised against the worktree server, not assumed from
the `:5173` main-checkout tab. Required viewports are 390×844, 768×1024, 1024×768, and
1440×900. The browser pass verifies:

- happy, loading, empty, and forced-error states;
- keyboard navigation and focus restoration;
- no unexpected console errors or failed API requests;
- local/cloud capability boundaries where the route differs;
- back/forward and reload for URL-backed tabs, filters, and pages;
- no viewport-level horizontal overflow.

Phase 8 repeats a complete route walkthrough and records bundle sizes. The final report
lists all commands, exit codes, CI links, unresolved warnings, and intentional deferrals.

## 17. Compatibility and rollout

- No production database migration is required by this design. Assistant consent is
  request/conversation scoped; screener jobs are in memory; pagination is additive.
- Existing transaction and screener GET endpoints remain during the program so an
  older client does not immediately break. The new SPA stops calling their expensive
  forms. Removal requires a separately approved compatibility change.
- Dividend response fields are additive. Invalid `pay_date` is intentionally sanitized
  to null because preserving a known-wrong value is not compatible behavior worth
  retaining.
- `/overview` redirects instead of returning 404. Stored `sb_platform` is ignored and
  removed once during startup. Existing palette, theme, currency, dashboard layout,
  portfolio, and authentication storage keys remain compatible.
- Each phase can be reverted independently before final integration. If an API and UI
  change must be reverted, revert the whole phase commit series together so contracts
  do not diverge.

## 18. Risks and controls

| Risk | Control |
|---|---|
| Yahoo fields are incomplete or semantically inconsistent | Preserve provenance, deterministic validation, review state, and explicit unavailable state; never invent a date or distribution. |
| In-process jobs disappear on restart | UI treats 404 as expired and offers Restart; acceptable for local-only yfinance scans. |
| Multiple scans exhaust Yahoo or worker threads | One active process-wide scan, request deduplication, bounded existing worker pool, cancellation flag, retained cache. |
| Pagination breaks mutations or cache invalidation | Add endpoint rather than replace old one; query-key factory; tests for delete on last item and filter resets. |
| Responsive changes regress dense desktop workflows | Shared navigation data with two presentations; required desktop and narrow browser matrix. |
| Route splitting violates edition boundaries | Build both editions every phase; import local-only routes only through edition manifests. |
| Accessibility fixes become isolated patches | Shared AppShell, AsyncSection, Pagination, tabs, and dialog behavior; component tests plus per-route manual audit. |
| Earlier approved import/privacy work is accidentally weakened | Preserve existing API contracts and tests; list those specs as explicit prerequisites in relevant plans. |
| Eight stacked branches become difficult to review | Small commits, one phase PR at a time, integration branch as the only base, no parallel merges into main. |

## 19. Explicit non-goals

- Filing taxes, certifying legal correctness, or changing Czech tax-law rules.
- Replacing Yahoo Finance or Shibui with a new data vendor.
- Redis, Celery, message brokers, WebSockets, or server-sent events for screener progress.
- Infinite scrolling or table virtualization in the first collection pass.
- A new component library, CSS framework, global state manager, or runtime UI dependency.
- A full visual rebrand; the current premium/classic themes and token architecture stay.
- Full localization, native/mobile packaging, offline caching, or a service worker.
- Payment activation, pricing changes, a new broker, or broader entitlement work.
- Automatic investment recommendations or claims that Assistant output is financial
  advice.

## 20. Owner review checklist

Approval of this specification locks the following product choices for the detailed
implementation plans:

- Remove platform selection and route portfolio users directly to Dashboard.
- Retire Overview from navigation and redirect its URL.
- Use grouped desktop navigation plus a mobile drawer below `lg`.
- Add transaction pagination without removing the old endpoint.
- Use polling-based, in-process yfinance screener jobs.
- Treat suspect dividend values as review states and exclude them from aggregate
  estimates.
- Split Stock Detail into five URL-backed tabs.
- Require an explicit Assistant portfolio-context mode.
- Keep the interface in English while centralizing locale-aware formatting.
- Deliver through the eight stacked non-main branches and gates defined above.

After owner approval, eight implementation-plan documents plus one master roadmap will
be written under `docs/superpowers/plans/`. Each task will identify exact files,
complete test code or assertions, commands, expected failures/passes, browser checks,
and a small commit boundary so a lower-cost execution model does not need to redesign
the solution while implementing it.
