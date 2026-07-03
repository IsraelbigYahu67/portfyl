# Portfyl Merge (portfyl-pc + portfyl-nb) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the diverged repos `portfyl-pc` and `portfyl-nb` into one working, tested codebase in a new clean repo `C:\Users\tomzo\claude\ptf_m\portfyl`.

**Architecture:** A real `git merge` of `nb/main` into the PC branch inside a scratch clone (`ptf_m/merge-work`), resolving 24 conflict hunks in 10 source files per the approved spec (union of features, PC look wins, NB quality work kept). The resolved tree is then exported flat (no `snowball-analytics/` nesting) into a fresh repo where all verification (pytest, vite build, live browser run) happens.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + SQLite (backend, Python via `uv venv` 3.12), React 18 + Vite 6 + Tailwind + react-query (frontend), pytest, git.

**Spec:** `C:\Users\tomzo\claude\ptf_m\docs\superpowers\specs\2026-07-03-portfyl-merge-design.md`

## Global Constraints

- Project name is **Portfyl** everywhere user-visible (title, sidebar, README, `package.json` name `portfyl`, DB file `portfyl.db`).
- **PC look wins** visual conflicts; **union** for features; NB wins on engineering quality (AutoLoad, start.bat, tests).
- Final repo contains **no** `node_modules/`, `__pycache__/`, `dist/`, `*.db`, `.env`, `.venv/` in git.
- Preserve PC conventions (from PC `CLAUDE.md`): all API under `/api`; axios interceptor auto-injects `portfolio_id` (exceptions in `PORTFOLIO_AGNOSTIC_PREFIXES`); `owner_id="default"` single-user sentinel; imperative idempotent startup migrations in `main.py` (no Alembic); values normalized to CZK via `fx_to_czk`; valuation uses 5-year average P/E.
- Light `--border`/`--hairline` value is PC's `#E6EAF0` (not NB's `#E2E8F0`).
- Dev auth password fallback is `snowball-dev` (`APP_PASSWORD` env overrides).
- Paths below are relative to `C:\Users\tomzo\claude\ptf_m` unless absolute. Shell is Git Bash unless noted.

## Ground truth already established (do not re-derive)

- Both repos share initial commit `e4e90868`; branch names are `main` (both).
- A trial merge already exists at `ptf_m/trial-merge` (PC clone + `nb` remote + merge in progress with conflicts materialized). Reuse it as `merge-work`.
- Conflicted source files (all `UU`): `backend/database.py` (1 hunk), `backend/main.py` (2), `backend/routers/market.py` (2), `frontend/src/App.jsx` (4), `frontend/src/components/Sidebar.jsx` (2), `frontend/src/components/StockDetail.jsx` (1), `frontend/src/index.css` (2), `frontend/src/pages/Dashboard.jsx` (6), `frontend/src/pages/Transactions.jsx` (3), `frontend/tailwind.config.js` (1). Plus artifacts: `frontend/dist/index.html` and 4 files under `frontend/node_modules/`.
- Auto-merged already (verify, don't redo): `api.js`, `package.json`, `package-lock.json`, `PortfolioSwitcher.jsx`, `Import.jsx`, `main.jsx` (fonts), `frontend/index.html` (NB version — PC never touched source `index.html`), NB `tests/`, NB `cache.py`, NB `dividend_calendar.py`, all PC routers/pages, `requirements.txt` (identical in both branches; **lacks pytest**).
- NB backend tests do **not** use `TestClient` — they call router functions directly with an in-memory SQLite session, so the PC auth middleware does not affect them. `conftest.py` patches `os.rename` before importing `database.py` (works with the merged rename block below).
- Merged `market.py` working tree already contains NB's TTM backend (`_ttm_from_quarters`, `"ttm": ttm` in fundamentals payload at ~line 1270).
- PC `StockDetail.jsx` does **not** have NB's TTM-column chart work or Shares Outstanding chart → Task 5 ports it.
- PC db is a strict superset of NB db (356 vs 318 transactions; + options/polymarket/broker rows). Source of truth: `portfyl-pc/snowball-analytics/backend/snowball.db`.

---

### Task 1: Merge workspace setup

**Files:**
- Rename: `trial-merge/` → `merge-work/`

**Interfaces:**
- Produces: `merge-work/` — a git clone of portfyl-pc on `main`, with `git merge nb/main` in progress and conflicts materialized. All later tasks run inside it until Task 7.

- [ ] **Step 1: Rename the trial clone and confirm merge state**

```bash
cd /c/Users/tomzo/claude/ptf_m
mv trial-merge merge-work
cd merge-work
git status --porcelain | grep -E '^(UU|AA|DD|AU|UA|DU|UD)' | wc -l
```

Expected: `15` (11 UU source+dist files + 4 node_modules artifacts). If the directory is missing or state is wrong, recreate it:

```bash
cd /c/Users/tomzo/claude/ptf_m
git clone portfyl-pc merge-work && cd merge-work
git remote add nb ../portfyl-nb && git fetch nb
git merge nb/main --no-commit --no-ff || true
```

- [ ] **Step 2: Resolve artifact conflicts (not shipped; keep the merge index clean)**

```bash
cd /c/Users/tomzo/claude/ptf_m/merge-work
git rm -r -q --force snowball-analytics/frontend/node_modules
git checkout --ours -- snowball-analytics/frontend/dist/index.html
git add snowball-analytics/frontend/dist/index.html
git diff --name-only --diff-filter=U
```

Expected: exactly the 10 source files listed in Ground Truth remain.

---

### Task 2: Resolve backend conflicts (database.py, main.py, market.py)

**Files:**
- Modify: `merge-work/snowball-analytics/backend/database.py`
- Modify: `merge-work/snowball-analytics/backend/main.py`
- Modify: `merge-work/snowball-analytics/backend/routers/market.py`

**Interfaces:**
- Produces: importable backend where `DB_FILE = "portfyl.db"`, `DATABASE_PATH` env override still works, all 14 routers mounted (`portfolio, market, analytics, broker, portfolios, watchlists, benchmarks, ibkr, options, polymarket, discord, notes, assistant, dividend_calendar`), and `market.py` has both PC's `market_data`/`_FUND_CACHE` and NB's `ttl_cache` + screener endpoints.

- [ ] **Step 1: Resolve `database.py` (1 hunk) — union: NB rename-migration + PC env override**

Replace the entire conflict block (from `<<<<<<< HEAD` to `>>>>>>> nb/main`) with:

```python
DB_FILE = "portfyl.db"
_LEGACY_DB_FILE = "snowball.db"  # pre-rename name; migrate existing data on first run

# One-time migration: if the database still lives under the old "snowball.db"
# name and no portfyl.db exists yet, rename it so existing portfolio data
# carries over transparently.
if os.path.exists(_LEGACY_DB_FILE) and not os.path.exists(DB_FILE):
    os.rename(_LEGACY_DB_FILE, DB_FILE)

# DB location is configurable so production can point at the mounted GCS volume,
# while local dev keeps ./portfyl.db (relative to the backend dir).
# Absolute paths work too: DATABASE_PATH=/mnt/data/portfyl.db -> sqlite:////mnt/data/...
DATABASE_PATH = os.getenv("DATABASE_PATH", f"./{DB_FILE}")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DATABASE_PATH}"
```

- [ ] **Step 2: Resolve `main.py` hunk 1 (imports) — union**

```python
from models import Base, Transaction, Portfolio, Benchmark, BenchmarkComponent, OptionsTrade, PolymarketPosition, DiscordWebhook, TradeNote, BrokerBalance, AppSetting
from routers import portfolio, market, analytics, broker, portfolios, watchlists, benchmarks, ibkr, options, polymarket, discord, notes, assistant, dividend_calendar
```

- [ ] **Step 3: Resolve `main.py` hunk 2 (router mounts) — union**

```python
app.include_router(ibkr.router, prefix="/api")
app.include_router(options.router, prefix="/api")
app.include_router(polymarket.router, prefix="/api")
app.include_router(discord.router, prefix="/api")
app.include_router(notes.router, prefix="/api")
app.include_router(assistant.router, prefix="/api")
app.include_router(dividend_calendar.router, prefix="/api")
```

- [ ] **Step 4: Resolve `market.py` hunk 1 (imports) — union**

```python
import market_data
from cache import ttl_cache
```

- [ ] **Step 5: Resolve `market.py` hunk 2 — keep BOTH sides in order**

Keep the HEAD lines first, then NB's entire screener block verbatim (it starts with the `# Stock screener` banner comment and defines `_PRESET_UNIVERSES`, `_ticker_screener_row`, `_in_range`, and the screener endpoint):

```python
    _FUND_CACHE[sym] = (time.time(), payload)
    return payload


# ---------------------------------------------------------------------------
# Stock screener: filter a list of tickers by fundamental criteria
# ---------------------------------------------------------------------------
# ... (everything from the nb/main side of the hunk, unchanged) ...
```

I.e. delete only the three marker lines and keep both bodies, HEAD's first.

- [ ] **Step 6: Syntax-check all three files and stage**

```bash
cd /c/Users/tomzo/claude/ptf_m/merge-work/snowball-analytics/backend
python -m py_compile database.py main.py routers/market.py && echo OK
grep -c '<<<<<<<' database.py main.py routers/market.py
```

Expected: `OK`, then `0` for each file. Sanity: `grep -n "ttl_cache" routers/market.py` — every use must be the imported decorator (NB uses it on dividend-calendar-adjacent helpers; no clash with PC's `_FUND_CACHE`).

```bash
cd /c/Users/tomzo/claude/ptf_m/merge-work
git add snowball-analytics/backend/database.py snowball-analytics/backend/main.py snowball-analytics/backend/routers/market.py
```

---

### Task 3: Resolve theme/config conflicts (tailwind.config.js, index.css, App.jsx)

**Files:**
- Modify: `merge-work/snowball-analytics/frontend/tailwind.config.js`
- Modify: `merge-work/snowball-analytics/frontend/src/index.css`
- Modify: `merge-work/snowball-analytics/frontend/src/App.jsx`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `App.jsx` exports `useCurrency`, `usePortfolio`, `usePalette` (value: `{ palette, setPalette, theme, setTheme, palettes }`), `usePlatform` (value: `{ platform, setPlatform }`), `resolveDark(theme)`. Tailwind token colors all resolve through CSS vars so dark mode can retheme PC components. `applyAppearance(name, isDark)` is the single source of truth for theme vars.

- [ ] **Step 1: Resolve `tailwind.config.js` (1 hunk) and convert PC's hardcoded token colors to CSS vars**

The hunk is the `border:` line — take NB's `border: "var(--border)"`. Then, in the same `colors` block, convert the remaining hardcoded values so the final `colors` section reads:

```js
      colors: {
        surface: {
          DEFAULT: "var(--bg)",
          card: "var(--surface-card)",
          hover: "var(--bg-subtle)",
          border: "var(--border)",
        },
        brand: {
          DEFAULT: "var(--brand)",
          dim: "var(--brand-hover)",
          light: "var(--brand-light)",
        },
        ink: "var(--ink)",
        muted: "var(--muted)",
        hairline: "var(--hairline)",
        gain: "var(--gain)",
        loss: "var(--loss)",
      },
```

Keep PC's `fontFamily`, `boxShadow`, `keyframes`, `animation` untouched. Verify `darkMode: "class"` survived auto-merge near the top; add it if missing:

```bash
grep -n 'darkMode' snowball-analytics/frontend/tailwind.config.js
```

Expected: `darkMode: "class",`.

- [ ] **Step 2: Resolve `index.css` hunk 1 (`:root` vars) — union with PC's border value**

```css
    --surface-card: #FFFFFF;
    --border: #E6EAF0;
    --ink: #0B1220;
    --muted: #64748B;
    --hairline: #E6EAF0;
    --gain: #10B981;
    --loss: #EF4444;
```

(These are light-mode defaults for pre-JS paint; `applyAppearance` overrides at runtime.)

- [ ] **Step 3: Resolve `index.css` hunk 2 (base styles) — PC aesthetics + NB functional additions**

```css
  * { box-sizing: border-box; }
  ::-webkit-scrollbar { width: 8px; height: 8px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: #DCE2EA; border-radius: 4px; }
  ::-webkit-scrollbar-thumb:hover { background: #B6C0CD; }
  h1, h2, h3, .font-display { font-family: theme("fontFamily.display"); }
  .tnum { font-variant-numeric: tabular-nums; }
  /* Keyboard-only focus ring across all interactive elements. */
  :focus-visible {
    outline: 2px solid var(--brand);
    outline-offset: 2px;
    border-radius: 4px;
  }
  /* Inputs already render their own focus ring (see .input below). */
  .input:focus-visible { outline: none; }
  @keyframes toast-in {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }
```

(`toast-in` is required by NB's `Toast.jsx`; `:focus-visible` is NB's a11y work.)

- [ ] **Step 4: Resolve `App.jsx` hunk 1 (imports) — NB side, drop usePrefetch**

```jsx
import { ToastProvider } from "./components/ui/Toast";
import { ConfirmProvider } from "./components/ui/ConfirmDialog";
import AutoLoad from "./components/AutoLoad";
```

Verify the auto-merged import block above it already imports both PC pages (`PlatformLanding`, `Options`, `Polymarket`, `Assistant`) and NB pages (`Screener`, `DividendCalendar`); add any that are missing.

- [ ] **Step 5: Resolve `App.jsx` hunk 2 (PALETTES) — PC light values + NB `brandLightDark`**

```jsx
    brand: "#059669", brandHover: "#047857", brandLight: "#D1FAE5", brandLightDark: "#064E3B",
    bg: "#F6F8F7", bgSubtle: "#F0FDF4", sidebarActive: "#ECFDF5",
  },
  blue: {
    brand: "#2563EB", brandHover: "#1D4ED8", brandLight: "#DBEAFE", brandLightDark: "#1E3A8A",
    bg: "#F5F7FA", bgSubtle: "#F1F5F9", sidebarActive: "#EFF6FF",
  },
  purple: {
    brand: "#7C3AED", brandHover: "#6D28D9", brandLight: "#EDE9FE", brandLightDark: "#4C1D95",
    bg: "#F7F6FB", bgSubtle: "#F5F3FF", sidebarActive: "#F5F3FF",
```

- [ ] **Step 6: Resolve `App.jsx` hunk 3 — keep BOTH `usePlatform` and NB's dark machinery, extended to PC tokens**

Replace the conflict block with:

```jsx
export function usePlatform() {
  return useContext(PlatformContext);
}

export function resolveDark(theme) {
  if (theme === "dark") return true;
  if (theme === "light") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function applyAppearance(name, isDark) {
```

Then find NB's auto-merged `DARK_SURFACES` const (above `usePalette`) and replace it plus the `applyAppearance` body so the whole appearance section reads:

```jsx
// Neutral dark surfaces shared across all hues (the brand stays vivid in dark mode).
// bgSubtle sits a step above the card so hover states / progress tracks stay visible.
const DARK_SURFACES = {
  bg: "#0F172A", bgSubtle: "#334155", surfaceCard: "#1E293B", border: "#334155",
  ink: "#E2E8F0", muted: "#94A3B8", hairline: "#334155",
};
const LIGHT_TOKENS = {
  surfaceCard: "#FFFFFF", border: "#E6EAF0",
  ink: "#0B1220", muted: "#64748B", hairline: "#E6EAF0",
};

function applyAppearance(name, isDark) {
  const p = PALETTES[name] || PALETTES.green;
  const s = document.documentElement.style;
  s.setProperty("--brand", p.brand);
  s.setProperty("--brand-hover", p.brandHover);
  s.setProperty("--brand-light", isDark ? p.brandLightDark : p.brandLight);
  const t = isDark ? DARK_SURFACES : LIGHT_TOKENS;
  s.setProperty("--surface-card", t.surfaceCard);
  s.setProperty("--border", t.border);
  s.setProperty("--ink", t.ink);
  s.setProperty("--muted", t.muted);
  s.setProperty("--hairline", t.hairline);
  if (isDark) {
    s.setProperty("--bg", DARK_SURFACES.bg);
    s.setProperty("--bg-subtle", DARK_SURFACES.bgSubtle);
    s.setProperty("--sidebar-active", p.brandLightDark);
  } else {
    s.setProperty("--bg", p.bg);
    s.setProperty("--bg-subtle", p.bgSubtle);
    s.setProperty("--sidebar-active", p.sidebarActive);
  }
  document.documentElement.classList.toggle("dark", isDark);
}
```

Verify the auto-merged `PaletteProvider` is NB's theme-aware version (has `theme`/`setTheme` state, `matchMedia` listener, calls `applyAppearance(palette, resolveDark(theme))`). If any `applyPalette(` call survives, replace it.

- [ ] **Step 7: Resolve `App.jsx` hunk 4 (provider tree) — PC structure wrapped in NB providers**

```jsx
          <ToastProvider>
            <ConfirmProvider>
              <PlatformProvider>
                <AppLayout />
              </PlatformProvider>
            </ConfirmProvider>
          </ToastProvider>
```

- [ ] **Step 8: Update `AppLayout` (auto-merged region) — AutoLoad replaces usePrefetch, add NB routes**

In `AppLayout`: delete the `usePrefetch(platform, currency, currentId);` line (and now-unused destructures if any). Render AutoLoad gated to the T212 platform, and add the two NB routes to the T212 route set:

```jsx
function AppLayout() {
  const { platform } = usePlatform();

  if (!platform) {
    return (
      <div className="flex min-h-screen">
        <Sidebar />
        <main className="flex-1 p-6 overflow-y-auto min-w-0 max-h-screen">
          <PlatformLanding />
        </main>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen">
      {/* Background prefetcher — warms the React Query cache for every T212 page
          in priority order so navigation is instant. Renders nothing. */}
      {platform === "t212" && <AutoLoad />}
      <Sidebar />
      <main className="flex-1 p-6 overflow-y-auto min-w-0 max-h-screen">
        <Routes>
          {platform === "t212" && (
            <>
              <Route path="/" element={<Dashboard />} />
              <Route path="/allocation" element={<Allocation />} />
              <Route path="/transactions" element={<Transactions />} />
              <Route path="/import" element={<Import />} />
              <Route path="/dividends" element={<Dividends />} />
              <Route path="/dividend-calendar" element={<DividendCalendar />} />
              <Route path="/analytics" element={<Analytics />} />
              <Route path="/tax-report" element={<TaxReport />} />
              <Route path="/search" element={<Search />} />
              <Route path="/stock/:ticker" element={<Stock />} />
              <Route path="/watchlists" element={<Watchlists />} />
              <Route path="/screener" element={<Screener />} />
              <Route path="/assistant" element={<Assistant />} />
            </>
          )}
          {platform === "ibkr" && (
            <>
              <Route path="/" element={<Options />} />
              <Route path="/options" element={<Options />} />
            </>
          )}
          {platform === "polymarket" && (
            <>
              <Route path="/" element={<Polymarket />} />
            </>
          )}
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
```

- [ ] **Step 9: Verify and stage**

```bash
cd /c/Users/tomzo/claude/ptf_m/merge-work
grep -c '<<<<<<<' snowball-analytics/frontend/tailwind.config.js snowball-analytics/frontend/src/index.css snowball-analytics/frontend/src/App.jsx
grep -n "usePrefetch" -r snowball-analytics/frontend/src && echo "FAIL: usePrefetch still referenced" || echo OK
git add snowball-analytics/frontend/tailwind.config.js snowball-analytics/frontend/src/index.css snowball-analytics/frontend/src/App.jsx
```

Expected: three `0`s; `OK` (the hook file itself is deleted in Task 5).

---

### Task 4: Resolve component/page conflicts (Sidebar, Transactions, Dashboard)

**Files:**
- Modify: `merge-work/snowball-analytics/frontend/src/components/Sidebar.jsx`
- Modify: `merge-work/snowball-analytics/frontend/src/pages/Transactions.jsx`
- Resolve: `merge-work/snowball-analytics/frontend/src/pages/Dashboard.jsx` (take PC wholesale)

**Interfaces:**
- Consumes: `usePalette` (with `theme`/`setTheme`) and `usePlatform` from Task 3's App.jsx.

- [ ] **Step 1: Resolve `Sidebar.jsx` hunk 1 (imports) — union**

```jsx
import { NavLink, useNavigate } from "react-router-dom";
import { LayoutDashboard, PieChart, ArrowLeftRight, Upload, Loader2, CalendarDays, Activity, FileText, Settings, Search, Star, Target, ArrowLeft, Hexagon, Bot, Sun, Moon, Monitor, CalendarCheck, Filter } from "lucide-react";
import { useCurrency, usePalette, usePlatform } from "../App";
```

- [ ] **Step 2: Resolve `Sidebar.jsx` hunk 2 (hooks) — union**

```jsx
  const { palette, setPalette, theme, setTheme } = usePalette();
  const { platform, setPlatform } = usePlatform();
  const navigate = useNavigate();
```

- [ ] **Step 3: Review the auto-merged Sidebar body**

Read the whole file. Ensure: (a) NB's Screener (`Filter` icon, `/screener`) and Dividend Calendar (`CalendarCheck`, `/dividend-calendar`) NavLinks are inside the **T212** nav section (PC renders nav per platform); (b) NB's theme `SegmentedControl` (Sun/Moon/Monitor, `onChange={setTheme}`) renders in the sidebar footer for all platforms; (c) brand text says **Portfyl**; (d) no leftover NB-only flat-nav remnants duplicate PC's platform nav. Fix placements as needed — keep PC structure, insert NB items.

- [ ] **Step 4: Resolve `Transactions.jsx` (3 hunks) — union**

Hunk 1 (imports — keep all three):

```jsx
import TradeNoteModal from "../components/TradeNoteModal";
import { useConfirm } from "../components/ui/ConfirmDialog";
import { useToast } from "../components/ui/Toast";
```

Hunk 2 (add-mutation onSuccess — PC's broad invalidation + NB's toast):

```jsx
      ["transactions", "holdings", "summary", "heatmap", "performance"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] })
      );
      toast.success(`${form.type === "dividend" ? "Dividend" : "Transaction"} added`);
```

Hunk 3 (delete-mutation onSuccess — same pattern):

```jsx
      ["transactions", "holdings", "summary", "heatmap", "performance"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] })
      );
      toast.success("Transaction deleted");
```

Then verify in the auto-merged body: `const toast = useToast();` and `const confirm = useConfirm();` exist (NB added them), and the delete flow uses `confirm(...)` not `window.confirm`. TradeNoteModal usage (PC) must still render.

- [ ] **Step 5: Resolve `Dashboard.jsx` — PC version wholesale (spec: PC look wins, NB restack superseded)**

```bash
cd /c/Users/tomzo/claude/ptf_m/merge-work
git checkout --ours -- snowball-analytics/frontend/src/pages/Dashboard.jsx
```

- [ ] **Step 6: Verify and stage**

```bash
grep -rc '<<<<<<<' snowball-analytics/frontend/src/components/Sidebar.jsx snowball-analytics/frontend/src/pages/Transactions.jsx snowball-analytics/frontend/src/pages/Dashboard.jsx
git add snowball-analytics/frontend/src/components/Sidebar.jsx snowball-analytics/frontend/src/pages/Transactions.jsx snowball-analytics/frontend/src/pages/Dashboard.jsx
```

Expected: `0` for each.

---

### Task 5: StockDetail TTM port + post-merge unification

**Files:**
- Modify: `merge-work/snowball-analytics/frontend/src/components/StockDetail.jsx`
- Delete: `merge-work/snowball-analytics/frontend/src/hooks/usePrefetch.js`
- Modify: `merge-work/snowball-analytics/frontend/src/components/AutoLoad.jsx`
- Verify/Modify: `merge-work/snowball-analytics/frontend/package.json`, `frontend/index.html`, `src/api.js`
- Modify: `merge-work/snowball-analytics/CLAUDE.md`, `merge-work/snowball-analytics/README.md`, `merge-work/snowball-analytics/start.bat`

**Interfaces:**
- Consumes: merged backend fundamentals payload exposing `"ttm": {revenue, net_income, eps, fcf, ...}` and `fin.shares_outstanding` (already present — Ground Truth).
- Produces: chart components `MetricBarChart({ metric, currencyCode, period, isCount = false, ttm = null })` and `MergedMetricBarChart({ ..., ttm = null })` in PC's StockDetail.

- [ ] **Step 1: Resolve `StockDetail.jsx` (1 hunk) — PC side**

Take the HEAD side of the hunk (the `reportConfig.config.order.map` sections renderer). Delete the NB side.

- [ ] **Step 2: Port NB's TTM/isCount chart support into PC's `MetricBarChart` and `MergedMetricBarChart`**

Reference implementation: `git show nb/main:snowball-analytics/frontend/src/components/StockDetail.jsx` (NB's `MetricBarChart` at ~line 131, `MergedMetricBarChart` at ~line 1153). Port the deltas into PC's components (PC `MetricBarChart` ~line 154, `MergedMetricBarChart` — find with grep):

- Signature: add `isCount = false, ttm = null` params.
- Data: in annual (non-quarterly) view, when `ttm != null` append `{ year: "TTM", value: ttm, yoy: null, isTTM: true }` to the chart data.
- Bar fill: TTM column gets `#8b5cf6`; counts get `#6366f1`; otherwise gain/loss coloring as PC has it.
- Tooltip: label TTM rows `"TTM · trailing 12M"`.
- Counts (`isCount`): plain quantities — no currency prefix, no gain/loss coloring.

- [ ] **Step 3: Wire TTM data through PC's financials section**

In PC's financials section (inside the sections registry / `StockOverview`): add `const ttm = data.ttm || {};` near the other derived values, then pass `ttm` at call sites — `ttm={ttm.revenue}` (revenue), `ttm={ttm.net_income}` (net income), `ttm={ttm.eps}` (EPS), `ttm={ttm.fcf}` (FCF) — and add the Shares Outstanding chart alongside them:

```jsx
<MetricBarChart metric={fin.shares_outstanding || {}} currencyCode={data.currency} period={period} isCount />
```

Update the EPS QuickStat to prefer real TTM: `value={ttm.eps != null ? `${cs}${ttm.eps.toFixed(2)}` : "—"}`.

- [ ] **Step 4: Delete PC's prefetch hook; adapt AutoLoad for PC features**

```bash
cd /c/Users/tomzo/claude/ptf_m/merge-work
git rm -q snowball-analytics/frontend/src/hooks/usePrefetch.js
```

In `AutoLoad.jsx`: add `fetchAllTradeNotes` to the api import list and warm it in the Transactions step:

```jsx
      if (!(await runTasks([
        [["transactions"], () => fetchTransactions()],
        [["trade-notes-all"], () => fetchAllTradeNotes()],
        [["watchlists"], () => fetchWatchlists()],
      ]))) return;
```

Verify `fetchAllTradeNotes` exists in merged `src/api.js` (PC added it): `grep -n "fetchAllTradeNotes" snowball-analytics/frontend/src/api.js`.

- [ ] **Step 5: Naming + docs sweep**

- `frontend/package.json`: `"name"` must be `"portfyl"` (NB set it; verify after auto-merge).
- `frontend/index.html`: `<title>Portfyl</title>` (NB version; verify).
- `start.bat`: NB version won without conflict (uv venv, "Portfyl" strings) — verify `grep -i snowball snowball-analytics/start.bat` returns nothing.
- `CLAUDE.md` (PC): update — title to Portfyl; add Screener + Dividend Calendar to pages list and `dividend_calendar` to routers list; DB file is `portfyl.db` (legacy `snowball.db` auto-renamed); remove the "committed artifacts" gotcha (no longer true post-export); run instructions mention `uv venv` per NB start.bat; add `backend/tests/` (pytest) section.
- `README.md` (NB): update run instructions if they mention paths that change with the flatten (Task 7), and mention the platform concept (T212 / IBKR / Polymarket) + new PC pages.
- Global check: `grep -rin "snowball" snowball-analytics/frontend/src snowball-analytics/backend --include="*.py" --include="*.jsx" --include="*.js" | grep -vi "snowball.db\|sb_"` — rename user-visible strings to Portfyl; keep `sb_` localStorage keys and internal names (renaming those would log users out / drop preferences — not worth it).

- [ ] **Step 6: Commit the resolved merge**

```bash
cd /c/Users/tomzo/claude/ptf_m/merge-work
git status --porcelain | grep -E '^(UU|AA|DD|AU|UA|DU|UD)' | wc -l   # expect 0
git add -A
git commit -m "merge: unify portfyl-pc and portfyl-nb

Union of features (PC: platforms/IBKR/options/polymarket/assistant/discord/
notes/auth/design tokens; NB: screener/dividend calendar/dark mode/AutoLoad/
tests/cache). PC look wins visual conflicts; NB AutoLoad replaces usePrefetch;
NB TTM charts ported into PC StockDetail; DB renamed to portfyl.db.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Backend verification in merge-work

**Files:**
- Create: `merge-work/snowball-analytics/backend/.venv/` (not committed)
- Possibly modify: `backend/tests/*` or backend code, if failures reveal merge bugs

**Interfaces:**
- Consumes: merged backend from Tasks 2+5.

- [ ] **Step 1: Create venv and install deps (matches start.bat: uv + Python 3.12)**

PowerShell:

```powershell
cd C:\Users\tomzo\claude\ptf_m\merge-work\snowball-analytics\backend
uv venv .venv --python 3.12
uv pip install --python .venv\Scripts\python.exe -r requirements.txt pytest
```

If `uv` is missing, fall back to `py -3.12 -m venv .venv` + `.venv\Scripts\python -m pip install -r requirements.txt pytest` (or the system Python if 3.12 is unavailable — record which was used).

- [ ] **Step 2: Run the test suite**

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v --tb=short
```

Expected: all tests pass. Known legitimate failure causes to fix (in this priority): (a) a merge mistake in `market.py`/`database.py` → fix the merge; (b) PC changed a router function signature NB tests call (PC touched `analytics.py`, `broker.py`, `portfolio.py`) → update the **test** to the new signature only after confirming the PC behavior is intended; (c) missing test dep → install it. Do not weaken assertions to make tests pass.

- [ ] **Step 3: Import smoke test of the full app (routers, models, auth)**

```powershell
$env:DATABASE_PATH = "./smoke-test.db"
.venv\Scripts\python.exe -c "import main; print('app OK, routes:', len(main.app.routes))"
Remove-Item smoke-test.db -ErrorAction SilentlyContinue
$env:DATABASE_PATH = $null
```

Expected: `app OK, routes: <n>` with n > 50 and no traceback. (Startup runs migrations + may attempt FX backfill; network errors logged as warnings are acceptable, crashes are not.)

- [ ] **Step 4: Commit any fixes**

```bash
cd /c/Users/tomzo/claude/ptf_m/merge-work && git add -A && git diff --cached --quiet || git commit -m "fix: post-merge backend corrections from test run

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Frontend build verification + export to clean repo

**Files:**
- Create: `C:\Users\tomzo\claude\ptf_m\portfyl\` (final repo: backend/, frontend/, docs/, start.bat, Dockerfile, .dockerignore, CLAUDE.md, README.md, sample_portfolio.csv, .gitignore)
- Create: `portfyl/.gitignore`
- Create: `portfyl/backend/portfyl.db` (copied data, NOT committed)

**Interfaces:**
- Consumes: committed merge from Tasks 5–6.
- Produces: the final repo all later work happens in. App at repo root (flatten is safe: `start.bat` uses `%~dp0`-relative paths; Dockerfile copies `backend/`/`frontend/` relative to build context).

- [ ] **Step 1: Frontend install + build in merge-work (fail fast before exporting)**

```powershell
cd C:\Users\tomzo\claude\ptf_m\merge-work\snowball-analytics\frontend
npm install
npx vitest run --passWithNoTests
npm run build
```

Expected: `npm install` regenerates a consistent lockfile; vitest passes (PC harness may have few/no tests); `npm run build` completes with no errors (warnings acceptable). Fix any build errors (they are merge bugs — typically a missed import or duplicate identifier in App.jsx/StockDetail.jsx) and commit fixes in merge-work.

- [ ] **Step 2: Export the app tree, flattened**

PowerShell:

```powershell
cd C:\Users\tomzo\claude\ptf_m
New-Item -ItemType Directory -Force portfyl | Out-Null
robocopy merge-work\snowball-analytics portfyl /E /XD node_modules dist __pycache__ .venv graphify-out /XF snowball.db portfyl.db smoke-test.db .graphify_python .graphify_uncached.txt /NFL /NDL /NJH
```

Expected: robocopy exit code ≤ 3 (success). Then copy the design docs and the authoritative DB:

```powershell
New-Item -ItemType Directory -Force portfyl\docs\superpowers\specs, portfyl\docs\superpowers\plans | Out-Null
Copy-Item docs\superpowers\specs\2026-07-03-portfyl-merge-design.md portfyl\docs\superpowers\specs\
Copy-Item docs\superpowers\plans\2026-07-03-portfyl-merge.md portfyl\docs\superpowers\plans\
Copy-Item portfyl-pc\snowball-analytics\backend\snowball.db portfyl\backend\portfyl.db
```

(The PC DB is copied under its **new** name `portfyl.db` — `database.py` uses it directly; the legacy-rename branch simply never fires.)

- [ ] **Step 3: Write `portfyl/.gitignore`**

```gitignore
# dependencies / build artifacts
node_modules/
frontend/dist/
__pycache__/
*.pyc
.venv/

# data & secrets — the DB holds real portfolio data, never commit it
*.db
.env

# editor/os noise
.DS_Store
Thumbs.db
```

- [ ] **Step 4: Init repo and make the initial commit**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
git init -b main
git add -A
git status --porcelain | grep -E "node_modules|\.db$|dist/" && echo "FAIL: artifacts staged" || echo OK
git commit -m "Portfyl: unified codebase merged from portfyl-pc and portfyl-nb

Merged at portfyl-pc ca24bce2 + portfyl-nb 17e1a1b5 (common base e4e90868).
Full merge resolution history lives in the archived repos and the design
doc under docs/superpowers/specs/.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

Expected: `OK` before commit; initial commit contains ~app source + docs only (roughly a few hundred files, not thousands).

- [ ] **Step 5: Re-verify tests and build in the clean repo (what ships is what's tested)**

```powershell
cd C:\Users\tomzo\claude\ptf_m\portfyl\backend
uv venv .venv --python 3.12
uv pip install --python .venv\Scripts\python.exe -r requirements.txt pytest
.venv\Scripts\python.exe -m pytest tests/ -q
cd ..\frontend
npm install
npm run build
```

Expected: pytest all pass; build clean. (`npm install` creates `package-lock.json` drift only if merge-work's lockfile was stale — commit the regenerated lockfile.)

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl && git add -A && git diff --cached --quiet || git commit -m "chore: regenerated lockfile from clean install

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Live end-to-end verification (both themes, all platforms)

**Files:**
- Possibly modify: anything a live bug points at (each fix = its own commit in `portfyl/`)

**Interfaces:**
- Consumes: running app — backend `uvicorn main:app --reload --port 8000` from `portfyl/backend` (venv python), frontend `npm run dev` (port 5173) from `portfyl/frontend`.

- [ ] **Step 1: Start both servers (background)**

```powershell
cd C:\Users\tomzo\claude\ptf_m\portfyl\backend
Start-Process .venv\Scripts\python.exe -ArgumentList "-m","uvicorn","main:app","--port","8000"
cd ..\frontend
Start-Process npm -ArgumentList "run","dev"
```

Wait for both, then `curl http://localhost:8000/health` → 200, `curl http://localhost:5173` → 200.

- [ ] **Step 2: Browser walkthrough — light mode**

Use the Claude-in-Chrome tools (or Playwright MCP per CLAUDE.md). At `http://localhost:5173`:

1. Login page appears → password `snowball-dev` → lands on PlatformLanding.
2. Choose **Trading 212** → Dashboard renders with data (356-transaction PC dataset), DashboardGrid Customize/Lock works.
3. Visit: Allocation, Transactions (add a dummy transaction → success toast; delete it → styled confirm dialog + toast), Import, Dividends, **Dividend Calendar**, Analytics, Tax Report, Search, **Screener** (run a preset screen → rows render), Watchlists, a Stock detail (e.g. AAPL) → **TTM column** visible in financial charts + **Shares Outstanding** chart renders, Assistant page loads.
4. Back to platform switcher → **IBKR** → Options page renders (64 options trades). → **Polymarket** → positions render (11).
5. Settings: palette switch works (green/blue/purple).
6. Check browser console for errors on each page (react-query fetch failures against yfinance for delisted tickers are tolerable; component crashes/red errors are not).

- [ ] **Step 3: Browser walkthrough — dark mode**

Toggle theme to **Dark** via the Sidebar segmented control. Re-visit: Dashboard, Stock detail, Screener, Dividend Calendar, Settings, **Options and Polymarket (PC-only pages — highest risk: they were written without dark classes)**. Verify: backgrounds flip to dark surfaces, text readable (no dark-on-dark), cards use `--surface-card`, borders visible. Fix contrast bugs by adjusting token usage (prefer `text-ink`/`text-muted`/`bg-surface-card` over hardcoded slate classes) — smallest change that fixes the page. Then toggle **System** and verify it follows the OS.

- [ ] **Step 4: Persistence + rename check**

Restart the backend once → confirm startup migrations run clean against the copied PC data and nothing is lost (transaction count still 356: `GET /api/portfolios` or check Transactions page). Confirm `backend/portfyl.db` is the file in use and no stray `snowball.db` was created.

- [ ] **Step 5: Fix-and-commit loop, then final verification**

Each bug found: fix, re-run the affected check, commit with a descriptive message. When the walkthrough is clean: run `pytest -q` + `npm run build` one final time, commit anything outstanding. Report results honestly — list anything deliberately left imperfect.

- [ ] **Step 6: Cleanup + handoff to user**

Stop the dev servers. Ask the user: (a) delete `merge-work/`? (b) push `portfyl/` to GitHub (new repo vs existing `portfyl` remote — their call); (c) archive/retire `portfyl-pc`/`portfyl-nb` clones in `ptf_m`. Do not push anything without explicit confirmation.

---

## Self-review notes

- **Spec coverage:** union of features (Tasks 2–5), PC look wins (T3 S5, T4 S5), Portfyl naming (T5 S5), AutoLoad over usePrefetch (T3 S8, T5 S4), StockDetail TTM port (T5 S1–3), dark mode × PC tokens (T3 S1/S6, T8 S3), clean repo + .gitignore + flatten (T7), PC DB as portfyl.db (T7 S2), tests pass (T6, T7 S5), live walkthrough both themes (T8), push deferred to user (T8 S6). Auth×tests risk resolved by ground truth (no TestClient) — no task needed beyond T6's failure triage.
- **Type consistency:** `applyAppearance(name, isDark)` used in T3 S6 matches NB's PaletteProvider call; `MetricBarChart` extended signature in T5 S2 matches call sites in T5 S3; `fetchAllTradeNotes` verified before use (T5 S4).
- **Placeholder scan:** market.py hunk-2 NB block is referenced "verbatim from the nb side" rather than reprinted (it is ~200 lines already materialized in the working tree between the conflict markers — the executor keeps it, not writes it). Same for Sidebar body review (T4 S3) — judgment step with explicit acceptance criteria. These are review steps over existing material, not omitted content.
