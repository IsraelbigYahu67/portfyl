# Portfyl — merge of portfyl-pc and portfyl-nb (design)

**Date:** 2026-07-03
**Goal:** Merge the two diverged repos `portfyl-pc` and `portfyl-nb` (same base, initial commit `e4e90868`) into one final, working, bug-free codebase in a new clean repo at `C:\Users\tomzo\claude\ptf_m\portfyl`.

## Decisions (confirmed with the user)

1. **Union of everything** — all features from both sides survive.
2. **PC look wins** on visual/UX conflicts (design tokens, fonts, DashboardGrid, UX overhaul direction).
3. **Destination:** new folder `ptf_m/portfyl`, fresh git history, single initial commit. Push target decided at the end.
4. **Data:** PC `snowball.db` is authoritative (verified: NB's 318 transactions are a strict subset of PC's 356; PC adds 64 options trades, 11 Polymarket positions, 4 broker connections). Placed in `backend/` locally, **never committed**.
5. **No known broken features**; app is started via `start.bat`.
6. **Merge mechanics:** real `git merge` (approach A) in a scratch working copy, then export the resolved tree into the clean repo.

## What each side contributes

**From PC** (~9,300 added lines):
- Backend: `auth.py` (password gate), `routers/ibkr.py`, `routers/options.py`, `routers/polymarket.py`, `routers/assistant.py`, `routers/discord.py`, `routers/notes.py`, `market_data.py`, expanded `models.py`/`main.py`.
- Frontend: platform concept (`PlatformLanding` → T212 / IBKR / Polymarket route sets), pages `Options`, `Polymarket`, `Assistant`, expanded `Settings`, `DashboardGrid`, `DiscordSettings`, `OptionsCalendar`, `TradeNoteModal`, `useStockReportConfig`.
- Design system: token expansion (type scale, ink/hairline/gain/loss, shadows, motion, reduced-motion), self-hosted fonts (Space Grotesk, Inter, JetBrains Mono), Vitest harness.
- Ops: `Dockerfile` (Cloud Run), `.dockerignore`, `CLAUDE.md`, UX overhaul plan doc.

**From NB** (~3,250 added lines):
- Backend: `routers/dividend_calendar.py`, screener endpoints in `market.py`, `cache.py` (TTL cache), FCF TTM fix (sum 4 quarters), test suite (`backend/tests/` — conftest, helpers, tests for analytics/broker/cache/dividend_calendar/fx/market/portfolio).
- Frontend: pages `Screener`, `DividendCalendar`, dark mode (light/dark/system in `PaletteProvider`, `DARK_SURFACES`, `dark` class), `AutoLoad` background prefetcher, UI kit (`Toast`, `ConfirmDialog`, `ErrorState`, `SegmentedControl`), `BreakdownChart`, StockDetail TTM columns + Shares Outstanding chart.
- Hygiene: project rename → **Portfyl**, `README.md`, `.gitignore` + `node_modules` removed from git, fixed `start.bat` (uv venv, no hardcoded interpreter path).

## Final repo layout

App flattened to repo root (no nested `snowball-analytics/` folder). `start.bat` uses `%~dp0`-relative paths and the Dockerfile copies `backend/` / `frontend/` relative to build context, so flattening is safe.

```
portfyl/
├── backend/          # FastAPI app, routers, tests; snowball.db local only
├── frontend/         # React 18 + Vite 6 + Tailwind SPA
├── docs/             # UX overhaul plan (PC) + this design doc
├── start.bat         # NB version (uv venv), "Portfyl" branding
├── Dockerfile        # PC (multi-stage, Cloud Run)
├── .dockerignore     # PC
├── CLAUDE.md         # PC, updated post-merge (routes, pages, run instructions)
├── README.md         # NB, updated post-merge
├── sample_portfolio.csv
└── .gitignore        # node_modules/, __pycache__/, dist/, *.db, .env, .venv/
```

Not carried over: `graphify-out/`, `.graphify_*`, root `snowball.db`, `.claude/` workspace configs, committed `node_modules`/`__pycache__`/`dist` artifacts.

## Conflict resolutions (file by file)

| File | Resolution |
|---|---|
| `frontend/src/App.jsx` | PC structure (PlatformProvider + platform-scoped routes) + NB's `ToastProvider`, `ConfirmProvider`, theme-aware `PaletteProvider` (light/dark/system + `DARK_SURFACES`), `AutoLoad`, and routes `/screener`, `/dividend-calendar` added to the T212 route set. PC's `usePrefetch` call removed. |
| Prefetch duplicate | **NB `AutoLoad` wins** (sequential, yfinance-friendly, exact cache keys). Delete PC `hooks/usePrefetch.js`. Extend AutoLoad: warm PC-only queries (`trade-notes-all`), run only when `platform === "t212"`. |
| `frontend/src/pages/Dashboard.jsx` | PC version (DashboardGrid). NB's layout restacking is superseded. |
| `frontend/src/components/StockDetail.jsx` | PC version as base; port NB's TTM-as-column rendering and Shares Outstanding chart if missing in PC. |
| `frontend/src/components/Sidebar.jsx` | PC version + NB nav links (Screener, Dividend Calendar) + dark-mode toggle affordance. |
| `frontend/src/index.css`, `tailwind.config.js` | PC token system + NB dark mode. Extend NB's dark handling to cover PC's full token set (ink, hairline, gain/loss, shadows). Tailwind `darkMode: "class"` from NB kept. |
| `frontend/src/api.js` | Union (PC endpoint helpers + NB additions). |
| `frontend/src/components/MetricCard.jsx`, `PortfolioSwitcher.jsx` | Union: PC behavior + NB dark-mode classes. |
| `frontend/index.html` | NB (Portfyl title, theme init) reconciled with PC font preloads. |
| `frontend/package.json` | Union of deps; `"name": "portfyl"`; regenerate `package-lock.json` via `npm install`. |
| `frontend/vite.config.js` | PC (vitest config + `/login`,`/logout` proxy). NB did not touch it. |
| `backend/main.py` | PC (auth, SPA fallback, all routers) + NB `dividend_calendar` router mount + NB idempotent migration helpers if any. |
| `backend/database.py` | Union of both changes. |
| `backend/routers/market.py` | Union: PC additions + NB screener endpoints + NB cache usage + NB FCF TTM fix. |
| `backend/routers/analytics.py`, `broker.py`, `portfolio.py`, `portfolios.py` | PC versions (NB didn't touch or trivial); verify via merge. |
| `start.bat` | NB version. |
| NB `backend/tests/` | Carried over; **must be adapted to PC's auth layer** (authenticate in `conftest.py` or bypass auth under test) — otherwise everything 401s. |

New files with no counterpart (PC's routers/pages, NB's Screener/DividendCalendar/ui kit/cache/tests) merge automatically.

## Verification (definition of "works, no bugs")

1. **Backend:** full NB pytest suite passes against the merged backend (auth handled in test setup).
2. **Frontend:** `npm install` + `npm run build` clean; Vitest tests (if present) pass.
3. **Live run:** backend :8000 + Vite :5173 via `start.bat` flow; drive the browser through: login → PlatformLanding → T212 Dashboard, Allocation, Transactions, Screener, Dividend Calendar, Stock detail, IBKR/Options, Polymarket, Settings; toggle dark mode — both themes must render correctly on PC-styled pages.
4. Fix anything found broken; re-verify.

## Out of scope

- Pushing to GitHub (decided at the end, once the user sees the result).
- Executing the PC UX overhaul plan (doc stays in `docs/` as future work).
- Multi-user auth (single-user `owner_id="default"` convention preserved).

## Risks

- **NB tests vs PC auth** — known, handled in test setup (see above).
- **Dark mode × PC tokens** — PC's new tokens have no dark variants yet; DARK_SURFACES must be extended and visually verified in both themes.
- **DB schema drift** — PC `main.py` runs idempotent `_ensure_*` migrations at startup; merged helpers from both sides must coexist. Using the PC DB (superset schema) minimizes risk; NB-added columns (if any) get ensured on first boot.
