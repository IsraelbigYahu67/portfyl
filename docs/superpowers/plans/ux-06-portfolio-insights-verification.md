# UX-06 Portfolio Insight Decisions Verification

Date: 2026-09-13
Branch: `codex/portfyl-ux-overhaul`

## Automated gates

| Gate | Result |
| --- | --- |
| `cd frontend; npm test` | Exit 0 — 61 files, 305 tests passed |
| `cd frontend; npm run test:cloud` | Exit 0 — 61 files, 305 tests passed |
| `cd frontend; npm run build` | Exit 0 — local production build completed |
| `cd frontend; npm run build:cloud` | Exit 0 — cloud production build completed |

Phase 6 is frontend-only. The backend was untouched, so its baseline remains
the 638 passing fast-suite tests recorded for Phase 5; the PostgreSQL/RLS
suite is unaffected and stays a CI gate.

## Implementation summary

| Task | Commit | Result |
| --- | --- | --- |
| 1. Attention signals | `f99dc78` | `derivePortfolioAlerts`: concentration >25%, dividend review, incomplete tax FX, events within 14 days; deterministic severity/date ordering |
| 2. Edition-safe tax signal | `f86fc85` | `fetchEditionDashboardSignals()` on both manifests; cloud resolves `{ taxReport: null }` and does not import `localApi` (asserted against the manifest source) |
| 3. Dashboard attention + order | `40966eb` | `DashboardAttention`; Dashboard h1 is `Dashboard`; fixed order performance → concentration (holdings + heatmap) → attention (signals + earnings) → movers → collapsed insider activity |
| 4. Layout controls + migration | `0e4d7b6` | `normalizeWidgetOrder`, order-first `sb_dashboard_widget_order_v2`, labelled Move up/down/Hide/Restore/Reset controls, retired ids discarded |
| 5. Allocation composition | `4f4432f` | `allocationRows`/`boundedAllocationRows`, `AllocationBreakdownList`; Position/Sector/Asset type/Currency (+Account when present), Active/Sold tabs, 7+Other chart with full text list |
| 6. Analytics risk-first | `fc76e21` | Shared `ChartSummary`; Analytics drops Sector/Country/Asset-type blocks, orders risk → benchmark → risk-adjusted/drawdown → correlations, adds period/data-loaded context and data-summary tables |

## Behavioral notes / deviations

- `DashboardGrid`'s widget ids changed to match the new grouped blocks
  (`performance`, `concentration`, `attention`, `movers`, `insiderBuys`).
  Stored pre-Phase-6 layouts are discarded once by `normalizeWidgetOrder`
  rather than rendering holes.
- The `All Holdings` table remains on Allocation below the composition card;
  the Active/Sold tabs govern the chart + full-list composition only.
- `AllocationBarList` is now a thin wrapper over `allocationRows` +
  `AllocationBreakdownList` so there is a single sorting/rendering path; its
  existing tests still pass unchanged.
- Test-only updates required by the new page composition:
  `Dashboard.async.test.jsx` wraps in a `MemoryRouter` (attention links),
  mocks `@edition-manifest`, and orders mocked grid children by the real
  widget order; `Analytics.async.test.jsx` no longer asserts a sector-block
  fetch.

## Browser matrix

**Not executed in this environment** — no browser-automation tool was
available to this session. Outstanding manual checks (390×844, 768×1024,
1024×768, 1440×900):

- Dashboard order, independent widget failure recovery, keyboard
  Move/Hide/Restore, collapsed insider activity, alert links.
- Allocation category/state switching, seven-plus-Other chart with complete
  text list, sold separation, summary copy.
- Analytics risk-first order with no allocation duplicates, top-ten
  correlations, ≤12 advanced matrix, chart summaries.
- No horizontal overflow, console errors, or failed requests.

## Warnings / deferrals

- Known >500 kB main-chunk build warning persists (baseline; Phase 8).
- The Dashboard no longer fetches `fetchSectorBreakdown`; Analytics stopped
  fetching it in Task 6. The endpoint remains for Allocation.
- Allocation's chart/list for `account` renders only when the payload supplies
  an `accounts` dimension; no synthetic account grouping was added.
