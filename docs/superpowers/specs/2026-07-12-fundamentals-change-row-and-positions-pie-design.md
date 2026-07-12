# Fundamentals change row + Allocation positions pie — design

Date: 2026-07-12
Status: approved (user), implementing

Two independent frontend features. No backend changes.

## 1. Change row in fundamentals charts (StockDetail)

Every chart in the Financials grid (`MetricBarChart` ×5, `MergedMetricBarChart`
for Revenue / Diluted EPS) shows the % change vs the previous column as a
second line of the x-axis tick, under the period label — always visible, no
hover needed.

- **Semantics**: value under column *i* = % change vs the previous *displayed*
  non-TTM column. Annual view → YoY; quarterly view → QoQ (adjacent quarter,
  lag 1 — NOT the backend's lag-4 quarterly `yoy`); analyst-estimate columns →
  growth vs prior period. Computed client-side from the values already in the
  chart rows.
- **TTM**: no longer a separate column (superseded during review). The TTM
  level renders as a dotted, semi-transparent purple overlay on top of the
  last full-year bar (annual view only), with a dashed line at the exact
  level, drawn via recharts `Customized` + the Bar's computed rects,
  `pointer-events: none`. That column's tooltip gains a violet `TTM` line;
  the y-domain is widened (5% headroom) only when TTM falls outside the
  bars' own range, preserving nice axis ticks otherwise.
- **Guards** (mirror backend `_yoy`): previous value missing or zero, or both
  values negative → render nothing for that column.
- **Colors**: green ≥ 0, red < 0 for every metric — including Shares
  Outstanding (user preference, overriding the neutral-for-counts
  `changeColor` convention). High-contrast 700-shades, bold, 10px.
- **Rendering**: custom XAxis `tick` component (two `<text>` lines) so each
  number is centered under its column for free. XAxis `height` grows ~16px.
- **Density fallback**: when quarterly labels are angled (>6 columns) the
  change line is hidden; instead the quarterly hover tooltip gains a `QoQ`
  line alongside the existing lag-4 `YoY`.

## 2. Positions pie on the Allocation page

A third `BreakdownChart` pie titled **"Positions"**, first in the chart grid:
desktop row 1 = `[Positions | Sector Allocation]`, Country moves to row 2.

- **Data source**: the page's existing holdings query (`fetchAllHoldings`) —
  `weight` there is % of open-holdings market value (cash-free, closed = 0),
  identical to the table's Weight column. No new endpoint.
- **Slices**: one per open position with weight > 2% (ticker as name). All
  positions ≤ 2% are combined into a single neutral-slate **"Other"** slice.
  Closed positions and cash are excluded.
- **"Other" hover**: tooltip lists the grouped tickers with their weights
  (`PLTR 1.8% · SOFI 1.2% · …`). `BreakdownChart` gets an optional extension:
  a data item may carry `items: [{name, weight}]`, which the tooltip renders
  when present. Sector/country usage unchanged.
- **Legend**: same as other pies — name, weight %, value in display currency;
  "Other" shows combined weight/value.
- **Loading**: tied to the holdings query (not the breakdown query), so the
  pie appears/refreshes with the table and the "Refresh prices" button.

## Testing

- Unit tests (vitest) for the two new pure helpers: the vs-previous-column
  change computation (TTM skip, zero/negative guards) and the >2% / "Other"
  grouping.
- Manual verification of both pages via the running dev servers.
