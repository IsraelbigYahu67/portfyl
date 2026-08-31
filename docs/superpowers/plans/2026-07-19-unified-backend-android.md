# Unified Backend + Free Deploy + Android TWA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One deployed Portfyl backend serving the desktop SPA at `/` and the mobile SPA at `/m`, reachable from any browser and from an installable Android app, with broker auto-syncs working on a $0/month Cloud Run deployment.

**Architecture:** The mobile frontend moves from the `portfyl-mobile` repo into this repo as `frontend-mobile/` (ending the frozen-backend duplication — this repo's backend becomes the only backend). FastAPI serves both built SPAs same-origin; the mobile SPA is re-based to `/m/`. Because Cloud Run scale-to-zero gives background asyncio loops no CPU, the in-process pollers are disabled in prod and a token-protected `/api/jobs/scheduler-tick` endpoint (same pattern as the existing IBKR `scheduler-sync`) is hit by Cloud Scheduler instead. The Android app is a Trusted Web Activity (Bubblewrap) wrapping `https://<service>/m/`, verified via `/.well-known/assetlinks.json`.

**Tech Stack:** FastAPI + SQLAlchemy + SQLite (GCS-volume-mounted), React 18 + Vite 6 (two SPAs), Cloud Run + Cloud Build + Cloud Scheduler + GCS, Bubblewrap CLI (TWA).

## Global Constraints

- **This repo's backend is canonical.** The two backends were verified identical on 2026-07-19 (`diff -rq` clean). After Task 1, `portfyl-mobile` is legacy — never edit it again.
- **Legacy names stay:** `sb_*` localStorage keys, `sb_session` cookie, `snowball.auth` logger, `snowball-dev` dev password fallback.
- **No service worker** in the mobile SPA (market data must not be cached stale). TWA does not require one.
- **Money normalized to CZK** via `fx_to_czk`; do not touch valuation code.
- **Prod pollers off:** Cloud Run deploys set `BROKER_AUTOSYNC_ENABLED=0`, `DIVIDEND_NOTIFY_ENABLED=0`, `ALERT_POLLER_ENABLED=0`; Cloud Scheduler drives `/api/jobs/scheduler-tick` every 30 min.
- **`--max-instances 1` always** on Cloud Run — SQLite must never have two writer instances.
- **Region `us-central1`** for strict $0 (GCS always-free is US regions only). `europe-west1` is allowed if the user accepts ~a few cents/month for storage.
- **TWA package id:** `app.portfyl.twa`. The signing keystore is generated once in Task 8 and must never be committed or lost.
- **Stitch UI redesign is out of scope** — it lands later as a restyle of `frontend-mobile/`.
- Dev ports after this plan: backend **8000**, desktop Vite **5173** (`/`), mobile Vite **5174** (served at `http://localhost:5174/m/`).
- Frontend test suites: desktop `cd frontend && npm test`; mobile `cd frontend-mobile && npm test` (107 tests green as of 2026-07-19). Backend: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -q` (198 green; pytest is not in requirements.txt — install into the venv if missing).

---

### Task 1: Import the mobile frontend into this repo as `frontend-mobile/`

**Files:**
- Create: `frontend-mobile/` (full copy of `../portfyl-mobile/frontend`, minus `node_modules/` and `dist/`)

**Interfaces:**
- Consumes: `c:/Users/tomzo/claude/ptf_m/portfyl-mobile/frontend` at commit `7dc015d` (includes the dividend-calendar clamp fix).
- Produces: `frontend-mobile/package.json` with `npm test` / `npm run build` working — Tasks 2 and 6 build on this exact directory name.

- [ ] **Step 1: Copy the source (Git Bash)**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
mkdir frontend-mobile
tar -C ../portfyl-mobile/frontend --exclude node_modules --exclude dist -cf - . | tar -C frontend-mobile -xf -
ls frontend-mobile   # expect: index.html package.json src public vite.config.js tailwind.config.js postcss.config.js package-lock.json
```

- [ ] **Step 2: Install and run the copied test suite**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/frontend-mobile && npm ci && npm test
```

Expected: `Test Files  26 passed`, `Tests  107 passed`.

- [ ] **Step 3: Commit**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
git add frontend-mobile
git commit -m "feat: import portfyl-mobile frontend as frontend-mobile/ (single-backend unification)"
```

---

### Task 2: Re-base the mobile SPA to `/m/`

**Files:**
- Modify: `frontend-mobile/vite.config.js`
- Modify: `frontend-mobile/src/main.jsx`
- Modify: `frontend-mobile/index.html`
- Modify: `frontend-mobile/public/manifest.webmanifest`
- Create: `frontend-mobile/public/logo-512.png`
- Modify: `start.bat`

**Interfaces:**
- Consumes: Task 1's `frontend-mobile/`.
- Produces: `npm run build` emitting `frontend-mobile/dist` whose asset URLs start with `/m/assets/`; manifest with `start_url`/`scope` = `/m/` and a 512×512 icon (Task 8's Bubblewrap requires ≥512px). Dev proxy now targets the unified backend on **8000** (was 8001).

- [ ] **Step 1: Set the Vite base and retarget the dev proxy**

Replace the `defineConfig` block in `frontend-mobile/vite.config.js` (keep the existing `test` block unchanged):

```js
export default defineConfig({
  base: "/m/",
  plugins: [react()],
  server: {
    port: 5174,
    proxy: {
      // Same-origin routes in dev: /api carries data; /login + /logout keep the
      // password gate working without bouncing between :5174 and :8000.
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/login": { target: "http://localhost:8000", changeOrigin: true },
      "/logout": { target: "http://localhost:8000", changeOrigin: true },
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

- [ ] **Step 2: Give the router the same base**

In `frontend-mobile/src/main.jsx` change:

```jsx
      <BrowserRouter>
```

to:

```jsx
      <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, "")}>
```

(Tests use `MemoryRouter` via `renderWithProviders`, so this doesn't affect them.)

- [ ] **Step 3: Base-relative asset refs in `index.html`**

In `frontend-mobile/index.html` replace lines 7–11:

```html
    <link rel="icon" type="image/png" href="/logo.png" />
    <link rel="manifest" href="/manifest.webmanifest" />
    <link rel="apple-touch-icon" href="/logo.png" />
    <meta name="theme-color" content="#059669" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
```

with:

```html
    <link rel="icon" type="image/png" href="%BASE_URL%logo.png" />
    <link rel="manifest" href="%BASE_URL%manifest.webmanifest" />
    <link rel="apple-touch-icon" href="%BASE_URL%logo.png" />
    <meta name="theme-color" content="#059669" />
    <meta name="mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
```

(`%BASE_URL%` is Vite's built-in HTML env replacement — becomes `/m/` in builds. The extra `mobile-web-app-capable` meta clears the deprecation warning found in the 2026-07-19 walkthrough.)

- [ ] **Step 4: Generate the 512×512 icon**

The current `logo.png` is 342×342; TWA needs ≥512. Upscale for now (replace with a proper export when the Stitch assets land):

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
uv pip install --python backend/.venv/Scripts/python.exe pillow
backend/.venv/Scripts/python.exe -c "from PIL import Image; Image.open('frontend-mobile/public/logo.png').convert('RGBA').resize((512,512), Image.LANCZOS).save('frontend-mobile/public/logo-512.png')"
```

- [ ] **Step 5: Rewrite the manifest for the `/m/` scope**

Replace the whole `frontend-mobile/public/manifest.webmanifest`:

```json
{
  "name": "Portfyl",
  "short_name": "Portfyl",
  "id": "/m/",
  "start_url": "/m/",
  "scope": "/m/",
  "display": "standalone",
  "background_color": "#0F172A",
  "theme_color": "#059669",
  "icons": [
    { "src": "/m/logo.png", "sizes": "342x342", "type": "image/png" },
    { "src": "/m/logo-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any" }
  ]
}
```

- [ ] **Step 6: Add the mobile dev server to `start.bat`**

After the existing frontend block (lines 21–22), insert:

```bat
cd /d "%~dp0frontend-mobile"
start "Portfyl Mobile Frontend" cmd /k "npm install --silent && npm run dev"
```

and change the echo block to:

```bat
echo  Backend:         http://localhost:8000
echo  Frontend:        http://localhost:5173
echo  Mobile frontend: http://localhost:5174/m/
```

- [ ] **Step 7: Verify tests still pass and the build is based on /m/**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/frontend-mobile && npm test && npm run build && grep -c "/m/assets/" dist/index.html
```

Expected: `Tests  107 passed`; build succeeds; grep prints ≥ `1`.

- [ ] **Step 8: Commit**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
git add frontend-mobile start.bat
git commit -m "feat: base the mobile SPA at /m/ (vite base, router basename, PWA manifest, 512px icon)"
```

---

### Task 3: Serve `/m` from FastAPI + return users to where they logged in from

**Files:**
- Modify: `backend/auth.py` (add `safe_next`, extend `login_page_html`)
- Modify: `backend/main.py:345-397` (middleware + login handlers), `backend/main.py:507-518` (insert `/m` serving block **before** the desktop SPA block)
- Test: `backend/tests/test_auth.py` (new)

**Interfaces:**
- Consumes: `frontend-mobile/dist` from Task 2 (present in prod images; may be absent in dev — the mounts are conditional, same as the desktop block).
- Produces: `auth.safe_next(raw: str | None) -> str` (returns a same-origin path or `"/"`); GET `/m/...` serves the mobile SPA; `/login?next=/m/` round-trips so a phone user lands back on `/m/` after login.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_auth.py`:

```python
"""safe_next: only same-origin absolute paths may be used as post-login redirects."""
from auth import safe_next


def test_safe_next_allows_same_origin_paths():
    assert safe_next("/m/") == "/m/"
    assert safe_next("/settings") == "/settings"


def test_safe_next_rejects_everything_else():
    assert safe_next(None) == "/"
    assert safe_next("") == "/"
    assert safe_next("//evil.com") == "/"          # protocol-relative
    assert safe_next("https://evil.com") == "/"    # absolute URL
    assert safe_next("\\\\evil") == "/"            # backslash tricks
```

- [ ] **Step 2: Run it — must fail**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/backend && .venv/Scripts/python.exe -m pytest tests/test_auth.py -v
```

Expected: FAIL — `ImportError: cannot import name 'safe_next'`.

- [ ] **Step 3: Implement `safe_next` and the `next` field in `auth.py`**

Add near `check_password` (after line ~68):

```python
def safe_next(raw: str | None) -> str:
    """Post-login redirect target. Only same-origin absolute paths pass;
    anything else (absolute URLs, protocol-relative //host, backslashes)
    falls back to "/" to prevent open redirects."""
    if raw and raw.startswith("/") and not raw.startswith("//") and "\\" not in raw:
        return raw
    return "/"
```

Change the signature at line ~143 from `def login_page_html(error: bool = False) -> str:` to:

```python
def login_page_html(error: bool = False, next_path: str = "/") -> str:
```

and inside the form (right after the password `<input ...>` at line ~174) add — note the `html.escape` (add `import html` at the top of `auth.py` if absent):

```python
    <input type="hidden" name="next" value="{html.escape(next_path)}" />
```

(the f-string interpolation matches how `error_html` is already injected).

- [ ] **Step 4: Wire `next` through `main.py`**

Add to the imports at the top of `main.py`:

```python
from urllib.parse import quote
```

Change line 354 (`require_login` middleware):

```python
    return RedirectResponse("/login?next=" + quote(request.url.path), status_code=303)
```

Replace the two login handlers (lines 375–389):

```python
@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    nxt = auth.safe_next(request.query_params.get("next"))
    if auth.is_authenticated(request):
        return RedirectResponse(nxt, status_code=303)
    return HTMLResponse(auth.login_page_html(next_path=nxt))


@app.post("/login", include_in_schema=False)
async def login_submit(request: Request):
    form = await request.form()
    nxt = auth.safe_next(form.get("next"))
    if not auth.check_password(form.get("password", "")):
        return HTMLResponse(auth.login_page_html(error=True, next_path=nxt), status_code=401)
    response = RedirectResponse(nxt, status_code=303)
    auth.set_session_cookie(response)
    return response
```

- [ ] **Step 5: Insert the `/m` serving block**

In `main.py`, immediately **before** the `# --- serve the built React SPA (production / same-origin) ---` comment (line ~513) — order matters: these routes must register before the desktop catch-all `/{full_path:path}`:

```python
# --- serve the built mobile SPA under /m (same backend, phone-first UI) --------
# Registered BEFORE the desktop catch-all below so /m/* never falls through to
# the desktop index.html. Conditional like the desktop block: absent in dev
# (use the Vite server on :5174), present in the prod image.
_MDIST = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend-mobile", "dist"))
_MASSETS = os.path.join(_MDIST, "assets")

if os.path.isdir(_MASSETS):
    app.mount("/m/assets", StaticFiles(directory=_MASSETS), name="m-assets")

if os.path.isdir(_MDIST):
    @app.get("/m", include_in_schema=False)
    def m_root():
        return RedirectResponse("/m/", status_code=307)

    @app.get("/m/{full_path:path}", include_in_schema=False)
    def m_spa_fallback(full_path: str):
        # Same containment rules as the desktop fallback below.
        candidate = os.path.normpath(os.path.join(_MDIST, full_path))
        if full_path and candidate.startswith(_MDIST + os.sep) and os.path.isfile(candidate):
            return FileResponse(candidate)
        index_html = os.path.join(_MDIST, "index.html")
        if os.path.isfile(index_html):
            return FileResponse(index_html)
        raise HTTPException(status_code=404)
```

- [ ] **Step 6: Run the tests**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/backend && .venv/Scripts/python.exe -m pytest tests/ -q
```

Expected: all pass (198 existing + 2 new).

- [ ] **Step 7: Live smoke (dev servers running via `start.bat`)**

```bash
curl -s -o /dev/null -w "%{http_code} %{redirect_url}\n" http://localhost:8000/m/
```

Expected: `303 http://localhost:8000/login?next=/m/` (unauthenticated → gate with next). Then in a browser: log in from `http://localhost:8000/login?next=/m/` — after Task 6's image build (or a manual `npm run build` in `frontend-mobile/`) you land on the mobile UI.

- [ ] **Step 8: Commit**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
git add backend/auth.py backend/main.py backend/tests/test_auth.py
git commit -m "feat: serve mobile SPA at /m and preserve login destination via ?next="
```

---

### Task 4: `/api/jobs/scheduler-tick` — machine-triggered job pass for scale-to-zero

**Files:**
- Create: `backend/routers/jobs_api.py`
- Modify: `backend/main.py:342` (`_PUBLIC_PATHS`), `backend/main.py:399-415` (router includes)
- Test: `backend/tests/test_jobs_api.py` (new)

**Interfaces:**
- Consumes: `jobs.autosync_tick(db)`, `jobs.dividend_exdate_pass(db)`, `routers.alerts.run_check(db)` (all existing async, take a `Session`), `auth.check_scheduler_token(submitted: str) -> bool`.
- Produces: `POST /api/jobs/scheduler-tick` returning `{"status": "ok", "autosync": [...], "dividends": [...], "alerts": [...]}`; 403 without a valid `SCHEDULER_TOKEN` (header `X-Scheduler-Token` or `?token=`). Task 7's Cloud Scheduler job calls this.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_jobs_api.py`:

```python
"""scheduler-tick: the Cloud Scheduler entrypoint that replaces the in-process
pollers on scale-to-zero deployments."""
import asyncio

import pytest
from fastapi import HTTPException


def _run(coro):
    return asyncio.run(coro)


def test_scheduler_tick_rejects_bad_token(db_session, monkeypatch):
    import auth
    monkeypatch.setattr(auth, "SCHEDULER_TOKEN", "tok")
    from routers.jobs_api import scheduler_tick

    with pytest.raises(HTTPException) as exc:
        _run(scheduler_tick(db=db_session, x_scheduler_token="wrong", token=None))
    assert exc.value.status_code == 403


def test_scheduler_tick_runs_all_passes(db_session, monkeypatch):
    import auth
    import jobs
    from routers import alerts as alerts_router
    monkeypatch.setattr(auth, "SCHEDULER_TOKEN", "tok")

    calls = []

    async def fake_autosync(db, now=None):
        calls.append("autosync")
        return []

    async def fake_dividends(db, today=None, lead_days=3):
        calls.append("dividends")
        return []

    async def fake_alerts(db):
        calls.append("alerts")
        return []

    monkeypatch.setattr(jobs, "autosync_tick", fake_autosync)
    monkeypatch.setattr(jobs, "dividend_exdate_pass", fake_dividends)
    monkeypatch.setattr(alerts_router, "run_check", fake_alerts)

    from routers.jobs_api import scheduler_tick
    out = _run(scheduler_tick(db=db_session, x_scheduler_token="tok", token=None))
    assert out["status"] == "ok"
    assert calls == ["autosync", "dividends", "alerts"]
```

- [ ] **Step 2: Run — must fail**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/backend && .venv/Scripts/python.exe -m pytest tests/test_jobs_api.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'routers.jobs_api'`.

- [ ] **Step 3: Implement the router**

Create `backend/routers/jobs_api.py`:

```python
"""Machine-triggered job runner for scale-to-zero deployments.

On always-on hosts the in-process pollers in main.py run these passes. On
Cloud Run with min-instances=0 those asyncio loops get no CPU between
requests, so the pollers are disabled (*_ENABLED=0) and Cloud Scheduler
POSTs here on a cron instead. Auth mirrors the IBKR scheduler-sync
endpoint: SCHEDULER_TOKEN via X-Scheduler-Token header or ?token= query.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from auth import check_scheduler_token
from database import get_db

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/scheduler-tick", include_in_schema=False)
async def scheduler_tick(
    db: Session = Depends(get_db),
    x_scheduler_token: str | None = Header(default=None),
    token: str | None = Query(default=None),
):
    if not check_scheduler_token(x_scheduler_token or token or ""):
        raise HTTPException(status_code=403, detail="Invalid or missing scheduler token")

    # Module-attribute access at call time (not from-imports at module top) so
    # tests can monkeypatch, mirroring main.py's lazy poller imports.
    import jobs
    from routers import alerts

    results: dict = {"status": "ok"}
    # autosync consults the user's saved schedule (Settings -> Auto-sync
    # schedule) and syncs only when due — the cron just provides the ticks.
    # A raised error here surfaces as a 500 so the scheduler sees the failure.
    results["autosync"] = await jobs.autosync_tick(db)
    try:
        results["dividends"] = await jobs.dividend_exdate_pass(db)
    except Exception:
        results["dividends"] = "error"
    try:
        results["alerts"] = await alerts.run_check(db)
    except Exception:
        results["alerts"] = "error"
    return results
```

- [ ] **Step 4: Register the router and open its path through the gate**

In `main.py` line 342, change `_PUBLIC_PATHS` to:

```python
_PUBLIC_PATHS = {"/health", "/login", "/logout", "/api/broker/ibkr/scheduler-sync",
                 "/api/jobs/scheduler-tick"}
```

Add `jobs_api` to the existing `from routers import ...` line, and after line 415 (`app.include_router(settings.router, prefix="/api")`):

```python
app.include_router(jobs_api.router, prefix="/api")
```

- [ ] **Step 5: Run the tests**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/backend && .venv/Scripts/python.exe -m pytest tests/test_jobs_api.py tests/test_jobs.py -v
```

Expected: all PASS (new tests + existing jobs tests untouched).

- [ ] **Step 6: Commit**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
git add backend/routers/jobs_api.py backend/main.py backend/tests/test_jobs_api.py
git commit -m "feat: token-protected /api/jobs/scheduler-tick for Cloud Scheduler deployments"
```

---

### Task 5: `/.well-known/assetlinks.json` for the TWA

**Files:**
- Create: `backend/routers/wellknown.py`
- Modify: `backend/main.py:342` (`_PUBLIC_PATHS`), router includes (after Task 4's line)
- Test: `backend/tests/test_wellknown.py` (new)

**Interfaces:**
- Consumes: env vars `TWA_SHA256_FINGERPRINT` (set in Task 8), optional `TWA_PACKAGE_NAME` (default `app.portfyl.twa`).
- Produces: GET `/.well-known/assetlinks.json` → Digital Asset Links JSON when the fingerprint env is set; 404 otherwise. Android uses this to verify the TWA owns the origin (removes the browser URL bar).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_wellknown.py`:

```python
"""assetlinks.json: Android Digital Asset Links for the TWA wrapper."""
import json

import pytest
from fastapi import HTTPException


def test_assetlinks_404_when_unconfigured(monkeypatch):
    monkeypatch.delenv("TWA_SHA256_FINGERPRINT", raising=False)
    from routers.wellknown import assetlinks
    with pytest.raises(HTTPException) as exc:
        assetlinks()
    assert exc.value.status_code == 404


def test_assetlinks_serves_fingerprint(monkeypatch):
    monkeypatch.setenv("TWA_SHA256_FINGERPRINT", "AA:BB:CC")
    monkeypatch.delenv("TWA_PACKAGE_NAME", raising=False)
    from routers.wellknown import assetlinks
    body = json.loads(assetlinks().body)
    assert body[0]["relation"] == ["delegate_permission/common.handle_all_urls"]
    assert body[0]["target"]["package_name"] == "app.portfyl.twa"
    assert body[0]["target"]["sha256_cert_fingerprints"] == ["AA:BB:CC"]
```

- [ ] **Step 2: Run — must fail**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/backend && .venv/Scripts/python.exe -m pytest tests/test_wellknown.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'routers.wellknown'`.

- [ ] **Step 3: Implement**

Create `backend/routers/wellknown.py`:

```python
"""Digital Asset Links for the Android TWA wrapper (Task: unified deploy).

Served only when TWA_SHA256_FINGERPRINT is configured, so deployments without
an Android app expose nothing at /.well-known/.
"""
import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/.well-known/assetlinks.json", include_in_schema=False)
def assetlinks():
    fp = os.environ.get("TWA_SHA256_FINGERPRINT")
    if not fp:
        raise HTTPException(status_code=404)
    return JSONResponse([{
        "relation": ["delegate_permission/common.handle_all_urls"],
        "target": {
            "namespace": "android_app",
            "package_name": os.environ.get("TWA_PACKAGE_NAME", "app.portfyl.twa"),
            "sha256_cert_fingerprints": [fp],
        },
    }])
```

In `main.py`: add `wellknown` to the `from routers import ...` line; include it **without** the `/api` prefix (after the Task 4 include):

```python
app.include_router(wellknown.router)
```

and extend `_PUBLIC_PATHS` (line 342) with the new path:

```python
_PUBLIC_PATHS = {"/health", "/login", "/logout", "/api/broker/ibkr/scheduler-sync",
                 "/api/jobs/scheduler-tick", "/.well-known/assetlinks.json"}
```

- [ ] **Step 4: Run the tests**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/backend && .venv/Scripts/python.exe -m pytest tests/test_wellknown.py -v
```

Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
git add backend/routers/wellknown.py backend/main.py backend/tests/test_wellknown.py
git commit -m "feat: serve /.well-known/assetlinks.json for the Android TWA"
```

---

### Task 6: Dockerfile builds both SPAs

**Files:**
- Modify: `Dockerfile`
- Modify (or create): `.dockerignore`

**Interfaces:**
- Consumes: Task 2's `frontend-mobile/` (with `npm run build` working), Task 3's `_MDIST` path `../frontend-mobile/dist` (resolves to `/app/frontend-mobile/dist` in the image).
- Produces: one image serving `/` (desktop) and `/m/` (mobile). Task 7 deploys it via Cloud Build (`gcloud run deploy --source .` uses this Dockerfile).

- [ ] **Step 1: Add the mobile build stage**

In `Dockerfile`, after the existing `frontend` stage, add:

```dockerfile
# ---- Stage 1b: build the mobile React frontend --------------------------------
FROM node:22-alpine AS frontend_mobile
WORKDIR /app/frontend-mobile
COPY frontend-mobile/package.json frontend-mobile/package-lock.json ./
RUN npm ci
COPY frontend-mobile/ ./
RUN npm run build
```

and in the `runtime` stage, after the existing `COPY --from=frontend ...` line:

```dockerfile
# Mobile SPA -> served by FastAPI at /m (main.py reads ../frontend-mobile/dist).
COPY --from=frontend_mobile /app/frontend-mobile/dist ./frontend-mobile/dist
```

- [ ] **Step 2: Keep junk out of the build context**

Append to `.dockerignore` (create it with exactly these lines if it doesn't exist):

```
frontend-mobile/node_modules
frontend-mobile/dist
twa/
```

- [ ] **Step 3: Verify locally if Docker Desktop is available (otherwise Task 7's Cloud Build is the verification)**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
docker build -t portfyl-test . && docker run --rm -p 8080:8080 -e APP_PASSWORD=test portfyl-test &
sleep 15 && curl -s -o /dev/null -w "root:%{http_code}\n" http://localhost:8080/login
curl -s -o /dev/null -w "m:%{http_code} %{redirect_url}\n" http://localhost:8080/m/
```

Expected: `root:200`, `m:303 .../login?next=/m/`.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile .dockerignore
git commit -m "build: compile both SPAs into the image (desktop at /, mobile at /m)"
```

---

### Task 7: Deploy to Cloud Run (free tier) with working syncs

**Files:** none in-repo (cloud config). Record the service URL in the final commit message of Task 9.

**Interfaces:**
- Consumes: the Task 6 image; `backend/portfyl.db` (local seed DB); Task 4's tick endpoint.
- Produces: `https://portfyl-<hash>-uc.a.run.app` serving both UIs; a Cloud Scheduler job ticking syncs every 30 min. Task 8 wraps this URL.

**Free-tier maths (why this is $0):** single-user traffic is a rounding error against Cloud Run's always-free allotment (180k vCPU-s, 360k GiB-s, 2M requests/month); Cloud Scheduler's first 3 jobs are free (we use 1); GCS ≤5 GB is free in US regions. A billing account (card) must be attached, but nothing at this scale bills. Cold starts add a few seconds to the first request after idle — normal for scale-to-zero.

- [ ] **Step 1: Project + APIs (one-time; requires `gcloud` CLI and browser login)**

```bash
gcloud auth login
gcloud projects create portfyl-app --name="Portfyl"    # pick a unique id if taken, e.g. portfyl-app-<initials>
gcloud config set project portfyl-app
# Attach billing in the console (required once): https://console.cloud.google.com/billing
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com cloudscheduler.googleapis.com storage.googleapis.com
```

- [ ] **Step 2: Bucket + seed the database**

```bash
gcloud storage buckets create gs://portfyl-app-data --location=us-central1 --uniform-bucket-level-access
gcloud storage cp /c/Users/tomzo/claude/ptf_m/portfyl/backend/portfyl.db gs://portfyl-app-data/portfyl.db
```

- [ ] **Step 3: Generate secrets (save both somewhere safe — a password manager)**

```bash
python -c "import secrets; print('APP_PASSWORD:', secrets.token_urlsafe(18)); print('SCHEDULER_TOKEN:', secrets.token_urlsafe(24))"
```

- [ ] **Step 4: Deploy**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
gcloud run deploy portfyl --source . --region us-central1 \
  --allow-unauthenticated --min-instances 0 --max-instances 1 \
  --memory 1Gi --cpu 1 --timeout 300 \
  --add-volume name=data,type=cloud-storage,bucket=portfyl-app-data \
  --add-volume-mount volume=data,mount-path=/data \
  --set-env-vars "DATABASE_PATH=/data/portfyl.db,APP_PASSWORD=<from step 3>,SCHEDULER_TOKEN=<from step 3>,BROKER_AUTOSYNC_ENABLED=0,DIVIDEND_NOTIFY_ENABLED=0,ALERT_POLLER_ENABLED=0"
```

Expected: Cloud Build compiles both SPA stages, then `Service URL: https://portfyl-....run.app`. (`--max-instances 1` is non-negotiable: SQLite, one writer.)

- [ ] **Step 5: Smoke the deployment**

```bash
URL=https://portfyl-....run.app   # from step 4
curl -s -o /dev/null -w "health:%{http_code}\n" $URL/health
curl -s -o /dev/null -w "root:%{http_code} %{redirect_url}\n" $URL/
curl -s -o /dev/null -w "m:%{http_code} %{redirect_url}\n" $URL/m/
```

Expected: `health:200`; root and m redirect `303` to `/login?next=...`. Then in a real browser: log in at `$URL` (desktop UI, zubik data) and `$URL/m/` (mobile UI).

- [ ] **Step 6: Cloud Scheduler tick (this is what makes syncs work while scaled to zero)**

```bash
gcloud scheduler jobs create http portfyl-tick --location us-central1 \
  --schedule "*/30 * * * *" --time-zone "Europe/Prague" \
  --uri "$URL/api/jobs/scheduler-tick" --http-method POST \
  --headers "X-Scheduler-Token=<SCHEDULER_TOKEN from step 3>" \
  --attempt-deadline 300s
gcloud scheduler jobs run portfyl-tick --location us-central1
gcloud run services logs read portfyl --region us-central1 --limit 20
```

Expected: the manual run returns without error and logs show the tick request. Note the semantics: the cron fires every 30 min, but `autosync_tick` only syncs when the schedule saved in Settings says it's due — so "daily at 02:00" runs at the 02:00 tick, and the Settings page stays the source of truth.

---

### Task 8: Android app (TWA via Bubblewrap)

**Files:**
- Create: `twa/` (Bubblewrap project; `twa/` is in `.dockerignore`. Commit `twa/twa-manifest.json`; **never** commit `*.keystore`)
- Modify: `.gitignore` (keystore + build outputs)

**Interfaces:**
- Consumes: `https://<service>/m/manifest.webmanifest` (Task 2/7), the `TWA_SHA256_FINGERPRINT` env consumed by Task 5's endpoint.
- Produces: `app-release-signed.apk` installable on the user's phone; package id `app.portfyl.twa`.

- [ ] **Step 1: Ignore the signing material**

Append to `.gitignore`:

```
twa/*.keystore
twa/app-release-*.apk
twa/app-release-*.aab
twa/build/
```

- [ ] **Step 2: Init the TWA project (first run downloads JDK + Android SDK — accept the prompts)**

```bash
npm i -g @bubblewrap/cli
mkdir -p /c/Users/tomzo/claude/ptf_m/portfyl/twa && cd /c/Users/tomzo/claude/ptf_m/portfyl/twa
bubblewrap init --manifest "https://<service-url>/m/manifest.webmanifest"
```

Prompt answers: Domain = the Cloud Run host; Start URL/path = `/m/`; App name = `Portfyl`; Package ID = `app.portfyl.twa`; Display = standalone; theme `#059669`; signing key = **create new** → keystore `twa/android.keystore` — save the keystore file and both passwords with the Task 7 secrets (losing it means a new package identity).

- [ ] **Step 3: Build the APK and capture the signing fingerprint**

```bash
bubblewrap build
# Fingerprint (also printed during build):
keytool -list -v -keystore android.keystore -alias android | grep "SHA256:"
```

Expected: `app-release-signed.apk` in `twa/`; a fingerprint like `SHA256: AA:BB:...` (32 colon-separated byte pairs).

- [ ] **Step 4: Publish the fingerprint so Android trusts the origin**

```bash
gcloud run services update portfyl --region us-central1 \
  --update-env-vars "TWA_SHA256_FINGERPRINT=<AA:BB:... from step 3>"
curl https://<service-url>/.well-known/assetlinks.json
```

Expected: the assetlinks JSON with `app.portfyl.twa` and the fingerprint.

- [ ] **Step 5: Install on the phone**

Either `adb install app-release-signed.apk` (USB debugging), or copy the APK to the phone and open it (allow "install unknown apps"). Launch **Portfyl**: it must open full-screen on `/m/` with **no browser URL bar** (URL bar visible = assetlinks mismatch — re-check step 4's fingerprint). Log in once; the `sb_session` cookie persists.

- [ ] **Step 6: Commit the reproducible parts**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl
git add .gitignore twa/twa-manifest.json
git commit -m "feat: Android TWA project (app.portfyl.twa) wrapping /m"
```

---

### Task 9: Final verification + docs

**Files:**
- Modify: `CLAUDE.md` (this repo), `../portfyl-mobile/README.md` (deprecation notice)

**Interfaces:** consumes everything; produces the verified, documented system.

- [ ] **Step 1: Full test suites**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl/frontend && npm test
cd /c/Users/tomzo/claude/ptf_m/portfyl/frontend-mobile && npm test && npm run build
cd /c/Users/tomzo/claude/ptf_m/portfyl/backend && .venv/Scripts/python.exe -m pytest tests/ -q
```

Expected: all green (mobile 107; backend 198 + 6 new across test_auth/test_jobs_api/test_wellknown).

- [ ] **Step 2: Playwright MCP walkthrough of the deployed URL** — desktop viewport on `https://<service>/` (login lands back on `/`, Dashboard shows zubik data) and 390×844 on `https://<service>/m/` (login lands back on `/m/`, Home hero shows a non-zero CZK value, bottom tabs work, no console errors). Confirm the Settings → Auto-sync schedule card shows the expected next-run time, and after the next scheduled boundary check `gcloud run services logs read portfyl --region us-central1` for the sync having fired.

- [ ] **Step 3: Update `CLAUDE.md`** — in the **Stack** section add: `**Mobile**: phone-first SPA in \`frontend-mobile/\` (Vite base \`/m/\`, port 5174 in dev), served by FastAPI at \`/m\`; wrapped by the Android TWA in \`twa/\` (package \`app.portfyl.twa\`).` In **Run it** add the mobile dev URL `http://localhost:5174/m/`. In **Architecture & conventions** add: `**Prod deploys are scale-to-zero**: in-process pollers are disabled (\`*_ENABLED=0\`) and Cloud Scheduler POSTs \`/api/jobs/scheduler-tick\` (SCHEDULER_TOKEN auth) every 30 min; the Settings-page schedule still decides when a sync actually runs.`

- [ ] **Step 4: Deprecate the old repo** — prepend to `../portfyl-mobile/README.md`:

```markdown
> **⚠️ MERGED:** This repo is archived. The mobile frontend now lives in the
> main portfyl repo as `frontend-mobile/` (served at `/m` by the shared
> backend). Do not commit here.
```

- [ ] **Step 5: Commit (both repos)**

```bash
cd /c/Users/tomzo/claude/ptf_m/portfyl && git add CLAUDE.md && git commit -m "docs: unified backend, /m mobile SPA, Cloud Run + TWA deploy story (service URL: <paste>)"
cd /c/Users/tomzo/claude/ptf_m/portfyl-mobile && git add README.md && git commit -m "docs: archived — frontend merged into portfyl as frontend-mobile/"
```

---

## Self-review notes (done at planning time)

- **Coverage:** unify → T1; /m base → T2; serve + login-next → T3; syncs-on-free-tier → T4+T7; TWA verification chain → T5+T8; image → T6; docs/verify → T9.
- **Ordering trap checked:** `/m/{full_path:path}` registers before the desktop catch-all because the block is inserted earlier in `main.py` (Starlette matches in registration order).
- **Test-style honesty:** backend tests call router functions directly (no TestClient) per repo convention — middleware behavior is smoke-tested with `curl`, not pytest.
- **Type consistency:** `safe_next` (T3) used by both login handlers; `check_scheduler_token` reused verbatim from the existing IBKR pattern; `TWA_SHA256_FINGERPRINT` name identical in T5 and T8; `frontend-mobile/dist` path identical in T3 (`_MDIST`) and T6 (COPY target).
- **Known judgment calls:** the 512px icon is an upscale until Stitch assets arrive; `us-central1` chosen for strict $0 (swap to `europe-west1` for ~cents/month and lower latency); alerts/dividends included in the tick so no prod feature silently dies.
