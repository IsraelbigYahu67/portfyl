# Stitch Desktop Re-skin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-skin the desktop Portfyl frontend (`frontend/`) to the Google Stitch "Corporate Modern with Glassmorphism" dark-institutional design system, without changing any page layout, navigation structure, routing, or functionality.

**Architecture:** The app already routes every color through CSS custom properties swapped at runtime by `applyAppearance()` (`App.jsx`) — that mechanism stays exactly as-is; only the token *values* change, plus new glass-specific tokens (blur, glass-border alpha, an elevated-surface tier) are added to the same system. A new `frontend/src/lib/chartTheme.js` centralizes the chart color palette that today is duplicated as hardcoded hex across 10 files. Stitch is dark-only, so light mode and the "Soft Iris" purple accent are original derivations in the same visual language — this plan states their exact values and the reasoning, not just "match Stitch."

**Tech Stack:** React 18, Tailwind CSS (existing `darkMode: "class"` + CSS-custom-property indirection), `@fontsource-variable/*` self-hosted fonts, `recharts`.

## Global Constraints

- **Re-skin only.** No page layout, widget order, navigation item list/order, routes, or component hierarchy changes. Every task changes colors/typography/spacing-tokens/radii/shadows only.
- **Desktop `frontend/` only.** Do not touch `frontend-mobile/` or `backend/`.
- **Preserve the theming mechanism**: CSS custom properties on `:root`/`html.dark`, written by `applyAppearance()`; the 3-accent picker (now: Arctic Blue / Mint Green / Soft Iris); the Light/Dark/System toggle. All three must keep working identically after this plan — only their color values change.
- **Gap-fill rule**: any element with no direct Stitch reference (light mode entirely; the "Soft Iris" purple accent; pages Cash, Options, DividendCalendar, Assistant, Search which have no matching mockup) is derived from the token system defined in Task 1 — never a one-off color.
- **Brand name is "Portfyl"** (correct spelling) everywhere in the app, even though several Stitch screens render it as a typo.
- **Do not re-skin third-party brand marks** — `DiscordSettings.jsx`'s Discord-blurple (`#5865F2`/`#4752C4`) stays Discord's own color, not a Portfyl token.
- **One new dependency**: `@fontsource-variable/plus-jakarta-sans`. Nothing else — no new UI/animation libraries.
- **`cd frontend && npm test` must stay green after every task.** If a test asserts a literal class name that a task changes, update the assertion in that same task — never defer it.
- Reference assets live at `docs/design/stitch/` (Task 1 moves them there from the root-level zip).

### Design tokens (locked values — every later task references this table, do not invent new hex elsewhere)

**Reconciliation note**: `DESIGN.md`'s YAML frontmatter and its prose section disagree on the canvas color (`#0b1326` vs `#020617`). Pixel-sampled ground truth from the actual screenshots (`portfyl_premium_dashboard/screen.png`) settles it: the true page canvas is `#020616` (≈ prose's `#020617`), and `#0b1326` is actually the *sidebar/base-card* tone, one step up the tonal ladder. The table below is the reconciled, verified system.

**Dark (default/primary — Stitch-matched):**
| Token (CSS var) | Value | Used for |
|---|---|---|
| `--bg` | `#020617` | page canvas |
| `--bg-subtle` | `#0B1326` | hover surfaces, progress-track backgrounds |
| `--surface-card` | `#131B2E` | `.card` fill |
| `--surface-card-elevated` *(new)* | `#1F2435` | stat/KPI tiles, raised surfaces |
| `--hairline` / `--border` | `#2A3245` | 1px card border, dividers |
| `--ink` | `#DAE2FD` | primary text |
| `--muted` | `#8A93B3` | secondary text, labels |
| `--gain` | `#34D399` | positive P&L (kept from today's existing dark value — already close to Stitch's secondary emerald `#4edea3`) |
| `--loss` | `#F87171` | negative P&L (kept from today's existing dark value — already matches Stitch's soft high-contrast red) |
| `--glass-border-alpha` *(new)* | `rgba(255,255,255,0.06)` | card edge "sheen" |
| `--glass-overlay-alpha` *(new)* | `rgba(255,255,255,0.03)` | card top-edge gradient wash |
| `--blur-card` *(new)* | `12px` | `.card` backdrop-blur |
| `--blur-overlay` *(new)* | `20px` | modal/dropdown backdrop-blur |
| `--shadow-ambient` *(new)* | `0px 4px 20px rgba(0,0,0,0.5)` | the one floating-element shadow per DESIGN.md |

**Light (original derivation — Stitch has no light mode):** same design language (glass cards, 8px radius, same brand hues), cool pale canvas instead of black, hue-neutral across all 3 accents (mirroring how dark mode is already hue-neutral):
| Token | Value |
|---|---|
| `--bg` | `#F3F5FB` |
| `--bg-subtle` | `#E8ECF5` |
| `--surface-card` | `#FFFFFF` |
| `--surface-card-elevated` | `#F7F9FD` |
| `--hairline` / `--border` | `#DDE3F0` |
| `--ink` | `#10162B` |
| `--muted` | `#6B7592` |
| `--gain` | `#10B981` (kept, today's existing light value) |
| `--loss` | `#EF4444` (kept, today's existing light value) |
| `--glass-border-alpha` | `rgba(16,22,43,0.06)` |
| `--glass-overlay-alpha` | `rgba(255,255,255,0.5)` |
| `--shadow-ambient` | `0px 4px 20px rgba(16,22,43,0.10)` |

**3-way accent palette** (`brand` / `brandHover` / `brandLightDark` [dark-mode tinted-chip bg] / `brandLight` [light-mode tinted-chip bg]) — **mode-independent brand hue** (correction, post-Task-1-review): the app's pre-existing `applyAppearance()` has never branched `--brand`/`--brand-hover` by light/dark, and Task 1 Step 7 deliberately keeps that structure untouched to avoid scope creep in the foundational task. An earlier draft of this table implied separate light-mode brand shades; that was dropped as an unnecessary refinement (existing `#3B82F6`-family blues already clear WCAG's 3:1 UI-component contrast bar on white) rather than implemented — one `brand`/`brandHover` pair serves both modes, exactly as `frontend/src/App.jsx`'s `PALETTES` (post Task 1) has it:
| Accent | Brand (both modes) | Hover (both modes) | Dark tint bg | Light tint bg |
|---|---|---|---|---|
| **Arctic Blue** | `#3B82F6` *(new — Stitch "Action Blue")* | `#2563EB` | `#1E3A5F` | `#DBEAFE` *(kept)* |
| **Mint Green** | `#34D399` *(new, close to Stitch secondary)* | `#10B981` | `#0F3D30` | `#D1FAE5` *(kept)* |
| **Soft Iris** *(gap-fill — not in Stitch)* | `#A78BFA` | `#8B5CF6` | `#2E2555` | `#EDE9FE` *(kept)* |

Soft Iris is derived, not copied: a periwinkle-violet at the same lightness/saturation register as the blue and emerald accents (Stitch's own tertiary is amber, not purple — amber is reserved for the chart palette instead, see below, so it doesn't collide with "warning" semantics).

`sidebarActive` (active nav-item glass-pill background) becomes a single rgba tint per accent instead of the current dual text-color + separate solid-hex mechanism: dark `rgba(<brand-rgb>, 0.16)`, light = the `brandLight`/tint-bg value above.

**Chart categorical palette** *(new, `frontend/src/lib/chartTheme.js`)* — replaces 4 separate duplicated rainbow arrays:
| Var | Value | Role |
|---|---|---|
| `--chart-1` | `var(--brand)` | primary series (tracks active accent) |
| `--chart-2` | `#4EDEA3` | Stitch secondary emerald (fixed — doesn't shift if accent=green) |
| `--chart-3` | `#FFB95F` | Stitch tertiary amber (fixed) |
| `--chart-4` | `#A78BFA` | Soft Iris purple (fixed) |
| `--chart-5` | `#38BDF8` | sky (supporting) |
| `--chart-6` | `#FB7185` | rose (supporting — distinct from `--loss` so it's never confused with a P&L red) |
| `--chart-7` | `#FACC15` | amber-yellow (supporting) |
| `--chart-8` | `#64748B` | neutral slate ("Others" bucket) |

Chart chrome (axis ticks/gridlines/tooltip) uses `var(--muted)` / `var(--hairline)` / `var(--surface-card-elevated)` — never hardcoded hex.

**Typography**: Plus Jakarta Sans (headings/display, weights 600–800) replaces Space Grotesk. Inter (body) stays. Numeric/financial data drops JetBrains Mono in favor of Inter + `tabular-nums`, matching DESIGN.md's explicit `numeric-data` token (`fontFamily: Inter`) rather than keeping a separate mono face.

**Radius**: Tailwind's `rounded-lg` is already 8px by default — buttons/inputs (128 occurrences) already match the Stitch spec and need no change. The only mismatch is `.card`'s `rounded-2xl` (16px) → drops to `rounded-lg` (8px). Pills stay `rounded-full`.

**Signature element**: every one of the 12 Stitch mockups opens with the same recurring device — a row of glass stat tiles (icon chip top-right, eyebrow label, big tabular value, colored delta subline). This is the re-skin's one deliberate, memorable move: `MetricCard.jsx` becomes the app's canonical stat-tile primitive, and every page's one-off summary-stat markup (`PortfolioHero`'s chips, Dividends/DividendCalendar/Cash/Options/Polymarket's ad hoc `<div>` stat rows) is brought to visually match it — used directly where the layout allows, or given the identical visual recipe where a page needs bespoke layout (e.g. `PortfolioHero`'s sparkline background).

---

### Task 1: Design tokens core — Tailwind config, CSS variables, theme provider

**Files:**
- Create: `docs/design/stitch/` (extracted reference assets)
- Modify: `.gitignore`, `frontend/tailwind.config.js`, `frontend/src/index.css`, `frontend/src/App.jsx`, `frontend/index.html`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: every CSS var and Tailwind color class named in the token table above, available app-wide via existing `bg-surface-card`/`text-ink`/`text-muted`/`text-gain`/`text-loss`/`border-hairline`/`bg-brand`/etc. classes. Every later task consumes these — do not invent new token names elsewhere.

- [ ] **Step 1: Move the Stitch reference into the repo**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
mkdir -p docs/design/stitch
unzip -o -q stitch_portfyl_desktop.zip -d docs/design/stitch
ls docs/design/stitch/stitch_portfyl_desktop   # sanity check: 13 screen folders + DESIGN.md
```

Append to `.gitignore`:
```
stitch_portfyl_desktop.zip
```

- [ ] **Step 2: Rewrite the CSS variable defaults in `frontend/src/index.css`**

Replace the existing `:root { ... }` block (the one declaring `--brand`, `--bg`, `--surface-card`, `--border`, `--ink`, `--muted`, `--hairline`, `--gain`, `--loss`) with:

```css
:root {
  /* Light (default at first paint; applyAppearance() overrides immediately on mount) */
  --brand: #059669;
  --brand-hover: #047857;
  --brand-light: #D1FAE5;
  --bg: #F3F5FB;
  --bg-subtle: #E8ECF5;
  --sidebar-active: #D1FAE5;
  --surface-card: #FFFFFF;
  --surface-card-elevated: #F7F9FD;
  --border: #DDE3F0;
  --hairline: #DDE3F0;
  --ink: #10162B;
  --muted: #6B7592;
  --gain: #10B981;
  --loss: #EF4444;
  --glass-border-alpha: rgba(16, 22, 43, 0.06);
  --glass-overlay-alpha: rgba(255, 255, 255, 0.5);
  --blur-card: 12px;
  --blur-overlay: 20px;
  --shadow-ambient: 0px 4px 20px rgba(16, 22, 43, 0.10);
}
```

- [ ] **Step 3: Update `.card` and related `@layer components` classes for the glass treatment**

In `frontend/src/index.css`, replace the `.card` rule:

```css
.card {
  @apply bg-surface-card rounded-lg border border-hairline p-5;
  background-image: linear-gradient(to bottom right, var(--glass-overlay-alpha), transparent 40%);
  backdrop-filter: blur(var(--blur-card));
  box-shadow: var(--shadow-ambient);
  border-color: var(--hairline);
  transition: box-shadow 0.18s ease, transform 0.18s ease, border-color 0.18s ease;
}
```

Update `.card-interactive:hover` to reference the new elevated surface instead of a generic shadow escalation:
```css
.card-interactive:hover {
  @apply -translate-y-0.5;
  background-color: var(--surface-card-elevated);
  border-color: color-mix(in srgb, var(--brand) 30%, var(--hairline));
}
```

Update `.eyebrow` to use the new label-md letter-spacing from DESIGN.md (`0.05em` instead of the current `0.12em`):
```css
.eyebrow {
  @apply font-display text-[11px] font-semibold uppercase tracking-[0.05em] text-muted;
}
```
(note: `.eyebrow` now uses `text-muted` — a token — instead of the raw `text-slate-500` it had before; this is the pattern every later task follows.)

Leave `.btn-primary`, `.btn-ghost`, `.input`, `.gain`, `.loss` structurally as-is (they already route through tokens/`rounded-lg`, which is already 8px).

- [ ] **Step 4: Delete the `.dark .foo{}` patch block**

Remove the entire unlayered `.dark .text-slate-XXX { ... }` / `.dark .bg-white { ... }` / etc. block (lines ~102–141 in the current file) — this blunt-override system is superseded by Task 3/7's move to semantic token classes. Leave the `::-webkit-scrollbar` dark-mode rule but repoint its colors at `var(--hairline)`/`var(--bg-subtle)`:
```css
.dark ::-webkit-scrollbar-thumb { background: var(--hairline); }
.dark ::-webkit-scrollbar-thumb:hover { background: var(--bg-subtle); }
```

- [ ] **Step 5: Add the chart-token CSS variables**

Append to the same `:root` block from Step 2:
```css
  --chart-1: var(--brand);
  --chart-2: #4EDEA3;
  --chart-3: #FFB95F;
  --chart-4: #A78BFA;
  --chart-5: #38BDF8;
  --chart-6: #FB7185;
  --chart-7: #FACC15;
  --chart-8: #64748B;
```

- [ ] **Step 6: Rewrite `PALETTES`, `DARK_SURFACES`, `LIGHT_TOKENS` in `frontend/src/App.jsx`**

Replace the existing three constants (lines ~33–46 per investigation) with:

```js
const PALETTES = {
  blue: {
    brand: "#3B82F6", brandHover: "#2563EB", brandLight: "#DBEAFE", brandLightDark: "#1E3A5F",
    bg: "#F3F5FB", bgSubtle: "#E8ECF5", sidebarActive: "rgba(59,130,246,0.16)",
  },
  green: {
    brand: "#34D399", brandHover: "#10B981", brandLight: "#D1FAE5", brandLightDark: "#0F3D30",
    bg: "#F3F5FB", bgSubtle: "#E8ECF5", sidebarActive: "rgba(52,211,153,0.16)",
  },
  purple: {
    brand: "#A78BFA", brandHover: "#8B5CF6", brandLight: "#EDE9FE", brandLightDark: "#2E2555",
    bg: "#F3F5FB", bgSubtle: "#E8ECF5", sidebarActive: "rgba(167,139,250,0.16)",
  },
};

const DARK_SURFACES = {
  bg: "#020617", bgSubtle: "#0B1326", surfaceCard: "#131B2E", surfaceCardElevated: "#1F2435",
  border: "#2A3245", ink: "#DAE2FD", muted: "#8A93B3", hairline: "#2A3245",
};
const LIGHT_TOKENS = {
  surfaceCard: "#FFFFFF", surfaceCardElevated: "#F7F9FD", border: "#DDE3F0",
  ink: "#10162B", muted: "#6B7592", hairline: "#DDE3F0",
};
```

Note: light-mode `bg`/`bgSubtle`/`sidebarActive` are now identical across all three palettes (`#F3F5FB`/`#E8ECF5`) instead of per-palette pastel tints — this makes light mode hue-neutral like dark mode already is, a deliberate simplification.

- [ ] **Step 7: Update `applyAppearance()` to set the new surface/glass vars**

In `applyAppearance()` (`App.jsx`), alongside the existing `--brand`/`--bg`/`--surface-card`/etc. assignments, add:
```js
root.style.setProperty("--surface-card-elevated", isDark ? DARK_SURFACES.surfaceCardElevated : LIGHT_TOKENS.surfaceCardElevated);
root.style.setProperty("--glass-border-alpha", isDark ? "rgba(255,255,255,0.06)" : "rgba(16,22,43,0.06)");
root.style.setProperty("--glass-overlay-alpha", isDark ? "rgba(255,255,255,0.03)" : "rgba(255,255,255,0.5)");
root.style.setProperty("--shadow-ambient", isDark ? "0px 4px 20px rgba(0,0,0,0.5)" : "0px 4px 20px rgba(16,22,43,0.10)");
root.style.setProperty("--gain", isDark ? "#34D399" : "#10B981");
root.style.setProperty("--loss", isDark ? "#F87171" : "#EF4444");
```
(the existing lines setting `--brand`, `--bg`, `--bg-subtle`, `--sidebar-active`, `--surface-card`, `--border`, `--hairline`, `--ink`, `--muted` stay, just now reading the updated constants from Steps 2/6 — `--surface-card` should read `palette.brandLightDark`-independent `DARK_SURFACES.surfaceCard`/`LIGHT_TOKENS.surfaceCard` as it already does today, no structural change to that part of the function).

- [ ] **Step 8: Fix the pre-paint flash-prevention script**

In `frontend/index.html`, the inline `<script>` in `<head>` hardcodes `--bg: #0F172A` to avoid a light-mode flash before React mounts. Update it to the new dark canvas:
```js
el.style.setProperty("--bg", "#020617");
el.style.background = "#020617";
```

- [ ] **Step 9: Add `rgba(<brand-rgb>, ...)` note for Tailwind arbitrary usage**

No code change — just confirm `bg-brand/10` and similar Tailwind opacity-modifier classes (used throughout `components/ui/`) still work: they require `--brand` to be a hex/rgb color (not itself an `rgba()` string), which it is (`#3B82F6` etc.) — only `sidebarActive`/`brandLightDark` became rgba/hex-in-navy-family, and neither is consumed via Tailwind's `/10` opacity-modifier syntax today (both are read via inline `style.backgroundColor`), so no conflict. Confirm by grepping:
```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/frontend && grep -rn "brand/1\|brand/2\|sidebar-active" src/ | grep -v node_modules
```
Expected: only `Sidebar.jsx`'s inline `style={{ backgroundColor: "var(--sidebar-active)" }}` and `bg-brand/10` usages inside `components/ui/*.jsx` icon chips — the latter reference `--brand` directly (always a solid hex), which is unaffected.

- [ ] **Step 10: Verify build + tests**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/frontend && npm test && npm run build
```
Expected: tests pass unchanged (no component logic touched); build succeeds. Visually the app will look "half-migrated" (dark navy canvas, but old radius/fonts/raw slate classes elsewhere) until later tasks land — that's expected at this checkpoint.

- [ ] **Step 11: Commit**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
git add docs/design/stitch .gitignore frontend/tailwind.config.js frontend/src/index.css frontend/src/App.jsx frontend/index.html
git commit -m "feat: Stitch design tokens — dark canvas, glass card system, 3-accent palette, chart tokens"
```

---

### Task 2: Typography — Plus Jakarta Sans, drop mono for numeric data

**Files:**
- Modify: `frontend/package.json`, `frontend/src/main.jsx`, `frontend/tailwind.config.js`
- Modify: `frontend/src/components/ui/DeltaPill.jsx` and any other `font-mono` + `tnum` combination (grep-discovered in Step 3 below)

**Interfaces:**
- Consumes: Task 1's token system (no direct dependency, but should land right after since font-family and color are both "core identity" changes best verified together).
- Produces: `font-display` → Plus Jakarta Sans; numeric data uses `font-sans tabular-nums` instead of `font-mono tnum`. Every later task's financial-figure markup uses this pattern.

- [ ] **Step 1: Install the font package**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/frontend && npm install @fontsource-variable/plus-jakarta-sans
```

- [ ] **Step 2: Swap the font import and Tailwind config**

In `frontend/src/main.jsx`, replace:
```js
import "@fontsource-variable/space-grotesk";
```
with:
```js
import "@fontsource-variable/plus-jakarta-sans";
```

In `frontend/tailwind.config.js`, `theme.extend.fontFamily`, change:
```js
display: ["Space Grotesk Variable", ...defaultTheme.fontFamily.sans],
```
to:
```js
display: ["Plus Jakarta Sans Variable", ...defaultTheme.fontFamily.sans],
```
(keep `sans: ["Inter Variable", ...]` and `mono: ["JetBrains Mono Variable", ...]` — mono stays installed/available for any genuinely code-like use, just stops being the default for money figures.)

- [ ] **Step 3: Find every numeric-data `font-mono` usage — and only those**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/frontend && grep -rln "font-mono" src/ | grep -v test
```

This returns 24 files. **Not every `font-mono` occurrence is numeric-data display** — some are genuinely code-like text that should stay mono: `MetricCard.jsx`'s `InfoIcon` renders a math formula string (`info.formula`, e.g. `"IRR = ..."`) in `font-mono text-[10px] text-brand` with no `tnum`/`tabular-nums` alongside it — that one stays mono. Likewise check `DiscordSettings.jsx` and `Settings.jsx` (broker API-key/webhook-URL display) — those are token/credential strings, not financial figures, and should also stay mono.

The rule: **only convert a `font-mono` occurrence that is paired with `tnum` or `tabular-nums` in the same className** (that combination is exactly how the codebase marks "this is a tabular financial figure" today) — e.g. in `DeltaPill.jsx`:
```jsx
// before: `inline-flex items-center rounded-full font-mono font-semibold tnum ${SIZES[size]} ${tone} ${className}`
// after:
`inline-flex items-center rounded-full font-sans font-semibold tabular-nums ${SIZES[size]} ${tone} ${className}`
```
Go through each of the 24 files individually and apply this `font-mono tnum` → `font-sans tabular-nums` substitution only where both classes co-occur; leave every standalone `font-mono` (formulas, credentials/tokens, webhook URLs) untouched.

- [ ] **Step 4: Verify `.tnum` utility still exists or remove it if unused**

```bash
grep -rn "\.tnum\b" frontend/src/index.css frontend/tailwind.config.js
```
If `.tnum` was a custom utility class (not Tailwind's built-in `tabular-nums`), and Step 3 removed its last usage, delete its definition from `index.css`. If any usage remains, leave it defined but confirm it maps to `font-variant-numeric: tabular-nums` (functionally identical to Tailwind's own `tabular-nums` utility — fine for either to remain, but don't leave two names for the same thing in new code going forward).

- [ ] **Step 5: Visual + automated check**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/frontend && npm test && npm run build
```
Then start `start.bat`, open the Dashboard, and confirm headings render in Plus Jakarta Sans (distinct rounded-geometric look vs. the old Space Grotesk) and that money figures (Portfolio value, P&L) still vertically align digit-for-digit (tabular-nums working) — screenshot for the record.

- [ ] **Step 6: Commit**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
git add frontend/package.json frontend/package-lock.json frontend/src/main.jsx frontend/tailwind.config.js frontend/src/index.css frontend/src/components/ui/DeltaPill.jsx
git commit -m "feat: swap Space Grotesk -> Plus Jakarta Sans, drop mono face for numeric data"
```
(add any additional numeric-data files touched in Step 3 to this commit too.)

---

### Task 3: Shared UI primitives — glass treatment + token cleanup

**Files:**
- Modify: `frontend/src/components/ui/{EmptyState,ErrorState,Toast,ConfirmDialog}.jsx` (raw slate/emerald/red → tokens)
- Modify: `frontend/src/components/ui/{SectionHeader,SegmentedControl,Skeleton}.jsx` (glass/radius/token alignment)

**Interfaces:**
- Consumes: Task 1's tokens (`bg-surface-card`, `bg-surface-card-elevated`, `text-ink`, `text-muted`, `text-gain`, `text-loss`, `border-hairline`).
- Produces: every shared primitive fully token-driven, zero raw `text-slate-*`/`bg-white`/`bg-slate-50`/`text-emerald-600`/`text-red-600` literals remaining in `components/ui/`. Tasks 4–7 (Sidebar, MetricCard, pages) rely on these primitives already being correct.

- [ ] **Step 1: `EmptyState.jsx`** — replace the icon chip `bg-slate-100 text-slate-400` with `bg-surface-card-elevated text-muted`; replace `text-slate-700`/`text-slate-500` body text with `text-ink`/`text-muted`.

- [ ] **Step 2: `ErrorState.jsx`** — replace `text-red-500` with `text-loss`; keep `.btn-ghost` (already tokenized); replace any raw `text-slate-500` with `text-muted`.

- [ ] **Step 3: `Toast.jsx`** — replace `text-emerald-600`/`text-red-600`/`text-slate-500` with `text-gain`/`text-loss`/`text-muted` (the component already uses `.card`/`border-surface-border`, which now inherit the glass treatment automatically from Task 1).

- [ ] **Step 4: `ConfirmDialog.jsx`** — keep `bg-black/30 backdrop-blur-sm` for the scrim (still correct for a modal overlay against any theme), but bump the blur to match DESIGN.md's overlay spec: `backdrop-blur-sm` → `style={{ backdropFilter: "blur(var(--blur-overlay))" }}`. Keep `.btn-ghost`/`bg-brand hover:bg-brand-dim` as-is (already tokenized); keep the danger button's `bg-red-600 hover:bg-red-700` as a deliberate exception (destructive actions use a fixed, theme-independent red per common UX convention, not the P&L `--loss` token — note this exception explicitly in a one-line code comment: `{/* deliberately not --loss: destructive-action red is fixed, not tied to P&L semantics */}`).

- [ ] **Step 5: `SectionHeader.jsx`** — the icon chip `bg-brand/10 text-brand` already routes through the token; no change needed beyond confirming (Tailwind's `/10` opacity modifier on `--brand` works regardless of whether `--brand` is currently a solid hex, which it always is per Task 1 Step 9). Update the wrapping card header's bottom-border (if any inline style is used) to `border-hairline`.

- [ ] **Step 6: `SegmentedControl.jsx`** — replace the active-state `bg-white font-semibold text-brand shadow-sm` with `bg-surface-card-elevated font-semibold text-brand`, and the track/inactive `bg-slate-100`/`text-slate-500 hover:text-slate-700` with `bg-bg-subtle`/`text-muted hover:text-ink` (add `bg-bg-subtle` to `tailwind.config.js`'s `colors.surface` group as `hover: "var(--bg-subtle)"` if not already present from Task 1 — check `tailwind.config.js` first; the investigation confirmed `surface.hover` already maps to `var(--bg-subtle)`, so use the existing `bg-surface-hover` class name, not a new one).

- [ ] **Step 7: `Skeleton.jsx`** — the `.shimmer` utility hardcodes `#EEF1F5` + a white-alpha sweep gradient, which will look wrong (light-grey flash) against the new dark canvas. In `index.css`, change `.shimmer`'s base color to `var(--bg-subtle)` and the sweep gradient to use `var(--glass-overlay-alpha)` instead of a hardcoded white alpha:
```css
.shimmer {
  background: var(--bg-subtle);
  position: relative;
  overflow: hidden;
}
.shimmer::after {
  content: "";
  position: absolute; inset: 0;
  background: linear-gradient(90deg, transparent, var(--glass-overlay-alpha), transparent);
  animation: shimmer-sweep 1.6s infinite;
}
```
(keep the existing `@keyframes shimmer-sweep` definition unchanged if the sweep animation itself is already parameterized correctly — only the color stops need updating.)

- [ ] **Step 8: Run tests + visual spot-check**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/frontend && npm test
```
Then in the running app, trigger each primitive at least once: an empty watchlist (EmptyState), a failed fetch — e.g. throttle network in devtools (ErrorState), save a setting (Toast), delete a portfolio (ConfirmDialog), a loading page (Skeleton), Dashboard's Value/Growth toggle (SegmentedControl). Screenshot each in dark mode.

- [ ] **Step 9: Commit**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
git add frontend/src/components/ui frontend/src/index.css frontend/tailwind.config.js
git commit -m "feat: token-drive all components/ui/ primitives, glass overlay/shimmer treatment"
```

---

### Task 4: Sidebar re-skin (highest-visibility surface)

**Files:**
- Modify: `frontend/src/components/Sidebar.jsx`

**Interfaces:**
- Consumes: Task 1's `--sidebar-active` (now rgba glass tint), `--surface-card`, `--hairline`; Task 3's `SegmentedControl`.
- Produces: no interface change (still the same nav item list/routes/props) — purely visual.

- [ ] **Step 1: Add the "INSTITUTIONAL GRADE" eyebrow under the wordmark**

Every Stitch screen renders this exact sidebar treatment — it's a direct reference, not a gap-fill. Update the header block:
```jsx
<div className="flex items-center gap-2.5 px-[18px] py-4 border-b border-hairline">
  <img src="/logo.png" alt="Portfyl" className="w-11 h-11 object-contain" />
  <div className="flex flex-col leading-tight">
    <span className="font-display font-bold text-[17px] tracking-tight text-ink">Portfyl</span>
    <span className="text-[9px] font-semibold uppercase tracking-[0.14em] text-muted">Institutional Grade</span>
  </div>
</div>
```

- [ ] **Step 2: Consolidate the active-nav-item mechanism to one glass pill**

Replace the current dual mechanism (className `text-brand` + separate inline `style` background) with a single className-driven glass pill:
```jsx
<NavLink
  key={to}
  to={to}
  end={to === "/"}
  className={({ isActive }) =>
    `flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] transition-all ${
      isActive
        ? "font-semibold text-brand bg-[var(--sidebar-active)] shadow-[inset_0_0_0_1px_var(--glass-border-alpha)]"
        : "text-muted hover:text-ink hover:bg-surface-hover"
    }`
  }
>
  <Icon size={16} />
  {label}
</NavLink>
```
(remove the separate `style={({isActive}) => ...}` prop entirely — Tailwind arbitrary-value `bg-[var(--sidebar-active)]` now does the same job in one place.)

- [ ] **Step 3: Update the "back to platform picker" link and footer copy to tokens**

Replace `text-slate-500 hover:text-brand`/`hover:bg-slate-50` with `text-muted hover:text-brand`/`hover:bg-surface-hover`; replace the four `text-slate-400`/`text-slate-300`/`text-red-500` footer labels ("Appearance", "Accent", "Display currency" labels, rate-unavailable message) with `text-muted`/`text-loss` respectively.

- [ ] **Step 4: Sidebar surface + shadow**

Update the `<aside>` wrapper: replace `bg-surface-card border-r border-surface-border` (already token-driven, no change needed there) but replace the hardcoded inline `style={{ boxShadow: "1px 0 4px rgba(0,0,0,0.02)" }}` with a right-edge hairline glow consistent with the glass system:
```jsx
style={{ boxShadow: "1px 0 0 var(--glass-border-alpha)" }}
```

- [ ] **Step 5: Currency toggle track**

Replace the hardcoded `bg-slate-100` track and `text-slate-300`/`text-slate-500 hover:text-slate-700` states with `bg-bg-subtle` / `text-muted` / `hover:text-ink` (accent-swatch dots and `bg-brand text-white` active-currency state already correctly reference the token system via Task 1's `PALETTES`, no change needed there).

- [ ] **Step 6: Test + screenshot**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/frontend && npm test
```
Screenshot the sidebar in dark mode against `docs/design/stitch/stitch_portfyl_desktop/portfyl_premium_dashboard/screen.png` for a side-by-side visual check (wordmark treatment, active-item glow, spacing).

- [ ] **Step 7: Commit**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
git add frontend/src/components/Sidebar.jsx
git commit -m "feat: Stitch-style sidebar — institutional-grade eyebrow, glass active-pill nav"
```

---

### Task 5: `MetricCard` as the canonical stat-tile (signature element)

**Files:**
- Modify: `frontend/src/components/MetricCard.jsx`
- Modify: `frontend/src/components/PortfolioHero.jsx` (bring its ad hoc "Chip" subcomponent visually in line)
- Modify: `frontend/src/pages/{Dividends,DividendCalendar,Cash,Options,Polymarket}.jsx` (their one-off summary-stat `<div>` rows)

**Interfaces:**
- Consumes: Task 1 tokens, Task 3's `SectionHeader` icon-chip pattern.
- Produces: `MetricCard` becomes the one visual recipe every page's top stat row follows: icon chip (top-right, `bg-brand/10 text-brand`), `eyebrow` label, big tabular value (`text-2xl font-display font-bold text-ink`), colored delta subline (`text-gain`/`text-loss`/`text-muted`). Later page-sweep tasks (Task 7) assume every stat row already looks like this.

- [ ] **Step 1: Rewrite `MetricCard.jsx`'s markup to the glass-tile recipe**

The current file (verified) has props `{ label, value, sub, positive, negative, loading, info }`, a `subColor` derived from the `positive`/`negative` booleans, an `InfoIcon` tooltip subcomponent (`info.title`/`info.what`/`info.formula`/`info.note`), and a `loading` skeleton-pulse state — **all of this must be preserved exactly** so existing call sites in `Analytics.jsx`/`TaxReport.jsx` need zero changes. Add one new *optional* prop, `icon`, purely additive (existing callers that don't pass it render with no chip, identical to today):

```jsx
import { Info } from "lucide-react";

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

export default function MetricCard({ icon: Icon, label, value, sub, positive, negative, loading, info }) {
  const subColor = positive ? "text-gain" : negative ? "text-loss" : "text-muted";

  return (
    <div className="card !bg-surface-card-elevated relative flex flex-col gap-1 min-w-0">
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
        <span className="text-2xl font-display font-bold tabular-nums truncate tracking-tight text-ink">{value}</span>
      )}
      {sub && !loading && <span className={`text-[13px] font-semibold tabular-nums ${subColor}`}>{sub}</span>}
    </div>
  );
}

export { InfoIcon };
```
Note `.eyebrow` already applies `text-muted` (from Task 1 Step 3), so the bare label text no longer needs its own `text-slate-500` — only the `InfoIcon`'s internal tooltip content needed explicit token classes since it renders in a separately-styled popover.

- [ ] **Step 2: Bring `PortfolioHero.jsx`'s inline "Chip" stats to the same recipe**

`PortfolioHero` can't use `MetricCard` directly (it needs the sparkline background behind the hero number), but its 4-up Invested/P&L/Dividends/Holdings chips should read as siblings of `MetricCard`, not a different design: apply the same eyebrow-label + tabular-value + toned-sub pattern and `bg-surface-card-elevated`-family background to those chip cells.

- [ ] **Step 3: Route the 5 remaining pages' one-off stat rows through `MetricCard`**

For each of `Dividends.jsx`, `DividendCalendar.jsx`, `Cash.jsx`, `Options.jsx`, `Polymarket.jsx`: locate the page's top summary-stat markup (grep `grid grid-cols` near the top of each file, per the investigation's page inventory — e.g. Dividends' "Paid YTD"/"Est. Remaining", DividendCalendar's 3-card row, Options' P&L/Commissions/Win Rate row, Polymarket's 5-card row) and replace the bespoke `<div>` structure with `<MetricCard icon={...} label="..." value={...} positive={...} negative={...} sub="..." />` calls, one per existing stat — preserving the exact same data bindings (a stat that's currently colored green/red conditionally becomes `positive={pnl > 0} negative={pnl < 0}`, matching `MetricCard`'s real boolean-prop shape from Step 1), just swapping the wrapper markup.

- [ ] **Step 4: Test + visual diff**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/frontend && npm test
```
Screenshot Dashboard, Analytics, TaxReport, Dividends, DividendCalendar, Cash, Options, Polymarket — confirm every page's top stat row now shares one unmistakable visual language.

- [ ] **Step 5: Commit**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
git add frontend/src/components/MetricCard.jsx frontend/src/components/PortfolioHero.jsx frontend/src/pages/Dividends.jsx frontend/src/pages/DividendCalendar.jsx frontend/src/pages/Cash.jsx frontend/src/pages/Options.jsx frontend/src/pages/Polymarket.jsx
git commit -m "feat: MetricCard as the app's one glass stat-tile primitive, used everywhere"
```

---

### Task 6: Chart color tokens

**Files:**
- Create: `frontend/src/lib/chartTheme.js`
- Modify: `frontend/src/components/{AllocationChart,BreakdownChart,CashBalanceChart,PerformanceChart,StockDetail,HeroSparkline,Heatmap}.jsx`
- Modify: `frontend/src/pages/{DividendCalendar,Dividends,Analytics,Dashboard}.jsx`

**Interfaces:**
- Consumes: Task 1's `--chart-1`..`--chart-8`, `--gain`, `--loss`, `--hairline`, `--muted`, `--surface-card-elevated`.
- Produces: `chartTheme.js` exports `CATEGORICAL` (8-entry array of `var(--chart-N, fallback)` strings), `AXIS_TICK` / `GRID_STROKE` / `TOOLTIP_STYLE` constants — every chart file imports from here instead of declaring its own hex array.

- [ ] **Step 1: Create `frontend/src/lib/chartTheme.js`**

```js
// Shared chart color tokens — every recharts consumer imports from here instead
// of hardcoding hex, so chart colors follow the active theme/accent automatically
// (SVG fill/stroke accept CSS var() strings directly; DividendCalendar.jsx already
// proved this pattern works in this codebase).
export const CATEGORICAL = [
  "var(--chart-1, #3B82F6)",
  "var(--chart-2, #4EDEA3)",
  "var(--chart-3, #FFB95F)",
  "var(--chart-4, #A78BFA)",
  "var(--chart-5, #38BDF8)",
  "var(--chart-6, #FB7185)",
  "var(--chart-7, #FACC15)",
  "var(--chart-8, #64748B)",
];

export const NEUTRAL_COLOR = "var(--chart-8, #64748B)";
export const GAIN_COLOR = "var(--gain, #34D399)";
export const LOSS_COLOR = "var(--loss, #F87171)";

export const AXIS_TICK = { fill: "var(--muted, #8A93B3)", fontSize: 11 };
export const GRID_STROKE = "var(--hairline, #2A3245)";
export const TOOLTIP_STYLE = {
  background: "var(--surface-card-elevated, #1F2435)",
  border: "1px solid var(--hairline, #2A3245)",
  borderRadius: 8,
  color: "var(--ink, #DAE2FD)",
};
```

- [ ] **Step 2: `AllocationChart.jsx` / `BreakdownChart.jsx` / `StockDetail.jsx`'s ownership pie / `Analytics.jsx`'s sector pie**

In each, replace the local hardcoded array (e.g. `["#22c55e","#3b82f6",...]`) and `NEUTRAL_COLOR = "#94a3b8"` with:
```js
import { CATEGORICAL, NEUTRAL_COLOR } from "../lib/chartTheme";
```
and use `CATEGORICAL[i % CATEGORICAL.length]` wherever the old array was indexed. Replace every `stroke="#e2e8f0"`/`tick={{ fill: "#64748b", ... }}`/`contentStyle={{ background: "#ffffff", ... }}` occurrence in these files with `GRID_STROKE`/`AXIS_TICK`/`TOOLTIP_STYLE` from the same import.

- [ ] **Step 3: `PerformanceChart.jsx`, `Dashboard.jsx` benchmark lines, `Analytics.jsx` comparison chart**

Replace the ad hoc `#94a3b8`/`#cbd5e1` invested-line colors and `Dashboard.jsx`'s per-benchmark hex map (`sp500 #f59e0b`, `nasdaq100 #8b5cf6`, `dowjones #ec4899`, `stoxx50 #06b6d4`, `bitcoin #f97316`) with `CATEGORICAL[0]`..`CATEGORICAL[4]` (keep a stable index-per-benchmark mapping so the same benchmark always gets the same color across sessions). Portfolio/benchmark comparison lines in `Analytics.jsx` (`#22c55e` portfolio, `#9ca3af` benchmark, `#3b82f6` active) become `GAIN_COLOR`, `NEUTRAL_COLOR`, `CATEGORICAL[0]` respectively.

- [ ] **Step 4: `Dividends.jsx`, `DividendCalendar.jsx`**

`Dividends.jsx`'s `fill="#22c55e"` (paid) / `fill="#7c3aed"` (estimated) become `GAIN_COLOR` / `CATEGORICAL[3]` (Soft Iris, keeping the same paid/estimated visual distinction). `DividendCalendar.jsx`'s existing `fill="var(--brand, #059669)"` gets its fallback hex updated to `#3B82F6` (matching the new default Arctic Blue brand) — the var-reference pattern itself is already correct and doesn't need restructuring.

- [ ] **Step 5: `StockDetail.jsx`** (largest chart-color surface)

Replace: insider-trade buy/sell bars (`fill="#ef4444"`/`"#22c55e"` → `LOSS_COLOR`/`GAIN_COLOR`), earnings actual/estimate bars (`#22c55e`/`#3b82f6` → `GAIN_COLOR`/`CATEGORICAL[0]`), price-history average line (`avgStroke` ternary → same `GAIN_COLOR`/`LOSS_COLOR`/`NEUTRAL_COLOR` three-way), analyst-rating dot (`#8b5cf6` → `CATEGORICAL[3]`), ownership pie (Step 2 above), legend swatches (`bg-[#22c55e]`/`bg-[#3b82f6]` arbitrary Tailwind classes → `bg-gain`/`style={{backgroundColor: CATEGORICAL[0]}}` since Tailwind arbitrary values can't consume a JS import — use inline `style` for these two legend swatches specifically). Every axis/grid/tooltip occurrence in this file (~6 chart blocks) gets the same `AXIS_TICK`/`GRID_STROKE`/`TOOLTIP_STYLE` treatment as Step 2.

- [ ] **Step 6: `HeroSparkline.jsx` and `Heatmap.jsx`**

`HeroSparkline.jsx`: change `const color = positive ? "var(--brand)" : "#EF4444";` to `const color = positive ? "var(--brand)" : "var(--loss)";` (was half-tokenized — now fully). `Heatmap.jsx`: replace its independent 9-stop hardcoded gain→loss gradient with one derived from `--gain`/`--loss` using `color-mix()`:
```js
const STOPS = [
  { min: 3,    color: "color-mix(in srgb, var(--gain) 100%, black 15%)" },
  { min: 1.5,  color: "var(--gain)" },
  { min: 0.5,  color: "color-mix(in srgb, var(--gain) 70%, var(--surface-card) 30%)" },
  { min: 0,    color: "color-mix(in srgb, var(--gain) 35%, var(--surface-card) 65%)" },
  { min: -0.001, color: "var(--surface-card-elevated)" }, // ~0%, avoids float-equality edge case
  { min: -0.5, color: "color-mix(in srgb, var(--loss) 35%, var(--surface-card) 65%)" },
  { min: -1.5, color: "color-mix(in srgb, var(--loss) 70%, var(--surface-card) 30%)" },
  { min: -3,   color: "var(--loss)" },
  { min: -Infinity, color: "color-mix(in srgb, var(--loss) 100%, black 15%)" },
];
```
and replace the hardcoded `#FFFFFF`/`#1E293B` text-contrast switch and `backgroundColor: "#E2E8F0"` empty-cell fallback with `text-white`/`text-ink` and `var(--bg-subtle)` respectively.

- [ ] **Step 7: Test + visual check**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/frontend && npm test
```
Visit Dashboard (benchmark chart + heatmap), Allocation, Analytics, Dividends, DividendCalendar, and a Stock detail page — confirm every chart's colors, gridlines, and tooltips read correctly against the dark canvas (this is also where the pre-existing dark-mode chart bug the investigation found — static light-mode axis/tooltip colors — gets fixed as a side effect).

- [ ] **Step 8: Commit**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
git add frontend/src/lib/chartTheme.js frontend/src/components/AllocationChart.jsx frontend/src/components/BreakdownChart.jsx frontend/src/components/CashBalanceChart.jsx frontend/src/components/PerformanceChart.jsx frontend/src/components/StockDetail.jsx frontend/src/components/HeroSparkline.jsx frontend/src/components/Heatmap.jsx frontend/src/pages/DividendCalendar.jsx frontend/src/pages/Dividends.jsx frontend/src/pages/Analytics.jsx frontend/src/pages/Dashboard.jsx
git commit -m "feat: centralize chart colors in chartTheme.js, fix static-hex dark-mode chart bug"
```

---

### Task 7: Page sweep — replace raw Tailwind literals with tokens, page by page

**Files:** all 18 files in `frontend/src/pages/` (grouped into 7 sub-tasks below).

**Interfaces:**
- Consumes: every token/primitive from Tasks 1–6.
- Produces: zero raw `text-slate-*`/`bg-white`/`bg-slate-50`/`bg-slate-100`/`text-emerald-600`/`text-red-600` literals remaining anywhere in `frontend/src/pages/`.

**Mapping table (applies identically across every sub-task below — mechanical find/replace, verify each with a visual screenshot rather than expecting line-for-line diffs to be enumerated here given the volume: ~1,114 `className=` occurrences across these 18 files):**

| Find (raw Tailwind) | Replace with (token) |
|---|---|
| `text-slate-800`, `text-slate-900` | `text-ink` |
| `text-slate-700` | `text-ink` (or `text-muted` if it's clearly secondary copy — judge per line) |
| `text-slate-600`, `text-slate-500`, `text-slate-400` | `text-muted` |
| `text-slate-300` | `text-muted` (dark-mode-only faint text; re-check contrast after) |
| `hover:text-slate-800`, `hover:text-slate-700` | `hover:text-ink` |
| `bg-white` | `bg-surface-card` |
| `bg-slate-50`, `bg-slate-100` | `bg-surface-hover` (i.e. `var(--bg-subtle)`) |
| `hover:bg-slate-50`, `hover:bg-slate-100` | `hover:bg-surface-hover` |
| `border-slate-200`, `border-slate-100` | `border-hairline` |
| `text-emerald-600`, `text-emerald-500` | `text-gain` |
| `text-red-600`, `text-red-500` (P&L context only — NOT destructive-action buttons, which stay red per Task 3 Step 4's exception) | `text-loss` |
| `bg-emerald-50`, `bg-emerald-100` (gain-tinted chip backgrounds) | `bg-gain/10` |
| `bg-red-50`, `bg-red-100` (loss-tinted chip backgrounds) | `bg-loss/10` |
| `rounded-2xl` on any card-like container | `rounded-lg` |

Each sub-task: apply the mapping table to its files, run `npm test`, screenshot each page, and where a direct Stitch reference exists compare side-by-side against it (path noted per file below, all under `docs/design/stitch/stitch_portfyl_desktop/`).

- [ ] **Task 7a: Dashboard, PlatformLanding** — direct references: `portfyl_premium_dashboard/screen.png`, `portfyl_platform_landing_glass_edition/screen.png`. Apply the mapping table; additionally confirm `PortfolioHero`/`DashboardGrid`/`Heatmap`/earnings-calendar/insider-buys sections all read as one coherent dark-glass page (these were the components most likely to still carry stray light-mode assumptions given Dashboard's complexity per the investigation).
  - Commit: `git commit -m "style: re-skin Dashboard + PlatformLanding to Stitch tokens"`

- [ ] **Task 7b: Allocation, Transactions, Cash, Watchlists** — direct references for the first two: `portfyl_allocation_glass_edition/screen.png`, `portfyl_transactions_glass_edition/screen.png`, `portfyl_watchlists_glass_edition/screen.png`; Cash has no direct mockup (gap-fill: apply the same token system + table-row treatment as Transactions, since Cash is structurally a transaction-style ledger).
  - Commit: `git commit -m "style: re-skin Allocation, Transactions, Cash, Watchlists to Stitch tokens"`

- [ ] **Task 7c: Dividends, DividendCalendar** — direct reference for Dividends: `portfyl_dividends_glass_edition/screen.png`; DividendCalendar has no direct mockup (gap-fill: same summary-card + bar-chart + table language as Dividends, its nearest structural cousin — already routed through `MetricCard` in Task 5).
  - Commit: `git commit -m "style: re-skin Dividends + DividendCalendar to Stitch tokens"`

- [ ] **Task 7d: Analytics, Screener, Stock, Search** — direct references: `portfyl_analytics_glass_edition/screen.png`, `portfyl_stock_screener_glass_edition/screen.png`, `portfyl_stock_detail_expanded_financials/screen.png`; Search's reference image failed to export from Stitch (28-byte stub) but its `code.html` is intact — read that file's structure (search input + results list, per the investigation's extracted text) as the reference instead of a screenshot.
  - Commit: `git commit -m "style: re-skin Analytics, Screener, Stock, Search to Stitch tokens"`

- [ ] **Task 7e: TaxReport, Import, Settings** — direct references: `portfyl_tax_report_glass_edition/screen.png`, `portfyl_import_glass_edition/screen.png`, `portfyl_settings_glass_edition/screen.png`. Settings is the largest/most component-dense page (T212/IBKR/Polymarket connection cards, `DiscordSettings`, `SyncScheduleSettings`) — apply the mapping table throughout but confirm `DiscordSettings.jsx`'s Discord-blurple badge is left untouched per the Global Constraints exception.
  - Commit: `git commit -m "style: re-skin TaxReport, Import, Settings to Stitch tokens"`

- [ ] **Task 7f: Options, Polymarket** — direct reference for Polymarket: `portfyl_polymarket_glass_edition/screen.png`; Options has no direct mockup (gap-fill: same tabbed-card + summary-row language, IBKR balance card follows the `MetricCard` recipe from Task 5).
  - Commit: `git commit -m "style: re-skin Options + Polymarket to Stitch tokens"`

- [ ] **Task 7g: Assistant** — no Stitch reference at all (gap-fill). Design the chat surface within the locked token system: message bubbles use `bg-surface-card-elevated` (assistant) / `bg-brand text-white` (user), input bar uses `.input`, suggestion chips use the same pill treatment as `DeltaPill`/status chips (`rounded-full border border-hairline text-muted hover:border-brand hover:text-brand`), config panel (API key/model) reuses `.card` + `.input`. This is the one page invented from the token system with no image to check against — screenshot it and confirm it reads as unmistakably part of the same family as the 12 referenced pages, not a different app.
  - Commit: `git commit -m "style: design Assistant page in the Stitch token system (no reference mockup)"`

---

### Task 8: Light mode verification pass

**Files:** none new — this task is verification-only, fixing anything Tasks 1–7 got wrong for light mode specifically (Stitch is dark-only, so light mode is the one mode nothing was screenshot-checked against during the sweep).

**Interfaces:** consumes everything; produces confidence that Light/Dark/System toggle and all 3 accents work correctly in both modes.

- [ ] **Step 1: Toggle to Light in Settings/Sidebar, walk every page**

For each of the 18 pages, switch to Light mode and screenshot. Check specifically: text contrast against the new `#F3F5FB` canvas (the old per-palette pastel light backgrounds are gone, replaced by one neutral canvas — confirm nothing assumed a colored background), `MetricCard`/`.card`'s subtle gradient overlay isn't muddy on white, chart tooltips/gridlines read correctly (Task 6's `TOOLTIP_STYLE`/`GRID_STROKE` should adapt automatically via the CSS vars — this is the real test that the var-based approach works, not just a dark-mode-only implementation).

- [ ] **Step 2: Cycle all 3 accents in both modes**

Arctic Blue / Mint Green / Soft Iris × Light / Dark = 6 combinations. Screenshot the Dashboard and Settings pages (highest brand-color density) in each of the 6.

- [ ] **Step 3: Fix any defects found, re-run**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/frontend && npm test
```

- [ ] **Step 4: Commit** (only if Step 3 found something to fix)

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
git add -A
git commit -m "fix: light-mode and accent-cycling polish across pages"
```

---

### Task 9: Final verification

**Files:** none (verification + docs only).

- [ ] **Step 1: Full suite + build**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/frontend && npm test && npm run build
```
Expected: all pass, clean build.

- [ ] **Step 2: Playwright walkthrough of every page, dark mode, default accent (Arctic Blue)**

Start `start.bat`, log in, visit all 18 routes, screenshot each, confirm no console errors and no visual regressions vs. the Task 7 checkpoints.

- [ ] **Step 3: Side-by-side comparison against Stitch references**

For the 12 pages with a direct mockup (`docs/design/stitch/stitch_portfyl_desktop/portfyl_*`), place the real app screenshot next to the reference and confirm: canvas/card tonal ladder matches, typography (Plus Jakarta Sans headings, Inter body) matches, 8px card radius matches, pill chips match, glass blur/sheen is present on cards. Note any deliberate deviations (there should be none beyond the documented gap-fills).

- [ ] **Step 4: Update `CLAUDE.md`**

Add to the **Stack** section: `Visual design follows the Stitch-derived dark-glassmorphism token system (docs/design/stitch/) — see frontend/src/index.css :root and App.jsx PALETTES/DARK_SURFACES/LIGHT_TOKENS for the token source of truth.`

- [ ] **Step 5: Final commit**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
git add CLAUDE.md
git commit -m "docs: note the Stitch design-token system as the frontend's visual source of truth"
```

---

## Self-review notes (done at planning time)

- **Coverage**: token core → T1; typography → T2; shared primitives → T3; sidebar → T4; signature stat-tile → T5; charts → T6; all 18 pages → T7a–g; light-mode (Stitch's one blind spot) → T8; verification → T9. Every file the investigation flagged is accounted for.
- **Placeholder scan**: core/high-leverage files (T1–T6, Sidebar, MetricCard, chartTheme.js) have complete, exact code. Page-sweep tasks (T7) intentionally use a mapping-table + screenshot-verification format instead of enumerating ~1,114 individual className diffs — that volume makes per-line diffs redundant with just doing the mechanical replacement; the table is unambiguous and complete as a specification.
- **Type/token consistency**: every task references only the token table defined once at the top (no task invents a new hex outside it) — `--surface-card-elevated`, `--chart-1..8`, `--glass-*` are each defined exactly once (T1) and consumed identically everywhere else. `MetricCard`'s prop shape (T5) is preserved, not renamed, so existing call sites in Analytics/TaxReport need no signature changes.
- **Known judgment calls**: reconciled DESIGN.md's internal frontmatter/prose contradiction via pixel-sampling the actual screenshots rather than guessing; kept existing light-mode green/purple brand hex unchanged (already proven, no Stitch light reference to contradict them); made light mode hue-neutral across accents to mirror how dark mode already works (a deliberate small improvement, not scope creep — same mechanism, one fewer special case); excluded Discord's brand color from re-skinning; kept the destructive-action red in `ConfirmDialog` fixed rather than tying it to `--loss` (different semantic meaning).
