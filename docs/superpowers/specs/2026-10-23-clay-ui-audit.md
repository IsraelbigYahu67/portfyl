# Clay UI/UX audit — 2026-10-23

Browser walk-through of the local edition in **Clay** at 1440×900 and 375×812
(every sidebar page, all five stock-detail tabs, all four Settings sections,
the Add Transaction modal and the portfolio switcher), plus an in-page script
that flagged truncated/overflowing text, text under 12px and legacy Tailwind
classes. Screener scan, Classic dark mode, Login and Onboarding were not
exercised. Each finding has an ID that the fix plan
(`docs/superpowers/plans/2026-10-23-clay-ui-fixes.md`) maps to a task.

## F — Formatting consistency (trust)

- **F1** Money mixes locales: Dashboard `63 898,83 Kč`, Analytics `66,127.45 Kč`
  / `526.49 Kč` (`pages/Analytics.jsx` local `fmt`), hero chips `63.7K Kč`
  (`formatCompact` is always en-US).
- **F2** Quantities mix separators: `0,3` (Transactions) vs `0.5` (Tax Report,
  Dividends) — `formatQuantity` is always en-US.
- **F3** Dates mix five formats: `23. 10. 16:19`, `Oct 16, 2026, 06:50 PM GMT+2`,
  raw ISO `2026-10-15` (Transactions, Cash, Filings, insider table), `Sep 29`
  with no year even under "All years" (Tax Report, insider buys).
- **F4** Raw enum codes shown: `STRONG_BUY`, `INTEREST_ON_FREE_CASH`,
  `LENDING_INTEREST`, lowercase `deposit` in the cash-type select; `--` instead
  of an em dash in Data & Privacy copy; "1 shares".
- **F5** Dividends "Estimated annual income" is shown in USD while the page is
  in the display currency (CZK).

## C — Not yet Clay (legacy Classic styling)

- **C1** Stock detail (`components/StockDetail.jsx`, 143 legacy classes):
  neon `bg-green-500`/`bg-red-500`/`bg-emerald-500`/`bg-slate-500` in analyst
  bars, price targets, DCF grid, insider table; square-cornered financial bars;
  purple TTM legend; non-sliding Annual/Quarterly toggle; square BEAT/SELL/OTHER
  chips; flat nested panels with no clay depth.
- **C2** Analytics correlation matrix: mint/salmon `bg-green-500/30`,
  `bg-red-500/60` cells, square ticker chips; risk badge colors
  `bg-yellow-400/10` etc.; legend dot `bg-gray-500`.
- **C3** Import: flat rectangular stepper, `bg-blue-100`/`bg-green-100` broker
  chips, `hover:border-gray-500` dropzone.
- **C4** Settings: browser-blue radio buttons (`SyncScheduleSettings`), Discord
  `bg-[#5865F2]` buttons/toggle and `bg-indigo-100` badge, `Toggle` off-state
  `bg-slate-300` + white knob, `rounded-lg` Connect/Clear buttons and palette
  chips, a card nested in a card in Data & Privacy.
- **C5** Watchlists Price Alerts: square inputs and Create button, heading style
  unlike other cards.
- **C6** `text-red-600` for Sell/negative and delete hover (Transactions, Cash)
  instead of the `--loss` token; transaction type is colored text, not a capsule.
- **C7** `text-amber-500` "Snapshot stale"; Tax Report `bg-blue-400/10`,
  `bg-yellow-400/10`, `bg-orange-400/10`, `text-amber-300` badges/warnings.
- **C8** Heatmap period selector uses `rounded-md`/`shadow-sm` buttons instead
  of `SegmentedControl`; card shows the title "Heatmap" twice.

## O — Overflow / does not fit

- **O1** Heatmap: bottom tile (CRWV) clipped by the card; tile text 9–10px
  (`Math.max(9|10, …)` in `components/Heatmap.jsx`).
- **O2** Stock financial charts: year ticks 7–8px, YoY labels 9px.
- **O3** Price-target pills (Max/Avg/Current/Min) overlap each other and the
  axis labels and are clipped at the right edge.
- **O4** Cash ledger: amount runs into the note (`+0,10 KčT212 …`), no
  pagination (page 17 900px desktop / 28 000px mobile).
- **O5** Allocation All Holdings table is wider than its card (1295 vs 1134px)
  with no scroll cue; donut legend percent overflows its `w-10` column.
- **O6** Portfolio switcher truncates the name to "P…" next to the
  "DEFAULT 759" badge.
- **O7** Analytics Net profit sub-line wraps to two lines.
- **O8** Mobile: Transactions and Tax Report tables show only Date/Ticker/Type;
  amounts are off-screen. Cash has 438 delete targets under 44px.

## D — Data presentation that misleads

- **D1** Tax Report rows all say red **TAXABLE** while the year card says
  "Taxable in CZ: 0 Kč" (value test passed).
- **D2** Dashboard profit +3 466 Kč vs Analytics "Net profit 526 Kč" and
  "Simple ROI +0.39%" with no explanation of the difference.
- **D3** Correlation values and Sell rows use the loss color, implying a loss.

## A — Accessibility

- **A1** Add Transaction modal (`pages/Transactions.jsx`): no `role="dialog"`,
  no focus move/trap, Escape does not close it.
- **A2** Modal placeholders `AAPL` / `10` / `185.50` read as filled values.

## U — UX structure

- **U1** Broker snapshot card ("Current positions") sits at the top of
  Dashboard, Allocation (20 rows) and Settings, pushing Net worth below the fold
  on mobile.
- **U2** Transactions: only a ticker filter (no type/date filter).
- **U3** Allocation page is 7 700px: Target allocation lists 22× "No target";
  sold rows repeated at the bottom of All Holdings.
- **U4** Empty states: Search shows only "Start typing"; Screener hides the
  universe/filters the empty state asks for; Watchlists puts Price Alerts above
  the watchlist.
- **U5** Stock detail: "About" is an unclamped wall of text (repeated on
  Valuation); filings not sorted by date and form types unexplained.
- **U6** Settings shows unavailable options greyed out (eToro "not available",
  Appearance/Accent palette under Clay) instead of hiding them.
- **U7** Tax Report §4 summary card is half-width with empty space beside it.

## Out of scope (needs a product decision)

- **X1** Valuation models use current and sector-median P/E
  (`backend/routers/market.py:426-428`), while CLAUDE.md says valuation uses the
  5-year average P/E. Not a UI fix; decide separately.
