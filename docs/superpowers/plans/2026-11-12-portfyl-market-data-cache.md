# Market-Data Store v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PostgreSQL a durable second cache level under `market_data` in the **local edition**, in front of yfinance, so the dashboard and stock detail are served from the database after a restart and refreshed behind a short deadline — with every number identical to today's.

**Architecture:** Three global tables (`market_instrument`, `market_snapshot`, `market_price_daily`) written only through a new package `backend/market_store/` using a narrow database role. `market_data.get_infos` gains an L2 step (memory → PostgreSQL → provider), history readers move to a small typed API (`market_store.history`). No scheduled jobs, no budget, no Twelve Data — those are later plans.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (sync), Alembic, PostgreSQL 16 (SQLite only in the fast suite), pandas, yfinance (through the existing `market_data` wrappers), React 18 + @tanstack/react-query, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-08-portfyl-market-data-cache-design.md` (revised 2026-11-12; `[REV-n]` marks). Evidence: `docs/superpowers/specs/2026-11-08-portfyl-market-data-cache-review.md` (findings `F-nn`). Read `CLAUDE.md` first.

## Global Constraints

- Flag: `PORTFYL_MARKET_STORE=on|off`, default off. **Off = today's code path; every existing test passes unmodified with the flag off.** On is refused at startup when `PORTFYL_EDITION=cloud`.
- Never run database work on the event loop: every function here is a plain `def`. No `async def` touches a `Session`.
- No public `market_store` function takes a `Session`; each opens and closes its own short session. **No session is open while the provider is called.**
- Market tables are written only by `market_store` (`info_store`, `history_store`, `purge`). No router, importer or job writes them.
- Only `backend/alembic/versions/0026_market_data_store.py` changes the schema; additive only. `EXPECTED_ALEMBIC_HEAD` becomes `"0026_market_data_store"` in the same task. Nobody runs `alembic upgrade` against a shared database.
- Do not touch `requirements*.txt`, `requirements*.lock`, `package.json`, `package-lock.json`.
- Time is UTC everywhere in `market_store` (`datetime.now(timezone.utc)`).
- Exact values: info TTL 300 s; empty back-off 60 s doubling, cap 900 s; stale deadline 1.5 s (`PORTFYL_MARKET_STALE_DEADLINE`), full deadline `market_data.INFO_TIMEOUT` (8 s); history tail TTL 300 s, tail period `"1mo"`; overlap tolerance 1e-4 relative; price sanity ×[0.5, 2.0], FX ×[0.8, 1.25], confirmation within 2 %; symbol pattern `^[A-Z0-9^][A-Z0-9.\-=^]{0,19}$`; instrument cap 20,000; default history depth 370 days.
- Units are never converted inside the store.
- Call collaborators through their module — `config.stale_deadline()`, `yahoo.fetch_daily(...)`, `market_data.get_infos(...)`, `info_store.save(...)` — never through a `from x import name` binding: the tests replace them by monkeypatching module attributes.
- yfinance logging stays suppressed. No new user-visible string, no colour, no CSS (so `DESIGN.md` and the i18n dictionaries are untouched).
- Commit style: conventional commits, ending with the attribution line the session's instructions give.

## Review Focus

1. **Provider answers empty or absurd for a held ticker** → the last good value stays, flagged with its real time; the position is never valued at 0 because of one bad answer. Tests: Task 3 (`test_empty_answer_keeps_last_good`, `test_absurd_price_is_parked_then_confirmed`).
2. **A split or dividend lands between two refreshes** → the series is replaced whole, never mixed. Tests: Task 4 (`test_split_in_tail_replaces_whole_series`, `test_dividend_rescale_replaces_series`).
3. **The app is stopped mid-session and restarted days later, offline** → no intraday value is ever a stored close. Tests: Task 1 (`test_daily_row_for_today_is_rejected`), Task 4 (`test_full_fetch_stores_only_completed_sessions`).
4. **The flag is on but the database user cannot write, or the edition is cloud** → startup fails with one clear sentence, not on the first write. Tests: Task 2 (`test_enabled_is_refused_in_cloud`), Task 12 (`test_preflight_names_the_writer_url`).
5. **Odd ticker strings** (lower-case, spaces, 40 characters, `;`, non-ASCII) → rejected, no row, no provider call; pence/agorot/cent quotes still valued in the major unit. Tests: Task 2 (`test_canonical_rejects`), Task 7 (`test_invalid_ticker_returns_empty_without_row`), Task 10 (`test_minor_unit_to_major`).

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `backend/alembic/versions/0026_market_data_store.py` | tables, role, grants, finality CHECK | 1 |
| `backend/models.py` (append) | `MarketInstrument`, `MarketSnapshot`, `MarketPriceDaily` | 1 |
| `backend/market_store/config.py` | flag and constants | 2 |
| `backend/market_store/db.py` | reader/writer sessions, `bind`, `preflight` | 2 |
| `backend/market_store/symbols.py` | validation | 2 |
| `backend/market_store/instruments.py` | get-or-create, row lock, cap | 2 |
| `backend/market_store/staleness.py`, `metrics.py` | per-call stale flag; counters | 2 |
| `backend/market_store/info_store.py` | `info` snapshot: load, save, sanity rules | 3 |
| `backend/market_store/yahoo.py` | one provider call → normalised daily frames | 4 |
| `backend/market_store/history_store.py` | daily rows: read, verify, append, replace | 4 |
| `backend/market_store/history.py` | read API: `closes`, `panel`, `refresh` | 4 |
| `frontend/src/hooks/usePriceRefreshRetry.js` | one delayed refetch | 5 |
| `backend/market_data.py` | L2 step in `get_infos` | 7 |
| `backend/fx.py`, `routers/analytics.py`, `routers/portfolio.py`, `routers/market.py` | history call sites | 8–11 |
| `backend/market_store/purge.py` | empty the three tables | 13 |

## Waves, parallelism, isolation

| Wave | Tasks | May run in parallel | Hotspots and their single owner |
|---|---|---|---|
| 0 | 1 → 2 | **no**, strictly in order | T1: `models.py`, `database.py`, `alembic/versions/`, `tests/test_plan_schema.py`, `tests/postgres/conftest.py`, `docs/security/tenant-isolation-matrix.md`. T2: `tests/conftest.py`, `currency_codes.py` |
| 1 | 3, 4, 5, then 6 | 3 ∥ 4 ∥ 5; 6 after all three | none shared (`market_store/__init__.py` is frozen after T2) |
| 2 | 7, 8, 9, 10, 11, then 12 | 7 ∥ 8 ∥ 9 ∥ 10 ∥ 11; 12 after all five | T7: `market_data.py`, `main.py`, `tests/conftest.py`, `routers/alerts.py`, `tests/test_alerts.py` |
| 3 | 13 → 14 | no | T13: `CLAUDE.md`, `docs/compliance/data-processing-inventory.md`, `deploy/cloudrun.md` |

Rules for every task:

- **Integration branch** `feat/market-store`, created from `main` by Task 1. Never commit to `main`; never push or merge to `main` — the founder does that.
- **Task branch** `feat/market-store-tNN-<slug>` from the tip of `feat/market-store`, in its own worktree `.claude/worktrees/ms-tNN`. Only the wave's gate task (6, 12) and Tasks 1, 2, 13, 14 merge into `feat/market-store`.
- **Backend environment** per worktree: `cd backend; uv venv .venv --python 3.12; uv pip install --require-hashes -r requirements-dev.lock`.
- **PostgreSQL** per task that needs it (the compose file's port is fixed, so use a private container): `docker run -d --name portfyl-test-ms-tNN -e POSTGRES_USER=portfyl_test -e POSTGRES_PASSWORD=portfyl_test -e POSTGRES_DB=portfyl_test -p 554NN:5432 postgres:16`, then `$env:TEST_DATABASE_URL = "postgresql+psycopg://portfyl_test:portfyl_test@localhost:554NN/portfyl_test"`; remove with `docker rm -f portfyl-test-ms-tNN` when done. `NN` = 50 + task number (Task 1 → 55451, Task 12 → 55462, Task 14 → 55464).
- **Dev servers** (:8000, :5173) are started by Task 14 only, when no other session uses them.
- Commands: fast suite `cd backend; python -m pytest tests/ --ignore=tests/postgres -q`; PostgreSQL suite `cd backend; python -m pytest tests/postgres/ -q`; frontend `cd frontend; npm test; npm run test:cloud; npm run build; npm run build:cloud`.
- **Model:** tasks marked **[stronger model]** decide isolation or money correctness; run them on the most capable model. The rest are sized for Sonnet.

---

## Wave 0 — foundation (serial)

### Task 1: Schema, role, grants **[stronger model — tenant isolation and database privileges]**

**Files:**
- Create: `backend/alembic/versions/0026_market_data_store.py`
- Modify: `backend/models.py` (append three classes at the end), `backend/database.py:82`, `backend/tests/test_plan_schema.py:27-28`, `backend/tests/postgres/conftest.py` (two fixtures), `docs/security/tenant-isolation-matrix.md` (new section after "Non-tenant infrastructure tables")
- Test: `backend/tests/postgres/test_market_store_schema.py`
- Must not touch: any router, `market_data.py`, `main.py`, `requirements*`

**Interfaces:**
- Produces (models, in `models.py`):
  - `MarketInstrument` → table `market_instrument`: `id` (`BigInteger().with_variant(Integer, "sqlite")`, PK, autoincrement), `symbol` `String(40)` unique not null, `kind` `String(16)` default `"unknown"`, `history_start` `Date` null, `history_checked_at` tz null, `history_attempts` `Integer` default 0, `history_next_attempt_at` tz null, `created_at` tz default now. Check `ck_market_instrument_kind`: `kind IN ('equity','etf','fund','index','fx','crypto','unknown')`.
  - `MarketSnapshot` → `market_snapshot`: PK (`instrument_id` FK → `market_instrument.id` `ON DELETE CASCADE`, `kind` `String(32)`), `payload` `JSON` not null, `schema_ver` `Integer` default 1, `source` `String(32)` not null, `status` `String(16)` not null, `fetched_at` tz not null, `checked_at` tz not null, `attempts` `Integer` default 0, `next_attempt_at` tz null, `pending_payload` `JSON` null. Checks `ck_market_snapshot_kind` (`kind IN ('info')`), `ck_market_snapshot_status` (`status IN ('ok','empty')`).
  - `MarketPriceDaily` → `market_price_daily`: PK (`instrument_id` FK cascade, `trade_date` `Date`), `close` `Float` not null, `adj_close` `Float` not null, `split_ratio` `Float` null, `dividend` `Float` null, `source` `String(32)` not null, `fetched_at` tz not null. Check `ck_market_price_daily_positive`: `close > 0 AND adj_close > 0`.
- Produces (PostgreSQL only, in the migration, **not** in the model because SQLite cannot parse it): `ck_market_price_daily_final`: `trade_date < (fetched_at AT TIME ZONE 'UTC')::date`; `payload`/`pending_payload` as `postgresql.JSONB`.
- Produces (role): `portfyl_market_writer`.
- Produces (fixtures in `tests/postgres/conftest.py`): `market_writer_session` (like `runtime_session`, with `SET LOCAL ROLE portfyl_market_writer`) and `role_engine` — a factory `role_engine(role: str) -> Engine` returning an engine on `postgres_url` whose every connection runs `SET ROLE <role>` (SQLAlchemy `connect` event), disposed at teardown.

- [ ] **Step 1: Create the branches.** `git switch -c feat/market-store main`, then the task branch and worktree as described above.

- [ ] **Step 2: Write the failing tests** in `backend/tests/postgres/test_market_store_schema.py`:

```python
MARKET_TABLES = ("market_instrument", "market_snapshot", "market_price_daily")

def _grants(session, role, table):
    return session.execute(text(
        "SELECT privilege_type FROM information_schema.role_table_grants "
        "WHERE grantee = :r AND table_schema = 'public' AND table_name = :t ORDER BY privilege_type"
    ), {"r": role, "t": table}).scalars().all()

def test_market_tables_have_no_tenant_columns(postgres_session):
    rows = postgres_session.execute(text(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name LIKE 'market\\_%' "
        "AND column_name IN ('workspace_id', 'user_id', 'portfolio_id')")).all()
    assert rows == []

def test_market_tables_reference_only_market_tables(postgres_session):
    targets = postgres_session.execute(text(
        "SELECT DISTINCT ccu.table_name FROM information_schema.table_constraints tc "
        "JOIN information_schema.constraint_column_usage ccu USING (constraint_schema, constraint_name) "
        "WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name LIKE 'market\\_%'")).scalars().all()
    assert targets == ["market_instrument"]

@pytest.mark.parametrize("table", MARKET_TABLES)
def test_runtime_role_has_select_only(postgres_session, table):
    assert _grants(postgres_session, "portfyl_runtime", table) == ["SELECT"]

def test_market_writer_has_exact_grants(postgres_session):
    assert _grants(postgres_session, "portfyl_market_writer", "market_instrument") == ["INSERT", "SELECT", "UPDATE"]
    assert _grants(postgres_session, "portfyl_market_writer", "market_snapshot") == ["INSERT", "SELECT", "UPDATE"]
    assert _grants(postgres_session, "portfyl_market_writer", "market_price_daily") == ["DELETE", "INSERT", "SELECT", "UPDATE"]

def test_market_writer_role_is_hardened(postgres_session):
    row = postgres_session.execute(text(
        "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb FROM pg_roles "
        "WHERE rolname = 'portfyl_market_writer'")).one()
    assert tuple(row) == (False, False, False, False)

@pytest.mark.parametrize("table", ("transactions", "users", "workspaces"))
def test_market_writer_cannot_read_tenant_tables(market_writer_session, table):
    with pytest.raises(ProgrammingError):          # insufficient_privilege
        market_writer_session.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))

def test_runtime_role_cannot_write_market_tables(runtime_session):
    with pytest.raises(ProgrammingError):
        runtime_session.execute(text("INSERT INTO market_instrument (symbol) VALUES ('AAPL')"))

def test_daily_row_for_today_is_rejected(postgres_session):
    iid = postgres_session.execute(text(
        "INSERT INTO market_instrument (symbol) VALUES ('AAPL') RETURNING id")).scalar_one()
    ins = text("INSERT INTO market_price_daily (instrument_id, trade_date, close, adj_close, source, fetched_at) "
               "VALUES (:i, (now() AT TIME ZONE 'UTC')::date - :back, 1, 1, 'test', now())")
    postgres_session.execute(ins, {"i": iid, "back": 1})          # yesterday: accepted
    with pytest.raises(IntegrityError):
        postgres_session.execute(ins, {"i": iid, "back": 0})      # today: rejected
```

- [ ] **Step 3: Run them and see them fail.** `python -m pytest tests/postgres/test_market_store_schema.py -q` → errors: relation `market_instrument` does not exist / fixture `market_writer_session` not found.

- [ ] **Step 4: Add the models** to `models.py` exactly as listed under Interfaces, each with a docstring saying "Global reference data, outside RLS; see docs/security/tenant-isolation-matrix.md".

- [ ] **Step 5: Write the migration.** `revision = "0026_market_data_store"`, `down_revision = "0025_stripe_billing"`. Follow `0025_stripe_billing.py` for style (`op.create_table`, raw `op.execute` for grants). Order in `upgrade()`: (1) `DO $$ … $$` block that runs `CREATE ROLE portfyl_market_writer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS` only if `pg_roles` has no such row (same shape as the `portfyl_runtime` block in `0002_tenant_rls.py:104-160`, without the re-hardening branch); (2) the three tables; (3) `ck_market_price_daily_final`; (4) `GRANT USAGE ON SCHEMA public TO portfyl_market_writer`, the table grants from the tests, `GRANT USAGE, SELECT ON SEQUENCE market_instrument_id_seq TO portfyl_market_writer`, `GRANT SELECT ON TABLE … TO portfyl_runtime` for the three tables. `downgrade()`: revoke those grants, drop `market_price_daily`, `market_snapshot`, `market_instrument`; leave the role (it is cluster-wide). Docstring: "Additive only … global reference data outside RLS, like job_runs".

- [ ] **Step 6: Bump the head** — `database.py:82` → `EXPECTED_ALEMBIC_HEAD = "0026_market_data_store"`; `tests/test_plan_schema.py:28` → the same string; in the same test add `assert {"market_instrument", "market_snapshot", "market_price_daily"} <= set(Base.metadata.tables)`.

- [ ] **Step 7: Add the two fixtures** to `tests/postgres/conftest.py` (Interfaces).

- [ ] **Step 8: Document.** In `docs/security/tenant-isolation-matrix.md` add `## Global reference data (market store)`: one paragraph (public market data, no tenant column, no FK to tenant tables, web runtime read-only, writes by `portfyl_market_writer` only) and a table `Table | Runtime grants | Writer grants | Test` with the three tables and the test names above.

- [ ] **Step 9: Verify.** `python -m pytest tests/postgres/test_market_store_schema.py -q` → all pass. `python -m pytest tests/postgres/ -q` → no new failures. `python -m pytest tests/ --ignore=tests/postgres -q` → pass. `alembic heads` → `0026_market_data_store (head)` only.

- [ ] **Step 10: Commit and merge into `feat/market-store`.** `feat(market-store): add market tables, writer role and grants (0026)`

**Acceptance:** one Alembic head equal to `EXPECTED_ALEMBIC_HEAD`; upgrade and downgrade both run on the disposable database; all tests above green. **Rollback:** `alembic downgrade 0025_stripe_billing` on a database that got it, revert the commit.

### Task 2: Package skeleton

**Files:**
- Create: `backend/market_store/__init__.py`, `config.py`, `db.py`, `symbols.py`, `instruments.py`, `staleness.py`, `metrics.py`
- Modify: `backend/currency_codes.py:11`, `backend/tests/conftest.py` (one fixture)
- Test: `backend/tests/test_market_store_core.py`, `backend/tests/test_currency_subunits.py`
- Must not touch: `market_data.py`, `main.py`, `models.py`, routers

**Interfaces:**
- Consumes: Task 1 models.
- Produces:
  - `market_store/__init__.py`: empty except a docstring (frozen after this task; later tasks import submodules explicitly).
  - `config.enabled(env: Mapping[str, str] = os.environ) -> bool` — `True` only for `PORTFYL_MARKET_STORE == "on"`; unset, empty or `"off"` → `False`; any other value → `RuntimeError`; `"on"` with `edition_from_env(env) is Edition.CLOUD` → `RuntimeError("PORTFYL_MARKET_STORE=on is local-edition only in v1")`.
  - `config.stale_deadline(env=os.environ) -> float` (default `1.5`), constants `INFO_TTL = 300.0`, `EMPTY_BACKOFF_BASE = 60.0`, `EMPTY_BACKOFF_CAP = 900.0`, `HISTORY_TAIL_TTL = 300.0`, `HISTORY_TAIL_PERIOD = "1mo"`, `HISTORY_DEFAULT_DAYS = 370`, `OVERLAP_TOLERANCE = 1e-4`, `MAX_INSTRUMENTS = 20_000`.
  - `db.reader_session() -> ContextManager[Session]`, `db.writer_session() -> ContextManager[Session]` (commit on success, rollback and re-raise on error, always close), `db.bind(engine: Engine | None, writer_engine: Engine | None = None) -> None` (test hook: both factories use `engine`, the writer uses `writer_engine` when given; `None` restores the defaults), `db.preflight() -> None`. Defaults: reader = `database.SessionLocal`; writer = an engine built with `database.build_engine` from `MARKET_WRITER_DATABASE_URL` when set (settings built the way `routers/internal_jobs._job_database_settings` does it), else `database.SessionLocal`. `preflight()` on PostgreSQL runs `SELECT has_table_privilege(current_user, 'market_snapshot', 'INSERT')` through the writer and raises `RuntimeError("market store: the database user cannot write market tables; set MARKET_WRITER_DATABASE_URL to a portfyl_market_writer connection or connect as the owner")` when false; on other dialects it returns.
  - `symbols.canonical(symbol: str) -> str` (strip, upper, validate), `symbols.InvalidSymbol(ValueError)`, `symbols.is_fx(symbol: str) -> bool` (`endswith("=X")`).
  - `instruments.get_ids(session, symbols: Iterable[str]) -> dict[str, int]`, `instruments.get_or_create(session, symbol: str) -> MarketInstrument` (sets `kind="fx"` for FX symbols, `"index"` for a leading `^`; raises `instruments.UniverseFull` when the row count is at `config.MAX_INSTRUMENTS`; on a unique-violation race, roll back to a savepoint and re-select), `instruments.lock(session, instrument_id: int) -> MarketInstrument` (`with_for_update()`).
  - `staleness.mark_stale_served() -> None`, `staleness.consume_stale_served() -> bool` (a `ContextVar[bool]`; consume returns the value and resets it to `False`).
  - `metrics.incr(name: str, n: int = 1) -> None`, `metrics.snapshot_and_reset() -> dict[str, int]`, `metrics.maybe_log(now: float | None = None) -> None` (logs the non-zero counters on logger `portfyl.market_store` at most once per 60 s). Counter names: `l2_hit`, `provider_fetch`, `stale_served`, `sanity_rejected`, `history_appended`, `history_replaced`.
  - `currency_codes.SUBUNITS = {"GBX": ("GBP", 100.0), "ILA": ("ILS", 100.0), "ZAC": ("ZAR", 100.0)}`.
  - Fixture `market_store_db` in `tests/conftest.py`: builds a private `sqlite:///:memory:` engine (`StaticPool`, `check_same_thread=False`), `Base.metadata.create_all`, `monkeypatch.setenv("PORTFYL_MARKET_STORE", "on")`, `market_store.db.bind(engine)`, yields the engine, then `bind(None)` and `metrics.snapshot_and_reset()`.

- [ ] **Step 1: Write the failing tests.**

```python
# tests/test_market_store_core.py
def test_enabled_defaults_to_off():
    assert config.enabled({"PORTFYL_EDITION": "local"}) is False
def test_enabled_on_in_local():
    assert config.enabled({"PORTFYL_EDITION": "local", "PORTFYL_MARKET_STORE": "on"}) is True
def test_enabled_is_refused_in_cloud():
    with pytest.raises(RuntimeError, match="local-edition only"):
        config.enabled({"PORTFYL_EDITION": "cloud", "PORTFYL_MARKET_STORE": "on"})
def test_enabled_rejects_other_values():
    with pytest.raises(RuntimeError):
        config.enabled({"PORTFYL_EDITION": "local", "PORTFYL_MARKET_STORE": "yes"})

@pytest.mark.parametrize("raw,expected", [(" aapl ", "AAPL"), ("usdczk=x", "USDCZK=X"),
    ("^gspc", "^GSPC"), ("brk-b", "BRK-B"), ("cez.pr", "CEZ.PR")])
def test_canonical_accepts(raw, expected):
    assert symbols.canonical(raw) == expected
@pytest.mark.parametrize("raw", ["", " ", "A" * 21, "AAPL;DROP", "AA PL", "../x", "ČEZ", ".AAPL", None])
def test_canonical_rejects(raw):
    with pytest.raises(symbols.InvalidSymbol):
        symbols.canonical(raw)

def test_get_or_create_is_idempotent(market_store_db):
    with db.writer_session() as s:
        a = instruments.get_or_create(s, "AAPL").id
    with db.writer_session() as s:
        assert instruments.get_or_create(s, "AAPL").id == a
        assert instruments.get_or_create(s, "USDCZK=X").kind == "fx"
def test_universe_cap_fails_closed(market_store_db, monkeypatch):
    monkeypatch.setattr(config, "MAX_INSTRUMENTS", 1)
    with db.writer_session() as s:
        instruments.get_or_create(s, "AAPL")
    with pytest.raises(instruments.UniverseFull), db.writer_session() as s:
        instruments.get_or_create(s, "MSFT")
def test_writer_session_rolls_back_on_error(market_store_db):
    with pytest.raises(ZeroDivisionError), db.writer_session() as s:
        instruments.get_or_create(s, "AAPL"); 1 / 0
    with db.reader_session() as s:
        assert instruments.get_ids(s, ["AAPL"]) == {}
def test_stale_flag_is_consumed_once():
    staleness.mark_stale_served()
    assert staleness.consume_stale_served() is True
    assert staleness.consume_stale_served() is False
def test_metrics_snapshot_resets():
    metrics.snapshot_and_reset(); metrics.incr("l2_hit", 2)
    assert metrics.snapshot_and_reset() == {"l2_hit": 2}
    assert metrics.snapshot_and_reset() == {}

# tests/test_currency_subunits.py
@pytest.mark.parametrize("code,expected", [("GBp", ("GBP", 100.0)), ("GBX", ("GBP", 100.0)),
    ("ILA", ("ILS", 100.0)), ("ZAc", ("ZAR", 100.0)), ("USD", ("USD", 1.0)), ("CZK", ("CZK", 1.0))])
def test_subunit(code, expected):
    assert subunit(code) == expected
```

- [ ] **Step 2: Run** `python -m pytest tests/test_market_store_core.py tests/test_currency_subunits.py -q` → fails with `ModuleNotFoundError: market_store`.
- [ ] **Step 3: Implement** the modules and the fixture exactly to the Interfaces block.
- [ ] **Step 4: Run** the two files → pass; run the fast suite → pass (the `ILA`/`ZAc` entries change no existing test).
- [ ] **Step 5: Commit and merge into `feat/market-store`.** `feat(market-store): package skeleton, flag, sessions, symbol validation`

**Acceptance:** tests green; `python -c "import market_store.config"` works with `PORTFYL_EDITION=local`. **Rollback:** revert the commit.

---

## Wave 1 — store modules and the frontend hook (3 ∥ 4 ∥ 5)

### Task 3: `info` snapshot store **[stronger model — the sanity rules decide what price users see]**

**Files:**
- Create: `backend/market_store/info_store.py`
- Test: `backend/tests/test_market_store_info.py`
- Must not touch: `market_data.py`, `market_store/__init__.py`, `tests/conftest.py`, anything owned by Tasks 4–5

**Interfaces:**
- Consumes: `db.reader_session`, `db.writer_session`, `instruments.get_or_create`, `instruments.lock`, `symbols.canonical`, `symbols.is_fx`, `config.*`, `metrics.incr`.
- Produces:
  - `@dataclass(frozen=True) class StoredInfo: payload: dict; status: str; fetched_at: datetime; checked_at: datetime; next_attempt_at: datetime | None`
  - `sanitize(info: dict) -> dict` — keeps `str`, `int`, `bool`, `None`, finite `float`; non-finite float → `None`; numpy scalars → `.item()`; recurses into `dict`/`list`; drops every other value and the key `"companyOfficers"`.
  - `price_of(info: dict) -> float` — first positive of `currentPrice`, `regularMarketPrice`, `previousClose`, else `0.0` (same order as `market_data.quote`).
  - `load(symbols: Iterable[str]) -> dict[str, StoredInfo]` — keyed by canonical symbol; invalid or unknown symbols are absent; one query.
  - `needs_fetch(stored: StoredInfo | None, now: datetime) -> bool` — `None` → `True`; `status == "ok"` → `now - checked_at >= INFO_TTL`; `status == "empty"` → `now >= next_attempt_at`.
  - `save(symbol: str, info: dict, *, now: datetime | None = None) -> dict` — applies the rules below and returns **the payload to serve**. Never raises for `InvalidSymbol` or `UniverseFull`: logs once and returns `sanitize(info)` without writing.

- [ ] **Step 1: Write the failing tests** (all use `market_store_db`; `T0 = datetime(2026, 11, 12, 15, 0, tzinfo=timezone.utc)`):

```python
def info(price, **extra): return {"currentPrice": price, "currency": "USD", **extra}

def test_save_then_load_roundtrip():
    assert info_store.save("aapl", info(150.0), now=T0) == info(150.0)
    st = info_store.load(["AAPL", "MSFT"])
    assert set(st) == {"AAPL"} and st["AAPL"].status == "ok" and st["AAPL"].fetched_at == T0

def test_empty_answer_keeps_last_good():
    info_store.save("AAPL", info(150.0), now=T0)
    assert info_store.save("AAPL", {}, now=T0 + timedelta(minutes=6)) == info(150.0)
    st = info_store.load(["AAPL"])["AAPL"]
    assert (st.status, st.payload, st.fetched_at) == ("empty", info(150.0), T0)
    assert st.next_attempt_at == T0 + timedelta(minutes=6, seconds=60)

def test_backoff_doubles_and_caps():
    t = T0
    for _ in range(6):
        info_store.save("DEAD", {}, now=t)
    assert info_store.load(["DEAD"])["DEAD"].next_attempt_at == t + timedelta(seconds=900)

def test_first_empty_answer_is_remembered():
    assert info_store.save("DEAD", {}, now=T0) == {}
    assert info_store.needs_fetch(info_store.load(["DEAD"])["DEAD"], T0 + timedelta(seconds=30)) is False

def test_absurd_price_is_parked_then_confirmed():
    info_store.save("AAPL", info(150.0), now=T0)
    assert info_store.save("AAPL", info(15000.0), now=T0) == info(150.0)       # parked
    assert info_store.load(["AAPL"])["AAPL"].payload == info(150.0)
    assert info_store.save("AAPL", info(15100.0), now=T0) == info(15100.0)     # within 2 % of the candidate
    assert metrics.snapshot_and_reset().get("sanity_rejected") == 1

def test_normal_move_is_accepted():
    info_store.save("AAPL", info(150.0), now=T0)
    assert info_store.save("AAPL", info(100.0), now=T0) == info(100.0)         # x0.67, inside [0.5, 2.0]

def test_fx_bounds_are_tighter():
    info_store.save("USDCZK=X", info(23.0), now=T0)
    assert info_store.save("USDCZK=X", info(1.0), now=T0) == info(23.0)
    assert info_store.save("USDCZK=X", info(27.0), now=T0) == info(27.0)       # x1.17
    assert info_store.save("USDCZK=X", info(36.0), now=T0) == info(27.0)       # x1.33 parked

def test_sanitize_drops_what_json_cannot_hold():
    raw = {"a": float("nan"), "b": np.float64(1.5), "c": object(), "companyOfficers": [{"n": 1}],
           "d": {"x": pd.Timestamp("2026-01-01"), "y": [1, float("inf")]}}
    assert info_store.sanitize(raw) == {"a": None, "b": 1.5, "d": {"y": [1, None]}}

def test_invalid_symbol_is_served_but_not_stored():
    assert info_store.save("AA PL", info(1.0), now=T0) == info(1.0)
    assert info_store.load(["AA PL"]) == {}

def test_needs_fetch_windows():
    info_store.save("AAPL", info(150.0), now=T0)
    st = info_store.load(["AAPL"])["AAPL"]
    assert info_store.needs_fetch(st, T0 + timedelta(seconds=299)) is False
    assert info_store.needs_fetch(st, T0 + timedelta(seconds=300)) is True
    assert info_store.needs_fetch(None, T0) is True
```

- [ ] **Step 2: Run** `python -m pytest tests/test_market_store_info.py -q` → fails (`info_store` missing).
- [ ] **Step 3: Implement `save`** with these rules, inside one `db.writer_session()` after `get_or_create` + `lock`:

```
clean = sanitize(info); p = price_of(clean); row = the instrument's 'info' snapshot or None
if p <= 0:                                   # empty or unpriced
    if row is None: insert(payload=clean, status='empty', fetched_at=now, attempts=1)
    else:           row.status='empty'; row.attempts += 1          # payload and fetched_at untouched
    next_attempt_at = now + min(60 * 2**(attempts-1), 900) seconds; checked_at = now
    return row.payload
old = price_of(row.payload) if row else 0
lo, hi = (0.8, 1.25) if is_fx(symbol) else (0.5, 2.0)
accept = old <= 0 or lo <= p/old <= hi \
         or (row.pending_payload and abs(p / price_of(row.pending_payload) - 1) <= 0.02)
if not accept:
    row.pending_payload = clean; row.checked_at = now; metrics.incr('sanity_rejected'); return row.payload
upsert(payload=clean, status='ok', fetched_at=now, checked_at=now, attempts=0,
       next_attempt_at=None, pending_payload=None, source='yfinance'); return clean
```

- [ ] **Step 4: Implement** `sanitize`, `price_of`, `load`, `needs_fetch` to the Interfaces block.
- [ ] **Step 5: Run** the file → pass; run the fast suite → pass.
- [ ] **Step 6: Commit** on the task branch. `feat(market-store): info snapshot store with sanity rules`

**Acceptance:** tests green; no function in `info_store` has a `Session` parameter. **Rollback:** drop the branch.

### Task 4: Daily history — adapter, store, read API **[stronger model — money correctness: bases, splits, completed sessions]**

**Files:**
- Create: `backend/market_store/yahoo.py`, `backend/market_store/history_store.py`, `backend/market_store/history.py`
- Test: `backend/tests/test_market_store_history.py`
- Must not touch: `market_data.py`, `market_store/__init__.py`, `tests/conftest.py`, anything owned by Tasks 3 and 5

**Interfaces:**
- Consumes: Task 2 modules; `market_data.download`, `market_data.run_bounded`, `market_data.get_infos`, `market_data.quote` (import `market_data` inside functions in `history.py`, at module top in `yahoo.py`).
- Produces:
  - `yahoo.fetch_daily(symbols: Sequence[str], *, start: date | None = None, period: str | None = None) -> dict[str, pd.DataFrame]` — exactly one of `start`/`period`. Calls `market_data.download(list(symbols), start=start.isoformat() | period=period, auto_adjust=False, actions=True, progress=False)`. Each returned frame: index of `datetime.date` ascending, columns `close`, `adj_close`, `split_ratio`, `dividend` (floats; `NaN` where there is no event). Handles both column layouts yfinance returns (MultiIndex `(field, ticker)` and flat for one ticker). `Adj Close` missing → `adj_close = close`. A `Stock Splits`/`Dividends` value of 0 → `NaN`. Rows whose `close` or `adj_close` is non-finite or ≤ 0 are dropped. Symbols with no rows are omitted. Any exception → `{}`.
  - `history_store.Coverage` (frozen dataclass): `history_start: date | None`, `checked_at: datetime | None`, `last_date: date | None`, `next_attempt_at: datetime | None`.
  - `history_store.coverage(symbols: Iterable[str]) -> dict[str, Coverage]` (unknown symbols absent).
  - `history_store.read(symbols: Iterable[str], *, start: date | None = None, last_n: int | None = None) -> dict[str, pd.DataFrame]` (frames shaped like `fetch_daily`'s).
  - `history_store.apply_fetch(symbol: str, frame: pd.DataFrame | None, *, requested_start: date | None, full: bool, now: datetime) -> str` → one of `"replaced"`, `"appended"`, `"unchanged"`, `"mismatch"`, `"empty"`.
  - `history.refresh(symbols: Sequence[str], start: date | None, *, now: datetime | None = None) -> None`
  - `history.closes(symbols: Sequence[str], *, start: date | None = None, last_n: int | None = None, adjusted: bool = True, include_today: bool = True, now: datetime | None = None) -> pd.DataFrame` — wide frame, tz-naive `DatetimeIndex` ascending, one column per symbol that has data (in the order given), values from `adj_close` (`adjusted=True`) or `close`.
  - `history.panel(symbols: Sequence[str], start: date, *, include_today: bool = True, now: datetime | None = None) -> tuple[pd.DataFrame, pd.DataFrame]` — `(close frame, split frame)`; the split frame has the same index and columns with `0.0` where there is no split (the shape `routers/analytics._load_close_panel` consumes).

- [ ] **Step 1: Write the failing tests** (`market_store_db`; `NOW = datetime(2026, 11, 13, 9, 0, tzinfo=timezone.utc)`; helper `frame({date: (close, adj[, split[, div]])})` builds a `fetch_daily`-shaped frame; helper `stub_fetch(monkeypatch, *answers)` replaces `yahoo.fetch_daily` with a recorder returning the answers in order):

```python
D10, D11, D12, D13 = (date(2026, 11, d) for d in (10, 11, 12, 13))

def test_full_fetch_stores_only_completed_sessions(monkeypatch):
    stub_fetch(monkeypatch, {"AAPL": frame({D11: (10, 10), D12: (11, 11), D13: (12, 12)})})
    history.refresh(["AAPL"], D10, now=NOW)                       # NOW is the 13th
    assert list(history_store.read(["AAPL"])["AAPL"].index) == [D11, D12]

def test_tail_appends_when_overlap_agrees(monkeypatch):
    calls = stub_fetch(monkeypatch,
        {"AAPL": frame({D10: (10, 10), D11: (11, 11)})},
        {"AAPL": frame({D10: (10, 10), D11: (11.0000001, 11), D12: (12, 12)})})
    history.refresh(["AAPL"], D10, now=NOW.replace(day=12))
    history.refresh(["AAPL"], D10, now=NOW)                       # 24 h later -> tail check
    assert list(history_store.read(["AAPL"])["AAPL"]["close"]) == [10, 11, 12]
    assert calls[1].kwargs == {"period": "1mo"}
    assert metrics.snapshot_and_reset()["history_appended"] == 1

def test_split_in_tail_replaces_whole_series(monkeypatch):
    calls = stub_fetch(monkeypatch,
        {"AAPL": frame({D10: (100, 100), D11: (104, 104)})},
        {"AAPL": frame({D10: (25, 25), D11: (26, 26), D12: (27, 27, 4.0)})},     # tail, new basis
        {"AAPL": frame({D10: (25, 25), D11: (26, 26), D12: (27, 27, 4.0)})})     # full refetch
    history.refresh(["AAPL"], D10, now=NOW.replace(day=12))
    history.refresh(["AAPL"], D10, now=NOW)
    stored = history_store.read(["AAPL"])["AAPL"]
    assert list(stored["close"]) == [25, 26, 27] and stored["split_ratio"][D12] == 4.0
    assert calls[2].kwargs == {"start": D10}
    assert metrics.snapshot_and_reset()["history_replaced"] == 2                  # first load + replace

def test_dividend_rescale_replaces_series(monkeypatch):
    stub_fetch(monkeypatch,
        {"KO": frame({D10: (60, 60), D11: (60, 60)})},
        {"KO": frame({D10: (60, 59.4), D11: (60, 59.4), D12: (59.4, 59.4, None, 0.6)})},
        {"KO": frame({D10: (60, 59.4), D11: (60, 59.4), D12: (59.4, 59.4, None, 0.6)})})
    history.refresh(["KO"], D10, now=NOW.replace(day=12)); history.refresh(["KO"], D10, now=NOW)
    assert list(history_store.read(["KO"])["KO"]["adj_close"]) == [59.4, 59.4, 59.4]

def test_no_overlap_replaces(monkeypatch): ...          # tail starts after the last stored date -> third call is start=
def test_empty_fetch_keeps_history(monkeypatch):
    stub_fetch(monkeypatch, {"AAPL": frame({D10: (10, 10), D11: (11, 11)})}, {})
    history.refresh(["AAPL"], D10, now=NOW.replace(day=12)); history.refresh(["AAPL"], D10, now=NOW)
    assert len(history_store.read(["AAPL"])["AAPL"]) == 2

def test_failed_replace_rolls_back(monkeypatch):        # make the bulk insert raise after the delete
    ...; assert len(history_store.read(["AAPL"])["AAPL"]) == 2

def test_fresh_check_makes_no_provider_call(monkeypatch):
    calls = stub_fetch(monkeypatch, {"AAPL": frame({D10: (10, 10), D11: (11, 11)})})
    history.refresh(["AAPL"], D10, now=NOW); history.refresh(["AAPL"], D10, now=NOW + timedelta(seconds=299))
    assert len(calls) == 1

def test_earlier_start_extends_coverage(monkeypatch):   # second refresh with start < history_start -> start= call
def test_closes_picks_the_adjusted_column(monkeypatch):
    stub_fetch(monkeypatch, {"KO": frame({D10: (60, 59.4), D11: (61, 60.4)})})
    assert list(history.closes(["KO"], start=D10, include_today=False, now=NOW)["KO"]) == [59.4, 60.4]
    assert list(history.closes(["KO"], start=D10, adjusted=False, include_today=False, now=NOW)["KO"]) == [60, 61]

def test_today_point_comes_from_the_quote(monkeypatch):
    stub_fetch(monkeypatch, {"AAPL": frame({D11: (10, 10), D12: (11, 11)})})
    monkeypatch.setattr(market_data, "get_infos", lambda syms, **kw: {"AAPL": {
        "currentPrice": 30.0, "regularMarketTime": int(NOW.timestamp())}})
    out = history.closes(["AAPL"], start=D10, now=NOW)
    assert out.index[-1] == pd.Timestamp(D13) and out["AAPL"].iloc[-1] == 30.0
    # a quote stamped on the 12th adds nothing; include_today=False adds nothing

def test_last_n_returns_last_rows(monkeypatch): ...     # last_n=2 with no coverage fetches start = today - 370 d
def test_panel_returns_split_frame(monkeypatch): ...    # splits[D12] == 4.0, 0.0 elsewhere, same index/columns
def test_unknown_symbol_is_left_out(monkeypatch): ...   # columns == ["AAPL"] when "ZZZZ" has no data
def test_invalid_symbol_is_ignored(monkeypatch): ...    # "AA PL" -> no provider call, no column

def test_tail_timeout_serves_stored_and_marks_stale(monkeypatch):
    gate = threading.Event()
    def slow(symbols, **kw):
        if "period" in kw: gate.wait(5)
        return {"AAPL": frame({D10: (10, 10), D11: (11, 11)})}
    monkeypatch.setattr(yahoo, "fetch_daily", slow)
    monkeypatch.setattr(config, "stale_deadline", lambda env=None: 0.05)
    history.refresh(["AAPL"], D10, now=NOW.replace(day=12))
    started = time.time(); history.refresh(["AAPL"], D10, now=NOW)
    assert time.time() - started < 2 and staleness.consume_stale_served() is True
    gate.set()

def test_fetch_daily_normalises_both_layouts(monkeypatch):
    # monkeypatch market_data.download with (a) a MultiIndex frame for two tickers including a NaN close
    # and a 0.0 close, (b) a flat frame for one ticker without "Adj Close"; assert columns, index type
    # (datetime.date), dropped rows, NaN for "no split"/"no dividend", adj_close == close in (b)

def test_parity_with_download(monkeypatch):
    # same MultiIndex frame through market_data.download; closes(adjusted=True, include_today=False)
    # equals raw["Adj Close"] for completed dates and closes(adjusted=False) equals raw["Close"]
    # (pd.testing.assert_frame_equal(..., check_freq=False, check_names=False))
```

Write out every test marked `...` in the same style before running; none may be skipped.

- [ ] **Step 2: Run** `python -m pytest tests/test_market_store_history.py -q` → fails (modules missing).
- [ ] **Step 3: Implement `yahoo.fetch_daily`** to the Interfaces block.
- [ ] **Step 4: Implement `history_store.apply_fetch`:**

```
finals = frame rows with index < now.astimezone(UTC).date()         (frame None -> empty)
if finals is empty:
    writer: history_attempts += 1; history_next_attempt_at = now + min(60 * 2**(attempts-1), 900) s
    return "empty"                                                    # nothing deleted
writer session -> get_or_create -> lock(instrument)
if full:
    delete the instrument's rows; bulk insert finals (source='yfinance', fetched_at=now)
    history_start = min(x for x in (requested_start, instrument.history_start) if x is not None)
    history_checked_at = now; history_attempts = 0; history_next_attempt_at = None
    metrics.incr('history_replaced'); return "replaced"
stored = the instrument's rows with trade_date >= finals.index.min()
common = dates present in both
if not common or any(abs(f/s - 1) > OVERLAP_TOLERANCE for close and adj_close over common):
    return "mismatch"                                                 # nothing written
new = finals rows with date > max(stored dates); insert them; history_checked_at = now; attempts = 0
metrics.incr('history_appended') if new else None
return "appended" if new else "unchanged"
```

- [ ] **Step 5: Implement `history.refresh`:**

```
valid = canonical symbols (invalid ones dropped); cov = history_store.coverage(valid)
want = start or (now.date() - HISTORY_DEFAULT_DAYS days)
full = [s for s in valid if s not in cov or cov[s].history_start is None or want < cov[s].history_start]
       minus symbols with next_attempt_at > now
tail = [s for s in valid if s not in full and (cov[s].checked_at is None or now - cov[s].checked_at >= HISTORY_TAIL_TTL)]
if full:                                              # no stored answer exists: block, as today
    frames = yahoo.fetch_daily(full, start=min(want, earliest existing history_start among `full`))
    for s in full: apply_fetch(s, frames.get(s), requested_start=want, full=True, now=now)
if tail:                                              # a stored answer exists: short deadline
    done = market_data.run_bounded(_tail_job, tail, now, timeout=config.stale_deadline(), default=None)
    if done is None: staleness.mark_stale_served(); metrics.incr('stale_served')
_tail_job(tail, now): frames = fetch_daily(tail, period=HISTORY_TAIL_PERIOD)
    for s in tail: if apply_fetch(s, frames.get(s), requested_start=None, full=False, now=now) == "mismatch":
        again = fetch_daily([s], start=<stored history_start>); apply_fetch(s, again.get(s), requested_start=None, full=True, now=now)
    return True
```

- [ ] **Step 6: Implement `closes` and `panel`:** call `refresh`, read, build the wide frame; when `include_today`, call `market_data.get_infos(symbols)` once and, for each symbol with a positive `market_data.quote(info, symbol)[0]` whose `regularMarketTime` falls on today's UTC date and after the symbol's last stored date, set that value on `pd.Timestamp(today)` (in `panel`, the split frame gets `0.0` there). Apply `last_n` with `.tail(last_n)` after dropping all-NaN rows.
- [ ] **Step 7: Run** the file → pass; run the fast suite → pass.
- [ ] **Step 8: Commit** on the task branch. `feat(market-store): daily history with verify-then-append`

**Acceptance:** tests green; `grep -n "Session" backend/market_store/history.py backend/market_store/yahoo.py` shows no function parameter. **Rollback:** drop the branch.

### Task 5: Dashboard one-shot refetch

**Files:**
- Create: `frontend/src/hooks/usePriceRefreshRetry.js`, `frontend/src/hooks/usePriceRefreshRetry.test.jsx`
- Modify: `frontend/src/pages/Dashboard.jsx` (one import, one call after the `holdings` query near line 91)
- Must not touch: `frontend/src/api.js`, `frontend/src/i18n/**`, `DESIGN.md`, any CSS, `package.json`

**Interfaces:**
- Consumes: `/portfolio/summary` field `prices_refreshing: boolean` (added by Task 10; absent or `false` until then — the hook then does nothing).
- Produces: `usePriceRefreshRetry(summary, refetchers, { delayMs = 3000, maxAttempts = 2 } = {})` — while `summary?.prices_refreshing === true` and fewer than `maxAttempts` retries have fired since it last became true, schedule one timer of `delayMs`; when it fires call every function in `refetchers`. The counter resets when `prices_refreshing` is not `true`. The timer is cleared on unmount and on every re-run.

- [ ] **Step 1: Write the failing test** (`vi.useFakeTimers()`, `renderHook` from `@testing-library/react`):

```jsx
it("refetches once after the delay while prices are refreshing", () => {
  const refetch = vi.fn();
  renderHook(() => usePriceRefreshRetry({ prices_refreshing: true }, [refetch]));
  vi.advanceTimersByTime(2999); expect(refetch).not.toHaveBeenCalled();
  vi.advanceTimersByTime(1);    expect(refetch).toHaveBeenCalledTimes(1);
});
it("stops after two attempts", () => {
  const refetch = vi.fn();
  const { rerender } = renderHook(({ s }) => usePriceRefreshRetry(s, [refetch]),
    { initialProps: { s: { prices_refreshing: true, n: 0 } } });
  for (let n = 1; n <= 4; n++) { vi.advanceTimersByTime(3000); rerender({ s: { prices_refreshing: true, n } }); }
  expect(refetch).toHaveBeenCalledTimes(2);
});
it("does nothing when prices are not refreshing", () => { /* false, undefined summary, missing field */ });
it("starts counting again after prices settled", () => { /* true -> false -> true gives a third call */ });
it("clears the timer on unmount", () => { /* unmount, advance, expect no call */ });
```

- [ ] **Step 2: Run** `npm test -- usePriceRefreshRetry` → fails (module missing).
- [ ] **Step 3: Implement the hook** (`useEffect` + `useRef` for the counter; no state, no render output).
- [ ] **Step 4: Wire it** in `Dashboard.jsx`: `usePriceRefreshRetry(summary, [refetchSummary, refetchHoldings]);`
- [ ] **Step 5: Run** `npm test`, `npm run test:cloud`, `npm run build`, `npm run build:cloud` → all pass.
- [ ] **Step 6: Commit** on the task branch. `feat(dashboard): refetch once when prices are being refreshed`

**Acceptance:** four commands green; `git diff --stat` shows only the three files. **Rollback:** drop the branch.

### Task 6: Wave 1 gate — re-integrate and re-verify

**Files:**
- Create: `backend/tests/test_market_store_contract.py`

- [ ] **Step 1:** Merge `main` into `feat/market-store` if `main` moved (resolve conflicts here, not in task branches), then merge the branches of Tasks 3, 4, 5.
- [ ] **Step 2: Add the contract test:**

```python
PUBLIC = (info_store, history, history_store, yahoo)
def test_store_functions_never_take_a_session():
    for module in PUBLIC:
        for name, fn in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("_") or fn.__module__ != module.__name__: continue
            for p in inspect.signature(fn).parameters.values():
                assert p.name not in ("db", "session") and p.annotation is not Session, f"{module.__name__}.{name}"
def test_store_modules_define_no_coroutines():
    for module in PUBLIC:
        assert not [n for n, f in inspect.getmembers(module, inspect.iscoroutinefunction)]
def test_only_store_modules_import_market_models():
    offenders = [p for p in BACKEND.rglob("*.py")
                 if "tests" not in p.parts and ".venv" not in p.parts and p.parent.name != "market_store"
                 and p.name != "models.py" and "alembic" not in p.parts
                 and re.search(r"Market(Instrument|Snapshot|PriceDaily)", p.read_text(encoding="utf-8"))]
    assert offenders == []
```

- [ ] **Step 3: Verify.** Fast suite on Python 3.12 **and** 3.14 (`uv venv .venv314 --python 3.14` + the same lock) → pass. PostgreSQL suite (port 55456) → pass. `alembic heads` equals `EXPECTED_ALEMBIC_HEAD`. Frontend four commands → pass.
- [ ] **Step 4: Commit** on `feat/market-store`. `test(market-store): contract tests for the store boundary`

**Acceptance:** everything in Step 3 green on the integration branch.

---

## Wave 2 — wiring the call sites (7 ∥ 8 ∥ 9 ∥ 10 ∥ 11)

Every task in this wave follows one pattern: `if market_store.config.enabled(): <store path> else: <the existing lines, unchanged>`. Existing tests are not edited unless the task says so.

### Task 7: L2 step in `market_data.get_infos` **[stronger model — concurrency and deadlines on the price path]**

**Files:**
- Modify: `backend/market_data.py` (`get_infos`, `get_info`, one new private function), `backend/main.py:389-393` (startup), `backend/routers/alerts.py:136`, `backend/tests/conftest.py` (autouse fixture), `backend/tests/test_alerts.py` and any other test whose `get_infos` stub is reached from `run_check` (they must accept `**kwargs`)
- Test: `backend/tests/test_market_data_store_path.py`
- Must not touch: `fx.py`, `routers/analytics.py`, `routers/portfolio.py`, `routers/market.py`, `market_store/*`

**Interfaces:**
- Consumes: `info_store.load`, `info_store.save`, `info_store.needs_fetch`, `config.enabled`, `config.stale_deadline`, `config.INFO_TTL`, `symbols.canonical`, `staleness.mark_stale_served`, `metrics.incr`, `metrics.maybe_log`, `db.preflight`.
- Produces: `get_infos(tickers, timeout: float = INFO_TIMEOUT, *, require_fresh: bool = False) -> dict[str, dict]` and `get_info(ticker, timeout=INFO_TIMEOUT, *, require_fresh=False) -> dict`. With the flag off both behave exactly as today and ignore `require_fresh`.

- [ ] **Step 1: Write the failing tests.** Two helpers live in the test file: fixture `mock_raw_info` replaces `market_data._raw_info` with a stub that returns `{"currentPrice": 150.0, "currency": "USD"}` and counts its invocations in `.calls`; `wait_until(predicate, timeout=5.0)` polls every 20 ms and fails the test on timeout.

```python
def test_flag_off_never_touches_the_store(monkeypatch, mock_raw_info):
    monkeypatch.delenv("PORTFYL_MARKET_STORE", raising=False)
    monkeypatch.setattr(info_store, "load", lambda *_: 1 / 0)
    assert market_data.get_infos(["AAPL"])["AAPL"]["currentPrice"] == 150.0

def test_restart_reads_from_the_database(market_store_db, mock_raw_info):
    market_data.get_infos(["AAPL"])
    market_data._cache.clear(); market_data._inflight.clear()            # "restart"
    assert market_data.get_infos(["AAPL"])["AAPL"]["currentPrice"] == 150.0
    assert mock_raw_info.calls == 1
    assert metrics.snapshot_and_reset()["l2_hit"] == 1

def test_stale_value_is_served_after_the_short_deadline(market_store_db, monkeypatch):
    info_store.save("AAPL", {"currentPrice": 150.0}, now=datetime.now(timezone.utc) - timedelta(hours=1))
    gate = threading.Event()
    monkeypatch.setattr(market_data, "_raw_info", lambda s: (gate.wait(5), {"currentPrice": 151.0})[1])
    monkeypatch.setattr(config, "stale_deadline", lambda env=None: 0.05)
    started = time.time()
    assert market_data.get_infos(["AAPL"])["AAPL"]["currentPrice"] == 150.0
    assert time.time() - started < 2 and staleness.consume_stale_served() is True
    gate.set(); wait_until(lambda: info_store.load(["AAPL"])["AAPL"].payload["currentPrice"] == 151.0)

def test_missing_value_waits_for_the_full_deadline(market_store_db, monkeypatch):
    monkeypatch.setattr(config, "stale_deadline", lambda env=None: 0.05)
    monkeypatch.setattr(market_data, "_raw_info", lambda s: (time.sleep(0.3), {"currentPrice": 10.0})[1])
    assert market_data.get_infos(["NEW"])["NEW"]["currentPrice"] == 10.0

def test_require_fresh_rejects_a_stale_value(market_store_db, monkeypatch):
    info_store.save("AAPL", {"currentPrice": 150.0}, now=datetime.now(timezone.utc) - timedelta(hours=1))
    monkeypatch.setattr(market_data, "_raw_info", lambda s: (time.sleep(1), {})[1])
    assert market_data.get_infos(["AAPL"], timeout=0.1, require_fresh=True) == {"AAPL": {}}

def test_backing_off_ticker_makes_no_provider_call(market_store_db, mock_raw_info):
    info_store.save("DEAD", {}, now=datetime.now(timezone.utc))
    assert market_data.get_infos(["DEAD"]) == {"DEAD": {}} and mock_raw_info.calls == 0

def test_broker_symbol_is_stored_under_its_yahoo_symbol(market_store_db, mock_raw_info):
    market_data.get_infos(["COPM.L"])
    assert set(info_store.load(["COPM.AS", "COPM.L"])) == {"COPM.AS"}

def test_invalid_ticker_returns_empty_without_row(market_store_db, mock_raw_info):
    assert market_data.get_infos(["bad ticker!"]) == {"bad ticker!": {}}
    assert mock_raw_info.calls == 0

def test_parked_price_is_not_returned_to_the_caller(market_store_db, monkeypatch):
    info_store.save("AAPL", {"currentPrice": 150.0}, now=datetime.now(timezone.utc) - timedelta(hours=1))
    monkeypatch.setattr(market_data, "_raw_info", lambda s: {"currentPrice": 15000.0})
    assert market_data.get_infos(["AAPL"])["AAPL"]["currentPrice"] == 150.0
```

- [ ] **Step 2: Run** → fail.
- [ ] **Step 3: Implement.** Keep the current body as the flag-off branch. Flag-on branch:

```
_raw_info_stored(symbol): info = _raw_info(symbol); metrics.incr('provider_fetch')
                          try: return info_store.save(symbol, info)   except Exception: log; return info
get_infos:
  serve from L1 exactly as today
  for the rest: sym = canonical(yf_symbol(tk)); InvalidSymbol -> out[tk] = {} and skip
  stored = info_store.load(all syms)                                   # one query, session closed
  per ticker, st = stored.get(sym):
     usable = st is not None and not needs_fetch(st, now)
     if usable and (not require_fresh or st.status == 'ok'):
         out[tk] = st.payload; L1[key] = (time.time() - age_of(st.checked_at), st.payload); metrics.incr('l2_hit')
     elif usable:                                                       # require_fresh, backing off
         out[tk] = {}
     else:
         fallback[key] = st.payload if (st and st.payload and not require_fresh) else None
         submit _raw_info_stored(sym) unless a future for key is already in _inflight   (release DB first, as today)
  wait: limit = timeout if fallback[key] is None else config.stale_deadline()
        result -> L1[key] = (time.time(), info); out
        timeout -> leave the future in _inflight (as today); if fallback: out = fallback,
                   staleness.mark_stale_served(), metrics.incr('stale_served'); else {}
  metrics.maybe_log()
```

- [ ] **Step 4: Startup.** In `main.py` after `assert_alembic_head(schema_db)`: `from market_store import config as _ms_config, db as _ms_db` and `if _ms_config.enabled(os.environ): _ms_db.preflight()` (this raises in the cloud edition and when the database user cannot write).
- [ ] **Step 5: Alerts.** `routers/alerts.py:136` → `asyncio.to_thread(market_data.get_infos, tickers, require_fresh=True)` (keep the variable names found there). Then `grep -rn "get_infos" backend/tests` and make every stub that `run_check` reaches accept `**kwargs`.
- [ ] **Step 6: `tests/conftest.py`:** in `_fresh_market_data_caches` also call `market_store.metrics.snapshot_and_reset()` and `market_store.staleness.consume_stale_served()` before and after.
- [ ] **Step 7: Run** the new file, `tests/test_market_data_cache.py`, `tests/test_alerts.py`, `tests/test_event_loop_not_blocked.py`, then the whole fast suite → pass.
- [ ] **Step 8: Commit.** `feat(market-data): durable second cache level for quotes`

**Acceptance:** tests green; with the flag off `git diff` shows the old `get_infos` body unchanged inside its branch. **Rollback:** drop the branch.

### Task 8: `fx.py` on the store

**Files:** Modify `backend/fx.py` (`_load_pair_series` only). Test: `backend/tests/test_fx_store_path.py`. Must not touch: everything else.

**Interfaces:** Consumes `history.closes`. Produces nothing new; `_load_pair_series(currency, start, end)` returns the same `pd.Series | None`.

- [ ] **Step 1: Failing tests** (`market_store_db`; stub `yahoo.fetch_daily` to return `{"USDCZK=X": frame({Fri: (23.4, 23.4), Mon: (23.6, 23.6)})}` and `{"GBPCZK=X": …(29.0)}`; stub `market_data.get_infos` to `{}`):

```python
def test_rate_on_a_trading_day():      assert fx.fetch_fx_to_czk("USD", MON) == 23.6
def test_weekend_uses_the_previous_close(): assert fx.fetch_fx_to_czk("USD", SUN) == 23.4
def test_pence_use_the_pound_rate():   assert fx.fetch_fx_to_czk("GBX", MON) == pytest.approx(0.29)
def test_czk_is_one():                 assert fx.fetch_fx_to_czk("CZK", MON) == 1.0
def test_no_data_returns_none():       assert fx.fetch_fx_to_czk("XXX", MON) is None
def test_bulk_uses_one_series_per_currency():   # bulk_fetch_fx([("USD", FRI), ("USD", MON)]) -> one fetch_daily call
```

- [ ] **Step 2: Run** → fail. **Step 3: Implement:** when enabled, `frame = history.closes([pair], start=start, adjusted=True)`; return `None` if the pair's column is absent or empty, else the column with rows `<= end + 2 days`, dropped NaN; keep `_DAILY_CACHE` exactly as now. **Step 4: Run** the new file and `tests/test_fx.py` → pass. **Step 5: Commit.** `feat(fx): read FX history from the market store`

**Acceptance:** `tests/test_fx.py` unchanged and green.

### Task 9: `routers/analytics.py` on the store

**Files:** Modify `backend/routers/analytics.py` (`_load_close_panel`, `_fx_to_usd_series`, `_ticker_daily_returns`, `_ccy_to_usd`, `_price_to_usd`, and the `"GBp"` test near line 1439). Test: `backend/tests/test_analytics_store_path.py`. Must not touch: everything else.

**Interfaces:** Consumes `history.panel`, `history.closes`, `currency_codes.subunit`. Produces: `_undo_future_splits(closes: pd.DataFrame, splits: pd.DataFrame, keep_split) -> pd.DataFrame` — the loop that is lines 70-83 today, moved without change and used by both branches.

- [ ] **Step 1: Failing tests:**

```python
def test_close_panel_is_identical_through_the_store(monkeypatch, market_store_db):
    # one fake raw frame (2 tickers, 6 completed days, a 4:1 split on day 4 for the first ticker)
    # flag off: patch routers.analytics.yf.download / market_data.download to return it
    # flag on: patch yahoo.fetch_daily with the same data in normalised form; market_data.get_infos -> {}
    pd.testing.assert_frame_equal(off_panel, on_panel, check_freq=False, check_names=False)
    assert on_panel["AAA"].iloc[0] == pytest.approx(4 * adjusted_close_day_1)      # as-traded before the split

def test_keep_split_leaves_the_adjustment(...):     # keep_split=lambda t, d: True -> panel equals the close frame
def test_minor_units_use_the_major_currency_rate():
    idx = pd.Timestamp("2026-11-10"); fx = {"ILS": pd.Series({idx: 0.27}), "GBP": pd.Series({idx: 1.3})}
    assert analytics._price_to_usd(1000.0, "ILA", fx, idx) == pytest.approx(2.7)
    assert analytics._price_to_usd(250.0, "GBp", fx, idx) == pytest.approx(3.25)
    assert analytics._price_to_usd(10.0, "USD", fx, idx) == 10.0
def test_benchmark_returns_from_the_store(...):     # _ticker_daily_returns equals pct_change of adj_close
```

- [ ] **Step 2: Run** → fail. **Step 3: Implement.** Extract `_undo_future_splits`. In `_load_close_panel`, when enabled: `closes, splits = history.panel(yf_tickers, start)`; empty → `pd.DataFrame()`; then `_undo_future_splits(...)` and the same `ffill().dropna(how="all")`. `_fx_to_usd_series` and `_ticker_daily_returns`: when enabled take the column from `history.closes([symbol], start=start, adjusted=True)`. Replace the `"GBp"` literals: `base, divisor = subunit(ccy)`; FX series are fetched and looked up by `base`; `_ccy_to_usd(ccy) = _live_to_usd(base) / divisor`. **Step 4: Run** the new file, `tests/test_analytics.py`, `tests/test_value_series_equivalence.py` → pass. **Step 5: Commit.** `feat(analytics): read close panels from the market store`

**Acceptance:** existing analytics tests unchanged and green; the parity test passes.

### Task 10: `routers/portfolio.py` on the store

**Files:** Modify `backend/routers/portfolio.py` — the four `market_data.download(` call sites (`_two_day_closes`, `get_movers`, `get_heatmap`, `get_benchmarks`; find them with `grep -n "market_data.download(" routers/portfolio.py`), `_pence_to_pounds`, and the dict returned by `get_summary` (next to `"price_source"`, near line 1644). Test: `backend/tests/test_portfolio_store_path.py`. Must not touch: everything else.

**Interfaces:** Consumes `history.closes`, `staleness.consume_stale_served`, `currency_codes.subunit`, `ticker_map.yf_symbol`. Produces: `/portfolio/summary` key `"prices_refreshing": bool` (always present; `False` when the flag is off).

- [ ] **Step 1: Failing tests:**

```python
def test_two_day_closes_from_the_store(market_store_db, monkeypatch):
    # fetch_daily -> AAPL (10, 11), MSFT (20, 22); get_infos -> {}
    assert portfolio._two_day_closes(["AAPL", "MSFT"]) == {"AAPL": (10.0, 11.0), "MSFT": (20.0, 22.0)}
def test_two_day_closes_maps_broker_symbols(...):   # "COPM.L" is fetched as "COPM.AS", keyed back as "COPM.L"
def test_two_day_closes_never_raises(...):          # fetch_daily raises -> {}
def test_minor_unit_to_major():
    assert portfolio._pence_to_pounds(250.0, "GBp") == (2.5, "GBP")
    assert portfolio._pence_to_pounds(250.0, "ZAc") == (2.5, "ZAR")
    assert portfolio._pence_to_pounds(250.0, "ILA") == (2.5, "ILS")
    assert portfolio._pence_to_pounds(250.0, "USD") == (250.0, "USD")
def test_summary_says_when_prices_are_refreshing(...):
    # drive get_summary the way tests/test_portfolio.py does; staleness.mark_stale_served() inside a
    # patched market_data.get_infos -> response["prices_refreshing"] is True; without it False
def test_movers_window_from_the_store(...):         # period "1w" reads start = today - 7 days
```

- [ ] **Step 2: Run** → fail. **Step 3: Implement.** Add one helper, `_store_closes(tickers: list[str], *, start: date | None = None, last_n: int | None = None) -> pd.DataFrame | None`: returns `None` when the flag is off; otherwise `history.closes([yf_symbol(t) for t in tickers], start=start, last_n=last_n, adjusted=True)` with the columns renamed back to the tickers given. Each of the four sites calls it first and, when it returns a frame, uses that frame as its wide close frame (one column per ticker) and skips its `market_data.download` lines; when it returns `None` the existing lines run unchanged. Windows: `_two_day_closes` → `last_n=2`, result `(first, last)` per column, `{}` on any exception; movers → `start = today − 7 days` for `1w`, `today − 31 days` for `1m`; heatmap and benchmarks → the `start` they already compute, or `today − N days` for the period string they pass today. `_pence_to_pounds` → `base, divisor = subunit(ccy)`; return `(price / divisor, base)` when `divisor != 1.0`, else `(price, ccy)`. `get_summary` → `"prices_refreshing": consume_stale_served() if enabled else False`, read **after** all prices were fetched. **Step 4: Run** the new file, `tests/test_portfolio.py`, `tests/test_movers.py` → pass. **Step 5: Commit.** `feat(portfolio): read price windows from the market store`

**Acceptance:** existing portfolio and movers tests unchanged and green.

### Task 11: `routers/market.py` endpoints on the store

**Files:** Modify `backend/routers/market.py` — `get_fx_rate`, `get_quote`, `get_history` only (lines ~996-1061). Test: `backend/tests/test_market_store_endpoints.py`. Must not touch: `get_fundamentals` and everything else.

**Interfaces:** Consumes `market_data.get_info`, `history.closes`, `symbols.canonical`, `ticker_map.yf_symbol`. Produces: no response-shape change.

- [ ] **Step 1: Failing tests** (call the endpoint functions directly, as `tests/test_market.py` does; clear their `ttl_cache` between tests with `cache.cache_clear()`):

```python
def test_history_comes_from_the_store(market_store_db, monkeypatch):
    # fetch_daily -> AAPL adj_close 10, 11; get_infos -> {}
    assert market.get_history("aapl", period="1mo")["data"] == [
        {"date": "2026-11-10", "close": 10.0}, {"date": "2026-11-11", "close": 11.0}]
def test_history_rejects_an_invalid_ticker(market_store_db):
    with pytest.raises(HTTPException) as e: market.get_history("AA PL")
    assert e.value.status_code == 400
def test_history_rejects_an_unknown_period(market_store_db):
    with pytest.raises(HTTPException) as e: market.get_history("AAPL", period="17q")
    assert e.value.status_code == 400
def test_history_without_data_is_404(market_store_db, monkeypatch): ...
def test_quote_comes_from_the_stored_info(market_store_db, monkeypatch): ...   # same keys as today's response
def test_fx_rate_comes_from_the_stored_info(market_store_db, monkeypatch): ... # {"pair": "USDCZK", "rate": 23.5, "base": "USD", "quote": "CZK"}
def test_flag_off_keeps_the_raw_path(monkeypatch): ...                         # yf.Ticker is still called
```

- [ ] **Step 2: Run** → fail. **Step 3: Implement.** When enabled: validate with `symbols.canonical(yf_symbol(ticker.upper()))` → 400 `"Invalid ticker"` on `InvalidSymbol`; `get_quote`/`get_fx_rate` read `market_data.get_info(symbol)` and build the same response from it; `get_history` maps `period` with `{"5d": 5, "1mo": 31, "3mo": 92, "6mo": 183, "1y": 366, "2y": 731, "5y": 1827, "10y": 3653}` days, `"ytd"` → 1 January, `"max"` → `date(1990, 1, 1)`, anything else → 400; reads `history.closes([symbol], start=…, adjusted=True)`; an absent or empty column → 404 as today. **Step 4: Run** the new file and `tests/test_market.py` → pass. **Step 5: Commit.** `feat(market): serve quote, FX and history endpoints from the market store`

**Acceptance:** `tests/test_market.py` unchanged and green.

### Task 12: Wave 2 gate — re-integrate and prove it end to end

**Files:** Create `backend/tests/postgres/test_market_store_e2e.py`.

- [ ] **Step 1:** Merge `main` into `feat/market-store` if it moved, then the branches of Tasks 7–11. Resolve conflicts here.
- [ ] **Step 2: Write the end-to-end tests** (real PostgreSQL, real roles; `role_engine` from Task 1; `monkeypatch.setenv("PORTFYL_MARKET_STORE", "on")`; always `db.bind(None)` in a `finally`):

```python
def test_quotes_and_history_flow_through_the_two_roles(role_engine, postgres_engine, monkeypatch):
    db.bind(role_engine("portfyl_runtime"), writer_engine=role_engine("portfyl_market_writer"))
    monkeypatch.setattr(market_data, "_raw_info", lambda s: {"currentPrice": 150.0, "currency": "USD"})
    monkeypatch.setattr(yahoo, "fetch_daily", lambda symbols, **kw: {"AAPL": frame({D10: (10, 10), D11: (11, 11)})})
    assert market_data.get_infos(["AAPL"])["AAPL"]["currentPrice"] == 150.0
    assert list(history.closes(["AAPL"], start=D10, include_today=False)["AAPL"]) == [10.0, 11.0]
    with postgres_engine.connect() as c:
        assert c.execute(text("SELECT count(*) FROM market_snapshot")).scalar_one() == 1
        assert c.execute(text("SELECT count(*) FROM market_price_daily")).scalar_one() == 2
    # clean up the three tables as the owner in a finally block

def test_preflight_names_the_writer_url(role_engine):
    db.bind(role_engine("portfyl_runtime"))                       # writer falls back to the runtime role
    with pytest.raises(RuntimeError, match="MARKET_WRITER_DATABASE_URL"):
        db.preflight()

def test_preflight_passes_for_the_writer_role(role_engine):
    db.bind(role_engine("portfyl_runtime"), writer_engine=role_engine("portfyl_market_writer")); db.preflight()

def test_series_replace_is_atomic_for_a_reader(role_engine, postgres_engine):
    # store 3 rows; open a second connection, BEGIN, SELECT count -> 3; run a full apply_fetch with 5 rows
    # from the store; the open reader statement still returns 3 or 5 on each new SELECT, never another number
```

- [ ] **Step 3: Verify everything.** Fast suite on 3.12 and 3.14 → pass. PostgreSQL suite (port 55462) → pass. `alembic heads` == `EXPECTED_ALEMBIC_HEAD`. Frontend four commands → pass. `grep -rn "yf\.\(Ticker\|download\)" backend --include=*.py --exclude-dir=tests --exclude-dir=.venv` → the hits are only: `market_data.py`, `jobs.py` (`_next_dividend_info`), `routers/market.py` (flag-off branches, `get_fundamentals`, earnings recap, `_safe_info`, search) — list them in the commit message as the known remainder for Wave 2 of the spec.
- [ ] **Step 4: Commit** on `feat/market-store`. `test(market-store): end-to-end proof with the runtime and writer roles`

**Acceptance:** all of Step 3 green on the integration branch.

---

## Wave 3 — purge, documentation, final proof (serial)

### Task 13: Purge command and documentation

**Files:**
- Create: `backend/market_store/purge.py`, `backend/tests/test_market_store_purge.py`
- Modify: `CLAUDE.md`, `docs/compliance/data-processing-inventory.md` (the "In-process market cache" row, line 66), `deploy/cloudrun.md` (one paragraph in the environment-variables part)

**Interfaces:** Produces `purge.main(argv: list[str] | None = None) -> int` and `python -m market_store.purge --yes`. Without `--yes` it prints what it would delete and returns 2. With it: on PostgreSQL `TRUNCATE market_price_daily, market_snapshot, market_instrument RESTART IDENTITY`; on SQLite three `DELETE`s; uses `db.writer_session()`'s engine unless `--database-url` is given; prints one JSON line `{"deleted": {"market_instrument": n, "market_snapshot": n, "market_price_daily": n}}`; a privilege error prints "purge needs the table owner; pass --database-url" and returns 1.

- [ ] **Step 1: Failing tests:**

```python
def test_purge_requires_yes(market_store_db, capsys):
    info_store.save("AAPL", {"currentPrice": 1.0}); assert purge.main([]) == 2
    assert "AAPL" in info_store.load(["AAPL"])
def test_purge_empties_the_three_tables(market_store_db, capsys):
    info_store.save("AAPL", {"currentPrice": 1.0}); assert purge.main(["--yes"]) == 0
    assert info_store.load(["AAPL"]) == {}
    assert json.loads(capsys.readouterr().out)["deleted"]["market_instrument"] == 1
```

- [ ] **Step 2: Run** → fail. **Step 3: Implement.** **Step 4: Run** → pass.
- [ ] **Step 5: Documentation.**
  - `CLAUDE.md`: add a section "Market-data store" under "Architecture & conventions" (flag, local-only, the three tables are global and outside RLS, writes only through `market_store`, no `Session` across a provider call, completed sessions only, purge command, spec path). In the "Money / FX" bullet replace "Missing rates are backfilled at startup via `fx.bulk_fetch_fx`" with "Missing rates are filled at import and at T212 finalisation via `fx.bulk_fetch_fx`".
  - `data-processing-inventory.md`: the cache row becomes "Market-data store (local edition, behind `PORTFYL_MARKET_STORE`) | quote/profile dictionaries and daily closes keyed by market symbol | PostgreSQL tables `market_*` (global, no tenant data) plus web-instance memory | Yahoo/yfinance | Durable until purged with `python -m market_store.purge --yes`; not exported; never enabled in the cloud edition until commercial rights exist."
  - `deploy/cloudrun.md`: "`PORTFYL_MARKET_STORE` must stay unset in the cloud edition; the service refuses to start with `on`."
- [ ] **Step 6: Commit and merge into `feat/market-store`.** `feat(market-store): purge command; document the store`

**Acceptance:** tests green; the three documents updated.

### Task 14: Final re-integration and verification

- [ ] **Step 1:** Merge `main` into `feat/market-store`; fix conflicts.
- [ ] **Step 2:** Fast suite on 3.12 and 3.14; PostgreSQL suite (port 55464); frontend four commands; `alembic heads` == `EXPECTED_ALEMBIC_HEAD`; `git diff --stat main...feat/market-store -- backend/requirements* frontend/package*.json` is empty.
- [ ] **Step 3: Live check, flag on** (only when no other session uses :8000/:5173): on a local database migrated to head, set `PORTFYL_MARKET_STORE=on`, run `start.bat`, log in, open the dashboard and one stock detail. Then stop the backend, start it again and reload the dashboard. Record: the log line of `portfyl.market_store` counters (`l2_hit` > 0 and `provider_fetch` == 0 on the reload when under 300 s; `stale_served` > 0 when older), response times of `/api/portfolio/summary` before and after, a screenshot. Compare `total_value` of `/api/portfolio/summary` with the flag off and on within one minute — equal to the displayed precision.
- [ ] **Step 4:** If startup fails with the preflight message, the local database user is `portfyl_runtime`: give `portfyl_market_writer` a password (`ALTER ROLE portfyl_market_writer LOGIN PASSWORD '…'` as the owner), set `MARKET_WRITER_DATABASE_URL`, repeat Step 3, and note it in the report.
- [ ] **Step 5:** Report to the founder: commands and results of Steps 2–3, the screenshot, the list of remaining raw `yf.*` call sites, and the branch name. **Do not merge to `main` and do not push.**

**Acceptance:** all checks green; the live numbers recorded. **Rollback of v1 as a whole:** set `PORTFYL_MARKET_STORE=off` (or unset) and restart; optionally `python -m market_store.purge --yes`; the migration stays.

---

## Not in this plan (each needs its own, after the founder decisions in spec §16)

Wave 2 of the spec (dividends/earnings/insider/statement snapshots, `ticker_attrs`, `jobs._next_dividend_info`), the cloud foundation (`market_request`, `market_fill`, admission caps, `pending`), and the Twelve Data wave (adapter, aliases, budget, `market_tick`, `market_daily`, seed, shadow mode).
