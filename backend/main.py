import logging
import os

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

# yfinance logs "possibly delisted" / "no earnings dates found" at ERROR
# level for tickers Yahoo simply lacks data for (newly-listed names like
# AVEX, ETFs missing under their LSE symbol, etc). Our code handles missing
# data gracefully via empty/null checks; suppress the noise.
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

from database import engine, SessionLocal
from models import Base, Transaction, Portfolio, Benchmark, BenchmarkComponent, OptionsTrade, PolymarketPosition, DiscordWebhook, TradeNote, BrokerBalance, AppSetting
from routers import portfolio, market, analytics, broker, portfolios, watchlists, benchmarks, ibkr, options, polymarket, discord, notes, assistant, dividend_calendar
from fx import bulk_fetch_fx
import auth

Base.metadata.create_all(bind=engine)


def _ensure_fx_column() -> None:
    """SQLite ALTER TABLE for existing DBs that pre-date the fx_to_czk column."""
    insp = inspect(engine)
    cols = {c["name"] for c in insp.get_columns("transactions")}
    if "fx_to_czk" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE transactions ADD COLUMN fx_to_czk FLOAT"))


def _ensure_cash_columns():
    """Add Transaction.amount and relax ticker NOT NULL for cash rows (SQLite rebuild).

    Must run before _backfill_fx(): that helper does an ORM `db.query(Transaction)`,
    which selects every mapped column (now including `amount`) — same reasoning as
    why _ensure_fx_column() also runs ahead of it.
    """
    with engine.begin() as conn:
        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(transactions)"))}
        if "amount" not in cols:
            conn.execute(text("ALTER TABLE transactions ADD COLUMN amount FLOAT"))
        # Relax ticker NOT NULL if the existing table still enforces it.
        info = list(conn.execute(text("PRAGMA table_info(transactions)")))
        ticker_notnull = any(r[1] == "ticker" and r[3] == 1 for r in info)  # r[3] = notnull
        if ticker_notnull:
            conn.execute(text("ALTER TABLE transactions RENAME TO transactions_old"))
            # SQLite index names are global; RENAME leaves ix_* bound to the old
            # table, so free those names before the ORM recreates identically-named
            # indexes on the new table (otherwise: "index ... already exists").
            # Materialize the PRAGMA rows first: iterating that cursor lazily while
            # issuing DROP INDEX on the same connection triggers "database table is
            # locked" (an open read cursor blocks the write).
            idx_names = [row[1] for row in conn.execute(text("PRAGMA index_list(transactions_old)"))]
            for idx_name in idx_names:
                if not idx_name.startswith("sqlite_autoindex"):
                    conn.execute(text(f'DROP INDEX IF EXISTS "{idx_name}"'))
            Base.metadata.tables["transactions"].create(bind=conn)
            old_cols = [r[1] for r in conn.execute(text("PRAGMA table_info(transactions_old)"))]
            collist = ", ".join(old_cols)
            conn.execute(text(f"INSERT INTO transactions ({collist}) SELECT {collist} FROM transactions_old"))
            conn.execute(text("DROP TABLE transactions_old"))


def _ensure_cash_interest_rate_table():
    """create_all() builds it for fresh DBs; this is a no-op safety net for existing DBs."""
    with engine.begin() as conn:
        exists = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cash_interest_rates'"
        )).first()
        if not exists:
            Base.metadata.tables["cash_interest_rates"].create(bind=conn)


def _ensure_default_portfolio() -> int:
    """Return the id of the default portfolio, creating it if missing."""
    db = SessionLocal()
    try:
        default = db.query(Portfolio).filter(Portfolio.is_default.is_(True)).first()
        if default is None:
            default = db.query(Portfolio).filter(Portfolio.name == "Default").first()
        if default is None:
            default = Portfolio(name="Default", is_default=True)
            db.add(default)
            db.commit()
            db.refresh(default)
        elif not default.is_default:
            default.is_default = True
            db.commit()
        return default.id
    finally:
        db.close()


def _ensure_portfolio_columns(default_portfolio_id: int) -> None:
    """Add portfolio_id columns to legacy DBs and backfill them to the default portfolio.

    Also drops the legacy `broker_connections.broker UNIQUE` constraint that prevented
    more than one connection across all portfolios.
    """
    insp = inspect(engine)

    txn_cols = {c["name"] for c in insp.get_columns("transactions")}
    if "portfolio_id" not in txn_cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE transactions ADD COLUMN portfolio_id INTEGER"))
            conn.execute(
                text("UPDATE transactions SET portfolio_id = :pid WHERE portfolio_id IS NULL"),
                {"pid": default_portfolio_id},
            )
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_transactions_portfolio_id ON transactions(portfolio_id)"))
    else:
        # Defensive backfill in case rows snuck in with NULL.
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE transactions SET portfolio_id = :pid WHERE portfolio_id IS NULL"),
                {"pid": default_portfolio_id},
            )

    bc_cols = {c["name"] for c in insp.get_columns("broker_connections")}
    if "portfolio_id" not in bc_cols:
        # Legacy DBs had a UNIQUE constraint on `broker`; SQLite can't drop a column-
        # level constraint without rebuilding the table. Rebuild it.
        with engine.begin() as conn:
            conn.execute(text(
                """
                CREATE TABLE IF NOT EXISTS broker_connections_new (
                    id INTEGER PRIMARY KEY,
                    portfolio_id INTEGER NOT NULL,
                    broker VARCHAR NOT NULL,
                    api_key VARCHAR NOT NULL,
                    api_secret VARCHAR DEFAULT '',
                    environment VARCHAR DEFAULT 'live',
                    auto_sync BOOLEAN DEFAULT 0,
                    last_synced_at DATETIME,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (broker, portfolio_id),
                    FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE
                )
                """
            ))
            conn.execute(text(
                """
                INSERT INTO broker_connections_new
                    (id, portfolio_id, broker, api_key, api_secret, environment, auto_sync, last_synced_at, created_at)
                SELECT id, :pid, broker, api_key, COALESCE(api_secret, ''), COALESCE(environment, 'live'),
                       COALESCE(auto_sync, 0), last_synced_at, created_at
                FROM broker_connections
                """
            ), {"pid": default_portfolio_id})
            conn.execute(text("DROP TABLE broker_connections"))
            conn.execute(text("ALTER TABLE broker_connections_new RENAME TO broker_connections"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_broker_connections_portfolio_id ON broker_connections(portfolio_id)"))
    else:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE broker_connections SET portfolio_id = :pid WHERE portfolio_id IS NULL"),
                {"pid": default_portfolio_id},
            )


def _backfill_fx() -> None:
    db = SessionLocal()
    try:
        rows = db.query(Transaction).filter(Transaction.fx_to_czk.is_(None)).all()
        if not rows:
            return
        pairs = {(r.currency or "USD", r.date) for r in rows}
        resolved = bulk_fetch_fx(pairs)
        filled = 0
        for r in rows:
            v = resolved.get(((r.currency or "USD").upper(), r.date))
            if v is not None:
                r.fx_to_czk = v
                filled += 1
        db.commit()
        print(f"[fx-backfill] filled {filled}/{len(rows)} transactions")
    finally:
        db.close()


_PRESET_BENCHMARKS = [
    {"name": "S&P 500",     "kind": "ticker", "ticker": "^GSPC",     "components": None},
    {"name": "NASDAQ 100",  "kind": "ticker", "ticker": "^NDX",      "components": None},
    {"name": "Dow Jones",   "kind": "ticker", "ticker": "^DJI",      "components": None},
    {"name": "STOXX 50",    "kind": "ticker", "ticker": "^STOXX50E", "components": None},
    {"name": "MSCI World",  "kind": "ticker", "ticker": "URTH",      "components": None},
    {"name": "MSCI ACWI",   "kind": "ticker", "ticker": "ACWI",      "components": None},
    {"name": "60/40 (World + Agg Bond)", "kind": "basket", "ticker": None,
     "components": [("URTH", 0.6), ("AGG", 0.4)]},
]


def _seed_preset_benchmarks() -> None:
    """Insert system presets if absent. Matches on (portfolio_id IS NULL, name)
    so re-running is idempotent and renames upstream don't double-seed."""
    db = SessionLocal()
    try:
        existing = {
            b.name
            for b in db.query(Benchmark).filter(
                Benchmark.portfolio_id.is_(None),
                Benchmark.is_preset.is_(True),
            ).all()
        }
        added = 0
        for preset in _PRESET_BENCHMARKS:
            if preset["name"] in existing:
                continue
            b = Benchmark(
                portfolio_id=None,
                name=preset["name"],
                kind=preset["kind"],
                ticker=preset["ticker"],
                is_default=False,
                is_preset=True,
            )
            db.add(b)
            db.flush()
            for ticker, weight in (preset["components"] or []):
                db.add(BenchmarkComponent(benchmark_id=b.id, ticker=ticker, weight=weight))
            added += 1
        if added:
            db.commit()
            print(f"[benchmarks] seeded {added} preset benchmarks")
    finally:
        db.close()


def _ensure_options_trades_table() -> None:
    """Create the options_trades table if it doesn't exist (for existing DBs)."""
    insp = inspect(engine)
    if "options_trades" not in insp.get_table_names():
        OptionsTrade.__table__.create(bind=engine)


def _ensure_polymarket_table() -> None:
    """Create the polymarket_positions table if it doesn't exist."""
    insp = inspect(engine)
    if "polymarket_positions" not in insp.get_table_names():
        PolymarketPosition.__table__.create(bind=engine)


def _ensure_broker_balances_table() -> None:
    """Create the broker_balances table if it doesn't exist (for existing DBs)."""
    insp = inspect(engine)
    if "broker_balances" not in insp.get_table_names():
        BrokerBalance.__table__.create(bind=engine)


def _ensure_app_settings_table() -> None:
    """Create the app_settings table if it doesn't exist (for existing DBs)."""
    insp = inspect(engine)
    if "app_settings" not in insp.get_table_names():
        AppSetting.__table__.create(bind=engine)


# Per-user tables that carry an owner_id (see models.py). The app is single-user
# today (every row is "default"), but the column lets us add per-user isolation
# later without a schema rewrite.
_OWNER_ID_TABLES = [
    "portfolios", "broker_connections", "watchlists", "watchlist_items",
    "options_trades", "broker_balances", "polymarket_positions",
    "app_settings", "trade_notes", "discord_webhooks",
]


def _ensure_owner_id_columns() -> None:
    """Add owner_id to existing DBs that pre-date it, backfilling "default".

    Idempotent: tables that already have the column are skipped, and tables that
    create_all() just built already include it (+ index), so they're skipped too.
    Plain ALTER TABLE / CREATE INDEX so it works on SQLite now and Postgres later.
    """
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    for table in _OWNER_ID_TABLES:
        if table not in existing_tables:
            continue  # create_all() will have created it with owner_id already
        cols = {c["name"] for c in insp.get_columns(table)}
        if "owner_id" in cols:
            continue
        with engine.begin() as conn:
            conn.execute(text(
                f"ALTER TABLE {table} ADD COLUMN owner_id VARCHAR NOT NULL DEFAULT 'default'"
            ))
            # ADD COLUMN ... DEFAULT already backfills existing rows; normalize any
            # stray NULLs defensively (mirrors the portfolio_id backfill above).
            conn.execute(text(f"UPDATE {table} SET owner_id = 'default' WHERE owner_id IS NULL"))
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS ix_{table}_owner_id ON {table}(owner_id)"))


# owner_id must exist before the first ORM query below (the Portfolio lookup in
# _ensure_default_portfolio), so it runs ahead of the other startup migrations.
_ensure_owner_id_columns()
_ensure_fx_column()
_ensure_cash_columns()
_ensure_cash_interest_rate_table()
_default_pid = _ensure_default_portfolio()
_ensure_portfolio_columns(_default_pid)
_backfill_fx()
_seed_preset_benchmarks()
_ensure_options_trades_table()
_ensure_polymarket_table()
_ensure_broker_balances_table()
_ensure_app_settings_table()

# Add commission column to options_trades if missing
def _ensure_commission_column():
    insp = inspect(engine)
    if "options_trades" in insp.get_table_names():
        columns = [c["name"] for c in insp.get_columns("options_trades")]
        if "commission" not in columns:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE options_trades ADD COLUMN commission REAL DEFAULT 0.0"))

_ensure_commission_column()

app = FastAPI(title="Portfyl API", version="1.0.0")


# --- password gate ------------------------------------------------------------
# Paths reachable without a session: the login screen and its POST, logout, the
# Cloud Run health check, and the scheduler sync endpoint (which authenticates
# with its own SCHEDULER_TOKEN instead of the session cookie).
_PUBLIC_PATHS = {"/health", "/login", "/logout", "/api/broker/ibkr/scheduler-sync"}


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
# response (including the 401 above). Prod is same-origin so CORS is mostly moot,
# but it stays configurable (Section 4 wires FRONTEND_ORIGIN).
_cors_origins = ["http://localhost:5173", "http://localhost:3000"]
_frontend_origin = os.getenv("FRONTEND_ORIGIN")
if _frontend_origin:
    # Optional extra allowed origin (prod is same-origin, so usually unset).
    _cors_origins.append(_frontend_origin.strip())

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
app.include_router(dividend_calendar.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}


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
