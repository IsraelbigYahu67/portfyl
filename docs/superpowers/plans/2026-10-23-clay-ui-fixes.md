# Clay UI/UX Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix every finding of the 2026-10-23 Clay audit: one number/date format, no legacy Classic colors on Clay pages, nothing clipped or under 12px, an accessible modal, and the UX restructures the audit lists.

**Architecture:** Wave 1 adds shared building blocks (locale-aware formatters, `Badge`, `Modal`, a Clay `Toggle`, a compact broker-snapshot variant, a legacy-class test guard). Wave 2 applies them page by page, each task owning disjoint files, while Lane S restyles the 3 500-line `StockDetail.jsx` in three sequential tasks. Wave 3 re-runs the audit.

**Tech Stack:** React 18, Vite 6, Tailwind, recharts, Vitest + Testing Library. Frontend only: no backend, migration or lockfile change.

**Spec:** `docs/superpowers/specs/2026-10-23-clay-ui-audit.md` (finding IDs F1–U7 below refer to it). Design rules: `DESIGN.md`.

## Global Constraints

- Colors only from tokens: Tailwind aliases (`text-gain`, `text-loss`, `text-brand`, `bg-surface-card`, `text-muted`, …), `var(--chart-1..8)`, and `CATEGORICAL` / `GAIN_COLOR` / `LOSS_COLOR` / `NEUTRAL_COLOR` from `lib/chartTheme.js`. Tints are `color-mix(in srgb, <token> N%, var(--surface-card))`. No Tailwind palette classes (`bg-green-500`, `text-red-600`, `bg-slate-300`, …) and no `bg-[#hex]`.
- No financial text, chart tick or label below **12px** (`AXIS_TICK_STYLE`, `.financial-*`, `.chart-label`, `.eyebrow`).
- Gain/loss never by color alone: always an arrow or a +/− sign.
- Money: `formatMoney(value, currency)`. Compact: `formatCompact(value, currency)`. Quantities: `formatQuantity(value, currency)`. Table dates: `formatTableDate(iso)`. Timestamps: `formatDateTime(iso)`. No local `toLocaleString`/`toFixed` money formatters.
- UI copy stays English. Number separators follow the display currency (CZK → `cs-CZ`, otherwise `en-US`).
- Clay shapes: buttons, segmented controls and badges are pills. Segmented/period selectors use `components/ui/SegmentedControl.jsx`, inputs use `.input`, primary/secondary buttons use `.btn-primary` / `.btn-ghost`.
- Touch targets ≥ 44px below the `md` breakpoint.
- Never re-add Tax Report/Screener to shared files (`App.jsx`, `Sidebar.jsx`, `api.js`). Edits stay inside their existing page files.
- Every task ends green on `npm test` and `npm run build` in `frontend/`. Tasks touching `Dashboard`, `Settings`, `Import` or `Screener` also run `npm run test:cloud` and `npm run build:cloud`.

## Review Focus

1. **Display currency USD.** All audit numbers were CZK, but a USD user must still see `$1,234.56`, `$63.7K` and `0.5`. → Task 1 tests `formatCompact(63700,"USD")` and `formatQuantity(0.5,"USD")`.
2. **A tax year that fails the value test.** Rows must keep saying Taxable; only years with `value_test_passed` turn them Exempt. → Task 7 test `keeps Taxable when the sell year failed the value test`.
3. **Tiny heatmap tiles (weight just over 1%).** Labels are dropped, never shrunk below 12px, and the tooltip still names the ticker. → Task 3 test `tileLabels hides labels that cannot fit at 12px`.
4. **Ledger lengths at page boundaries** (0, exactly 25, 26 rows). Pagination appears only above one page. → Task 6 test `shows pagination only when rows exceed one page`.
5. **Keyboard users of the new Modal.** Escape closes it and focus returns to the opening button. → Task 2 test `Modal closes on Escape and restores focus`.

## Parallel execution and isolation

| Wave | Tasks | Run together? | Owns |
|---|---|---|---|
| 1 | 1 → 2 | one session, in order | `lib/format.js`, `components/ui/*`, `components/BrokerPositionSnapshot.jsx`, `src/test/legacyClasses.js`, `DESIGN.md` |
| 2 | 3–11 | yes, one worktree branch each | only the files listed in each task |
| S | 12 → 13 → 14 | one session, in order, parallel with wave 2 | `components/StockDetail.jsx`, `components/stock/*`, `components/StockDetail.*.test.*` |
| 3 | 15 | after all merge | verification only |

### Execution schedule (three Sonnet agents per round)

The owner asked for three parallel agents with short tasks. Task 2 is split into **2a** (`Badge`, `Modal`, `src/test/legacyClasses.js`, the `DESIGN.md` paragraph, `ui/index.js`) and **2b** (`Toggle`, `BrokerPositionSnapshot`). The BEAT/MISS badge moves from Task 12 to Task 14, so Task 12 does not need `Badge`. Every agent branches from the `clay-ui-fixes` integration branch as it stood after the previous round's merge.

| Round | Agent 1 | Agent 2 | Agent 3 |
|---|---|---|---|
| 1 | Task 1 | Task 2a | Task 12 |
| 2 | Task 2b | Task 5 | Task 13 |
| 3 | Task 3 | Task 4 | Task 14 |
| 4 | Task 6 | Task 7 | Task 8 |
| 5 | Task 9 | Task 10 | Task 11 |
| 6 | Task 15 (the coordinating session) | | |

Each session branches off the wave-1 merge commit. For visual checks it runs its own Vite port (`npx vite --port 52NN --strictPort`, NN = task number) against the shared local backend on :8000. No task writes data except through explicit UI actions in a test portfolio. No task touches `package.json`, lockfiles, `backend/` or `DESIGN.md` outside Task 2. If a wave-2 task needs a new token or rule, it says so in its PR description and Task 15 folds it into `DESIGN.md`.

---

### Task 1: Locale-aware formatters (F1, F2, F3, F4)

**Files:**
- Modify: `frontend/src/lib/format.js`
- Test: `frontend/src/lib/format.test.js`

**Interfaces:**
- Produces:
  - `displayLocale(currency: string) -> "cs-CZ" | "en-US"`
  - `formatCompact(n, currency = "USD") -> string`: CZK uses a decimal comma
  - `formatQuantity(value, currency = "USD") -> string`: CZK uses cs-CZ separators
  - `formatTableDate(iso: string, now: Date = new Date()) -> string`: `"Oct 15"` within the current year, `"Oct 15, 2025"` otherwise, `"—"` for empty or invalid input
  - `humanizeCode(code: string) -> string`: `"INTEREST_ON_FREE_CASH"` → `"Interest on free cash"`
  - `pluralize(n: number, one: string, many: string) -> string`: returns the word only

- [ ] **Step 1: Write the failing tests** in `format.test.js`:

```js
describe("locale-aware formatting", () => {
  it("formatCompact uses a decimal comma for CZK and keeps USD", () => {
    expect(formatCompact(63700, "CZK")).toBe("63,7K Kč");
    expect(formatCompact(168.7, "CZK")).toBe("168,7 Kč");
    expect(formatCompact(63700, "USD")).toBe("$63.7K");
  });
  it("formatQuantity follows the display currency", () => {
    expect(formatQuantity(0.5, "CZK")).toBe("0,5");
    expect(formatQuantity(1234.5, "CZK")).toBe("1 234,5");
    expect(formatQuantity(0.5, "USD")).toBe("0.5");
    expect(formatQuantity(0.5)).toBe("0.5");
  });
  it("formatTableDate adds the year only outside the current year", () => {
    const now = new Date(2026, 9, 23);
    expect(formatTableDate("2026-10-15", now)).toBe("Oct 15");
    expect(formatTableDate("2025-09-29", now)).toBe("Sep 29, 2025");
    expect(formatTableDate("", now)).toBe("—");
    expect(formatTableDate("garbage", now)).toBe("—");
  });
  it("humanizeCode turns enum codes into sentence case", () => {
    expect(humanizeCode("INTEREST_ON_FREE_CASH")).toBe("Interest on free cash");
    expect(humanizeCode("STRONG_BUY")).toBe("Strong buy");
    expect(humanizeCode("deposit")).toBe("Deposit");
    expect(humanizeCode(null)).toBe("—");
  });
  it("pluralize picks the singular only for exactly one", () => {
    expect(pluralize(1, "share", "shares")).toBe("share");
    expect(pluralize(0.4, "share", "shares")).toBe("shares");
  });
});
```

- [ ] **Step 2: Run the tests and check that they fail**

Run: `cd frontend && npx vitest run src/lib/format.test.js`
Expected: FAIL. `formatTableDate`, `humanizeCode`, `pluralize` and `displayLocale` are not exported, and the CZK compact/quantity strings differ.

- [ ] **Step 3: Implement the helpers in `lib/format.js`**

- `displayLocale` reads `LOCALE_BY_CURRENCY`, falling back to `en-US`.
- `formatCompact` keeps en-US compact notation and, for CZK only, swaps the decimal point for a comma.
- `formatQuantity` passes `displayLocale(currency)` to `Intl.NumberFormat`.
- `formatTableDate` reuses the local-components parsing from `formatShortDate` and adds `year: "numeric"` when the year differs from `now`.

Existing callers keep their current output, because the new `currency` argument defaults to `"USD"`.

- [ ] **Step 4: Run the tests and check that they pass**

Run: `cd frontend && npx vitest run src/lib/format.test.js`
Expected: PASS, including the existing `formatQuantity`/`formatCompact` cases.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/format.js frontend/src/lib/format.test.js
git commit -m "feat(format): locale-aware compact/quantity, table dates, code labels"
```

### Task 2: Shared Clay primitives (A1, C4 Toggle, C6/C7 badges, U1)

**Files:**
- Create: `frontend/src/components/ui/Badge.jsx`, `frontend/src/components/ui/Modal.jsx`, `frontend/src/test/legacyClasses.js`
- Modify: `frontend/src/components/ui/Toggle.jsx`, `frontend/src/components/ui/index.js`, `frontend/src/components/BrokerPositionSnapshot.jsx`, `DESIGN.md` (§8)
- Test: `frontend/src/components/ui/primitives.test.jsx`, `frontend/src/components/BrokerPositionSnapshot.test.jsx`

**Interfaces:**
- Consumes: `formatQuantity`, `pluralize`, `formatMoney`, `formatTableDate` (Task 1), and `useFocusTrap({ active, onEscape, initialFocusRef, restoreFocusRef })` from `hooks/useFocusTrap.js`.
- Produces:
  - `<Badge tone="gain|loss|warn|neutral|brand" size="sm|md" title?>`: a pill with `data-tone={tone}`, a `color-mix` 16% tint of the tone token and text in the tone token, 12px semibold. Warn = `var(--chart-3)`, neutral = `var(--chart-8)`.
  - `<Modal open onClose titleId initialFocusRef? className?>`: an overlay plus a `.card` panel with `role="dialog"`, `aria-modal="true"`, `aria-labelledby={titleId}`. Focus is trapped via `useFocusTrap`, and `onClose` runs on Escape or a backdrop click. With reduced motion there is no transform transition.
  - `legacyColorClassesIn(url: URL) -> Promise<string[]>`: reads the source file and returns every match of `/\b(?:bg|text|border|ring|fill|stroke|from|via|to)-(?:white|(?:gray|slate|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose)-\d{2,3})(?:\/\d+)?\b|\b(?:bg|text|border)-\[#[0-9a-fA-F]{3,8}\]/g`.
  - `Toggle`: off track `var(--bg-subtle)` with `--clay-inset-sm`, knob `bg-surface-card-elevated` with `--clay-raise-sm`. The on state is unchanged (`activeClassName`, default `bg-brand`).
  - `<BrokerPositionSnapshot query variant="summary|list" limit=5>`:
    - `summary` renders one line, "Trading 212 snapshot · {n} positions · {total} · updated {formatTableDate}", plus a stale `Badge tone="warn"` and a "Show positions" disclosure that expands the list.
    - `list` keeps today's behavior.
    - Quantity text: `${formatQuantity(q, currency)} ${pluralize(q, "share", "shares")}`.

- [ ] **Step 1: Write the failing tests**
  - In `primitives.test.jsx`:
    - `Badge renders its tone`: `render(<Badge tone="warn">Stale</Badge>)`. Expect `getByText("Stale")` to have `data-tone="warn"`.
    - `Modal closes on Escape and restores focus`: an opener button toggles `<Modal titleId="t"><h2 id="t">Add</h2><input/></Modal>`. After the click, `getByRole("dialog", { name: "Add" })` contains `document.activeElement`. After `userEvent.keyboard("{Escape}")`, `queryByRole("dialog")` is null and the opener has focus.
    - `Toggle and Badge use no legacy color classes`: `legacyColorClassesIn(new URL("./Toggle.jsx", import.meta.url))` and the same for `./Badge.jsx` both resolve to `[]`.
  - In `BrokerPositionSnapshot.test.jsx`:
    - `summary variant shows one line and expands`: with 22 positions, `"22 positions"` is shown and `"AAOI"` is absent until "Show positions" is clicked.
    - `uses singular share for one`: quantity 1 renders `"1 share"`.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/components/ui/primitives.test.jsx src/components/BrokerPositionSnapshot.test.jsx`. Expected: FAIL (missing exports; `Toggle.jsx` contains `bg-slate-300`/`bg-white`).
- [ ] **Step 3: Implement the primitives above.** Export `Badge` and `Modal` from `ui/index.js`. Add a "Badges and dialogs" paragraph to DESIGN.md §8 naming the five tones and the Modal contract.
- [ ] **Step 4: Run** `cd frontend && npm test`. Expected: the whole suite passes (`Toggle` is shared).
- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui frontend/src/test/legacyClasses.js frontend/src/components/BrokerPositionSnapshot*.jsx DESIGN.md
git commit -m "feat(ui): Clay Badge, accessible Modal, clay Toggle, compact snapshot"
```

---

### Task 3: Dashboard and heatmap (O1, C8, U1, F3)

**Files:**
- Modify: `frontend/src/components/Heatmap.jsx`, `frontend/src/pages/Dashboard.jsx`, `frontend/src/components/dashboard/InsiderBuysCard.jsx`
- Test: `frontend/src/components/Heatmap.test.jsx` (create), `frontend/src/pages/Dashboard.async.test.jsx`

**Interfaces:**
- Consumes: `SegmentedControl`, `BrokerPositionSnapshot variant="summary"`, `formatTableDate`, `formatCompact`, `legacyColorClassesIn`.
- Produces: `export function tileLabels(w: number, h: number) -> { ticker: boolean, change: boolean, weight: boolean }`. `export function squarify(items, W, H)` is now exported for tests.

- [ ] **Step 1: Write the failing tests** in `Heatmap.test.jsx`:
  - `tileLabels hides labels that cannot fit at 12px`:
    - `tileLabels(30, 18)` → all false
    - `tileLabels(40, 24)` → `{ ticker: true, change: false, weight: false }`
    - `tileLabels(60, 40)` → ticker and change true, weight false
    - `tileLabels(80, 56)` → all true
  - `squarify keeps every tile inside the box`: weights `[8,8,7,6,6,5,5,4,4,4,4,4,4,3,3,3,3,3,2,2,2,1.9]` in 600×400 give `x + w ≤ 600.5` and `y + h ≤ 400.5` for every tile.
  - `uses no legacy color classes` for `./Heatmap.jsx`.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/components/Heatmap.test.jsx`. Expected: FAIL (`tileLabels` is not exported).
- [ ] **Step 3: Heatmap changes**
  - Tile text is fixed at 12px (ticker, change and weight lines) and each line is shown per `tileLabels`. Thresholds: ticker needs w ≥ 36 and h ≥ 20; change needs h ≥ 36; weight needs h ≥ 52.
  - Remove the inner `<h2>Heatmap</h2>`; the dashboard card title already names it.
  - Replace the period buttons with `<SegmentedControl size="sm" options={PERIODS.map((p) => ({ value: p.key, label: p.label }))} value={period} onChange={setPeriod} aria-label="Heatmap period" />`.
  - Make the tile container `flex-1 min-h-0` and drop the inline `minHeight: "400px"`, so the ResizeObserver lays tiles out in the height the card really gives. This removes the clipped bottom row.
  - Tile corners: `rounded-[10px]`.
- [ ] **Step 4: Dashboard changes**
  - Render `<BrokerPositionSnapshot variant="summary">` after the hero, KPI row and attention signals instead of before them.
  - `InsiderBuysCard` dates go through `formatTableDate`, values through `formatCompact(Math.abs(b.value), b.currency)`, so `$3,483,800.00` becomes `$3.5M`.
  - Add `renders net worth before the broker snapshot` to `Dashboard.async.test.jsx`: the "Net worth" label precedes the "Trading 212 snapshot" text in document order (`compareDocumentPosition`).
- [ ] **Step 5: Run** `cd frontend && npm test && npm run build && npm run test:cloud && npm run build:cloud`. Expected: all PASS.
- [ ] **Step 6: Visual check** on `npx vite --port 5203 --strictPort` in Clay at 1440 and 375 wide. Expected: no clipped heatmap row, no tile text under 12px.
- [ ] **Step 7: Commit** `git commit -m "fix(dashboard): heatmap fits its card at 12px, snapshot below hero"`

### Task 4: Allocation (O5, U3, U1)

**Files:**
- Modify: `frontend/src/pages/Allocation.jsx`, `frontend/src/components/AllocationTargets.jsx`
- Test: `frontend/src/pages/Allocation.decisions.test.jsx`, `frontend/src/components/AllocationTargets.test.jsx`

**Interfaces:**
- Consumes: `BrokerPositionSnapshot variant="summary"`, `formatPercent`, `legacyColorClassesIn`.

- [ ] **Step 1: Write the failing tests**
  - `collapses rows without a target into one summary row` (AllocationTargets): with 22 rows of which 1 has a target, the table shows the targeted row plus a button `"21 holdings without a target"`. Clicking it reveals the 21 rows.
  - `All Holdings lists only active positions in the Active view` (Allocation): no row contains the `SOLD` marker while "Active positions" is selected.
  - `legend percentages share one precision`: weights 6 and 8.12 render as `"6.00%"` and `"8.12%"`.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/pages/Allocation.decisions.test.jsx src/components/AllocationTargets.test.jsx`. Expected: FAIL.
- [ ] **Step 3: Implement**
  - The snapshot uses `variant="summary"` (drop `limit={20}`).
  - The legend percent column becomes `w-12` with `formatPercent(x, { sign: false, digits: 2 })`.
  - All Holdings renders sold rows only when "Sold positions" is active. While `scrollWidth > clientWidth`, the table wrapper gets a right-edge fade (`mask-image: linear-gradient(to right, black 92%, transparent)`); the ticker column is sticky.
  - AllocationTargets groups untargeted rows behind the disclosure button.
- [ ] **Step 4: Run** `cd frontend && npm test && npm run build`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "fix(allocation): compact snapshot, grouped untargeted rows, scroll cue"`

### Task 5: Transactions (A1, A2, C6, F2, F3, U2, O8)

**Files:**
- Modify: `frontend/src/pages/Transactions.jsx`
- Test: `frontend/src/pages/Transactions.page.test.jsx`

**Interfaces:**
- Consumes: `Modal`, `Badge`, `SegmentedControl`, `formatQuantity`, `formatTableDate`, `legacyColorClassesIn`.

- [ ] **Step 1: Write the failing tests**
  - `Add Transaction opens as an accessible dialog`: clicking "Add" gives `getByRole("dialog", { name: "Add Transaction" })` with the Ticker input focused; Escape closes it.
  - `placeholders are marked as examples`: Ticker `"e.g. AAPL"`, Shares `"e.g. 10"`, Price `"e.g. 185.50"`.
  - `filters by transaction type`: choosing "Dividend" in the `All | Buy | Sell | Dividend` control leaves only dividend rows.
  - `type renders as a badge`: "Buy" has `data-tone="brand"`, "Sell" `data-tone="neutral"`, "Dividend" `data-tone="gain"`.
  - `uses no legacy color classes` for `./Transactions.jsx`.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/pages/Transactions.page.test.jsx`. Expected: FAIL.
- [ ] **Step 3: Implement**
  - The add form renders inside `<Modal>`, with `initialFocusRef` on Ticker.
  - Placeholders as above.
  - The type filter works client-side over the fetched page.
  - Dates use `formatTableDate`, shares use `formatQuantity(t.shares, currency)`.
  - Delete hover is `hover:text-loss`.
  - Below `md`, a `<ul>` of cards replaces the table (`md:hidden` / `hidden md:block`). Each card shows ticker + type badge, then date · shares × price, then the total right-aligned. Delete and note actions keep 44px targets.
- [ ] **Step 4: Run** `cd frontend && npm test && npm run build`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "fix(transactions): accessible add dialog, type filter, badges, mobile cards"`

### Task 6: Cash (O4, F3, F4, C6, O8)

**Files:**
- Modify: `frontend/src/pages/Cash.jsx`, `frontend/src/components/CashBalanceChart.jsx`
- Test: `frontend/src/pages/Cash.test.jsx`

**Interfaces:**
- Consumes: `Pagination({ offset, limit, total, onOffsetChange, onLimitChange, ariaLabel })`, `humanizeCode`, `formatTableDate`, `legacyColorClassesIn`.

- [ ] **Step 1: Write the failing tests**
  - `shows pagination only when rows exceed one page`: 0 rows show the empty state; 25 rows show no pagination nav; 26 rows show the nav and 25 rows on page 1.
  - `ledger has a header row and separate amount and note cells`: header columns `Date | Type | Amount | Note`; a note `"T212 INTEREST_ON_FREE_CASH"` renders as `"T212 Interest on free cash"` in its own cell.
  - `cash type options are humanized`: the select shows `"Deposit"` (value stays `deposit`).
  - `uses no legacy color classes` for `./Cash.jsx`.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/pages/Cash.test.jsx`. Expected: FAIL.
- [ ] **Step 3: Implement**
  - Client-side pagination of `rows.data`, page size 25.
  - A ledger `<thead>` and a `pl-6` note column. Dates use `formatTableDate`.
  - Notes keep a leading `T212 ` prefix and `humanizeCode` the remainder when it matches `/^[A-Z_]+$/`.
  - Delete hover is `hover:text-loss`, with a 44px target below `md`. On mobile each ledger entry is a stacked row (date + type, amount on the right, note below).
  - `CashBalanceChart` XAxis gets `interval="preserveStartEnd"` and `minTickGap={24}`.
- [ ] **Step 4: Run** `cd frontend && npm test && npm run build`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "fix(cash): paginated ledger with headers, readable notes, mobile rows"`

### Task 7: Dividends and Tax Report (F2, F3, F5, D1, C7, U7, O8)

**Files:**
- Modify: `frontend/src/pages/Dividends.jsx`, `frontend/src/pages/TaxReport.jsx`
- Test: `frontend/src/pages/Dividends.trust.test.jsx`, `frontend/src/pages/TaxReport.precision.test.jsx`

**Interfaces:**
- Consumes: `Badge`, `formatQuantity`, `formatTableDate`, `formatMoney`, `legacyColorClassesIn`.
- Produces: `export function czRowStatus(gain, yearsByTaxYear) -> "exempt_time" | "exempt_value" | "taxable"` in `TaxReport.jsx`. `yearsByTaxYear` maps `tax_year` to `{ value_test_passed: boolean }`, and the row's tax year is the year of `gain.sell_date`.

- [ ] **Step 1: Write the failing tests**
  - `marks rows exempt when the sell year passed the value test`: `czRowStatus({ cz_exempt_time_test: false, sell_date: "2026-03-10" }, { 2026: { value_test_passed: true } })` → `"exempt_value"`.
  - `keeps Taxable when the sell year failed the value test`: the same row with `false` → `"taxable"`.
  - `time test wins`: `cz_exempt_time_test: true` → `"exempt_time"` whatever the year says.
  - `row badges read Exempt · 3y, Exempt · value test, Taxable`: rendered with tones gain, gain and warn.
  - `estimated annual income is shown in the display currency` (Dividends): display currency CZK, rate 21.71 and USD rows summing to 18.03 give a card showing `formatMoney(18.03 * 21.71, "CZK")` and no `"USD"` label.
  - `uses no legacy color classes` for both page files.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/pages/TaxReport.precision.test.jsx src/pages/Dividends.trust.test.jsx`. Expected: FAIL.
- [ ] **Step 3: Implement**
  - TaxReport:
    - Row badges come from `czRowStatus`.
    - The Term badge becomes `Badge` (long = brand, short = neutral).
    - The incomplete-FX warning uses warn-tone tokens instead of `text-amber-300`/`bg-amber-400/5`.
    - Dates use `formatTableDate`, shares use `formatQuantity(g.shares, "CZK")`.
    - The §4 year cards sit in `grid gap-6 sm:grid-cols-2 xl:grid-cols-3`, so one card fills the row's start and several fill the width.
    - Below `md`, realized gains render as a card list.
  - Dividends:
    - USD estimate totals are converted with the existing `usdRate` and merged into the display currency; other currencies stay separate tiles.
    - Shares use `formatQuantity(row.shares, currency)`, dates use `formatTableDate`.
- [ ] **Step 4: Run** `cd frontend && npm test && npm run build`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "fix(tax,dividends): honest CZ badges, display-currency income, unified formats"`

### Task 8: Analytics (F1, C2, D2, D3, O7)

**Files:**
- Modify: `frontend/src/pages/Analytics.jsx`, `frontend/src/lib/correlationPairs.js`
- Test: `frontend/src/lib/correlationPairs.test.js`, `frontend/src/pages/Analytics.decisions.test.jsx`

**Interfaces:**
- Consumes: `formatMoney`, `Badge`, `NEUTRAL_COLOR`, `legacyColorClassesIn`.
- Produces: `export function correlationColor(v: number) -> string` in `lib/correlationPairs.js`. For v ≥ 0 it returns `color-mix(in srgb, var(--chart-2) P%, var(--surface-card))`; for v < 0 the same with `var(--chart-4)`. P = round(15 + 55·|v|). The caller paints the diagonal with `var(--bg-subtle)`.

- [ ] **Step 1: Write the failing tests**
  - `correlationColor scales copper with positive correlation`: `correlationColor(0.63)` contains `var(--chart-2) 50%`; `correlationColor(-0.2)` contains `var(--chart-4) 26%`.
  - `Analytics money uses the display-currency formatter`: currency CZK, rate 21.71 and a net profit of 24.25 render `formatMoney(24.25 * 21.71, "CZK")`.
  - `uses no legacy color classes` for `./Analytics.jsx`.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/lib/correlationPairs.test.js src/pages/Analytics.decisions.test.jsx`. Expected: FAIL.
- [ ] **Step 3: Implement**
  - The local `fmt` becomes `(n) => formatMoney(convert(n), currency)`.
  - Matrix cells use `correlationColor` with `rounded-[10px]`. Ticker chips become `Badge tone="neutral"` (selected = `brand`).
  - "Strongest correlations" values render in `text-ink` with a Copper dot instead of `text-loss`.
  - Risk badges (Poor/Moderate/Active) become `Badge` tones loss, warn and brand.
  - The benchmark legend dot is `NEUTRAL_COLOR`.
  - The Net profit sub-line gets `truncate` with a `title` of the full text.
  - D2: an info icon on Net profit and Simple ROI. Its `title` states which inputs each figure includes, written from the fields this page reads from the analytics API and the fields `PortfolioHero` reads for "Total profit". Write the sentence after reading both definitions in the code, not before.
- [ ] **Step 4: Run** `cd frontend && npm test && npm run build`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "fix(analytics): one money format, organic correlation scale, Clay badges"`

### Task 9: Import (C3)

**Files:**
- Modify: `frontend/src/pages/Import.jsx`
- Test: `frontend/src/pages/Import.test.jsx`

- [ ] **Step 1: Write the failing tests**
  - `uses no legacy color classes` for `./Import.jsx`.
  - `the stepper marks the current step`: the step item "Select source" has `aria-current="step"`.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/pages/Import.test.jsx`. Expected: FAIL.
- [ ] **Step 3: Implement**
  - The stepper becomes pill steps in an inset trough (`--clay-inset-sm`, `rounded-full` items). The current step is raised with `--clay-raise-sm` and brand text.
  - Broker chips become `Badge` (Trading 212 = brand, the rest neutral).
  - The dropzone hover uses `hover:border-brand`.
  - The page container widens to `max-w-5xl`, and at `xl` the "How to export" accordion sits beside the dropzone (`xl:grid-cols-2`).
- [ ] **Step 4: Run** `cd frontend && npm test && npm run build && npm run test:cloud && npm run build:cloud`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "fix(import): Clay stepper and broker badges"`

### Task 10: Settings (C4, U6, U1, F4)

**Files:**
- Modify: `frontend/src/pages/Settings.jsx`, `frontend/src/components/SyncScheduleSettings.jsx`, `frontend/src/components/DiscordSettings.jsx`, `frontend/src/components/DataPrivacySettings.jsx`, `frontend/src/components/settings/IBKRConnectionCard.jsx`, `frontend/src/components/settings/EtoroConnectionCard.jsx`, `frontend/src/components/settings/PreferencesSettings.jsx`
- Test: `frontend/src/pages/Settings.sections.test.jsx`, `frontend/src/components/SyncScheduleSettings.test.jsx`, `frontend/src/components/DiscordSettings.test.jsx`, `frontend/src/components/DataPrivacySettings.test.jsx`

**Interfaces:**
- Consumes: `Badge`, `SegmentedControl`, `Toggle`, `BrokerPositionSnapshot variant="summary"`, `legacyColorClassesIn`.

- [ ] **Step 1: Write the failing tests**
  - `sync schedule mode is a segmented control`: options "Daily at" and "Every N hours" render through `SegmentedControl` (`aria-label="Sync mode"`), and no `input[type="radio"]` exists.
  - `eToro card is hidden when unavailable`: with the mocked response that today produces "The eToro connection is not available on this server yet.", no "eToro" heading renders.
  - `Clay hides appearance and accent palette`: with theme style `clay`, the "Appearance" and "Accent palette" groups are absent and "Clay uses its own light palette." is shown.
  - `privacy copy uses em dashes`: the text contains `"working — sign-in"` and no `" -- "`.
  - `uses no legacy color classes` for each of the seven modified files.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/pages/Settings.sections.test.jsx src/components/SyncScheduleSettings.test.jsx src/components/DiscordSettings.test.jsx src/components/DataPrivacySettings.test.jsx`. Expected: FAIL.
- [ ] **Step 3: Implement**
  - Discord: buttons become `.btn-primary`, the status chip becomes `Badge`, and the toggle uses the default `activeClassName`. Only the logo SVG keeps its `#5865F2` fill (an attribute, not a class).
  - Connect, Disconnect and Clear portfolio become `.btn-primary` / `.btn-ghost` pills; destructive actions use `.btn-ghost text-loss`.
  - Accent palette chips become pills.
  - The inner "Analytics preferences" block becomes an inset well instead of a second raised card.
  - The connections tab uses `BrokerPositionSnapshot variant="summary"`.
  - "Connected" / "Not connected" become `Badge` gain / neutral.
- [ ] **Step 4: Run** `cd frontend && npm test && npm run build && npm run test:cloud && npm run build:cloud`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "fix(settings): Clay controls, hide unavailable options, compact snapshot"`

### Task 11: Watchlists, Search, Screener, portfolio switcher (C5, U4, O6)

**Files:**
- Modify: `frontend/src/pages/Watchlists.jsx`, `frontend/src/pages/Search.jsx`, `frontend/src/pages/Screener.jsx`, `frontend/src/components/PortfolioSwitcher.jsx`
- Test: `frontend/src/pages/Watchlists.flows.test.jsx`, `frontend/src/pages/ResearchPages.async.test.jsx`, `frontend/src/pages/Screener.test.jsx`, `frontend/src/components/PortfolioSwitcher.test.jsx`

**Interfaces:**
- Consumes: `SectionHeader`, `Badge`, `legacyColorClassesIn`.

- [ ] **Step 1: Write the failing tests**
  - `price alerts render after the watchlists`: the "Price Alerts" heading follows the watchlist section in document order.
  - `search shows your holdings before typing`: with an empty query, a "Your holdings" list of up to 8 tickers links to `/stock/:ticker`.
  - `screener filters are open on first visit`: the "Universe" select is visible without clicking Filters.
  - `switcher shows the default badge on its own line`: the portfolio name and `"Default · 759 transactions"` are separate elements, and the name element is not inside the same flex row as the badge.
  - `uses no legacy color classes` for the four files.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/pages/Watchlists.flows.test.jsx src/pages/ResearchPages.async.test.jsx src/pages/Screener.test.jsx src/components/PortfolioSwitcher.test.jsx`. Expected: FAIL.
- [ ] **Step 3: Implement**
  - Alert inputs use `.input` and buttons `.btn-primary`. The alerts header uses `SectionHeader`, and the alerts card renders after the watchlists.
  - Search holdings reuse the portfolio-holdings query the Allocation page already uses (same query key, so no new request).
  - Screener `showFilters` starts as `true`.
  - Switcher rows: the name on line 1, "Default · N transactions" as `text-xs text-muted` on line 2.
- [ ] **Step 4: Run** `cd frontend && npm test && npm run build && npm run test:cloud && npm run build:cloud`. Expected: PASS (the cloud build must still exclude Screener).
- [ ] **Step 5: Commit** `git commit -m "fix(research): Clay alerts, useful empty states, readable switcher"`

---

### Task 12: Stock financials charts (O2, C1 part 1)

**Files:**
- Modify: `frontend/src/components/StockDetail.jsx` (`financialPeriodAxisLayout`, `ChangeTick`, `MetricBarChart`, `MergedMetricBarChart`, `EarningsRecapSection`), `frontend/src/components/stock/StockFinancialsTab.jsx`
- Test: `frontend/src/components/StockDetail.financialGrowth.test.jsx`

**Interfaces:**
- Consumes: `CATEGORICAL`, `LOSS_COLOR`, `SegmentedControl`, `Badge`.
- Produces: `financialPeriodAxisLayout(labels, containerWidth, isQuarterly) -> { fontSize: 12, angle: 0, interval: number, short: boolean }`. It never returns a font under 12. When labels do not fit horizontally, it first sets `short: true` (years as `'17`, quarters as `Q1'24`), then raises `interval` (show every (interval+1)-th label).

- [ ] **Step 1: Replace the two existing `financialPeriodAxisLayout` tests with:**
  - `never goes below 12px`: 10 annual labels at 300px give `fontSize === 12`, `angle === 0` and `short === true`.
  - `thins labels when even short labels collide`: 40 quarterly labels at 300px give `interval ≥ 1`.
  - `keeps every label when they fit`: 10 labels at 1200px give `interval === 0` and `short === false`.
  - `bars use theme series, not hex fills`: rendering `MetricBarChart` with the file's existing fixture gives at least one `.recharts-bar-rectangle path`, and no `fill` attribute starts with `#`.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/components/StockDetail.financialGrowth.test.jsx`. Expected: FAIL.
- [ ] **Step 3: Implement**
  - The new axis layout.
  - `ChangeTick` drops the YoY line whenever it would render under 12px; the YoY value stays in the bar tooltip.
  - Bar fills: actual `CATEGORICAL[0]`, estimate `CATEGORICAL[5]`, TTM `CATEGORICAL[3]`, negative `LOSS_COLOR`, all with `radius={[7, 7, 0, 0]}`.
  - The Annual/Quarterly toggle becomes `SegmentedControl`.
  - EPS-surprise bars are rounded. (The BEAT/MISS chip moves to Task 14.)
- [ ] **Step 4: Run** `cd frontend && npm test && npm run build`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "fix(stock): financial charts at 12px, organic rounded bars"`

### Task 13: Stock valuation (C1 part 2, O3, F4)

**Files:**
- Modify: `frontend/src/components/StockDetail.jsx` (`RatingPill`, `AnalystBar`, `DcfSensitivityTable`, `ValuationSection`, `AnalystForecastCone`, `RightEdgePills`, `TargetRangeBar`), `frontend/src/components/stock/StockValuationTab.jsx`
- Test: `frontend/src/components/StockDetail.valuation.test.jsx` (create)

**Interfaces:**
- Consumes: `Badge`, `humanizeCode`, `GAIN_COLOR`, `LOSS_COLOR`.
- Produces: `export function layoutEdgePills(items: { key, y }[], { top: number, bottom: number, minGap: number }) -> { key, y }[]`. It keeps the input order by y and spreads neighbours until they are ≥ `minGap` px apart, all within `[top + minGap/2, bottom − minGap/2]`.

- [ ] **Step 1: Write the failing tests**
  - `layoutEdgePills separates overlapping pills`: inputs y = 100, 104, 108 (minGap 22, top 0, bottom 300) come out ≥ 22 apart in the same order.
  - `layoutEdgePills keeps pills inside the plot`: an input at y = 295 (bottom 300, minGap 22) comes out ≤ 289.
  - `analyst rating label is humanized`: the rating shows "Strong buy", not "STRONG_BUY".
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/components/StockDetail.valuation.test.jsx`. Expected: FAIL.
- [ ] **Step 3: Implement**
  - `RightEdgePills` positions through `layoutEdgePills` with minGap 22, and the cone chart reserves `margin.right = 104` so the pills never clip.
  - Cone fills are `color-mix` 18% of `GAIN_COLOR` (upside) and `LOSS_COLOR` (downside).
  - Analyst bars: strong buy/buy `GAIN_COLOR`, hold `var(--chart-3)`, sell/strong sell `LOSS_COLOR`, as `style={{ backgroundColor }}` on a `rounded-full` bar inside an inset track.
  - DCF cells use `color-mix` of the gain/loss tokens by distance from the current price.
  - `RatingPill` becomes `Badge`.
  - Remove the duplicated About block from `StockValuationTab.jsx`; it stays on Overview.
- [ ] **Step 4: Run** `cd frontend && npm test && npm run build`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "fix(stock): non-overlapping target pills, token-colored valuation"`

### Task 14: Stock overview, ownership, insiders, filings (C1 part 3, F3, U5)

**Files:**
- Modify: `frontend/src/components/StockDetail.jsx` (`Chip`, `TypeFilterChips`, `OwnershipSection`, `ShibuiFilingsSection`, `ShibuiInsiderActivitySection`, `InsiderTransactionsSection`, `InsiderVolumeChart`), `frontend/src/components/stock/StockOverviewTab.jsx`, `frontend/src/components/stock/StockFilingsTab.jsx`
- Test: `frontend/src/components/StockDetail.insiderPagination.test.jsx`, `frontend/src/components/stock/StockOverviewTab.test.jsx`, `frontend/src/components/StockDetail.clay.test.jsx` (create)

**Interfaces:**
- Consumes: `Badge`, `KpiBox`, `formatTableDate`, `legacyColorClassesIn`.

- [ ] **Step 1: Write the failing tests**
  - `About is clamped with a toggle`: the description has `line-clamp-3`, and a "Show more" button removes it.
  - `insider rows without a price show a dash`: a type OTHER row with price 0 shows "—" in Price and Value.
  - `insider dates use table format`: `"2026-10-13"` renders as `formatTableDate("2026-10-13")`.
  - `filings are sorted newest first and explain form types`: rows are in descending date order. Titles: `10-K` = "Annual report", `10-Q` = "Quarterly report", `8-K` = "Current report", `4` = "Insider transaction".
  - `StockDetail.jsx uses no legacy color classes`: `legacyColorClassesIn(new URL("./StockDetail.jsx", import.meta.url))` → `[]`. This closes C1 for the whole file, including leftovers from Tasks 12–13.
- [ ] **Step 2: Run** `cd frontend && npx vitest run src/components/StockDetail.insiderPagination.test.jsx src/components/stock/StockOverviewTab.test.jsx src/components/StockDetail.clay.test.jsx`. Expected: FAIL.
- [ ] **Step 3: Implement**
  - `Chip` tones become `Badge`; `TypeFilterChips` become pill toggles (active = raised with brand text).
  - The earnings BEAT/MISS chip in `EarningsRecapSection` becomes `Badge` gain/loss (moved here from Task 12).
  - Drop the full-row red tint on insider sells; the badge carries the meaning.
  - Ownership and insider panels become `.card`, with nested KPI tiles as `KpiBox` inset wells.
  - Every remaining `bg-*-500` / `text-*-700` class becomes a token.
- [ ] **Step 4: Run** `cd frontend && npm test && npm run build`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "fix(stock): Clay ownership/insider/filings, clamped About"`

---

### Task 15: Re-integrate and re-audit

**Files:**
- Modify: `docs/superpowers/specs/2026-10-23-clay-ui-audit.md` (append a "Result" section), `DESIGN.md` (only if a wave-2 PR asked for a rule)

- [ ] **Step 1: Merge** all task branches into one integration branch and resolve conflicts locally. `git diff --stat main` lists only files named in Tasks 1–14.
- [ ] **Step 2: Run** `cd frontend && npm test && npm run test:cloud && npm run build && npm run build:cloud`. Expected: all PASS.
- [ ] **Step 3: Legacy sweep**: `grep -rEn "\b(bg|text|border)-(white|(gray|slate|zinc|red|green|emerald|amber|yellow|orange|blue|indigo|purple|rose|sky)-[0-9]{2,3})" frontend/src/pages frontend/src/components --include=*.jsx | grep -v "\.test\."`. Expected: no output, or only files outside the audit's scope, each listed in the Result section as a follow-up.
- [ ] **Step 4: Browser re-audit** in Clay at 1440×900 and 375×812 with the audit's in-page script on every page and stock tab. Expected: 0 text nodes under 12px, 0 page-level horizontal scroll, no clipped heatmap tile, no overlapping target pills. Then check Dashboard and Allocation in Premium, because `Badge`, `Modal` and `Toggle` are shared.
- [ ] **Step 5: Record** pass/fail per finding ID in the spec's "Result" section and commit: `git commit -m "docs: record Clay audit re-check"`

---

## Not in this plan

- **X1** (5-year average P/E vs current/sector P/E in `backend/routers/market.py`): a methodology decision for the owner, tracked separately.
- Classic dark mode, Screener scan results, Login/Onboarding: the audit did not cover them, so they need their own audit before anyone changes them.
