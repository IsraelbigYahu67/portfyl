# Portfyl Mobile — Design

**Date:** 2026-07-18
**Status:** Approved (brainstorming session with visual mockups; navigation pattern and
Home-screen direction validated in the visual companion)

## Goal

A fully separate mobile version of Portfyl named **portfyl-mobile**: all features of the
desktop app, same visual identity, but the frontend redesigned from scratch for phone
screens. Entirely independent of the original — its own folder, git repo, backend, and
database. The frontend stays a plain, self-contained Vite + React app so it can later be
handed to Google AI Studio to produce a packaged native app.

## Decisions made during brainstorming

| Question | Decision |
|---|---|
| Platform | Mobile-first web app (PWA-installable), same stack as desktop |
| Separation | Full standalone copy: own backend + own SQLite DB at `ptf_m/portfyl-mobile` |
| Navigation | **B** — bottom tab bar + hamburger drawer mirroring the desktop sidebar |
| Bottom tabs | Home (Dashboard) · Allocation · Dividends · Activity (Transactions) |
| Build approach | Copy backend verbatim; rebuild frontend fresh, reusing the proven data layer |
| Visual identity | Keep the PC design language (palettes, fonts, light/dark), phone-adjusted layout |

## Project shape

New folder `c:/Users/tomzo/claude/ptf_m/portfyl-mobile`, initialized as its own git repo.
Nothing is shared with `portfyl` — changes to one never affect the other.

```
portfyl-mobile/
├── backend/            # verbatim copy of portfyl/backend (see Backend section)
│   └── portfyl.db      # copied from portfyl so the app starts with real data (zubik)
├── frontend/           # NEW mobile-first SPA (see Frontend section)
├── docs/superpowers/specs/   # this design doc, copied in
├── Dockerfile          # copied, unchanged (multi-stage, Cloud Run compatible)
├── start.bat           # adapted: backend port 8001, frontend port 5174
├── sample_portfolio.csv
├── .gitignore          # same rules as portfyl (db, venv, node_modules, dist, .superpowers)
├── CLAUDE.md           # adapted from portfyl's (ports, mobile-frontend conventions)
└── README.md           # short: what it is, how to run
```

**Excluded from the copy:** `__pycache__/`, `*.pre-dedupe-backup-*.db`, `frontend/dist`,
`node_modules`, `.venv` — all rebuildable or backup artifacts.

**Dev ports** (so both apps run side by side): backend **8001**, frontend **5174**.
Vite proxy (`/api`, `/login`, `/logout`) targets `http://localhost:8001`. `start.bat`
prints and opens `http://localhost:5174`.

## Backend — copied verbatim

All of `portfyl/backend` comes over unchanged: the 18 routers, auth gate (`sb_session`
cookie, `snowball-dev` dev password, `APP_PASSWORD` override), imperative startup
migrations (`_ensure_*` / `_backfill_*`), FX→CZK normalization, yfinance noise
suppression, `owner_id="default"` convention, and the pytest suite (`backend/tests/`,
7 modules, run with `python -m pytest tests/ -v`; pytest installed separately via
`uv pip install pytest`).

**Zero behavioral edits.** This is what guarantees "all features kept." The only change
in the backend directory is none at all — port selection lives in `start.bat` / uvicorn
args, not in code.

`backend/portfyl.db` is copied at creation time so the app starts with the user's real
portfolio data. The two databases diverge from then on (imports into one do not appear
in the other) — that is the point of full separation.

## Frontend — new app, proven data layer

### Stack (identical to desktop, minus one library)

React 18 + Vite 6 + TailwindCSS 3 + @tanstack/react-query 5 + axios +
react-router-dom 7 + recharts + lucide-react + @fontsource-variable
(Inter, Space Grotesk, JetBrains Mono) + react-dropzone (Import file picking) +
vitest/@testing-library. **Dropped:** `react-grid-layout` — no draggable dashboard on a
phone; Home is a fixed stack.

### Carried over as-is (or near-verbatim)

- `src/api.js` — the axios instance, **portfolio-scoping interceptor**,
  `PORTFOLIO_AGNOSTIC_PREFIXES` (`/portfolios`, `/market`, `/watchlists`, `/settings`),
  401→`/login` redirect, and every fetch helper. This file encodes the app's hardest-won
  conventions; it is not rewritten.
- `src/lib/` — `format.js`, `chartChanges.js`, `positionsPie.js` **with their tests**.
- `src/hooks/` — `useCountUp` (+test), `useStockReportConfig`.
- Theme system from `App.jsx` — `PALETTES` (green default / blue / purple),
  `DARK_SURFACES`, `LIGHT_TOKENS`, `applyAppearance()`, CSS-variable tokens, Tailwind
  config (`surface/brand/ink/muted/gain/loss` colors, font families). Same `sb_*`
  localStorage keys (`sb_currency`, theme/palette keys) — different origin, no clash,
  consistent muscle memory.
- Context providers: Currency, Portfolio, Palette (Platform if needed) — same contracts.
- `src/components/ui/` primitives (Card, Toast, ConfirmDialog, Skeleton, EmptyState,
  ErrorState, DeltaPill, SectionHeader, SegmentedControl) — same API, restyled for touch.

### New: mobile app shell

- **TopBar** — hamburger button, page title, portfolio-switcher pill (opens a bottom
  sheet listing portfolios; mirrors desktop's PortfolioSwitcher).
- **BottomTabs** — Home · Allocation · Dividends · Activity. Active tab tinted with the
  brand color. Hidden on the Assistant chat's keyboard-open state if it fights the
  keyboard (implementation detail).
- **Drawer** — slides from the left, mirrors the desktop sidebar 1:1 with grouped
  sections: **Portfolio** (Dashboard, Allocation, Analytics, Transactions, Cash),
  **Income** (Dividends, Dividend Calendar, Options, Tax Report), **Discover**
  (Screener, Watchlists, Polymarket, Search, Assistant), **System** (Import, Settings).
  Scrim behind it; swipe or scrim-tap to close.
- **BottomSheet** — new ui primitive used for filters, add-transaction, portfolio
  switcher, benchmark toggles, and everything that was a modal/popover on desktop.
- Layout rules: `100dvh` shell, safe-area insets (`env(safe-area-inset-*)`), touch
  targets ≥ 44 px, no hover-dependent affordances.
- **PWA**: `manifest.webmanifest` + icons + `theme-color` so it installs to a home
  screen. **No service worker** — market data must never be served stale from a cache.

### Routes — and flattening the desktop "platform" shell

The desktop app splits into three platforms (T212 suite, IBKR → Options,
Polymarket) with platform-conditional routes and `PlatformLanding` as the picker.
On a phone one app with one navigation is the right shape, so **portfyl-mobile
flattens the platforms**: all routes are registered unconditionally and Options /
Polymarket are ordinary drawer entries. `PlatformLanding` survives as the first-run
screen (no active portfolio yet) and as the portfolio picker; the `AutoLoad`
prefetcher carries over and warms the portfolio pages' cache.

Routes: `/` = Home (Dashboard, matching desktop), `/allocation`, `/analytics`,
`/transactions`, `/cash`, `/dividends`, `/dividend-calendar`, `/options`,
`/polymarket`, `/screener`, `/watchlists`, `/tax-report`, `/import`, `/settings`,
`/assistant`, `/search`, `/stock/:ticker`. Deep links keep working; the only
change is that `/options` and `/polymarket` are always reachable instead of
gated behind a platform switch. Login stays the backend-served page (unchanged).

### Page treatments (pattern rules + per page)

**Pattern rules:** wide tables → card lists; filters/actions → bottom sheets; modals →
bottom sheets; charts → full-width with touch tooltips; multi-column grids → stacked
sections; long lists → grouped by date with sticky group headers.

- **Home (Dashboard)** — gradient hero card (portfolio value, day change, currency
  toggle), period chips (7D/MTD/1M/3M/YTD/1Y/All), performance chart with benchmark
  toggle sheet, horizontally scrolling stat cards (invested, gain, dividends, …),
  Top movers card, holdings preview (top 5 + "All ›"), earnings + insider-buys cards.
  Fixed stack — no drag layout.
- **Allocation** — segmented control (sector/type/currency/account) + donut + breakdown
  list with percentage bars.
- **Analytics** — the desktop sections stacked full-width, one card per chart.
- **Activity (Transactions)** — date-grouped transaction cards, FAB "+" opens
  add-transaction bottom sheet; trade-note editing via sheet.
- **Cash** — balance chart + date-grouped ledger list.
- **Dividends** — summary stat cards + received/upcoming lists.
- **Dividend Calendar** — month selector + agenda-style list.
- **Options** — position cards + options calendar as a list.
- **Polymarket** — market cards.
- **Screener** — filter bottom sheet + result cards.
- **Watchlists** — watchlist chips + ticker card list, add/remove inline.
- **Tax Report** — year selector + report sections as cards.
- **Import** — big tap-target file picker (dropzone), replace-vs-append choice,
  broker sync (T212/IBKR) buttons with progress.
- **Settings** — grouped mobile settings list: appearance (palette/theme), currency,
  portfolios management, sync schedule, Discord, broker credentials.
- **Assistant** — full-height chat (already phone-shaped); input pinned above the
  keyboard.
- **Search** — full-screen search with recents; results navigate to Stock.
- **Stock detail** — price header + chart, position stats, fundamentals sections,
  notes. Reached from anywhere a ticker appears.
- **PlatformLanding** — full-screen portfolio picker (cards + create).

## Error handling

Same contracts as desktop: React Query retry/stale behavior, `ErrorState` per section,
global 401 → `/login` redirect (single-navigation guard), toasts for mutations,
yfinance-missing-data rendered as empty states (never errors).

## Testing & verification

1. **Backend proof-of-copy:** fresh uv venv in `portfyl-mobile/backend`, install
   requirements + pytest, `python -m pytest tests/ -v` — must pass identically to the
   original.
2. **Frontend unit:** vitest carries over; the copied `lib/` + `hooks/` tests must pass
   unchanged. New tests: app-shell navigation (tabs + drawer render, route switching)
   and a render test per major page with mocked fetch helpers.
3. **End-to-end visual:** Playwright MCP at a 390×844 viewport against
   `http://localhost:5174` — log in with the dev password, walk every drawer entry,
   screenshot each page; fix anything broken or unusable before calling it done.

## Non-goals

- No new features, no behavior changes — feature parity only.
- No offline mode / service worker.
- No app-store packaging (that is the user's Google AI Studio step; our contribution is
  a clean, conventional, self-contained frontend).
- No desktop optimization — it will render on desktop but is designed for phones.
- The original `portfyl` repo is untouched (apart from housing this spec).
