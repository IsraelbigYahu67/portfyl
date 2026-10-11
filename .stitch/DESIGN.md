---
name: Portfyl Clay
colors:
  background: '#E9EDF8'
  surface: '#EEF1FA'
  surface-container-lowest: '#FFFFFF'
  surface-container-low: '#F6F8FE'
  surface-container: '#EEF1FA'
  surface-container-high: '#E2E7F5'
  surface-container-highest: '#D5DCEF'
  on-surface: '#10162B'
  on-surface-variant: '#4F5875'
  outline: '#8B94B3'
  outline-variant: '#D5DCEF'
  primary: '#047857'
  on-primary: '#FFFFFF'
  primary-container: '#C9F3E1'
  on-primary-container: '#064E3B'
  secondary: '#6D5BD0'
  on-secondary: '#FFFFFF'
  secondary-container: '#E4DEFB'
  on-secondary-container: '#2E2555'
  tertiary: '#B45309'
  on-tertiary: '#FFFFFF'
  tertiary-container: '#FFE3B8'
  on-tertiary-container: '#472A00'
  error: '#C62828'
  on-error: '#FFFFFF'
  error-container: '#FFD9D6'
  on-error-container: '#690005'
  gain: '#0E9E70'
  loss: '#DC2626'
  shadow-light: '#FFFFFF'
  shadow-dark: '#B7C0DC'
typography:
  display-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 52px
    fontWeight: '800'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 18px
    fontWeight: '700'
    lineHeight: 26px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 12px
    fontWeight: '700'
    lineHeight: 16px
    letterSpacing: 0.05em
  numeric-data:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
rounded:
  sm: 0.75rem
  DEFAULT: 1rem
  md: 1.25rem
  lg: 1.75rem
  xl: 2rem
  full: 9999px
spacing:
  unit: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  gutter: 24px
  margin-desktop: 40px
  margin-mobile: 16px
  max-width: 1440px
---

# Design System: Portfyl Clay

## 1. Visual Theme & Atmosphere

Portfyl Clay is a **claymorphism** reinterpretation of an investor's portfolio-analytics workspace. Every container looks like a piece of soft, inflated modelling clay resting on a pale periwinkle table: fat rounded corners, a bright highlight on the top-left edge, a gentle shade on the bottom-right, and a wide, diffused drop shadow underneath. Surfaces feel tactile and friendly, like pressable pillows, but the numbers inside them stay crisp, serious and instantly legible. It must still read as a trustworthy finance tool, never a toy.

The mood is calm, optimistic and approachable. Generous breathing room replaces hairline borders: depth does all the separating work. Colour is used sparingly on top of cool off-white clay — one confident emerald for primary actions and growth, with violet, amber, sky and rose appearing only as chart series and tags. The app is light-first in this variant; dark mode is out of scope here.

## 2. Color Palette & Roles

### Primary Foundation
- **Periwinkle Mist Canvas** (`#E9EDF8`) — page background, the "table" the clay sits on.
- **Cool Clay Surface** (`#EEF1FA`) — default card body.
- **Soft Cloud White** (`#F6F8FE`) — raised cards, hero panel, active segmented-control pill.
- **Pure Highlight White** (`#FFFFFF`) — the top-left highlight shadow colour and the brightest inner glow.
- **Pressed Lavender Well** (`#E2E7F5`) — inset wells: inputs, progress tracks, inactive segmented-control troughs.

### Accent & Interactive
- **Deep Growth Emerald** (`#047857`) — primary buttons, active navigation, links, focus ring. White text on it passes AA.
- **Mint Clay** (`#C9F3E1`) — tinted fills behind active nav items and primary-tinted chips.
- **Soft Violet** (`#6D5BD0`) / **Lilac Clay** (`#E4DEFB`) — secondary series and tags.
- **Warm Amber** (`#B45309`) / **Apricot Clay** (`#FFE3B8`) — warnings, earnings-date tags, third chart series.

### Typography & Text Hierarchy
- **Midnight Ink** (`#10162B`) — headings, financial figures.
- **Slate Periwinkle** (`#4F5875`) — secondary text, labels, axis ticks (AA on every clay surface).
- **Fog Outline** (`#8B94B3`) — decorative strokes only, never body text.

### Functional States
- **Gain Green** (`#0E9E70`) — positive P&L, up arrows, gain pills (always paired with an arrow or +, never colour alone).
- **Loss Red** (`#DC2626`) — negative P&L, down arrows, loss pills (always paired with an arrow or −).
- **Shadow Highlight** (`#FFFFFF`) and **Shadow Shade** (`#B7C0DC`) — the two halves of every clay shadow.

## 3. Typography Rules

### Hierarchy & Weights
- **Plus Jakarta Sans** (geometric, friendly, slightly wide) for headings, KPI numbers and eyebrow labels. Weights 700–800 so text holds its own against heavy shapes.
- **Inter** for body copy, tables and data; tabular figures on everything numeric.
- Net-worth hero figure: 52px / 800 / tight tracking. Section titles: 18px / 700. Eyebrow labels: 12px / 700, uppercase, +0.05em tracking.
- Ticker symbols use a monospace face (JetBrains Mono) at 600 weight.

### Spacing Principles
Line-height relaxed (1.4–1.5) for data, tight (1.0–1.1) for display numbers. Never set financial text below 12px.

## 4. Component Stylings

### Clay Elevation Recipe (applies to every raised container)
- Outer shadow: `8px 8px 20px #B7C0DC` (bottom-right shade) plus `-6px -6px 16px #FFFFFF` (top-left highlight), both soft and wide.
- Inner glow: `inset 2px 2px 4px rgba(255,255,255,0.9)` and `inset -3px -3px 6px rgba(183,192,220,0.35)` so the surface looks puffy and rounded.
- No visible borders. A faint 1px `rgba(255,255,255,0.6)` rim at most.
- **Pressed / inset** elements (inputs, tracks, inactive toggles) invert it: inset dark shade bottom-right, inset white highlight top-left, no outer shadow.

### Buttons
- Primary: Deep Growth Emerald pill, fully rounded, white 600 text, clay elevation recipe in emerald-tinted shade (`rgba(4,120,87,0.35)`); on hover lifts 2px, on press sinks (inset) with 120ms ease.
- Secondary / ghost: Cool Clay Surface with the standard raised recipe and Midnight Ink text; no border.
- Icon buttons: 40px circular clay bubbles.

### Cards & Containers
- Corner radius 28–32px for cards, 20px for nested chips/tiles. Internal padding 24px (hero: 32px).
- Cards sit raised; nested KPI tiles inside a card are **inset wells** to create a two-level puffy hierarchy.
- Interactive cards lift 2px and gain a slightly larger shadow on hover.

### Navigation
- Left sidebar is one tall raised clay slab with a 32px radius, floating 16px away from the viewport edge. Items are 44px tall pills; the active item is a pressed-in Mint Clay well with emerald icon and bold label; others are flat text with Slate Periwinkle icons. Group headings are small uppercase eyebrow labels.
- Top bar: transparent on the canvas, with a circular clay avatar and portfolio switcher pill.

### Inputs & Forms
- Pressed Lavender Well fill, inset shadow, 16–20px radius, no border; focus adds a 3px Mint Clay ring plus emerald caret.

### Segmented Controls & Tabs
- The trough is an inset well; the active segment is a raised Soft Cloud White pill with emerald text and bold weight. Same pattern for period selectors (7D / MTD / 1M / 3M / YTD / 1Y / All) and stock tabs.

### Domain-Specific Components
- **Delta pill**: small clay capsule, gain/loss tinted background at ~15% with arrow icon and signed percentage.
- **KPI tile**: inset well with eyebrow label and bold tabular number.
- **Holdings bar row**: ticker (mono) + inset track with a rounded emerald raised fill + percentage + value.
- **Charts**: lines 3px thick with round caps and soft smoothing, area fill as a faint gradient of the series colour, grid lines barely visible, chart sits in an inset well or directly on a raised card. Series palette: emerald, violet, amber, sky `#38BDF8`, rose `#FB7185`.

## 5. Layout Principles

### Grid & Structure
12-column grid, max content width 1440px, 24px gutters, sidebar 256px. Cards snap to the grid; dashboard sections reflow by priority with KPIs top-left.

### Whitespace Strategy
4px base unit. 24–32px between sections, 24px card padding, 40px page margins on desktop, 16px on mobile. Clay needs space around it so shadows never collide — minimum 24px between adjacent raised cards.

### Alignment & Visual Balance
Left-aligned text, right-aligned numbers in tables. Visual weight comes from the hero card and the main chart; secondary lists stay quieter.

### Responsive Behavior & Touch
Desktop-first. Below 1024px the sidebar collapses into a bottom/top bar of clay bubbles; grids collapse to one column; touch targets ≥ 44px.

## 6. Design System Notes for Stitch Generation

### Language to Use
"soft inflated clay surfaces", "puffy rounded cards with a top-left highlight and bottom-right shade", "pressed-in inset wells", "pill-shaped tactile buttons", "pastel periwinkle canvas", "diffused wide drop shadows". Avoid: flat, hairline borders, glass blur, neon glows, sharp corners.

### Color References
Periwinkle Mist Canvas `#E9EDF8`, Cool Clay Surface `#EEF1FA`, Soft Cloud White `#F6F8FE`, Deep Growth Emerald `#047857`, Mint Clay `#C9F3E1`, Midnight Ink `#10162B`, Slate Periwinkle `#4F5875`, Gain Green `#0E9E70`, Loss Red `#DC2626`.

### Component Prompts
- "A net-worth hero card: huge bold figure, small gain pill, four inset KPI tiles underneath, faint area sparkline behind."
- "A segmented period selector sitting in an inset trough with a raised white active pill."
- "A holdings list with mono tickers, inset progress tracks and emerald raised fills."

### Incremental Iteration
Generate the shell and hero first, then refine chart and table cards one at a time; keep shadow direction (light from the top-left) identical on every element.

## 7. Source Extraction Notes (current app, for reference)

Extracted from `frontend/src` (index.css, tailwind.config.js, lib/themeTokens.js, Dashboard.jsx, Stock.jsx, PortfolioHero.jsx, StockHeader.jsx, StockOverviewTab.jsx):
- Current style: Stitch-derived dark glassmorphism (classic) with optional light and a warm "Premium" neumorphic hybrid; cards use `--radius-card` 0.5rem (premium 1.25rem), blurred translucent surfaces, 1px hairline borders, one ambient shadow.
- Fonts: Plus Jakarta Sans (display), Inter (body), JetBrains Mono (tickers). Retained.
- Brand: emerald (default), blue and purple alternates; gain `#0E9E70`, loss `#EF4444`. Retained (loss deepened for AA on light).
- Dashboard structure: header with Customize/Refresh → Net Worth hero (4 KPI chips) → Portfolio Performance chart (Value / Growth %, 7 period buttons, 5 benchmark toggles) → Concentration (Heatmap + Top 10 Holdings) → Needs attention (Attention signals + Earnings Calendar) → Insider activity (collapsible table) → Top Movers (Gainers/Losers, %/$ sort, Today/Week/Month).
- Stock detail structure: Back link → single card with identity header (ticker, name, sector, country, price + change, watchlist button) → five tabs (Overview, Financials, Valuation, Ownership, Filings) → Overview: quick stats, 52-week range, one-year price chart, "Your position" panel, About.
- Sidebar groups: Portfolio (Dashboard, Allocation, Transactions, Cash), Research (Search, Watchlists), Insights (Dividends, Analytics), Assistant, System (Import, Settings).

## 8. Mockup v2 — Snowball-inspired layout (2026-10-10)

The current mockup is `mockups/clay-mockup.html` + `mockups/clay.css`; v1 (sidebar + big hero) is kept as `clay-mockup.v1.html` / `clay.v1.css`.
**Colours: v2 uses the Portfyl "Premium" palette documented in the header of `clay.css`, not the periwinkle values in the front matter above.**

Borrowed from Snowball Analytics (structure and density), rendered in Portfyl's warm clay style:
- **Top navigation pill** instead of the 12-link sidebar: Dashboard · Analytics · Portfolio · Research · Dividends, with AI button, primary "+ Add", search, watchlists, portfolio switcher, currency and avatar on the right.
- **Four KPI cards** (Value · Total profit · IRR · Passive income), each with a tinted icon tile, "?" help dot and one sub-line (invested / today / current holdings / annual income).
- **Portfolio insights** row of dismissible cards with a type tag and one action (replaces "Attention signals").
- **Composition**: donut with an inner actual ring and thin outer target ring + category table (Value/Invested, Gain, Allocation actual · target with drift in pp, Total row). Uses Portfyl's allocation targets.
- **Performance** card gains a one-line verdict banner ("ahead of the S&P 500 by +10.1 pp").
- **Top gainers / Top losers** as two cards with logo circles, name + ticker, position value and day change.
- **Future payments / Dividends received** bar cards with two mini KPIs each.
- **Underline tabs** with icons on the stock detail (Overview, Financials, Valuation, Dividends, Ownership, Filings).
- Change values use Snowball's "▲/▼ + coloured text" instead of pills; card radius 24px (v1: 30px), softer shadows, sentence-case labels instead of uppercase eyebrows.
