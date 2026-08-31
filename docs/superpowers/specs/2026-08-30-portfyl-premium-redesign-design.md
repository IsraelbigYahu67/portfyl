# Portfyl Premium Redesign — Design Spec

**Date:** 2026-08-30
**Status:** Approved (brainstorming complete)
**Plan:** `docs/superpowers/plans/2026-08-30-portfyl-premium-redesign.md`

## Goal

Give Portfyl a modern, premium look — a warm glassmorphism/neumorphism hybrid
built on a user-supplied earthy palette — with tasteful animations, smooth
UX, and highly readable text. Every metric on the **Stock Detail** page moves
into its own rounded **KPI box**; the new look rolls out app-wide through the
shared token system and shared components.

## Approved decisions (from brainstorming Q&A)

1. **Scope:** Global design-system retune + shared-component upgrade (so all
   ~17 pages inherit the premium look) + **deep** rebuild of Stock Detail +
   showcase polish on Dashboard/Overview. Not a hand-crafted page-by-page pass.
2. **Theme approach:** Retune the existing light **`neu`** (Soft Neumorphism)
   theme to the user's palette and make it the **default** look. The `glass`
   (Classic) theme stays available in the switcher. Relabel `neu` → **"Premium"**.
3. **Dark mode:** Light-only premium look (matches the all-light palette;
   `neu` was already light-only). `glass` keeps its light/dark.
4. **Animations:** Tasteful & subtle only. No WebGL backgrounds.

## Palette (user-supplied)

| Hex | RGB | Role in design |
|---|---|---|
| `#a9ab88` | 169,171,136 | sage — primary accent (fills, chart 1, brand-light) |
| `#dbaa89` | 219,170,137 | peach — secondary accent (chart 2, badges) |
| `#d4c3a1` | 212,195,161 | sand — chart 3, surfaces |
| `#b7afa3` | 183,175,163 | warm gray — chart 4, hairlines |
| `#f3e8da` | 243,232,218 | cream — app background base |

**Contrast note:** the raw sage/peach are too light for small text on cream
(WCAG AA fails). They are used for **fills, backgrounds, borders, chart series,
and accent washes**. For small text/links/button labels we use darkened
derivatives (`--brand #6D7048`, etc.). This mirrors how the existing `neu`
theme already handles it. Gain/loss stay clearly distinct (finance data).

## Design tokens (the retuned `NEU_TOKENS`)

These replace `NEU_TOKENS` in `frontend/src/App.jsx`. All hues verified to
clear WCAG AA on the `#F3E8DA` card except where noted (the plan includes a
contrast-verification step).

```
bg                 #F3E8DA   (cream) + warm CSS mesh gradient on <body>
bgSubtle           #ECE0CF   (wells, hover tracks)
surfaceCard        rgba(250,245,237,0.78)   ← translucent = the "glass"
surfaceCardElevated rgba(253,249,243,0.92)  ← KPI boxes, popovers
border / hairline  rgba(120,105,84,0.14)
ink                #3A352C   primary text (AAA on cream)
muted              #6B6353   secondary text (AA)
brand              #6D7048   (darkened sage) fills + links + button labels
brandHover         #5C5F3C
brandLight         #E4E5D3   (pale sage wash) sidebar-active, chips
gain               #5B7A4C   (deep sage-green)
loss               #B8543A   (terracotta)
glassBorderAlpha   rgba(120,105,84,0.16)
glassOverlayAlpha  rgba(255,252,247,0.55)   top-left highlight on .card
blurCard           14px
blurOverlay        22px
shadowAmbient      7px 7px 18px rgba(190,172,146,0.5), -7px -7px 18px rgba(255,253,248,0.9)
shadowInset        inset 3px 3px 8px rgba(190,172,146,0.45), inset -3px -3px 8px rgba(255,253,248,0.85)
radiusCard         1.25rem
chart              [#A9AB88, #DBAA89, #D4C3A1, #B7AFA3, #7C8A5A, #C08457, #9E8E6E, #8A8478]
```

**Hybrid mechanism:** neumorphic soft dual shadows (`shadowAmbient`) **+**
translucent surfaces with `backdrop-filter: blur()` **+** a warm mesh gradient
behind everything (so the frosted glass has something to refract). The existing
`.card` class already reads all of these from CSS vars, so retuning the vars +
enabling blur/alpha for the premium theme is most of the work.

## react-bits usage (dependency-free)

The user asked to use the react-bits MCP server. We vendor the components as
JSX under `frontend/src/components/reactbits/`, **without adding any npm
dependency** (the upstream animated variants pull in `motion`/`gsap`; we adapt):

- **SpotlightCard** — vendored verbatim (TSX→JSX), hardcoded dark colors
  removed so it inherits the theme. Warm radial hover glow on KPI boxes/cards.
- **ShinyText** — adapted to a pure-CSS clip-gradient sweep (no `motion`).
  Subtle shine on hero headings/eyebrows.
- **Reveal** — plays react-bits `AnimatedContent`'s role (fade+lift on scroll)
  via `IntersectionObserver` + CSS (no `gsap`).
- **Count-up** — reuse the existing `frontend/src/hooks/useCountUp.js`
  (respects `prefers-reduced-motion`) instead of react-bits `CountUp`.

All animation respects `prefers-reduced-motion` (existing global CSS already
neutralizes animations under that query).

## New / changed component inventory

- **New** `components/reactbits/SpotlightCard.jsx`, `ShinyText.jsx`, `Reveal.jsx`
- **New** `components/ui/KpiBox.jsx` — the reusable premium KPI tile
  (label + count-up value + optional delta pill/sub/icon/info; never truncates;
  spaced numbers). Exported from `components/ui/index.js`.
- **New** `lib/format.js` helpers: `formatNumberSpaced`, `formatMoneySpaced`
  (space thousands separators + comma decimals — "1 234 567,89 Kč").
- **Changed** `App.jsx` — retuned `NEU_TOKENS`, `applyAppearance` premium
  branch (glass hybrid + `theme-premium` class), default theme = premium (+
  one-time migration), .
- **Changed** `index.css` — `.theme-premium body` mesh gradient, `.shiny-text`
  keyframes.
- **Changed** `Sidebar.jsx` — style label "Neumorphism" → "Premium".
- **Changed** `MetricCard.jsx` — premium look (spotlight + count-up + spacing),
  **same prop API** (used on 8 pages → global rollout, no call-site edits).
- **Changed** `StockDetail.jsx` — `QuickStat`, ratios table, header hero, 52w
  range, `OwnershipStat`, dividend tiles → KPI boxes; section reveals.
- **Changed** `Dashboard.jsx`, `Overview.jsx` — showcase reveals + hero shine.

## Non-goals / constraints

- No new npm dependencies.
- Do not change the `glass` theme's appearance or the blue/green/purple accents.
- Keep `sb_*` localStorage keys and single-user `owner_id="default"` behavior.
- Keep all existing Vitest tests green; add tests for new pure logic.
- Charts stay charts (they get glass-card framing + warm colors, not KPI boxes).
- KPI-box-per-metric is required on Stock Detail; used elsewhere only where it
  reads well (MetricCard upgrade covers the dashboards).

## Verification

- `npm run build` and `npm test` (from `frontend/`) both clean.
- Playwright drive `http://localhost:5173` (dev password `snowball-dev`),
  screenshot Stock Detail + Dashboard, confirm: readable text, spaced numbers,
  KPI boxes with rounded corners, warm glass look, working hover/reveal.
- Manual contrast check on `--muted`, `--gain`, `--loss` against `#F3E8DA`.
