# Portfyl UX Overhaul — Phase 1: Design Foundation + Dashboard "Wow" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Portfyl's "dev tool" look with a premium, refined-light design system and a signature Dashboard hero (a living equity curve), so the app reads like paid SaaS (Sharesight / Snowball Analytics class) on first open.

**Architecture:** Build a reusable design foundation first — self-hosted type (Space Grotesk / Inter / JetBrains Mono), an expanded token system (ink, hairline, gain/loss, layered shadows, radii, motion), and a small kit of primitives (`Card`, `SectionHeader`, shimmer `Skeleton`, directive `EmptyState`, `DeltaPill`). Then assemble the Dashboard "wow": a `PortfolioHero` (count-up value over an ambient gradient equity curve + a day-change pill + supporting stat chips) mounted above the existing customizable widget grid, with every widget re-skinned through the new primitives. A tiny authoritative backend addition supplies the day-change number.

**Tech Stack:** React 18, Vite 6, TailwindCSS 3.4, recharts 2, lucide-react, @tanstack/react-query 5 (frontend); FastAPI + SQLAlchemy 2.0, yfinance (backend). New dev/test deps: Vitest, @testing-library/react, jsdom. New runtime deps: `@fontsource-variable/{space-grotesk,inter,jetbrains-mono}`. No count-up library — we write a hook.

## Global Constraints

- **Refined LIGHT theme only** this phase. No dark mode (deferred). Canvas `#F7F8FA`, Card `#FFFFFF`, Ink `#0B1220`, Muted `#64748B`, Hairline `#E6EAF0`, Gain `#10B981`, Loss `#EF4444`, Brand = themeable `var(--brand)`.
- **Type roles (exact):** Space Grotesk = display (hero value, page titles, section eyebrows, nav). Inter = body/labels/buttons/table text. JetBrains Mono = ALL financial figures (prices, %, P&L, table numeric columns, axis ticks, the day pill).
- **Preserve existing features unchanged:** the 3 swappable brand palettes (green/blue/purple), portfolio scoping (axios auto-injects `portfolio_id` — never thread it through call sites; agnostic prefixes `/portfolios`, `/market`, `/watchlists`), CZK/USD currency toggle, and the `react-grid-layout` customizable dashboard for the lower widgets.
- **All motion gated by `prefers-reduced-motion: reduce`.** One orchestrated load sequence + disciplined hovers only — no ambient/looping effects.
- **Backend resilience:** `day_change` must degrade to `null` (never raise / never hang) when yfinance returns nothing for the holdings — the hero hides the pill when null. Keep yfinance logging suppressed; bound the network call.
- **Do not commit rebuilt `frontend/dist` or `__pycache__`/`*.pyc` churn** (CLAUDE.md gotcha). Only commit source.
- **No new heavy dependencies** beyond the fonts and the test harness.
- **Verifying UI:** dev servers via `start.bat` (frontend :5173 proxies `/api` → backend :8000), dev login password `snowball-dev`. Visual tasks are verified with the `smoke-test-ui` skill (Playwright MCP screenshots), not by assertion.

## Testing Approach (read once)

The repo currently has **no test harness**. This plan adds Vitest for the genuinely testable logic — pure functions (`lib/format`), the `useCountUp` hook, and the backend pure aggregator — using classic red→green TDD. **Presentational components and visual aesthetics are verified differently:** each UI task ends with (a) a render *smoke* test (the component mounts without throwing and renders its key text/role) and (b) a Playwright screenshot gate via the `smoke-test-ui` skill. This is the honest verification shape for visual work — a unit test cannot assert "this looks premium." Every task below states which mode it uses.

---

## File Structure

**New (frontend):**
- `frontend/src/lib/format.js` — money/percent/compact/number formatters (DRY home for the inline `fmt`/`fmtPct` duplicated across pages).
- `frontend/src/lib/format.test.js` — unit tests.
- `frontend/src/hooks/useCountUp.js` — rAF count-up, `prefers-reduced-motion` aware.
- `frontend/src/hooks/useCountUp.test.js` — unit tests.
- `frontend/src/components/ui/Card.jsx` — `Card`.
- `frontend/src/components/ui/SectionHeader.jsx` — eyebrow + icon chip + action slot.
- `frontend/src/components/ui/Skeleton.jsx` — `Skeleton`, `SkeletonText`, `SkeletonRows`, `SkeletonChart`, `SkeletonMetric`.
- `frontend/src/components/ui/EmptyState.jsx` — icon + title + hint + action.
- `frontend/src/components/ui/DeltaPill.jsx` — gain/loss pill (arrow, value, pct).
- `frontend/src/components/ui/index.js` — barrel re-export.
- `frontend/src/components/ui/primitives.test.jsx` — render smoke tests for the kit.
- `frontend/src/components/PortfolioHero.jsx` — the signature hero.
- `frontend/src/components/HeroSparkline.jsx` — ambient recharts area curve.
- `frontend/src/test/setup.js` — jsdom + jest-dom setup.

**Modified (frontend):**
- `frontend/package.json` — add deps + `"test"` script.
- `frontend/vite.config.js` — add Vitest `test` config (jsdom, setup file).
- `frontend/src/main.jsx` — import the three `@fontsource-variable` CSS entries.
- `frontend/src/index.css` — tokens, font wiring, upgraded `.card`/`.btn-*`/`.input`, shimmer + fade-up keyframes, reduced-motion guard.
- `frontend/tailwind.config.js` — `fontFamily`, colors (`ink`, `hairline`, `gain`, `loss`), `boxShadow` scale, keyframes/animation.
- `frontend/src/App.jsx` — retune each palette's `bg` to the cooler canvas (tokens only; logic untouched).
- `frontend/src/pages/Dashboard.jsx` — mount `PortfolioHero` above the grid; drop the old `metrics` widget (folded into hero); re-skin all widgets via primitives; use `lib/format`.
- `frontend/src/components/PerformanceChart.jsx` — gradient area fill, gain/loss theming, refined tooltip + mono ticks.
- `frontend/src/components/DashboardGrid.jsx` — remove `metrics` from `ALL_WIDGETS`/`DEFAULT_LAYOUTS`; shift default `y` rows up.

**Modified (backend):**
- `backend/routers/portfolio.py` — extract `_two_day_closes(tickers)` (refactor `get_movers` onto it — DRY), add pure `aggregate_day_change(rows)`, wire `day_change`/`day_change_percent` into `get_summary`.
- `backend/tests/test_day_change.py` (NEW) — unit test for `aggregate_day_change` (pure, no yfinance).

---

## Phase 0 — Design Foundation

### Task 1: Test harness + fonts + dependencies

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/vite.config.js`
- Create: `frontend/src/test/setup.js`
- Modify: `frontend/src/main.jsx`

**Interfaces:**
- Produces: `npm test` (Vitest) runnable; `@fontsource-variable/*` font CSS imported globally; `globals: true` so `describe/it/expect` need no import.

- [ ] **Step 1: Install deps**

```bash
cd frontend
npm i @fontsource-variable/space-grotesk @fontsource-variable/inter @fontsource-variable/jetbrains-mono
npm i -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

- [ ] **Step 2: Add the test script to `frontend/package.json`**

In the `"scripts"` block add:

```json
    "test": "vitest run",
    "test:watch": "vitest"
```

- [ ] **Step 3: Wire Vitest into `frontend/vite.config.js`**

Add a `test` key to the exported config (keep existing `plugins`/`server`):

```js
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test/setup.js",
    css: false,
  },
```

If `vite.config.js` uses `defineConfig` from `vite`, switch the import to `import { defineConfig } from "vitest/config";` so the `test` key type-checks.

- [ ] **Step 4: Create `frontend/src/test/setup.js`**

```js
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 5: Import fonts globally in `frontend/src/main.jsx`** (add at top, before `./index.css`)

```js
import "@fontsource-variable/space-grotesk";
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
```

- [ ] **Step 6: Verify the harness runs**

Run: `cd frontend && npx vitest run`
Expected: Vitest starts and reports `No test files found` (exit 0) — harness works; tests come next.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.js frontend/src/test/setup.js frontend/src/main.jsx
git commit -m "build: add Vitest harness and self-hosted fonts (Space Grotesk, Inter, JetBrains Mono)"
```

---

### Task 2: Design tokens (CSS + Tailwind + palettes)

**Files:**
- Modify: `frontend/tailwind.config.js`
- Modify: `frontend/src/index.css`
- Modify: `frontend/src/App.jsx:28-41` (PALETTES `bg` values only)

**Interfaces:**
- Produces: Tailwind utilities `font-display`/`font-sans`/`font-mono`, colors `text-ink`/`border-hairline`/`text-gain`/`text-loss`, `shadow-card`/`shadow-card-hover`/`shadow-pop`, `animate-fade-up`; CSS classes `.card`/`.btn-primary`/`.btn-ghost`/`.input` upgraded; `.shimmer` utility; reduced-motion guard.

- [ ] **Step 1: Replace `frontend/tailwind.config.js`**

```js
/** @type {import('tailwindcss').Config} */
import defaultTheme from "tailwindcss/defaultTheme";

export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Space Grotesk Variable"', '"Space Grotesk"', ...defaultTheme.fontFamily.sans],
        sans: ['"Inter Variable"', "Inter", ...defaultTheme.fontFamily.sans],
        mono: ['"JetBrains Mono Variable"', '"JetBrains Mono"', ...defaultTheme.fontFamily.mono],
      },
      colors: {
        surface: {
          DEFAULT: "var(--bg)",
          card: "#FFFFFF",
          hover: "var(--bg-subtle)",
          border: "#E6EAF0",
        },
        brand: {
          DEFAULT: "var(--brand)",
          dim: "var(--brand-hover)",
          light: "var(--brand-light)",
        },
        ink: "#0B1220",
        hairline: "#E6EAF0",
        gain: "#10B981",
        loss: "#EF4444",
      },
      boxShadow: {
        card: "0 1px 2px rgba(11,18,32,0.04), 0 1px 3px rgba(11,18,32,0.06)",
        "card-hover": "0 6px 16px rgba(11,18,32,0.08), 0 2px 6px rgba(11,18,32,0.05)",
        pop: "0 12px 32px rgba(11,18,32,0.14)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.5s cubic-bezier(0.16,1,0.3,1) both",
      },
    },
  },
  plugins: [],
};
```

Note: the `surface.border` token now points at the softer hairline `#E6EAF0` (was `#E2E8F0`) so existing `border-surface-border` usages get the refined value for free.

- [ ] **Step 2: Replace `frontend/src/index.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    --brand: #059669;
    --brand-hover: #047857;
    --brand-light: #D1FAE5;
    --bg: #F6F8F7;
    --bg-subtle: #F0FDF4;
    --sidebar-active: #ECFDF5;
    --ink: #0B1220;
    --muted: #64748B;
    --hairline: #E6EAF0;
    --gain: #10B981;
    --loss: #EF4444;
  }
  body {
    @apply bg-surface text-ink font-sans;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    line-height: 1.5;
  }
  * { box-sizing: border-box; }
  ::-webkit-scrollbar { width: 8px; height: 8px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #DCE2EA; border-radius: 4px; }
  ::-webkit-scrollbar-thumb:hover { background: #B6C0CD; }
  h1, h2, h3, .font-display { font-family: theme("fontFamily.display"); }
  .tnum { font-variant-numeric: tabular-nums; }
}

@layer components {
  .card {
    @apply bg-surface-card rounded-2xl border border-hairline p-5 shadow-card;
    transition: box-shadow 0.18s ease, transform 0.18s ease, border-color 0.18s ease;
  }
  .card-interactive:hover {
    @apply shadow-card-hover -translate-y-0.5;
    border-color: color-mix(in srgb, var(--brand) 22%, var(--hairline));
  }
  .btn-primary {
    @apply bg-brand hover:bg-brand-dim text-white font-semibold px-4 py-2 rounded-lg transition-colors;
  }
  .btn-ghost {
    @apply border border-hairline hover:border-slate-300 text-slate-500 hover:text-slate-700 px-4 py-2 rounded-lg transition-colors;
  }
  .input {
    @apply bg-slate-50 border border-hairline rounded-lg px-3 py-2 text-ink placeholder-slate-400 focus:outline-none focus:border-brand w-full;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  .input:focus { box-shadow: 0 0 0 3px var(--brand-light); }
  .eyebrow {
    @apply font-display text-[11px] font-semibold uppercase tracking-[0.12em] text-slate-500;
  }
  .gain { @apply text-gain; }
  .loss { @apply text-loss; }
}

@layer utilities {
  .shimmer {
    position: relative;
    overflow: hidden;
    background: #EEF1F5;
  }
  .shimmer::after {
    content: "";
    position: absolute;
    inset: 0;
    transform: translateX(-100%);
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.65), transparent);
    animation: shimmer 1.4s ease-in-out infinite;
  }
  @keyframes shimmer { 100% { transform: translateX(100%); } }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.001ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.001ms !important;
    scroll-behavior: auto !important;
  }
  .shimmer::after { display: none; }
}
```

Key changes to be aware of: body text color moves `slate-800` → `ink` (`#0B1220`); the `.card` hover lift is opt-in via `.card-interactive` (so static cards don't bounce). Existing `.card` usages keep working and just gain the new radius/shadow/border.

- [ ] **Step 3: Retune palette canvas in `frontend/src/App.jsx:28-41`**

Change only the `bg` hex in each palette (leave every other value):

```js
const PALETTES = {
  green: {
    brand: "#059669", brandHover: "#047857", brandLight: "#D1FAE5",
    bg: "#F6F8F7", bgSubtle: "#F0FDF4", sidebarActive: "#ECFDF5",
  },
  blue: {
    brand: "#2563EB", brandHover: "#1D4ED8", brandLight: "#DBEAFE",
    bg: "#F5F7FA", bgSubtle: "#F1F5F9", sidebarActive: "#EFF6FF",
  },
  purple: {
    brand: "#7C3AED", brandHover: "#6D28D9", brandLight: "#EDE9FE",
    bg: "#F7F6FB", bgSubtle: "#F5F3FF", sidebarActive: "#F5F3FF",
  },
};
```

- [ ] **Step 4: Verify the app still builds and renders**

Run: `cd frontend && npm run build`
Expected: build succeeds (no Tailwind/PostCSS errors).
Then with `start.bat` running, load http://localhost:5173 — the app renders with the new fonts (Inter body, headings in Space Grotesk) and softer surfaces; nothing is broken.

- [ ] **Step 5: Commit**

```bash
git add frontend/tailwind.config.js frontend/src/index.css frontend/src/App.jsx
git commit -m "feat(design): expand token system — type, ink/hairline/gain/loss, shadows, motion, reduced-motion"
```

---

### Task 3: `lib/format` formatters (TDD)

**Files:**
- Create: `frontend/src/lib/format.js`
- Test: `frontend/src/lib/format.test.js`

**Interfaces:**
- Produces:
  - `formatMoney(n, currency = "USD") -> string` — `null/undefined → "—"`; 2 dp; en-US grouping; CZK suffix `" Kč"`, else `$` prefix; sign before the symbol (`-$12.00`, `-12.00 Kč`).
  - `formatPercent(n, { sign = true, digits = 2 } = {}) -> string` — `null → "—"`; `+`/`-` per `sign`; `"%"` suffix.
  - `formatCompact(n, currency = "USD") -> string` — `null → "—"`; compact notation (`$190K`, `$1.2M`); CZK suffix.
  - `formatNumber(n, digits = 0) -> string` — `null → "—"`; en-US grouping, fixed digits.

- [ ] **Step 1: Write the failing test `frontend/src/lib/format.test.js`**

```js
import { formatMoney, formatPercent, formatCompact, formatNumber } from "./format";

describe("formatMoney", () => {
  it("formats USD with symbol and 2dp", () => {
    expect(formatMoney(1234.5, "USD")).toBe("$1,234.50");
  });
  it("formats CZK with suffix", () => {
    expect(formatMoney(1234.5, "CZK")).toBe("1,234.50 Kč");
  });
  it("puts the sign before the symbol for negatives", () => {
    expect(formatMoney(-12, "USD")).toBe("-$12.00");
    expect(formatMoney(-12, "CZK")).toBe("-12.00 Kč");
  });
  it("returns an em dash for null/undefined", () => {
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney(undefined)).toBe("—");
  });
});

describe("formatPercent", () => {
  it("adds a + for positives by default", () => {
    expect(formatPercent(2.4)).toBe("+2.40%");
  });
  it("omits the + when sign:false", () => {
    expect(formatPercent(2.4, { sign: false })).toBe("2.40%");
  });
  it("keeps the - for negatives", () => {
    expect(formatPercent(-1.2)).toBe("-1.20%");
  });
  it("returns an em dash for null", () => {
    expect(formatPercent(null)).toBe("—");
  });
});

describe("formatCompact", () => {
  it("compacts thousands with currency symbol", () => {
    expect(formatCompact(190000, "USD")).toBe("$190K");
  });
  it("returns an em dash for null", () => {
    expect(formatCompact(null)).toBe("—");
  });
});

describe("formatNumber", () => {
  it("groups with no decimals by default", () => {
    expect(formatNumber(12345)).toBe("12,345");
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/lib/format.test.js`
Expected: FAIL — `Failed to resolve import "./format"`.

- [ ] **Step 3: Implement `frontend/src/lib/format.js`**

```js
const DASH = "—";

export function formatMoney(n, currency = "USD") {
  if (n == null || Number.isNaN(n)) return DASH;
  const sign = n < 0 ? "-" : "";
  const str = Math.abs(n).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return currency === "CZK" ? `${sign}${str} Kč` : `${sign}$${str}`;
}

export function formatPercent(n, { sign = true, digits = 2 } = {}) {
  if (n == null || Number.isNaN(n)) return DASH;
  const prefix = n >= 0 ? (sign ? "+" : "") : "-";
  return `${prefix}${Math.abs(n).toFixed(digits)}%`;
}

export function formatCompact(n, currency = "USD") {
  if (n == null || Number.isNaN(n)) return DASH;
  const sign = n < 0 ? "-" : "";
  const str = Math.abs(n).toLocaleString("en-US", {
    notation: "compact",
    maximumFractionDigits: 1,
  });
  return currency === "CZK" ? `${sign}${str} Kč` : `${sign}$${str}`;
}

export function formatNumber(n, digits = 0) {
  if (n == null || Number.isNaN(n)) return DASH;
  return n.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/lib/format.test.js`
Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/format.js frontend/src/lib/format.test.js
git commit -m "feat(format): add shared money/percent/compact/number formatters with tests"
```

---

### Task 4: `useCountUp` hook (TDD)

**Files:**
- Create: `frontend/src/hooks/useCountUp.js`
- Test: `frontend/src/hooks/useCountUp.test.js`

**Interfaces:**
- Produces: `useCountUp(target, { duration = 900, enabled = true } = {}) -> number` — animates 0→`target` with rAF and an ease-out; returns `target` immediately when `enabled` is false, when `prefers-reduced-motion` is set, or when `target` is not a finite number. Re-animates when `target` changes.

- [ ] **Step 1: Write the failing test `frontend/src/hooks/useCountUp.test.js`**

```js
import { renderHook } from "@testing-library/react";
import { useCountUp } from "./useCountUp";

describe("useCountUp", () => {
  it("returns the target immediately when disabled", () => {
    const { result } = renderHook(() => useCountUp(1000, { enabled: false }));
    expect(result.current).toBe(1000);
  });

  it("returns the target immediately under reduced motion", () => {
    window.matchMedia = (q) => ({
      matches: true, media: q, onchange: null,
      addEventListener() {}, removeEventListener() {},
      addListener() {}, removeListener() {}, dispatchEvent() { return false; },
    });
    const { result } = renderHook(() => useCountUp(500));
    expect(result.current).toBe(500);
  });

  it("passes through a non-finite target unchanged", () => {
    const { result } = renderHook(() => useCountUp(null, { enabled: true }));
    expect(result.current).toBe(null);
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/hooks/useCountUp.test.js`
Expected: FAIL — cannot resolve `./useCountUp`.

- [ ] **Step 3: Implement `frontend/src/hooks/useCountUp.js`**

```js
import { useEffect, useRef, useState } from "react";

function prefersReducedMotion() {
  return typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function useCountUp(target, { duration = 900, enabled = true } = {}) {
  const isNumber = typeof target === "number" && Number.isFinite(target);
  const [value, setValue] = useState(isNumber ? (enabled ? 0 : target) : target);
  const frame = useRef(null);

  useEffect(() => {
    if (!isNumber || !enabled || prefersReducedMotion()) {
      setValue(target);
      return;
    }
    const start = performance.now();
    const from = 0;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
      setValue(from + (target - from) * eased);
      if (t < 1) frame.current = requestAnimationFrame(tick);
    };
    frame.current = requestAnimationFrame(tick);
    return () => frame.current && cancelAnimationFrame(frame.current);
  }, [target, duration, enabled, isNumber]);

  return value;
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd frontend && npx vitest run src/hooks/useCountUp.test.js`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/useCountUp.js frontend/src/hooks/useCountUp.test.js
git commit -m "feat(hooks): add reduced-motion-aware useCountUp"
```

---

### Task 5: UI primitive kit (render smoke tests)

**Files:**
- Create: `frontend/src/components/ui/Card.jsx`
- Create: `frontend/src/components/ui/SectionHeader.jsx`
- Create: `frontend/src/components/ui/Skeleton.jsx`
- Create: `frontend/src/components/ui/EmptyState.jsx`
- Create: `frontend/src/components/ui/DeltaPill.jsx`
- Create: `frontend/src/components/ui/index.js`
- Test: `frontend/src/components/ui/primitives.test.jsx`

**Interfaces:**
- Consumes: `formatMoney`, `formatPercent` from `../../lib/format`.
- Produces (barrel `ui/index.js`):
  - `<Card as="div" interactive={false} className padded={true} ...rest>` — applies `.card` (+ `.card-interactive` when `interactive`); `padded={false}` drops padding for flush charts.
  - `<SectionHeader icon={LucideComp} action={node} className>{label}</SectionHeader>` — brand-tinted icon chip + `.eyebrow` label + right-aligned `action`.
  - `<Skeleton className w h rounded>`; `<SkeletonText lines={3}>`; `<SkeletonRows rows={5} cols={4}>`; `<SkeletonChart height={256}>`; `<SkeletonMetric>` — all use the `.shimmer` utility.
  - `<EmptyState icon={LucideComp} title hint action={node}>` — centered, muted, directive.
  - `<DeltaPill value={number} pct={number} currency="USD" size="md">` — gain/loss colored pill, `▲`/`▼`, mono `formatMoney(value)` + `(formatPercent(pct))`; renders `null` when both `value` and `pct` are null.

- [ ] **Step 1: Write the failing smoke test `frontend/src/components/ui/primitives.test.jsx`**

```jsx
import { render, screen } from "@testing-library/react";
import { Calendar } from "lucide-react";
import { Card, SectionHeader, Skeleton, EmptyState, DeltaPill } from "./index";

describe("ui primitives", () => {
  it("Card renders children", () => {
    render(<Card>hello</Card>);
    expect(screen.getByText("hello")).toBeInTheDocument();
  });
  it("SectionHeader renders its label", () => {
    render(<SectionHeader icon={Calendar}>Earnings Calendar</SectionHeader>);
    expect(screen.getByText("Earnings Calendar")).toBeInTheDocument();
  });
  it("Skeleton renders a shimmer element", () => {
    const { container } = render(<Skeleton w="4rem" h="1rem" />);
    expect(container.querySelector(".shimmer")).toBeTruthy();
  });
  it("EmptyState shows title and hint", () => {
    render(<EmptyState icon={Calendar} title="No holdings yet" hint="Import to begin." />);
    expect(screen.getByText("No holdings yet")).toBeInTheDocument();
    expect(screen.getByText("Import to begin.")).toBeInTheDocument();
  });
  it("DeltaPill shows a formatted gain", () => {
    render(<DeltaPill value={58000} pct={2.41} currency="USD" />);
    expect(screen.getByText(/\$58,000\.00/)).toBeInTheDocument();
    expect(screen.getByText(/2\.41%/)).toBeInTheDocument();
  });
  it("DeltaPill renders nothing when empty", () => {
    const { container } = render(<DeltaPill value={null} pct={null} />);
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/components/ui/primitives.test.jsx`
Expected: FAIL — cannot resolve `./index`.

- [ ] **Step 3: Implement `frontend/src/components/ui/Card.jsx`**

```jsx
export function Card({ as: Tag = "div", interactive = false, padded = true, className = "", children, ...rest }) {
  return (
    <Tag
      className={[
        "card",
        interactive ? "card-interactive" : "",
        padded ? "" : "p-0",
        className,
      ].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </Tag>
  );
}
```

- [ ] **Step 4: Implement `frontend/src/components/ui/SectionHeader.jsx`**

```jsx
export function SectionHeader({ icon: Icon, action, className = "", children }) {
  return (
    <div className={`flex items-center justify-between mb-4 ${className}`}>
      <div className="flex items-center gap-2 min-w-0">
        {Icon && (
          <span className="grid place-items-center w-6 h-6 rounded-lg bg-brand/10 text-brand shrink-0">
            <Icon size={13} />
          </span>
        )}
        <span className="eyebrow truncate">{children}</span>
      </div>
      {action && <div className="flex items-center gap-2 shrink-0">{action}</div>}
    </div>
  );
}
```

- [ ] **Step 5: Implement `frontend/src/components/ui/Skeleton.jsx`**

```jsx
export function Skeleton({ w = "100%", h = "1rem", rounded = "0.5rem", className = "" }) {
  return <div className={`shimmer ${className}`} style={{ width: w, height: h, borderRadius: rounded }} />;
}

export function SkeletonText({ lines = 3, className = "" }) {
  return (
    <div className={`space-y-2 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} h="0.75rem" w={i === lines - 1 ? "60%" : "100%"} />
      ))}
    </div>
  );
}

export function SkeletonRows({ rows = 5, cols = 4, className = "" }) {
  return (
    <div className={`space-y-2.5 ${className}`}>
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex items-center gap-3">
          {Array.from({ length: cols }).map((_, c) => (
            <Skeleton key={c} h="0.85rem" w={c === 0 ? "3.5rem" : "100%"} className="flex-1" />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonChart({ height = 256, className = "" }) {
  return <Skeleton h={`${height}px`} w="100%" rounded="0.75rem" className={className} />;
}

export function SkeletonMetric({ className = "" }) {
  return (
    <div className={`space-y-2 ${className}`}>
      <Skeleton h="0.7rem" w="40%" />
      <Skeleton h="1.6rem" w="70%" />
    </div>
  );
}
```

- [ ] **Step 6: Implement `frontend/src/components/ui/EmptyState.jsx`**

```jsx
export function EmptyState({ icon: Icon, title, hint, action, className = "" }) {
  return (
    <div className={`flex flex-col items-center justify-center text-center py-10 px-4 ${className}`}>
      {Icon && (
        <span className="grid place-items-center w-11 h-11 rounded-2xl bg-slate-100 text-slate-400 mb-3">
          <Icon size={20} />
        </span>
      )}
      {title && <p className="font-display text-sm font-semibold text-slate-700">{title}</p>}
      {hint && <p className="text-xs text-slate-500 mt-1 max-w-[34ch]">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
```

- [ ] **Step 7: Implement `frontend/src/components/ui/DeltaPill.jsx`**

```jsx
import { formatMoney, formatPercent } from "../../lib/format";

const SIZES = {
  sm: "text-[11px] px-1.5 py-0.5 gap-1",
  md: "text-xs px-2 py-1 gap-1.5",
  lg: "text-sm px-2.5 py-1 gap-1.5",
};

export function DeltaPill({ value = null, pct = null, currency = "USD", size = "md", className = "" }) {
  if (value == null && pct == null) return null;
  const positive = (value ?? pct ?? 0) >= 0;
  const tone = positive
    ? "bg-gain/10 text-gain"
    : "bg-loss/10 text-loss";
  return (
    <span className={`inline-flex items-center rounded-full font-mono font-semibold tnum ${SIZES[size]} ${tone} ${className}`}>
      <span aria-hidden="true">{positive ? "▲" : "▼"}</span>
      {value != null && <span>{formatMoney(Math.abs(value), currency)}</span>}
      {pct != null && <span className="opacity-80">({formatPercent(pct)})</span>}
    </span>
  );
}
```

- [ ] **Step 8: Implement the barrel `frontend/src/components/ui/index.js`**

```js
export { Card } from "./Card";
export { SectionHeader } from "./SectionHeader";
export { Skeleton, SkeletonText, SkeletonRows, SkeletonChart, SkeletonMetric } from "./Skeleton";
export { EmptyState } from "./EmptyState";
export { DeltaPill } from "./DeltaPill";
```

- [ ] **Step 9: Run to verify the smoke tests pass**

Run: `cd frontend && npx vitest run src/components/ui/primitives.test.jsx`
Expected: PASS (6 tests).

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/ui
git commit -m "feat(ui): add primitive kit — Card, SectionHeader, Skeleton, EmptyState, DeltaPill"
```

---

## Phase 1 — Dashboard "Wow"

### Task 6: Backend day-change in `/portfolio/summary` (TDD on the pure aggregator)

**Files:**
- Modify: `backend/routers/portfolio.py` (extract `_two_day_closes`; refactor `get_movers` onto it; add `aggregate_day_change`; wire summary)
- Test: `backend/tests/test_day_change.py` (NEW)

**Interfaces:**
- Produces:
  - `_two_day_closes(tickers: list[str]) -> dict[str, tuple[float, float]]` — `{ticker: (start_close, end_close)}` from a bounded `yf.download(..., period="2d")`; tickers with <2 closes are omitted; returns `{}` (never raises) on any error/empty.
  - `aggregate_day_change(rows: list[dict]) -> tuple[float, float]` — pure. Each row `{"shares": float, "start": float, "end": float, "fx": float}`. Returns `(change, prev_value)` where `change = Σ shares*(end-start)*fx`, `prev_value = Σ shares*start*fx`.
  - `get_summary` response gains `"day_change"` and `"day_change_percent"` (both `float`, or `null` when no closes are available).
- Consumes: existing `_build_holdings`, `get_holdings`, `_two_day_closes`.

- [ ] **Step 1: Write the failing test `backend/tests/test_day_change.py`**

```python
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routers.portfolio import aggregate_day_change


def test_aggregate_day_change_basic():
    rows = [
        {"shares": 10, "start": 100.0, "end": 110.0, "fx": 1.0},  # +100
        {"shares": 5,  "start": 200.0, "end": 190.0, "fx": 1.0},  # -50
    ]
    change, prev_value = aggregate_day_change(rows)
    assert round(change, 2) == 50.0
    assert round(prev_value, 2) == 2000.0  # 10*100 + 5*200


def test_aggregate_day_change_applies_fx():
    rows = [{"shares": 1, "start": 100.0, "end": 110.0, "fx": 23.0}]  # +10 native * 23
    change, prev_value = aggregate_day_change(rows)
    assert round(change, 2) == 230.0
    assert round(prev_value, 2) == 2300.0


def test_aggregate_day_change_empty():
    assert aggregate_day_change([]) == (0.0, 0.0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && python -m pytest tests/test_day_change.py -v`
Expected: FAIL — `ImportError: cannot import name 'aggregate_day_change'`. (If pytest is missing: `pip install pytest`.)

- [ ] **Step 3: Add the pure aggregator + the extracted fetch to `backend/routers/portfolio.py`**

Add near the other module-level helpers (above `get_movers`):

```python
def aggregate_day_change(rows):
    """Pure: sum per-holding day P&L and the prior day's value, both in the
    display currency (each row carries its own fx multiplier)."""
    change = 0.0
    prev_value = 0.0
    for r in rows:
        shares, start, end, fx = r["shares"], r["start"], r["end"], r["fx"]
        change += shares * (end - start) * fx
        prev_value += shares * start * fx
    return change, prev_value


def _two_day_closes(tickers):
    """{ticker: (start_close, end_close)} from a 2-day window. Never raises."""
    if not tickers:
        return {}
    try:
        raw = yf.download(tickers, period="2d", auto_adjust=True, progress=False)
        if raw is None or raw.empty:
            return {}
        if len(tickers) == 1:
            closes = raw[["Close"]].rename(columns={"Close": tickers[0]})
        else:
            closes = raw["Close"] if "Close" in raw.columns else raw
    except Exception:
        return {}
    closes = closes.ffill().dropna(how="all")
    out = {}
    for ticker in tickers:
        if ticker not in closes.columns:
            continue
        col = closes[ticker].dropna()
        if len(col) < 2:
            continue
        out[ticker] = (float(col.iloc[0]), float(col.iloc[-1]))
    return out
```

- [ ] **Step 4: Refactor `get_movers` to reuse `_two_day_closes` (DRY)**

Replace the inline download/close-extraction block in `get_movers` (current lines ~1047-1073) so it builds `closes_map = _two_day_closes(tickers)` for the `1d` path and derives `start_price`/`end_price` from it. Keep the `1w`/`1m` periods on their existing `period_map` download (only `1d` needs the shared 2-day helper). Concretely, for the `1d` case:

```python
    if period.lower() == "1d":
        closes_map = _two_day_closes(tickers)
        if not closes_map:
            return {"gainers": [], "losers": []}
        results = []
        for ticker in tickers:
            if ticker not in closes_map:
                continue
            start_price, end_price = closes_map[ticker]
            if start_price <= 0:
                continue
            change_pct = round(((end_price - start_price) / start_price) * 100, 2)
            price, name, currency = _fetch_price_and_info(ticker)
            shares = active[ticker]["shares"]
            results.append({
                "ticker": ticker, "name": name,
                "current_price": round(end_price, 2),
                "change_pct": change_pct,
                "period_pnl": round(shares * (end_price - start_price), 2),
                "currency": currency,
            })
        results.sort(key=lambda x: x["change_pct"], reverse=True)
        return {
            "gainers": results[:5],
            "losers": list(reversed(results[-5:])) if len(results) >= 5 else list(reversed(results)),
        }
    # ... existing multi-period path unchanged below ...
```

(Leave the existing non-`1d` logic intact beneath this branch.)

- [ ] **Step 5: Wire day-change into `get_summary`** (`backend/routers/portfolio.py`, in the return-dict region ~457-465)

Before the `return {`, build rows whose `fx` is the *implied* per-holding rate from the already-converted holdings (so it stays exactly consistent with `total_value`):

```python
    # Day change — authoritative, reuses the movers 2-day-close logic across ALL
    # holdings. fx per holding is derived from the already-converted market_value
    # so it matches total_value exactly. Degrades to None on any data gap.
    day_change = None
    day_change_pct = None
    active_day = _build_holdings(transactions)
    closes_map = _two_day_closes(list(active_day.keys())) if active_day else {}
    if closes_map:
        rows = []
        mv_by_ticker = {h["ticker"]: h for h in holdings}
        for ticker, (start_px, end_px) in closes_map.items():
            shares = active_day[ticker]["shares"]
            h = mv_by_ticker.get(ticker)
            if not h or shares <= 0 or end_px <= 0:
                continue
            fx = h["market_value"] / (shares * end_px)  # native -> display currency
            rows.append({"shares": shares, "start": start_px, "end": end_px, "fx": fx})
        if rows:
            change, prev_value = aggregate_day_change(rows)
            day_change = round(change, 2)
            day_change_pct = round(change / prev_value * 100, 2) if prev_value > 0 else None
```

Then add to the returned dict:

```python
        "day_change": day_change,
        "day_change_percent": day_change_pct,
```

- [ ] **Step 6: Run the pure-aggregator test to verify it passes**

Run: `cd backend && python -m pytest tests/test_day_change.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Smoke-verify the live endpoint**

With `start.bat` running and the sample portfolio imported, hit the summary endpoint (logged-in browser or curl with the session cookie). Confirm the JSON now includes `day_change` and `day_change_percent` (numbers, or `null` if yfinance returned nothing) and that `total_value` is unchanged.

- [ ] **Step 8: Commit**

```bash
git add backend/routers/portfolio.py backend/tests/test_day_change.py
git commit -m "feat(api): add day_change/day_change_percent to /portfolio/summary; DRY movers onto _two_day_closes"
```

---

### Task 7: `HeroSparkline` + `PortfolioHero` (render smoke test)

**Files:**
- Create: `frontend/src/components/HeroSparkline.jsx`
- Create: `frontend/src/components/PortfolioHero.jsx`
- Test: extend `frontend/src/components/ui/primitives.test.jsx` is wrong home — Create: `frontend/src/components/PortfolioHero.test.jsx`

**Interfaces:**
- Consumes: `useCountUp`, `formatMoney`/`formatCompact`, `DeltaPill`, recharts `AreaChart`.
- Produces:
  - `<HeroSparkline data={Array<{value:number}>} positive={bool} />` — ambient, non-interactive `AreaChart` (no axes/grid/tooltip) with a brand/gain or loss gradient fill; returns `null` when `data` has <2 points.
  - `<PortfolioHero summary={object|undefined} loading={bool} currency="USD" series={Array} />` — renders the eyebrow, the count-up value (`summary.total_value`), a `DeltaPill` from `summary.day_change`/`day_change_percent` (hidden when both null), the ambient `HeroSparkline` (from `series`), and a supporting chip row (Invested, All-time P&L, Dividends, Holdings). Shows `SkeletonMetric`/`Skeleton` placeholders while `loading`.

- [ ] **Step 1: Write the failing test `frontend/src/components/PortfolioHero.test.jsx`**

```jsx
import { render, screen } from "@testing-library/react";
import PortfolioHero from "./PortfolioHero";

const summary = {
  total_value: 248310.55, total_invested: 190000, total_pnl: 58310.55,
  total_pnl_percent: 30.7, total_dividends: 2100, holdings_count: 23,
  day_change: 5820.12, day_change_percent: 2.41,
};

describe("PortfolioHero", () => {
  it("renders the portfolio value and the day pill", () => {
    render(<PortfolioHero summary={summary} loading={false} currency="USD" series={[]} />);
    expect(screen.getByText(/PORTFOLIO VALUE/i)).toBeInTheDocument();
    expect(screen.getByText(/2\.41%/)).toBeInTheDocument();
  });

  it("renders skeletons while loading without throwing", () => {
    const { container } = render(<PortfolioHero summary={undefined} loading currency="USD" series={[]} />);
    expect(container.querySelector(".shimmer")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd frontend && npx vitest run src/components/PortfolioHero.test.jsx`
Expected: FAIL — cannot resolve `./PortfolioHero`.

- [ ] **Step 3: Implement `frontend/src/components/HeroSparkline.jsx`**

```jsx
import { AreaChart, Area, ResponsiveContainer, YAxis } from "recharts";

export default function HeroSparkline({ data = [], positive = true }) {
  if (!Array.isArray(data) || data.length < 2) return null;
  const color = positive ? "var(--brand)" : "#EF4444";
  return (
    <div className="absolute inset-x-0 bottom-0 h-28 pointer-events-none opacity-[0.18] select-none" aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="heroFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.9} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2} fill="url(#heroFill)" isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 4: Implement `frontend/src/components/PortfolioHero.jsx`**

```jsx
import { useCountUp } from "../hooks/useCountUp";
import { formatMoney, formatCompact, formatNumber } from "../lib/format";
import { DeltaPill, Skeleton, SkeletonMetric } from "./ui";
import HeroSparkline from "./HeroSparkline";

function Chip({ label, value }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wider text-slate-400 font-medium">{label}</span>
      <span className="font-mono text-sm font-semibold text-ink tnum">{value}</span>
    </div>
  );
}

export default function PortfolioHero({ summary, loading, currency = "USD", series = [] }) {
  const positive = (summary?.day_change ?? summary?.total_pnl ?? 0) >= 0;
  const animatedValue = useCountUp(summary?.total_value ?? 0, { enabled: !loading && summary != null });

  return (
    <section className="card card-interactive relative overflow-hidden p-6 animate-fade-up">
      <HeroSparkline data={series} positive={positive} />
      <div className="relative">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="eyebrow">Portfolio Value</p>
            {loading || summary == null ? (
              <div className="mt-2"><Skeleton h="2.75rem" w="16rem" /></div>
            ) : (
              <div className="flex items-baseline gap-3 flex-wrap mt-1">
                <span className="font-display text-[clamp(2.25rem,5vw,3.25rem)] font-bold tracking-tight text-ink tnum leading-none">
                  {formatMoney(animatedValue, currency)}
                </span>
                <DeltaPill value={summary.day_change} pct={summary.day_change_percent} currency={currency} size="lg" />
              </div>
            )}
          </div>
        </div>

        <div className="mt-6 grid grid-cols-2 sm:grid-cols-4 gap-x-8 gap-y-4 max-w-2xl">
          {loading || summary == null ? (
            <>
              <SkeletonMetric /><SkeletonMetric /><SkeletonMetric /><SkeletonMetric />
            </>
          ) : (
            <>
              <Chip label="Invested" value={formatCompact(summary.total_invested, currency)} />
              <Chip
                label="All-time P&L"
                value={`${summary.total_pnl >= 0 ? "+" : ""}${formatCompact(summary.total_pnl, currency)}`}
              />
              <Chip label="Dividends" value={formatCompact(summary.total_dividends, currency)} />
              <Chip label="Holdings" value={formatNumber(summary.holdings_count)} />
            </>
          )}
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd frontend && npx vitest run src/components/PortfolioHero.test.jsx`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/HeroSparkline.jsx frontend/src/components/PortfolioHero.jsx frontend/src/components/PortfolioHero.test.jsx
git commit -m "feat(dashboard): add PortfolioHero with count-up value, day pill, ambient equity curve"
```

---

### Task 8: Mount the hero; retire the old metrics widget

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`
- Modify: `frontend/src/components/DashboardGrid.jsx`

**Interfaces:**
- Consumes: `PortfolioHero`; the existing `summary`/`perf`/`sl`/`pl` query state in `Dashboard`.
- Produces: hero rendered above `DashboardGrid`; `metrics` removed from `ALL_WIDGETS`/`DEFAULT_LAYOUTS`; the `metrics` child key removed from the `DashboardGrid` children object.

- [ ] **Step 1: Build the hero series in `Dashboard.jsx`**

After the `perf` query, derive a lightweight series for the sparkline. The perf points expose `value` (verified — `PerformanceChart` renders the portfolio line with `dataKey="value"`):

```js
  const heroSeries = (perf || [])
    .map((p) => ({ value: p.value }))
    .filter((p) => Number.isFinite(p.value));
```

- [ ] **Step 2: Render the hero above the grid in `Dashboard.jsx`**

Immediately under the page header `</div>` (the flex row with the title + Customize/Refresh buttons), before `<DashboardGrid ...>`, add:

```jsx
      <PortfolioHero summary={summary} loading={sl} currency={currency} series={heroSeries} />
```

And add the import at the top:

```js
import PortfolioHero from "../components/PortfolioHero";
```

- [ ] **Step 3: Remove the `metrics` widget from the grid children**

In `Dashboard.jsx`, delete the entire `metrics: ( ... )` entry from the object passed to `DashboardGrid` (the 5 `MetricCard`s now live in the hero). Leave the other six widget entries unchanged.

- [ ] **Step 4: Remove `metrics` from `DashboardGrid.jsx`**

In `ALL_WIDGETS` delete the `{ id: "metrics", ... }` line. In `DEFAULT_LAYOUTS.lg` delete the `metrics` row and shift the remaining rows' `y` up by 2 so the layout starts at the top:

```js
const DEFAULT_LAYOUTS = {
  lg: [
    { i: "performance", x: 0, y: 0, w: 3, h: 5 },
    { i: "heatmap", x: 3, y: 0, w: 3, h: 5 },
    { i: "earnings", x: 0, y: 5, w: 3, h: 4 },
    { i: "holdings", x: 3, y: 5, w: 3, h: 4 },
    { i: "insiderBuys", x: 0, y: 9, w: 6, h: 5 },
    { i: "movers", x: 0, y: 14, w: 6, h: 4 },
  ],
};
```

Note: users with a saved `sb_dashboard_layout`/`sb_dashboard_widgets` in localStorage still containing `metrics` are handled gracefully — `DashboardGrid` filters layouts by `visible`, and a `metrics` id with no matching child renders nothing. No migration needed, but the old metrics card will simply disappear (intended).

- [ ] **Step 5: Verify in the browser**

With dev servers running, open the Dashboard: the hero shows the count-up value + day pill + chips over the faint curve; the old 5-card metrics row is gone; the six widgets render below. Run `cd frontend && npm run build` to confirm no unused-import/JSX errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Dashboard.jsx frontend/src/components/DashboardGrid.jsx
git commit -m "feat(dashboard): mount PortfolioHero; retire standalone metrics widget"
```

---

### Task 9: Re-skin the six Dashboard widgets through the primitives

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`

**Interfaces:**
- Consumes: `Card`, `SectionHeader`, `SkeletonRows`/`SkeletonChart`, `EmptyState`, `DeltaPill` from `../components/ui`; `formatMoney`/`formatPercent` from `../lib/format`.
- Produces: every widget uses `SectionHeader` (not ad-hoc `<h2 class="uppercase…">`), shimmer skeletons (not "Loading…" text), and `EmptyState` (not bare "No …" text). The inline `fmt`/`fmtPct` are replaced by `formatMoney`/`formatPercent`.

This is a **mechanical application** task: swap the repeated patterns. Apply this transformation to each widget.

- [ ] **Step 1: Replace the inline formatters with the shared lib**

At the top of `Dashboard.jsx` add `import { formatMoney, formatPercent } from "../lib/format";` and add to the existing `ui` import. Delete the local `const fmt = ...` and `const fmtPct = ...` (lines ~83-94). Then replace call sites: `fmt(x)` → `formatMoney(x, currency)`, `fmtPct(x)` → `formatPercent(x)`. (The `convert` shim is already a no-op; leave it or inline it.)

- [ ] **Step 2: Apply the per-widget transformation**

For each widget, (a) wrap the body in `<Card className="h-full" padded>` instead of `<div className="card h-full">`; (b) replace the header `<h2>` with `<SectionHeader icon={...} action={...controls}>Label</SectionHeader>`; (c) replace the loading branch with the matching skeleton; (d) replace the empty branch with `<EmptyState>`. Exact content per widget:

| Widget | SectionHeader icon | Loading skeleton | EmptyState (icon, title, hint) |
|---|---|---|---|
| performance | `TrendingUp` | `<SkeletonChart height={256} />` | n/a (chart handles its own empty) |
| heatmap | `LayoutGrid` | `<SkeletonChart height={256} />` | icon `LayoutGrid`, "No holdings to map", "Import transactions to see your heatmap." |
| earnings | `Calendar` | `<SkeletonRows rows={6} cols={3} />` | icon `Calendar`, "No upcoming earnings", "None of your current holdings report soon." |
| holdings | `PieChart` (import from lucide) | `<SkeletonRows rows={8} cols={3} />` | icon `PieChart`, "No holdings yet", "Import your transactions to see your top positions." + an `EmptyState` action `<a href="/import" className="btn-primary text-xs">Import CSV</a>` |
| insiderBuys | `UserCheck` | `<SkeletonRows rows={6} cols={6} />` | icon `UserCheck`, "No insider buys", "No insider purchases across your holdings in the last 12 months." |
| movers | `Activity` (import from lucide) | `<SkeletonRows rows={6} cols={3} />` | icon `Activity`, "No movers yet", "Import transactions to track daily gainers and losers." |

The segmented controls currently inside each `<h2>` flex row move into the `action` prop of `SectionHeader` unchanged (same button markup).

- [ ] **Step 3: Worked example — the `earnings` widget** (apply the same shape to the others)

Before:

```jsx
          earnings: (
            <div className="card h-full flex flex-col">
              <h2 className="text-sm font-semibold text-slate-500 mb-4 uppercase tracking-wider flex items-center gap-2">
                <Calendar size={14} /> Earnings Calendar
              </h2>
              {el ? (
                <div className="h-20 flex items-center justify-center">
                  <div className="text-slate-500 text-sm animate-pulse">Loading earnings…</div>
                </div>
              ) : earnings.length === 0 ? (
                <p className="text-slate-400 text-xs">No upcoming earnings reports for current holdings.</p>
              ) : (
                /* ...rows... */
```

After:

```jsx
          earnings: (
            <Card className="h-full flex flex-col">
              <SectionHeader icon={Calendar}>Earnings Calendar</SectionHeader>
              {el ? (
                <SkeletonRows rows={6} cols={3} />
              ) : earnings.length === 0 ? (
                <EmptyState icon={Calendar} title="No upcoming earnings"
                  hint="None of your current holdings report soon." />
              ) : (
                /* ...rows unchanged, but fmt(...) -> formatMoney(..., currency)... */
```

- [ ] **Step 4: Use `DeltaPill` for the movers' change column** (optional polish)

In the gainers/losers rows, the `+{m.change_pct}%` / `{m.change_pct}%` span can become `<DeltaPill pct={m.change_pct} value={null} size="sm" />` for consistent tone. Keep the `formatMoney(m.period_pnl, currency)` value column as-is.

- [ ] **Step 5: Verify**

Run `cd frontend && npx vitest run` (all unit/smoke tests still green) and `cd frontend && npm run build`. In the browser, toggle to an empty portfolio (or temporarily point at one) to confirm the new empty states render; confirm loading shows shimmer skeletons (throttle network in devtools).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/Dashboard.jsx
git commit -m "feat(dashboard): re-skin widgets via SectionHeader/Skeleton/EmptyState; use shared formatters"
```

---

### Task 10: PerformanceChart polish

**Files:**
- Modify: `frontend/src/components/PerformanceChart.jsx`

**Interfaces:**
- Produces: gradient area fill under the portfolio line tinted by overall direction; mono tick labels; a refined tooltip card (white, `shadow-pop`, rounded-xl, mono numbers); reduced/!subtle gridlines. Benchmark lines and the existing `mode`/`benchmarks` props are unchanged.

- [ ] **Step 1: Note the existing structure (already mapped).** `PerformanceChart` is a `ComposedChart` that ALREADY has: `defs` gradients `gValue`/`gInvested`/`gGrowth`, a `CustomTooltip`, `CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0"`, axis ticks `{ fill: "#64748B", fontSize: 11 }`, the portfolio `<Area dataKey="value" stroke="#22c55e" fill="url(#gValue)">`, the invested `<Area dataKey="invested" stroke="#3b82f6" fill="url(#gInvested)">`, the growth-mode `<Area dataKey="pnl_pct">`, and benchmark `<Line>`s on a second y-axis. This is a **refinement**, not a rewrite — preserve every `dataKey`, the `mode`/`benchmarks`/`benchmarkMeta` props, the dual y-axes, the legend, and the sampling/merge logic.

- [ ] **Step 2: Re-tint to the design tokens.** In `defs`, change the `gValue` and `gGrowth` gradient stop colors from `#22c55e` to `var(--brand)` (so the chart follows the active palette) with `stopOpacity` `0.2 → 0`. Update the portfolio `Area` `stroke` (both value and growth modes) from `#22c55e` to `var(--brand)` and bump `strokeWidth` to `2.5`. Soften the invested `Area` stroke from `#3b82f6` to a muted `#94A3B8` (invested is context, not the hero line).

- [ ] **Step 3: Refine grid + axes.** `CartesianGrid` → drop `strokeDasharray`, set `vertical={false}` and `stroke="#EEF1F5"`. On every `XAxis`/`YAxis`, add `axisLine={false}`, `tickLine={false}`, and change `tick` to `{ fill: "#94A3B8", fontSize: 11, fontFamily: "JetBrains Mono Variable" }` so axis numbers render in mono.

- [ ] **Step 4: Refine the existing `CustomTooltip`.** Swap its container classes to `bg-white border border-hairline rounded-xl shadow-pop px-3 py-2 text-xs`; import `formatMoney`/`formatPercent` from `../lib/format` and replace the inline `fmtMoney`/`fmtSignedMoney`/`fmtSignedPct` with them (`formatPercent` already prefixes the sign); add `font-mono tnum` to every value `<span>`; map the `moneyColor` gain/loss branches to the `text-gain`/`text-loss` tokens.

- [ ] **Step 5: Verify** with `npm run build` and a browser screenshot of the performance widget across periods (7D/YTD/All) and with a benchmark toggled on — lines render, tooltip is legible, no console errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/PerformanceChart.jsx
git commit -m "feat(dashboard): gradient area fill, mono ticks, refined tooltip for PerformanceChart"
```

---

### Task 11: Orchestrated load animation

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`

**Interfaces:**
- Produces: a single staggered fade-up of the hero then the widget grid on first mount, gated by `prefers-reduced-motion` (handled globally in CSS — the `.animate-fade-up` utility is neutralized under reduced motion).

- [ ] **Step 1:** The hero already has `animate-fade-up` (Task 7). Add a small stagger to the grid container: wrap the non-editing grid render in `DashboardGrid` so each visible widget gets `className="animate-fade-up"` with `style={{ animationDelay: \`${index * 60}ms\` }}`. Cap the delay at ~360ms so later widgets don't lag.

- [ ] **Step 2:** In `DashboardGrid.jsx`, in the **non-editing** branch only (the `space-y-6` map), add the delay:

```jsx
        <div className="space-y-6">
          {visible.map((id, i) => (
            <div key={id} className="animate-fade-up" style={{ animationDelay: `${Math.min(i * 60, 360)}ms` }}>
              {children[id]}
            </div>
          ))}
        </div>
```

(Do not add animation to the editing/draggable branch — it interferes with drag transforms.)

- [ ] **Step 3: Verify** — reload the Dashboard: hero and cards rise in once, smoothly; enable "Reduce motion" in OS settings and confirm everything appears instantly with no movement.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Dashboard.jsx frontend/src/components/DashboardGrid.jsx
git commit -m "feat(dashboard): orchestrated fade-up load sequence (reduced-motion safe)"
```

---

### Task 12: Dashboard QA sweep

**Files:** none (verification only)

- [ ] **Step 1: Run the full unit/smoke suite**

Run: `cd frontend && npx vitest run`
Expected: all tests pass.
Run: `cd backend && python -m pytest tests/ -v`
Expected: day-change tests pass.

- [ ] **Step 2: Run the `smoke-test-ui` skill against the Dashboard**

Use the `smoke-test-ui` skill (Playwright MCP) to log in (`snowball-dev`) and screenshot the Dashboard. Verify: hero count-up + curve + day pill render; no blank charts; no console errors; no failed `/api` calls. Capture before/after screenshots of the Dashboard for the record.

- [ ] **Step 3: Accessibility floor** — keyboard-tab through the Dashboard: focus rings are visible on the Customize/Refresh buttons and segmented controls; the hero curve is `aria-hidden`; color is not the only signal (the day pill has ▲/▼ glyphs). Fix any gap found.

- [ ] **Step 4: Responsive check** — narrow the viewport to ~390px: the hero value clamps down, chips wrap to 2 columns, widgets stack. Fix any overflow.

- [ ] **Step 5: Final commit (if fixes were made)**

Stage only the source touched by QA fixes — never `git add -A` (it would sweep in rebuilt `dist`/`pyc` churn, violating the global constraint):

```bash
git add frontend/src
git commit -m "fix(dashboard): a11y focus + responsive polish from QA sweep"
```

---

## Out of Scope (next plan)

**Phase 2 — Consistency pass (separate plan, written after this one lands):** apply the primitives + type system to the **Sidebar** (active rail, grouped nav, refined controls) and every remaining page — Allocation, Transactions, Analytics, Dividends, TaxReport, Options, Polymarket, Watchlists, Import, Settings, Search, Stock, Assistant, PlatformLanding. Standardize page H1s, tables, tabs/segmented controls, buttons, inputs, loading, and empty states. That plan's tasks will reference the **real** primitive signatures finalized here (`Card`, `SectionHeader`, `Skeleton*`, `EmptyState`, `DeltaPill`, `lib/format`), which is exactly why it's deferred until these exist.

**Phase 3 — Dividend tracking upgrade** (yield-on-cost, DRIP, projected income, dividend growth) remains explicitly after the whole UX foundation, per the agreed direction.

---

## Self-Review

**Spec coverage** (against the locked direction — refined light, Space Grotesk/Inter/JetBrains Mono, living equity-curve hero, consistency primitives, disciplined motion):
- Refined-light tokens → Task 2. ✓
- Three-font type system → Tasks 1 (load) + 2 (wire). ✓
- Living equity-curve hero (count-up value, day pill, ambient curve, chips) → Tasks 6 (data) + 7 (component) + 8 (mount). ✓
- Reusable consistency primitives (Card/SectionHeader/Skeleton/EmptyState/DeltaPill) → Task 5, applied Task 9. ✓
- Skeletons replace "Loading…" text; EmptyStates replace bare text → Task 9. ✓
- Disciplined motion, reduced-motion safe → Tasks 2 (guard) + 7/11 (sequence). ✓
- Preserve palettes/scoping/currency/grid → Constraints + Tasks 2/8 (tokens-only palette edit; grid kept). ✓
- Day-change sourced authoritatively + graceful degradation → Task 6 + hero null-guard. ✓

**Placeholder scan:** every code step contains complete code except Tasks 9–11, which are explicitly framed as *mechanical application / recharts edits* with a worked example (Task 9 Step 3) and an exact per-widget table — no "TBD"/"add error handling"/"similar to Task N" hand-waves. Task 1 Step 3 and Task 4 Step 3 call out the two easy-to-miss gotchas inline (vitest/config import; `useRef` casing).

**Type consistency:** `formatMoney(n, currency)`, `formatPercent(n, opts)`, `formatCompact(n, currency)`, `formatNumber(n, digits)` used consistently in Tasks 3/5/7/9. `useCountUp(target, {duration, enabled})` defined Task 4, consumed Task 7. `<DeltaPill value pct currency size>`, `<SectionHeader icon action>`, `<Skeleton w h rounded>`/`SkeletonRows`/`SkeletonChart`/`SkeletonMetric`, `<EmptyState icon title hint action>` defined Task 5, consumed Tasks 7/9. Backend `aggregate_day_change(rows)` + `_two_day_closes(tickers)` defined and consumed within Task 6; summary keys `day_change`/`day_change_percent` produced Task 6, consumed Task 7. Consistent throughout.
