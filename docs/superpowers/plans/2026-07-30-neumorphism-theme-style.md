# Neumorphism Theme Style Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Style" switch (Classic glass / Soft Neumorphism) to Portfyl's
Sidebar that instantly repaints the whole app between the existing
dark-glassmorphism system and a new neumorphism system, persisted per-device.

**Architecture:** Portfyl's entire theme is already indirected through CSS
custom properties written by one JS function, `applyAppearance()` in
`frontend/src/App.jsx` — components consume the vars via Tailwind classes
(`bg-surface-card`, `text-ink`, ...) or, for charts, via `var()` strings in
`frontend/src/lib/chartTheme.js`. This plan adds a second value table
(`NEU_TOKENS`) that the same function writes when the new `themeStyle` state
is `"neu"`, plus two new tokens (`--radius-card`, `--shadow-inset`) for the
one structural difference plain color tokens can't express (corner radius,
embossed vs. ambient shadow). No page file needs direct changes — only the
token-writing function, the primitives that hardcode radius, the three
copy-pasted toggle switches, and the Sidebar control that flips the switch.

**Tech Stack:** React 18, Tailwind CSS (utility classes resolving to CSS
custom properties), no frontend test framework (see Global Constraints).

**Full design context:** `docs/superpowers/specs/2026-07-30-neumorphism-theme-style-design.md`

## Global Constraints

- **No frontend test framework exists in this repo** (`CLAUDE.md`: only
  backend `pytest`). Every task below substitutes an automatable
  `npm run build` sanity gate (catches syntax/import errors) plus a concrete
  manual/Playwright visual-verification step for the "test" step a normal
  plan would run as `pytest` — do not invent a test framework or write
  fake `.test.jsx` files that don't run under anything.
- **`sb_theme` and `sb_palette` localStorage keys are not renamed or reused.**
  The new key is `sb_theme_style`, values `"glass" | "neu"`, default
  `"glass"` — existing users see zero change until they opt in.
- **Classic must stay pixel-identical.** Every new/changed CSS custom
  property must have a glass-mode value equal to today's rendered output
  (e.g. `--radius-card: 0.5rem` matches today's hardcoded `rounded-lg`,
  `--shadow-inset: none` is a no-op `box-shadow`).
- Dev servers: `start.bat` from repo root (backend :8000, frontend :5173,
  opens browser). Frontend-only changes in this plan — no backend restart
  needed after the first server start.
- Verify UI with Playwright MCP against `http://localhost:5173` per
  `CLAUDE.md`'s "Verifying UI changes" section (log in with dev password
  `snowball-dev` unless `APP_PASSWORD` is set).

---

### Task 1: Radius token — `.card`/buttons/input/SegmentedControl go through `--radius-card`

**Files:**
- Modify: `frontend/src/index.css:6-35` (add tokens to `:root`), `:64-90`
  (`.card`, `.btn-primary`, `.btn-ghost`, `.input`)
- Modify: `frontend/src/components/ui/SegmentedControl.jsx:29,42`

**Interfaces:**
- Produces: CSS custom properties `--radius-card` (default `0.5rem`) and
  `--shadow-inset` (default `none`), consumed by every primitive below and
  later by `applyAppearance()` in Task 3.

- [x] **Step 1: Add the two new tokens to `index.css`'s `:root` block**

In `frontend/src/index.css`, inside `@layer base { :root { ... } }`, add these
two lines right after the existing `--chart-8: #64748B;` line (line 34):

```css
    --chart-8: #64748B;
    --radius-card: 0.5rem;
    --shadow-inset: none;
  }
```

- [x] **Step 2: Route `.card`, `.btn-primary`, `.btn-ghost`, `.input` through `--radius-card`**

In the same file's `@layer components` block, replace these four lines:

```css
  .card {
    @apply bg-surface-card rounded-lg border border-hairline p-5;
```

with:

```css
  .card {
    @apply bg-surface-card border border-hairline p-5 rounded-[var(--radius-card)];
```

Replace:

```css
  .btn-primary {
    @apply bg-brand hover:bg-brand-dim text-white font-semibold px-4 py-2 rounded-lg transition-colors;
  }
```

with:

```css
  .btn-primary {
    @apply bg-brand hover:bg-brand-dim text-white font-semibold px-4 py-2 rounded-[var(--radius-card)] transition-colors;
  }
```

Replace (inside `.btn-ghost`, keep the existing comment above it untouched):

```css
    @apply border border-hairline hover:border-slate-300 text-muted hover:text-ink px-4 py-2 rounded-lg transition-colors;
```

with:

```css
    @apply border border-hairline hover:border-slate-300 text-muted hover:text-ink px-4 py-2 rounded-[var(--radius-card)] transition-colors;
```

Replace (inside `.input`):

```css
    @apply bg-surface border border-hairline rounded-lg px-3 py-2 text-ink placeholder-muted focus:outline-none focus:border-brand w-full;
```

with:

```css
    @apply bg-surface border border-hairline rounded-[var(--radius-card)] px-3 py-2 text-ink placeholder-muted focus:outline-none focus:border-brand w-full;
```

- [x] **Step 3: Route `SegmentedControl.jsx` through the same token**

In `frontend/src/components/ui/SegmentedControl.jsx`, line 29, replace:

```jsx
      className={`${block ? "flex w-full" : "inline-flex"} gap-0.5 rounded-lg bg-surface-hover p-0.5 ${className}`}
```

with:

```jsx
      className={`${block ? "flex w-full" : "inline-flex"} gap-0.5 rounded-[var(--radius-card)] bg-surface-hover p-0.5 ${className}`}
```

And line 42, replace:

```jsx
            className={`rounded-md font-medium transition-colors ${block ? "flex-1 flex items-center justify-center" : ""} ${SIZES[size]} ${
```

with:

```jsx
            className={`rounded-[var(--radius-card)] font-medium transition-colors ${block ? "flex-1 flex items-center justify-center" : ""} ${SIZES[size]} ${
```

- [x] **Step 4: Build sanity check**

Run: `cd frontend && npm run build`
Expected: build succeeds with no errors (Tailwind's arbitrary-value syntax
`rounded-[var(--radius-card)]` is valid and needs no config change).

- [x] **Step 5: Manual visual check — Classic is unchanged**

Start dev servers (`start.bat` from repo root), log in, open
`http://localhost:5173/` (Dashboard). Take a screenshot. Corners on cards,
buttons, and the Appearance segmented control should look identical to
before this task (8px-ish radius) — this is expected, since
`--radius-card: 0.5rem` is the same value `rounded-lg` already produced.

- [x] **Step 6: Commit**

```bash
git add frontend/src/index.css frontend/src/components/ui/SegmentedControl.jsx
git commit -m "feat(theme): route card/button/input/segmented-control radius through a CSS var"
```

---

### Task 2: Extract `Toggle.jsx` primitive from the 3 copy-pasted switches

**Files:**
- Create: `frontend/src/components/ui/Toggle.jsx`
- Modify: `frontend/src/pages/Settings.jsx:1-7` (import), `:358-364` (T212
  auto-sync), `:510-516` (IBKR auto-sync)
- Modify: `frontend/src/components/DiscordSettings.jsx:1-4` (import),
  `:151-157` (per-preference toggle)

**Interfaces:**
- Produces: `Toggle({ checked, onChange, disabled, activeClassName, "aria-label" })`
  — `onChange` is called with the **new** boolean value (not a click event),
  `activeClassName` defaults to `"bg-brand"` (override for Discord's fixed
  blurple `bg-[#5865F2]`).
- Consumes: `--shadow-inset` from Task 1 (renders as `none` until Task 3
  gives it a real neu value, so this task changes zero pixels).

- [x] **Step 1: Create the `Toggle` primitive**

Create `frontend/src/components/ui/Toggle.jsx`:

```jsx
export default function Toggle({
  checked,
  onChange,
  disabled = false,
  activeClassName = "bg-brand",
  "aria-label": ariaLabel,
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      onClick={() => onChange(!checked)}
      disabled={disabled}
      className={`w-9 h-5 rounded-full transition-colors relative ${checked ? activeClassName : "bg-slate-300"}`}
      style={{ boxShadow: "var(--shadow-inset)" }}
    >
      <span
        className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform shadow-sm ${checked ? "left-[18px]" : "left-0.5"}`}
      />
    </button>
  );
}
```

- [x] **Step 2: Replace the T212 auto-sync toggle in `Settings.jsx`**

Add the import — in `frontend/src/pages/Settings.jsx`, after line 7
(`import SyncScheduleSettings from "../components/SyncScheduleSettings";`),
add:

```jsx
import Toggle from "../components/ui/Toggle";
```

Then replace (around line 358-364):

```jsx
                <button
                  onClick={() => autoSyncMutation.mutate(!status.auto_sync)}
                  disabled={autoSyncMutation.isPending}
                  className={`w-9 h-5 rounded-full transition-colors relative ${status.auto_sync ? "bg-brand" : "bg-slate-300"}`}
                >
                  <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform shadow-sm ${status.auto_sync ? "left-[18px]" : "left-0.5"}`} />
                </button>
```

with:

```jsx
                <Toggle
                  checked={status.auto_sync}
                  onChange={(v) => autoSyncMutation.mutate(v)}
                  disabled={autoSyncMutation.isPending}
                  aria-label="T212 auto-sync"
                />
```

- [x] **Step 3: Replace the IBKR auto-sync toggle in `Settings.jsx`**

Replace (around line 510-516):

```jsx
                <button
                  onClick={() => ibkrAutoSyncMutation.mutate(!ibkrStatus.auto_sync)}
                  disabled={ibkrAutoSyncMutation.isPending}
                  className={`w-9 h-5 rounded-full transition-colors relative ${ibkrStatus.auto_sync ? "bg-brand" : "bg-slate-300"}`}
                >
                  <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform shadow-sm ${ibkrStatus.auto_sync ? "left-[18px]" : "left-0.5"}`} />
                </button>
```

with:

```jsx
                <Toggle
                  checked={ibkrStatus.auto_sync}
                  onChange={(v) => ibkrAutoSyncMutation.mutate(v)}
                  disabled={ibkrAutoSyncMutation.isPending}
                  aria-label="IBKR auto-sync"
                />
```

- [x] **Step 4: Replace the notification-preference toggle in `DiscordSettings.jsx`**

Add the import — after line 4
(`import { Loader2, Unlink, CheckCircle2, AlertCircle, Send, Bell, BellOff } from "lucide-react";`),
add:

```jsx
import Toggle from "./ui/Toggle";
```

Then replace (around line 151-157):

```jsx
                <button
                  onClick={() => toggleMut.mutate({ [key]: !webhook[key] })}
                  className={`w-9 h-5 rounded-full transition-colors relative ${webhook[key] ? "bg-[#5865F2]" : "bg-slate-300"}`}
                >
                  <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform shadow-sm ${webhook[key] ? "left-[18px]" : "left-0.5"}`} />
                </button>
```

with:

```jsx
                <Toggle
                  checked={webhook[key]}
                  onChange={(v) => toggleMut.mutate({ [key]: v })}
                  activeClassName="bg-[#5865F2]"
                  aria-label={label}
                />
```

- [x] **Step 5: Build sanity check**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [x] **Step 6: Manual visual check — behavior unchanged**

On `http://localhost:5173/settings`, connect (or view, if already connected)
a T212/IBKR/Discord integration and click each toggle. Confirm: visual
appearance and click behavior are identical to before this task (knob
slides, color flips), since `--shadow-inset: none` makes the new inline
`boxShadow` a no-op.

- [x] **Step 7: Commit**

```bash
git add frontend/src/components/ui/Toggle.jsx frontend/src/pages/Settings.jsx frontend/src/components/DiscordSettings.jsx
git commit -m "refactor(settings): extract shared Toggle primitive from 3 copy-pasted switches"
```

---

### Task 3: Neumorphism token engine — `NEU_TOKENS` + `applyAppearance()` + `PaletteProvider`

**Files:**
- Modify: `frontend/src/App.jsx:33-101` (palette tables, `applyAppearance`),
  `:207-241` (`PaletteProvider`)

**Interfaces:**
- Consumes: `--radius-card`/`--shadow-inset` declared in Task 1.
- Produces: `applyAppearance(name, isDark, themeStyle)` (new 3rd param);
  `PaletteContext` value gains `themeStyle` (string, `"glass" | "neu"`) and
  `setThemeStyle(next)` — consumed by Task 4's Sidebar control.

- [x] **Step 1: Add `NEU_TOKENS` and a `GLASS_CHART` constant**

In `frontend/src/App.jsx`, after the `LIGHT_TOKENS` const (line 54-57), add:

```jsx
// Soft Neumorphism — one fixed light appearance (no dark variant, no accent
// palettes); see docs/superpowers/specs/2026-07-30-neumorphism-theme-style-design.md.
const NEU_TOKENS = {
  bg: "#EDEAE3", bgSubtle: "#E4E0D7", surfaceCard: "#EDEAE3", surfaceCardElevated: "#F1EEE8",
  border: "rgba(58,54,46,0.06)", hairline: "rgba(58,54,46,0.06)",
  ink: "#3A362E", muted: "#8A8478",
  brand: "#4FBA95", brandHover: "#3FA382", brandLight: "#D9F1E8",
  gain: "#4FBA95", loss: "#E88A72",
  shadowAmbient: "6px 6px 14px rgba(190,178,158,0.55), -6px -6px 14px rgba(255,255,255,0.85)",
  shadowInset: "inset 3px 3px 8px rgba(190,178,158,0.5), inset -3px -3px 8px rgba(255,255,255,0.8)",
  radiusCard: "1.5rem",
  chart: ["#4FBA95", "#E88A72", "#E3B873", "#B6A7D1", "#8FC5D6", "#E3A6B0", "#D9C9A6", "#A69C8C"],
};
const GLASS_CHART = ["var(--brand)", "#4EDEA3", "#FFB95F", "#A78BFA", "#38BDF8", "#FB7185", "#FACC15", "#64748B"];
```

- [x] **Step 2: Give `applyAppearance` a `themeStyle` param and a `neu` branch**

Replace the entire `applyAppearance` function (lines 73-101):

```jsx
function applyAppearance(name, isDark) {
  const p = PALETTES[name] || PALETTES.green;
  const s = document.documentElement.style;
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
  s.setProperty("--shadow-ambient", isDark ? "0px 4px 20px rgba(0,0,0,0.5)" : "0px 4px 20px rgba(16,22,43,0.10)");
  s.setProperty("--gain", isDark ? "#34D399" : "#10B981");
  s.setProperty("--loss", isDark ? "#F87171" : "#EF4444");
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

with:

```jsx
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
    s.setProperty("--glass-border-alpha", "rgba(0,0,0,0)");
    s.setProperty("--glass-overlay-alpha", "rgba(255,255,255,0)");
    s.setProperty("--blur-card", "0px");
    s.setProperty("--blur-overlay", "0px");
    s.setProperty("--shadow-ambient", NEU_TOKENS.shadowAmbient);
    s.setProperty("--shadow-inset", NEU_TOKENS.shadowInset);
    s.setProperty("--radius-card", NEU_TOKENS.radiusCard);
    NEU_TOKENS.chart.forEach((color, i) => s.setProperty(`--chart-${i + 1}`, color));
    document.documentElement.classList.toggle("dark", false);
    return;
  }

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

(The explicit `--blur-card`/`--blur-overlay`/`--radius-card`/`--shadow-inset`/
chart-token writes in the glass branch are new — previously these were never
touched by JS and relied on `:root` defaults. They must be written explicitly
now so that switching **back** from `neu` to `glass` overwrites `neu`'s
inline overrides instead of leaving them stuck.)

- [x] **Step 3: Wire `themeStyle` into `PaletteProvider`**

Replace the `PaletteProvider` function (lines 207-241):

```jsx
function PaletteProvider({ children }) {
  const [palette, setPaletteState] = useState(
    () => localStorage.getItem("sb_palette") || "green"
  );
  const [theme, setThemeState] = useState(
    () => localStorage.getItem("sb_theme") || "system"
  );

  const setPalette = (p) => {
    localStorage.setItem("sb_palette", p);
    setPaletteState(p);
  };

  const setTheme = (t) => {
    localStorage.setItem("sb_theme", t);
    setThemeState(t);
  };

  useEffect(() => {
    const apply = () => applyAppearance(palette, resolveDark(theme));
    apply();
    // Follow OS changes only while on "system".
    if (theme === "system") {
      const mq = window.matchMedia("(prefers-color-scheme: dark)");
      mq.addEventListener("change", apply);
      return () => mq.removeEventListener("change", apply);
    }
  }, [palette, theme]);

  return (
    <PaletteContext.Provider value={{ palette, setPalette, theme, setTheme, palettes: PALETTES }}>
      {children}
    </PaletteContext.Provider>
  );
}
```

with:

```jsx
function PaletteProvider({ children }) {
  const [palette, setPaletteState] = useState(
    () => localStorage.getItem("sb_palette") || "green"
  );
  const [theme, setThemeState] = useState(
    () => localStorage.getItem("sb_theme") || "system"
  );
  const [themeStyle, setThemeStyleState] = useState(
    () => localStorage.getItem("sb_theme_style") || "glass"
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
    // Follow OS changes only while on "system" AND on the classic glass
    // style — Neumorphism ignores Light/Dark/System entirely.
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

- [x] **Step 4: Build sanity check**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [x] **Step 5: Manual verification — engine works via devtools (no UI trigger yet)**

There is no clickable control yet (Task 4 adds it), but the engine is fully
wired via `localStorage`. Start dev servers, log in, open browser devtools
console on `http://localhost:5173/`, run:

```js
localStorage.setItem("sb_theme_style", "neu"); location.reload();
```

Expected: page background turns warm light beige, cards/buttons show a
visible embossed dual shadow (no blur), text turns warm dark brown instead
of navy. Then run `localStorage.setItem("sb_theme_style", "glass");
location.reload();` and confirm the app returns exactly to its normal
dark-glassmorphism look (proves the "switch back" token-reset logic from
Step 2 works).

- [x] **Step 6: Commit**

```bash
git add frontend/src/App.jsx
git commit -m "feat(theme): add Neumorphism token table and themeStyle to PaletteProvider"
```

---

### Task 4: Sidebar "Style" control

**Files:**
- Modify: `frontend/src/components/Sidebar.jsx:42` (destructure),
  `:98-134` (footer JSX)

**Interfaces:**
- Consumes: `themeStyle`/`setThemeStyle` from `usePalette()` (Task 3).

- [x] **Step 1: Destructure `themeStyle`/`setThemeStyle`**

In `frontend/src/components/Sidebar.jsx`, line 42, replace:

```jsx
  const { palette, setPalette, theme, setTheme } = usePalette();
```

with:

```jsx
  const { palette, setPalette, theme, setTheme, themeStyle, setThemeStyle } = usePalette();
```

- [x] **Step 2: Add the Style control, dim Appearance/Accent when `neu` is active**

Replace the footer's Appearance + Palette blocks (lines 98-134):

```jsx
      <div className="mt-auto pb-3 space-y-3">
        {/* Appearance (light / dark / system) */}
        <div className="px-4">
          <p className="text-[10px] text-muted mb-1.5 pl-0.5">Appearance</p>
          <SegmentedControl
            block
            size="sm"
            aria-label="Appearance"
            value={theme}
            onChange={setTheme}
            options={[
              { value: "light", label: <Sun size={13} />, title: "Light" },
              { value: "dark", label: <Moon size={13} />, title: "Dark" },
              { value: "system", label: <Monitor size={13} />, title: "System" },
            ]}
          />
        </div>

        {/* Palette switcher */}
        <div className="px-4">
          <p className="text-[10px] text-muted mb-1.5 pl-0.5">Accent</p>
          <div className="flex gap-1.5">
            {PALETTE_OPTIONS.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setPalette(key)}
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

with:

```jsx
      <div className="mt-auto pb-3 space-y-3">
        {/* Theme style (Classic glass vs Soft Neumorphism) */}
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
              { value: "neu", label: "Neumorphism", title: "Soft Neumorphism theme" },
            ]}
          />
        </div>

        {/* Appearance (light / dark / system) — inert while Neumorphism is
            active, which ships as the one fixed light appearance. */}
        <div className={`px-4 ${themeStyle === "neu" ? "opacity-40 pointer-events-none" : ""}`}>
          <p className="text-[10px] text-muted mb-1.5 pl-0.5">Appearance</p>
          <SegmentedControl
            block
            size="sm"
            aria-label="Appearance"
            value={theme}
            onChange={setTheme}
            options={[
              { value: "light", label: <Sun size={13} />, title: "Light" },
              { value: "dark", label: <Moon size={13} />, title: "Dark" },
              { value: "system", label: <Monitor size={13} />, title: "System" },
            ]}
          />
        </div>

        {/* Palette switcher — same rationale as Appearance above. */}
        <div className={`px-4 ${themeStyle === "neu" ? "opacity-40 pointer-events-none" : ""}`}>
          <p className="text-[10px] text-muted mb-1.5 pl-0.5">Accent</p>
          <div className="flex gap-1.5">
            {PALETTE_OPTIONS.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setPalette(key)}
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

- [x] **Step 3: Build sanity check**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [x] **Step 4: Manual visual check — the real switch works end-to-end**

Start dev servers, log in, open `http://localhost:5173/`. In the Sidebar
footer, click **Neumorphism** in the new Style row. Expected: the whole app
repaints instantly (warm background, embossed cards, mint/coral accents, no
blur); the Appearance and Accent rows visibly dim and stop responding to
clicks. Click **Classic** — the app instantly returns to today's
dark-glassmorphism look and Appearance/Accent become clickable again.
Reload the page — the chosen style should persist (it's read from
`localStorage` on mount).

- [x] **Step 5: Commit**

```bash
git add frontend/src/components/Sidebar.jsx
git commit -m "feat(sidebar): add Style control to switch between Classic and Neumorphism"
```

---

### Task 5: Full visual sweep across page types (both styles)

**Files:** none (verification-only task; no code changes expected — if this
task finds a bug, fix it in the relevant file from Tasks 1-4 and re-run this
task's checks before committing).

- [x] **Step 1: Playwright sweep — Classic (must be unaffected by this whole plan)**

Using Playwright MCP against `http://localhost:5173` (logged in, Style set
to Classic): visit Dashboard (`/`), Stock detail (`/stock/:ticker` — pick any
holding), Transactions (`/transactions`), and Settings (`/settings`).
Screenshot each. Expected: identical to how these pages looked before this
plan — same corner radii, same shadows, same colors, toggle switches behave
as before.

- [x] **Step 2: Playwright sweep — Neumorphism**

Switch Style to Neumorphism in the Sidebar. Revisit the same four pages,
screenshot each. Expected, matching the moodboard concepts in the published
gallery artifact: warm light background throughout; cards read as embossed
(soft dual shadow, no border, no blur) rather than glassy; buttons/inputs/
segmented controls show visibly larger corner radius; P&L pills and chart
lines use the mint/coral palette instead of green/red; the three toggle
switches (Settings ×2, Discord notification prefs) show the embossed inset
track from `--shadow-inset`.

- [x] **Step 3: Confirm no regressions in chart-heavy and table-heavy content**

Still in Neumorphism, check `/analytics` (charts: performance area chart,
correlation matrix) and `/tax-report` or `/transactions` (dense tables).
Expected: recharts elements (grid lines, tooltips, axis ticks, categorical
fills) repaint via `chartTheme.js`'s existing `var()` reads with no console
errors; table rows/text remain legible against the new `--ink`/`--muted`
values (no low-contrast regressions).

- [x] **Step 4: If everything matches, this task needs no commit**

If Steps 1-3 all pass, there is nothing to commit — this task only exists to
catch integration issues the isolated per-task checks in Tasks 1-4 couldn't.
If something doesn't match, fix it in the owning task's file, re-run the
build sanity check for that task, redo this task's affected step, then
commit the fix with a message referencing what broke, e.g.:

```bash
git add frontend/src/index.css
git commit -m "fix(theme): correct hairline contrast in Neumorphism on dense tables"
```

---

## Outcome (2026-08-01)

All five tasks executed. Steps 1-2 passed as written: Classic is byte-identical
(`--radius-card` 0.5rem → 8px computed, `--shadow-inset: none`, `--blur-card`
12px, chart tokens unchanged, all 5 toggles still 36×20 pill with Discord's
blurple intact), `sb_theme_style` defaults to unset → `glass`, the switch
repaints without a reload, and switching back restores every token in both
directions. Zero console errors across Dashboard / Settings / Transactions /
Analytics in both styles.

**Step 3 found one real regression** — the moodboard's pastel text tokens were
too light on the `#EDEAE3` card: muted 3.09, brand/gain 1.99, loss 2.10, all
below their Classic-light counterparts, with muted the only sub-AA value in any
Portfyl style. Most visible on the Transactions table header/notes and the
Analytics chart legends. Fixed in `NEU_TOKENS` (the Task 3 file) — see the
contrast note in the design spec's token table. The `--chart-*` pastels were
deliberately left alone: they are large fills, not 11px text.
