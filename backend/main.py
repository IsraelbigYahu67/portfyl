import logging
import os

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# yfinance logs "possibly delisted" / "no earnings dates found" at ERROR
# level for tickers Yahoo simply lacks data for (newly-listed names like
# AVEX, ETFs missing under their LSE symbol, etc). Our code handles missing
# data gracefully via empty/null checks; suppress the noise.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

from database import SessionLocal, assert_alembic_head
from routers import portfolio, market, analytics, broker, portfolios, watchlists, benchmarks, ibkr, options, polymarket, discord, notes, assistant, cash, alerts, settings
import auth

app = FastAPI(title="Portfyl API", version="1.0.0")


# --- password gate ------------------------------------------------------------
# Paths reachable without a session: the login screen and its POST, logout, the
# Cloud Run health check, and the scheduler sync endpoint (which authenticates
# with its own SCHEDULER_TOKEN instead of the session cookie).
_PUBLIC_PATHS = {"/health", "/login", "/logout", "/api/auth/login", "/api/broker/ibkr/scheduler-sync"}


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    # OPTIONS (CORS preflight) and the public paths skip the gate; everything else
    # requires a valid signed session cookie.
    if request.method == "OPTIONS" or path in _PUBLIC_PATHS or auth.is_authenticated(request):
        return await call_next(request)
    if path.startswith("/api"):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)
    return RedirectResponse("/login", status_code=303)


# CORS is added after the gate so it wraps it and its headers apply to every
# response (including the 401 above). The desktop SPA is same-origin (baked into
# the image), but the native app calls cross-origin from Capacitor's local
# origins, so those are allowed here; FRONTEND_ORIGIN adds any extras.
_cors_origins = [
    "http://localhost:5173",   # Vite dev server
    "http://localhost:3000",
    "https://localhost",       # Capacitor Android (androidScheme: "https")
    "capacitor://localhost",   # Capacitor default / iOS scheme
]
_frontend_origin = os.getenv("FRONTEND_ORIGIN")
if _frontend_origin:
    # Optional extra allowed origin(s), comma-separated (e.g. a hosted frontend).
    _cors_origins.extend(o.strip() for o in _frontend_origin.split(",") if o.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    if auth.is_authenticated(request):
        return RedirectResponse("/", status_code=303)
    return HTMLResponse(auth.login_page_html())


@app.post("/login", include_in_schema=False)
async def login_submit(request: Request):
    form = await request.form()
    if not auth.check_password(form.get("password", "")):
        return HTMLResponse(auth.login_page_html(error=True), status_code=401)
    response = RedirectResponse("/", status_code=303)
    auth.set_session_cookie(response)
    return response


@app.post("/api/auth/login", include_in_schema=False)
async def api_login(request: Request):
    """JSON login for native clients: {"password": ...} -> {"token": ...}.

    The token is the same signed session value the cookie carries; the app stores
    it and sends it back as `Authorization: Bearer <token>`, which the auth gate
    accepts via auth.is_authenticated(). Cross-origin, so cookies aren't used here.
    """
    body: dict = {}
    try:
        parsed = await request.json()
        if isinstance(parsed, dict):
            body = parsed
    except Exception:
        pass
    token = auth.login_token(body.get("password", ""))
    if token is None:
        return JSONResponse({"detail": "Incorrect password"}, status_code=401)
    return JSONResponse({"token": token})


@app.get("/logout", include_in_schema=False)
def logout():
    response = RedirectResponse("/login", status_code=303)
    auth.clear_session_cookie(response)
    return response


app.include_router(portfolios.router, prefix="/api")
app.include_router(portfolio.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
app.include_router(broker.router, prefix="/api")
app.include_router(watchlists.router, prefix="/api")
app.include_router(benchmarks.router, prefix="/api")
app.include_router(ibkr.router, prefix="/api")
app.include_router(options.router, prefix="/api")
app.include_router(polymarket.router, prefix="/api")
app.include_router(discord.router, prefix="/api")
app.include_router(notes.router, prefix="/api")
app.include_router(assistant.router, prefix="/api")
app.include_router(cash.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(settings.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}


# --- background pollers --------------------------------------------------------
# The app has no external scheduler, so asyncio tasks handle the recurring work:
#   * price alerts  — every ALERT_CHECK_INTERVAL_SECONDS (default 15 min),
#                     opt-out ALERT_POLLER_ENABLED=0
#   * broker sync   — 60 s heartbeat; jobs.autosync_tick runs the sync when the
#                     configured schedule says so (Settings → Auto-sync
#                     schedule: daily at HH:MM — default 02:00 Europe/Prague,
#                     BROKER_SYNC_TIMEZONE overrides — or every N hours).
#                     Opt-out BROKER_AUTOSYNC_ENABLED=0; only connections whose
#                     auto_sync flag is on are synced (per-portfolio opt-in).
#                     Last-run is persisted, so a missed boundary (asleep at
#                     2 AM) catches up at the first tick after startup.
#   * dividends     — every DIVIDEND_NOTIFY_INTERVAL_SECONDS (default 12 h),
#                     opt-out DIVIDEND_NOTIFY_ENABLED=0; announces ex-dates due
#                     within DIVIDEND_NOTIFY_LEAD_DAYS (default 3), each at most
#                     once (dividend_notifications dedup table)
# Each tick uses its own DB session and swallows errors so a bad pass never
# takes the app down. While the process is asleep between ticks nothing fires —
# these are self-hosted convenience pollers, not low-latency feeds.
_BG_TASKS: list = []


async def _periodic_loop(name: str, pass_fn, interval: int, initial_delay: int):
    """Run `await pass_fn(db)` every `interval` seconds, forever. `pass_fn`
    returns a list of things that happened (logged when non-empty)."""
    import asyncio as _asyncio

    logger = logging.getLogger(f"portfyl.{name}")
    delay = initial_delay
    while True:
        try:
            await _asyncio.sleep(delay)
            delay = interval
            db = SessionLocal()
            try:
                happened = await pass_fn(db)
                if happened:
                    logger.info("%s pass: %d event(s)", name, len(happened))
            finally:
                db.close()
        except _asyncio.CancelledError:
            break
        except Exception:
            logger.exception("%s pass failed", name)


@app.on_event("startup")
async def _start_background_pollers():
    import asyncio as _asyncio
    from routers.alerts import run_check
    from jobs import autosync_tick, dividend_exdate_pass

    schema_db = SessionLocal()
    try:
        assert_alembic_head(schema_db)
    finally:
        schema_db.close()

    def _env_int(key: str, default: int) -> int:
        try:
            return int(os.environ.get(key, default))
        except ValueError:
            return default

    if os.environ.get("ALERT_POLLER_ENABLED", "1") == "1":
        interval = _env_int("ALERT_CHECK_INTERVAL_SECONDS", 900)
        _BG_TASKS.append(_asyncio.create_task(
            _periodic_loop("alerts", run_check, interval, initial_delay=interval)))

    if os.environ.get("BROKER_AUTOSYNC_ENABLED", "1") == "1":
        # 60 s heartbeat: each tick asks jobs.autosync_tick whether the
        # configured schedule is due; the sync itself runs only then. Short
        # initial delay so a restart quickly catches up on a missed boundary
        # (the persisted last-run makes early ticks safe).
        _BG_TASKS.append(_asyncio.create_task(
            _periodic_loop("autosync", autosync_tick, interval=60, initial_delay=300)))

    if os.environ.get("DIVIDEND_NOTIFY_ENABLED", "1") == "1":
        interval = _env_int("DIVIDEND_NOTIFY_INTERVAL_SECONDS", 43200)
        lead = _env_int("DIVIDEND_NOTIFY_LEAD_DAYS", 3)

        async def _dividend_pass(db, _lead=lead):
            return await dividend_exdate_pass(db, lead_days=_lead)

        # Short initial delay (not a full interval): a restart shouldn't be able
        # to skip today's ex-date check — the dedup table makes early runs safe.
        _BG_TASKS.append(_asyncio.create_task(
            _periodic_loop("dividends", _dividend_pass, interval, initial_delay=300)))


@app.on_event("shutdown")
async def _stop_background_pollers():
    while _BG_TASKS:
        _BG_TASKS.pop().cancel()


# --- serve the built React SPA (production / same-origin) ---------------------
# In dev you use the Vite server on :5173 (which proxies /api, /login, /logout
# here), so dist/ may be absent; we mount it only when present. The gate above
# runs first, so an unauthenticated visit to any SPA route is redirected to
# /login before the app shell is ever served.
_DIST = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist"))
_ASSETS = os.path.join(_DIST, "assets")

if os.path.isdir(_ASSETS):
    app.mount("/assets", StaticFiles(directory=_ASSETS), name="assets")

if os.path.isdir(_DIST):
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        # Never shadow the API / auth / health routes (they match first anyway).
        if full_path == "api" or full_path.startswith("api/") or full_path in ("health", "login", "logout"):
            raise HTTPException(status_code=404)
        # Serve real files (favicon, logo, etc.) directly; everything else returns
        # index.html so the client-side router can handle the route. normpath +
        # containment check blocks path traversal out of dist/.
        candidate = os.path.normpath(os.path.join(_DIST, full_path))
        if full_path and candidate.startswith(_DIST + os.sep) and os.path.isfile(candidate):
            return FileResponse(candidate)
        index_html = os.path.join(_DIST, "index.html")
        if os.path.isfile(index_html):
            return FileResponse(index_html)
        raise HTTPException(status_code=404)
