# Portfyl Premium Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Portfyl a premium warm glassmorphism/neumorphism look on a
user-supplied earthy palette, move every Stock Detail metric into its own
rounded KPI box, and roll the look out app-wide — with tasteful,
dependency-free animations and highly readable, well-spaced text.

**Architecture:** Retune the existing light `neu` theme's design tokens to the
new palette and make it the default look (the `glass`/Classic theme stays as an
option). Everything flows through CSS custom properties + shared components, so
retuning tokens and upgrading `MetricCard` premiumizes all pages automatically;
Stock Detail gets a deep KPI-box rebuild. Animations use vendored react-bits
components adapted to zero external dependencies.

**Tech Stack:** React 18 + Vite 6, TailwindCSS 3.4 (JSX only, no TS), recharts,
Vitest + Testing Library. react-bits components vendored as JSX.

**Spec:** `docs/superpowers/specs/2026-08-30-portfyl-premium-redesign-design.md`

## Global Constraints

- **No new npm dependencies.** Vendor react-bits as JSX; reuse the existing
  `useCountUp` hook; do reveals with `IntersectionObserver` + CSS.
- **All files are `.jsx`/`.js`** — no TypeScript. Strip all TS types when
  vendoring react-bits components.
- **Do not alter the `glass` theme** appearance or its blue/green/purple accents.
- **Preserve** `sb_*` localStorage keys and `owner_id="default"` behavior.
- **Keep every existing Vitest test green.** Run `npm test` from `frontend/`.
- Follow existing Tailwind opacity conventions already in the codebase
  (`bg-brand/10`, `bg-gain/10`, `bg-amber-500/15`, …) — reuse them, don't invent
  a different opacity mechanism.
- Run commands from `frontend/` unless stated otherwise. Build = `npm run build`,
  tests = `npm test`.
- Commit after each task with the message shown in its final step.

**Exact palette → tokens** (single source of truth for the whole plan):

```
bg #F3E8DA | bgSubtle #ECE0CF
surfaceCard rgba(250,245,237,0.78) | surfaceCardElevated rgba(253,249,243,0.92)
border/hairline rgba(120,105,84,0.14)
ink #3A352C | muted #6B6353
brand #6D7048 | brandHover #5C5F3C | brandLight #E4E5D3
gain #5B7A4C | loss #B8543A
glassBorderAlpha rgba(120,105,84,0.16) | glassOverlayAlpha rgba(255,252,247,0.55)
blurCard 14px | blurOverlay 22px
shadowAmbient 7px 7px 18px rgba(190,172,146,0.5), -7px -7px 18px rgba(255,253,248,0.9)
shadowInset inset 3px 3px 8px rgba(190,172,146,0.45), inset -3px -3px 8px rgba(255,253,248,0.85)
radiusCard 1.25rem
chart [#A9AB88,#DBAA89,#D4C3A1,#B7AFA3,#7C8A5A,#C08457,#9E8E6E,#8A8478]
```

---

## Task 1: Vendor react-bits components (dependency-free)

**Files:**
- Create: `frontend/src/components/reactbits/SpotlightCard.jsx`
- Create: `frontend/src/components/reactbits/ShinyText.jsx`
- Create: `frontend/src/components/reactbits/Reveal.jsx`

**Interfaces:**
- Produces:
  - `SpotlightCard({ children, className?, spotlightColor? })` — default export.
  - `ShinyText({ text, className?, speed?=4, disabled?=false })` — default export.
  - `Reveal({ children, className?, delay?=0, as?='div' })` — default export.

- [ ] **Step 1: Create `SpotlightCard.jsx`** (vendored from react-bits, TSX→JSX; hardcoded dark surface removed so it inherits the theme)

```jsx
import { useRef, useState } from "react";

// Vendored from React Bits (Components/SpotlightCard), converted TSX→JSX.
// The upstream hardcoded `bg-neutral-900 border-neutral-800 p-8` were removed
// so the card inherits the app theme; callers supply their own surface classes
// via `className`. Warm radial glow follows the cursor.
export default function SpotlightCard({
  children,
  className = "",
  spotlightColor = "rgba(169,171,136,0.28)",
}) {
  const divRef = useRef(null);
  const [isFocused, setIsFocused] = useState(false);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [opacity, setOpacity] = useState(0);

  const handleMouseMove = (e) => {
    if (!divRef.current || isFocused) return;
    const rect = divRef.current.getBoundingClientRect();
    setPosition({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };
  const handleFocus = () => {
    setIsFocused(true);
    setOpacity(0.6);
  };
  const handleBlur = () => {
    setIsFocused(false);
    setOpacity(0);
  };
  const handleMouseEnter = () => setOpacity(0.6);
  const handleMouseLeave = () => setOpacity(0);

  return (
    <div
      ref={divRef}
      onMouseMove={handleMouseMove}
      onFocus={handleFocus}
      onBlur={handleBlur}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      className={`relative overflow-hidden ${className}`}
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-500 ease-in-out"
        style={{
          opacity,
          background: `radial-gradient(circle at ${position.x}px ${position.y}px, ${spotlightColor}, transparent 70%)`,
        }}
      />
      {children}
    </div>
  );
}
```

- [ ] **Step 2: Create `ShinyText.jsx`** (react-bits ShinyText adapted to dependency-free CSS; the `.shiny-text` keyframes are added to `index.css` in Task 3)

```jsx
// Adapted from React Bits (TextAnimations/ShinyText) to a dependency-free CSS
// implementation — the upstream version pulls in `motion`. A highlight sweeps
// across the text via an animated clip-gradient (see `.shiny-text` in index.css).
export default function ShinyText({ text, className = "", speed = 4, disabled = false }) {
  if (disabled) return <span className={className}>{text}</span>;
  return (
    <span className={`shiny-text ${className}`} style={{ animationDuration: `${speed}s` }}>
      {text}
    </span>
  );
}
```

- [ ] **Step 3: Create `Reveal.jsx`** (plays react-bits AnimatedContent's role via IntersectionObserver + CSS, no gsap)

```jsx
import { useEffect, useRef, useState } from "react";

// Lightweight scroll/mount reveal — react-bits AnimatedContent's role, done
// dependency-free (upstream pulls in gsap). Fades + lifts children in when they
// enter the viewport. Respects prefers-reduced-motion and degrades to
// immediately-visible where IntersectionObserver is unavailable (e.g. jsdom).
export default function Reveal({ children, className = "", delay = 0, as: Tag = "div" }) {
  const ref = useRef(null);
  const [shown, setShown] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const reduce =
      typeof window !== "undefined" &&
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || typeof IntersectionObserver === "undefined") {
      setShown(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            setShown(true);
            io.disconnect();
          }
        });
      },
      { threshold: 0.08 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <Tag
      ref={ref}
      className={className}
      style={{
        opacity: shown ? 1 : 0,
        transform: shown ? "none" : "translateY(12px)",
        transition:
          "opacity .5s cubic-bezier(.16,1,.3,1), transform .5s cubic-bezier(.16,1,.3,1)",
        transitionDelay: `${delay}ms`,
      }}
    >
      {children}
    </Tag>
  );
}
```

- [ ] **Step 4: Verify build**

Run: `npm run build`
Expected: build succeeds (files compile; not yet imported anywhere).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/reactbits/
git commit -m "feat(frontend): vendor react-bits SpotlightCard/ShinyText/Reveal as dependency-free JSX"
```

---

## Task 2: Retune design tokens + make Premium the default theme

**Files:**
- Modify: `frontend/src/App.jsx` (`NEU_TOKENS` ~lines 61-76; `applyAppearance` neu branch ~96-121 and glass branch end ~144-153; `themeStyle` default ~267-269)
- Modify: `frontend/src/components/Sidebar.jsx` (style option label ~line 110)

**Interfaces:**
- Consumes: nothing new.
- Produces: `applyAppearance` toggles a `theme-premium` class on
  `document.documentElement` whenever the premium (`neu`) style is active
  (consumed by CSS in Task 3). Default `themeStyle` becomes `"neu"`.

- [ ] **Step 1: Replace the `NEU_TOKENS` object in `App.jsx`** with the retuned palette

Find the existing `const NEU_TOKENS = { ... };` block and replace it entirely with:

```jsx
// Premium — one fixed warm light appearance (no dark variant, no accent
// palettes). Glassmorphism/neumorphism hybrid on the user's earthy palette;
// see docs/superpowers/specs/2026-08-30-portfyl-premium-redesign-design.md.
const NEU_TOKENS = {
  bg: "#F3E8DA", bgSubtle: "#ECE0CF",
  surfaceCard: "rgba(250,245,237,0.78)", surfaceCardElevated: "rgba(253,249,243,0.92)",
  border: "rgba(120,105,84,0.14)", hairline: "rgba(120,105,84,0.14)",
  // Text-bearing tokens darkened from the raw palette so each clears WCAG AA on
  // the cream card; the raw sage/peach live in `chart` (large fills, not text).
  ink: "#3A352C", muted: "#6B6353",
  brand: "#6D7048", brandHover: "#5C5F3C", brandLight: "#E4E5D3",
  gain: "#5B7A4C", loss: "#B8543A",
  // Glass hybrid: translucent surfaces + blur over the warm mesh background,
  // on top of the neumorphic dual shadow.
  glassBorderAlpha: "rgba(120,105,84,0.16)",
  glassOverlayAlpha: "rgba(255,252,247,0.55)",
  blurCard: "14px", blurOverlay: "22px",
  shadowAmbient: "7px 7px 18px rgba(190,172,146,0.5), -7px -7px 18px rgba(255,253,248,0.9)",
  shadowInset: "inset 3px 3px 8px rgba(190,172,146,0.45), inset -3px -3px 8px rgba(255,253,248,0.85)",
  radiusCard: "1.25rem",
  chart: ["#A9AB88", "#DBAA89", "#D4C3A1", "#B7AFA3", "#7C8A5A", "#C08457", "#9E8E6E", "#8A8478"],
};
```

- [ ] **Step 2: Update the `neu` branch of `applyAppearance`** to enable the glass hybrid and stamp the `theme-premium` class

Replace the entire `if (themeStyle === "neu") { ... return; }` block with:

```jsx
  if (themeStyle === "neu") {
    s.setProperty("--brand", NEU_TOKENS.brand);
    s.setProperty("--brand-hover", NEU_TOKENS.brandHover);
    s.setProperty("--brand-light", NEU_TOKENS.brandLight);
    s.setProperty("--bg", NEU_TOKENS.bg);
    s.setProperty("--bg-subtle", NEU_TOKENS.bgSubtle);
    s.setProperty("--sidebar-active", NEU_TOKENS.brandLight);
    s.setProperty("--surface-card", NEU_TOKENS.surfaceCard);
    s.setProperty("--surface-card-elevated", NEU_TOKENS.surfaceCardElevated);
    s.setProperty("--border", NEU_TOKENS.border);
    s.setProperty("--hairline", NEU_TOKENS.hairline);
    s.setProperty("--ink", NEU_TOKENS.ink);
    s.setProperty("--muted", NEU_TOKENS.muted);
    s.setProperty("--gain", NEU_TOKENS.gain);
    s.setProperty("--loss", NEU_TOKENS.loss);
    // Glass hybrid (was zeroed in the pure-neu original).
    s.setProperty("--glass-border-alpha", NEU_TOKENS.glassBorderAlpha);
    s.setProperty("--glass-overlay-alpha", NEU_TOKENS.glassOverlayAlpha);
    s.setProperty("--blur-card", NEU_TOKENS.blurCard);
    s.setProperty("--blur-overlay", NEU_TOKENS.blurOverlay);
    s.setProperty("--shadow-ambient", NEU_TOKENS.shadowAmbient);
    s.setProperty("--shadow-inset", NEU_TOKENS.shadowInset);
    s.setProperty("--radius-card", NEU_TOKENS.radiusCard);
    NEU_TOKENS.chart.forEach((color, i) => s.setProperty(`--chart-${i + 1}`, color));
    document.documentElement.classList.toggle("dark", false);
    document.documentElement.classList.toggle("theme-premium", true);
    return;
  }
```

- [ ] **Step 3: In the `glass` branch of `applyAppearance`, clear the `theme-premium` class**

Find the last line of the glass branch, `document.documentElement.classList.toggle("dark", isDark);`, and add immediately after it:

```jsx
  document.documentElement.classList.toggle("theme-premium", false);
```

- [ ] **Step 4: Make Premium the default `themeStyle` with a one-time migration**

Replace the `themeStyle` state initializer in `PaletteProvider`:

```jsx
  const [themeStyle, setThemeStyleState] = useState(() => {
    // One-time upgrade to the Premium (retuned neumorphism) default. Existing
    // installs have sb_theme_style="glass"; flip them once so the premium look
    // becomes active. Users can still switch to Classic afterwards — the flag
    // makes the flip happen only once, so a later manual choice sticks.
    const stored = localStorage.getItem("sb_theme_style");
    if (!localStorage.getItem("sb_premium_default_v1")) {
      localStorage.setItem("sb_premium_default_v1", "1");
      localStorage.setItem("sb_theme_style", "neu");
      return "neu";
    }
    return stored || "neu";
  });
```

- [ ] **Step 5: Relabel the style switcher in `Sidebar.jsx`**

Change the `neu` option label from `"Neumorphism"` to `"Premium"` and its title:

```jsx
              { value: "neu", label: "Premium", title: "Premium warm theme (default)" },
```

(Leave the `glass` option `{ value: "glass", label: "Classic", ... }` unchanged.)

- [ ] **Step 6: Verify build + existing tests**

Run: `npm run build && npm test`
Expected: build succeeds; all existing tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/App.jsx frontend/src/components/Sidebar.jsx
git commit -m "feat(frontend): retune neumorphism theme to warm premium palette, make it the default"
```

---

## Task 3: Premium background mesh + shine keyframes in CSS

**Files:**
- Modify: `frontend/src/index.css` (append to the file)

**Interfaces:**
- Consumes: the `theme-premium` class from Task 2; `.shiny-text` used by
  `ShinyText.jsx` from Task 1.
- Produces: warm mesh background under the premium theme; `.shiny-text` styling.

- [ ] **Step 1: Append the premium background + shine styles to `index.css`**

Add at the end of the file (after the existing dark-mode scrollbar block):

```css
/* ----------------------------------------------------------------------------
 * Premium theme (retuned neumorphism) — a warm mesh gradient behind everything
 * so the translucent glass cards have something to refract. Scoped to the
 * `theme-premium` class set by applyAppearance(). Fixed so it doesn't scroll.
 * ------------------------------------------------------------------------- */
.theme-premium body {
  background:
    radial-gradient(1200px 800px at 12% -10%, rgba(169,171,136,0.22), transparent 60%),
    radial-gradient(1000px 700px at 108% 8%, rgba(219,170,137,0.20), transparent 55%),
    radial-gradient(900px 900px at 50% 118%, rgba(212,195,161,0.18), transparent 60%),
    var(--bg);
  background-attachment: fixed;
}

/* ShinyText — a highlight sweeps across the text via an animated clip-gradient.
 * Used sparingly on hero headings. */
.shiny-text {
  display: inline-block;
  background: linear-gradient(
    120deg,
    var(--ink) 0%, var(--ink) 42%,
    color-mix(in srgb, var(--brand) 55%, #ffffff) 50%,
    var(--ink) 58%, var(--ink) 100%
  );
  background-size: 200% auto;
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  color: transparent;
  animation: shiny-text-move 4s linear infinite;
}
@keyframes shiny-text-move { to { background-position: -200% center; } }

@media (prefers-reduced-motion: reduce) {
  .shiny-text {
    animation: none;
    color: var(--ink);
    -webkit-text-fill-color: var(--ink);
  }
}
```

- [ ] **Step 2: Verify build**

Run: `npm run build`
Expected: build succeeds.

- [ ] **Step 3: Visual check (dev server)**

Ensure dev servers run (`start.bat` from repo root, or `npm run dev` in `frontend/`).
Open `http://localhost:5173`, log in with `snowball-dev`. Confirm the app now
shows the warm cream background with soft glass cards. If the style switcher
in the sidebar shows "Classic" selected, click **Premium** once.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(frontend): warm mesh background + ShinyText keyframes for premium theme"
```

---

## Task 4: Spaced number formatters (TDD)

**Files:**
- Modify: `frontend/src/lib/format.js`
- Test: `frontend/src/lib/format.test.js`

**Interfaces:**
- Produces:
  - `formatNumberSpaced(n, digits=0) -> string` — space thousands separators,
    comma decimal ("1 234 567,89"); `"—"` for null/NaN.
  - `formatMoneySpaced(n, currency="USD", digits=2) -> string` — same grouping
    with the currency prefix/suffix ("$1 234,50", "1 234,50 Kč").

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/lib/format.test.js` (import the two new names in the
existing import from `./format`):

```js
describe("formatNumberSpaced", () => {
  it("groups thousands with spaces and uses a comma decimal", () => {
    expect(formatNumberSpaced(1234567.89, 2)).toBe("1 234 567,89");
  });
  it("handles integers with no decimals", () => {
    expect(formatNumberSpaced(1234567, 0)).toBe("1 234 567");
  });
  it("keeps the sign and groups the absolute value", () => {
    expect(formatNumberSpaced(-1234.5, 1)).toBe("-1 234,5");
  });
  it("returns a dash for null/NaN", () => {
    expect(formatNumberSpaced(null)).toBe("—");
    expect(formatNumberSpaced(NaN)).toBe("—");
  });
});

describe("formatMoneySpaced", () => {
  it("appends the CZK suffix with a space", () => {
    expect(formatMoneySpaced(1234.5, "CZK")).toBe("1 234,50 Kč");
  });
  it("prefixes USD", () => {
    expect(formatMoneySpaced(1234.5, "USD")).toBe("$1 234,50");
  });
  it("returns a dash for null", () => {
    expect(formatMoneySpaced(null, "USD")).toBe("—");
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- format`
Expected: FAIL — `formatNumberSpaced`/`formatMoneySpaced` are not exported.

- [ ] **Step 3: Implement the helpers in `format.js`**

Append to `frontend/src/lib/format.js` (it already defines `DASH` and the
internal `currencyParts`):

```js
// Group thousands with a plain space and use a comma decimal (Czech-readable,
// e.g. "1 234 567,89"). Implemented by hand rather than via Intl so the group
// separator is a deterministic ASCII space (Intl emits U+00A0/U+202F depending
// on the ICU build, which makes exact-match tests brittle).
export function formatNumberSpaced(n, digits = 0) {
  if (n == null || Number.isNaN(n)) return DASH;
  const sign = n < 0 ? "-" : "";
  const fixed = Math.abs(n).toFixed(digits);
  const [intPart, decPart] = fixed.split(".");
  const grouped = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return `${sign}${grouped}${decPart ? "," + decPart : ""}`;
}

export function formatMoneySpaced(n, currency = "USD", digits = 2) {
  if (n == null || Number.isNaN(n)) return DASH;
  const sign = n < 0 ? "-" : "";
  const body = formatNumberSpaced(Math.abs(n), digits);
  const { prefix = "", suffix = "" } = currencyParts(currency);
  return `${sign}${prefix}${body}${suffix}`;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- format`
Expected: PASS (all format tests, new and existing).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/format.js frontend/src/lib/format.test.js
git commit -m "feat(frontend): add space-grouped number/money formatters"
```

---

## Task 5: KpiBox component (TDD)

**Files:**
- Create: `frontend/src/components/ui/KpiBox.jsx`
- Modify: `frontend/src/components/ui/index.js`
- Test: `frontend/src/components/ui/KpiBox.test.jsx`

**Interfaces:**
- Consumes: `useCountUp` (`hooks/useCountUp.js`), `SpotlightCard`
  (`components/reactbits/SpotlightCard.jsx`), `InfoIcon`
  (exported from `components/MetricCard.jsx`).
- Produces: `KpiBox({ label, value, format?, sub?, subTone?, delta?,
  deltaTone?, icon?, info?, animate?=true, className? })` — named **and** default
  export. When `value` is a finite number and `format` is given, the value
  animates via `useCountUp` and is rendered as `format(current)`. When `value`
  is a string it renders verbatim (no count-up). `deltaTone`/`subTone` ∈
  `'gain'|'loss'|'muted'`. Never truncates (uses `break-words`).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/ui/KpiBox.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { KpiBox } from "./KpiBox";
import { formatNumberSpaced } from "../../lib/format";

describe("KpiBox", () => {
  it("renders the label and a preformatted string value", () => {
    render(<KpiBox label="P/E (TTM)" value="24.3" />);
    expect(screen.getByText("P/E (TTM)")).toBeInTheDocument();
    expect(screen.getByText("24.3")).toBeInTheDocument();
  });

  it("formats a numeric value (animation off for determinism)", () => {
    render(
      <KpiBox
        label="Market Cap"
        value={1234567}
        format={(n) => formatNumberSpaced(Math.round(n), 0)}
        animate={false}
      />,
    );
    expect(screen.getByText("1 234 567")).toBeInTheDocument();
  });

  it("renders a delta pill", () => {
    render(<KpiBox label="Change" value="—" delta="+2.10%" deltaTone="gain" />);
    expect(screen.getByText("+2.10%")).toBeInTheDocument();
  });

  it("shows a dash for null values", () => {
    render(<KpiBox label="Beta" value={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test -- KpiBox`
Expected: FAIL — `KpiBox` module does not exist.

- [ ] **Step 3: Implement `KpiBox.jsx`**

```jsx
import { useCountUp } from "../../hooks/useCountUp";
import SpotlightCard from "../reactbits/SpotlightCard";
import { InfoIcon } from "../MetricCard";

// Premium KPI tile: rounded glass/neumorphic surface, warm spotlight hover
// glow, animated count-up for numeric values, generous spacing, never
// truncates. `value` may be a finite number (animated + formatted via
// `format`) or a preformatted string (rendered verbatim).
export function KpiBox({
  label,
  value,
  format,
  sub,
  subTone = "muted",
  delta,
  deltaTone = "muted",
  icon: Icon,
  info,
  animate = true,
  className = "",
}) {
  const isNum = typeof value === "number" && Number.isFinite(value);
  const counted = useCountUp(isNum ? value : 0, { enabled: animate && isNum });
  const display = isNum
    ? format
      ? format(counted)
      : String(Math.round(counted))
    : value == null
      ? "—"
      : value;

  const tone = (t) =>
    t === "gain" ? "text-gain" : t === "loss" ? "text-loss" : "text-muted";

  return (
    <SpotlightCard className={`rounded-2xl ${className}`}>
      <div className="relative flex flex-col gap-1.5 rounded-2xl bg-surface-card-elevated border border-hairline px-4 py-3.5 shadow-[var(--shadow-ambient)] transition-transform duration-200 hover:-translate-y-0.5 min-w-0">
        {Icon && (
          <span className="absolute top-3.5 right-3.5 grid place-items-center w-7 h-7 rounded-xl bg-brand/10 text-brand">
            <Icon size={14} />
          </span>
        )}
        <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
          {label}
          <InfoIcon info={info} />
        </span>
        <span className="text-2xl font-display font-bold tabular-nums tracking-tight text-ink break-words leading-tight">
          {display}
        </span>
        {sub != null && (
          <span className={`text-[13px] font-semibold tabular-nums ${tone(subTone)}`}>
            {sub}
          </span>
        )}
        {delta != null && (
          <span
            className={`inline-flex w-fit items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums ${
              deltaTone === "gain"
                ? "bg-gain/10 text-gain"
                : deltaTone === "loss"
                  ? "bg-loss/10 text-loss"
                  : "bg-muted/10 text-muted"
            }`}
          >
            {delta}
          </span>
        )}
      </div>
    </SpotlightCard>
  );
}

export default KpiBox;
```

- [ ] **Step 4: Export from the ui barrel** — add to `frontend/src/components/ui/index.js`:

```js
export { KpiBox } from "./KpiBox";
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `npm test -- KpiBox`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/ui/KpiBox.jsx frontend/src/components/ui/index.js frontend/src/components/ui/KpiBox.test.jsx
git commit -m "feat(frontend): add reusable premium KpiBox component"
```

---

## Task 6: Stock Detail — QuickStats + 52-week range → KPI boxes

**Files:**
- Modify: `frontend/src/components/StockDetail.jsx` (`QuickStat` ~lines 1203-1210;
  `sections.quickStats` ~876-886; `sections.weekRange` ~888-908)

**Interfaces:**
- Consumes: `KpiBox` (`components/ui`), `formatNumberSpaced`/`formatMoneySpaced`
  (`lib/format`).

- [ ] **Step 1: Add the import at the top of `StockDetail.jsx`**

Add to the existing import block:

```jsx
import { KpiBox } from "./ui";
```

(The `formatNumberSpaced`/`formatMoneySpaced` helpers are exercised through
`KpiBox` and its test; Stock Detail passes preformatted strings here, so no
direct import is needed in this file.)

- [ ] **Step 2: Replace the `quickStats` section** (grid of six `QuickStat`) with a KPI-box grid that never truncates

Replace the `quickStats:` value with:

```jsx
    quickStats: (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <KpiBox label="Market Cap" value={fmtCompact(data.market_cap, cs)} />
        <KpiBox label="P/E (TTM)" value={fmtRatio(ratios.pe)} />
        <KpiBox label="EPS (TTM)" value={ttm.eps != null ? `${cs}${ttm.eps.toFixed(2)}` : "—"} />
        <KpiBox label="Div Yield" value={ratios.div_yield != null ? `${ratios.div_yield.toFixed(2)}%` : "—"} />
        <KpiBox label="Beta" value={fmtRatio(data.beta)} />
        <KpiBox label="EV/EBITDA" value={fmtRatio(ratios.ev_ebitda)} />
      </div>
    ),
```

- [ ] **Step 3: Replace the `weekRange` section** — wrap the existing range bar in a premium `.card` and spell out the numbers with spacing

Replace the `weekRange:` value with:

```jsx
    weekRange: range ? (
      <div className="card !bg-surface-card-elevated px-5 py-4">
        <div className="flex items-center justify-between text-[10px] text-muted uppercase tracking-wider mb-2">
          <span>52-Week Range</span>
          {data.fifty_day_avg != null && (
            <span>
              50D Avg {cs}{data.fifty_day_avg.toFixed(2)} · 200D Avg{" "}
              {data.two_hundred_day_avg?.toFixed(2) ?? "—"}
            </span>
          )}
        </div>
        <div className="relative h-2.5 bg-surface-hover rounded-full">
          <div
            className="absolute top-0 h-2.5 w-1.5 bg-brand rounded"
            style={{ left: `calc(${range.pct}% - 3px)` }}
          />
        </div>
        <div className="flex items-center justify-between text-xs mt-2 tabular-nums">
          <span className="text-loss">{cs}{range.lo.toFixed(2)}</span>
          <span className="text-muted">Current {cs}{data.price.toFixed(2)}</span>
          <span className="text-gain">{cs}{range.hi.toFixed(2)}</span>
        </div>
      </div>
    ) : null,
```

- [ ] **Step 4: Delete the now-unused `QuickStat` component**

Remove the `function QuickStat({ label, value }) { ... }` definition (~lines
1203-1210). Confirm no other references remain:

Run: `cd frontend && npx rg -n "QuickStat" src/`
Expected: no matches.

- [ ] **Step 5: Verify build + tests**

Run: `npm run build && npm test`
Expected: build succeeds; tests pass (incl. `StockDetail.divgrowth.test`).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/StockDetail.jsx
git commit -m "feat(frontend): Stock Detail quick stats + 52w range as premium KPI boxes"
```

---

## Task 7: Stock Detail — ratios table → KPI-box grid

**Files:**
- Modify: `frontend/src/components/StockDetail.jsx` (`sections.ratiosAnalyst`
  left column ~lines 975-1014; keep the Analyst/Price-target/About right column
  as-is)

**Interfaces:**
- Consumes: `KpiBox`, existing `RATIO_ROWS`, `fmtPctValue`, `fmtRatio`,
  `fmtSignedNumber`, `ratios`, `sector`.

- [ ] **Step 1: Replace the "Valuation & Quality" table card** (the left column,
  the `<div className="bg-surface rounded-lg p-4">` that renders the `Metric /
  Value / Sector / Δ` header and maps `RATIO_ROWS` through `RatioRow`) with a
  KPI-box grid. Each ratio becomes its own box: label, big value, and a
  `Sector · Δ` sub-line whose color follows the same `lowerIsBetter` logic.

Replace that left-column `<div>...</div>` with:

```jsx
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-muted uppercase tracking-wider">
              Valuation & Quality
            </h3>
            {sector.sample_size > 0 && (
              <span className="text-[10px] text-muted">
                Sector = median of {sector.sample_size} {data.sector}
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {RATIO_ROWS.map((r) => {
              const fmt = r.pct ? fmtPctValue : fmtRatio;
              const year = r.yearKey ? ratios[r.yearKey] : null;
              const label =
                r.labelYearSuffix && year != null ? `${r.label} (${year})` : r.label;
              const value = ratios[r.key];
              const sectorVal = r.noSector ? null : sector[r.key];
              const delta = value != null && sectorVal != null ? value - sectorVal : null;
              const favourable =
                delta == null ? null : r.lowerIsBetter ? delta < 0 : delta > 0;
              const subTone = favourable == null ? "muted" : favourable ? "gain" : "loss";
              const sub =
                sectorVal == null
                  ? "No sector"
                  : `Sector ${fmt(sectorVal)} · Δ ${delta == null ? "—" : fmtSignedNumber(delta, 2)}`;
              return (
                <KpiBox
                  key={r.key}
                  label={label}
                  value={fmt(value)}
                  sub={sub}
                  subTone={subTone}
                  info={{ title: label, what: r.tooltip }}
                />
              );
            })}
          </div>
        </div>
```

Note: the outer `ratiosAnalyst` grid keeps its `grid-cols-1 xl:grid-cols-2`
wrapper — this replaces only the left column; the right column (Analyst Rating,
Price Targets, About) stays exactly as it is.

- [ ] **Step 2: Verify build + tests**

Run: `npm run build && npm test`
Expected: build succeeds; tests pass.

- [ ] **Step 3: Visual check** — open a stock (e.g. `http://localhost:5173/stock/AAPL`),
confirm the ratios render as a readable grid of KPI boxes with hover tooltips
(the `info` (i) icon) and sector/Δ sub-lines colored correctly.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/StockDetail.jsx
git commit -m "feat(frontend): Stock Detail ratios as premium KPI-box grid"
```

---

## Task 8: Stock Detail — hero header, ownership stats, dividend tiles, section reveals

**Files:**
- Modify: `frontend/src/components/StockDetail.jsx` (`StockOverview` header
  ~1130-1189 and the section render loop ~1191-1198; `OwnershipStat` ~1919-1926;
  `DividendGrowthSection` tiles ~800-809)

**Interfaces:**
- Consumes: `KpiBox`, `ShinyText` (`components/reactbits/ShinyText`), `Reveal`
  (`components/reactbits/Reveal`).

- [ ] **Step 1: Add imports** to `StockDetail.jsx`:

```jsx
import ShinyText from "./reactbits/ShinyText";
import Reveal from "./reactbits/Reveal";
```

- [ ] **Step 2: Premiumize the header price block.** In the `StockOverview`
header, replace the right-hand price `<div className="text-right">...</div>`
(the one holding `data.price` and the change line) with a compact hero KPI:

```jsx
          <div className="text-right rounded-2xl bg-surface-card-elevated border border-hairline px-4 py-2.5 shadow-[var(--shadow-ambient)]">
            <div className="text-2xl font-display font-bold tabular-nums text-ink">
              {data.price != null ? `${cs}${data.price.toFixed(2)}` : "—"}
            </div>
            {priceChange != null && (
              <div
                className={`text-sm font-semibold flex items-center justify-end gap-1 ${priceUp ? "text-gain" : "text-loss"}`}
              >
                {priceUp ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                {data.change != null && `${data.change >= 0 ? "+" : ""}${data.change.toFixed(2)} `}
                ({fmtPct(priceChange)})
              </div>
            )}
          </div>
```

- [ ] **Step 3: Add a subtle shine to the ticker heading.** Replace the ticker
`<h2 className="text-2xl font-bold font-mono">{data.ticker}</h2>` with:

```jsx
            <h2 className="text-2xl font-bold font-mono">
              <ShinyText text={data.ticker} speed={5} />
            </h2>
```

- [ ] **Step 4: Reveal each section on scroll.** In the section render loop at
the bottom of `StockOverview`, wrap each rendered section in `Reveal`:

```jsx
      <div className="p-6 space-y-6">
        {reportConfig.config.order.map((id, i) => {
          if (!reportConfig.isVisible(id)) return null;
          const content = sections[id];
          if (!content) return null;
          return (
            <Reveal key={id} delay={Math.min(i, 6) * 40}>
              {content}
            </Reveal>
          );
        })}
      </div>
```

- [ ] **Step 5: Convert `OwnershipStat` to a KPI box.** Replace the
`OwnershipStat` component body with:

```jsx
function OwnershipStat({ label, value }) {
  return <KpiBox label={label} value={value} />;
}
```

- [ ] **Step 6: Convert the dividend-history tiles to KPI boxes.** In
`DividendGrowthSection`, replace the `.map` over `tiles` (the
`<div key={t.label} className="rounded-lg border ...">` block) with:

```jsx
        {tiles.map((t) => (
          <KpiBox key={t.label} label={t.label} value={t.value} />
        ))}
```

- [ ] **Step 7: Verify build + tests**

Run: `npm run build && npm test`
Expected: build succeeds; tests pass (incl. `StockDetail.divgrowth.test`, which
renders `DividendGrowthSection` — confirm it still finds the tile labels/values).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/StockDetail.jsx
git commit -m "feat(frontend): Stock Detail hero header, KPI ownership/dividend tiles, section reveals"
```

---

## Task 9: MetricCard premium upgrade (global rollout)

**Files:**
- Modify: `frontend/src/components/MetricCard.jsx`

**Interfaces:**
- Consumes: `SpotlightCard` (`components/reactbits/SpotlightCard`).
- Produces: **unchanged public API** — `MetricCard({ icon, label, value, sub,
  positive, negative, loading, info })` and the existing `InfoIcon` export must
  both remain, so the 8 call sites (Dashboard, Overview via PortfolioHero,
  Analytics, Dividends, Options, Cash, TaxReport, Polymarket) need no edits.

- [ ] **Step 1: Rewrite `MetricCard`'s wrapper** to add the spotlight glow, a
rounded-2xl premium surface, and a hover lift — keeping `InfoIcon` and the same
props/markup for label/value/sub. Replace the `MetricCard` function (keep the
`InfoIcon` component above it and the `export { InfoIcon }` below it unchanged):

```jsx
export default function MetricCard({ icon: Icon, label, value, sub, positive, negative, loading, info }) {
  const subColor = positive ? "text-gain" : negative ? "text-loss" : "text-muted";

  return (
    <SpotlightCard className="rounded-2xl">
      <div className="relative flex flex-col gap-1 min-w-0 rounded-2xl bg-surface-card-elevated border border-hairline p-5 shadow-[var(--shadow-ambient)] transition-transform duration-200 hover:-translate-y-0.5">
        {Icon && (
          <span className="absolute top-4 right-4 grid place-items-center w-7 h-7 rounded-xl bg-brand/10 text-brand">
            <Icon size={14} />
          </span>
        )}
        <span className="eyebrow flex items-center gap-1.5">
          {label}
          <InfoIcon info={info} />
        </span>
        {loading ? (
          <div className="h-8 w-28 bg-surface-hover rounded animate-pulse mt-1" />
        ) : (
          <span className="text-2xl font-display font-bold tabular-nums break-words tracking-tight text-ink">
            {value}
          </span>
        )}
        {sub && !loading && (
          <span className={`text-[13px] font-semibold tabular-nums ${subColor}`}>{sub}</span>
        )}
      </div>
    </SpotlightCard>
  );
}
```

Add the import at the top of the file:

```jsx
import SpotlightCard from "./reactbits/SpotlightCard";
```

Note the deliberate change from the original `truncate` on the value to
`break-words` so long values stay fully visible (per the readability brief).

- [ ] **Step 2: Verify build + tests**

Run: `npm run build && npm test`
Expected: build succeeds; **all** tests pass, especially
`PortfolioHero.test.jsx` and `Overview.test.jsx` (they render `MetricCard`). If
either asserts on the removed `truncate` class or the old DOM shape, update the
assertion to match the new markup — do **not** revert the premium change.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/MetricCard.jsx
git commit -m "feat(frontend): premium MetricCard (spotlight glow, no truncation) — global rollout"
```

---

## Task 10: Dashboard + Overview showcase polish

**Files:**
- Modify: `frontend/src/pages/Dashboard.jsx`
- Modify: `frontend/src/pages/Overview.jsx`

**Interfaces:**
- Consumes: `Reveal`, `ShinyText` (`components/reactbits/*`).

- [ ] **Step 1: Read both pages first** to place the wrappers correctly:

Run: `cd frontend && npx rg -n "return \\(|<h1|<h2|grid" src/pages/Dashboard.jsx src/pages/Overview.jsx | head -40`

- [ ] **Step 2: Dashboard** — add `import Reveal from "../components/reactbits/Reveal";`
and wrap the top-level metric grid (the first `MetricCard`/KPI grid returned by
the page) in `<Reveal> ... </Reveal>`. If the page renders multiple stacked
sections (charts, tables), wrap each major section in its own `<Reveal delay={n*40}>`
with increasing `n`. Do not wrap individual chart internals — only section-level
containers, to keep motion subtle.

- [ ] **Step 3: Overview** — add `import Reveal from "../components/reactbits/Reveal";`
(and `import ShinyText from "../components/reactbits/ShinyText";` if the page has
a hero portfolio title). Wrap the page's main heading value/title in `ShinyText`
if one exists, and wrap the metric grid + each subsequent section in `Reveal` as
in Step 2.

- [ ] **Step 4: Verify build + tests**

Run: `npm run build && npm test`
Expected: build succeeds; tests pass. If `Overview.test.jsx` queries the hero
title by exact text and `ShinyText` splits it, keep the title as a single
`text` prop (ShinyText renders it in one `<span>`, so `getByText` still matches);
if a test breaks, prefer adjusting the wrapper over changing the test's intent.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Dashboard.jsx frontend/src/pages/Overview.jsx
git commit -m "feat(frontend): reveal-on-scroll + hero shine on Dashboard/Overview"
```

---

## Task 11: Full verification + visual QA

**Files:** none (verification only).

- [ ] **Step 1: Clean build**

Run: `cd frontend && npm run build`
Expected: succeeds with no errors.

- [ ] **Step 2: Full test suite**

Run: `cd frontend && npm test`
Expected: all suites pass. Record the pass count.

- [ ] **Step 3: Contrast verification** — confirm the retuned tokens clear WCAG
AA on the `#F3E8DA` card. Check `--muted #6B6353`, `--gain #5B7A4C`,
`--loss #B8543A`, `--brand #6D7048` (and white text on `--brand` for buttons).
Use any contrast tool. If `--gain` measures below 4.5:1 for its small-text uses,
darken it to `#4F6B41` in `NEU_TOKENS.gain` and re-run build; note the change.

- [ ] **Step 4: Playwright visual QA.** Ensure dev servers run (`start.bat`).
Drive `http://localhost:5173`, log in with `snowball-dev`. Screenshot and
confirm on **Stock Detail** (`/stock/AAPL`) and **Dashboard** (`/`):
  - warm cream glass background, soft rounded cards, spotlight glow on card hover;
  - every Stock Detail metric in its own rounded KPI box (quick stats + ratios);
  - all text visible and readable, numbers spaced (no clipped/truncated values);
  - sections fade/lift in on scroll; the Sidebar **Premium** style is selected.

- [ ] **Step 5: Final commit (if any tweaks from Steps 3-4)**

```bash
git add -A
git commit -m "fix(frontend): premium redesign contrast/QA tweaks"
```

---

## Self-Review (completed by plan author)

- **Spec coverage:** palette→tokens (T2), background/glass hybrid (T2/T3),
  KPI boxes on Stock Detail (T6/T7/T8), react-bits usage (T1), spaced numbers
  (T4/T5), global rollout via MetricCard (T9), showcase (T10), light-only +
  Premium default + relabel (T2), verification incl. contrast (T11). ✓
- **No new dependencies:** confirmed — SpotlightCard/ShinyText/Reveal are
  dependency-free; count-up reuses `useCountUp`. ✓
- **Type/name consistency:** `KpiBox`, `SpotlightCard`, `ShinyText`, `Reveal`,
  `formatNumberSpaced`, `formatMoneySpaced`, `theme-premium`,
  `sb_premium_default_v1` used consistently across tasks. `InfoIcon` reused from
  `MetricCard` (already exported there). ✓
- **Risk note:** Tasks 9/10 may require updating existing test assertions to the
  new markup — instructions say adjust the assertion to the new premium markup,
  never revert the feature.
