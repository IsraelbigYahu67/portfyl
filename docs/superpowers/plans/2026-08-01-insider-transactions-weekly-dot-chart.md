# Insider Transactions Weekly Dot Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "Insider Volume" monthly bar+line chart on the stock detail page with a weekly price-line chart where every insider buy/sell is a hoverable dot sitting on the line, matching the approved spec.

**Architecture:** Extract pure, testable bucketing/snapping logic into a new `frontend/src/lib/insiderWeekly.js` module (weekly price bucketing + transaction-to-week assignment + dot-jitter math). Rewrite `InsiderVolumeChart` in `frontend/src/components/StockDetail.jsx` to consume that module and render a Recharts `ComposedChart` (`Line` + two `Scatter` layers) with a custom dot `shape` that drives hover-fade styling and a manually-positioned info-box overlay (no reliance on Recharts' built-in `<Tooltip>`, which would be ambiguous to trigger reliably on a numeric axis shared between a `Line` and two `Scatter` series).

**Tech Stack:** React 18, Recharts 2.14, Vitest + `@testing-library` (existing frontend test setup), no backend changes.

## Global Constraints

- No backend/API changes — everything needed is already in `data.insider_transactions` and the existing `fetchHistory(ticker, "1y")` daily price series. (Spec: "No backend changes are required.")
- Lookback window stays fixed at 1 year / ~52 weeks — no new configurability. (Spec: "Out of scope: Configurable lookback window.")
- Opposite-side dots fade to **near-zero opacity** on hover (not `display:none`) while the hovered side's dots are fully unaffected. (Spec: "Interaction.")
- Info box shows **exactly** four fields — name, date, shares, $ amount — no extra fields (no side pill, no price/share, no P&L). (Spec: "Interaction.")
- `InsiderTransactionsSection` (the list/table below the chart) is untouched. (Spec: "Summary.")
- Follow the repo's existing chart styling tokens: `GAIN_COLOR`/`LOSS_COLOR`/`CATEGORICAL`/`AXIS_TICK`/`GRID_STROKE` from `frontend/src/lib/chartTheme.js`, and the app's existing custom-tooltip-card styling (`bg-surface-card-elevated border border-hairline rounded-lg px-3 py-2 text-xs shadow-lg space-y-0.5`, already used in this same file for `AnalystForecastCone` and the old `InsiderVolumeChart` tooltip).
- Run `npm run build` and `npm test` from `frontend/` for this change, per CLAUDE.md.

---

### Task 1: Weekly bucketing + transaction-snapping helpers

**Files:**
- Create: `frontend/src/lib/insiderWeekly.js`
- Create: `frontend/src/lib/insiderWeekly.test.js`

**Interfaces:**
- Produces (consumed by Task 2):
  - `buildWeeklyBuckets(dailySeries, weeks = 52) -> Array<{ weekKey: string, weekTs: number, close: number | null }>`
    - `dailySeries`: array of `{ date: string /* "YYYY-MM-DD" */, close: number }` (matches `fetchHistory(ticker, period).data`).
    - Returns `weeks` buckets in ascending chronological order, spaced exactly 7 days apart, covering the trailing `weeks * 7` days up to the last date present in `dailySeries`. `weekKey` is the bucket's start date as an ISO `"YYYY-MM-DD"` string (UTC). A bucket's `close` is the last daily close falling inside its 7-day window, or `null` if no daily point falls in that window.
  - `assignTransactionsToWeeks(transactions, buckets) -> Array<{ key: string, side: "buy" | "sell", weekKey: string, weekTs: number, close: number, insider: string | null, date: string, shares: number | null, value: number | null }>`
    - `transactions`: array of raw insider-transaction objects as returned by the backend (`{ insider, date, side, shares, value, ... }`).
    - `buckets`: the array returned by `buildWeeklyBuckets`.
    - Drops transactions whose `side` is not `"buy"`/`"sell"`, whose `date` doesn't parse, whose date falls before the first bucket or after the last, or whose matching bucket has `close: null`. `shares`/`value` are returned as absolute values (matches the existing display convention elsewhere in this file).
  - `jitterOffsetPx(index) -> number`
    - Pure pixel-offset formula for spreading dots that land in the same week+side group: `0 -> 0, 1 -> 6, 2 -> -6, 3 -> 12, 4 -> -12, ...` (alternating outward from the true point).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/lib/insiderWeekly.test.js`:

```js
import { buildWeeklyBuckets, assignTransactionsToWeeks, jitterOffsetPx } from "./insiderWeekly";

const DAY = 24 * 60 * 60 * 1000;
const WEEK = 7 * DAY;

describe("buildWeeklyBuckets", () => {
  it("returns an empty array for empty/missing input", () => {
    expect(buildWeeklyBuckets([])).toEqual([]);
    expect(buildWeeklyBuckets(null)).toEqual([]);
  });

  it("buckets daily closes into 7-day windows, keeping the last close per window", () => {
    const series = [
      { date: "2026-01-01", close: 100 },
      { date: "2026-01-03", close: 105 },
      { date: "2026-01-08", close: 110 },
    ];
    const buckets = buildWeeklyBuckets(series, 2);
    expect(buckets).toHaveLength(2);
    expect(buckets[0]).toEqual({ weekKey: "2026-01-01", weekTs: Date.UTC(2026, 0, 1), close: 105 });
    expect(buckets[1]).toEqual({ weekKey: "2026-01-08", weekTs: Date.UTC(2026, 0, 8), close: 110 });
  });

  it("leaves close: null for weeks with no daily data", () => {
    const series = [
      { date: "2026-01-01", close: 100 },
      { date: "2026-01-15", close: 120 },
    ];
    const buckets = buildWeeklyBuckets(series, 3);
    expect(buckets.map((b) => b.close)).toEqual([100, null, 120]);
  });

  it("spaces bucket timestamps exactly one week apart", () => {
    const series = [{ date: "2026-01-01", close: 100 }];
    const buckets = buildWeeklyBuckets(series, 4);
    expect(buckets.map((b) => b.weekTs)).toEqual([
      Date.UTC(2026, 0, 1) - 3 * WEEK,
      Date.UTC(2026, 0, 1) - 2 * WEEK,
      Date.UTC(2026, 0, 1) - 1 * WEEK,
      Date.UTC(2026, 0, 1),
    ]);
  });
});

describe("assignTransactionsToWeeks", () => {
  const series = [
    { date: "2026-01-01", close: 100 },
    { date: "2026-01-15", close: 120 },
  ];
  const buckets = buildWeeklyBuckets(series, 3); // weeks: Jan01 (100), Jan08 (null), Jan15 (120)

  it("returns an empty array when there are no buckets", () => {
    expect(assignTransactionsToWeeks([{ date: "2026-01-01", side: "buy" }], [])).toEqual([]);
  });

  it("snaps a transaction to the week bucket containing its date", () => {
    const out = assignTransactionsToWeeks(
      [{ insider: "Alice", date: "2026-01-02", side: "buy", shares: -100, value: 5000 }],
      buckets,
    );
    expect(out).toEqual([
      {
        key: expect.any(String),
        side: "buy",
        weekKey: "2026-01-01",
        weekTs: Date.UTC(2026, 0, 1),
        close: 100,
        insider: "Alice",
        date: "2026-01-02",
        shares: 100,
        value: 5000,
      },
    ]);
  });

  it("drops transactions landing in an empty (null close) bucket", () => {
    const out = assignTransactionsToWeeks(
      [{ insider: "Bob", date: "2026-01-10", side: "sell", shares: 50, value: 2500 }],
      buckets,
    );
    expect(out).toEqual([]);
  });

  it("drops transactions before the bucket range", () => {
    const out = assignTransactionsToWeeks(
      [{ insider: "Carol", date: "2025-12-01", side: "buy", shares: 10, value: 100 }],
      buckets,
    );
    expect(out).toEqual([]);
  });

  it("drops non buy/sell sides", () => {
    const out = assignTransactionsToWeeks(
      [{ insider: "Dave", date: "2026-01-16", side: "other", shares: 5, value: 50 }],
      buckets,
    );
    expect(out).toEqual([]);
  });

  it("keeps one entry per transaction with unique keys when several share a week+side", () => {
    const out = assignTransactionsToWeeks(
      [
        { insider: "Alice", date: "2026-01-02", side: "buy", shares: 100, value: 5000 },
        { insider: "Eve", date: "2026-01-05", side: "buy", shares: 200, value: 9000 },
      ],
      buckets,
    );
    expect(out).toHaveLength(2);
    expect(out[0].key).not.toEqual(out[1].key);
    expect(out.every((d) => d.weekKey === "2026-01-01")).toBe(true);
  });
});

describe("jitterOffsetPx", () => {
  it("alternates outward from the true point", () => {
    expect([0, 1, 2, 3, 4].map(jitterOffsetPx)).toEqual([0, 6, -6, 12, -12]);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `frontend/`): `npm test -- insiderWeekly`
Expected: FAIL — `frontend/src/lib/insiderWeekly.js` does not exist yet.

- [ ] **Step 3: Write the implementation**

Create `frontend/src/lib/insiderWeekly.js`:

```js
// Weekly bucketing + insider-transaction-to-week snapping for the stock
// detail page's insider dot chart. Kept as pure functions so the bucket/
// snap math is unit-testable without rendering Recharts.

const DAY_MS = 24 * 60 * 60 * 1000;
const WEEK_MS = 7 * DAY_MS;

// Buckets a daily {date, close} price series (as returned by
// fetchHistory().data) into `weeks` trailing 7-day windows ending at the
// last date present in the series. Each bucket's close is the last daily
// close inside its window; weeks with no data get close: null so the line
// can gap rather than snapping to a stale value.
export function buildWeeklyBuckets(dailySeries, weeks = 52) {
  const points = (dailySeries || [])
    .map((p) => ({ ts: new Date(p.date).getTime(), close: p.close }))
    .filter((p) => Number.isFinite(p.ts) && p.close != null)
    .sort((a, b) => a.ts - b.ts);

  if (!points.length) return [];

  const endTs = points[points.length - 1].ts;
  const startTs = endTs - (weeks - 1) * WEEK_MS;

  const buckets = Array.from({ length: weeks }, (_, i) => {
    const weekTs = startTs + i * WEEK_MS;
    return { weekKey: new Date(weekTs).toISOString().slice(0, 10), weekTs, close: null };
  });

  for (const p of points) {
    if (p.ts < startTs) continue;
    const idx = Math.min(weeks - 1, Math.floor((p.ts - startTs) / WEEK_MS));
    buckets[idx].close = p.close;
  }

  return buckets;
}

// Snaps each buy/sell insider transaction to the weekly bucket containing
// its date, producing one dot descriptor per transaction. Transactions with
// side "other", an unparseable date, a date outside the bucket range, or
// whose bucket has no price (close: null) are dropped — they stay visible
// in the separate transactions list, just not plotted on this chart.
export function assignTransactionsToWeeks(transactions, buckets) {
  if (!buckets?.length) return [];
  const startTs = buckets[0].weekTs;
  const weeks = buckets.length;
  const dots = [];

  for (const t of transactions || []) {
    if (t.side !== "buy" && t.side !== "sell") continue;
    const ts = new Date(t.date).getTime();
    if (!Number.isFinite(ts) || ts < startTs) continue;
    const idx = Math.floor((ts - startTs) / WEEK_MS);
    if (idx < 0 || idx >= weeks) continue;
    const bucket = buckets[idx];
    if (bucket.close == null) continue;
    dots.push({
      key: `${bucket.weekKey}-${t.side}-${dots.length}`,
      side: t.side,
      weekKey: bucket.weekKey,
      weekTs: bucket.weekTs,
      close: bucket.close,
      insider: t.insider ?? null,
      date: t.date,
      shares: t.shares != null ? Math.abs(t.shares) : null,
      value: t.value != null ? Math.abs(t.value) : null,
    });
  }

  return dots;
}

// Pixel offset for spreading dots that land in the same week+side group so
// they don't fully overlap: 0, +6, -6, +12, -12, ... Applied to the
// rendered dot's cy, never to the underlying data value.
export function jitterOffsetPx(index) {
  if (!index) return 0;
  const magnitude = Math.ceil(index / 2) * 6;
  return index % 2 === 1 ? magnitude : -magnitude;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- insiderWeekly`
Expected: PASS, all cases green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/insiderWeekly.js frontend/src/lib/insiderWeekly.test.js
git commit -m "feat(stock-detail): add weekly bucketing helpers for insider dot chart"
```

---

### Task 2: Rewrite `InsiderVolumeChart` as the weekly dot chart

**Files:**
- Modify: `frontend/src/components/StockDetail.jsx` (recharts import ~line 4-7; delete `aggregateInsiderByMonth` ~lines 1885-1920; keep `MONTH_LABELS` ~line 1922; delete `formatMonthTick` ~lines 1924-1928; replace `InsiderVolumeChart` ~lines 1930-2087)

**Interfaces:**
- Consumes (from Task 1, `frontend/src/lib/insiderWeekly.js`): `buildWeeklyBuckets(dailySeries, weeks)`, `assignTransactionsToWeeks(transactions, buckets)`, `jitterOffsetPx(index)` — exact signatures as specified in Task 1.
- Consumes existing module-level helpers already in `StockDetail.jsx`: `fmtCompact(v, currencySymbol)`, `currencySymbol(code)`, `MONTH_LABELS` (array), and the imported `fetchHistory(ticker, period)` from `../api`.
- No change to `InsiderVolumeChart`'s own props (`{ ticker, transactions, currencyCode }`) or to how it's invoked at the `insiderVolume:` report-section key — the call site is untouched.

- [ ] **Step 1: Add `Scatter` to the recharts import**

In `frontend/src/components/StockDetail.jsx`, change the top-of-file recharts import:

```js
import {
  Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Customized, Legend,
  Line, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
```

to:

```js
import {
  Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, Customized, Legend,
  Line, Pie, PieChart, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis,
} from "recharts";
```

- [ ] **Step 2: Import the new helpers**

Add to the existing local-imports block (near `import { columnChanges } from "../lib/chartChanges";`):

```js
import { buildWeeklyBuckets, assignTransactionsToWeeks, jitterOffsetPx } from "../lib/insiderWeekly";
```

- [ ] **Step 3: Delete the now-dead monthly-only helpers**

Delete `aggregateInsiderByMonth` (the whole function, ~lines 1885-1920) and `formatMonthTick` (~lines 1924-1928). Keep the `MONTH_LABELS` constant — it's reused below.

- [ ] **Step 4: Replace `InsiderVolumeChart`**

Replace the entire `InsiderVolumeChart` function (from `function InsiderVolumeChart({ ticker, transactions, currencyCode }) {` through its closing `}`, ~lines 1930-2087) with:

```jsx
function formatWeekTick(ts) {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return MONTH_LABELS[d.getUTCMonth()];
}

// Custom Scatter `shape`: renders one buy/sell dot, applying the hover-fade
// (opposite side fades to near-zero opacity) and hover-enlarge behavior.
// Handlers live directly on the circle (not on <Scatter>) so they have
// cx/cy in scope, which is what positions the info-box overlay.
function makeDotShape({ side, color, hoveredKey, hoveredSide, onEnter, onLeave }) {
  return function DotShape(props) {
    const { cx, cy, payload } = props;
    if (cx == null || cy == null) return null;
    const jitterY = cy + jitterOffsetPx(payload.jitterIndex);
    const isHovered = hoveredKey === payload.key;
    const faded = hoveredSide != null && hoveredSide !== side;
    return (
      <circle
        cx={cx}
        cy={jitterY}
        r={isHovered ? 7 : 4}
        fill={color}
        fillOpacity={faded ? 0.05 : 1}
        stroke={color}
        strokeOpacity={isHovered ? 0.5 : 0}
        strokeWidth={isHovered ? 2 : 0}
        style={{ cursor: "pointer", transition: "fill-opacity 120ms ease" }}
        onMouseEnter={() => onEnter({ ...payload, cx, cy: jitterY })}
        onMouseLeave={onLeave}
      />
    );
  };
}

function InsiderVolumeChart({ ticker, transactions, currencyCode }) {
  const cs = currencySymbol(currencyCode);
  const [hoveredDot, setHoveredDot] = useState(null);

  const { data: hist } = useQuery({
    queryKey: ["history", ticker, "1y"],
    queryFn: () => fetchHistory(ticker, "1y"),
    staleTime: 5 * 60 * 1000,
    retry: false,
    enabled: Boolean(ticker),
  });

  const buckets = useMemo(() => buildWeeklyBuckets(hist?.data, 52), [hist]);

  const chartData = useMemo(
    () => buckets.map((b) => ({ x: b.weekTs, y: b.close })),
    [buckets],
  );

  const dots = useMemo(() => {
    const raw = assignTransactionsToWeeks(transactions, buckets);
    const groupCounts = new Map();
    return raw.map((d) => {
      const groupKey = `${d.weekKey}_${d.side}`;
      const idx = groupCounts.get(groupKey) ?? 0;
      groupCounts.set(groupKey, idx + 1);
      return { ...d, x: d.weekTs, y: d.close, jitterIndex: idx };
    });
  }, [transactions, buckets]);

  const buyDots = useMemo(() => dots.filter((d) => d.side === "buy"), [dots]);
  const sellDots = useMemo(() => dots.filter((d) => d.side === "sell"), [dots]);

  const hasPriceData = chartData.some((r) => r.y != null);
  if (!dots.length && !hasPriceData) return null;

  const closes = chartData.map((r) => r.y).filter((v) => v != null);
  const minClose = closes.length ? Math.min(...closes) : 0;
  const maxClose = closes.length ? Math.max(...closes) : 1;
  const pad = (maxClose - minClose) * 0.1 || maxClose * 0.05 || 1;

  return (
    <div>
      <h3 className="text-sm font-semibold text-muted uppercase tracking-wider mb-3">
        Insider Trading Volume
      </h3>
      <div className="bg-surface rounded-lg p-4">
        <div className="relative h-72">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={chartData} margin={{ top: 8, right: 24, bottom: 8, left: 8 }}>
              <CartesianGrid strokeDasharray="2 4" stroke={GRID_STROKE} vertical={false} />
              <XAxis
                dataKey="x"
                type="number"
                domain={["dataMin", "dataMax"]}
                tickFormatter={formatWeekTick}
                tick={AXIS_TICK}
                tickLine={false}
                axisLine={{ stroke: GRID_STROKE }}
              />
              <YAxis
                domain={[Math.max(0, minClose - pad), maxClose + pad]}
                tick={{ ...AXIS_TICK, fontSize: 10 }}
                tickFormatter={(v) => `${cs}${v.toFixed(2)}`}
                tickLine={false}
                axisLine={false}
                width={64}
              />
              <Line
                type="monotone"
                dataKey="y"
                stroke={CATEGORICAL[0]}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
                connectNulls
              />
              <Scatter
                data={buyDots}
                dataKey="y"
                isAnimationActive={false}
                shape={makeDotShape({
                  side: "buy",
                  color: GAIN_COLOR,
                  hoveredKey: hoveredDot?.key,
                  hoveredSide: hoveredDot?.side,
                  onEnter: setHoveredDot,
                  onLeave: () => setHoveredDot(null),
                })}
              />
              <Scatter
                data={sellDots}
                dataKey="y"
                isAnimationActive={false}
                shape={makeDotShape({
                  side: "sell",
                  color: LOSS_COLOR,
                  hoveredKey: hoveredDot?.key,
                  hoveredSide: hoveredDot?.side,
                  onEnter: setHoveredDot,
                  onLeave: () => setHoveredDot(null),
                })}
              />
              <Legend
                verticalAlign="top"
                align="left"
                height={20}
                iconType="square"
                iconSize={9}
                wrapperStyle={{ paddingBottom: 4 }}
                formatter={(v) => <span className="text-[10px] text-muted uppercase tracking-wider">{v}</span>}
                payload={[
                  { value: "Close Price", type: "line", color: CATEGORICAL[0] },
                  { value: "Insider Buys", type: "square", color: GAIN_COLOR },
                  { value: "Insider Sells", type: "square", color: LOSS_COLOR },
                ]}
              />
            </ComposedChart>
          </ResponsiveContainer>
          {hoveredDot && (
            <div
              className="absolute z-10 pointer-events-none bg-surface-card-elevated border border-hairline rounded-lg px-3 py-2 text-xs shadow-lg space-y-0.5 whitespace-nowrap"
              style={{ left: hoveredDot.cx, top: hoveredDot.cy, transform: "translate(14px, -50%)" }}
            >
              <div className="text-ink font-semibold truncate max-w-[180px]">
                {hoveredDot.insider || "—"}
              </div>
              <div className="text-muted">{hoveredDot.date}</div>
              <div className="text-ink">
                {hoveredDot.shares != null ? fmtCompact(hoveredDot.shares, "") : "—"} sh
              </div>
              <div className={hoveredDot.side === "buy" ? "text-gain" : "text-loss"}>
                {hoveredDot.value != null ? fmtCompact(hoveredDot.value, cs) : "—"}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

Note: the info box always anchors to the right of the hovered dot (`translate(14px, -50%)`). Dots very close to the chart's right edge may render their box slightly clipped — acceptable per YAGNI; revisit only if manual verification (Step 6) shows it's actually a problem.

- [ ] **Step 5: Run the frontend build and full test suite**

Run (from `frontend/`): `npm run build`
Expected: builds cleanly, no unused-import or reference errors (confirms `aggregateInsiderByMonth`/`formatMonthTick` removal didn't leave dangling references, and the new `Scatter` import/usage is valid JSX).

Run: `npm test`
Expected: full suite green, including the new `insiderWeekly.test.js` from Task 1.

- [ ] **Step 6: Manual verification against the running app**

Per CLAUDE.md's "Verifying UI changes": ensure dev servers are running (`start.bat` if not already up), then in Playwright:
1. Navigate to `http://localhost:5173`, log in with the dev password.
2. Open the "Latest Insider Transactions" list for a ticker with recent insider activity (check a few tickers already in the portfolio, or a well-covered large-cap like `AAPL`/`MSFT` as fallback) to confirm the underlying data exists.
3. Go to that ticker's Stock Detail page and confirm the "Insider Trading Volume" section now shows a weekly price line with green/red dots on it instead of monthly bars.
4. Hover a green dot: confirm red dots fade to near-invisible, the hovered dot enlarges, and an info box appears next to it showing name, date, shares, and $ amount matching that row in the transactions list below. Repeat hovering a red dot and confirm the reverse (greens fade, reds stay).
5. If any week has multiple same-side transactions, confirm their dots are visibly separated (not fully overlapping) and each is independently hoverable.
6. Screenshot the hovered state for the record.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/StockDetail.jsx
git commit -m "feat(stock-detail): render insider transactions as weekly dots on the price line"
```

---

## Testing Summary

- `npm test` from `frontend/` — full suite green, including new `insiderWeekly.test.js` coverage for bucketing, transaction-snapping, and jitter math.
- `npm run build` from `frontend/` — clean build.
- Manual Playwright pass against `http://localhost:5173` per Task 2 Step 6 — visual + interaction confirmation (hover-fade, info box content, overlap handling) that automated tests can't cover for a Recharts-rendered, mouse-driven chart.
