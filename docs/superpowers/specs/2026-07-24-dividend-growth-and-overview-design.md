# Design: Dividend-growth analytics, cross-portfolio Overview, and dividend-calendar removal

**Date:** 2026-07-24
**Status:** Approved (pending spec review)
**Branch:** `feat/dividend-growth-and-overview`

## Summary

Three independent changes to Portfyl, bundled because they touch overlapping
files (`Dividends.jsx`, `portfolio.py`, the sidebar/routes) and were requested
together:

1. **Remove the forward dividend calendar entirely** — the dead
   `/analytics/dividend-calendar` endpoint and its already-removed frontend page.
   Preserve the Discord ex-date notification job that shares one helper with it.
2. **Cross-portfolio "Overview" page** — a new, non-portfolio-scoped page showing
   total net worth (sum across all portfolios, in the active display currency)
   plus combined sector/country/asset-type allocation.
3. **Dividend-growth analytics** — per-holding growth metrics (streak, 5yr CAGR,
   YoY, payout ratio) in a table on the Dividends page, and a per-share dividend
   history chart on the stock detail view.

Each is described in its own section below. They can be implemented and reviewed
independently; there is no runtime dependency between them.

---

## 1. Remove the forward dividend calendar

### Current state

- **Frontend removal is already done** (uncommitted, carried onto this branch):
  `pages/DividendCalendar.jsx` deleted; `fetchDividendCalendar` removed from
  `api.js`; the "Div. Calendar" nav link and unused `CalendarCheck` icon removed
  from `Sidebar.jsx`; a stale comment reference cleaned from `chartTheme.js`;
  the import + `/dividend-calendar` route removed from `App.jsx`.
- **Backend still present:** `backend/routers/dividend_calendar.py` exposes
  `GET /api/analytics/dividend-calendar` (12-month forward projection — now
  unreachable from the UI). The same file defines `_next_dividend_info(symbol)`,
  which **`backend/jobs.py` imports and uses** (via `_upcoming_dividends`) for
  the Discord ex-dividend notification job (`dividend_exdate_pass`). That job is
  a live, working feature and must keep functioning identically.

### Approach

Relocate the shared helper, then delete the router.

- Move `_next_dividend_info(symbol)` (and its module-level `import`s that it
  actually needs: `date`/`timedelta`, `pandas as pd`, `yfinance as yf`,
  `yf_symbol` from `ticker_map`) **into `backend/jobs.py`** as a private
  helper. `jobs.py` already lazy-imports it inside `_upcoming_dividends`; that
  lazy import becomes a direct reference to the now-local function. No behavior
  change — same yfinance calls, same return shape.
- Delete `backend/routers/dividend_calendar.py` in full (the `dividend_calendar`
  router and the `dividend_calendar()` endpoint go away with it).
- In `backend/main.py`: remove `dividend_calendar` from the `from routers import …`
  line and delete the `app.include_router(dividend_calendar.router, …)` line.

### Tests

- `backend/tests/test_dividend_calendar.py`: tests that exercise
  `_next_dividend_info` (helper behavior) move to `backend/tests/test_jobs.py`,
  re-pointed at the new location. Tests that hit the HTTP `dividend_calendar()`
  endpoint are deleted (the endpoint no longer exists). If, after moving the
  helper tests, the file has nothing left, delete it.
- `backend/tests/test_jobs.py` already imports from `jobs`; update any
  `from routers.dividend_calendar import _next_dividend_info` to the new path.

### Verification

Full backend suite green (`python -m pytest tests/ -v` from `backend/`), with
particular attention to `test_jobs.py` — the Discord notification path must still
find `_next_dividend_info` and produce the same `_upcoming_dividends` output.

---

## 2. Cross-portfolio "Overview" page

### Goal

A single page answering "how are we doing across everything?" — the user runs two
portfolios (`zubik`, `mama`). Scope per the brainstorm: **total net worth + daily
change** (summed across all portfolios) and **combined allocation** (sector,
country, asset-type). Explicitly out of scope for now: a side-by-side per-portfolio
comparison table, and a combined performance/TWR time-series chart.

### Backend

New endpoint `GET /api/portfolios/overview` in `backend/routers/portfolios.py`.
`/portfolios` is already in the frontend's `PORTFOLIO_AGNOSTIC_PREFIXES`, so the
axios interceptor will **not** inject `portfolio_id` — correct, this is
cross-portfolio.

Accepts `currency: str = "USD"` (respects the app's display-currency toggle, same
as every other page). Iterates all `Portfolio` rows and, for each `pid`:

- **Net worth + day change:** calls the existing `get_summary(currency=…, db=db,
  pid=p.id)` from `routers/portfolio.py` **directly** (plain function call, not
  through FastAPI DI — the same pattern `jobs.py` uses to reuse router logic).
  Sums `net_worth` and `day_change` across portfolios; recomputes the combined
  `day_change_percent` from summed change ÷ summed prior value (skip when the
  base is 0). This reuses all existing FX/cash/valuation logic with no
  duplication.

- **Combined allocation:** requires a small refactor of `sector_breakdown` in
  `routers/analytics.py` (see below) so raw per-dimension totals can be summed
  across portfolios **before** weighting. Sum the raw `sector_totals`,
  `country_totals`, `type_totals` dicts across all portfolios (same ticker held
  in two portfolios naturally accumulates), then call the existing `_weighted()`
  once on each combined dict.

Response shape:

```json
{
  "currency": "CZK",
  "total_net_worth": 1234567.0,
  "total_day_change": 4321.0,
  "total_day_change_percent": 0.35,
  "portfolio_count": 2,
  "sectors":     [{"name": "...", "value": ..., "weight": ...}, ...],
  "countries":   [ ... ],
  "asset_types": [ ... ]
}
```

### Refactor: extract raw allocation totals from `sector_breakdown`

`analytics.py::sector_breakdown` currently computes raw `defaultdict` totals
(sector/country/type/currency), appends the folded Cash bucket, then returns
`_weighted(...)` of each. To reuse the raw totals for aggregation:

- Extract the raw-totals computation into a new module-level helper, e.g.
  `_allocation_totals(db, pid, display_ccy) -> dict` returning
  `{"sectors": {...}, "countries": {...}, "asset_types": {...},
    "currencies": {...}, "cash_total": float, "cash_by_ccy": {...},
    "total_value": float}` — the raw `defaultdict`/float values **before**
  `_weighted`, including the existing cash-folding and cash-only-portfolio
  branches.
- `sector_breakdown` becomes a thin wrapper: call `_allocation_totals`, then
  `_weighted` each dimension exactly as today. Its response is byte-for-byte
  unchanged (guard with the existing `test_analytics` tests).
- The Overview endpoint calls `_allocation_totals` per portfolio and merges the
  raw dicts. Overview merges only sector/country/asset-type (per scope); the
  currency dimension stays available in the helper for `sector_breakdown` but
  Overview ignores it.

This is the only change to existing backend logic; it is behavior-preserving for
the single-portfolio path.

### Frontend

- New page `frontend/src/pages/Overview.jsx`:
  - Header stat block: large **total net worth** in the active currency + **daily
    change** (absolute + %), styled like the Dashboard summary cards
    (reuse `MetricCard` where it fits).
  - Three allocation pie charts (sector / country / asset-type) using the same
    recharts + `chartTheme` tokens and visual treatment as `Allocation.jsx`.
    Factor out a small shared pie component if `Allocation.jsx`'s chart is not
    already reusable; otherwise mirror its markup.
  - React Query key e.g. `["overview", currency]`; new `fetchOverview(currency)`
    in `api.js` hitting `/portfolios/overview`.
- Wire-up: add the route in `App.jsx` (e.g. `/overview`) and a nav link in
  `Sidebar.jsx` `T212_LINKS` (near the top, after Dashboard — an icon like
  `Layers` or `Globe` from lucide). Overview is a T212-platform page only
  (IBKR/Polymarket keep their own minimal link sets).

### Edge cases

- Single portfolio: page still works (sum of one). Values equal that portfolio's
  Dashboard headline — acceptable.
- A portfolio with no transactions contributes 0 to sums and empty allocation
  dicts; merging must tolerate empty/missing dimensions.
- CZK unavailable (FX rate missing): the currency toggle already disables CZK in
  that state; Overview inherits the active currency, so no extra handling needed.

---

## 3. Dividend-growth analytics

### Goal

For dividend-paying holdings, show how the dividend has grown over time. Two
surfaces (per the brainstorm — "obojí"):

- **Dividends page:** a portfolio-wide table, one row per dividend-paying
  holding, with growth metrics for a quick cross-portfolio scan.
- **Stock detail:** a per-share dividend history chart (quarterly bars, as many
  years as yfinance provides) plus the same growth metrics for that one stock.

### Shared backend helper

New module `backend/dividend_growth.py` (top-level, alongside `fx.py` /
`cash_ledger.py` — not under `routers/`). One public function:

```
compute_dividend_growth(symbol: str) -> dict
```

- Pulls `yf.Ticker(yf_symbol(symbol)).dividends` (full available history — do
  not truncate).
- Aggregates payments into **calendar-year** per-share totals (sum of all
  ex-dated payments in each year) → an ordered annual DPS series.
- **streak_years:** count of consecutive most-recent *closed* years where annual
  DPS strictly increased year-over-year (start from the last complete year and
  walk back while each year > prior). The in-progress current year is excluded
  from the streak calc (partial data would break the comparison).
- **cagr_pct + cagr_years_used:** CAGR of annual DPS over up to the last 5 closed
  years. If fewer than 5 closed years exist, compute over what's available and
  report `cagr_years_used` so the UI can label it honestly (e.g. "3yr"). Needs a
  positive start value; return `null` cagr if the earliest year in the window is
  0 or missing.
- **yoy_pct:** last closed year vs. the year before it.
- **payout_ratio_pct:** reuse the existing normalization already in
  `routers/market.py` (`_f` + `_to_pct` over `info.get("payoutRatio")`). Import
  and reuse — do not re-derive. (If importing from a router is awkward, lift
  those two tiny helpers into a shared util and import from both places.)
- **payments:** the raw per-payment series `[{ex_date, amount}, …]` for the chart
  (no forcing monthly payers into quarters — render what actually occurred).
- **annual:** the aggregated `[{year, dps}, …]` series (used by the streak/CAGR
  display and available to the chart if a yearly view is preferred).
- Wrap the yfinance call in `cache.ttl_cache` with a ~1h TTL (dividend schedules
  change slowly — the deleted calendar used the same TTL).
- yfinance-noise tolerant: thin/non-paying tickers return a well-formed dict with
  `null` metrics and empty `payments`/`annual`, never an exception (consistent
  with the codebase's empty/null handling convention).

### Endpoint A — portfolio table

`GET /api/portfolio/dividends/growth` in `routers/portfolio.py`, portfolio-scoped
(uses `require_portfolio`). Builds current open holdings (reuse `_build_holdings`
over the portfolio's transactions), and for each held ticker calls
`compute_dividend_growth`. Returns a **lightweight** list (no `payments` series —
keep the payload small):

```json
[{"ticker": "...", "name": "...", "streak_years": 12, "cagr_pct": 8.4,
  "cagr_years_used": 5, "yoy_pct": 6.1, "payout_ratio_pct": 42.0}, ...]
```

Skip non-payers (all-null metrics) so the table shows only relevant rows.

### Endpoint B — stock detail

`GET /api/market/{ticker}/dividend-growth` in `routers/market.py`. Returns the
full `compute_dividend_growth` dict for one ticker, **including** `payments` and
`annual`, for the chart.

### Frontend

- **Dividends page** (`pages/Dividends.jsx`): new section "Dividend growth" with a
  table — columns Ticker · Company · Streak (e.g. "12 yrs") · 5yr CAGR (labeled
  with `cagr_years_used` when < 5) · YoY · Payout ratio. Rows clickable → open the
  stock detail (reuse `useStockDetail().openStock(ticker)`, already used by the
  existing dividends table). New `fetchDividendGrowth()` in `api.js` →
  `/portfolio/dividends/growth`; React Query key `["dividend-growth"]`.
- **Stock detail** (`components/StockDetail.jsx`, `StockOverview`): new section
  with a recharts **bar chart** of per-share dividend history (from `payments`,
  x = ex-date, y = amount — as many years as returned), plus three stat tiles
  (streak / CAGR / YoY) sitting next to the existing Div Yield + Payout Ratio
  metrics (already rendered around line 830 / the ratios list). New
  `fetchStockDividendGrowth(ticker)` in `api.js` → `/market/{ticker}/dividend-growth`;
  React Query key `["dividend-growth", ticker]`. Render nothing (or an empty
  state) when the stock pays no dividend.

### Tests

- `backend/tests/` new coverage for `compute_dividend_growth` with a synthetic
  dividend series (monkeypatch the yfinance fetch): rising series → correct
  streak/CAGR/YoY; a cut/flat year → streak breaks; <5 years → `cagr_years_used`
  reflects reality; empty series → all-null, no exception. Add to a new
  `test_dividend_growth.py` (register it in the module list noted in CLAUDE.md).
- Endpoint tests calling the router functions directly (per the repo's
  no-TestClient convention in `tests/helpers.py`).

---

## Cross-cutting notes

- **Currency:** money figures follow the CZK-default portfolio-level convention;
  per-share dividend amounts on the stock chart stay in the stock's **native**
  currency (per the cash-model rule — do not convert per-share prices to CZK).
- **Migrations:** none. No new tables or columns — all three features are
  read/compute-only over existing data and yfinance.
- **`owner_id`:** untouched (`"default"` everywhere, as today).
- **Sidebar scope:** new nav entries go in `T212_LINKS` only.

## Testing summary

- Backend: `python -m pytest tests/ -v` from `backend/` green, including the new
  `test_dividend_growth.py` and the relocated `test_jobs.py` dividend-helper
  tests.
- Frontend: `npm run build` green; verify Overview, the Dividends growth table,
  and the stock-detail dividend chart via Playwright against
  `http://localhost:5173` (login with the dev password) per CLAUDE.md.

## Out of scope (explicitly deferred)

- Per-portfolio side-by-side comparison table on Overview.
- Combined TWR/performance chart on Overview.
- Any push/email notification channel (Discord remains the only one).
- Dividend safety scoring beyond the raw payout ratio.
