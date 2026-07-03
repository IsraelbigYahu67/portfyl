# Portfyl

Self-hosted portfolio analytics for a Trading 212 / IBKR investor. Import broker
CSVs (or sync via API), then view performance, allocation, dividends, options,
tax reports, and an AI assistant across one or more portfolios. Single-user today.
(Formerly "Snowball Analytics" — some internal identifiers still carry the `sb_`
/ `snowball.*` prefix for backwards compatibility; see the naming notes below.)

## Stack

- **Backend**: FastAPI + SQLAlchemy 2.0, SQLite (`backend/portfyl.db`, legacy
  `snowball.db` auto-renamed on first startup). Market
  data via `yfinance`; `pandas`/`numpy` for calcs; `httpx` for outbound calls.
- **Frontend**: React 18 + Vite 6, TailwindCSS, `recharts`, `@tanstack/react-query`,
  `axios`, `react-router-dom` 7. SPA in `frontend/src` (pages + components).
- **Deploy**: multi-stage `Dockerfile` → Cloud Run. SQLite lives on a mounted GCS
  volume in prod (`DATABASE_PATH`), never baked into the image.

## Run it

- **Dev (Windows)**: `start.bat` bootstraps the backend venv with **uv** on first
  run (`uv venv .venv --python 3.12`, then `uv pip install -r requirements.txt`),
  launches backend (`uvicorn main:app --reload`, port **8000**) + frontend
  (`npm run dev`, port **5173**) and opens the browser. Use **http://localhost:5173**
  — Vite proxies `/api`, `/login`, `/logout` → :8000. (Install uv from
  https://docs.astral.sh/uv/ if the bootstrap step errors out.)
- **Backend only**: activate the `.venv` uv created, then from `backend/`,
  `python -m uvicorn main:app --reload --port 8000`.
- **Prod build**: `npm run build` emits `frontend/dist`, which FastAPI serves as a
  same-origin SPA (see SPA fallback at the bottom of `main.py`).
- **Login**: a single password gate. Dev fallback password is `snowball-dev`
  (set `APP_PASSWORD` to override). Unauthenticated `/api` calls get 401; page
  routes redirect to `/login`.

## Architecture & conventions (read before editing)

- **All API routes are under `/api`** (mounted with that prefix in `main.py`).
  Routers live in `backend/routers/`: portfolio(s), market, analytics, broker,
  ibkr, watchlists, benchmarks, options, polymarket, discord, notes, assistant,
  dividend_calendar.
- **Portfolio scoping is implicit.** The axios interceptor in `frontend/src/api.js`
  auto-injects `portfolio_id` from the active portfolio into every request —
  call sites never pass it. **Exceptions**: prefixes in `PORTFOLIO_AGNOSTIC_PREFIXES`
  (`/portfolios`, `/market`, `/watchlists`) must NOT receive it. If you add a
  cross-portfolio endpoint, add its prefix there or it will 404/mis-route.
- **`owner_id` is always `"default"`.** The app is single-user; `auth.get_current_user()`
  returns the `"default"` sentinel stamped on every row. The column exists so
  per-user isolation can land later without a schema rewrite — keep it.
- **DB migrations are imperative, at startup.** There is **no Alembic**. `main.py`
  runs `Base.metadata.create_all()` then a series of idempotent `_ensure_*` /
  `_backfill_*` helpers (raw `ALTER TABLE` / table rebuilds for SQLite). When you
  add a column/table, add a matching idempotent helper there — don't assume the
  user will drop their `portfyl.db` (a legacy `snowball.db` is auto-renamed to
  `portfyl.db` at startup by `database.py` before the engine is created).
- **Money / FX**: transactions carry `fx_to_czk`; values are normalized to **CZK**.
  Missing rates are backfilled at startup via `fx.bulk_fetch_fx`. Preserve this
  when touching valuation/performance code.
- **Valuation uses the 5-year average P/E, not the current P/E.** This is a
  deliberate methodology choice for fair-value / valuation calcs.
- **yfinance is noisy.** "possibly delisted" / "no earnings dates" errors are
  expected for thin tickers; logging is suppressed to CRITICAL and missing data
  is handled with empty/null checks. Don't "fix" these by adding noise back.

## Gotchas

- Build artifacts (`frontend/dist`, `node_modules`, `__pycache__`, `*.db`, `.venv`)
  are **git-ignored** — don't commit them. (They were tracked in an earlier import
  and scrubbed on export; see `.gitignore`.)
- Pages: `frontend/src/pages/` (Dashboard, Allocation, Analytics, Dividends,
  Dividend Calendar, Options, Polymarket, Screener, TaxReport, Transactions,
  Watchlists, Import, Settings, Stock, Search, Assistant, PlatformLanding).
  Reusable charts/widgets in `frontend/src/components/`.
- Sample import data: `sample_portfolio.csv` at the project root.

## Naming (Snowball → Portfyl)

The product was renamed from "Snowball Analytics" to **Portfyl**. User-visible
strings are all Portfyl, but a handful of internal identifiers deliberately keep
the old prefix because renaming them would break existing installs: `sb_*`
localStorage keys (theme/palette/currency prefs), the `sb_session` auth cookie,
the `snowball.auth` logger name, and the `snowball-dev` dev-password fallback
(`APP_PASSWORD` overrides it). Don't "finish" the rename on these.

## Backend tests (`backend/tests/`)

- **pytest** suite (7 modules: `test_portfolio`, `test_analytics`, `test_broker`,
  `test_cache`, `test_fx`, `test_dividend_calendar`, `test_market`). Run from
  `backend/`: `python -m pytest tests/ -v`.
- **pytest is NOT in `requirements.txt`** — install it into the venv separately
  (`uv pip install pytest` / `pip install pytest`) before running the suite.
- Tests **do not use `TestClient`** — they call router functions directly against
  an in-memory SQLite session (see `tests/helpers.py`), so the `/api` auth
  middleware is bypassed and no live server / real DB is needed.
- `tests/conftest.py` patches `os.rename` **before** importing `database.py` so the
  legacy `snowball.db → portfyl.db` startup rename doesn't touch the real filesystem.

## Verifying UI changes

Playwright MCP is installed. To check a frontend change, ensure the dev servers
are running (`start.bat`), then drive **http://localhost:5173** — logging in with
the dev password — and screenshot/inspect rather than guessing from the diff.
