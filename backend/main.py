import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from logging_setup import configure_logging, correlation_id_var

configure_logging()

# yfinance logs "possibly delisted" / "no earnings dates found" at ERROR
# level for tickers Yahoo simply lacks data for (newly-listed names like
# AVEX, ETFs missing under their LSE symbol, etc). Our code handles missing
# data gracefully via empty/null checks; suppress the noise.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

from database import SessionLocal, assert_alembic_head, get_db
from edition import Edition, edition_from_env
from entitlements import EntitlementDenied, entitlement_denied_handler
from error_monitoring import configure_sentry
from cloud_gate import CloudApiGateMiddleware
from security_headers import SecurityHeadersMiddleware
from rate_limit import (
    InvalidClientIp,
    RateLimitExceeded,
    RateLimitUnavailable,
    invalid_client_ip_handler,
    rate_limit_exceeded_handler,
    rate_limit_unavailable_handler,
)
from routers import portfolio, market, analytics, broker, portfolios, watchlists, benchmarks, ibkr, options, polymarket, discord, notes, assistant, cash, alerts, settings, allocation_targets, capabilities, auth as auth_router
from tenancy import (
    RequestContextError,
    get_request_context,
    request_context_error_handler,
)

PORTFYL_EDITION = edition_from_env(os.environ)
configure_sentry(environment=PORTFYL_EDITION.value)
app = FastAPI(title="Portfyl API", version="1.0.0")
app.state.portfyl_edition = PORTFYL_EDITION
app.add_exception_handler(
    auth_router.AuthAPIError,
    auth_router.auth_api_error_handler,
)
app.add_exception_handler(
    RequestContextError,
    request_context_error_handler,
)
app.add_exception_handler(EntitlementDenied, entitlement_denied_handler)
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_exception_handler(RateLimitUnavailable, rate_limit_unavailable_handler)
app.add_exception_handler(InvalidClientIp, invalid_client_ip_handler)


# The desktop SPA is same-origin (baked into the image), but the native app calls
# cross-origin from Capacitor's local origins, so those are allowed here;
# FRONTEND_ORIGIN adds any extras.
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

if PORTFYL_EDITION is Edition.CLOUD:
    # Registered before CORSMiddleware's own add_middleware() call so it
    # ends up more inner than CORS in Starlette's wrap order (later-added
    # middleware wraps outermost) -- CORS then still decorates this gate's
    # own direct 400/403/429/503 responses instead of skipping them.
    app.add_middleware(CloudApiGateMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Added after CORS so it wraps outermost and compresses the final response
# body (JSON payloads like a full-history performance series run well past
# minimum_size uncompressed; small responses are left alone).
app.add_middleware(GZipMiddleware, minimum_size=500)

# Added after GZip so it wraps the rendered SPA HTML at the very outermost
# layer and sees the final Content-Type; it only stamps headers onto
# text/html responses, so it never touches JSON API responses or static
# assets served from /assets.
app.add_middleware(SecurityHeadersMiddleware)


@app.middleware("http")
async def _stamp_correlation_id(request: Request, call_next):
    """Every log line emitted while handling this request carries the same
    id (logging_setup.RedactingFormatter's %(correlation_id)s), so a single
    request's log lines can be grepped together without exposing anything
    about the request itself."""
    token = correlation_id_var.set(uuid.uuid4().hex[:12])
    try:
        return await call_next(request)
    finally:
        correlation_id_var.reset(token)


app.include_router(auth_router.router, prefix="/api")
app.include_router(capabilities.build_router(PORTFYL_EDITION), prefix="/api")
if PORTFYL_EDITION is Edition.CLOUD:
    from routers import test_plans

    app.include_router(test_plans.router, prefix="/api")
app.include_router(portfolios.router, prefix="/api")
app.include_router(portfolio.router, prefix="/api")
app.include_router(
    market.router,
    prefix="/api",
    dependencies=[Depends(get_request_context)],
)
app.include_router(analytics.router, prefix="/api")
if PORTFYL_EDITION is Edition.LOCAL:
    # Imported only in the local edition so cloud never registers the owner-only
    # Tax Report or Screener operations (and they stay absent from OpenAPI).
    from routers import local_features

    app.include_router(
        local_features.router,
        prefix="/api",
        dependencies=[Depends(get_request_context)],
    )
app.include_router(broker.router, prefix="/api")
app.include_router(
    watchlists.router,
    prefix="/api",
    dependencies=[Depends(get_request_context)],
)
app.include_router(benchmarks.router, prefix="/api")
app.include_router(ibkr.router, prefix="/api")
app.include_router(
    options.router,
    prefix="/api",
    dependencies=[Depends(get_request_context)],
)
app.include_router(polymarket.router, prefix="/api")
app.include_router(discord.router, prefix="/api")
app.include_router(notes.router, prefix="/api")
app.include_router(
    assistant.router,
    prefix="/api",
    dependencies=[Depends(get_request_context)],
)
app.include_router(cash.router, prefix="/api")
app.include_router(allocation_targets.router, prefix="/api")
app.include_router(alerts.router, prefix="/api")
app.include_router(
    settings.router,
    prefix="/api",
    dependencies=[Depends(get_request_context)],
)
if PORTFYL_EDITION is Edition.CLOUD:
    # Cloud Scheduler-triggered job endpoints, replacing the in-process
    # pollers _start_background_pollers only registers in the local
    # edition. Not under /api -- own OIDC auth, no cookie/CSRF session.
    from routers import internal_jobs

    app.include_router(internal_jobs.router)


_JOB_MAX_AGES = {
    "alerts": timedelta(minutes=30),
    "autosync": timedelta(hours=2),
    "dividends": timedelta(hours=25),
    "broker_backfill": timedelta(minutes=30),
}
if PORTFYL_EDITION is Edition.CLOUD:
    # Cleanup jobs only ever run in cloud (internal_jobs.router is cloud-only);
    # local must never expect heartbeats for jobs it never schedules, or
    # /health would report permanently degraded there.
    # Cloud Scheduler runs alerts every 2 hours (deploy/operations.json), so the
    # local 15-minute poller's limit would report permanent degradation here.
    _JOB_MAX_AGES["alerts"] = timedelta(hours=4)
    _JOB_MAX_AGES["rate_limit_cleanup"] = timedelta(hours=2)
    _JOB_MAX_AGES["account_deletion_cleanup"] = timedelta(hours=26)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@app.get("/health")
def health(db=Depends(get_db)):
    """Cheap, dependency-aware service health without upstream network I/O."""
    from sqlalchemy import select, text
    from models import JobRun

    checks: dict[str, dict] = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:
        checks["database"] = {
            "status": "error",
            "error_type": type(exc).__name__,
        }
        checks["scheduler"] = {"status": "unavailable"}
        return {"status": "degraded", "checks": checks}

    now = datetime.now(timezone.utc)
    rows = {
        row.job_name: row
        for row in db.scalars(select(JobRun).where(JobRun.job_name.in_(_JOB_MAX_AGES))).all()
    }
    jobs = {}
    scheduler_ok = True
    for name, max_age in _JOB_MAX_AGES.items():
        row = rows.get(name)
        if row is None:
            jobs[name] = {"status": "missing", "last_success_at": None}
            scheduler_ok = False
            continue
        last_success = _as_utc(row.last_success_at)
        fresh = now - last_success <= max_age
        jobs[name] = {
            "status": "ok" if fresh else "stale",
            "last_success_at": last_success.isoformat(),
        }
        scheduler_ok = scheduler_ok and fresh
    checks["scheduler"] = {
        "status": "ok" if scheduler_ok else "degraded",
        "jobs": jobs,
    }
    return {
        "status": "ok" if scheduler_ok else "degraded",
        "checks": checks,
    }


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
#   * broker backfill — BROKER_BACKFILL_INTERVAL_SECONDS heartbeat (default
#                     10 s); drains BrokerSyncRun rows created by a
#                     T212 connect/sync (see t212_sync.claim_or_create_run),
#                     independent of auto_sync/schedule. Opt-out
#                     BROKER_BACKFILL_ENABLED=0.
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
            token = correlation_id_var.set(f"job-{name}-{uuid.uuid4().hex[:8]}")
            db = SessionLocal()
            try:
                happened = await pass_fn(db)
                from jobs import mark_job_succeeded

                mark_job_succeeded(db, name)
                db.commit()
                if happened:
                    logger.info("%s pass: %d event(s)", name, len(happened))
            finally:
                correlation_id_var.reset(token)
                db.close()
        except _asyncio.CancelledError:
            break
        except Exception:
            logger.exception("%s pass failed", name)


@app.on_event("startup")
async def _start_background_pollers():
    schema_db = SessionLocal()
    try:
        assert_alembic_head(schema_db)
    finally:
        schema_db.close()

    if PORTFYL_EDITION is not Edition.LOCAL:
        # Cloud is multi-instance: an in-process asyncio timer would either
        # fire on every instance (duplicate syncs/alerts/notifications) or
        # need its own leader-election scheme. internal_jobs.router (mounted
        # below, cloud-only) replaces this with Cloud Scheduler-driven,
        # advisory-lock-guarded endpoints instead. The local edition is
        # always single-instance, so the simpler in-process timer stays.
        return

    import asyncio as _asyncio
    from jobs import (
        alert_check_all_workspaces,
        autosync_all_workspaces,
        broker_backfill_all_workspaces,
        dividend_notify_all_workspaces,
    )

    def _env_int(key: str, default: int) -> int:
        try:
            return int(os.environ.get(key, default))
        except ValueError:
            return default

    if os.environ.get("ALERT_POLLER_ENABLED", "1") == "1":
        interval = _env_int("ALERT_CHECK_INTERVAL_SECONDS", 900)
        _BG_TASKS.append(_asyncio.create_task(
            _periodic_loop("alerts", alert_check_all_workspaces, interval, initial_delay=interval)))

    if os.environ.get("BROKER_AUTOSYNC_ENABLED", "1") == "1":
        # 60 s heartbeat: each tick asks jobs.autosync_all_workspaces whether
        # each workspace's configured schedule is due; the sync itself runs
        # only then. Short initial delay so a restart quickly catches up on a
        # missed boundary (the persisted last-run makes early ticks safe).
        _BG_TASKS.append(_asyncio.create_task(
            _periodic_loop("autosync", autosync_all_workspaces, interval=60, initial_delay=300)))

    if os.environ.get("BROKER_BACKFILL_ENABLED", "1") == "1":
        # Independent of auto_sync and the sync schedule (plan §5.4) -- this
        # only drains BrokerSyncRun rows sync_transactions already created; it
        # never starts one itself. Short initial delay so a run started just
        # before a restart resumes promptly. The tick is short so a user who
        # just pressed Sync does not wait up to a minute for the first history
        # step; each tick costs a workspace enumeration, one due-runs query per
        # workspace and one job_runs update, and the interval is tunable via
        # BROKER_BACKFILL_INTERVAL_SECONDS.
        _BG_TASKS.append(_asyncio.create_task(
            _periodic_loop(
                "broker_backfill", broker_backfill_all_workspaces,
                interval=max(1, _env_int("BROKER_BACKFILL_INTERVAL_SECONDS", 10)),
                initial_delay=5,
            )))

    if os.environ.get("DIVIDEND_NOTIFY_ENABLED", "1") == "1":
        interval = _env_int("DIVIDEND_NOTIFY_INTERVAL_SECONDS", 43200)
        lead = _env_int("DIVIDEND_NOTIFY_LEAD_DAYS", 3)

        async def _dividend_pass(db, _lead=lead):
            return await dividend_notify_all_workspaces(db, lead_days=_lead)

        # Short initial delay (not a full interval): a restart shouldn't be able
        # to skip today's ex-date check — the dedup table makes early runs safe.
        _BG_TASKS.append(_asyncio.create_task(
            _periodic_loop("dividends", _dividend_pass, interval, initial_delay=300)))


@app.on_event("shutdown")
async def _stop_background_pollers():
    while _BG_TASKS:
        _BG_TASKS.pop().cancel()


# --- serve the built React SPA (production / same-origin) ---------------------
# In dev the Vite server on :5173 proxies `/api`; dist/ may therefore be absent.
# Public auth pages and protected app pages are both frontend routes, so every
# non-API path reaches the SPA shell and React decides what to render.
_DIST = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist"))
_ASSETS = os.path.join(_DIST, "assets")

if os.path.isdir(_ASSETS):
    app.mount("/assets", StaticFiles(directory=_ASSETS), name="assets")

if os.path.isdir(_DIST):
    @app.get("/{full_path:path}", include_in_schema=False)
    def spa_fallback(full_path: str):
        # Never shadow the API / auth / health routes (they match first anyway).
        if full_path == "api" or full_path.startswith("api/") or full_path == "health":
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
