# Neumorphism theme style — design

## Context

Portfyl's frontend was fully reskinned to a "Stitch" dark-glassmorphism design
system in July 2026 (`docs/design/stitch/stitch_portfyl_desktop/`, commit
`1074fdd`). As a follow-on exploration, a Higgsfield-generated moodboard
(3 directions × Dashboard/Stock, then a full 16-page pass on the winning
direction) established **Soft Neumorphism** as a second, distinct visual
identity: warm light background, embossed cards with dual-tone soft shadows,
pastel mint/coral accents, rounded shapes, no blur.

The user wants both to coexist in the running app as two switchable "versions":
**Classic** (today's glass look, unchanged) and **Neumorphism** (new). This
spec covers making that switch real — not picking between the two.

## Goal

Add a **Theme style** control, next to the existing Appearance (Light/Dark/
System) and Accent pickers, that swaps the whole app between the existing
glass system and a new neumorphism system, instantly and per-device
(`localStorage`), the same way Appearance already works.

## Why this is a small change, architecturally

Portfyl's theming is already fully indirected through CSS custom properties
written by one function, `applyAppearance()` in `frontend/src/App.jsx`, which
sets `document.documentElement.style` properties directly — there is no
`[data-theme]` attribute and no `dark:` Tailwind variants anywhere in `src`.
Every page/component consumes color via Tailwind classes that resolve to
those vars (`bg-surface-card`, `text-ink`, `text-gain`, etc.) or, for charts,
via `frontend/src/lib/chartTheme.js`'s `var(--chart-N, #hex)` strings. That
means **most pages need zero code changes** — a second value table applied
by the same mechanism is enough for them to repaint correctly.

The parts that need real work are the handful of places that hardcode the
*glass* look structurally rather than through a token: `backdrop-filter: blur()`
and the glass sheen overlay on `.card`, the fixed corner radius on card/button/
pill primitives, and the three copy-pasted toggle-switch buttons that never
went through a shared component.

## Data model

- New `localStorage` key: **`sb_theme_style`**, values `"glass" | "neu"`,
  default `"glass"`. Additive, sibling to the existing `sb_theme` (light/dark/
  system) and `sb_palette` (accent) keys — neither of those is renamed or
  reused, per the naming rule in `CLAUDE.md`.
- `PaletteProvider` (App.jsx) gains `themeStyle` state + `setThemeStyle`,
  read from/written to `sb_theme_style`, exposed via the existing
  `PaletteContext` (`usePalette()` already returns `{ palette, setPalette,
  theme, setTheme }` — add `themeStyle, setThemeStyle`).
- **When `themeStyle === "neu"`, Light/Dark/System and the 5-swatch accent
  picker stop applying** — Neumorphism ships as the one fixed light
  appearance shown in the moodboard, not a fourth palette × 3 modes. The
  effect that calls `applyAppearance` short-circuits to the neu branch
  regardless of `theme`/`palette` state (their state is preserved, just inert,
  so switching back to Classic restores whatever the user had).

## Token changes

`applyAppearance(name, isDark, themeStyle)` gains a third parameter. When
`themeStyle === "neu"`, it writes one fixed table (`NEU_TOKENS`, new const
next to `PALETTES`/`DARK_SURFACES`/`LIGHT_TOKENS`) instead of doing the
palette/dark lookup, and additionally sets two vars that don't vary by mode
today but need to for neu:

| Token | Glass (unchanged) | Neu |
|---|---|---|
| `--bg` | existing per-mode value | `#EDEAE3` |
| `--bg-subtle` | " | `#E4E0D7` |
| `--surface-card` | " | `#EDEAE3` (same as `--bg` — neumorphic cards emerge from the page color via shadow, not a fill contrast) |
| `--surface-card-elevated` | " | `#F1EEE8` |
| `--border` / `--hairline` | " | `rgba(58,54,46,0.06)` (near-invisible — neu reads through shadow, not borders) |
| `--ink` | " | `#3A362E` |
| `--muted` | " | `#6B665A` |
| `--brand` / `--brand-hover` / `--brand-light` | per accent palette | `#27805F` / `#1F6A4E` / `#D9F1E8` |
| `--gain` / `--loss` | `#10B981` / `#EF4444` | `#27805F` / `#C05437` |

The four text-bearing values above are darkened from the moodboard's pastels
(`#8A8478` / `#4FBA95` / `#E88A72`). Measured on the `#EDEAE3` card, the
moodboard set gave muted 3.09, brand/gain 1.99, loss 2.10 — muted being the
only sub-AA value in *any* Portfyl style, and all four below their Classic-light
counterparts. The shipped values measure 4.76 / 4.03 / 3.83 (and 4.84 for white
button labels on `--brand`), clearing Classic light's 4.58 / 3.68 / 3.76 on
every token. The pastels remain in `--chart-*`, where they are large fills
rather than 11px table text.
| `--chart-1`…`--chart-8` | existing | `#4FBA95, #E88A72, #E3B873, #B6A7D1, #8FC5D6, #E3A6B0, #D9C9A6, #A69C8C` |
| `--shadow-ambient` | existing single ambient shadow | `6px 6px 14px rgba(190,178,158,0.55), -6px -6px 14px rgba(255,255,255,0.85)` (the embossed dual shadow — same var, no new name needed since it already holds an arbitrary box-shadow value) |
| `--blur-card` / `--blur-overlay` | `12px` / `20px` | `0px` (no-ops the existing `backdrop-filter: blur(var(...))` rules without touching their CSS) |
| `--glass-border-alpha` / `--glass-overlay-alpha` | existing | `rgba(0,0,0,0)` / `rgba(255,255,255,0)` (suppresses the glass sheen overlay/border tint entirely, same mechanism) |

Two genuinely **new** tokens, declared in `index.css` `:root` with glass-mode
defaults that are no-ops, then given real values only in the neu branch:

- `--shadow-inset` — glass default: `none`. Neu:
  `inset 3px 3px 8px rgba(190,178,158,0.5), inset -3px -3px 8px rgba(255,255,255,0.8)`.
  Used for "pressed in" states (selected segmented-control option, toggle
  track) where neumorphism's language calls for an inset rather than
  raised surface.
- `--radius-card` — glass default: `0.5rem` (matches today's `rounded-lg`,
  so this is a no-visual-change refactor for Classic). Neu: `1.5rem`.
  `Card.jsx`, `.btn-primary`/`.btn-ghost` (index.css), `DeltaPill.jsx`, and
  `MetricCard.jsx` switch their hardcoded `rounded-lg`/`rounded-full`-ish
  classes to `rounded-[var(--radius-card)]` so neu's noticeably rounder,
  pill-like shapes (seen throughout the moodboard) come through everywhere
  at once instead of per-component overrides.

`chartTheme.js` needs **no code changes** — `CATEGORICAL`, `GAIN_COLOR`,
`LOSS_COLOR`, `AXIS_TICK`, `GRID_STROKE`, `TOOLTIP_STYLE` are already pure
`var()` reads, so they repaint correctly once the vars above change.

## Component changes

1. **`Toggle.jsx`** (new, `components/ui/`) — extracted from the three
   copy-pasted toggle-switch buttons (`Settings.jsx` ×2 for T212/IBKR
   auto-sync, `DiscordSettings.jsx` ×1). Today they're hardcoded
   `bg-brand`/`bg-slate-300` with no theme awareness beyond that; the new
   primitive uses `--shadow-inset`/`--radius-card` so it reads as an
   embossed track+knob in neu and keeps its current flat look in glass
   (glass's `--shadow-inset: none` makes it a no-op there). This is a
   prerequisite refactor, not new scope creep — without it the three toggles
   would look identically "glass" even in neu mode.
2. **`Card.jsx`, index.css `.btn-primary`/`.btn-ghost`, `DeltaPill.jsx`,
   `MetricCard.jsx`** — swap hardcoded radius utility classes for
   `rounded-[var(--radius-card)]`.
3. **`Sidebar.jsx`** footer — add a third row, same shell as the existing
   Appearance/Accent rows (`<p class="text-[10px] text-muted mb-1.5">Style</p>`
   + a `SegmentedControl` with `options={[{value:"glass", label:"Classic"},
   {value:"neu", label:"Neumorphism"}]}`, bound to `themeStyle`/
   `setThemeStyle` from `usePalette()`). No changes needed to
   `SegmentedControl.jsx` itself — third reuse of an existing generic
   primitive. When `themeStyle === "neu"`, the Appearance and Accent rows
   render `disabled`/dimmed (not removed — removing them would shift layout
   and make it look broken rather than "currently inert").
4. **`App.jsx`** — `NEU_TOKENS` const; `applyAppearance` signature/logic
   change described above; `PaletteProvider` state + effect dependency
   array gains `themeStyle`.
5. **`index.css`** — add `--shadow-inset: none;` and `--radius-card: 0.5rem;`
   to the `:root` block (glass-mode no-op defaults only; the JS sets the
   real neu values, same pattern as every other token here).

No other page file (`Dashboard`, `Allocation`, `Analytics`, `Dividends`,
`Options`, `Polymarket`, `Screener`, `TaxReport`, `Transactions`,
`Watchlists`, `Import`, `Settings`, `Stock`, `Search`, `Assistant`,
`PlatformLanding`) needs direct changes — they inherit the new look through
the Tailwind-class-to-CSS-var indirection already in place.

## Explicitly out of scope

Carried over unchanged from the original Stitch reskin's documented
raw-literal exceptions (destructive-action red, Toast ring colors, `Home`
hero-gradient overlays, `Analytics` rating-tier array + correlation-matrix
scale, `Stock` TargetRangeBar/AnalystBar/null-score badge, `.btn-ghost`'s
literal hover border) — these were deliberately not tied to the
`--gain`/`--loss`/accent tokens in the original reskin and stay that way for
neu too; re-litigating them is a separate task, not part of this one.

Neumorphism does **not** get its own Light/Dark/System or 3-accent matrix in
this pass — it's the one fixed appearance from the moodboard. Adding that
flexibility later is possible (the token mechanism generalizes cleanly) but
is not requested here.

## Testing / verification

No frontend automated test suite exists (per `CLAUDE.md`, only backend
`pytest`); this is a frontend-only, purely visual change, so verification is
manual via Playwright MCP per the project's "Verifying UI changes" convention:
toggle Classic ↔ Neumorphism on Dashboard, Stock, Transactions (table-heavy),
and Settings (the new control + the refactored toggles), in both cases
confirming Classic is pixel-identical to before the change (the `--radius-card`/
`--shadow-inset` glass defaults are no-ops) and Neumorphism matches the
moodboard's mood (warm bg, embossed cards, mint/coral accents, no blur).

## Rollout

Default `sb_theme_style` is `"glass"` — existing users see no change until
they opt in. No backend/API/DB changes; nothing in this spec touches
`backend/`.
