# Portfyl design system (source of truth for the live app)

Read this file **before any frontend change** (colors, charts, cards, motion,
typography, new components). It describes what the app looks like *today*.
When you change the look, update this file in the same change.

Not to be confused with `.stitch/DESIGN.md` and
`docs/design/stitch/**/DESIGN.md`: those are Stitch mockup specs (an older
periwinkle clay variant) kept for history. Where they disagree with this file,
this file wins.

## 1. Look and feel

Portfyl is a calm, warm, **organic** finance workspace. Two warm appearances
share one palette and are light-only (they ignore Light/Dark/System):

- **Premium** (`neu`, the default) - frosted, translucent surfaces on a warm
  mesh gradient.
- **Clay** - the same palette with soft, inflated clay depth: raised surfaces
  with an inner highlight, pressed "wells" for inputs/tracks, pill controls,
  24px cards, floating sidebar. Light always comes from the **top-left**.

Classic (blue / green / purple brand, light and dark) still exists and is
untouched by the organic palette. It keeps its own vivid `GLASS_CHART` series.

Mood: tactile and friendly, but numbers stay crisp and serious. Never neon,
never flat-and-sharp, never glass-blur on Clay.

## 2. Where the tokens live (do not hardcode hex in components)

| What | File |
|---|---|
| Palettes, warm tokens (`NEU_TOKENS`, `CLAY_TOKENS`), chart series, contrast pairs | `frontend/src/lib/themeTokens.js` |
| Applying tokens as CSS variables per theme | `applyAppearance()` in `frontend/src/App.jsx` |
| Chart color/axis/tooltip helpers (`CATEGORICAL`, `NEUTRAL_COLOR`, `GAIN_COLOR`, `LOSS_COLOR`, `TOOLTIP_STYLE`...) | `frontend/src/lib/chartTheme.js` |
| Shape, shadow, hover and clay overrides (`.theme-clay`, `.hover-pop-zone`) | `frontend/src/index.css` |
| Tailwind color/font aliases (`bg-surface-card`, `text-ink`, `text-muted`, `text-brand`, `text-gain`...) | `frontend/tailwind.config.js` |

Use the Tailwind aliases or `var(--token)`; charts take colors from
`CATEGORICAL` / the `--chart-N` variables so they follow the active theme.
Opacity modifiers work on every alias (`bg-loss/10`, `border-brand/30`,
`ring-brand/30`): `tailwind.config.js` wraps each token in a `color-mix`
with an `<alpha-value>` slot. Keep that wrapper for any new color alias, or
Tailwind silently emits no CSS for its `/NN` classes.

## 3. Warm palette (Premium + Clay)

Surfaces and text:

| Token | Value | Use |
|---|---|---|
| `--bg` | `#F3E8DA` | page background (plus the warm mesh gradient) |
| `--bg-subtle` | `#ECE0CF` | pressed wells, tracks, inactive toggle trough |
| `--surface-card` | `rgba(250,245,237,0.78)` Premium / `0.86` Clay | cards |
| `--surface-card-elevated` | `rgba(253,249,243,0.92)` Premium / `0.94` Clay | sidebar, top bar, active pill |
| `--ink` | `#3A352C` | text, figures |
| `--muted` | `#6B6353` | secondary text, axis ticks (AA on the background) |
| `--hairline` / `--border` | `rgba(120,105,84,0.14)` | thin dividers (Clay hides card borders) |
| `--brand` | `#6D7048` | primary buttons, links, focus ring, active nav |
| `--brand-hover` | `#5C5F3C` | hover/pressed brand |
| `--brand-light` | `#E4E5D3` | tinted fills, active nav well, focus halo |
| `--gain` | `#5B7A4C` Premium / `#4A6A3C` Clay | positive P&L |
| `--loss` | `#B8543A` Premium / `#9E4129` Clay | negative P&L |

Gain and loss are never shown by color alone: always add an arrow or a +/-.

### Chart series (the "organic" palette)

Defined once in `NEU_TOKENS.chart` (Clay inherits it) and exposed as
`--chart-1..8` / `CATEGORICAL[0..7]`. Order matters: it is arranged so
neighbouring slices never sit light-on-light or dark-on-dark.

| # | Name | Hex |
|---|---|---|
| 1 | Leafy Green | `#8C8639` |
| 2 | Copper | `#8A4719` |
| 3 | Sunshine | `#B08623` |
| 4 | Ocean | `#3F5F5E` |
| 5 | Espresso | `#282119` |
| 6 | Sand | `#DCC892` |
| 7 | Evergreen | `#2E2C10` |
| 8 | Neutral warm grey (Cash, Other, "no category") | `#8A8478` |

Source swatches the user picked: Cream, Sand, Sunshine, Copper, Leafy Green,
Ocean, Espresso, Evergreen, Deep Sea. The Autumn / Fern / Sky row was
**deliberately excluded**. Cream (`#FFF2D8`) is left out because it vanishes
on cream cards; Deep Sea is left out because it is nearly identical to
Espresso and Evergreen; Sand is a touch deeper than its swatch so it reads on
the cards. Keep new series organic: earthy, saturated enough to read, no neon,
no cool pastel or purple/pink. Slot 8 is always the neutral for Cash/Other.

Classic themes keep `GLASS_CHART` (vivid blue/mint/amber/violet/sky/rose).

## 4. Shape and depth

- Radius: cards **24px** (Clay), nested elevated tiles 14px, inputs 16px,
  `rounded-xl` 20px, `rounded-2xl` 24px, sidebar/drawer 28px, buttons,
  segmented controls and the top bar are **pills (999px)**. Premium cards use
  `--radius-card` 1.25rem; Classic uses 0.5rem. Prefer rounder over sharper.
- Clay shadows (`.theme-clay` variables): `--clay-raise` (cards),
  `--clay-raise-hover`, `--clay-raise-sm` (small raised: active pill, ghost
  buttons), `--clay-inset-sm` (pressed wells, inputs, tracks),
  `--clay-raise-brand` (primary button). A raised shadow has a warm dark
  bottom-right half and a bright top-left half; insets invert it.
- Clay cards have no visible border; separation comes from depth.
- Pressed/inset = inputs, progress tracks, inactive toggle troughs, nested
  KPI tiles. Raised = cards, active segment, buttons.

## 5. Typography

- **Plus Jakarta Sans** (`font-display`, applied to h1-h3) for headings, KPI
  figures and eyebrow labels. **Inter** for body and tables. **JetBrains
  Mono** for tickers (600 weight).
- Tabular figures on everything numeric (`tabular-nums` / `.tnum`).
- Never set financial text or chart labels below **12px**. Use the semantic
  classes `.financial-headline`, `.financial-data`, `.financial-meta`,
  `.data-label`, `.chart-label`, `.eyebrow` instead of arbitrary sizes.
- Eyebrow: 12px, 600-700, uppercase, +0.05em tracking.

## 6. Charts

- Colors: only `CATEGORICAL`, `NEUTRAL_COLOR`, `GAIN_COLOR`, `LOSS_COLOR`,
  `SERIES_STYLES` from `chartTheme.js` (CSS vars), never raw hex.
- **Round everything.** Donuts: `paddingAngle={3}` and `cornerRadius` 7-9.
  Bars: `radius={[7, 7, 0, 0]}`; custom div bars use `rounded-t-xl
  rounded-b-lg` or rounder. Lines/areas: `strokeLinecap="round"
  strokeLinejoin="round"`, soft `monotone` smoothing, 2-3px strokes.
  Donut slices have no outline stroke (`stroke="none"`). Recharts drops
  rounding on slices too thin for `cornerRadius`, so feed donut data through
  `withSliceCorners` (`lib/pieCorners.js`) to keep small slices rounded.
- Grid lines barely visible (`GRID_STROKE`), axis ticks use
  `AXIS_TICK_STYLE` (12px, `--muted`), tooltips use `TOOLTIP_STYLE` or the
  `bg-surface-card-elevated` rounded tooltip pattern in `BreakdownChart`.
- Area fills are a faint gradient of the series color.
- Cash and "Other" always use `NEUTRAL_COLOR`.
- A donut slice scales 1.04 on hover (see section 7). To get that on a new
  donut, put the `pie-pop` class on the chart wrapper (inside a
  `.hover-pop-zone` page). The scale origin is the wrapper center; set
  `--pie-cy` if a legend moves the donut center.

## 7. Motion

All hover motion is opt-in per page with the `hover-pop-zone` class (used on
Dashboard and Allocation) and uses the standalone `translate`/`scale`
properties (not `transform`) so it composes with `animate-fade-up`.
Add `no-block-pop` next to it to keep donut-slice and button hover but leave
cards and tiles still (Allocation does this: its data/text blocks do not move).

- Spring easing: `cubic-bezier(0.34, 1.56, 0.64, 1)`, about 0.2-0.32s.
- Cards lift 4px and scale 1.01. **Cards that contain a chart
  (`.recharts-wrapper`) lift but never scale**, because scaling blurs the
  text inside. Small tiles (`.pop-tile`: KPIs, metric cards, hero chips)
  lift 3px and scale 1.04. Buttons lift 1px and scale 1.06 (0.97 on press).
- Donut slices scale 1.04 around the donut center (`.pie-pop`), the same
  small growth as a `.pop-tile`.
- Hand-drawn bar columns (`.bar-pop` on the column, `.bar-pop-bar` on the bar;
  `DividendBarsCard`) lift 3px and the bar grows 1.1x from its base with the
  `.pop-tile` brand glow. Unlike the rules above this works outside
  `.hover-pop-zone` (the Dividends page does not opt in).
- **Segmented control** (`components/ui/SegmentedControl.jsx`): one shared
  pill slides to the clicked option; its leading edge moves faster than the
  trailing edge (about 0.28s vs 0.45s), so it stretches and then settles like
  liquid pouring across. No animation on first render. Keep spring overshoot
  small (`cubic-bezier(0.34, 1.1, 0.64, 1)`) so the pill never pokes out of
  the trough.
- `prefers-reduced-motion` turns the hover scale/translate off and shortens
  transitions to ~0; any new motion must respect it.

## 8. Layout and components

- 4px base unit; 24-32px between sections, 24px card padding; keep at least
  24px between raised Clay cards so shadows do not collide.
- Primary action = brand pill; secondary = ghost pill (raised); icon buttons
  are circular.
- A selected choice card gets `outline outline-2 outline-offset-4
  outline-brand` plus a brand `Badge` ("Selected", with a check) and
  `aria-pressed`. Never signal selection with a border or ring alone: Clay
  hides card borders and owns the card box-shadow.
- Segmented controls and period selectors sit in an inset trough with a
  raised active pill (brand-colored bold text).
- Delta/gain-loss: tinted capsule or colored text, always with arrow or sign.
- Badges and dialogs: status labels use `components/ui/Badge.jsx`, a pill with
  six tones (`gain`, `loss`, `warn` = `--chart-3`, `info` = `--chart-4` blue,
  `neutral` = `--chart-8`, `brand`) drawn as a 16% `color-mix` tint of the tone token with text in the
  token, 12px semibold; never Tailwind palette classes. Dialogs use
  `components/ui/Modal.jsx`: an overlay plus a `.card` panel with
  `role="dialog"`, `aria-modal`, `aria-labelledby={titleId}`, focus trapped and
  restored to the opener (`useFocusTrap`), closing on Escape or a backdrop
  click, and no transform motion under reduced motion.
- Keyboard focus: 3px brand outline with 2px offset (Clay), 2px elsewhere.
- Touch targets at least 44px on mobile; right-align numbers in tables.
- **Phone shell (below `lg`)**: a sticky top bar (`MobileTopBar`: logo, compact
  `PortfolioSwitcher`, compact `AccountMenu` - the only phone log-out besides
  the drawer) and a fixed bottom bar (`MobileBottomNav`: Dashboard, Positions =
  Allocation, Transactions, Dividends, More). "More" opens the drawer, which
  also holds the account menu. Top bar, drawer and bottom bar share one rule in
  `index.css` that lays the translucent `--surface-card-elevated` over the solid
  `--bg` and blurs it, so page text never shows through; Clay floats the bottom
  bar as a raised pill. `AppShell` adds a spacer so content clears the bar.
- **Tables become cards on phones** (`useIsPhone()`, below 768px, renders only
  one layout): Allocation holdings and sold positions (`HoldingCards`, with a
  `CardSortBar`), insider buys and composition. Ticker and value on top, P&L and
  weight below, no sideways scrolling. Charts keep working; do not squeeze a
  10-column table into 390px.
- **Phone Dashboard**: `DashboardGrid` shows Top movers open and every other
  widget as a collapsed row (remembered in `sb_dashboard_phone_open_v1`);
  "Customize" still edits order and visibility.
- **Control rows scroll, they do not wrap** on phones: `SegmentedControl`,
  `UrlTabs` (right-edge fade while more tabs follow), the Dashboard period and
  benchmark chips and the chart legend. Buttons in them are 40px tall.
- Form controls are 16px on phones (iOS zooms the page for anything smaller);
  info icons and other tiny glyphs get a 44px hit area via `before:-inset-4`.
- Numbers follow the display currency everywhere (`formatMoney`,
  `formatQuantity`): CZK reads `5 224,05 Kč`, never `5,224.05 Kč`.

## 9. Checklist for a frontend change

1. Read this file. Reuse the tokens and classes above; do not invent colors.
2. New chart? Palette from `chartTheme.js`, rounded shapes, 12px labels,
   `pie-pop` for donuts.
3. New card/tile? Use `.card` / `.pop-tile`; no per-component shadows.
4. Edition-sensitive change? See the edition rules in `CLAUDE.md`.
5. Run `npm test` and `npm run build` in `frontend/`, then look at it in the
   browser (Premium and Clay) instead of judging from the diff.
6. If the look changed (palette, radii, motion), update this file.

## 10. Public landing (portfyl.com)

The cloud edition's public home (`pages/Welcome.jsx` + `Welcome.css`, plus
its first-visit language picker) always renders **Clay**, whatever appearance
a signed-in user picked. It renders outside `App.jsx`, so `applyAppearance()`
never runs there: `Welcome.jsx` scopes the `CLAY_TOKENS` variables onto the
`.welcome` root (`CLAY_STYLE`) and adds `theme-clay`, which resolves the
`--clay-*` shadows from `index.css`. `Welcome.css` holds no hex colors; tints
are `color-mix()` of the chart tokens.

Landing-specific pieces: a floating pill header (like `.app-topbar`, without
blur), soft raised clay blobs behind the hero window, the broker ribbon as an
inset trough with raised chips, raised 24px feature cards and 20px FAQ cards,
an inset showcase panel, and the app's `SegmentedControl` for the language and
preview switches (the preview trough is 24px, not a pill, because it wraps to
two rows). Same motion rules as section 7, opt-in per element.

The public legal pages `/terms` and `/privacy` (`pages/Legal.jsx` +
`Legal.css`, cloud only) reuse the landing's Clay root (`lib/clayStyle.js`),
pill header and footer. The text sits in one raised 24px card with a sticky
contents list beside it (a collapsible inset well below 1024px). Tables are
inset wells that stack into labelled cards on phones, so the page never
scrolls sideways. An unfinished `[[TODO]]` placeholder from `docs/legal/`
renders as a pending `mark`, tinted like Badge's `warn` tone (`--chart-3`).
