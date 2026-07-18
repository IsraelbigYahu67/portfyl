# Portfyl Mobile Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `ptf_m/portfyl-mobile` — a fully standalone mobile version of Portfyl: backend copied verbatim, database seeded from the original, and a brand-new mobile-first frontend (bottom tabs + drawer) with feature parity across all 17 pages.

**Architecture:** Two-part monorepo mirroring portfyl: `backend/` is an untouched copy of the FastAPI app (18 routers, imperative startup migrations, SQLite); `frontend/` is a new React 18 + Vite SPA that reuses portfyl's proven data layer (`api.js` interceptor, lib helpers, theme system) under a new mobile shell (TopBar + BottomTabs + Drawer + BottomSheet). The desktop "platform" shell is flattened into one navigation.

**Tech Stack:** FastAPI + SQLAlchemy + SQLite (unchanged) · React 18, Vite 6, TailwindCSS 3, @tanstack/react-query 5, axios, react-router-dom 7, recharts, lucide-react, react-dropzone, vitest + @testing-library.

**Spec:** `docs/superpowers/specs/2026-07-18-portfyl-mobile-design.md` (approved). Read it before starting any task.

## Global Constraints

- **Never edit anything under `portfyl-mobile/backend/`** — it is a verbatim copy; all behavior lives there and must not drift. (Exception: none. Port selection lives in `start.bat`.)
- **The original repo `c:/Users/tomzo/claude/ptf_m/portfyl` is read-only reference material.** Never modify it.
- Dev ports: backend **8001**, frontend **5174** (so portfyl on 8000/5173 can run simultaneously).
- Dependencies exactly as portfyl's `frontend/package.json` **minus `react-grid-layout`**; no additions without a spec change.
- **No service worker.** PWA = manifest + icons only.
- Keep `sb_*` localStorage keys (`sb_theme`, `sb_palette`, `sb_currency`, `sb_portfolio_id`), the `/api` axios base, and `PORTFOLIO_AGNOSTIC_PREFIXES = ["/portfolios", "/market", "/watchlists", "/settings"]` unchanged.
- Styling: only Tailwind token classes from `tailwind.config.js` (`bg-surface`, `bg-surface-card`, `text-ink`, `text-muted`, `border-hairline`, `text-brand`/`bg-brand`, `text-gain`, `text-loss`) — no hard-coded hex in pages. Fonts: `font-display` (Space Grotesk) for big numbers/headings, `font-sans` (Inter) body, `font-mono` (JetBrains Mono) tickers.
- Mobile idioms everywhere: touch targets ≥ 44px, `100dvh` shell, `env(safe-area-inset-*)` padding, bottom sheets instead of modals/popovers, card lists instead of tables, no hover-only affordances.
- For every page task: the desktop page at `c:/Users/tomzo/claude/ptf_m/portfyl/frontend/src/pages/<Name>.jsx` is the **authoritative feature spec**. Its import list from `../api` is the exact set of fetch helpers to use. Read the whole desktop file before writing the test.
- Money/FX: display via `lib/format.js` helpers; default currency CZK; respect `useCurrency()` rate conversion exactly as the desktop page does.
- Every commit message ends with: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`
- All commits happen inside `c:/Users/tomzo/claude/ptf_m/portfyl-mobile` (its own repo — never commit to portfyl).

## File Structure (target)

```
portfyl-mobile/
├── backend/                     # Task 1 — verbatim copy incl. portfyl.db seed
├── frontend/
│   ├── index.html               # Task 2 — + manifest link, viewport-fit, theme-flash script
│   ├── package.json             # Task 2
│   ├── vite.config.js           # Task 2 — port 5174, proxy → 8001
│   ├── tailwind.config.js       # Task 2 — copied
│   ├── postcss.config.js        # Task 2 — copied
│   ├── public/logo.png          # Task 2 — copied
│   ├── public/manifest.webmanifest  # Task 2
│   └── src/
│       ├── main.jsx             # Task 2
│       ├── index.css            # Task 2 — copied
│       ├── api.js               # Task 3 — copied verbatim
│       ├── lib/                 # Task 3 — copied with tests
│       ├── hooks/               # Task 3 — copied with tests
│       ├── context/AppProviders.jsx  # Task 4
│       ├── components/ui/       # Task 4 — copied primitives + new BottomSheet (Task 5)
│       ├── components/shell/    # Task 5 — TopBar, BottomTabs, Drawer, AppShell
│       ├── components/AutoLoad.jsx   # Task 5 — copied
│       ├── test/setup.js        # Task 2 — copied
│       ├── test/renderWithProviders.jsx  # Task 5
│       ├── App.jsx              # Task 2 stub → Task 5 real shell + routes
│       └── pages/               # Task 5 stubs → Tasks 6–15 real pages
├── docs/superpowers/{specs,plans}/   # Task 1 — spec + this plan copied in
├── Dockerfile                   # Task 1 — copied unchanged
├── start.bat                    # Task 1 — adapted ports
├── sample_portfolio.csv         # Task 1
├── .gitignore                   # Task 1 — copied
├── CLAUDE.md                    # Task 1
└── README.md                    # Task 1
```

---

### Task 1: Bootstrap the repo — backend copy, seed DB, root files, git init

**Files:**
- Create: `c:/Users/tomzo/claude/ptf_m/portfyl-mobile/` (everything root-level listed above)
- Test: the copied backend pytest suite

**Interfaces:**
- Produces: a green backend on port 8001 with the user's real data; a git repo all later tasks commit into.

- [ ] **Step 1: Copy backend + root files** (Bash tool):

```bash
cd /c/Users/tomzo/claude/ptf_m
mkdir -p portfyl-mobile
cp -r portfyl/backend portfyl-mobile/backend
rm -rf portfyl-mobile/backend/__pycache__ portfyl-mobile/backend/routers/__pycache__ \
       portfyl-mobile/backend/tests/__pycache__ portfyl-mobile/backend/.venv
rm -f portfyl-mobile/backend/*.pre-dedupe-backup-*.db
cp portfyl/Dockerfile portfyl-mobile/
cp portfyl/sample_portfolio.csv portfyl-mobile/
cp portfyl/.gitignore portfyl-mobile/
mkdir -p portfyl-mobile/docs/superpowers/specs portfyl-mobile/docs/superpowers/plans
cp portfyl/docs/superpowers/specs/2026-07-18-portfyl-mobile-design.md portfyl-mobile/docs/superpowers/specs/
cp portfyl/docs/superpowers/plans/2026-07-18-portfyl-mobile.md portfyl-mobile/docs/superpowers/plans/
ls portfyl-mobile/backend/portfyl.db   # must exist — this is the data seed
```

- [ ] **Step 2: Write `start.bat`** at `portfyl-mobile/start.bat` — portfyl's script with three changes (title, port 8001, port 5174):

```bat
@echo off
echo Starting Portfyl Mobile...

if exist "%~dp0.env" (
    for /f "usebackq tokens=1,* delims==" %%a in ("%~dp0.env") do (
        set "%%a=%%b"
    )
)

cd /d "%~dp0backend"

REM First run: create an isolated Python environment with uv (https://docs.astral.sh/uv/).
if not exist ".venv\Scripts\python.exe" (
    echo Setting up backend Python environment with uv...
    uv venv .venv --python 3.12 || goto :no_uv
    uv pip install --python ".venv\Scripts\python.exe" -r requirements.txt || goto :no_uv
)

start "Portfyl Mobile Backend" cmd /k ".venv\Scripts\python.exe -m uvicorn main:app --reload --port 8001"

cd /d "%~dp0frontend"
start "Portfyl Mobile Frontend" cmd /k "npm install --silent && npm run dev"

echo.
echo  Backend:  http://localhost:8001
echo  Frontend: http://localhost:5174
echo.
timeout /t 5 >nul
start http://localhost:5174
goto :eof

:no_uv
echo.
echo  ERROR: could not create the backend Python environment.
echo  Install uv from https://docs.astral.sh/uv/ then run start.bat again.
echo.
pause
```

- [ ] **Step 3: Write `README.md`**:

```markdown
# Portfyl Mobile

Standalone mobile-first version of [Portfyl](../portfyl) — same features, same
backend, frontend redesigned for phone screens (bottom tabs + drawer, PWA-installable).
Fully independent: own repo, own SQLite DB (seeded from portfyl at creation).

**Run (Windows):** `start.bat` → http://localhost:5174 (backend :8001).
Dev login password: `snowball-dev` (override with `APP_PASSWORD`).

Design spec: `docs/superpowers/specs/2026-07-18-portfyl-mobile-design.md`.
```

- [ ] **Step 4: Write `CLAUDE.md`** — portfyl's CLAUDE.md conventions still apply; write this adapted version:

```markdown
# Portfyl Mobile

Standalone **mobile-first** fork of Portfyl (../portfyl). Same FastAPI backend
(copied verbatim — treat `backend/` as frozen; port it forward from portfyl if
ever needed, don't hand-edit). New phone-first React frontend.

## Run it

- **Dev (Windows)**: `start.bat` — backend :8001 (uvicorn, uv-managed venv),
  frontend :5174 (Vite). Use **http://localhost:5174**; Vite proxies `/api`,
  `/login`, `/logout` → :8001. Dev password `snowball-dev` (`APP_PASSWORD` overrides).
- **Tests**: backend `python -m pytest tests/ -v` from `backend/` (install pytest
  into the venv first); frontend `npm test` from `frontend/`.

## Conventions (inherited from portfyl — read before editing)

- All API routes under `/api`; routers in `backend/routers/`.
- `frontend/src/api.js` auto-injects `portfolio_id` via an axios interceptor;
  `PORTFOLIO_AGNOSTIC_PREFIXES` (`/portfolios`, `/market`, `/watchlists`,
  `/settings`) must NOT receive it.
- `owner_id` is always `"default"`; DB migrations are imperative `_ensure_*`
  helpers in `main.py` (no Alembic); money normalized to CZK via `fx_to_czk`;
  valuation uses 5-year average P/E; yfinance noise is intentionally suppressed.
- `sb_*` localStorage keys, `sb_session` cookie, `snowball-dev` fallback are
  deliberate legacy names — don't rename.

## Mobile frontend structure

- Shell: `src/components/shell/` — TopBar (hamburger + title + portfolio pill),
  BottomTabs (Home / Allocation / Dividends / Activity), Drawer (all pages,
  grouped: Portfolio / Income / Discover / System). `src/components/ui/BottomSheet.jsx`
  replaces every desktop modal/popover.
- Pages in `src/pages/` mirror desktop portfyl pages 1:1 in features; layout is
  stacked cards, card lists instead of tables, filters in bottom sheets.
- Touch targets ≥ 44px; `100dvh` + safe-area insets; Tailwind token classes only
  (`bg-surface-card`, `text-ink`, `text-muted`, `text-gain/loss`, brand).
- PWA: `public/manifest.webmanifest`, **no service worker** (market data must
  not be cached stale).
```

- [ ] **Step 5: Set up venv and run the backend test suite** (this is the task's test — proves the copy is sound):

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl-mobile/backend
uv venv .venv --python 3.12
uv pip install --python .venv/Scripts/python.exe -r requirements.txt pytest
.venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all 7 test modules PASS (same result as running the suite in portfyl). If anything fails here it fails in portfyl too — verify there before touching anything, and never "fix" it by editing the copy.

- [ ] **Step 6: Sanity-boot the backend on 8001**:

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl-mobile/backend
.venv/Scripts/python.exe -m uvicorn main:app --port 8001 &
sleep 6 && curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/api/portfolios
# Expected: 401 (auth gate works). Then kill the uvicorn process.
```

- [ ] **Step 7: git init + first commit**:

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl-mobile
git init -b main
git add -A
git status   # confirm: no *.db, no .venv, no __pycache__ staged (.gitignore covers them)
git commit -m "chore: bootstrap portfyl-mobile — backend + docs copied from portfyl

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Frontend scaffold — builds, tests, and serves

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.js`, `frontend/index.html`, `frontend/public/manifest.webmanifest`, `frontend/src/main.jsx`, `frontend/src/App.jsx` (stub)
- Copy from portfyl frontend: `tailwind.config.js`, `postcss.config.js`, `src/index.css`, `src/test/setup.js`, `public/logo.png`

**Interfaces:**
- Produces: `npm run dev` (5174, proxied to 8001), `npm test`, `npm run build` all green; every later frontend task builds on this.

- [ ] **Step 1: Copy the config files that carry over unchanged**:

```bash
cd /c/Users/tomzo/claude/ptf_m
mkdir -p portfyl-mobile/frontend/src/test portfyl-mobile/frontend/public
cp portfyl/frontend/tailwind.config.js portfyl-mobile/frontend/
cp portfyl/frontend/postcss.config.js portfyl-mobile/frontend/
cp portfyl/frontend/src/index.css portfyl-mobile/frontend/src/
cp portfyl/frontend/src/test/setup.js portfyl-mobile/frontend/src/test/
cp portfyl/frontend/public/logo.png portfyl-mobile/frontend/public/
```

- [ ] **Step 2: Write `frontend/package.json`** — portfyl's with new name and **without `react-grid-layout`**:

```json
{
  "name": "portfyl-mobile",
  "version": "1.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@fontsource-variable/inter": "^5.2.8",
    "@fontsource-variable/jetbrains-mono": "^5.2.8",
    "@fontsource-variable/space-grotesk": "^5.2.10",
    "@tanstack/react-query": "^5.62.7",
    "axios": "^1.7.9",
    "lucide-react": "^0.468.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-dropzone": "^14.3.5",
    "react-router-dom": "^7.0.2",
    "recharts": "^2.14.1"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.9.1",
    "@testing-library/react": "^16.3.2",
    "@vitejs/plugin-react": "^4.3.4",
    "autoprefixer": "^10.4.20",
    "jsdom": "^29.1.1",
    "postcss": "^8.4.49",
    "tailwindcss": "^3.4.17",
    "vite": "^6.0.3",
    "vitest": "^4.1.9"
  }
}
```

- [ ] **Step 3: Write `frontend/vite.config.js`** — port 5174, proxy to 8001:

```js
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      // Same-origin routes in dev: /api carries data; /login + /logout keep the
      // password gate working without bouncing between :5174 and :8001.
      "/api": { target: "http://localhost:8001", changeOrigin: true },
      "/login": { target: "http://localhost:8001", changeOrigin: true },
      "/logout": { target: "http://localhost:8001", changeOrigin: true },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test/setup.js",
    css: false,
    passWithNoTests: true,
  },
});
```

- [ ] **Step 4: Write `frontend/index.html`** — portfyl's plus PWA/mobile meta (`viewport-fit=cover`, manifest, apple-touch-icon, theme-color); keep the pre-paint theme script verbatim:

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <title>Portfyl</title>
    <link rel="icon" type="image/png" href="/logo.png" />
    <link rel="manifest" href="/manifest.webmanifest" />
    <link rel="apple-touch-icon" href="/logo.png" />
    <meta name="theme-color" content="#059669" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <script>
      // Apply the saved theme before first paint to avoid a light flash.
      (function () {
        try {
          var t = localStorage.getItem("sb_theme") || "system";
          var dark = t === "dark" || (t === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
          if (dark) {
            var el = document.documentElement;
            el.classList.add("dark");
            el.style.setProperty("--bg", "#0F172A");
            el.style.background = "#0F172A";
          }
        } catch (e) {}
      })();
    </script>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.jsx"></script>
  </body>
</html>
```

- [ ] **Step 5: Write `frontend/public/manifest.webmanifest`**:

```json
{
  "name": "Portfyl",
  "short_name": "Portfyl",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0F172A",
  "theme_color": "#059669",
  "icons": [{ "src": "/logo.png", "sizes": "any", "type": "image/png" }]
}
```

- [ ] **Step 6: Write `frontend/src/main.jsx`** (same as portfyl's) and a stub `frontend/src/App.jsx`:

```jsx
// main.jsx
import "@fontsource-variable/space-grotesk";
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
});

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>
);
```

```jsx
// App.jsx — stub, replaced by the real shell in Task 5
export default function App() {
  return <div className="p-4 text-ink">Portfyl Mobile — shell arrives in Task 5</div>;
}
```

- [ ] **Step 7: Install, test, build**:

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl-mobile/frontend
npm install
npm test        # Expected: passes (passWithNoTests)
npm run build   # Expected: emits frontend/dist without errors
```

- [ ] **Step 8: Commit**:

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl-mobile
git add -A && git commit -m "feat: frontend scaffold — Vite on 5174 proxying 8001, PWA manifest

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Data layer — api.js, lib, hooks (with their tests)

**Files:**
- Copy from portfyl `frontend/src/`: `api.js`, `lib/` (all 6 files incl. `*.test.js`), `hooks/` (all 3 files incl. test)

**Interfaces:**
- Produces: every fetch helper exported by `src/api.js` (e.g. `fetchSummary(currency)`, `fetchHoldings(currency)`, `fetchPortfolios()`, `fetchFxRate(pair)`, `setActivePortfolioId(id)`, `getActivePortfolioId()` — the full desktop set); `formatMoney` / `formatPercent` from `src/lib/format.js`; `useCountUp`, `useStockReportConfig` hooks. Copied **verbatim** — later tasks rely on exact desktop signatures.

- [ ] **Step 1: Copy**:

```bash
cd /c/Users/tomzo/claude/ptf_m
cp portfyl/frontend/src/api.js portfyl-mobile/frontend/src/
cp -r portfyl/frontend/src/lib portfyl-mobile/frontend/src/
cp -r portfyl/frontend/src/hooks portfyl-mobile/frontend/src/
```

- [ ] **Step 2: Run the copied tests** (they ARE this task's tests — format/chartChanges/positionsPie/useCountUp):

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl-mobile/frontend && npm test
```

Expected: PASS — same results as in portfyl. Do not edit any copied file to make tests pass; a failure means the copy is bad.

- [ ] **Step 3: Commit**:

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl-mobile
git add -A && git commit -m "feat: carry over proven data layer (api.js, lib, hooks) with tests

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Theme system, contexts, ui primitives

**Files:**
- Create: `frontend/src/context/AppProviders.jsx`
- Copy from portfyl: `frontend/src/components/ui/` (whole directory: Card, SectionHeader, Skeleton, EmptyState, ErrorState, DeltaPill, SegmentedControl, Toast, ConfirmDialog, index.js, primitives.test.jsx)
- Test: copied `primitives.test.jsx` + new `frontend/src/context/AppProviders.test.jsx`

**Interfaces:**
- Consumes: `src/api.js` (`fetchPortfolios`, `fetchFxRate`, `setActivePortfolioId`, `getActivePortfolioId`).
- Produces — exact contracts (identical to desktop `App.jsx`, PlatformProvider dropped):
  - `<AppProviders>{children}</AppProviders>` — wraps Palette → Portfolio → Currency → Toast → Confirm providers.
  - `useCurrency()` → `{ currency, setCurrency, rate, rateLoading }`
  - `usePortfolio()` → `{ portfolios, currentId, current, setCurrentId, refetchPortfolios, isLoading, ready }`
  - `usePalette()` → `{ palette, setPalette, theme, setTheme, palettes }`
  - `resolveDark(theme)` exported for Settings.

- [ ] **Step 1: Copy ui primitives**:

```bash
cd /c/Users/tomzo/claude/ptf_m
mkdir -p portfyl-mobile/frontend/src/components
cp -r portfyl/frontend/src/components/ui portfyl-mobile/frontend/src/components/ui
```

- [ ] **Step 2: Write the failing provider test** at `frontend/src/context/AppProviders.test.jsx`:

```jsx
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../api", () => ({
  fetchPortfolios: async () => [{ id: 1, name: "zubik", is_default: true }],
  fetchFxRate: async () => ({ rate: 20.85 }),
  setActivePortfolioId: () => {},
  getActivePortfolioId: () => 1,
}));

import { AppProviders, usePortfolio, useCurrency } from "./AppProviders";

function Probe() {
  const { current } = usePortfolio();
  const { currency } = useCurrency();
  return <div>{currency}:{current ? current.name : "none"}</div>;
}

describe("AppProviders", () => {
  it("exposes portfolio and currency contexts with desktop contracts", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <AppProviders><Probe /></AppProviders>
      </QueryClientProvider>
    );
    expect(await screen.findByText("CZK:zubik")).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run it — must fail** (`AppProviders.jsx` doesn't exist):

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl-mobile/frontend
npx vitest run src/context/AppProviders.test.jsx
```

- [ ] **Step 4: Write `frontend/src/context/AppProviders.jsx`** by extracting from `c:/Users/tomzo/claude/ptf_m/portfyl/frontend/src/App.jsx` lines 1–274: copy `PALETTES`, `DARK_SURFACES`, `LIGHT_TOKENS`, `applyAppearance`, `resolveDark`, `CurrencyProvider`, `PortfolioProvider`, `PaletteProvider` **verbatim**, plus the three contexts and hooks. Changes allowed: (a) drop `PlatformProvider`/`PlatformContext`/`usePlatform` entirely (mobile flattens platforms), (b) export a single composite:

```jsx
export function AppProviders({ children }) {
  return (
    <PaletteProvider>
      <PortfolioProvider>
        <CurrencyProvider>
          <ToastProvider>
            <ConfirmProvider>{children}</ConfirmProvider>
          </ToastProvider>
        </CurrencyProvider>
      </PortfolioProvider>
    </PaletteProvider>
  );
}
```

(`ToastProvider` from `../components/ui/Toast`, `ConfirmProvider` from `../components/ui/ConfirmDialog` — same as desktop.) Export `useCurrency`, `usePortfolio`, `usePalette`, `resolveDark`, `PALETTES`.

- [ ] **Step 5: Run all frontend tests — provider test and primitives test must pass**:

```bash
npm test
```

Note: `primitives.test.jsx` imports from `../../App` in portfyl if it references hooks — if it fails on an import path, fix the **import path only** to `../../context/AppProviders`, nothing else.

- [ ] **Step 6: Commit**:

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl-mobile
git add -A && git commit -m "feat: theme/palette system, app contexts, ui primitives

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Mobile app shell — BottomSheet, TopBar, BottomTabs, Drawer, routes

**Files:**
- Create: `frontend/src/components/ui/BottomSheet.jsx`, `frontend/src/components/shell/TopBar.jsx`, `frontend/src/components/shell/BottomTabs.jsx`, `frontend/src/components/shell/Drawer.jsx`, `frontend/src/components/shell/AppShell.jsx`, `frontend/src/test/renderWithProviders.jsx`, stub files for all 17 pages in `frontend/src/pages/`
- Copy: `frontend/src/components/AutoLoad.jsx` from portfyl
- Modify: `frontend/src/App.jsx` (replace stub with real shell + routes)
- Test: `frontend/src/components/shell/AppShell.test.jsx`

**Interfaces:**
- Consumes: `AppProviders`, `usePortfolio`, `usePalette` (Task 4 contracts).
- Produces:
  - `<BottomSheet open onClose title>{children}</BottomSheet>` — used by ALL later page tasks for filters/actions. Add `export { BottomSheet } from "./BottomSheet";` to `components/ui/index.js`.
  - `renderWithProviders(ui, { route = "/" })` from `src/test/renderWithProviders.jsx` — used by every page test.
  - Routes registered at: `/`, `/allocation`, `/analytics`, `/transactions`, `/cash`, `/dividends`, `/dividend-calendar`, `/options`, `/polymarket`, `/screener`, `/watchlists`, `/tax-report`, `/import`, `/settings`, `/assistant`, `/search`, `/stock/:ticker` — page files named `Home.jsx`, `Allocation.jsx`, `Analytics.jsx`, `Transactions.jsx`, `Cash.jsx`, `Dividends.jsx`, `DividendCalendar.jsx`, `Options.jsx`, `Polymarket.jsx`, `Screener.jsx`, `Watchlists.jsx`, `TaxReport.jsx`, `Import.jsx`, `Settings.jsx`, `Assistant.jsx`, `Search.jsx`, `Stock.jsx`, plus `PlatformLanding.jsx`.

- [ ] **Step 1: Write the failing shell test** at `frontend/src/components/shell/AppShell.test.jsx`:

```jsx
import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";

vi.mock("../../api", () => ({
  fetchPortfolios: async () => [{ id: 1, name: "zubik", is_default: true }],
  fetchFxRate: async () => ({ rate: 20.85 }),
  setActivePortfolioId: () => {},
  getActivePortfolioId: () => 1,
}));

import { renderWithProviders } from "../../test/renderWithProviders";
import App from "../../App";

describe("mobile shell", () => {
  it("renders bottom tabs and navigates via the drawer", async () => {
    renderWithProviders(<App />);
    // Bottom tabs present
    expect(await screen.findByRole("link", { name: /home/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /allocation/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /dividends/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /activity/i })).toBeInTheDocument();
    // Drawer opens from the hamburger and contains a non-tab page
    fireEvent.click(screen.getByRole("button", { name: /open menu/i }));
    expect(await screen.findByRole("link", { name: /tax report/i })).toBeInTheDocument();
  });
});
```

Note: `App` must not include `BrowserRouter` (it lives in `main.jsx`); `renderWithProviders` supplies `MemoryRouter`. Because App already includes `AppProviders`, `renderWithProviders` must NOT double-wrap — see Step 3.

- [ ] **Step 2: Run it — must fail**:

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl-mobile/frontend
npx vitest run src/components/shell/AppShell.test.jsx
```

- [ ] **Step 3: Write `frontend/src/test/renderWithProviders.jsx`** — router + query client only (pages/App bring their own providers as needed):

```jsx
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppProviders } from "../context/AppProviders";

// Wrap a bare page in full providers; pass { withProviders: false } when the
// tree under test (e.g. <App/>) already includes AppProviders itself.
export function renderWithProviders(ui, { route = "/", withProviders } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const isApp = withProviders === false || ui.type?.name === "App";
  const inner = isApp ? ui : <AppProviders>{ui}</AppProviders>;
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>{inner}</MemoryRouter>
    </QueryClientProvider>
  );
}
```

- [ ] **Step 4: Write `frontend/src/components/ui/BottomSheet.jsx`** (and add the export to `components/ui/index.js`):

```jsx
// Mobile replacement for every desktop modal/popover. Renders nothing when
// closed; scrim tap closes. Content scrolls within 85dvh.
export function BottomSheet({ open, onClose, title, children }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="absolute inset-x-0 bottom-0 max-h-[85dvh] overflow-y-auto rounded-t-2xl border-t border-hairline bg-surface-card pb-[env(safe-area-inset-bottom)]">
        <div className="mx-auto mt-2 h-1 w-10 rounded-full bg-hairline" />
        {title && <div className="px-4 pt-3 pb-1 font-display text-base font-semibold text-ink">{title}</div>}
        <div className="p-4">{children}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Write `frontend/src/components/shell/BottomTabs.jsx`**:

```jsx
import { NavLink } from "react-router-dom";
import { Home, PieChart, HandCoins, Receipt } from "lucide-react";

const TABS = [
  { to: "/", label: "Home", icon: Home, end: true },
  { to: "/allocation", label: "Allocation", icon: PieChart },
  { to: "/dividends", label: "Dividends", icon: HandCoins },
  { to: "/transactions", label: "Activity", icon: Receipt },
];

export default function BottomTabs() {
  return (
    <nav className="flex-none border-t border-hairline bg-surface-card pb-[env(safe-area-inset-bottom)]">
      <div className="flex">
        {TABS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex min-h-[44px] flex-1 flex-col items-center gap-0.5 py-2 text-[11px] font-medium ${
                isActive ? "text-brand" : "text-muted"
              }`
            }
          >
            <Icon size={20} strokeWidth={2.2} />
            {label}
          </NavLink>
        ))}
      </div>
    </nav>
  );
}
```

- [ ] **Step 6: Write `frontend/src/components/shell/Drawer.jsx`** — groups exactly per spec:

```jsx
import { NavLink, useLocation } from "react-router-dom";
import { useEffect } from "react";
import {
  LayoutDashboard, PieChart, LineChart, Receipt, Wallet, HandCoins, CalendarDays,
  Target, FileText, Filter, Eye, Dices, Search, Bot, Download, Settings as SettingsIcon,
} from "lucide-react";
import { usePortfolio } from "../../context/AppProviders";

const GROUPS = [
  { label: "Portfolio", items: [
    { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
    { to: "/allocation", label: "Allocation", icon: PieChart },
    { to: "/analytics", label: "Analytics", icon: LineChart },
    { to: "/transactions", label: "Transactions", icon: Receipt },
    { to: "/cash", label: "Cash", icon: Wallet },
  ]},
  { label: "Income", items: [
    { to: "/dividends", label: "Dividends", icon: HandCoins },
    { to: "/dividend-calendar", label: "Dividend Calendar", icon: CalendarDays },
    { to: "/options", label: "Options", icon: Target },
    { to: "/tax-report", label: "Tax Report", icon: FileText },
  ]},
  { label: "Discover", items: [
    { to: "/screener", label: "Screener", icon: Filter },
    { to: "/watchlists", label: "Watchlists", icon: Eye },
    { to: "/polymarket", label: "Polymarket", icon: Dices },
    { to: "/search", label: "Search", icon: Search },
    { to: "/assistant", label: "Assistant", icon: Bot },
  ]},
  { label: "System", items: [
    { to: "/import", label: "Import", icon: Download },
    { to: "/settings", label: "Settings", icon: SettingsIcon },
  ]},
];

export default function Drawer({ open, onClose }) {
  const { current } = usePortfolio();
  const location = useLocation();
  // Close whenever navigation happens.
  useEffect(() => { onClose(); /* eslint-disable-line */ }, [location.pathname]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[80vw] flex-col overflow-y-auto bg-surface-card pt-[env(safe-area-inset-top)] shadow-pop">
        <div className="px-4 py-4 font-display text-lg font-bold text-ink">
          Portfyl {current && <span className="text-sm font-medium text-muted">· {current.name}</span>}
        </div>
        {GROUPS.map((g) => (
          <div key={g.label} className="px-2 pb-2">
            <div className="px-2 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-widest text-muted">{g.label}</div>
            {g.items.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  `flex min-h-[44px] items-center gap-3 rounded-xl px-3 text-sm font-medium ${
                    isActive ? "bg-brand-light text-brand" : "text-ink"
                  }`
                }
              >
                <Icon size={18} /> {label}
              </NavLink>
            ))}
          </div>
        ))}
      </aside>
    </div>
  );
}
```

- [ ] **Step 7: Write `frontend/src/components/shell/TopBar.jsx`**:

```jsx
import { useState } from "react";
import { useLocation } from "react-router-dom";
import { Menu } from "lucide-react";
import { usePortfolio } from "../../context/AppProviders";
import { BottomSheet } from "../ui";

const TITLES = {
  "/": "Home", "/allocation": "Allocation", "/analytics": "Analytics",
  "/transactions": "Activity", "/cash": "Cash", "/dividends": "Dividends",
  "/dividend-calendar": "Dividend Calendar", "/options": "Options",
  "/polymarket": "Polymarket", "/screener": "Screener", "/watchlists": "Watchlists",
  "/tax-report": "Tax Report", "/import": "Import", "/settings": "Settings",
  "/assistant": "Assistant", "/search": "Search",
};

export default function TopBar({ onMenu }) {
  const { pathname } = useLocation();
  const { portfolios, current, setCurrentId } = usePortfolio();
  const [pickerOpen, setPickerOpen] = useState(false);
  const title = TITLES[pathname] || (pathname.startsWith("/stock/") ? pathname.split("/")[2] : "Portfyl");
  return (
    <header className="flex-none border-b border-hairline bg-surface-card pt-[env(safe-area-inset-top)]">
      <div className="flex h-14 items-center gap-2 px-2">
        <button aria-label="Open menu" onClick={onMenu} className="grid h-11 w-11 place-items-center rounded-xl text-ink">
          <Menu size={22} />
        </button>
        <h1 className="font-display text-base font-bold text-ink">{title}</h1>
        {current && (
          <button
            onClick={() => setPickerOpen(true)}
            className="ml-auto mr-1 rounded-full bg-brand-light px-3 py-1.5 text-xs font-semibold text-brand"
          >
            {current.name} ▾
          </button>
        )}
      </div>
      <BottomSheet open={pickerOpen} onClose={() => setPickerOpen(false)} title="Portfolios">
        {portfolios.map((p) => (
          <button
            key={p.id}
            onClick={() => { setCurrentId(p.id); setPickerOpen(false); }}
            className={`flex min-h-[44px] w-full items-center rounded-xl px-3 text-left text-sm font-medium ${
              current?.id === p.id ? "bg-brand-light text-brand" : "text-ink"
            }`}
          >
            {p.name}
          </button>
        ))}
      </BottomSheet>
    </header>
  );
}
```

- [ ] **Step 8: Copy `AutoLoad.jsx`, create page stubs, write `AppShell.jsx` and the real `App.jsx`**:

```bash
cp /c/Users/tomzo/claude/ptf_m/portfyl/frontend/src/components/AutoLoad.jsx \
   /c/Users/tomzo/claude/ptf_m/portfyl-mobile/frontend/src/components/
```

Each stub in `frontend/src/pages/` (all 18 files listed in Interfaces) looks like:

```jsx
// e.g. src/pages/Allocation.jsx — stub, replaced in its own task
export default function Allocation() {
  return <div className="p-4 text-muted">Allocation</div>;
}
```

`frontend/src/components/shell/AppShell.jsx`:

```jsx
import { useState } from "react";
import TopBar from "./TopBar";
import BottomTabs from "./BottomTabs";
import Drawer from "./Drawer";
import AutoLoad from "../AutoLoad";
import PlatformLanding from "../../pages/PlatformLanding";
import { usePortfolio } from "../../context/AppProviders";

export default function AppShell({ children }) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const { portfolios, isLoading } = usePortfolio();
  // First run: no portfolio exists yet → full-screen landing (create/pick).
  if (!isLoading && portfolios.length === 0) return <PlatformLanding />;
  return (
    <div className="flex h-dvh flex-col bg-surface">
      <AutoLoad />
      <TopBar onMenu={() => setDrawerOpen(true)} />
      <main className="min-h-0 flex-1 overflow-y-auto">{children}</main>
      <BottomTabs />
      <Drawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  );
}
```

`frontend/src/App.jsx` (replaces the Task 2 stub):

```jsx
import { Routes, Route } from "react-router-dom";
import { AppProviders } from "./context/AppProviders";
import AppShell from "./components/shell/AppShell";
import Home from "./pages/Home";
import Allocation from "./pages/Allocation";
import Analytics from "./pages/Analytics";
import Transactions from "./pages/Transactions";
import Cash from "./pages/Cash";
import Dividends from "./pages/Dividends";
import DividendCalendar from "./pages/DividendCalendar";
import Options from "./pages/Options";
import Polymarket from "./pages/Polymarket";
import Screener from "./pages/Screener";
import Watchlists from "./pages/Watchlists";
import TaxReport from "./pages/TaxReport";
import Import from "./pages/Import";
import Settings from "./pages/Settings";
import Assistant from "./pages/Assistant";
import Search from "./pages/Search";
import Stock from "./pages/Stock";

export default function App() {
  return (
    <AppProviders>
      <AppShell>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/allocation" element={<Allocation />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/transactions" element={<Transactions />} />
          <Route path="/cash" element={<Cash />} />
          <Route path="/dividends" element={<Dividends />} />
          <Route path="/dividend-calendar" element={<DividendCalendar />} />
          <Route path="/options" element={<Options />} />
          <Route path="/polymarket" element={<Polymarket />} />
          <Route path="/screener" element={<Screener />} />
          <Route path="/watchlists" element={<Watchlists />} />
          <Route path="/tax-report" element={<TaxReport />} />
          <Route path="/import" element={<Import />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/assistant" element={<Assistant />} />
          <Route path="/search" element={<Search />} />
          <Route path="/stock/:ticker" element={<Stock />} />
        </Routes>
      </AppShell>
    </AppProviders>
  );
}
```

If `AutoLoad.jsx` imports `usePlatform` from `../App` (it may check the platform before prefetching), change that import to always-prefetch behavior: delete the platform check and its import — that is the flattening decision from the spec, and the ONLY allowed edit to a copied file in this task.

- [ ] **Step 9: Run the shell test, then the whole suite**:

```bash
npx vitest run src/components/shell/AppShell.test.jsx   # Expected: PASS
npm test                                                # Expected: all green
```

- [ ] **Step 10: Commit**:

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl-mobile
git add -A && git commit -m "feat: mobile shell — TopBar, BottomTabs, Drawer, BottomSheet, routes

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Page tasks (6–15) — shared recipe

Every page task below follows the same five steps; the task defines its page-specific content.

1. **Read the desktop reference page fully** (path given per task) — its `../api` imports are the exact fetchers to use; its JSX defines the features that must all survive (filters, sorts, toggles, mutations, empty states).
2. **Write the failing page test** (code given per task) at `frontend/src/pages/<Page>.test.jsx`, run `npx vitest run src/pages/<Page>.test.jsx`, confirm FAIL (stub doesn't render the asserted content).
3. **Replace the stub** with the real mobile page: stacked cards per the section list given per task; wide desktop tables → card lists; desktop modals/filter popovers → `BottomSheet`; charts → full-width recharts with touch tooltips; loading → `Skeleton*` primitives; empty → `EmptyState` with the exact copy the test asserts; errors → `ErrorState`.
4. **Run the page test (PASS), then `npm test` (all green).**
5. **Commit** with the message given per task.

The `vi.mock("../api", …)` factory in each test must include the four provider functions (`fetchPortfolios`, `fetchFxRate`, `setActivePortfolioId`, `getActivePortfolioId` — same stubs as Task 5's test) **plus** every helper the page imports, returning empty data (`async () => []` / `async () => ({})`). If the page imports a helper not listed in the test below, add it to the factory with an empty return — do not remove assertions.

---

### Task 6: Home (Dashboard)

**Files:** Create `frontend/src/pages/Home.jsx` (replace stub), `frontend/src/pages/Home.test.jsx`
**Desktop reference:** `portfyl/frontend/src/pages/Dashboard.jsx` (440 lines; fetchers: `fetchSummary`, `fetchHoldings`, `fetchPerformance`, `fetchBenchmarks`, `fetchMovers`, `fetchEarnings`, `fetchInsiderBuys`)

**Sections (in order, fixed stack):**
1. Gradient hero card (`bg-gradient-to-br from-brand to-brand-dim`): "Portfolio value" label, `font-display` total, day change with `DeltaPill`, currency toggle (CZK/USD via `useCurrency`).
2. Period chips row (7D/MTD/1M/3M/YTD/1Y/All) + a "vs benchmark" chip opening a `BottomSheet` with the 5 desktop benchmark toggles.
3. Full-width performance chart (recharts, value/gain mode toggle as on desktop).
4. Horizontally scrolling stat cards (`overflow-x-auto flex gap-2 snap-x`): the desktop `MetricCard` metrics.
5. "Top movers" card — period segmented control (Today/Week/Month), rows with ticker, name, change; each row links to `/stock/:ticker`.
6. Holdings preview — top 5 by value + "All ›" link to `/allocation`.
7. Earnings card and Insider buys card (as on desktop, stacked).

- [ ] **Test** (`Home.test.jsx`):

```jsx
import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";

vi.mock("../api", () => ({
  fetchPortfolios: async () => [{ id: 1, name: "zubik", is_default: true }],
  fetchFxRate: async () => ({ rate: 20.85 }),
  setActivePortfolioId: () => {},
  getActivePortfolioId: () => 1,
  fetchSummary: async () => ({}),
  fetchHoldings: async () => [],
  fetchPerformance: async () => [],
  fetchBenchmarks: async () => ({}),
  fetchMovers: async () => [],
  fetchEarnings: async () => [],
  fetchInsiderBuys: async () => [],
}));

import { renderWithProviders } from "../test/renderWithProviders";
import Home from "./Home";

describe("Home", () => {
  it("renders hero and movers sections", async () => {
    renderWithProviders(<Home />);
    expect(await screen.findByText(/portfolio value/i)).toBeInTheDocument();
    expect(await screen.findByText(/top movers/i)).toBeInTheDocument();
  });
});
```

- [ ] Steps 1–5 of the shared recipe. Commit: `feat: Home page — hero, performance chart, movers, holdings preview`

---

### Task 7: Allocation + Analytics

**Files:** Create `frontend/src/pages/Allocation.jsx`, `Allocation.test.jsx`, `frontend/src/pages/Analytics.jsx`, `Analytics.test.jsx`
**Desktop references:** `portfyl/frontend/src/pages/Allocation.jsx`, `portfyl/frontend/src/pages/Analytics.jsx` (also `components/AllocationChart.jsx`, `components/BreakdownChart.jsx`, `lib/positionsPie.js`)

**Allocation sections:** segmented control for the same dimensions as desktop (sector/type/currency/account…), donut (recharts Pie, full-width), breakdown list rows (name, % bar tinted `bg-brand`, value) — replaces the desktop table. Empty state copy: **"No holdings yet"**.
**Analytics sections:** each desktop analytics section becomes a full-width stacked card in the same order; keep every metric/chart. Empty state copy: **"No data yet"**.

- [ ] **Allocation test** (Analytics test identical shape, asserting `no data yet`):

```jsx
import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";

vi.mock("../api", () => ({
  fetchPortfolios: async () => [{ id: 1, name: "zubik", is_default: true }],
  fetchFxRate: async () => ({ rate: 20.85 }),
  setActivePortfolioId: () => {},
  getActivePortfolioId: () => 1,
  fetchHoldings: async () => [],
  fetchAllHoldings: async () => [],
}));

import { renderWithProviders } from "../test/renderWithProviders";
import Allocation from "./Allocation";

describe("Allocation", () => {
  it("shows the empty state with no holdings", async () => {
    renderWithProviders(<Allocation />);
    expect(await screen.findByText(/no holdings yet/i)).toBeInTheDocument();
  });
});
```

- [ ] Shared recipe for each page (test → fail → implement → pass), one commit per page:
  - `feat: Allocation page — donut + breakdown list`
  - `feat: Analytics page — stacked analytics sections`

---

### Task 8: Activity (Transactions) + Cash

**Files:** Create `frontend/src/pages/Transactions.jsx`, `Transactions.test.jsx`, `frontend/src/pages/Cash.jsx`, `Cash.test.jsx`
**Desktop references:** `portfyl/frontend/src/pages/Transactions.jsx` (incl. `TradeNoteModal` usage), `portfyl/frontend/src/pages/Cash.jsx` (+ `components/CashBalanceChart.jsx`). Desktop `Cash.test.jsx` exists — read it for expected behaviors.

**Transactions sections:** date-grouped card list (sticky date headers) replacing the desktop table — each card: ticker (mono), type badge, qty × price, total, note indicator; tap opens detail/edit `BottomSheet` (incl. trade note editing, delete with `ConfirmDialog`); floating "+" FAB (min 56px, above the tab bar) opens the add-transaction `BottomSheet` with the same fields as the desktop form; keep all desktop filters in a filter `BottomSheet`. Empty copy: **"No transactions yet"**.
**Cash sections:** balance chart card (full-width `CashBalanceChart` equivalent), then date-grouped ledger card list with the same row data as desktop. Empty copy: **"No cash activity yet"**.

- [ ] **Transactions test** (Cash test identical shape asserting `no cash activity yet`, mocking the cash fetchers the desktop page imports):

```jsx
import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";

vi.mock("../api", () => ({
  fetchPortfolios: async () => [{ id: 1, name: "zubik", is_default: true }],
  fetchFxRate: async () => ({ rate: 20.85 }),
  setActivePortfolioId: () => {},
  getActivePortfolioId: () => 1,
  fetchTransactions: async () => [],
  createTransaction: async () => ({}),
  deleteTransaction: async () => ({}),
}));

import { renderWithProviders } from "../test/renderWithProviders";
import Transactions from "./Transactions";

describe("Transactions", () => {
  it("shows the empty state and the add FAB", async () => {
    renderWithProviders(<Transactions />);
    expect(await screen.findByText(/no transactions yet/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add transaction/i })).toBeInTheDocument();
  });
});
```

- [ ] Shared recipe; commits:
  - `feat: Activity page — grouped transaction cards, add/edit sheets`
  - `feat: Cash page — balance chart + ledger list`

---

### Task 9: Dividends + Dividend Calendar

**Files:** Create `frontend/src/pages/Dividends.jsx`, `Dividends.test.jsx`, `frontend/src/pages/DividendCalendar.jsx`, `DividendCalendar.test.jsx`
**Desktop references:** `portfyl/frontend/src/pages/Dividends.jsx`, `portfyl/frontend/src/pages/DividendCalendar.jsx`

**Dividends sections:** summary stat cards (annual income, yield — whatever desktop shows) as a horizontal scroll row; received-dividends list grouped by month; projection/upcoming section as on desktop. Empty copy: **"No dividends yet"**.
**Dividend Calendar sections:** month selector (chips or ‹ › pager), agenda list of upcoming payouts (date header + ticker rows). Empty copy: **"No upcoming dividends"**.

- [ ] **Dividends test** (Calendar test identical shape asserting `no upcoming dividends`):

```jsx
import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";

vi.mock("../api", () => ({
  fetchPortfolios: async () => [{ id: 1, name: "zubik", is_default: true }],
  fetchFxRate: async () => ({ rate: 20.85 }),
  setActivePortfolioId: () => {},
  getActivePortfolioId: () => 1,
  fetchDividends: async () => [],
  fetchHoldings: async () => [],
}));

import { renderWithProviders } from "../test/renderWithProviders";
import Dividends from "./Dividends";

describe("Dividends", () => {
  it("shows the empty state", async () => {
    renderWithProviders(<Dividends />);
    expect(await screen.findByText(/no dividends yet/i)).toBeInTheDocument();
  });
});
```

(If the desktop page's dividend fetchers have different names, use those exact names in both the page and the mock factory.)

- [ ] Shared recipe; commits:
  - `feat: Dividends page — income summary + history`
  - `feat: Dividend Calendar page — month agenda`

---

### Task 10: Options + Polymarket

**Files:** Create `frontend/src/pages/Options.jsx`, `Options.test.jsx`, `frontend/src/pages/Polymarket.jsx`, `Polymarket.test.jsx`
**Desktop references:** `portfyl/frontend/src/pages/Options.jsx` (558 lines, + `components/OptionsCalendar.jsx`), `portfyl/frontend/src/pages/Polymarket.jsx`

**Options sections:** position cards (underlying, strike/expiry in mono, P/L with gain/loss colors), summary stats row, options calendar as an agenda list; keep IBKR sync actions. Empty copy: **"No option positions"**.
**Polymarket sections:** market/position cards with the same data as desktop rows. Empty copy: **"No positions"**.

- [ ] **Options test** (Polymarket identical shape asserting `no positions`):

```jsx
import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";

vi.mock("../api", () => ({
  fetchPortfolios: async () => [{ id: 1, name: "zubik", is_default: true }],
  fetchFxRate: async () => ({ rate: 20.85 }),
  setActivePortfolioId: () => {},
  getActivePortfolioId: () => 1,
}));
// Add the option/polymarket fetchers the desktop page imports, each async () => [].

import { renderWithProviders } from "../test/renderWithProviders";
import Options from "./Options";

describe("Options", () => {
  it("shows the empty state", async () => {
    renderWithProviders(<Options />);
    expect(await screen.findByText(/no option positions/i)).toBeInTheDocument();
  });
});
```

- [ ] Shared recipe; commits:
  - `feat: Options page — position cards + expiry agenda`
  - `feat: Polymarket page — market position cards`

---

### Task 11: Screener + Watchlists

**Files:** Create `frontend/src/pages/Screener.jsx`, `Screener.test.jsx`, `frontend/src/pages/Watchlists.jsx`, `Watchlists.test.jsx`
**Desktop references:** `portfyl/frontend/src/pages/Screener.jsx`, `portfyl/frontend/src/pages/Watchlists.jsx` (510 lines)

**Screener sections:** "Filters" button (opens `BottomSheet` containing ALL desktop filter controls), active-filter chips row, result cards (ticker, name, key metrics; tap → `/stock/:ticker`). Initial-state copy: **"Set filters to screen the market"**.
**Watchlists sections:** watchlist selector chips + create/rename/delete (via `BottomSheet` + `ConfirmDialog`), ticker card list with the desktop columns condensed to two lines per card, add-ticker input. Empty copy: **"No watchlists yet"**. (Watchlists API is portfolio-agnostic — do not pass portfolio_id; `api.js` already handles this.)

- [ ] **Screener test** (Watchlists identical shape asserting `no watchlists yet`, mocking the watchlist fetchers with `async () => []`):

```jsx
import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";

vi.mock("../api", () => ({
  fetchPortfolios: async () => [{ id: 1, name: "zubik", is_default: true }],
  fetchFxRate: async () => ({ rate: 20.85 }),
  setActivePortfolioId: () => {},
  getActivePortfolioId: () => 1,
}));
// Add the screener fetchers the desktop page imports, each async () => [].

import { renderWithProviders } from "../test/renderWithProviders";
import Screener from "./Screener";

describe("Screener", () => {
  it("shows the initial prompt and a Filters button", async () => {
    renderWithProviders(<Screener />);
    expect(await screen.findByText(/set filters to screen the market/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /filters/i })).toBeInTheDocument();
  });
});
```

- [ ] Shared recipe; commits:
  - `feat: Screener page — filter sheet + result cards`
  - `feat: Watchlists page — chips + ticker cards`

---

### Task 12: Tax Report + Import

**Files:** Create `frontend/src/pages/TaxReport.jsx`, `TaxReport.test.jsx`, `frontend/src/pages/Import.jsx`, `Import.test.jsx`
**Desktop references:** `portfyl/frontend/src/pages/TaxReport.jsx` (508 lines), `portfyl/frontend/src/pages/Import.jsx`

**TaxReport sections:** year selector chips, then each desktop report section as a stacked card (totals, per-category breakdowns, per-trade lists as card rows). Empty copy: **"Nothing to report"**.
**Import sections:** big tap-target dropzone card (react-dropzone; copy: **"Drop your broker CSV"** — on mobile it opens the file picker), replace-vs-append choice (radio cards, preserving the desktop `replace` param exactly), import progress/result, broker sync section (T212/IBKR buttons with the same endpoints as desktop). Note: replace-mode import is the user's standard workflow — it must work identically to desktop.

- [ ] **Import test** (TaxReport identical shape asserting `nothing to report`, mocking its fetchers empty):

```jsx
import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";

vi.mock("../api", () => ({
  fetchPortfolios: async () => [{ id: 1, name: "zubik", is_default: true }],
  fetchFxRate: async () => ({ rate: 20.85 }),
  setActivePortfolioId: () => {},
  getActivePortfolioId: () => 1,
  importCSV: async () => ({}),
}));
// Add broker-sync helpers the desktop Import page imports, each async () => ({}).

import { renderWithProviders } from "../test/renderWithProviders";
import Import from "./Import";

describe("Import", () => {
  it("renders the dropzone", async () => {
    renderWithProviders(<Import />);
    expect(await screen.findByText(/drop your broker csv/i)).toBeInTheDocument();
  });
});
```

- [ ] Shared recipe; commits:
  - `feat: Tax Report page — yearly report cards`
  - `feat: Import page — CSV dropzone + broker sync`

---

### Task 13: Settings

**Files:** Create `frontend/src/pages/Settings.jsx`, `Settings.test.jsx`; copy-and-adapt `components/DiscordSettings.jsx` and `components/SyncScheduleSettings.jsx` (+ its test) from portfyl if their internals fit mobile cards, else rebuild with identical behavior.
**Desktop reference:** `portfyl/frontend/src/pages/Settings.jsx` (675 lines)

**Sections (grouped settings list, each group a card):** Appearance (palette picker green/blue/purple via `usePalette`, theme light/dark/system), Currency default, Portfolios (create/rename/delete — with `ConfirmDialog`), Sync schedule (`SyncScheduleSettings`), Discord (`DiscordSettings`), Broker credentials (T212/IBKR forms as desktop). First group header copy: **"Appearance"**.

- [ ] **Test**:

```jsx
import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";

vi.mock("../api", () => ({
  fetchPortfolios: async () => [{ id: 1, name: "zubik", is_default: true }],
  fetchFxRate: async () => ({ rate: 20.85 }),
  setActivePortfolioId: () => {},
  getActivePortfolioId: () => 1,
  createPortfolio: async () => ({}),
  updatePortfolio: async () => ({}),
  deletePortfolio: async () => ({}),
}));
// Add settings/discord/sync fetchers the desktop page imports, each async () => ({}).

import { renderWithProviders } from "../test/renderWithProviders";
import Settings from "./Settings";

describe("Settings", () => {
  it("renders the Appearance group", async () => {
    renderWithProviders(<Settings />);
    expect(await screen.findByText(/appearance/i)).toBeInTheDocument();
  });
});
```

- [ ] Shared recipe. Commit: `feat: Settings page — grouped mobile settings`

---

### Task 14: Assistant + Search

**Files:** Create `frontend/src/pages/Assistant.jsx`, `Assistant.test.jsx`, `frontend/src/pages/Search.jsx`, `Search.test.jsx`
**Desktop references:** `portfyl/frontend/src/pages/Assistant.jsx` (333 lines), `portfyl/frontend/src/pages/Search.jsx`

**Assistant:** full-height chat — messages list (user right/brand, assistant left/card), input pinned at the bottom of the page area (above BottomTabs) with placeholder **"Ask about your portfolio…"**; preserve desktop's streaming/response handling exactly.
**Search:** full-screen search input (autofocus, placeholder **"Search stocks…"**), recent searches, result rows → `/stock/:ticker`.

- [ ] **Assistant test** (Search identical shape asserting the `search stocks` placeholder):

```jsx
import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";

vi.mock("../api", () => ({
  fetchPortfolios: async () => [{ id: 1, name: "zubik", is_default: true }],
  fetchFxRate: async () => ({ rate: 20.85 }),
  setActivePortfolioId: () => {},
  getActivePortfolioId: () => 1,
}));
// Add assistant/search helpers the desktop pages import, each async () => ({}).

import { renderWithProviders } from "../test/renderWithProviders";
import Assistant from "./Assistant";

describe("Assistant", () => {
  it("renders the chat input", async () => {
    renderWithProviders(<Assistant />);
    expect(await screen.findByPlaceholderText(/ask about your portfolio/i)).toBeInTheDocument();
  });
});
```

- [ ] Shared recipe; commits:
  - `feat: Assistant page — mobile chat`
  - `feat: Search page — full-screen search`

---

### Task 15: Stock detail + PlatformLanding

**Files:** Create `frontend/src/pages/Stock.jsx`, `Stock.test.jsx`, `frontend/src/pages/PlatformLanding.jsx`, `PlatformLanding.test.jsx`
**Desktop references:** `portfyl/frontend/src/pages/Stock.jsx` + `components/StockDetail.jsx`, `portfyl/frontend/src/pages/PlatformLanding.jsx`

**Stock sections:** header (ticker mono + name + price + `DeltaPill`), full-width price chart with period chips, "Your position" card (only when held), fundamentals sections from desktop `StockDetail` stacked, notes section. Route: `/stock/:ticker` via `useParams`.
**PlatformLanding (mobile role — portfolio landing):** shown by AppShell only when NO portfolio exists: heading copy **"Welcome to Portfyl"**, create-portfolio form; desktop's platform cards are dropped (flattened navigation). Also export nothing else — AppShell imports it by default export.

- [ ] **Stock test** (PlatformLanding test renders it directly and asserts `welcome to portfyl`):

```jsx
import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";

vi.mock("../api", () => ({
  fetchPortfolios: async () => [{ id: 1, name: "zubik", is_default: true }],
  fetchFxRate: async () => ({ rate: 20.85 }),
  setActivePortfolioId: () => {},
  getActivePortfolioId: () => 1,
}));
// Add the stock-detail fetchers the desktop Stock/StockDetail import, each async () => ({}).

import { renderWithProviders } from "../test/renderWithProviders";
import Stock from "./Stock";

describe("Stock", () => {
  it("renders the ticker from the route", async () => {
    renderWithProviders(<Stock />, { route: "/stock/NVDA" });
    // Page must render the ticker symbol even with empty data.
    expect(await screen.findByText(/NVDA/)).toBeInTheDocument();
  });
});
```

Note: rendering `<Stock />` directly at route `/stock/NVDA` requires the test to wrap it in a route — use:

```jsx
import { Routes, Route } from "react-router-dom";
renderWithProviders(
  <Routes><Route path="/stock/:ticker" element={<Stock />} /></Routes>,
  { route: "/stock/NVDA" }
);
```

- [ ] Shared recipe; commits:
  - `feat: Stock detail page`
  - `feat: portfolio landing (first-run) page`

---

### Task 16: Full verification — suites, build, live walkthrough

**Files:** Modify only what bugs require (frontend only — backend stays frozen).

**Interfaces:** Consumes everything; produces the verified, shippable app.

- [ ] **Step 1: Full test suites**:

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl-mobile/frontend && npm test && npm run build
cd /c/Users/tomzo/claude/ptf_m/portfyl-mobile/backend && .venv/Scripts/python.exe -m pytest tests/ -v
```

Expected: all green, build clean.

- [ ] **Step 2: Start both servers** (backend `uvicorn main:app --reload --port 8001` from `backend/` with the venv python; frontend `npm run dev` from `frontend/` — both via run_in_background).

- [ ] **Step 3: Playwright MCP walkthrough** at viewport **390×844** against `http://localhost:5174`:
  1. Land on `/login`, enter password `snowball-dev`, submit.
  2. Home loads with REAL data (the seeded DB has the user's zubik portfolio) — verify the hero shows a non-zero CZK value.
  3. Tap each bottom tab: Allocation, Dividends, Activity — each renders data, no horizontal overflow, no console errors.
  4. Open the drawer; visit every remaining entry: Analytics, Cash, Dividend Calendar, Options, Tax Report, Screener, Watchlists, Polymarket, Search, Assistant, Import, Settings. Screenshot each.
  5. Tap a holding → `/stock/:ticker` renders.
  6. Settings: switch palette to blue and theme to dark — colors change app-wide; switch back.
  7. Note every defect found; fix (frontend only), re-run `npm test`, re-verify the broken screen.

- [ ] **Step 4: Final commit**:

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl-mobile
git add -A && git commit -m "fix: walkthrough polish across pages

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

(If Step 3 found nothing to fix, skip the commit.)

---

## Self-review notes (done at planning time)

- **Spec coverage:** project shape → T1; backend verbatim + seed → T1; scaffold/ports/PWA-no-SW → T2; data layer → T3; theme/contexts/primitives → T4; shell/tabs/drawer/sheet/flattening/AutoLoad → T5; all 17 pages + Stock + landing → T6–15; error handling → per-page recipe (ErrorState/EmptyState/skeletons); verification (pytest, vitest, Playwright 390×844) → T1/T16. Login page needs no task (backend-served, T1 covers it).
- **Type consistency:** provider contracts in T4 Interfaces match T5/T14 consumers (`usePortfolio().current/currentId/setCurrentId`); `BottomSheet` prop set consistent across T5–T13; `renderWithProviders(ui, { route })` consistent in every test.
- **Known judgment calls:** page tests assert plan-mandated stable copy (empty states/placeholders) rather than guessed data shapes — the desktop reference file is authoritative for data handling; mock factories mirror each page's real `../api` import list.
