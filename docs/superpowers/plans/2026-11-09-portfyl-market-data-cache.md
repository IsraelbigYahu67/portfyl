# Market-data cache in PostgreSQL — implementation plan

Date: 2026-11-09 · Status: **draft, waiting for spec approval (gate G1)**

> **Scope decision 2026-11-09 (founder):** no Twelve Data yet. The first
> delivery is **local edition only**, loading data from **Shibui (primary) and
> yfinance (fallback/complement)** into the store. See §0b, which overrides the
> spec where they differ. Wave 4 (Twelve Data, cloud) waits until a plan is
> bought.
Spec: [`docs/superpowers/specs/2026-11-08-portfyl-market-data-cache-design.md`](../specs/2026-11-08-portfyl-market-data-cache-design.md)
(read it first; section numbers below such as "§7.1" refer to it).

> **For agentic workers:** execute one task at a time, in wave order, on your own
> branch or worktree (CLAUDE.md "Parallel session safety"). Each task lists the
> files it **owns**: do not edit files owned by another task in the same wave.
> Write the tests first, watch them fail, then implement. Tick the checkboxes as
> you go. A wave is done only when its "Wave exit" checks pass after re-integrating
> `main`.

**Goal.** PostgreSQL becomes the shared market-data store. Request handlers read
the database; provider calls happen in scheduled jobs and in a small,
rate-limited fill-on-miss path. The store first sits in front of yfinance (local
edition only), then in front of Twelve Data (cloud), seeded up front with a
curated universe and refreshed after each earnings report (§7.1).

**Architecture.** A new package `backend/market_store/` is the only module that
may talk to a market-data provider. It has a read API (`store.py`), a fill/claim
service (`service.py`), a cross-instance credit limiter (`budget.py`), provider
adapters that normalise into canonical shapes (`adapters/`, `shapes.py`), and job
passes (`jobs.py`) driven by Cloud Scheduler in cloud and by the existing
in-process poller in local.

**Tech.** FastAPI (sync `def` handlers), SQLAlchemy 2.0, Alembic, PostgreSQL 16
(Neon), `httpx` for Twelve Data, `yfinance` via the existing `market_data.py`
gate. No new Python dependency is needed, so the lockfiles stay untouched until
Wave 5.

---

## 0. What changed versus the spec (found while reading the code, 2026-11-09)

These are corrections or decisions the spec did not make. Each one is built into
the tasks below; items marked **(confirm)** need the founder's OK.

1. **Jobs run as `portfyl_runtime`, not a separate role.** `deploy/cloudrun.md`
   §3: `JOB_DATABASE_URL` is "the same `portfyl_runtime` role", only unpooled.
   So §5.5's "runtime has no `DELETE`, jobs own cleanup" cannot be done with
   grants. **Plan:** the runtime role gets no `DELETE`/`TRUNCATE` on any
   `market_*` table. Cleanup goes through two `SECURITY DEFINER` functions owned
   by the migration owner: `market_gc(cutoff timestamptz)` (old snapshots, budget
   rows) and `market_purge_all()` (the 30-day purge after leaving Twelve Data,
   §17). `EXECUTE` on the GC function goes to `portfyl_runtime`. The purge
   function is **not** granted; only the migration-owner credential runs it.
2. **No advisory lock around the provider call.** The runtime `DATABASE_URL` is
   the Neon **pooled** endpoint (PgBouncer transaction pooling). Session advisory
   locks do not work there. A transaction-scoped lock (`pg_try_advisory_xact_lock`,
   §6) would keep a pooled connection open during a 0.3–3 s provider call. That
   breaks the "call `database.release_connection` before slow outbound calls"
   rule. **Plan:** single-flight uses a **lease row** in `market_fetch_state`
   (`lease_until`). The fill path claims the lease with one conditional `UPDATE`,
   commits, releases the connection, calls the provider, and then writes the
   result. If the lease is already held, the request serves stale or `pending`.
   This works on both the pooled and the direct URL.
3. **`market_demand` cannot be hidden at the database level**, because the
   request path and the jobs use the same role. **Plan:** isolation is enforced
   in the application and by tests. Only `market_store/demand.py` may reference
   the table (checked by a static test), and no API response contains anything
   derived from it except freshness. **(confirm)** One aggregate side channel
   remains: a widely held instrument is hot, so its `as_of` is fresher. That shows
   "someone holds or views X" but never who. The plan accepts this.
4. **Call sites differ from §3/§12.** `broker_cash.py` makes no provider call.
   `routers/watchlists.py` does (`get_info`/`get_infos`), and so do the
   `main.py` startup FX backfill and `cache.py`, which only mentions it in a docstring.
   Analytics and alerts live in `routers/analytics.py` and `routers/alerts.py`.
   The Wave 3 task list uses the real set.
5. **New rate-limit rule needs deploy changes in the same task.**
   `rate_limit.load_rate_limit_rules` fails closed in cloud if any rule's env
   vars are missing. The per-workspace cold-fill rule `market_cold_fill` therefore
   needs `RATE_LIMIT_MARKET_COLD_FILL_LIMIT` and `…_WINDOW_SECONDS` in the
   `gcloud run deploy` command in `deploy/cloudrun.md`, all in the same commit.
6. **The answer to §16.5 is enforced in code.** At startup the cloud edition
   refuses `PORTFYL_MARKET_STORE=on` together with
   `PORTFYL_MARKET_PROVIDER=yfinance`. A persistent shared cache of Yahoo data
   therefore cannot reach cloud users by misconfiguration.
7. **Seed CLI is built in Wave 3, not Wave 4.** It is provider-agnostic, and the
   spec wants a local rehearsal with yfinance before credits are spent (§7.1).
   Wave 4 only runs it in cloud.
8. **Fast-suite compatibility.** The fast unit suite runs on in-memory SQLite.
   Every upsert uses SQLAlchemy's dialect `insert(...).on_conflict_do_update`
   (the SQLite ≥ 3.35 path supports `WHERE` and `RETURNING`). Lease and limiter
   logic is plain SQL that both dialects accept. Real concurrency is tested only
   in `tests/postgres/`.

---

## 0b. Local phase: Shibui + yfinance (decision 2026-11-09)

The store runs **only in the local edition** to prove that it works. Shibui is the
primary source because its history is longer (fundamentals since 1990,
valuation since 1993, prices since 1962). yfinance fills what Shibui does not
have. **This overrides spec §15 "Shibui stays outside the store in v1".**

**Facts about Shibui** (from `get_database_schema` and a live query on 2026-11-09):

- It covers NYSE and NASDAQ only (~10,400 symbols: stocks, US-listed ETFs,
  ADRs). All values are in USD.
- It has no FX, no indices, no intraday data, and no exchanges outside the US.
- Data is end-of-day with a ~1 trading-day lag: on Mon 2026-11-09 the last day
  was Fri 2026-11-06.
- **200 rows per query at most.**
- Prices are split-adjusted but not dividend-adjusted, the same basis the store
  uses.
- Days of price history per symbol: AAPL 11,567 (from 1980-12-12), KO 16,320
  (from 1962-01-02), MSFT 10,243, NVDA 6,992, O 8,068.

### Data sets, sources and refresh

"US" means a symbol Shibui covers (NYSE/NASDAQ). "Other" means Prague, Xetra,
LSE, UCITS ETFs, indices and FX.

| # | Data | US: primary → fallback | Other | Refresh (local) | Store as |
|---|---|---|---|---|---|
| D1 | Profile: name, GICS sector/industry, description, country, website, employees, ISIN, IPO date, logo | Shibui `general_info` → yf `.info` | yf `.info` | 90 d | `market_instrument` columns |
| D2 | Latest price: price, change, % change, previous close, market state, 52-week range | **yf** (Shibui is EOD, 1 day late) | yf | held: every 15 min while the exchange is open; on Stock detail open if > 5 min old | `market_price_latest` |
| D3 | Daily price history | Shibui `stock_quotes` (from 1962) → yf | yf | daily: append the new day(s) for all held symbols in one batched query (≤ 200 rows each); the yf close fills today until Shibui has it, then Shibui overwrites | `market_price_daily` (`source` per row) |
| D4 | FX rates (`USD/CZK` …) | — | yf | like D2/D3 | `market_price_*` with `kind='fx'` |
| D5 | Benchmarks and indices (S&P 500, …) | — | yf | daily | `market_price_daily` with `kind='index'` |
| D6 | Statements, quarterly and annual: income, balance sheet, cash flow (since 1990) | Shibui `fundamentals_quarterly` / `fundamentals_yearly` → yf (~4 y / 5 q only) | yf | after each report (D11 dates) +1/+3/+7 d; safety net 120 d | snapshots `income_*`, `balance_*`, `cashflow_*` |
| D7 | Quarterly ratios: margins, ROE, ROIC, D/E, YoY growth, DPS | Shibui `fundamentals_derived_quarterly` → yf `.info` | yf `.info` | with D6 | snapshot `ratios_quarterly` |
| D8 | Valuation history (P/E, EV/EBITDA, P/S, P/FCF, P/B; feeds the 5-year average P/E) | Shibui `valuation` + `fundamentals_derived_daily` (from 1993) | not available (as today) | weekly append | snapshot `valuation_history`: **daily for the last 2 years, weekly before that** |
| D9 | Current valuation: market cap, EV, P/B, trailing/operating P/E, dividend yield, payout | latest Shibui row (D8), recomputed with the D2 price (`derived.py`) | yf `.info` | with D2 (no fetch, computed) | computed on read |
| D10 | Dividends: per payment (ex-date, amount) | **yf** (Shibui has no events) | yf | after each report; safety net 30 d (payers) / 90 d | `market_dividend_event` |
| D10b | Dividends: annual/quarterly DPS since 1990 | Shibui (D7 `dividends_per_share`) → yf | yf | with D6 | inside `ratios_quarterly` |
| D11 | Splits | yf | yf | split anomaly + 90 d | `market_split_event` |
| D12 | Earnings history: EPS actual, estimate, surprise, report date | Shibui `earnings_quarterly` → yf | yf | after each report | snapshot `earnings_history` |
| D13 | Next earnings date | **yf** `calendar` (Shibui has only past dates) | yf | daily for held symbols, otherwise 7 d | snapshot `earnings_dates` |
| D14 | Analysts: target price, EPS estimates, forward P/E, forward PEG | Shibui `analyst_estimates` → yf | yf | 7 d | snapshot `estimates` |
| D14b | Analysts: recommendation, number of analysts, target low/high | yf only | yf | 7 d | snapshot `recommendations` |
| D15 | Ownership: % insiders, % institutions, short % of float, float shares | Shibui `ownership_stats` → yf | yf | 7 d | snapshot `ownership` |
| D16 | Insider transactions, 13D/13G stakes, SEC filings list | Shibui (as today) | — | on open only, 24 h | snapshots `insider_transactions`, `beneficial_ownership`, `sec_filings` |
| — | Politician trades, Shibui screener | unchanged, outside the store for now | | | |

The source priority is one table in `market_store/sources.py`
(`{kind: [ "shibui", "yfinance" ]}`) plus a coverage test
(`shibui_coverage.covers(symbol)` → `general_info` lookup, cached as an alias
row). Each stored row or snapshot records its `source`, so the UI can show it
and the equivalence tests can compare like with like.

### Shibui load and politeness

- Seed cost per US symbol, in Shibui queries:
  - D3 prices: rows ÷ 200, so 35–82 (≈ 55 on average);
  - D1 1, D6 2, D7 1, D8 ≈ 10, D12 1, D14 + D15 1;
  - total **≈ 70 queries**.
- For 300 US symbols that is ≈ 21,000 queries, about **6 hours** at one query at
  a time (~1 s each). That is a one-off overnight run, resumable via
  `market_fetch_state`.
- Daily upkeep is small because queries are batched (`WHERE ticker IN (…)`):
  - D3: one query per 200 symbol-days;
  - D8: one query per symbol per week;
  - D6/D7/D12: only after reports.
- Limit: `PORTFYL_SHIBUI_MAX_CONCURRENCY=1` and `…_MIN_INTERVAL_MS=500`,
  enforced in `adapters/shibui.py`. Shibui is a free public service with no
  stated quota. Being polite costs nothing locally, and a run that hits errors
  backs off.
- If 6 hours is too long: take D3 history from yfinance (one call per symbol)
  and use Shibui only to cross-check. **Open question for the founder.** Whether
  yfinance's `period="max"` reaches as far back could not be checked from the
  cloud container (Yahoo is blocked there). Task 3.6 measures it locally.

### Refresh cadence (local)

Local runs on the owner's PC and PostgreSQL, so frequency costs no money. It is
limited only by Yahoo throttling and politeness to Shibui:

- `market_prices`: every 15 min, 08:00–22:30 Prague time, weekdays.
- `market_refresh`: every 5 min.
- `market_shibui_daily`: 14:00 Prague time. Shibui posts the previous US day
  overnight, and this run appends D3/D8 for held symbols.
- `market_earnings_watch`: daily, from D13 dates. No `/earnings_calendar` without
  Twelve Data.
- `market_cache_gc`: daily.

All of them are in-process pollers (`main.py`), not Cloud Scheduler.

### Disk (local)

About 1.3 MB per US symbol (prices ~1.2 MB, everything else compressed
~0.1 MB). 300 symbols ≈ 0.4 GB; 1,000 ≈ 1.3 GB.

### What this changes in the waves below

- Task 2A adds `market_store/sources.py`, `market_store/shibui_coverage.py` and
  `market_store/adapters/shibui.py`. The Shibui adapter reuses `shibui_client.query`
  and `_SHIBUI_TICKER_RE`, and pages D3/D8 in ≤ 200-row windows by date range.
  Canonical shapes get the extra kinds listed above.
- Migration `0026` adds the snapshot kinds `ratios_quarterly`,
  `valuation_history`, `earnings_history`, `ownership`, `beneficial_ownership`
  and `sec_filings` to the `CHECK` constraint.
- Task 2B adds the `market_shibui_daily` pass. Cloud Scheduler entries are
  **not** added in this phase. The `/internal/jobs/market_*` endpoints are
  built later with Wave 4.
- Task 3.1: the `/market/shibui/*` endpoints, `_shibui_fundamentals` and
  `_shibui_ownership_stats` read through the store. Valuation keeps the
  **5-year average P/E**, now computed from the stored D8 series.
- Task 3.6: the seed loads D1–D15 from Shibui first and yfinance second.
  `--dry-run` prints the number of Shibui queries and yf calls and the estimated
  time.
- The cloud guard (§0.6) stays: the cloud edition refuses to start with the
  store on and no Twelve Data provider.

---

## 1. Gates (decisions and outside inputs)

| Gate | Owner | Blocks | Default if unanswered |
|---|---|---|---|
| **G1** Spec + this plan approved | founder | Wave 1 start | — (hard stop) |
| **G2** §16.3: is "price as of yesterday's close" OK for EOD-only exchanges (Prague, Xetra, LSE on Grow)? | founder | Task 2C copy | Yes; badge reads "close dd.mm." |
| **G3** §16.4: ETFs/funds, profile/statistics or not? | founder | Task 4.1 scope | Price, history, dividends and `/profile` if it answers; statistics shown as "not available" |
| **G4** §16.6: seed universe list (several hundred) | founder | Task 4.5 (cloud seed run) | Draft list generated in Task 3.6 for approval |
| **G5** Twelve Data support answers: overage billing, storage period, 2-minute polling OK, `/earnings_calendar` plan and non-US coverage, `/quote` batch size | founder emails, Claude drafts | Task 4.6 (cloud flip) | Do not flip |
| **G6** Venture plan bought, key stored as Secret Manager secret `portfyl-twelvedata-api-key` | founder | Tasks 4.1 live contract test, 4.4, 4.5 | Fixtures and `demo` key only |
| **G7** `docs/compliance/data-processing-inventory.md` + privacy notice list Twelve Data as a processor | Claude drafts, founder approves | Task 4.6 | Do not flip |
| **G8** Workstream A commercial market-data rights | founder | Task 4.6 | Do not flip |

---

## 2. Wave map and file ownership

| Wave | Task | Parallel? | Owns (only this task edits these) |
|---|---|---|---|
| 1 | 1.1 Models + migration + grants | single session (hotspot) | `backend/market_store/__init__.py`, `backend/market_store/models.py`, `backend/models.py` (one import line), `backend/alembic/versions/0026_market_data_store.py`, `backend/database.py` (`EXPECTED_ALEMBIC_HEAD`) |
| 1 | 1.2 Schema/isolation tests + docs | same session, after 1.1 | `backend/tests/postgres/test_market_store_schema.py`, `backend/tests/test_market_store_models.py`, `docs/security/tenant-isolation-matrix.md` |
| 2 | 2.0 Contracts (first commit of 2A, merged before 2B starts coding) | short, blocking | `backend/market_store/contracts.py` |
| 2 | 2A Store core + yfinance adapter + resolver | parallel | `market_store/{config,symbols,shapes,freshness,derived,store,service,demand}.py`, `market_store/adapters/{__init__,base,yfinance}.py`, matching `backend/tests/test_market_store_*.py` |
| 2 | 2B Budget + jobs + scheduling | parallel | `market_store/{budget,calendar,jobs}.py`, `backend/routers/internal_jobs.py`, `deploy/operations.json`, `backend/main.py` (`_JOB_MAX_AGES`, local pollers only), `backend/rate_limit.py`, `deploy/cloudrun.md` (rate-limit env vars only), `backend/tests/test_market_budget.py`, `backend/tests/test_market_jobs.py`, `backend/tests/postgres/test_market_budget_postgres.py` |
| 2 | 2C Frontend freshness UI | parallel | `frontend/src/components/market/*`, `frontend/src/hooks/usePendingRefetch.js`, `frontend/src/i18n/messages/*.js` (new keys only), `DESIGN.md` (only if the look changes) |
| 3 | 3.1 `routers/market.py` | sequential | `backend/routers/market.py`, `backend/tests/test_market.py` |
| 3 | 3.2 `routers/portfolio.py` + import/sync hooks | after 3.1 | `backend/routers/portfolio.py`, `backend/ledger_import.py`, `backend/t212_sync.py`, their tests |
| 3 | 3.3 analytics, FX, dividends, jobs, alerts, watchlists | after 3.2 | `backend/routers/analytics.py`, `backend/fx.py`, `backend/main.py` (startup FX only), `backend/dividend_growth.py`, `backend/jobs.py`, `backend/routers/alerts.py`, `backend/routers/watchlists.py`, their tests |
| 3 | 3.4 Frontend wiring | after 3.1–3.3 merged | pages/components that render prices, `frontend/src/api.js` only if a new prefix is needed |
| 3 | 3.5 Equivalence + local rollout | after 3.4 | `backend/tests/test_market_store_equivalence.py`, `start.bat` (flag) |
| 3 | 3.6 Seed CLI + local rehearsal | parallel with 3.4/3.5 | `backend/market_store/seed.py`, `backend/market_store/universe/`, `backend/tests/test_market_seed.py` |
| 4 | 4.1 Twelve Data adapter | parallel with 4.2 | `market_store/adapters/twelvedata.py`, `backend/tests/fixtures/twelvedata/`, `backend/tests/test_twelvedata_adapter.py` |
| 4 | 4.2 Symbol mapping `SYMBOL:MIC` | parallel with 4.1 | `market_store/mic.py`, `backend/tests/test_market_mic.py` |
| 4 | 4.3 Earnings-calendar watch on real data | after 4.1 | `market_store/earnings.py`, its tests |
| 4 | 4.4 Shadow mode | after 4.1–4.3 | `market_store/shadow.py`, `backend/scripts/market_shadow_report.py` |
| 4 | 4.5 Cloud seed run | after 4.4, G4, G6 | `deploy/run-market-seed.ps1`, `deploy/cloudrun.md` (seed section) |
| 4 | 4.6 Cloud flip + monitoring + compliance | after G5, G7, G8 | `deploy/cloudrun.md` (Twelve Data section), `deploy/operations.json`, `backend/main.py` (`/health` market subsystem), `docs/compliance/*`, `docs/legal/*`, `docs/operations/market-data-purge.md` |
| 5 | 5.1 Remove flag + old paths | single session (lockfile hotspot) | everything that still has `if not store_enabled`, `market_data.py`, `cache.py` users, `requirements*.txt/.lock` only if yfinance leaves the cloud image |

Rough size: Wave 1 ≈ 1 session; Wave 2 ≈ 3 parallel sessions of 1–2 days;
Wave 3 ≈ 4–5 sessions in sequence; Wave 4 ≈ 3–4 sessions plus waiting time for
G5/G6; Wave 5 ≈ 1 session.

---

## 3. Wave 1 — schema (one session, owns the migration hotspot)

### Task 1.1 — Models, migration `0026_market_data_store`, grants

**Files:** create `backend/market_store/__init__.py` (empty) and
`backend/market_store/models.py`. Add one line at the bottom of `backend/models.py`:
`from market_store import models as _market_models  # noqa: F401,E402`, so that
`alembic/env.py` (which imports `models`) and the schema tests see the tables.
Create `backend/alembic/versions/0026_market_data_store.py` and set
`EXPECTED_ALEMBIC_HEAD = "0026_market_data_store"` in `backend/database.py`.

- [ ] **Step 1: test first.** `backend/tests/test_market_store_models.py`:
  every table in the list below is in `Base.metadata.tables`, and none of them
  has a column named `workspace_id`, `user_id`, `portfolio_id` or `owner_id`.
  Run: `cd backend && python -m pytest tests/test_market_store_models.py -v`.
  Expected: FAIL (import error).
- [ ] **Step 2: models.** Use `database.Base`, a `BigInteger` identity primary key
  (`id`) and `DateTime(timezone=True)` everywhere. Tables and columns as in spec
  §5, plus these additions:

  | Table | Key | Additions to spec §5 |
  |---|---|---|
  | `market_instrument` | `id`, `symbol_key` UNIQUE | `CHECK kind IN ('stock','etf','fund','index','fx','crypto')`, `CHECK status IN ('active','delisted','unresolvable')`, `CHECK data_latency IN ('realtime','delayed','eod')`, `history_basis_split_count int default 0` (detects a new split) |
  | `market_instrument_alias` | `alias` PK | `alias_kind` CHECK in `('broker','yahoo','twelvedata','isin','bare')`; index on `instrument_id` |
  | `market_price_daily` | (`instrument_id`, `trade_date`) | `close` NOT NULL, other OHLCV nullable |
  | `market_price_latest` | `instrument_id` | `next_refresh_after timestamptz` (makes the hot pass a plain indexed query) |
  | `market_dividend_event` | (`instrument_id`, `ex_date`) | `pay_date` nullable |
  | `market_split_event` | (`instrument_id`, `split_date`) | — |
  | `market_snapshot` | (`instrument_id`, `kind`) | `CHECK kind IN (…spec §5.3 list…)`, `payload jsonb NOT NULL`, `latest_period text` (for "stop when the period changed", §7.1); partial index `ON (next_refresh_after) WHERE next_refresh_after IS NOT NULL` |
  | `market_fetch_state` | (`instrument_id`, `kind`) | **`lease_until timestamptz`**, `priority smallint default 0` (0 = background, 1 = stale read, 2 = new import/interactive), `post_report_checks smallint default 0` |
  | `market_demand` | `instrument_id` | as in spec |
  | `market_budget` | `minute_bucket` | `credits_used int NOT NULL default 0`, `cap int NOT NULL` |
  | `market_provider_state` | `provider` PK (text) | one row per provider instead of a single row, so shadow mode can track both |
  | `market_usage_daily` | (`day`, `provider`, `endpoint`) | `provider` added to the key |

  Use JSONB on PostgreSQL and JSON on SQLite: `JSON().with_variant(JSONB, "postgresql")`.
- [ ] **Step 3: migration.** Revision `0026_market_data_store`, down_revision
  `0025_stripe_billing`. Add tables only, so older running instances keep
  working. Then:

  ```python
  RUNTIME_RW = ["market_instrument", "market_instrument_alias", "market_price_daily",
                "market_price_latest", "market_dividend_event", "market_split_event",
                "market_snapshot", "market_fetch_state", "market_demand",
                "market_budget", "market_provider_state", "market_usage_daily"]
  for t in RUNTIME_RW:
      op.execute(f"GRANT SELECT, INSERT, UPDATE ON TABLE {t} TO portfyl_runtime")
  op.execute("GRANT USAGE, SELECT ON SEQUENCE market_instrument_id_seq TO portfyl_runtime")

  op.execute("""
  CREATE FUNCTION market_gc(cutoff timestamptz) RETURNS integer
  LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
  DECLARE n integer := 0; k integer;
  BEGIN
    DELETE FROM market_snapshot s USING market_demand d
     WHERE d.instrument_id = s.instrument_id
       AND d.held_flag = false
       AND coalesce(d.last_viewed_at, 'epoch') < cutoff;
    GET DIAGNOSTICS k = ROW_COUNT; n := n + k;
    DELETE FROM market_budget WHERE minute_bucket < now() - interval '2 days';
    GET DIAGNOSTICS k = ROW_COUNT; n := n + k;
    RETURN n;
  END $$;
  REVOKE ALL ON FUNCTION market_gc(timestamptz) FROM PUBLIC;
  GRANT EXECUTE ON FUNCTION market_gc(timestamptz) TO portfyl_runtime;
  """)
  # market_purge_all(): TRUNCATE every market_* table. Owner only, no grant.
  ```

  `downgrade()` drops both functions and the tables in reverse FK order.
- [ ] **Step 4:** run the fast test (PASS) and the migration on a disposable
  database:
  `docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait`, then
  `cd backend && alembic upgrade head && alembic heads`. Expected: exactly one head,
  `0026_market_data_store (head)`, equal to `EXPECTED_ALEMBIC_HEAD`.
- [ ] **Step 5: commit.** `feat(market-store): add global market-data tables (0026)`

### Task 1.2 — PostgreSQL schema and isolation tests, docs

**Files:** `backend/tests/postgres/test_market_store_schema.py`,
`docs/security/tenant-isolation-matrix.md`.

- [ ] Tests (as the real `portfyl_runtime` role, using the existing
  `runtime_session` fixture pattern from `tests/postgres/test_runtime_role.py`):
  1. no `market_*` table has a tenant column (query `information_schema.columns`);
  2. no `market_*` table has RLS enabled (this exception is on purpose and is
     documented);
  3. runtime can `SELECT/INSERT/UPDATE` `market_instrument`;
  4. runtime `DELETE FROM market_snapshot` and `TRUNCATE market_budget` raise
     `InsufficientPrivilege`;
  5. runtime `SELECT market_gc(now())` works and deletes only unheld, unviewed
     snapshots;
  6. runtime cannot execute `market_purge_all()`;
  7. `alembic downgrade 0025_stripe_billing && alembic upgrade head` round-trips.
- [ ] Add a "Global reference data (no tenant columns, no RLS)" section to the
  matrix doc. List the 12 tables, the reason (public data, no tenant column), the
  test file, and the `market_demand` rule from §0.3.
- [ ] `cd backend && python -m pytest tests/postgres/ -v` (the whole gate suite,
  because the head changed). Commit:
  `test(market-store): runtime grants and no-tenant-column guarantees`.

**Wave 1 exit:** rebase on `main`; `alembic heads` = `EXPECTED_ALEMBIC_HEAD`; fast
suite + postgres suite green; backend starts against the migrated DB
(`assert_alembic_head` passes). Merge to `main` before Wave 2 branches are cut.

---

## 4. Wave 2 — core, jobs, UI (three parallel sessions)

### Task 2.0 — Contracts (blocking, ~1 hour, done by the 2A session)

`backend/market_store/contracts.py`. Only types, no logic, so 2A and 2B can code
against the same interfaces:

```python
@dataclass(frozen=True)
class Meta:
    as_of: datetime | None        # provider timestamp of the value
    fetched_at: datetime | None   # when we stored it
    stale: bool
    pending: bool                 # no data yet, a fill is queued
    source: str | None            # "yfinance" | "twelvedata" | "shibui"

@dataclass(frozen=True)
class Result(Generic[T]):
    data: T | None
    meta: Meta

class Priority(IntEnum):
    BACKGROUND = 0; STALE_READ = 1; INTERACTIVE = 2

class Budget(Protocol):
    def reserve(self, db, provider: str, credits: int, *, interactive: bool) -> bool: ...
    def settle(self, db, provider: str, reserved: int, actual: int | None) -> None: ...
    def cooling_down(self, db, provider: str) -> bool: ...
    def note_429(self, db, provider: str) -> None: ...

class ProviderAdapter(Protocol):
    name: str
    def cost(self, endpoint: str, n_symbols: int = 1) -> int: ...
    def quotes(self, symbols: list[str]) -> dict[str, "shapes.Quote"]: ...
    def history(self, symbol: str, start: date | None) -> list["shapes.DailyBar"]: ...
    def profile(self, symbol: str) -> "shapes.Profile | None": ...
    def statistics(self, symbol: str) -> "shapes.Statistics | None": ...
    def dividends(self, symbol: str) -> list["shapes.DividendEvent"]: ...
    def splits(self, symbol: str) -> list["shapes.SplitEvent"]: ...
    def statements(self, symbol: str, kind: str) -> "shapes.Statements | None": ...
    def earnings_dates(self, symbol: str) -> "shapes.EarningsDates | None": ...
    def earnings_calendar(self, day_from: date, day_to: date) -> list["shapes.Report"]: ...
    def search(self, query: str) -> list["shapes.SymbolMatch"]: ...

class NullBudget:  # tests: always allows
    ...
```

Merge 2.0 to `main` first. 2B rebases on it before writing `budget.py`.

### Task 2A — Store core, resolver, canonical shapes, yfinance adapter

**Owns:** `market_store/{config,symbols,shapes,freshness,derived,store,service,demand}.py`,
`market_store/adapters/{__init__,base,yfinance}.py`, `tests/test_market_store_*.py`.

- [ ] **config.py**: `MarketStoreConfig.from_env(env)` reads
  `PORTFYL_MARKET_STORE` (`on|off`, default `off`), `PORTFYL_MARKET_PROVIDER`
  (`yfinance|twelvedata`, default `yfinance`), `PORTFYL_MARKET_PLAN_CREDITS_PER_MIN`
  (default 610), `…_CAP_FRACTION` (0.8), `…_INTERACTIVE_RESERVE` (0.3),
  `…_HOT_INTERVAL_SECONDS` (120), `…_FILL_TIMEOUT_SECONDS` (3), the TTLs in
  the freshness table below, and `…_SPLIT_ANOMALY_PCT` (15). It fails closed on
  bad values. **Rule from §0.6:** `edition=cloud`, store `on` and provider
  `yfinance` together raise `RuntimeError` at import, with the same error style
  as `rate_limit._require_positive_int`. Tests: every bad value; the cloud +
  yfinance refusal; local + yfinance allowed.
- [ ] **shapes.py**: canonical, provider-neutral `TypedDict`s with
  `SCHEMA_VER = {kind: int}`. Build them from what the consumers read today.
  The full list of `.info` keys used in `routers/*.py`, `dividend_growth.py` and
  `jobs.py` (grep 2026-11-09):
  - `Quote`: price, previous_close, change, percent_change, week52_low/high,
    volume, average_volume, currency, is_market_open, quote_time, is_eod,
    exchange, data_delay_minutes
    (← `regularMarketPrice/currentPrice/previousClose/regularMarketChange*`,
    `fiftyTwoWeek*`, `marketState`, `exchangeDataDelayedBy`, `regularMarketTime`).
  - `Profile`: name, short_name, kind, sector, industry, country, website,
    description, employees, exchange, currency, legal_type, category, region.
  - `Statistics`: shares_outstanding, float_shares, market_cap_reported,
    enterprise_value, ebitda, total_cash, total_debt, total_revenue,
    free_cashflow, trailing_eps, forward_eps, trailing_pe_reported, forward_pe,
    peg, trailing_peg, price_to_book, price_to_sales, ev_to_revenue,
    ev_to_ebitda, debt_to_equity, current_ratio, quick_ratio, gross/operating/
    profit_margins, roe, roa, beta, payout_ratio, dividend_rate,
    trailing_annual_dividend_rate, ex_dividend_date, dividend_date,
    fifty_day_avg, two_hundred_day_avg, held_pct_insiders,
    held_pct_institutions, short_ratio, most_recent_quarter,
    last_fiscal_year_end, latest_period.
  - `AnalystView` (kept on yfinance/Shibui, §7): target mean/median/low/high,
    recommendation key/mean, number_of_opinions.
  - `Statements`: `{"periods": [{"end": "2025-12-31", "fiscal": "FY2025",
    "values": {"revenue": …, "net_income": …, "fcf": …}}]}`. Value keys match
    what `_metric_block` / `_shibui_metric_block` consume today.
  - `DailyBar`, `DividendEvent`, `SplitEvent`, `EarningsDates`
    (`next_date`, `last_date`, `last_period`), `Report`, `SymbolMatch`.

  The yfinance adapter must fill every field the current UI shows. Write a test
  for each shape with a recorded yfinance `info` fixture (`tests/fixtures/`).
- [ ] **symbols.py (resolver)**: `resolve(db, raw: str) -> Instrument | None` and
  `resolve_many`. Order of lookup: exact alias → normalise (T212 forms through
  `t212_sync._normalize_t212_ticker` rules, upper-case, `ticker_map.TICKER_FALLBACKS`)
  → Yahoo suffix to MIC table (`.L`→`XLON`, `.DE`→`XETR`, `.PR`→`XPRA`,
  `.AS`→`XAMS`, `.PA`→`XPAR`, `.MI`→`XMIL`, `.SW`→`XSWX`, `.TO`→`XTSE`, no
  suffix → US, MIC filled later by search) → `=X` pairs to `kind='fx'`
  (`USDCZK=X` → `USD/CZK`) → otherwise `None`. Free text **never** creates an
  instrument here. Creation needs a `SymbolMatch` from the adapter's `search()`
  (validation, §6). Store every form seen as an alias. If the adapter can't
  match, set `status='unresolvable'`. Tests: T212, IBKR, Degiro ISIN, FX and
  `COPM.L→COPM.AS` cases; the same input twice creates one instrument.
- [ ] **freshness.py** (pure functions, no DB). Default policy:

  | kind | fresh for | stale-but-served for | trigger besides TTL |
  |---|---|---|---|
  | quote, hot tier, exchange open | `max(120 s, hot_count ÷ job_cpm)` | 7 days | — |
  | quote, otherwise | until next after-close pass | 7 days | — |
  | history | append daily; full refetch only on a new split | forever | split anomaly |
  | profile | 90 d | forever | — |
  | statistics / statements | 120 d safety net | forever | earnings report +1/+3/+7 d (§7.1) |
  | dividends | 30 d payers / 90 d non-payers | forever | earnings report |
  | splits | 90 d | forever | `previous_close` vs last stored close > 15 % |
  | earnings_dates | set by the daily watch | forever | — |
  | negative (`empty`/`unsupported`) | 24 h, doubling up to 7 d | — | — |

  Functions: `is_fresh(kind, fetched_at, now, ctx)`,
  `next_refresh_after(kind, fetched_at, ctx)` and `backoff(attempts)`. Tests use
  a frozen clock and cover each row.
- [ ] **derived.py**: market cap = price × shares_outstanding; trailing P/E =
  price ÷ TTM EPS (EPS ≤ 0 or missing → `None`); dividend yield = sum of
  dividends in the last 365 days ÷ price; 52-week range from `market_price_daily`.
  Display only: valuation keeps the **5-year average P/E** from Shibui (CLAUDE.md).
  Each formula gets tests, including missing inputs → `None` and a currency
  mismatch → `None`.
- [ ] **store.py (read API, request path, no provider call)**:

  ```python
  def get_quotes(db, symbols: list[str]) -> dict[str, Result[Quote]]   # one SQL query
  def get_history(db, symbol, start: date, end: date | None = None) -> Result[list[DailyBar]]
  def get_profile(db, symbol) -> Result[Profile]
  def get_snapshot(db, symbol, kind) -> Result[dict]
  def get_dividends(db, symbol, since: date | None = None) -> Result[list[DividendEvent]]
  def get_fx(db, pair: str, start: date, end: date | None = None) -> Result[list[DailyBar]]
  def ensure_instruments(db, raw_symbols: list[str], *, priority=Priority.INTERACTIVE,
                         cap: int = 200) -> None
  ```

  Behaviour: fresh → return. Stale → return with `stale=True`, and set
  `next_refresh_after = now()` and `priority = max(priority, 1)` (one `UPDATE`,
  only if not already due). Miss → hand over to `service.fill_on_miss`. Add an L1
  `BoundedTTLCache` (45 s, 2048 entries, keyed by symbol and kind) in front, for
  bursts on one instance. Tests: fresh, stale, miss, batch of 30 → 1 query (count
  with a SQLAlchemy event listener).
- [ ] **service.py (fill-on-miss and lease)**:

  ```sql
  -- claim (one statement, both dialects):
  INSERT INTO market_fetch_state (instrument_id, kind, status, attempts, lease_until, last_attempt_at)
  VALUES (:i, :k, 'ok', 0, :now + interval '10 seconds', :now)
  ON CONFLICT (instrument_id, kind) DO UPDATE
     SET lease_until = excluded.lease_until, last_attempt_at = excluded.last_attempt_at
   WHERE market_fetch_state.lease_until IS NULL OR market_fetch_state.lease_until < :now
  RETURNING instrument_id;
  ```

  (In SQLite, write the interval as a bound parameter `:lease_until` computed in
  Python.) Steps: symbol validation (resolver; an unknown symbol calls
  `adapter.search` only after the cold-fill limit) → per-workspace
  `consume_rate_limit(rule=market_cold_fill)` → `budget.reserve(interactive=True)`
  → claim lease → `db.commit()` + `database.release_connection(db)` → adapter
  call bounded by `FILL_TIMEOUT_SECONDS` (worker thread, the same pattern as
  `market_data.run_bounded`) → upsert → clear lease → `budget.settle`. On a
  timeout, 429, refused budget or lost lease, return `Result(None, pending=True)`
  and leave `priority=2`, so the next `market_refresh` tick picks it up.
  Tests: lost lease → no adapter call; budget refused → pending; timeout →
  pending, no row written; `empty` → negative cache row with backoff.
- [ ] **demand.py**: `touch_view(db, instrument_id)` (upsert `last_viewed_at`,
  at most once per instrument per 10 minutes per process) and
  `held_set_update(db, instrument_ids)`. Static test
  `tests/test_market_store_demand_isolation.py`: grep `backend/` (except
  `market_store/demand.py`, `market_store/jobs.py` and migrations) for
  `market_demand` and fail on any hit.
- [ ] **adapters/yfinance.py**: wraps `market_data.get_infos`, `market_data.download`
  and `market_data.ticker(...).dividends/.splits/.calendar`, so the existing
  gate, timeout and stall protections stay. It only maps into `shapes`. `cost()`
  returns 0. `search()` uses the same logic as `/market/search` today. Tests
  use recorded fixtures (no network).
- [ ] Commit per module (`feat(market-store): …`). Run `python -m pytest tests/ --ignore=tests/postgres -v`.

### Task 2B — Credit limiter, job passes, scheduling

**Owns:** `market_store/{budget,calendar,jobs}.py`, `routers/internal_jobs.py`,
`deploy/operations.json`, `main.py` (`_JOB_MAX_AGES` and the local poller block
only), `rate_limit.py`, `deploy/cloudrun.md` (rate-limit env vars only), tests.

- [ ] **budget.py**: implements `contracts.Budget`.

  ```sql
  INSERT INTO market_budget (minute_bucket, credits_used, cap)
  VALUES (date_trunc('minute', :now), :c, :cap)
  ON CONFLICT (minute_bucket) DO UPDATE
     SET credits_used = market_budget.credits_used + excluded.credits_used
   WHERE market_budget.credits_used + excluded.credits_used <= :limit
  RETURNING credits_used;
  ```

  `cap = plan × 0.8`. The limit is `cap` for interactive calls and
  `cap × (1 − 0.3)` for jobs. No row returned → refused. In Python, compute the
  minute bucket for SQLite. `settle()` corrects the reservation with the
  `api-credits-used` header value when it is known. `note_429()` sets
  `market_provider_state.cooldown_until` to the next minute boundary, and
  `reserve()` refuses while it is in the future. After 5 consecutive 5xx the
  circuit breaker opens for 5 minutes. Every call adds to `market_usage_daily`
  (calls, credits, hits, misses, errors). Tests: arithmetic at the boundaries,
  the job share stopping at 70 %, cooldown, and the breaker.
  `tests/postgres/test_market_budget_postgres.py`: 20 threads reserve 30 credits
  each against cap 488 → exactly 16 succeed, `credits_used` = 480.
- [ ] **calendar.py**: per-MIC session table (tz, open, close; weekdays only;
  holidays not modelled in v1, and a holiday shows up as "price unchanged" plus
  `is_market_open=false` from the quote). Data latency per MIC for the plan
  (`XNAS/XNYS` realtime; `XPRA`, `XETR`, `XLON` eod on Venture, to be confirmed
  in G5). Tests use fixed instants around DST changes.
- [ ] **jobs.py**: pass functions with the existing signature
  `async def pass_fn(db) -> list[event]`, called through `_run_job` and
  `run_on_private_loop`, like the other jobs. Their bodies are sync, and each
  adapter call is preceded by `release_connection`.
  1. `market_demand_pass`: iterates workspaces exactly like the dividends job
     (sets `portfyl.workspace_id` per workspace, reads only the **distinct set of
     open-position tickers**), then outside the workspace loop:
     `ensure_instruments`, `held_set_update`, tier =
     `hot` if held by a workspace with an `auth_sessions` row active in 7 days,
     or `last_viewed_at` < 24 h; else `warm` if held; else `cold`. Test with two
     workspaces: the pass writes no workspace id anywhere.
  2. `market_prices_pass`: `job_budget = limit − used this minute`; selects hot
     instruments whose exchange is open and `next_refresh_after <= now`, oldest
     first, `LIMIT job_budget`. Then held instruments whose exchange closed since
     their last quote (the after-close pass). Batches `adapter.quotes` (batch size
     from config, falling back to single calls if the provider rejects a batch),
     upserts `market_price_latest`, and appends `market_price_daily` when
     `is_eod` or after close. **Split anomaly:** if `previous_close` differs from
     the last stored close by more than 15 %, mark `splits` and `history` due with
     priority 2.
  3. `market_refresh_pass`: drains `market_fetch_state`/`market_snapshot` rows
     with `next_refresh_after <= now`, ordered by `priority DESC,
     next_refresh_after`, until the job budget for this minute is used. It also
     handles the bounded runtime (stops at 240 s, so it finishes inside the
     300 s attempt deadline). Each item claims the lease first.
  4. `market_earnings_watch_pass`: one `adapter.earnings_calendar(yesterday,
     today)`. If it returns 1,200 records, it splits by country. It matches by
     alias, sets `post_report_checks = 3`, and marks `statistics`, `dividends`,
     `earnings_dates` and provider-sourced statements due at +1 d. The refresh
     pass then schedules +3 d and +7 d, and stops early once `latest_period`
     changes.
  5. `market_cache_gc_pass`: `SELECT market_gc(now() - interval '180 days')`;
     downgrade tiers with no views or holdings.
- [ ] **internal_jobs.py**: five endpoints (`/internal/jobs/market_demand`,
  `market_prices`, `market_refresh`, `market_earnings_watch`, `market_cache_gc`)
  copied from `run_dividends_job`. Each one returns `{"skipped": "store off"}`
  when the flag is off, without a provider call. Extend `tests/test_internal_jobs.py`
  (auth required, lock skip, flag off).
- [ ] **operations.json** (UTC):

  ```json
  {"name": "market_demand",         "schedule": "11 2 * * *"},
  {"name": "market_prices",         "schedule": "* 6-21 * * 1-5"},
  {"name": "market_refresh",        "schedule": "*/5 * * * *"},
  {"name": "market_earnings_watch", "schedule": "37 22 * * 1-5"},
  {"name": "market_cache_gc",       "schedule": "23 3 * * *"}
  ```

  `market_prices` covers the EU open (06:00 UTC in summer) through the US
  after-close pass (21:xx UTC in winter). Outside those hours, nothing calls the
  service, so the instance can scale to zero.
  **Cloud scheduler entries are applied only in Task 4.6**. Until then the
  entries are present but the endpoints no-op (flag off), so applying
  `operations.json` early costs nothing.
- [ ] **main.py**: in `_JOB_MAX_AGES`, cloud only: `market_refresh` 30 min,
  `market_demand` 26 h, `market_earnings_watch` 4 d (weekends),
  `market_cache_gc` 26 h, `market_prices` 3 d 1 h (weekends; real price age is
  tracked by the market health subsystem in Task 4.6). These are registered
  **only when the store is on**, or `/health` would report degraded during
  Waves 2–3. Local edition: when the store is on, `_start_background_pollers`
  adds the same five passes with intervals 60 s / 300 s / 24 h / 24 h / 24 h.
- [ ] **rate_limit.py** + **cloudrun.md**: add rule
  `"market_cold_fill": ("RATE_LIMIT_MARKET_COLD_FILL_LIMIT",
  "RATE_LIMIT_MARKET_COLD_FILL_WINDOW_SECONDS")` and append
  `RATE_LIMIT_MARKET_COLD_FILL_LIMIT=20,RATE_LIMIT_MARKET_COLD_FILL_WINDOW_SECONDS=3600`
  to the deploy command in the same commit (§0.5). Update
  `tests/test_rate_limit_config.py`.

### Task 2C — Frontend freshness and pending states

Read **`DESIGN.md`** first. Use tokens only, with no new colours.

- [ ] `frontend/src/components/market/DataAge.jsx`: small muted label next to
  a price. It shows nothing when `as_of` is missing (old responses), and
  "close 07.11." for EOD (G2 copy), "15 min ago" for delayed or stale. A stale
  value adds a warning tone and a tooltip with `fetched_at` and `source`.
- [ ] `frontend/src/components/market/PendingValue.jsx`: skeleton shimmer with
  the text "Loading market data…". It respects `prefers-reduced-motion`.
- [ ] `frontend/src/hooks/usePendingRefetch.js`: when any item in a query result
  has `pending: true`, refetch at 3 s, 6 s, 12 s, 24 s, then stop (react-query
  `refetchInterval` function).
- [ ] New i18n keys in all language files in `frontend/src/i18n/messages/`
  (`messages.test.js` enforces that the key sets match).
- [ ] Tests: `DataAge.test.jsx` (absent, fresh, stale, EOD, locale formats) and
  `usePendingRefetch.test.jsx` (backoff, stop). Run `npm test`, `npm run test:cloud`,
  `npm run build`, `npm run build:cloud` (the component is shared by both editions).

**Wave 2 exit:** all three branches rebased on `main` and merged; fast suite,
postgres suite and frontend suite green; with `PORTFYL_MARKET_STORE=off`, behaviour
is identical. Check with `tests/test_value_series_equivalence.py` and the existing
router tests, all unchanged and green.

---

## 5. Wave 3 — route the app through the store (local edition only)

Each task is behind `if store_config.enabled:` with the old code kept in the
`else` branch until Wave 5. Response changes are **additive only**: optional
`as_of`, `stale`, `pending` per item, and a top-level `market_data_as_of` where a
list is returned. Handlers stay plain `def`. `tests/test_event_loop_not_blocked.py`
must stay green.

### Task 3.1 — `routers/market.py`

- [ ] `/market/quote/{ticker}`, `/market/history/{ticker}`, `/market/fx/{pair}` →
  `store.get_quotes` / `get_history` / `get_fx`. Add a test per endpoint for
  fresh, stale and pending.
- [ ] `/market/fundamentals/{ticker}`: the `.info` parts read `profile`,
  `statistics` and `quote` through the store, plus `derived.*`. Analyst fields
  (`targetMeanPrice`, `recommendation*`, `numberOfAnalystOpinions`) come from
  snapshot kinds `estimates`/`recommendations`/`price_target`, still filled by the
  yfinance adapter (§7). **Local phase (§0b):** the Shibui blocks (`_shibui_*`,
  valuation history, 5-year average P/E) also read through the store, with
  Shibui as the primary source.
- [ ] `/market/search`: when it is the gateway to a new instrument, it goes
  through `resolver` + `adapter.search` and is cached as alias rows.
- [ ] New `POST /market/revalidate/{ticker}`: marks the instrument's quote and
  open snapshots due with priority 2. There is a per-instrument cooldown of 5 min
  (the timestamp is kept on `market_fetch_state`) and the `market_cold_fill` rate
  limit applies. The endpoint never calls the provider. `/market` is already in
  `PORTFOLIO_AGNOSTIC_PREFIXES`, so `api.js` is unchanged.
- [ ] `useStockIntentPrefetch` is harmless now because it reads the store.
  Confirm with a test that hover never reaches an adapter.

### Task 3.2 — `routers/portfolio.py` + import/sync hooks

- [ ] `/summary`, `/holdings`, `/movers`, `/heatmap`, `/benchmarks`, `/performance`
  (portfolio part), `/earnings`, `/dividends`, `/dividends/forecast`,
  `/dividends/growth`, `/insider-buys` (Shibui part unchanged). **One
  `get_quotes(all_holdings)` per request.** This also removes today's mix of raw
  tickers and `yf_symbol(...)` (spec §3), because every call goes through the
  resolver.
- [ ] **Unresolvable or pending tickers** (spec §15): the position row stays,
  with cost basis; the price shows "unavailable" or pending. The position is
  excluded from market-value totals, and the response carries
  `excluded_from_totals: ["XYZ"]` so the UI can show a notice. T212 positions
  fall back to `broker_positions.current_price` (≤ 25 h) while pending, marked
  `source: "broker_snapshot"`.
- [ ] `commit_import_csv` and `ledger_import.insert_new_provider_rows` (used by
  IBKR, eToro and T212 syncs) call `store.ensure_instruments(new_tickers,
  priority=INTERACTIVE, cap=200)` **after** the commit. This step never fails the
  import: an error is logged and skipped.
- [ ] Tests: dashboard of 30 holdings = 1 market query; import of 250 new tickers
  marks 200; one unresolvable ticker is excluded from totals and reported.

### Task 3.3 — Analytics, FX, dividends, Discord job, alerts, watchlists

- [ ] `routers/analytics.py`: `_load_closes`-style `market_data.download` calls
  (lines ~46, ~155, ~911) → `get_history`; listing currency (~126, ~603) →
  `get_profile`/`get_quotes`; sector (~1298, ~1431) → `get_profile`. Note: today
  `auto_adjust=True` is used for benchmark/FX returns. The store keeps
  split-adjusted closes plus dividend events, so total-return series are
  rebuilt from them. **Verify with `test_value_series_equivalence.py` and a new
  benchmark-returns equivalence test** (spec §17, last bullet). If results differ
  by more than 0.1 pp over a year, store `adj_close` as an extra column instead
  (that would need a small Wave 1-style migration, sequenced on its own).
- [ ] `fx.py`: `_load_series` / `_load_pair_series` / `bulk_fetch_fx` → `get_fx`.
  The startup backfill in `main.py` uses the same function. `transactions.fx_to_czk`
  semantics do not change.
- [ ] `dividend_growth.py`: yfinance `.dividends` → `get_dividends`; payout ratio
  → `statistics`. Shibui first, unchanged.
- [ ] `jobs.py::_next_dividend_info` (currently a raw `yf.Ticker`, with no
  gate): → `get_snapshot('statistics')` + `get_dividends`. This removes the last
  ungated provider call.
- [ ] `routers/alerts.py::run_check` and `routers/watchlists.py` → `get_quotes`.
- [ ] Add a test (`tests/test_market_store_gateway.py`) that fails if any module
  outside `market_store/`, `market_data.py` and `shibui_client.py` imports
  `yfinance` or calls `market_data.` (allow-list shrinks to zero in Wave 5).

### Task 3.4 — Frontend wiring

- [ ] Place `DataAge` next to prices on Dashboard (hero, holdings, movers),
  Stock overview, Watchlists, Allocation. Use `PendingValue` +
  `usePendingRefetch` where `pending` can occur. Show the "excluded from totals"
  notice on Dashboard and Allocation.
- [ ] Stock page refresh button → `POST /market/revalidate/{ticker}`, then a
  refetch after 5 s.
- [ ] Check in the browser at 390 px and on desktop (CLAUDE.md "Verifying UI
  changes"). Run the four frontend commands.

### Task 3.5 — Equivalence and local switch-on

- [ ] `tests/test_market_store_equivalence.py`: for a fixture portfolio, every
  migrated endpoint returns the same numbers with the flag `off` and `on`
  (yfinance adapter, recorded fixtures), except the new fields. The tolerance is
  1e-9 for money and 0.1 pp for return series.
- [ ] `start.bat`: `set PORTFYL_MARKET_STORE=on` (local only; the Dockerfile
  stays without it, and cloud keeps it off per §16.5).
- [ ] The owner runs local for 3 days. Check `market_usage_daily` hit rate
  (expect > 95 % after the first day) and p95 latency of `/portfolio/summary`
  and `/market/fundamentals` (target < 150 ms warm).

### Task 3.6 — Seed CLI and local rehearsal (§7.1)

- [ ] `backend/market_store/seed.py`, run as
  `python -m market_store.seed --universe market_store/universe/seed_v1.csv
  [--provider yfinance|twelvedata] [--only stocks|fx] [--dry-run] [--max-credits N]`.
  Universe CSV columns: `symbol, mic, kind, reason` (`owner_holding`,
  `t212_popular`, `index:SPX` …). For each row: resolve or create the instrument
  (search-validated) → profile → full history → dividends → splits → statistics
  → earnings_dates → statements only if `not shibui_covers(symbol)`. Use the
  existing Shibui coverage check from `routers/market.py`, moved into
  `market_store/shibui_coverage.py` as a small pure helper so the router is not
  imported.
- [ ] Resumable: each step is a `market_fetch_state` row. Rerunning skips rows
  that are `ok` and fresh. Throttled by `budget.reserve(interactive=False)`.
  `--dry-run` prints the credit estimate (122 per instrument + 600 for
  statements, §7.1) without calling anything.
- [ ] Draft `seed_v1.csv` (G4): the owner's current holdings (from the owner DB,
  written by the CLI's `--export-owner-holdings`, run as the owner on their
  machine), plus the S&P 500 top ~200 by weight, DAX 40, PX constituents and the
  most common UCITS ETFs held by T212 users (public lists). The founder edits and
  approves it.
- [ ] Rehearsal on local with yfinance: a full run reports instruments
  ok/unresolvable/errors, and the unresolvable list feeds Task 4.2.

**Wave 3 exit:** fast + postgres + frontend suites green; equivalence test green;
three days of local use without regressions; `alembic heads` unchanged. Cloud still
has `PORTFYL_MARKET_STORE` unset (= off).

---

## 6. Wave 4 — Twelve Data and cloud (deferred: no Twelve Data plan yet, 2026-11-09)

### Task 4.1 — Twelve Data adapter

- [ ] `adapters/twelvedata.py` with `httpx.Client(base_url="https://api.twelvedata.com",
  timeout=3.0)`. Key from `PORTFYL_TWELVEDATA_API_KEY` (Secret Manager), sent as
  header `Authorization: apikey …`, never in the URL, so it can't be logged.
  Add the header name to the redaction list in `logging_setup.py` if it is not
  already redacted.
- [ ] Endpoint → shape mapping: `/quote` (1/symbol; batch via comma list; if a
  batch is rejected, fall back to single calls and set `batch_ok=false` in
  `market_provider_state`), `/time_series?interval=1day&adjust=splits&outputsize=5000`,
  `/profile` (10), `/statistics` (50), `/dividends` (20), `/splits` (20),
  `/earnings?period=next`-style lookup (20), `/earnings_calendar` (40/request),
  `/income_statement`, `/balance_sheet`, `/cash_flow` (100 each, annual and
  quarterly), `/symbol_search` (1).
- [ ] Read `api-credits-used`/`api-credits-left` → `budget.settle`. HTTP 429 →
  `note_429`. `{"status":"error","code":404}` → `empty` with negative caching;
  `code 403` (plan) → `unsupported`.
- [ ] Fixtures: record responses with the `demo` key for the symbols it allows,
  and hand-write the rest from the documented examples (marked synthetic in a
  README, like the broker fixtures). One live contract test,
  `@pytest.mark.live`, skipped unless `TWELVEDATA_LIVE=1`.

### Task 4.2 — Symbol mapping to `SYMBOL:MIC`

- [ ] `market_store/mic.py`: Yahoo suffix ↔ MIC ↔ Twelve Data `exchange` name.
  The resolver writes `twelvedata` aliases as `SYMBOL:MIC`. US symbols without
  a suffix get their MIC from `/symbol_search`, filtered by `country=United States`
  and `instrument_type`.
- [ ] Run against the Task 3.6 rehearsal output. Every seed row must map or be
  listed for manual decision (`universe/manual_map.csv`, approved by the founder).

### Task 4.3 — Earnings watch on real data

- [ ] `market_store/earnings.py`: parse `/earnings_calendar`, match by
  `SYMBOL:MIC` alias, and handle a 1,200-record page by splitting the request per
  country. Record the coverage per exchange in `market_usage_daily` (matched vs.
  held). If non-US coverage is poor (G5), those instruments keep the safety-net
  TTLs only. That fallback is already the default.

### Task 4.4 — Shadow mode

- [ ] `PORTFYL_MARKET_SHADOW=twelvedata` (local and a cloud staging revision only):
  for a 10 % sample of each job batch, also call Twelve Data. Compare price
  (±0.5 %), previous close, 52-week range, shares outstanding (±1 %), dividend
  events (exact dates and amounts) and last 30 closes. Log one structured line
  per difference (logger `portfyl.market.shadow`, no user data). Shadow results
  are not stored.
- [ ] `backend/scripts/market_shadow_report.py` summarises a log export into
  match rates per field and exchange. Exit criterion: ≥ 99 % price match, ≥ 98 %
  dividend-event match, every mismatch explained or fixed.

### Task 4.5 — Cloud seed run (after G4, G6)

- [ ] `deploy/run-market-seed.ps1`: runs the same image as a Cloud Run **Job**
  `portfyl-market-seed` with `--command python --args -m,market_store.seed,…`,
  `DATABASE_URL` = the direct runtime URL, provider `twelvedata`, and
  `--max-credits` set. It is modelled on `deploy/run-migrations.ps1`.
- [ ] Run overnight (≈ 1.8 h for 300 US names, about 3 h more for 100 non-Shibui
  names, §7.1). Live traffic is unaffected because the seed uses only the job
  share of the budget. Record the result in `docs/operations/` (date, credits
  used, unresolved count).

### Task 4.6 — Cloud flip, monitoring, compliance (after G5, G7, G8)

- [ ] `/health` gets a `market_data` subsystem: credits used today vs.
  `plan × 1440 × 0.7`, last 429, cooldown active, oldest hot quote age during
  session, `pending` share in the last hour. It turns `degraded` at 70 % of
  budget or when the oldest hot quote is > 10 min old during session.
- [ ] `deploy/cloudrun.md`: new "Twelve Data market data" section covering the
  secret, the env vars (`PORTFYL_MARKET_STORE=on`, `PORTFYL_MARKET_PROVIDER=twelvedata`,
  plan knobs), scheduler apply, the rollback steps (set the flag `off`, and the
  old path still works until Wave 5), and the support answers from G5.
- [ ] `docs/operations/market-data-purge.md`: how the migration owner runs
  `SELECT market_purge_all();` within 30 days after leaving Twelve Data (§17
  terms 16.2), and how to verify that the tables are empty.
- [ ] Compliance: Twelve Data in `docs/compliance/data-processing-inventory.md`
  (it receives only instrument symbols and our key; no personal data) and in both
  privacy notices if the list of recipients is enumerated there.
- [ ] Flip order: deploy with the flag off → apply scheduler entries → run
  `market_demand` once by hand (backfills current holdings, §15) → flag on →
  watch `/health` and usage for 48 h.

---

## 7. Wave 5 — cleanup (optional, later)

- [ ] Remove `PORTFYL_MARKET_STORE` and every `else` branch. Delete the in-memory
  info/download caches in `market_data.py` that only the old path used. The
  gateway test allow-list becomes `market_store/` + `shibui_client.py`.
- [ ] Decide whether yfinance stays as the **local edition** adapter (free, no
  key). If the cloud image no longer needs it, removing it is a lockfile change:
  a hotspot task on its own (CLAUDE.md lock rules, both Python versions).

---

## 8. Verification matrix (what proves each spec requirement)

| Requirement (spec) | Test |
|---|---|
| No tenant data in market tables (§2 anti-goal, §5.5) | `test_market_store_models.py`, `postgres/test_market_store_schema.py` |
| Runtime cannot delete; GC via definer function (§0.1) | `postgres/test_market_store_schema.py` 4–6 |
| `market_demand` never reaches an API (§0.3) | `test_market_store_demand_isolation.py` |
| Single flight across instances (§6) | `postgres/test_market_fill_lease.py`: 10 threads miss the same symbol → 1 adapter call |
| Limiter never exceeds cap (§8) | `test_market_budget.py`, `postgres/test_market_budget_postgres.py` |
| Request path never calls a provider when data exists (§2) | adapter spy in router tests asserts 0 calls for fresh and stale |
| Stale refresh happens in jobs, not requests (§6) | stale read test asserts `next_refresh_after` set, 0 adapter calls |
| Results-driven refresh (§7.1) | `test_market_jobs.py`: report → due at +1/+3/+7, stops on new `latest_period` |
| Split → full history refetch (§5.2) | anomaly test in `test_market_jobs.py` |
| Cloud cannot serve a Yahoo-backed shared cache (§16.5) | `test_market_store_config.py` |
| No event-loop blocking | existing `test_event_loop_not_blocked.py` |
| Same numbers as before (§17) | `test_market_store_equivalence.py`, `test_value_series_equivalence.py` |
| Additive API fields only | existing frontend tests pass unchanged; new `DataAge` handles absence |

---

## 9. Risks and how the plan contains them

| Risk | Containment |
|---|---|
| Canonical shapes miss a field the UI shows | the shape tests are built from the full `.info` key list (Task 2A); the equivalence test catches the rest |
| Benchmark/FX returns change because `auto_adjust=True` is gone | equivalence test in 3.3; fallback `adj_close` column as a separate migration |
| `/earnings_calendar` is weak outside the US | safety-net TTLs already cover it; coverage is measured in 4.3 |
| `/quote` batches not accepted on Venture | automatic fallback to single calls; same credits, more HTTP round-trips |
| Every-minute `market_prices` keeps Cloud Run warm during sessions | the schedule is limited to 06–21 UTC on weekdays; cost is visible in the GCP billing export |
| Pooled DB + long provider call | lease rows + `release_connection` (§0.2); no lock is held across the call |
| Concurrent sessions touching hotspots | the ownership table in §2; migrations only in Wave 1 (and a possible `adj_close` follow-up, sequenced alone) |

---

## 10. Wave checklist (copy into each PR description)

- [ ] Rebased on latest `main`; conflicts fixed locally
- [ ] `cd backend && python -m pytest tests/ --ignore=tests/postgres -v` green
- [ ] `cd backend && python -m pytest tests/postgres/ -v` green (disposable PG16)
- [ ] `alembic heads` = `EXPECTED_ALEMBIC_HEAD` (only Wave 1 changes it)
- [ ] Frontend: `npm test`, `npm run test:cloud`, `npm run build`, `npm run build:cloud`
- [ ] With `PORTFYL_MARKET_STORE=off`: no behaviour change (until Wave 4 flip)
- [ ] No file edited outside the task's ownership row
