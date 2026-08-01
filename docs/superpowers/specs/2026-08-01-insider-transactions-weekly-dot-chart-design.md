# Design: Insider transactions weekly dot chart

**Date:** 2026-08-01
**Status:** Approved (pending spec review)
**Branch:** TBD (created at implementation time)

## Summary

Replace the "Insider Volume" section on the stock detail page — currently a
monthly bar+line chart (`InsiderVolumeChart` in
[StockDetail.jsx](../../../frontend/src/components/StockDetail.jsx)) — with a
weekly price-line chart where every individual insider buy/sell is plotted as
a dot directly on the line. Hovering a dot fades the opposite-side dots to
near-zero opacity and shows an info box (name, date, shares, $ amount) for
that transaction. Based on a user-supplied sketch: a continuous weekly price
line with green (buy) / red (sell) dots sitting on it; hovering a dot keeps
same-color dots visible and fades the other color; a small info box appears
next to the hovered dot.

The separate "Latest Insider Transactions" list (`InsiderTransactionsSection`)
below it is unchanged — it already shows more history (up to 200 rows) than
fits usefully on a chart, and remains the place to scan full detail. Both stay
independent, reorderable/toggleable sections (`insiderVolume` / `insiderTx`)
in `useStockReportConfig`; only the internals of the `insiderVolume` section
change.

## Current state

- `InsiderVolumeChart` (StockDetail.jsx, function starting ~line 1930) fetches
  `fetchHistory(ticker, "1y")` (daily closes) via React Query, aggregates
  `data.insider_transactions` into 12 calendar-month buckets
  (`aggregateInsiderByMonth`) with `buy`/`sell` share totals per month, and
  renders a `ComposedChart`: two `Bar`s (buy/sell share volume, right axis) +
  one `Line` (mid-month close price, left axis). Tooltip shows the month's buy
  and sell totals (shares, value, count).
- `data.insider_transactions` (from `_build_insider_transactions` in
  `backend/routers/market.py`) already carries everything the new design
  needs per transaction: `insider` (name), `position`, `transaction`, `side`
  (`"buy" | "sell" | "other"`), `shares`, `value`, `date` (`YYYY-MM-DD`),
  `ownership`, `url`. **No backend changes are required.**
- `InsiderTransactionsSection` (same file, ~line 2089) renders the detailed
  list/table and is untouched by this design.

## Data & layout

- Reuse the exact same query — `fetchHistory(ticker, "1y")` — no backend or
  API changes. No new `interval` param; weekly points are derived client-side
  from the existing daily series so caching (`AutoLoad.jsx`'s prefetch,
  `_HISTORY_TTL`) behaves exactly as it does today.
- **Weekly bucketing:** walk the daily series into trailing 7-day windows
  covering the fetched range (~52 buckets over 1y). Each bucket's `close` is
  the last available daily close within that window (mirrors the existing
  "closest trading day" snapping style already used for the monthly line, but
  simpler — last-in-window rather than nearest-to-the-15th, since weekly
  buckets don't need a mid-point anchor).
- **Transaction → dot placement:** each transaction with a parseable `date`
  and `side` of `"buy"` or `"sell"` (`"other"` is dropped, same as today's
  monthly aggregation) is snapped to the week bucket whose window contains its
  date. The dot's `(x, y)` is that bucket's `(weekTs, close)`, so dots always
  sit exactly on the price line, per the sketch. Transactions older than the
  1-year window are simply not plotted (they remain visible in the
  `insiderTx` list below, which has no such window) — no error state needed.
- **Overlap handling:** when two or more transactions of the *same side* land
  in the same week bucket, offset their dots vertically in pixel space (not
  data space) by a small fixed step per extra dot (e.g. ±6px, alternating
  above/below the true point), so they don't fully overlap and each stays
  independently hoverable. This must not affect the underlying `close` value
  or the line's shape — it's purely a rendering offset applied in the dot's
  `shape` renderer, computed from the dot's index within its
  week+side group.
- Buys render as `GAIN_COLOR`, sells as `LOSS_COLOR` (from
  `lib/chartTheme.js`), consistent with every other buy/sell color use in
  this file (bars, table rows, pills).

## Interaction

- Hover state is tracked locally in the component (which transaction, if
  any, is hovered — plus its `side`).
- **While a dot is hovered:**
  - Dots on the *opposite* side fade to very low opacity (near-invisible,
    per explicit product decision — not a hard `display:none`, so the chart
    doesn't visually jump, but effectively "gone").
  - Dots on the *same* side as the hovered one are unaffected — full opacity,
    normal size, exactly as when nothing is hovered.
  - The specific hovered dot itself is enlarged with a subtle ring/halo so
    it's unambiguous which transaction the info box refers to.
  - The price line and week-axis are unaffected by hover.
- **Info box:** appears anchored near the hovered dot, showing exactly:
  - `name` — `t.insider`
  - `date` — `t.date`
  - `shares` — `fmtCompact(Math.abs(t.shares), "")`
  - `$ amount` — `fmtCompact(Math.abs(t.value), cs)` (currency symbol from
    `currencySymbol(currencyCode)`, matching the rest of the page)
  - Styled as a small card matching the app's existing custom tooltip
    treatment elsewhere in this file (`bg-surface-card-elevated`,
    `border border-hairline`, `rounded-lg`, `shadow-lg`, `text-xs`) rather
    than a plain unstyled box, for visual consistency with the rest of
    Portfyl. No extra fields beyond the four specified (no side pill, no
    price/share, no P&L) — the detailed table below already covers that.
- No click/tap interaction is added — hover-only, consistent with this app's
  existing desktop-web chart tooltips (mobile is a separate Capacitor app,
  out of scope here).
- Legend stays: Close Price (line) / Insider Buys (green) / Insider Sells
  (red) — same three-item legend as today, unaffected by hover state.

## Visual style

- Same outer wrapper as today: `bg-surface rounded-lg p-4`, `h-72` chart
  area, same section heading "Insider Trading Volume" (heading text
  unchanged — only the chart beneath it changes).
- Chart type: `ComposedChart` with one `Line` (weekly close, left axis, same
  stroke as today) and two `Scatter` series (buy dots, sell dots) sharing the
  same x/y axes as the line — no separate right-hand volume axis anymore
  (that axis existed only for the bar chart's share totals, which are gone).
- X-axis ticks: month labels (reuse `MONTH_LABELS`), consistent with the
  sketch showing `Nov / Dec / Jan / Feb`-style ticks.
- Default dot radius small (~4px); hovered dot larger (~7px) with a stroke
  ring in its own color.
- Empty/loading states unchanged in spirit: if there's no insider activity in
  the window *and* no price history at all, render nothing (`return null`),
  same bail-out condition as today. If there's price history but zero
  transactions in-window, the line still renders with no dots (matches
  current fallback behavior for the bar chart, which also degrades to a bare
  price line).

## Cleanup

- Remove `aggregateInsiderByMonth` and `formatMonthTick` (dead once the
  monthly bar chart is gone).
- Keep `MONTH_LABELS` — still used for x-axis tick formatting and for
  formatting the `date` field shown in the new info box.
- No changes to `useStockReportConfig.js` (`insiderVolume` label "Insider
  Volume" still accurately describes the section).

## Testing

- Add a focused unit test for the weekly-bucketing helper (pure function —
  given a daily price series and a lookback window, returns the expected
  weekly buckets) and for the transaction→bucket snapping logic, following
  the existing pattern in `frontend/src/lib/format.test.js` /
  `src/components/ui/primitives.test.jsx`. No insider-chart tests exist today
  (`InsiderVolumeChart`/`InsiderTransactionsSection` are currently untested),
  so this is new coverage, not a rewrite of existing tests.
- `npm run build` and `npm test` from `frontend/`, per CLAUDE.md.
- No backend tests needed — no backend code changes.
- Manual verification via Playwright against `http://localhost:5173` (dev
  password login) on a ticker with insider activity: confirm dots render on
  the line, hover fades the opposite side and shows the info box with correct
  name/date/shares/$ amount, and that overlapping same-week/same-side
  transactions are visually separated and each independently hoverable.

## Out of scope

- Any backend/API change (no `interval` param, no new endpoint) — everything
  needed is already in `data.insider_transactions` and the existing 1y daily
  history.
- Changing or removing `InsiderTransactionsSection` (the list/table).
- Click/tap-to-pin interaction, or mobile-specific behavior.
- Configurable lookback window (stays fixed at 1y / ~52 weeks, matching
  today's chart).
