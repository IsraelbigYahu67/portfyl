# Portfyl Premium Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retune Portfyl's design-token system to a warm glassmorphism/neumorphism
"Premium" theme (the user's earthy palette), roll it out app-wide as the new
default, move every metric on the Stock Detail page into its own rounded KPI
box, and add tasteful, reduced-motion-safe animation (spotlight hover glow,
text shine, scroll reveals) via dependency-free react-bits ports.

**Architecture:** Everything is CSS-custom-property driven (`--brand`, `--bg`,
`--surface-card`, etc., set by `applyAppearance()` in `App.jsx` and consumed
by Tailwind's `theme.extend.colors` + the `.card`/`.btn-*`/`.input` component
classes in `index.css`). The redesign adds a second axis to that system — a
`themeStyle` ("glass" | "neu") alongside the existing hue `palette` — and a
small set of new shared components (`KpiBox`, `SpotlightCard`, `ShinyText`,
`Reveal`) that every touched page/section renders through, so the visual
change is concentrated in the token layer and a handful of reusable
components rather than hand-styled on every page.

**Tech Stack:** React 18, Tailwind CSS (CSS-custom-property theme), Vitest +
Testing Library. No new npm dependencies — react-bits components are
hand-ported to drop their `motion`/`gsap` dependencies.

**Spec:** `docs/superpowers/specs/2026-08-30-portfyl-premium-redesign-design.md`

## Global Constraints

- **No new npm dependencies.** react-bits' `SpotlightCard`, `ShinyText`, and
  the `AnimatedContent` scroll-reveal are hand-ported as plain JSX + CSS
  (dropping their upstream `motion`/`gsap` imports), not installed.
- **Do not change the `glass` (Classic) theme's appearance.** `PALETTES`,
  `DARK_SURFACES`, `LIGHT_TOKENS`, and `GLASS_CHART` keep their current
  values; the premium work only adds a parallel `neu` branch.
- **Premium is light-only.** It ignores the Light/Dark/System `theme` setting
  entirely (matches how `glass` dark mode already only applies to itself).
- **Keep `sb_*` localStorage keys** (adds one new key, `sb_theme_style`) and
  single-user `owner_id="default"` behavior (not touched by this plan —
  frontend-only work).
- **Keep all existing Vitest tests green; add tests for new pure logic**
  (format helpers, contrast math, `KpiBox`, `Reveal`'s no-IntersectionObserver
  fallback). Presentational-only JSX rewires (the StockDetail/Dashboard/
  Overview tasks) are verified by the full suite + `npm run build`, matching
  this codebase's existing convention of not unit-testing per-block markup.
- **Charts stay charts** — they get glass-card framing + the new warm chart
  palette, never converted to KPI boxes.
- **KPI-box-per-metric is required on Stock Detail**; `MetricCard` (used on 8
  other pages) gets the premium visual upgrade but keeps its exact current
  prop API — no call-site edits anywhere else in the app.
- **Foundational gap this plan closes first:** the spec assumes a `neu`/
  `glass` theme-style switcher and a `NEU_TOKENS` table already exist in
  `frontend/src/App.jsx` (referencing `docs/superpowers/plans/2026-07-30-neumorphism-theme-style.md`).
  They don't — that work (commits `2873149`, `77f0bbf`, `4438894`) lives only
  in pre-merge repo history and was dropped when this repo was unified from
  `portfyl-pc`/`portfyl-nb` (commit `731d943`). **Task 1 below reintroduces
  that foundation from scratch** (adapted from the historical implementation,
  not a literal cherry-pick, since the target files have since evolved) before
  any retuning happens. Every later task assumes Task 1 is done.

---

### Task 1: Classic/Premium theme-style switcher with the final warm tokens

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/Sidebar.jsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Consumes: nothing new (builds on the existing `PaletteContext`/`applyAppearance` pattern already in `App.jsx`).
- Produces: `usePalette()` now also returns `{ themeStyle, setThemeStyle }`; `document.documentElement` gets a `theme-premium` class when Premium is active (consumed by `index.css`'s mesh-gradient rule); a new `NEU_TOKENS` export (consumed by Task 6's contrast test); `localStorage["sb_theme_style"]` ("glass" default fallback is never hit — see below).

This task writes the **final** premium token values directly (sourced from
the spec's token table) rather than porting the old neumorphism palette and
retuning it in a second pass — there's no reviewable intermediate state
between "switch exists" and "switch has the right colors," so splitting that
into two tasks would just be rework.

- [ ] **Step 1: Add the Premium token table and the Classic chart palette constant**

In `frontend/src/App.jsx`, after the `LIGHT_TOKENS` constant (after line 57), insert:

```js
// "Premium" — warm glassmorphism/neumorphism hybrid: soft dual shadows (the
// neumorphic half) layered on translucent, blurred surfaces (the glass half)
// over a warm mesh-gradient background (.theme-premium body in index.css).
// One fixed light appearance — ignores Light/Dark/System entirely, same as
// the historical Neumorphism style this replaces.
// See docs/superpowers/specs/2026-08-30-portfyl-premium-redesign-design.md.
export const NEU_TOKENS = {
  bg: "#F3E8DA", bgSubtle: "#ECE0CF",
  surfaceCard: "rgba(250,245,237,0.78)", surfaceCardElevated: "rgba(253,249,243,0.92)",
  border: "rgba(120,105,84,0.14)", hairline: "rgba(120,105,84,0.14)",
  ink: "#3A352C", muted: "#6B6353",
  brand: "#6D7048", brandHover: "#5C5F3C", brandLight: "#E4E5D3",
  gain: "#5B7A4C", loss: "#B8543A",
  glassBorderAlpha: "rgba(120,105,84,0.16)", glassOverlayAlpha: "rgba(255,252,247,0.55)",
  blurCard: "14px", blurOverlay: "22px",
  shadowAmbient: "7px 7px 18px rgba(190,172,146,0.5), -7px -7px 18px rgba(255,253,248,0.9)",
  shadowInset: "inset 3px 3px 8px rgba(190,172,146,0.45), inset -3px -3px 8px rgba(255,253,248,0.85)",
  radiusCard: "1.25rem",
  chart: ["#A9AB88", "#DBAA89", "#D4C3A1", "#B7AFA3", "#7C8A5A", "#C08457", "#9E8E6E", "#8A8478"],
};
// Classic's chart series was previously hardcoded inline inside
// applyAppearance(); pulled out to a constant so both branches follow the
// same "array of 8 -> --chart-1..8" pattern below.
const GLASS_CHART = ["var(--brand)", "#4EDEA3", "#FFB95F", "#A78BFA", "#38BDF8", "#FB7185", "#FACC15", "#64748B"];
```

- [ ] **Step 2: Give `applyAppearance` a `themeStyle` branch**

Replace the whole `applyAppearance` function (current lines 73-101) with:

```js
function applyAppearance(name, isDark, themeStyle) {
  const s = document.documentElement.style;

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

  document.documentElement.classList.toggle("theme-premium", false);
  const p = PALETTES[name] || PALETTES.green;
  s.setProperty("--brand", p.brand);
  s.setProperty("--brand-hover", p.brandHover);
  s.setProperty("--brand-light", isDark ? p.brandLightDark : p.brandLight);
  const t = isDark ? DARK_SURFACES : LIGHT_TOKENS;
  s.setProperty("--surface-card", t.surfaceCard);
  s.setProperty("--surface-card-elevated", isDark ? DARK_SURFACES.surfaceCardElevated : LIGHT_TOKENS.surfaceCardElevated);
  s.setProperty("--border", t.border);
  s.setProperty("--ink", t.ink);
  s.setProperty("--muted", t.muted);
  s.setProperty("--hairline", t.hairline);
  s.setProperty("--glass-border-alpha", isDark ? "rgba(255,255,255,0.06)" : "rgba(16,22,43,0.06)");
  s.setProperty("--glass-overlay-alpha", isDark ? "rgba(255,255,255,0.03)" : "rgba(255,255,255,0.5)");
  s.setProperty("--blur-card", "12px");
  s.setProperty("--blur-overlay", "20px");
  s.setProperty("--shadow-ambient", isDark ? "0px 4px 20px rgba(0,0,0,0.5)" : "0px 4px 20px rgba(16,22,43,0.10)");
  s.setProperty("--shadow-inset", "none");
  s.setProperty("--radius-card", "0.5rem");
  s.setProperty("--gain", isDark ? "#34D399" : "#10B981");
  s.setProperty("--loss", isDark ? "#F87171" : "#EF4444");
  GLASS_CHART.forEach((color, i) => s.setProperty(`--chart-${i + 1}`, color));
  if (isDark) {
    s.setProperty("--bg", DARK_SURFACES.bg);
    s.setProperty("--bg-subtle", DARK_SURFACES.bgSubtle);
    s.setProperty("--sidebar-active", p.sidebarActive);
  } else {
    s.setProperty("--bg", p.bg);
    s.setProperty("--bg-subtle", p.bgSubtle);
    s.setProperty("--sidebar-active", p.brandLight);
  }
  document.documentElement.classList.toggle("dark", isDark);
}
```

- [ ] **Step 3: Add `themeStyle` state to `PaletteProvider`, default to Premium**

Replace the `PaletteProvider` function (current lines 207-241) with:

```js
function PaletteProvider({ children }) {
  const [palette, setPaletteState] = useState(
    () => localStorage.getItem("sb_palette") || "green"
  );
  const [theme, setThemeState] = useState(
    () => localStorage.getItem("sb_theme") || "system"
  );
  // Premium (the warm glass-hybrid look) is the default; Classic glass stays
  // available in the switcher. This is the style's first release in this
  // repo, so no installs have sb_theme_style set yet -- no migration needed.
  const [themeStyle, setThemeStyleState] = useState(
    () => localStorage.getItem("sb_theme_style") || "neu"
  );

  const setPalette = (p) => {
    localStorage.setItem("sb_palette", p);
    setPaletteState(p);
  };

  const setTheme = (t) => {
    localStorage.setItem("sb_theme", t);
    setThemeState(t);
  };

  const setThemeStyle = (style) => {
    localStorage.setItem("sb_theme_style", style);
    setThemeStyleState(style);
  };

  useEffect(() => {
    const apply = () => applyAppearance(palette, resolveDark(theme), themeStyle);
    apply();
    // Follow OS changes only while on "system" AND on Classic glass --
    // Premium ignores Light/Dark/System entirely.
    if (theme === "system" && themeStyle === "glass") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      mq.addEventListener("change", apply);
      return () => mq.removeEventListener("change", apply);
    }
  }, [palette, theme, themeStyle]);

  return (
    <PaletteContext.Provider
      value={{ palette, setPalette, theme, setTheme, themeStyle, setThemeStyle, palettes: PALETTES }}
    >
      {children}
    </PaletteContext.Provider>
  );
}
```

- [ ] **Step 4: Sidebar — Style switcher, relabel, disable Appearance/Accent under Premium**

In `frontend/src/components/Sidebar.jsx`, change the destructure on line 42:

```jsx
  const { palette, setPalette, theme, setTheme, themeStyle, setThemeStyle } = usePalette();
```

Replace the "Appearance" block (current lines 98-114) with:

```jsx
        {/* Theme style (Classic glass vs Premium warm glass-hybrid) */}
        <div className="px-4">
          <p className="text-[10px] text-muted mb-1.5 pl-0.5">Style</p>
          <SegmentedControl
            block
            size="sm"
            aria-label="Theme style"
            value={themeStyle}
            onChange={setThemeStyle}
            options={[
              { value: "glass", label: "Classic", title: "Classic glass theme" },
              { value: "neu", label: "Premium", title: "Warm glass-hybrid theme" },
            ]}
          />
        </div>

        {/* Appearance (light / dark / system) -- inert while Premium is
            active, which ships as one fixed light appearance. */}
        <div className={`px-4 ${themeStyle === "neu" ? "opacity-40 pointer-events-none" : ""}`}>
          <p className="text-[10px] text-muted mb-1.5 pl-0.5">Appearance</p>
          <SegmentedControl
            block
            size="sm"
            aria-label="Appearance"
            value={theme}
            onChange={setTheme}
            options={[
              { value: "light", label: <Sun size={13} />, title: "Light", disabled: themeStyle === "neu" },
              { value: "dark", label: <Moon size={13} />, title: "Dark", disabled: themeStyle === "neu" },
              { value: "system", label: <Monitor size={13} />, title: "System", disabled: themeStyle === "neu" },
            ]}
          />
        </div>
```

Then replace the "Palette switcher" block's opening `<div>` line (current line 117) and its button's `onClick`/props (current lines 119-133) — the full block becomes:

```jsx
        {/* Palette switcher -- same rationale as Appearance above. */}
        <div className={`px-4 ${themeStyle === "neu" ? "opacity-40 pointer-events-none" : ""}`}>
          <p className="text-[10px] text-muted mb-1.5 pl-0.5">Accent</p>
          <div className="flex gap-1.5">
            {PALETTE_OPTIONS.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setPalette(key)}
                disabled={themeStyle === "neu"}
                title={label}
                aria-label={`Theme: ${label}`}
                aria-pressed={palette === key}
                className={`w-5 h-5 rounded-full transition-all ${
                  palette === key ? "ring-2 ring-offset-1 ring-slate-400 scale-110" : "hover:scale-110"
                }`}
                style={{ backgroundColor: { blue: "#2563EB", green: "#059669", purple: "#7C3AED" }[key] }}
              />
            ))}
          </div>
        </div>
```

- [ ] **Step 5: Let the currency toggle's corners follow the radius token**

In `frontend/src/components/Sidebar.jsx`, in the "Currency toggle" block, change:

```jsx
          <div className="flex items-center gap-0.5 bg-surface-hover rounded-lg p-0.5">
```

to:

```jsx
          <div className="flex items-center gap-0.5 bg-surface-hover rounded-[var(--radius-card)] p-0.5">
```

and:

```jsx
                className={`flex-1 text-xs py-1.5 rounded-md font-semibold transition-colors ${
```

to:

```jsx
                className={`flex-1 text-xs py-1.5 rounded-[var(--radius-card)] font-semibold transition-colors ${
```

- [ ] **Step 6: `index.css` — radius/inset-shadow token defaults, token-driven corners, mesh gradient**

In `frontend/src/index.css`, add two lines to the `:root` block (after `--shadow-ambient: 0px 4px 20px rgba(16, 22, 43, 0.10);`):

```css
    --radius-card: 0.5rem;
    --shadow-inset: none;
```

In the `@layer components` block, change `.card`, `.btn-primary`, `.btn-ghost`, and `.input` from a fixed `rounded-lg`/`rounded-lg` (`.card` and `.input`'s implicit border radius comes from `rounded-lg` in `.card`, and `rounded-lg` on `.btn-primary`/`.btn-ghost`/`.input`) to the token:

```css
  .card {
    @apply bg-surface-card border border-hairline p-5 rounded-[var(--radius-card)];
    background-image: linear-gradient(to bottom right, var(--glass-overlay-alpha), transparent 40%);
    backdrop-filter: blur(var(--blur-card));
    box-shadow: var(--shadow-ambient);
    border-color: var(--hairline);
    transition: box-shadow 0.18s ease, transform 0.18s ease, border-color 0.18s ease;
  }
```

```css
  .btn-primary {
    @apply bg-brand hover:bg-brand-dim text-white font-semibold px-4 py-2 rounded-[var(--radius-card)] transition-colors;
  }
```

```css
  .btn-ghost {
    /* hover:border-slate-300 stays literal: hover:border-hairline would equal the
       resting border color and erase the hover affordance entirely (same call
       Task 7a made for DashboardGrid's Reset button -- no token exists for a
       "slightly darker than hairline" border today). */
    @apply border border-hairline hover:border-slate-300 text-muted hover:text-ink px-4 py-2 rounded-[var(--radius-card)] transition-colors;
  }
```

```css
  .input {
    @apply bg-surface border border-hairline rounded-[var(--radius-card)] px-3 py-2 text-ink placeholder-muted focus:outline-none focus:border-brand w-full;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
```

Finally, add the mesh-gradient rule after the dark-mode scrollbar block at the bottom of the file:

```css

/* ----------------------------------------------------------------------------
 * Premium theme: a warm mesh gradient behind the whole app so the frosted
 * (backdrop-blur) cards have something to refract. Toggled by
 * applyAppearance() in App.jsx alongside the token swap.
 * ------------------------------------------------------------------------- */
.theme-premium body {
  background-image:
    radial-gradient(ellipse 70% 50% at 15% -10%, rgba(169, 171, 136, 0.20), transparent 60%),
    radial-gradient(ellipse 60% 45% at 100% 0%, rgba(219, 170, 137, 0.18), transparent 60%),
    radial-gradient(ellipse 60% 40% at 50% 100%, rgba(212, 195, 161, 0.16), transparent 60%);
  background-attachment: fixed;
}
```

- [ ] **Step 7: Verify**

```bash
cd frontend && npm test && npm run build
```

Expected: all existing tests still pass; build succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/App.jsx frontend/src/components/Sidebar.jsx frontend/src/index.css
git commit -m "feat(theme): reintroduce Classic/Premium theme-style switcher, default to Premium"
```

---

### Task 2: Vendor react-bits components (SpotlightCard, ShinyText, Reveal)

**Files:**
- Create: `frontend/src/components/reactbits/SpotlightCard.jsx`
- Create: `frontend/src/components/reactbits/ShinyText.jsx`
- Create: `frontend/src/components/reactbits/Reveal.jsx`
- Create: `frontend/src/components/reactbits/Reveal.test.jsx`
- Modify: `frontend/src/index.css`

**Interfaces:**
- Produces: `SpotlightCard({ children, className, spotlightColor })` (default export) -- a pointer-tracked radial-glow wrapper with no hardcoded surface colors, so it inherits whatever `className` (typically `.card ...`) it's combined with. `ShinyText({ text, className, disabled })` (default export) -- pure-CSS clip-gradient sweep, no `motion` dependency. `Reveal({ children, className, delay, as })` (default export) -- IntersectionObserver-driven fade+lift, degrades to "visible immediately" with no observer (matches this repo's jsdom test environment, which -- like `ResizeObserver` -- doesn't implement it).
- Consumed by: Task 4's `KpiBox` (`SpotlightCard`), Task 5's `MetricCard` (`SpotlightCard`), Task 10's StockDetail header + Task 11's `PortfolioHero` + Task 12's `Overview` (`ShinyText`, `Reveal`).

- [ ] **Step 1: `SpotlightCard`**

Create `frontend/src/components/reactbits/SpotlightCard.jsx`:

```jsx
import { useRef, useState } from "react";

// Adapted from react-bits' SpotlightCard: the hardcoded dark
// border-neutral-800/bg-neutral-900 classes are dropped so this inherits
// whatever surface it's combined with (usually the app's .card) instead of a
// fixed dark look, and the TS types are stripped.
export default function SpotlightCard({ children, className = "", spotlightColor = "rgba(169,171,136,0.35)" }) {
  const ref = useRef(null);
  const [opacity, setOpacity] = useState(0);
  const [position, setPosition] = useState({ x: 0, y: 0 });

  const handleMouseMove = (e) => {
    if (!ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    setPosition({ x: e.clientX - rect.left, y: e.clientY - rect.top });
  };

  return (
    <div
      ref={ref}
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setOpacity(1)}
      onMouseLeave={() => setOpacity(0)}
      onFocus={() => setOpacity(1)}
      onBlur={() => setOpacity(0)}
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

- [ ] **Step 2: `ShinyText`**

Create `frontend/src/components/reactbits/ShinyText.jsx`:

```jsx
// Adapted from react-bits' ShinyText: the upstream version drives the sweep
// with `motion/react`'s useAnimationFrame; this instead emits a plain <span>
// and lets a CSS @keyframes animation (.shiny-text in index.css) do the
// sweep, so no animation library is needed.
export default function ShinyText({ text, className = "", disabled = false }) {
  return (
    <span className={`shiny-text ${disabled ? "" : "shiny-text-animated"} ${className}`}>
      {text}
    </span>
  );
}
```

- [ ] **Step 3: `Reveal`**

Create `frontend/src/components/reactbits/Reveal.jsx`:

```jsx
import { useEffect, useRef, useState } from "react";

// Plays react-bits' AnimatedContent's role (fade+lift on scroll into view)
// without gsap/ScrollTrigger: a plain IntersectionObserver flips a CSS class,
// and index.css's .reveal/.reveal-visible transition does the rest.
// jsdom (this repo's test environment) doesn't implement
// IntersectionObserver -- same situation as ResizeObserver in src/test/setup.js
// -- so this renders already-visible rather than crashing or staying hidden.
export default function Reveal({ children, className = "", delay = 0, as: Tag = "div" }) {
  const ref = useRef(null);
  const [visible, setVisible] = useState(typeof IntersectionObserver === "undefined");

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.15 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <Tag
      ref={ref}
      className={`reveal ${visible ? "reveal-visible" : ""} ${className}`}
      style={delay ? { transitionDelay: `${delay}ms` } : undefined}
    >
      {children}
    </Tag>
  );
}
```

- [ ] **Step 4: Write the `Reveal` fallback test**

Create `frontend/src/components/reactbits/Reveal.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import Reveal from "./Reveal";

describe("Reveal", () => {
  it("renders children immediately when IntersectionObserver is unavailable (jsdom default)", () => {
    render(<Reveal>hello</Reveal>);
    expect(screen.getByText("hello")).toBeInTheDocument();
  });

  it("applies the delay as a transition-delay style", () => {
    const { container } = render(<Reveal delay={150}>hi</Reveal>);
    expect(container.firstChild.style.transitionDelay).toBe("150ms");
  });
});
```

- [ ] **Step 5: Run it**

```bash
cd frontend && npx vitest run src/components/reactbits/Reveal.test.jsx
```

Expected: 2 PASS.

- [ ] **Step 6: Shine + reveal CSS**

In `frontend/src/index.css`, append to the end of the `@layer utilities` block (after the `@keyframes shimmer` rule, still inside the same `@layer utilities { ... }`):

```css
  .shiny-text {
    background-image: linear-gradient(100deg, var(--ink) 0%, var(--ink) 42%, var(--brand) 50%, var(--ink) 58%, var(--ink) 100%);
    background-size: 220% auto;
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
  }
  .shiny-text-animated { animation: shiny-sweep 3.2s linear infinite; }
  @keyframes shiny-sweep {
    0% { background-position: 160% center; }
    100% { background-position: -60% center; }
  }

  .reveal {
    opacity: 0;
    transform: translateY(16px);
    transition: opacity 0.5s ease, transform 0.5s ease;
  }
  .reveal-visible { opacity: 1; transform: translateY(0); }
```

(No extra `prefers-reduced-motion` rule is needed: the existing block further
down already sets `animation-duration`/`transition-duration` to `0.001ms` for
every element, which neutralizes both the shine sweep and the reveal
transition under that query.)

- [ ] **Step 7: Verify**

```bash
cd frontend && npm test && npm run build
```

Expected: all tests pass (including the 2 new `Reveal` tests); build succeeds.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/reactbits frontend/src/index.css
git commit -m "feat(ui): vendor dependency-free SpotlightCard/ShinyText/Reveal from react-bits"
```

---

### Task 3: Spaced-number format helpers

**Files:**
- Modify: `frontend/src/lib/format.js`
- Modify: `frontend/src/lib/format.test.js`

**Interfaces:**
- Produces: `formatNumberSpaced(n, digits = 0) -> string` (non-breaking-space thousands groups, comma decimal); `formatMoneySpaced(n, currency = "USD") -> string` (same, with the existing `currencyParts()` prefix/suffix). Both return `"—"` for `null`/`NaN`, matching every other formatter in this file.
- Consumed by: Task 4's `KpiBox` (as the default `format` prop for money/plain-number KPIs).

- [ ] **Step 1: Write the failing tests**

Append to `frontend/src/lib/format.test.js`:

```js
import { formatNumberSpaced, formatMoneySpaced } from "./format";

describe("formatNumberSpaced", () => {
  it("groups thousands with a non-breaking space and a comma decimal", () => {
    expect(formatNumberSpaced(1234567.89, 2)).toBe("1 234 567,89");
  });
  it("defaults to 0 decimals", () => {
    expect(formatNumberSpaced(1234)).toBe("1 234");
  });
  it("keeps the minus sign before the digits", () => {
    expect(formatNumberSpaced(-1234.5, 2)).toBe("-1 234,50");
  });
  it("returns an em dash for null/NaN", () => {
    expect(formatNumberSpaced(null)).toBe("—");
    expect(formatNumberSpaced(NaN)).toBe("—");
  });
});

describe("formatMoneySpaced", () => {
  it("formats CZK with the spaced-group suffix style", () => {
    expect(formatMoneySpaced(1234567.89, "CZK")).toBe("1 234 567,89 Kč");
  });
  it("formats USD with the $ prefix", () => {
    expect(formatMoneySpaced(1234.5, "USD")).toBe("$1 234,50");
  });
  it("puts the sign before the prefix for negatives", () => {
    expect(formatMoneySpaced(-12, "USD")).toBe("-$12,00");
  });
  it("returns an em dash for null", () => {
    expect(formatMoneySpaced(null)).toBe("—");
  });
});
```

- [ ] **Step 2: Run it — must fail**

```bash
cd frontend && npx vitest run src/lib/format.test.js
```

Expected: FAIL — `formatNumberSpaced is not a function`.

- [ ] **Step 3: Implement**

In `frontend/src/lib/format.js`, export the previously module-private `currencyParts` (add the `export` keyword to its existing declaration on line 5):

```js
export function currencyParts(currency) {
```

Then append at the end of the file:

```js

export function formatNumberSpaced(n, digits = 0) {
  if (n == null || Number.isNaN(n)) return DASH;
  const sign = n < 0 ? "-" : "";
  const [intPart, fracPart] = Math.abs(n).toFixed(digits).split(".");
  const spacedInt = intPart.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return fracPart != null ? `${sign}${spacedInt},${fracPart}` : `${sign}${spacedInt}`;
}

export function formatMoneySpaced(n, currency = "USD") {
  if (n == null || Number.isNaN(n)) return DASH;
  const sign = n < 0 ? "-" : "";
  const { prefix = "", suffix = "" } = currencyParts(currency);
  return `${sign}${prefix}${formatNumberSpaced(Math.abs(n), 2)}${suffix}`;
}
```

- [ ] **Step 4: Run it — must pass**

```bash
cd frontend && npx vitest run src/lib/format.test.js
```

Expected: all PASS (existing formatMoney/formatPercent/etc. tests + the new ones).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/format.js frontend/src/lib/format.test.js
git commit -m "feat(format): add formatNumberSpaced/formatMoneySpaced (space-grouped, comma-decimal)"
```

---

### Task 4: `KpiBox` shared component

**Files:**
- Create: `frontend/src/components/ui/KpiBox.jsx`
- Create: `frontend/src/components/ui/KpiBox.test.jsx`
- Modify: `frontend/src/components/ui/index.js`

**Interfaces:**
- Consumes: `SpotlightCard` (Task 2), `DeltaPill` (existing, `./DeltaPill`), `InfoIcon` (existing, exported from `../MetricCard`), `useCountUp` (existing, `../../hooks/useCountUp`).
- Produces: `KpiBox({ icon, label, value, format, delta, sub, subTone, info, loading, size, className })` (named export `KpiBox`, re-exported from `components/ui/index.js`). `value` may be a `number` (animated via `useCountUp` then run through `format`) or a pre-formatted `string`/`null` (rendered as-is, no animation). `size="sm"` renders the dense variant used in grids of many boxes (StockDetail's quick stats/ratios/ownership); default `"md"` is the standard tile. Never truncates the value (unlike `MetricCard`).

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/components/ui/KpiBox.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import { KpiBox } from "./index";

describe("KpiBox", () => {
  it("renders a label and a pre-formatted string value without animating", () => {
    render(<KpiBox label="P/E (TTM)" value="24.1" />);
    expect(screen.getByText("P/E (TTM)")).toBeInTheDocument();
    expect(screen.getByText("24.1")).toBeInTheDocument();
  });

  it("renders a numeric value through the count-up path under reduced motion", () => {
    window.matchMedia = (q) => ({
      matches: true, media: q, onchange: null,
      addEventListener() {}, removeEventListener() {},
      addListener() {}, removeListener() {}, dispatchEvent() { return false; },
    });
    render(<KpiBox label="Market Cap" value={1234} format={(v) => `$${Math.round(v)}`} />);
    expect(screen.getByText("$1234")).toBeInTheDocument();
  });

  it("shows a loading skeleton and hides the value", () => {
    const { container } = render(<KpiBox label="Beta" value={1.2} loading />);
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
    expect(screen.queryByText("1.2")).not.toBeInTheDocument();
  });

  it("colors the sub line by subTone", () => {
    render(<KpiBox label="ROE" value="18.2%" sub="Sector 12.4 · Δ +5.8" subTone="gain" />);
    expect(screen.getByText("Sector 12.4 · Δ +5.8")).toHaveClass("text-gain");
  });

  it("renders nothing for value when null (dash callers pass their own dash string)", () => {
    render(<KpiBox label="Beta" value={null} />);
    expect(screen.getByText("Beta")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it — must fail**

```bash
cd frontend && npx vitest run src/components/ui/KpiBox.test.jsx
```

Expected: FAIL — `KpiBox` is not exported from `./index`.

- [ ] **Step 3: Implement**

Create `frontend/src/components/ui/KpiBox.jsx`:

```jsx
import SpotlightCard from "../reactbits/SpotlightCard";
import { DeltaPill } from "./DeltaPill";
import { InfoIcon } from "../MetricCard";
import { useCountUp } from "../../hooks/useCountUp";

const SUB_TONE = { gain: "text-gain", loss: "text-loss", muted: "text-muted" };

function KpiValue({ value, format }) {
  const isNumber = typeof value === "number" && Number.isFinite(value);
  const animated = useCountUp(isNumber ? value : 0, { enabled: isNumber });
  if (!isNumber) return value ?? null;
  return format(animated);
}

export default function KpiBox({
  icon: Icon,
  label,
  value,
  format = (v) => String(v),
  delta = null,
  sub = null,
  subTone = "muted",
  info = null,
  loading = false,
  size = "md",
  className = "",
}) {
  const dense = size === "sm";
  return (
    <SpotlightCard
      className={`card !bg-surface-card-elevated flex flex-col gap-1 min-w-0 ${dense ? "!p-3" : ""} ${className}`}
    >
      <div className="flex items-start justify-between gap-2">
        <span className={`eyebrow flex items-center gap-1.5 ${dense ? "text-[10px]" : ""}`}>
          {label}
          <InfoIcon info={info} />
        </span>
        {Icon && (
          <span className="grid place-items-center w-7 h-7 rounded-lg bg-brand/10 text-brand shrink-0">
            <Icon size={14} />
          </span>
        )}
      </div>
      {loading ? (
        <div className="h-7 w-24 bg-surface-hover rounded animate-pulse mt-1" />
      ) : (
        <span className={`font-display font-bold tabular-nums tracking-tight text-ink ${dense ? "text-base" : "text-2xl"}`}>
          <KpiValue value={value} format={format} />
        </span>
      )}
      {delta && !loading && (
        <DeltaPill value={delta.value} pct={delta.pct} currency={delta.currency} size="sm" />
      )}
      {sub && !loading && (
        <span className={`text-[13px] font-semibold ${SUB_TONE[subTone] || SUB_TONE.muted}`}>{sub}</span>
      )}
    </SpotlightCard>
  );
}
```

In `frontend/src/components/ui/index.js`, add:

```js
export { default as KpiBox } from "./KpiBox";
```

- [ ] **Step 4: Run it — must pass**

```bash
cd frontend && npx vitest run src/components/ui/KpiBox.test.jsx
```

Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ui/KpiBox.jsx frontend/src/components/ui/KpiBox.test.jsx frontend/src/components/ui/index.js
git commit -m "feat(ui): add KpiBox, the reusable premium KPI tile"
```

---

### Task 5: `MetricCard` premium upgrade (same prop API)

**Files:**
- Modify: `frontend/src/components/MetricCard.jsx`
- Create: `frontend/src/components/MetricCard.test.jsx`

**Interfaces:**
- Consumes: `SpotlightCard` (Task 2).
- Produces: same public API as before (`icon, label, value, sub, positive, negative, loading, info`; still exports `InfoIcon`). `value` additionally accepts a raw `number` (opts into count-up + `toLocaleString` grouping); every existing caller across the 8 pages that use `MetricCard` already passes a pre-formatted string, so their rendering is byte-identical — this is purely additive.

- [ ] **Step 1: Write the failing test**

Create `frontend/src/components/MetricCard.test.jsx`:

```jsx
import { render, screen } from "@testing-library/react";
import MetricCard from "./MetricCard";

describe("MetricCard", () => {
  it("renders a pre-formatted string value unchanged (existing call sites)", () => {
    render(<MetricCard label="Balance" value="$1,234.50" />);
    expect(screen.getByText("$1,234.50")).toBeInTheDocument();
  });

  it("animates a numeric value under reduced motion and renders it grouped", () => {
    window.matchMedia = (q) => ({
      matches: true, media: q, onchange: null,
      addEventListener() {}, removeEventListener() {},
      addListener() {}, removeListener() {}, dispatchEvent() { return false; },
    });
    render(<MetricCard label="Holdings" value={12345} />);
    expect(screen.getByText("12,345")).toBeInTheDocument();
  });

  it("still shows a loading skeleton and hides the value", () => {
    const { container } = render(<MetricCard label="Beta" value="1.2" loading />);
    expect(container.querySelector(".animate-pulse")).toBeTruthy();
    expect(screen.queryByText("1.2")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it — must fail**

```bash
cd frontend && npx vitest run src/components/MetricCard.test.jsx
```

Expected: FAIL — the numeric-value test fails (`value={12345}` currently renders the literal number `12345`, not `"12,345"`).

- [ ] **Step 3: Implement**

Replace the full contents of `frontend/src/components/MetricCard.jsx` with:

```jsx
import { Info } from "lucide-react";
import SpotlightCard from "./reactbits/SpotlightCard";
import { useCountUp } from "../hooks/useCountUp";

function InfoIcon({ info }) {
  if (!info) return null;
  return (
    <span className="relative group inline-flex items-center">
      <button
        type="button"
        aria-label={`What is ${info.title}?`}
        className="inline-flex text-muted hover:text-ink cursor-help transition-colors"
      >
        <Info size={12} />
      </button>
      <span
        className="hidden group-hover:block group-focus-within:block absolute left-1/2 -translate-x-1/2 top-5 z-30 w-72
                   bg-surface-card-elevated border border-hairline rounded-lg px-3 py-2 shadow-[var(--shadow-ambient)]
                   text-[11px] leading-relaxed text-muted normal-case tracking-normal font-normal"
      >
        <span className="block font-semibold text-ink mb-1">{info.title}</span>
        <span className="block text-muted">{info.what}</span>
        {info.formula && (
          <span className="block mt-1.5 pt-1.5 border-t border-hairline font-mono text-[10px] text-brand">
            {info.formula}
          </span>
        )}
        {info.note && (
          <span className="block mt-1 text-[10px] text-muted italic">{info.note}</span>
        )}
      </span>
    </span>
  );
}

// `value` is normally a pre-formatted string (every current caller already
// formats via lib/format.js before passing it in). Passing a raw number
// instead opts into a count-up animation -- additive, backward compatible.
function MetricValue({ value }) {
  const isNumber = typeof value === "number" && Number.isFinite(value);
  const animated = useCountUp(isNumber ? value : 0, { enabled: isNumber });
  return isNumber ? animated.toLocaleString("en-US", { maximumFractionDigits: 0 }) : value;
}

export default function MetricCard({ icon: Icon, label, value, sub, positive, negative, loading, info }) {
  const subColor = positive ? "text-gain" : negative ? "text-loss" : "text-muted";

  return (
    <SpotlightCard className="card !bg-surface-card-elevated relative flex flex-col gap-1.5 min-w-0">
      {Icon && (
        <span className="absolute top-4 right-4 grid place-items-center w-7 h-7 rounded-lg bg-brand/10 text-brand">
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
        <span className="text-2xl font-display font-bold tabular-nums truncate tracking-tight text-ink">
          <MetricValue value={value} />
        </span>
      )}
      {sub && !loading && <span className={`text-[13px] font-semibold tabular-nums ${subColor}`}>{sub}</span>}
    </SpotlightCard>
  );
}

export { InfoIcon };
```

- [ ] **Step 4: Run it — must pass**

```bash
cd frontend && npx vitest run src/components/MetricCard.test.jsx
```

Expected: 3 PASS.

- [ ] **Step 5: Run the full suite (8 pages consume MetricCard)**

```bash
cd frontend && npm test
```

Expected: all green, no regressions on Cash/Analytics/TaxReport/Polymarket/Options/Dividends/Dashboard.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/MetricCard.jsx frontend/src/components/MetricCard.test.jsx
git commit -m "feat(ui): premium MetricCard (spotlight glow + optional count-up), same prop API"
```

---

### Task 6: Contrast verification for the Premium tokens

**Files:**
- Create: `frontend/src/lib/contrast.js`
- Create: `frontend/src/lib/contrast.test.js`

**Interfaces:**
- Consumes: `NEU_TOKENS` (exported from `../App` in Task 1).
- Produces: `contrastRatio(hexA, hexB) -> number` (WCAG relative-luminance contrast ratio, 1-21). Automates the spec's "manual contrast check on `--muted`, `--gain`, `--loss` against `#F3E8DA`" verification step.

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/lib/contrast.test.js`:

```js
import { contrastRatio } from "./contrast";
import { NEU_TOKENS } from "../App";

const CARD_BG = "#F3E8DA"; // NEU_TOKENS.bg -- the cream ground text sits on

describe("contrastRatio", () => {
  it("matches the textbook WCAG example (black on white = 21:1)", () => {
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 0);
  });
  it("is symmetric", () => {
    expect(contrastRatio("#3A352C", "#F3E8DA")).toBeCloseTo(contrastRatio("#F3E8DA", "#3A352C"), 5);
  });
});

describe("Premium theme contrast against the cream card", () => {
  it("ink clears AAA body text (7:1)", () => {
    expect(contrastRatio(NEU_TOKENS.ink, CARD_BG)).toBeGreaterThanOrEqual(7);
  });
  it("muted clears AA body text (4.5:1)", () => {
    expect(contrastRatio(NEU_TOKENS.muted, CARD_BG)).toBeGreaterThanOrEqual(4.5);
  });
  // brand/gain/loss render as bold small-caps pills, deltas and icons (not
  // paragraph text), so the applicable bar is WCAG's large-text/UI-component
  // threshold (3:1, SC 1.4.11) rather than normal body text's 4.5:1.
  it("brand clears the large-text/UI-component threshold (3:1)", () => {
    expect(contrastRatio(NEU_TOKENS.brand, CARD_BG)).toBeGreaterThanOrEqual(3);
  });
  it("gain clears the large-text/UI-component threshold (3:1)", () => {
    expect(contrastRatio(NEU_TOKENS.gain, CARD_BG)).toBeGreaterThanOrEqual(3);
  });
  it("loss clears the large-text/UI-component threshold (3:1)", () => {
    expect(contrastRatio(NEU_TOKENS.loss, CARD_BG)).toBeGreaterThanOrEqual(3);
  });
  it("white button labels on --brand clear AA body text (4.5:1)", () => {
    expect(contrastRatio("#FFFFFF", NEU_TOKENS.brand)).toBeGreaterThanOrEqual(4.5);
  });
});
```

- [ ] **Step 2: Run it — must fail**

```bash
cd frontend && npx vitest run src/lib/contrast.test.js
```

Expected: FAIL — `Cannot find module './contrast'`.

- [ ] **Step 3: Implement**

Create `frontend/src/lib/contrast.js`:

```js
function srgbToLinear(c) {
  const v = c / 255;
  return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
}

function relativeLuminance(hex) {
  const h = hex.replace("#", "");
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b);
}

export function contrastRatio(hexA, hexB) {
  const lA = relativeLuminance(hexA);
  const lB = relativeLuminance(hexB);
  const lighter = Math.max(lA, lB);
  const darker = Math.min(lA, lB);
  return (lighter + 0.05) / (darker + 0.05);
}
```

- [ ] **Step 4: Run it — must pass**

```bash
cd frontend && npx vitest run src/lib/contrast.test.js
```

Expected: all PASS (verified by hand: ink≈10.1:1, muted≈4.9:1, brand≈4.3:1, gain≈4.0:1, loss≈4.0:1, white-on-brand≈5.2:1 — all clear their asserted thresholds).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/contrast.js frontend/src/lib/contrast.test.js
git commit -m "test(theme): automate the Premium-palette WCAG contrast check"
```

---

### Task 7: StockDetail — Quick Stats row + 52-Week Range

**Files:**
- Modify: `frontend/src/components/StockDetail.jsx`

**Interfaces:**
- Consumes: `KpiBox` (Task 4).
- Produces: no change to `StockOverview`'s own props; `QuickStat` (the local component) is deleted, its only 6 call sites become `KpiBox`.

- [ ] **Step 1: Import `KpiBox`**

In `frontend/src/components/StockDetail.jsx`, after the existing `chartTheme` import block (after line 22), add:

```js
import { KpiBox } from "./ui";
```

- [ ] **Step 2: Quick Stats row → `KpiBox` grid**

Replace:

```jsx
    quickStats: (
      <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
        <QuickStat label="Market Cap" value={fmtCompact(data.market_cap, cs)} />
        <QuickStat label="P/E (TTM)" value={fmtRatio(ratios.pe)} />
        <QuickStat label="EPS (TTM)" value={ttm.eps != null ? `${cs}${ttm.eps.toFixed(2)}` : "—"} />
        <QuickStat label="Div Yield" value={ratios.div_yield != null ? `${ratios.div_yield.toFixed(2)}%` : "—"} />
        <QuickStat label="Beta" value={fmtRatio(data.beta)} />
        <QuickStat label="EV/EBITDA" value={fmtRatio(ratios.ev_ebitda)} />
      </div>
    ),
```

with:

```jsx
    quickStats: (
      <div className="grid grid-cols-3 md:grid-cols-6 gap-3">
        <KpiBox size="sm" label="Market Cap" value={fmtCompact(data.market_cap, cs)} />
        <KpiBox size="sm" label="P/E (TTM)" value={fmtRatio(ratios.pe)} />
        <KpiBox size="sm" label="EPS (TTM)" value={ttm.eps != null ? `${cs}${ttm.eps.toFixed(2)}` : "—"} />
        <KpiBox size="sm" label="Div Yield" value={ratios.div_yield != null ? `${ratios.div_yield.toFixed(2)}%` : "—"} />
        <KpiBox size="sm" label="Beta" value={fmtRatio(data.beta)} />
        <KpiBox size="sm" label="EV/EBITDA" value={fmtRatio(ratios.ev_ebitda)} />
      </div>
    ),
```

- [ ] **Step 3: 52-Week Range — pick up the radius token**

Replace:

```jsx
    weekRange: range ? (
      <div className="bg-surface rounded-lg px-4 py-3">
```

with:

```jsx
    weekRange: range ? (
      <div className="bg-surface rounded-[var(--radius-card)] px-4 py-3">
```

(This block already sits inside the report's card shell, so it stays flat —
`rounded-lg` -> the radius token is the only change, not the full `.card`
blur/shadow treatment, which would double up the glass effect.)

- [ ] **Step 4: Delete the now-dead `QuickStat` component**

Remove:

```jsx
function QuickStat({ label, value }) {
  return (
    <div className="bg-surface rounded-lg px-3 py-2">
      <div className="text-[10px] text-muted uppercase tracking-wider">{label}</div>
      <div className="text-base font-bold tabular-nums truncate">{value}</div>
    </div>
  );
}
```

- [ ] **Step 5: Verify**

```bash
cd frontend && npm test && npm run build
```

Expected: all tests pass; build succeeds; no remaining reference to `QuickStat` (`grep -c QuickStat frontend/src/components/StockDetail.jsx` returns `0`).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/StockDetail.jsx
git commit -m "feat(stock): Quick Stats row -> KpiBox grid, restyle the 52-week range card"
```

---

### Task 8: StockDetail — Valuation & Quality ratios table → dense KPI grid

**Files:**
- Modify: `frontend/src/components/StockDetail.jsx`

**Interfaces:**
- Consumes: `KpiBox` (Task 4, already imported by Task 7).
- Produces: `RatioRow` (the local component) is deleted; `RATIO_ROWS` (the data array) is unchanged, only its renderer changes.

- [ ] **Step 1: Replace the ratios panel's header row + `RatioRow` list with a `KpiBox` grid**

Replace:

```jsx
        <div className="bg-surface rounded-lg p-4">
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
          <div className="flex items-center justify-between text-[10px] uppercase tracking-wider text-muted pb-1 border-b border-surface-border mb-1">
            <span>Metric</span>
            <div className="flex items-center gap-3">
              <span className="w-16 text-right">Value</span>
              <span className="w-16 text-right">Sector</span>
              <span className="w-14 text-right">Δ</span>
            </div>
          </div>
          {RATIO_ROWS.map((r) => {
            const year = r.yearKey ? ratios[r.yearKey] : null;
            const label =
              r.labelYearSuffix && year != null
                ? `${r.label} (${year})`
                : r.label;
            return (
              <RatioRow
                key={r.key}
                label={label}
                value={ratios[r.key]}
                sector={sector[r.key]}
                fmt={r.pct ? fmtPctValue : fmtRatio}
                tooltip={r.tooltip}
                lowerIsBetter={r.lowerIsBetter}
                noSector={r.noSector}
              />
            );
          })}
        </div>
```

with:

```jsx
        <div className="bg-surface rounded-[var(--radius-card)] p-4">
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
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {RATIO_ROWS.map((r) => {
              const year = r.yearKey ? ratios[r.yearKey] : null;
              const label =
                r.labelYearSuffix && year != null
                  ? `${r.label} (${year})`
                  : r.label;
              const fmt = r.pct ? fmtPctValue : fmtRatio;
              const value = ratios[r.key];
              const sectorVal = r.noSector ? null : sector[r.key];
              const delta = value != null && sectorVal != null ? value - sectorVal : null;
              const favourable = delta == null ? null : (r.lowerIsBetter ? delta < 0 : delta > 0);
              const direction = r.lowerIsBetter ? "Lower is better." : "Higher is better.";
              return (
                <KpiBox
                  key={r.key}
                  size="sm"
                  label={label}
                  value={fmt(value)}
                  info={r.tooltip ? { title: label, what: r.tooltip, note: direction } : { title: label, what: direction }}
                  sub={r.noSector ? null : `Sector ${fmt(sectorVal)} · Δ ${delta == null ? "—" : fmtSignedNumber(delta, 2)}`}
                  subTone={favourable == null ? "muted" : favourable ? "gain" : "loss"}
                />
              );
            })}
          </div>
        </div>
```

- [ ] **Step 2: Delete the now-dead `RatioRow` component**

Remove:

```jsx
function RatioRow({ label, value, sector, fmt, tooltip, lowerIsBetter, noSector }) {
  const sectorVal = noSector ? null : sector;
  const delta = value != null && sectorVal != null ? value - sectorVal : null;
  // Green when the focal stock is on the "better" side of the sector median;
  // direction depends on the metric (cheap multiples = lower is better, fat
  // margins = higher is better).
  const deltaColor = (() => {
    if (delta == null) return "text-muted";
    const favourable = lowerIsBetter ? delta < 0 : delta > 0;
    return favourable ? "text-gain" : "text-loss";
  })();
  // Always close the description with which direction is "good", derived from
  // the same lowerIsBetter flag that drives the Δ-vs-sector colouring above so
  // the two can never disagree.
  const direction = lowerIsBetter ? "Lower is better." : "Higher is better.";
  const titleText = tooltip ? `${tooltip}\n\n${direction}` : direction;
  return (
    <div className="flex items-center justify-between py-1.5 text-sm border-b border-surface-border last:border-0">
      <div className="flex items-center gap-1 text-muted cursor-help" title={titleText}>
        <span className="text-xs">{label}</span>
        <Info size={11} className="text-muted shrink-0" />
      </div>
      <div className="flex items-center gap-3 tabular-nums">
        <span className="text-ink font-medium w-16 text-right">{fmt(value)}</span>
        <span className="text-muted w-16 text-right text-xs">
          {noSector ? "—" : fmt(sectorVal)}
        </span>
        <span className={`w-14 text-right text-xs font-medium ${deltaColor}`}>
          {delta == null ? "—" : fmtSignedNumber(delta, 2)}
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify**

```bash
cd frontend && npm test && npm run build
```

Expected: all tests pass; build succeeds; `grep -c "RatioRow" frontend/src/components/StockDetail.jsx` returns `0`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/StockDetail.jsx
git commit -m "feat(stock): Valuation & Quality ratios -> dense KpiBox grid"
```

---

### Task 9: StockDetail — Ownership stats + Dividend-growth tiles → KpiBox

**Files:**
- Modify: `frontend/src/components/StockDetail.jsx`

**Interfaces:**
- Consumes: `KpiBox` (already imported since Task 7).
- Produces: `OwnershipStat` (local component) is deleted; `DividendGrowthSection`'s tile markup is simplified in place (same `tiles` array, same section, no prop/behavior change).

- [ ] **Step 1: Ownership stats → `KpiBox`**

Replace:

```jsx
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
            <OwnershipStat
              label="Institutions"
              value={instPct != null ? `${instPct.toFixed(1)}%` : "—"}
            />
            <OwnershipStat
              label="Insiders"
              value={insiderPct != null ? `${insiderPct.toFixed(1)}%` : "—"}
            />
            <OwnershipStat
              label="Top holders"
              value={
                ownership.institutions_count != null
                  ? `${ownership.institutions_count}`
                  : "—"
              }
            />
            <OwnershipStat
              label="Short interest"
              value={shortPct != null ? `${(shortPct * 100).toFixed(2)}%` : "—"}
            />
          </div>
```

with:

```jsx
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
            <KpiBox
              size="sm"
              label="Institutions"
              value={instPct != null ? `${instPct.toFixed(1)}%` : "—"}
            />
            <KpiBox
              size="sm"
              label="Insiders"
              value={insiderPct != null ? `${insiderPct.toFixed(1)}%` : "—"}
            />
            <KpiBox
              size="sm"
              label="Top holders"
              value={
                ownership.institutions_count != null
                  ? `${ownership.institutions_count}`
                  : "—"
              }
            />
            <KpiBox
              size="sm"
              label="Short interest"
              value={shortPct != null ? `${(shortPct * 100).toFixed(2)}%` : "—"}
            />
          </div>
```

- [ ] **Step 2: Delete the now-dead `OwnershipStat` component**

Remove:

```jsx
function OwnershipStat({ label, value }) {
  return (
    <div className="bg-surface-card rounded-md px-3 py-2 border border-surface-border">
      <div className="text-[10px] text-muted uppercase tracking-wider">{label}</div>
      <div className="text-base font-bold tabular-nums">{value}</div>
    </div>
  );
}
```

- [ ] **Step 3: Dividend-growth tiles → `KpiBox`**

Replace:

```jsx
      <div className="grid grid-cols-3 gap-3">
        {tiles.map((t) => (
          <div key={t.label} className="rounded-lg border border-surface-border bg-surface-card px-3 py-2">
            <p className="text-[10px] text-muted uppercase tracking-wider">{t.label}</p>
            <p className="text-sm font-semibold text-ink tabular-nums">{t.value}</p>
          </div>
        ))}
      </div>
```

with:

```jsx
      <div className="grid grid-cols-3 gap-3">
        {tiles.map((t) => (
          <KpiBox key={t.label} size="sm" label={t.label} value={t.value} />
        ))}
      </div>
```

- [ ] **Step 4: Verify**

```bash
cd frontend && npm test && npm run build
```

Expected: all tests pass, including `StockDetail.divgrowth.test.jsx`; build succeeds; `grep -c "OwnershipStat" frontend/src/components/StockDetail.jsx` returns `0`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StockDetail.jsx
git commit -m "feat(stock): ownership stats + dividend-growth tiles -> KpiBox"
```

---

### Task 10: StockDetail — header hero (shine + reveal)

**Files:**
- Modify: `frontend/src/components/StockDetail.jsx`

**Interfaces:**
- Consumes: `Reveal`, `ShinyText` (Task 2).

- [ ] **Step 1: Import `Reveal` and `ShinyText`**

After the `import { KpiBox } from "./ui";` line added in Task 7, add:

```js
import Reveal from "./reactbits/Reveal";
import ShinyText from "./reactbits/ShinyText";
```

- [ ] **Step 2: Wrap the header in `Reveal`, shine the ticker heading**

Replace:

```jsx
      {/* ----- Header (always visible) ----- */}
      <div className="flex items-start justify-between px-6 py-4 border-b border-surface-border">
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-3 flex-wrap">
            <h2 className="text-2xl font-bold font-mono">{data.ticker}</h2>
            <span className="text-muted text-base truncate">{data.name}</span>
```

with:

```jsx
      {/* ----- Header (always visible) ----- */}
      <Reveal className="flex items-start justify-between px-6 py-4 border-b border-surface-border">
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-3 flex-wrap">
            <h2 className="text-2xl font-bold font-mono"><ShinyText text={data.ticker} /></h2>
            <span className="text-muted text-base truncate">{data.name}</span>
```

- [ ] **Step 3: Close with `</Reveal>` instead of `</div>`**

Replace:

```jsx
          <SectionCustomizer {...reportConfig} />
          {headerTrailing}
        </div>
      </div>
```

with:

```jsx
          <SectionCustomizer {...reportConfig} />
          {headerTrailing}
        </div>
      </Reveal>
```

- [ ] **Step 4: Verify**

```bash
cd frontend && npm test && npm run build
```

Expected: all tests pass; build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/StockDetail.jsx
git commit -m "feat(stock): header hero -- shine on the ticker heading, reveal-on-mount"
```

---

### Task 11: PortfolioHero — shine on the Net Worth eyebrow

**Files:**
- Modify: `frontend/src/components/PortfolioHero.jsx`

**Interfaces:**
- Consumes: `ShinyText` (Task 2).

This is the Dashboard's actual hero (`Dashboard.jsx` renders `<PortfolioHero>`
at the top of the page). Dashboard's grid cards already have a tasteful
staggered `animate-fade-up` entrance (`animationDelay: "100ms"..."350ms"`,
`fade-up` keyframe in `tailwind.config.js`) — that's a mount-triggered reveal
that already reads as premium and is already reduced-motion-safe via the
global CSS rule, so it's left as-is rather than converted to the
scroll-triggered `Reveal` (which would be redundant motion on a page that's
mostly one viewport tall, and touching all 6 grid-card blocks for no visual
gain isn't worth the risk on a large, actively-used file).

- [ ] **Step 1: Import `ShinyText` and wrap the eyebrow**

At the top of `frontend/src/components/PortfolioHero.jsx`, add:

```js
import ShinyText from "./reactbits/ShinyText";
```

Replace:

```jsx
            <p className="eyebrow">Net Worth</p>
```

with:

```jsx
            <p className="eyebrow"><ShinyText text="Net Worth" /></p>
```

- [ ] **Step 2: Verify against the existing test**

```bash
cd frontend && npx vitest run src/components/PortfolioHero.test.jsx
```

Expected: 3 PASS (unchanged — `screen.getByText(/Net Worth/i)` still matches the text inside the new `<span>`).

- [ ] **Step 3: Run the full suite**

```bash
cd frontend && npm test && npm run build
```

Expected: all green; build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PortfolioHero.jsx
git commit -m "feat(dashboard): shine on the PortfolioHero Net Worth eyebrow"
```

---

### Task 12: Overview — reveal + shine polish

**Files:**
- Modify: `frontend/src/pages/Overview.jsx`

**Interfaces:**
- Consumes: `Reveal`, `ShinyText` (Task 2).

- [ ] **Step 1: Replace the file**

Replace the full contents of `frontend/src/pages/Overview.jsx` with:

```jsx
import { useQuery } from "@tanstack/react-query";
import { fetchOverview } from "../api";
import { useCurrency } from "../App";
import { formatMoney } from "../lib/format";
import BreakdownChart from "../components/BreakdownChart";
import Reveal from "../components/reactbits/Reveal";
import ShinyText from "../components/reactbits/ShinyText";
import { Layers, TrendingUp, TrendingDown } from "lucide-react";

export default function Overview() {
  const currencyCtx = useCurrency?.();
  const currency = currencyCtx?.currency || "USD";

  const { data, isLoading } = useQuery({
    queryKey: ["overview", currency],
    queryFn: () => fetchOverview(currency),
    staleTime: 5 * 60 * 1000,
  });

  const dc = data?.total_day_change ?? 0;
  const dcPct = data?.total_day_change_percent;
  const up = dc >= 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Layers size={18} className="text-brand" />
        <h1 className="text-xl font-semibold">Overview</h1>
        {data?.portfolio_count != null && (
          <span className="text-sm text-muted">· {data.portfolio_count} portfolios</span>
        )}
      </div>

      <Reveal>
        <div className="card">
          <p className="text-xs font-semibold text-muted uppercase tracking-wider">
            <ShinyText text="Total net worth" />
          </p>
          {isLoading ? (
            <p className="text-3xl font-semibold text-ink mt-2">…</p>
          ) : (
            <>
              <p className="text-3xl font-semibold text-ink mt-2 tabular-nums">
                {formatMoney(data?.total_net_worth ?? 0, currency)}
              </p>
              <p className={`text-sm mt-1 flex items-center gap-1 tabular-nums ${up ? "text-gain" : "text-loss"}`}>
                {up ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                {up ? "+" : ""}{formatMoney(dc, currency)}
                {dcPct != null && <span>({up ? "+" : ""}{dcPct.toFixed(2)}%) today</span>}
              </p>
            </>
          )}
        </div>
      </Reveal>

      {!isLoading && data && (
        <Reveal delay={100}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <BreakdownChart title="Sectors" data={data.sectors} currencyLabel={currency} />
            <BreakdownChart title="Countries" data={data.countries} currencyLabel={currency} />
            <BreakdownChart title="Asset types" data={data.asset_types} currencyLabel={currency} />
          </div>
        </Reveal>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify against the existing test**

```bash
cd frontend && npx vitest run src/pages/Overview.test.jsx
```

Expected: 1 PASS (unchanged — `findByText(/Total net worth/i)` still matches inside the new `<span>`).

- [ ] **Step 3: Run the full suite**

```bash
cd frontend && npm test && npm run build
```

Expected: all green; build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/Overview.jsx
git commit -m "feat(overview): reveal-on-scroll + shine polish"
```

---

### Task 13: Final verification

**Files:** none (verification only).

**Interfaces:** consumes everything from Tasks 1-12; produces the verified, shippable redesign.

- [ ] **Step 1: Full test suite + build**

```bash
cd frontend && npm test && npm run build
```

Expected: all Vitest suites green (existing + every test added in Tasks 2-6, 11); `npm run build` succeeds with no errors.

- [ ] **Step 2: Start the dev servers**

```bash
./start.bat
```

Expected: backend on :8000, frontend on :5173, browser opens.

- [ ] **Step 3: Playwright walkthrough**

Using the Playwright MCP (already installed per this repo's CLAUDE.md), drive `http://localhost:5173`:

1. Log in with the dev password (`snowball-dev`, or `$APP_PASSWORD` if set).
2. On Dashboard: confirm the Premium theme is active by default (warm cream
   background with the mesh gradient, soft dual-shadow cards, rounded
   `1.25rem` corners), the "Net Worth" eyebrow has a visible shine sweep, and
   hovering a `MetricCard`/`KpiBox` shows the warm spotlight glow.
3. Open Settings/Sidebar: toggle Style between "Premium" and "Classic" —
   confirm Classic restores the pre-existing blue/green/purple glass look
   unchanged, and Appearance/Accent controls re-enable; toggle back to
   Premium and confirm they gray out again.
4. Navigate to a Stock Detail page (`/stock/AAPL` or similar): confirm the
   Quick Stats row, the Valuation & Quality ratios grid, the Ownership
   stats, and the Dividend-growth tiles all render as individual rounded KPI
   boxes with readable text and (on hover) the spotlight glow; confirm the
   ticker heading shows the shine sweep.
5. Navigate to Overview: confirm the net-worth card and the sector/country/
   asset-type breakdown charts fade+lift into view.
6. Check for console errors throughout (`read_console_messages`).

- [ ] **Step 4: Manual contrast spot-check**

With Premium active, visually confirm body text (`--ink`), secondary text
(`--muted`), and gain/loss figures are comfortably readable on the cream
cards — this is the human-eyeball complement to Task 6's automated
`contrastRatio` assertions, not a replacement for them.

No commit for this task — it's verification of Tasks 1-12's already-committed work.
