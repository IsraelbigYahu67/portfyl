# Market-data cache in PostgreSQL — design

Date: 2026-11-08 · Revised: 2026-11-12 · Status: **revised after adversarial review, awaiting founder decisions (§16)**
· Review: `2026-11-08-portfyl-market-data-cache-review.md` (findings `F-nn`)
· Plan for v1: `docs/superpowers/plans/2026-11-12-portfyl-market-data-cache.md`

## Changelog (2026-11-12 revision)

Every changed or new passage is marked `[REV-n]`; the table links each mark to the review finding
that caused it. The draft text is in git (`b140ecc`). Section numbers are unchanged.

| Mark | Finding | What changed |
|---|---|---|
| REV-1 | F-01 | Daily rows carry `close`, `adj_close`, `split_ratio`, `dividend`; no single "split_adjusted" basis |
| REV-2 | F-02 | Verify-then-append replaces anomaly-triggered split detection; whole-series replace in one transaction |
| REV-3 | F-03 | Completed sessions only in the daily table, enforced by a CHECK; quote time = `last_quote_at` |
| REV-4 | F-04 | No advisory transaction lock; in-process single-flight in v1, lease rows in the cloud wave |
| REV-5 | F-05 | Runtime role is read-only on market tables; new role `portfyl_market_writer`; job-only writes in cloud |
| REV-6 | F-06 | No scheduled job in v1; one self-chaining market tick + one daily pass in the cloud wave; paid Neon is a gate |
| REV-7 | F-09 | Demand is not a v1 table; side channels listed; API never exposes fetch time, tier or held flags |
| REV-8 | F-10 | Symbol validator, instrument cap, catalogue-based admission, caps that include imports |
| REV-9 | F-11 | Required isolation tests spelled out |
| REV-10 | F-12 | Units stay in `currency_codes`; ILA and ZAc added |
| REV-11 | F-13 | v1 key = Yahoo-notation symbol behind a surrogate id; aliases deferred and re-keyed |
| REV-12 | F-14 | Sanity rules at the single write point |
| REV-13 | F-15 | Cost model recomputed |
| REV-14 | F-16 | Budget reservation rules |
| REV-15 | F-17 | Job registration checklist, time-boxing, health |
| REV-16 | F-18 | Store code owns its sessions; none is open across a provider call |
| REV-17 | F-19 | Flag, rollback, purge, counters |
| REV-18 | F-20, F-28 | **v1 scope = thin slice**; table verdicts; fundamentals payload cache deferred |
| REV-19 | F-21 | Real file list and hotspots |
| REV-20 | F-22 | Seed progress table and universe rule |
| REV-21 | F-23 | Existing `price_status` contract is reused; one additive field |
| REV-22 | F-24 | §3 corrected |
| REV-23 | F-25 | `require_fresh` for alerts; FX stamping semantics unchanged |
| REV-24 | F-27 | Earnings-driven refresh stays behind the safety nets until coverage is measured |
| REV-25 | F-29 | Compliance records updated with the durable store |

## 1. Intent

Portfyl fetches market data (prices, FX, profile, fundamentals, dividends) from
yfinance on the request path and caches it only in process memory (TTL 5 min /
6 h). That is fast enough for one user, but for the multi-tenant cloud edition it
means:

- every cold Cloud Run instance (`min-instances=0`, up to 5 instances) refetches
  everything; nothing is shared between instances or restarts;
- a stock-detail page costs up to ~2.3 s of provider calls (measured, warm, AAPL);
  the first yfinance call took 3.7 s; `.info` on a delisted ticker can hang for
  minutes (a gate/timeout exists in `market_data.py`);
- we plan to move to **Twelve Data**, which is **credit-metered per minute**.
  Naive 1:1 porting costs ~2,500 credits per cold dashboard open (30 holdings)
  and ~720 per stock-detail Overview open, and the 5-minute TTL would repay that
  every 5 minutes per user. See §10 for the numbers.

**Goal:** make PostgreSQL the shared market-data store. The request path reads
the database only (milliseconds). Provider calls happen in scheduled jobs and in a
small, rate-limited fill-on-miss path. Provider cost then scales with the number
of **distinct instruments across all users**, not with users × page views.

`[REV-18]` **The goal is reached in two steps.** v1 (this revision's plan) makes PostgreSQL a durable
second cache level in the **local edition, in front of yfinance, with no jobs**: stored data is served
at once and refreshed behind a short deadline. The cloud step (jobs, budget, Twelve Data) starts only
after the founder decisions in §16 and has its own plan.

## 2. Goals, non-goals, anti-goals

Goals
- Dashboard and stock detail served from PostgreSQL with no provider call when
  data is within its freshness window.
- Credits consumed ≈ distinct instruments × refresh frequency, tunable by knobs.
- Provider-agnostic: the same store works in front of yfinance first and in front
  of Twelve Data later; switching is a flag, not a rewrite.
- Every number shown can say how old it is (`price_as_of`) and where it came from. `[REV-21]`
- Never exceed the provider's per-minute budget; degrade to stale data, never to
  errors.
- `[REV-1]` **Numbers do not change.** With the store on and yfinance behind it, every figure equals
  what the same provider answers produce today.

Non-goals
- Real-time streaming / WebSocket (1 WS credit per symbol, capped at 500 on the entry Venture tier;
  portfolio views do not need ticks).
- Intraday candles/history for charts (daily closes only).
- Replacing Shibui (US fundamentals, ownership, insiders stay there).
- Changing valuation methodology (valuation keeps the **5-year average P/E**, see
  CLAUDE.md; locally derived "current P/E" is display only).

Anti-goals (a failure even if it "works")
- Any tenant-specific data (positions, quantities, who holds what) in these
  tables, or any way for one tenant to learn what another holds/views.
  `[REV-7]` One bounded inference remains and needs the founder's signature (§11, D-5).
- A request path that can still burn unbounded credits (arbitrary ticker strings,
  refresh buttons that bypass the cache, hover prefetch that calls the provider).
- Silently showing stale numbers as if live.
- `[REV-3]` An intraday price stored as a day's close; `[REV-2]` a history series that mixes two
  adjustment bases; `[REV-12]` a provider's empty or absurd answer replacing a good value.

## 3. Current state (facts, re-verified 2026-11-12 at `12dfe14`) `[REV-22]`

- No price/FX/history/info tables exist. Only `transactions.fx_to_czk` and
  `broker_positions.current_price` (T212 snapshot, 25 h freshness) are persisted.
- In-memory caches: `market_data.py` info (300 s ok / 60 s empty, 6 h stale
  fallback, 1,024 entries), `download()` (300 s, 128 entries, in-flight de-duplication),
  `ticker_attrs` (6 h, 2,048 entries, **no timeout**), `fx._DAILY_CACHE` (6 h, 512 entries),
  endpoint caches in `routers/market.py` (`/market/fx` 600 s, `/market/quote` 120 s,
  `/market/history` 30 min, `/market/fundamentals` 1 h).
- `market_data.py` is already the choke point for most traffic: `get_infos`/`get_info` (gated,
  deadline 8 s, maps symbols with `yf_symbol`), `download`, `ticker_attrs`, `ticker`. Raw `yf.Ticker`
  calls outside it: `routers/market.py` (`get_fx_rate`, `get_quote`, `get_history`,
  `get_fundamentals` statements/estimates/ownership, earnings recap), `jobs._next_dividend_info`,
  `dividend_growth.py` (via `market_data.ticker`).
- Files that reach the provider or its helpers (not only the eight the draft listed):
  `market_data.py`, `fx.py`, `ticker_map.py`, `dividend_growth.py`, `jobs.py`, `t212_sync.py`,
  `ledger_import.py`, `broker_cash.py`, and under `routers/`: `market.py`, `portfolio.py`,
  `analytics.py`, `alerts.py`, `watchlists.py`, `cash.py`, `broker.py`, `benchmarks.py`,
  `portfolios.py`, `allocation_targets.py`, `local_features.py` (+ `services/screener_jobs.py`).
  There is no `backend/analytics.py` or `backend/alerts.py`.
- History is read on **three bases** today: as-traded (performance, `routers/analytics.py:29-83`:
  `auto_adjust=False, actions=True`, split adjustment undone), split-adjusted (correlation, baskets),
  dividend-adjusted (`auto_adjust=True`: FX, 2-day change, movers, heatmap, benchmarks, stock chart).
  The last row of a daily download is today's unfinished bar while a market is open.
- A price-freshness contract already exists end to end: `market_data.price_freshness` →
  `price_status`, `price_as_of`, `price_delay_minutes`, `price_source` on `/portfolio/holdings` and
  `/portfolio/summary`, rendered by `frontend/src/lib/priceFreshness.js`.
- Symbol handling is inconsistent: summary/movers/insider-buys pass raw broker tickers to
  `download`/`ticker_attrs`, heatmap/performance pass `yf_symbol(...)`. `yf_symbol` is a one-entry
  table; `Transaction` has no ISIN or exchange column.
- **There is no startup FX backfill** (CLAUDE.md is stale on this): `bulk_fetch_fx` runs at import
  and at T212 finalisation.
- Sub-units: only `GBX` (`currency_codes.SUBUNITS`).
- Jobs run via Cloud Scheduler → `/internal/jobs/*` (OIDC verified, `with_job_lock` = **session-level**
  advisory lock on a dedicated NullPool connection to the **direct** host, `JOB_DATABASE_URL`),
  schedules in `deploy/operations.json` (all hourly or slower since the 2026-10-19 Neon outage).
  **Jobs connect as `portfyl_runtime`, the same role as the web runtime.** The runtime `DATABASE_URL`
  is Neon's pooled endpoint (PgBouncer transaction pooling). A Cloud Tasks queue
  (`backfill_trigger.py`) already wakes a job on demand.
- The local edition runs passes through `_periodic_loop` → `asyncio.to_thread` →
  `run_on_private_loop` (`main.py:348-384`).
- Rate limiting is PostgreSQL-backed, **cloud-only**, three rules, each defined by required env vars.
- Migrations: Alembic head `0025_stripe_billing`; runtime role `portfyl_runtime`
  gets explicit per-table grants; tenant tables use forced RLS; global infrastructure tables
  (`job_runs`, `rate_limit_buckets`, `stripe_events`, `beta_invites`) sit outside RLS with exact-grant tests.

## 4. Principles

1. **PostgreSQL is the source of truth for market data; memory is only an L1.**
2. **Request path = read DB.** Stale data is returned (flagged) and refreshed in
   the background (stale-while-revalidate). `[REV-5]` In the cloud edition the request path never
   calls the provider and never writes market tables. `[REV-18]` In v1 (local) a refresh may run
   behind a short deadline in a worker thread, as `market_data` already does today.
3. **One gateway.** `[REV-18]` The gateway is the existing `market_data` facade with the store
   (`backend/market_store/`) underneath it; routers stop calling `yfinance` directly.
4. **Freshness by data type**, not one TTL for everything (§7).
5. **Store raw facts, derive the rest locally** (market cap,
   P/E, yield, 52-week range) so price-dependent figures never need a provider
   call.
6. **Provider-neutral schema.** Provider is a column and an adapter, not a table
   name.
7. **Global public data only.** No `workspace_id`; nothing about users.
8. `[REV-12]` **One write point.** Every row enters through `market_store` writer functions that
   apply the sanity rules of §8.1; no router, importer or job writes market tables directly.
9. `[REV-16]` **No session across a provider call.** Store functions open and close their own short
   sessions and never accept the caller's `Session`.
10. `[REV-3]` **Daily rows are completed sessions.** "Today" is always composed at read time from the
    latest quote.

## 5. Data model (new Alembic revision `0026_market_data_store`)

All tables are global (no tenant column). UUID `public_id` is not needed (never
exposed by id); internal `bigint` ids are fine because nothing serializes them.
Provider-neutral names; `source` records which adapter wrote a row.

`[REV-18]` **v1 creates three tables** (§5.1–5.3). §5.4 lists the tables of later waves; they are
*not* created by `0026`.

### 5.1 Reference

`market_instrument` `[REV-11]`
- `id` bigint PK; `symbol` varchar(40) UNIQUE — the listing symbol **in Yahoo notation after
  `ticker_map.yf_symbol()`**, upper-case (`AAPL`, `CEZ.PR`, `USDCZK=X`, `^GSPC`); this is what every
  call site already passes.
- `kind` (`equity|etf|fund|index|fx|crypto|unknown`, default `unknown`).
- History bookkeeping (replaces `market_fetch_state` for history): `history_start` date (earliest
  date the stored series was requested from), `history_checked_at` timestamptz (last successful
  verification), `history_attempts` int, `history_next_attempt_at` timestamptz.
- `created_at`.
- Later, additively: `isin`, `exchange_mic`, `data_latency`, `status`.

`market_instrument_alias` — **deferred to the Twelve Data wave** `[REV-11]`. When it arrives its key is
`(namespace, alias)` (namespace = broker or provider), never `alias` alone, and resolution uses the
transaction currency and the ISIN in `transactions.source_instrument_id` as tie-breakers.

### 5.2 Prices and events

`market_price_daily` — PK (`instrument_id`, `trade_date`) `[REV-1]`:
- `close` double — the provider's **split-adjusted** close (yfinance `Close` with
  `auto_adjust=False`; Twelve Data `adjust=splits`);
- `adj_close` double — **split- and dividend-adjusted** (yfinance `Adj Close`; Twelve Data
  `adjust=all`);
- `split_ratio` double NULL — split effective that day (4.0 for 4:1);
- `dividend` double NULL — dividend with that ex-date, in the provider's (split-adjusted) units;
- `source`, `fetched_at`.

Readers: `auto_adjust=True` call sites read `adj_close`; correlation/basket read `close`;
performance reads `close` + `split_ratio` and keeps undoing the split adjustment exactly as
`routers/analytics._load_close_panel` does today. There is no `basis` column and no separate event
table in v1: one provider call returns all four values per bar.

`[REV-3]` **Completed sessions only**, enforced by
`CHECK (trade_date < (fetched_at AT TIME ZONE 'UTC')::date)`: a bar is storable on the first fetch
after UTC midnight following its session. Correct for every exchange whose regular session does not
cross UTC midnight on the closing side (all current ones); Asia/Pacific bars are held back a few
hours, never stored early. No time-zone, holiday or half-day table is needed.

`[REV-2]` **Verify, then append.** A tail refresh fetches the last ~30 daily bars. For every date
present both in the store and in the fetch, `close` and `adj_close` must agree within 1e-4 relative.
Agreement → insert the new completed bars. Any disagreement, or no common date → replace the whole
series of that instrument in **one transaction** (instrument row locked `FOR UPDATE`, delete, bulk
insert). A split or a dividend rescales every earlier bar, so it is always visible in the overlap.
An empty fetch never deletes stored history.

Latest price `[REV-18]`: in v1 the quote lives inside the `info` snapshot (§5.3). A typed
`market_price_latest` is reconsidered with Twelve Data, where `/quote` (1 credit) and `/profile`
(10) refresh on different clocks. Then: `quote_time` = `last_quote_at`, **not** `timestamp`
(which is the bar's opening time) `[REV-3]`.

FX pairs are `market_instrument` rows with `kind='fx'` and reuse the same tables. `[REV-10]` The store
never converts units: it keeps the provider's price and currency string; `currency_codes` stays the
only place that knows sub-units, and gains `ILA→ILS` and `ZAC→ZAR` next to `GBX→GBP`.
`transactions.fx_to_czk` keeps its role (trade-date rate stamped at import) and is not touched;
`[REV-23]` the way it is stamped does not change either (completed bars forward-filled, today from
the live quote).

### 5.3 Slow-moving blobs

`market_snapshot` — PK (`instrument_id`, `kind`): `payload` JSONB, `schema_ver` int, `source`,
`status` (`ok|empty`), `fetched_at` (last good payload), `checked_at` (last attempt), `attempts`,
`next_attempt_at`, `pending_payload` JSONB NULL (§8.1). `[REV-18]` These columns absorb the draft's
`market_fetch_state`.

`[REV-18]` **v1 has one kind: `info`** — the sanitised yfinance `.info` dict (JSON-safe values only).
That dict is the shape every consumer reads today (`quote()`, `price_freshness()`, sector, country,
dividend fields, the ratio builders), so storing it whole gives parity with no mapping layer and no
silent loss of a field. It is acceptable because v1 is the owner's private instance. The cloud wave
replaces it: `quote` and `profile` kinds with a documented, narrowed key list, written by the Twelve
Data adapter, read through the same `get_infos` contract — "the raw provider response is not stored"
applies from that wave on.

Later kinds (Wave 2 and after): `statistics`, statements, `earnings_dates`, dividends calendar,
insider transactions. The draft's canonical provider-neutral payloads are designed **then**, against
a second provider, not now. `[REV-18]` Caching the `/market/fundamentals` *response* is not allowed
until that response is proven identical for every plan and tenant (F-28).

### 5.4 Operations (later waves — not in `0026`) `[REV-18]`

- `market_request` (cloud wave): append-only enqueue of symbols the request path wants; runtime has
  `INSERT` only, no unique constraint (a duplicate-key error would itself be an oracle), no `SELECT`.
  Carries a lease (`lease_owner`, `leased_until`) for the fill job `[REV-4]`.
- `market_demand` (cloud wave) `[REV-7]`: readable and writable by the writer role only; filled by a
  job that reads each workspace's held symbols under RLS as `portfyl_runtime` and hands **only the
  distinct symbol set** to the writer session. Never touched by the request path.
- `market_budget`, `market_provider_state`, `market_usage_daily` (Twelve Data wave), rules in §8.
- `market_seed_item` (Twelve Data wave), §7.1.
- `market_instrument_alias`, §5.1.

### 5.5 Grants and RLS `[REV-5]`

- These are **not tenant tables**: no `workspace_id`, no RLS policies, no foreign key to any tenant
  table. Recorded as "Global reference data (market store)" in
  `docs/security/tenant-isolation-matrix.md`.
- `portfyl_runtime`: **`SELECT` only** on all three tables.
- New role **`portfyl_market_writer`** (created by `0026` if missing: `NOLOGIN NOSUPERUSER
  NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS`; an operator adds `LOGIN` and a
  password where it is used): `SELECT, INSERT, UPDATE` on `market_instrument` and `market_snapshot`;
  `SELECT, INSERT, UPDATE, DELETE` on `market_price_daily`; `USAGE, SELECT` on
  `market_instrument_id_seq`; `USAGE` on schema `public`. **No grant on any other table.**
- Writes go through `market_store.db.writer_session()`, bound to `MARKET_WRITER_DATABASE_URL` and
  falling back to `DATABASE_URL`. v1 local: the default dev database user is the owner, so nothing
  else is needed; if the local runtime connects as `portfyl_runtime`, startup's preflight says so and
  names the variable to set. Cloud wave: only the market job endpoints get the writer URL (direct
  host); web instances cannot write.
- Why not runtime writes or a `SECURITY DEFINER` function: review F-05.
- `[REV-9]` Tests (PostgreSQL suite): no `workspace_id`/`user_id`/`portfolio_id` column and no foreign
  key to a non-market table on any `market_*` table; exact grants for both roles; the writer role
  cannot read `transactions`, `users`, `workspaces`; the runtime role cannot write any `market_*`
  table; the finality CHECK rejects a same-day row.
- Migration is additive only (new tables, new role) → forward-compatible with running
  instances. Update `EXPECTED_ALEMBIC_HEAD` in the same change (project rule) and the hard-coded head
  in `tests/test_plan_schema.py`. Downgrade drops the tables and leaves the cluster-wide role.

## 6. Read path

`[REV-18]` v1 (local edition, yfinance):

```
caller (unchanged)                       market_data.get_infos([...])
        │                                          │
        ▼                                          ▼
 L1 in-process (as today)  ── miss ──▶  L2 market_snapshot (one SELECT, own session, closed)
        │                                          │
        │ fresh (< 300 s)  ◀───────────────────────┘ return
        │ stale / empty-and-backing-off / missing
        │        ▼
        │  worker thread: provider (.info behind the history gate) → sanity rules → writer session
        │        │
        │  wait ≤ 1.5 s when a stored value exists, ≤ 8 s (today's deadline) when none
        ▼
  result, or the stored value (its real `price_as_of`) if the deadline passes;
  the worker finishes and persists either way
```

History: `market_store.history.closes(symbols, start|last_n, adjusted)` and
`history.panel(symbols, start)` read `market_price_daily`, refresh the tail when the last check is
older than 300 s (same deadline rule), and append today's point from the stored quote.

Rules that hold in every wave:

- `[REV-21]` **No new response envelope.** Freshness travels in the fields that exist:
  `price_status`, `price_as_of`, `price_delay_minutes`, `price_source`. v1 adds one additive boolean,
  `prices_refreshing`, to `/portfolio/summary`. `[REV-7]` No API field carries `fetched_at`, a tier,
  or anything else that describes demand.
- Batch-first: a 30-holding dashboard is one SQL query for quotes.
- `[REV-4]` **Single-flight** in v1 is the in-process future map `market_data` already has; the only
  database lock is the instrument row lock inside the short write transaction, taken after the
  provider answered. No `pg_try_advisory_xact_lock`: it is released by the commit that
  `release_connection` performs before every provider call, and session locks do not exist on the
  pooled runtime endpoint.
- `[REV-8]` **Symbol validation:** `^[A-Z0-9^][A-Z0-9.\-=^]{0,19}$` after upper-casing, at every
  store entry; `/market/quote|history|fx` reject anything else with 400. A hard cap on instrument
  rows (default 20,000) fails closed.
- `[REV-23]` `get_infos(..., require_fresh=True)` (price alerts): full deadline, and a value older
  than the TTL counts as unavailable.
- The refresh button and hover prefetch are harmless: they read the store.

Cloud wave (replaces the worker-thread refresh; own plan) `[REV-5]` `[REV-6]`:

- A stale read marks the row due; a **miss** inserts into `market_request` and enqueues an immediate
  Cloud Task (the `backfill_trigger.py` pattern). The response carries `price_status: "pending"` (a
  new enum value with dictionary entries); the client retries on a bounded schedule (2 s, 5 s, 15 s,
  then stops).
- The fill job claims requests by lease, calls the provider with no transaction open, writes through
  the writer role.
- `[REV-8]` Admission: only symbols found in the locally stored catalogue; per-workspace daily limit
  of new instruments from plan entitlements, **imports included**; a global daily ceiling that alerts.
  `ensure_instruments` at import is subject to the same counters.

## 7. Refresh policy (defaults; all are config knobs)

`[REV-18]` v1 (yfinance): `info` 300 s (empty answers back off 60 s → 15 min); history tail check
300 s; everything else stays on today's in-memory paths.

Cloud/Twelve Data wave. Credit costs VERIFIED against the official docs on 2026-11-12 (review §4).

| Data | Endpoint (credits) | Freshness / trigger | Notes |
|---|---|---|---|
| Latest price | `/quote` (1/symbol) | `hot`: every 2 min while a **real-time** exchange is open (founder decision; adaptive, see §8); all held: once after close | `[REV-13]` On Venture only US exchanges are real-time; **Prague, Xetra, London, Paris, Amsterdam, Toronto are EOD** and refresh once after close (D-1) |
| Daily close history | `/time_series` 1day (1, any `outputsize`) | full history once at first sight; then a 30-bar tail per day, verified against the store `[REV-2]` | second call with `adjust=all` if `adj_close` cannot be derived (decided in shadow mode) |
| FX | `/quote` or `/exchange_rate` (1) | `[REV-13]` every 10 min 08:00–22:00 CET for pairs in use (≈ 53,000 credits/month for 30 pairs); not "same as prices" | ~30 pairs |
| Profile | `/profile` (10) | 90 days | sector/industry/description |
| Statistics | `/statistics` (50) | **after each earnings report** (§7.1); safety net 120 days | seeded universe + instruments viewed in the last 30 days |
| Dividends | `/dividends` (20) | after each earnings report; safety net 30 days for payers, 90 days for known non-payers | feeds dividend tab and forecast |
| Splits | — | `[REV-2]` **not polled**: a split shows up in the tail verification and triggers the series replace | `/splits` (20) only to label the event if the bars do not carry it |
| Earnings dates / who reported | `/earnings_calendar` (**40 per request**, max 1,200 records) daily; `/earnings` period=next (20) only for single-instrument fills | daily pass | `[REV-24]` non-US coverage and minimum plan are not documented; safety nets remain the mechanism of record |
| Statements (6 calls × 100) | `/income_statement`, `/balance_sheet`, `/cash_flow` (annual + quarterly) | once after each earnings date | **skip for instruments Shibui covers**; Venture qualifies, but "full access to historical data requires the Ultra … or the Enterprise plan" (D-2) |
| Estimates, recommendations, price targets, institutional holders | 20 / 100 / 75 / 1500 | **not fetched from Twelve Data** | Ultra/Enterprise only |
| Insider transactions | `/insider_transactions` (200) | on click, 24 h | Shibui first for US |
| ETF / fund data | 200–1000 | **not available on Venture** | answers the draft's question 16.4 |

Derived locally, never fetched: market cap = price × shares outstanding; trailing
P/E = price ÷ TTM EPS; dividend yield = trailing 12-month dividends ÷ price;
52-week range from `market_price_daily`. `short_percent_of_float` has no Twelve
Data field → stays on Shibui.

### 7.1 Seed first, then update after results (founder's idea, 2026-11-08)

Instead of discovering instruments one by one as users add them, the store is
**bulk-loaded up front for a curated universe of a few hundred companies**, and
afterwards the slow data is **refreshed only when a company reports results**
(plus a long safety net), not on a calendar.

**Seed (one-off, resumable admin command `market_seed`, not a scheduled job)**
- `[REV-20]` Universe = a file the founder approves (`deploy/market-seed-universe.csv`), built by
  rule rather than by hand: (a) every distinct symbol held or watched in the owner's local database,
  (b) the constituents of the indices the app already ships as benchmarks, (c) nothing else until
  measured demand says so. Decision D-6.
- Per instrument: resolve and store aliases (this validates the symbol mapping up
  front), `/profile`, full daily history, `/dividends`, `/statistics`, next earnings date.
  Statements (6 × 100) only for instruments Shibui does not cover.
- One-off cost per instrument ≈ 122 credits (1 + 1 + 10 + 50 + 20 + 20 + 20) plus
  600 for statements where needed. Example: 300 US names ≈ 36,600 credits; 100
  non-Shibui names add 60,000. At ~340 credits/min for jobs this is roughly 1.8 h
  and 2.9 h respectively. `[REV-13]` One instrument's six statements (600 credits) cannot fit one
  minute of the 488-credit soft cap; the command spreads them.
- `[REV-20]` Resumable by construction: `market_seed_item(symbol, step, status, attempts,
  last_error)`; every step is an idempotent upsert; `--dry-run` prints the credit total; throttled by
  the reservation of §8; the command follows `backend/manage_beta.py` (argparse, run as a one-off
  Cloud Run Job) and uses the writer URL.
- Benefit: the first view of any seeded company is instant for every user, and
  the dress rehearsal can run on the local edition with the free yfinance adapter
  before any credits are spent.
- Non-seeded tickers use the enqueue path (§6) and join the universe once admitted.

**Results-driven updates**
- Store each instrument's next report date (`market_snapshot` kind
  `earnings_dates`). Do **not** poll per instrument for it. Use one cheap
  market-wide call: `/earnings_calendar` costs **40 credits per request** (not per
  symbol; limited to 1,200 records, filterable by date, exchange, country). The daily pass fetches
  yesterday's/today's reporters, matches them to our instruments, and marks `statistics`,
  `dividends`, the statements (if provider-sourced) and `earnings_dates` as due.
- Data lags the announcement. After a report, re-check at +1, +3 and +7 days until
  the latest fiscal period in the snapshot changes, then stop (bounded retries).
- Safety nets only if nothing changed: profile 90 days, statistics and statements
  120 days, dividends 30 days (some companies declare dividends outside earnings).
- `[REV-24]` Until shadow mode has measured how many non-US reporters the calendar lists, the safety
  nets are treated as the primary trigger outside the US.
- Prices are unaffected: they follow §7.

## 8. Credit budget and protection (Twelve Data wave)

- **Cross-instance limiter:** before a provider call, atomically reserve credits
  in `market_budget` for the current minute
  (`INSERT … ON CONFLICT DO UPDATE SET credits_used = credits_used + :c WHERE
  credits_used + :c <= :cap RETURNING …`). `cap` = plan limit × 0.8.
  `[REV-14]` The minute comes from the database clock (`date_trunc('minute', now())`). Reservations
  are **never refunded** (a failed call may still be charged). After every response
  `credits_used = GREATEST(credits_used, plan_limit − api-credits-left)`. Rows older than 48 h are
  trimmed by the daily pass. Only jobs call the provider, so at most three writers touch the row.
- **Priority:** fills requested by users may use up to the full cap; scheduled refresh only the part
  not reserved for them (default 30 % reserved).
- **Learn from the provider:** read `api-credits-left`/`api-credits-used`
  headers; on HTTP 429 set `cooldown_until` to the next minute boundary and serve
  stale. Circuit breaker on repeated 5xx.
- **Adaptive cadence for hot prices.** Target is a 2-minute refresh, but the real
  interval is `max(2 min, hot_count ÷ job_credits_per_minute)`. With the entry Venture tier
  (610/min, cap 80 % = 488, 30 % reserved → 341.6/min for
  jobs) a 2-minute cycle covers ~683 hot instruments; beyond that the interval
  stretches automatically instead of hitting 429. Instruments whose exchange is
  `eod`/closed are skipped. The achieved age is exposed in `price_as_of`.
- **Cost visibility:** `market_usage_daily`, surfaced in the existing subsystem
  health; alert at 70 % of the per-minute budget.

### 8.1 Sanity rules at the write point (all waves) `[REV-12]`

1. An empty or unpriced answer never replaces a good payload. The last good one stays, `status`
   becomes `empty`, `attempts` grows and `next_attempt_at` backs off 60 s, 120 s … capped at 15 min.
2. A price outside ×[0.5, 2.0] of the stored price (FX: ×[0.8, 1.25]) is parked in
   `pending_payload`; it is promoted only when the next fetch agrees with it within 2 %. Until then
   the stored value is served.
3. Daily bars with a non-finite or non-positive `close`/`adj_close` are dropped; negative dividends
   and non-positive split ratios are dropped.
4. `[REV-10]` Nothing is unit-converted on the way in.

## 9. Jobs

`[REV-6]` **v1 has no scheduled job and adds no in-process loop.** Refresh is driven by reads.

Cloud wave (own plan), replacing the draft's five jobs:

| Job | Trigger | Does |
|---|---|---|
| `market_tick` | **self-chaining Cloud Task** while at least one hot instrument's exchange is open; an hourly Cloud Scheduler entry restarts the chain | batches `/quote` for the hot set within the job budget; enqueues its own continuation (≥ 20 s later, named by time bucket so duplicates collapse), stops at the close |
| `market_fill` | immediate Cloud Task from the request path; hourly safety net | claims `market_request` rows by lease, resolves against the catalogue, fills quote + history |
| `market_daily` | once a day after the US close | EOD pass for all held (tail verify), demand collection, earnings calendar, due slow data, GC, budget trim |

- `[REV-6]` Why not "every minute" and "every 5 minutes": at Neon's smallest compute the draft's
  schedule keeps the database awake 730 h a month = 182.5 CU-hours against a Free quota of 100; the
  tick limited to the US session is 34.6 (review F-06, §5). **A paid Neon plan is a gate for the
  cloud wave (D-3).**
- `[REV-15]` Registration checklist, owned by one task: `jobs.RECURRING_JOB_NAMES`,
  `main._JOB_MAX_AGES`, `routers/internal_jobs.py`, `deploy/operations.json`,
  `tests/test_event_loop_not_blocked.py`. A name missing from the first makes the job answer 500
  after doing its work. Passes are `async def pass(db) -> list`, time-boxed to 240 s (attempt
  deadline 300 s), commit per batch, idempotent. `/health` max age for the tick chain is 96 h (it
  rests over weekends); the health signal that matters is the age of the oldest hot quote while its
  exchange is open.
- `[REV-16]` A job pass commits (ends its transaction) before every provider call; job sessions are
  not covered by `release_request_connections`.
- Local edition, cloud wave onward: the same passes run under `_periodic_loop`; nothing extra in v1.
- The Discord dividend job (`jobs._next_dividend_info`) moves behind the store in Wave 2.

## 10. Cost model (with stated assumptions) `[REV-13]`

Assumptions: 1,000 distinct held instruments, 300 "hot" **and US-listed**, 300 with a detail page
opened per month, 30 pairs of FX, **21** trading days, **195** two-minute refreshes per US session
(390 minutes), 60 % dividend payers, 10 % of detail-opened instruments not covered by Shibui.
Arithmetic: review §5.

| Item | Credits / month |
|---|---|
| Daily tail for all held (1,000 × 21) | 21,000 |
| 2-minute intraday for hot (300 × 195 × 21) | 1,228,500 |
| FX every 10 min, 14 h (30 × 84 × 21) | 52,920 |
| Profile (1,000 × 10 ÷ 3) | 3,333 |
| Statistics (300 × 50 × 4 ÷ 12; up to ×3 with re-checks) | 5,000–15,000 |
| Dividends (600 × 20 + 400 × 20 ÷ 3) | 14,667 |
| Splits | ~0 (verification, §5.2) |
| Earnings calendar (40 × 21; ×5 if split by country) | 840–4,200 |
| Statements for non-Shibui (30 × 600 ÷ 3) | 6,000 |
| **Total (steady state, excl. one-off seed)** | **≈ 1.33–1.35 M ≈ 31 credits/min average; ≈ 150/min for the hot pass during the US session** |

The 2-minute cadence is ~92 % of all spend. Against the 24×7 ceiling of the entry Venture tier
(610 × 60 × 24 × 30 = 26,352,000) this is 5 %, but that is the wrong yardstick: the hot pass runs
only in US sessions, where the ceiling is 610 × 390 × 21 = 4,995,900 (the pass is 25 % of it) and the
job share is 341.6/min (the pass is 44 % of it at 300 hot instruments, 100 % at 683).

Other running costs of the cloud wave: Neon compute 34.6 CU-hours/month for the US-session tick
plus ~1.3 for the daily pass (≈ $3.80 on Launch at 0.25 CU; a multiple if the compute autoscales);
Cloud Scheduler $0.10 per job per month beyond three free; Cloud Run request time is inside the free
tier at this volume. Venture: USD 149/month (entry tier; 1,597 credits at USD 299, 2,584 at USD 499).

For comparison the naive port costs ≈ 2,500 credits per cold dashboard open and
repeats it every 5 min per user.

## 11. Security, privacy, compliance

- Tables hold public market data only; isolation tests in §5.5.
- `[REV-7]` **What a tenant can still infer.** Demand is observable without reading any table:
  whether a first view is instant, how fresh a quote is, whether an unknown string is rejected at
  once. Mitigations: the API exposes only the provider's market timestamp; a viewer's own request
  promotes the instrument; the seed covers common names. Residual: the *first* response for a
  non-seeded instrument tells the viewer whether anyone else asked for it before — existence only,
  no identity, no quantity. Recorded in the isolation matrix as an accepted inference (D-5). Not
  applicable to v1 (one tenant).
- Provider receives only instrument identifiers and our API key — no user data.
  `[REV-25]` v1 updates `docs/compliance/data-processing-inventory.md`: the market cache row becomes
  "durable, local database, purge command"; the cloud wave adds Twelve Data as a recipient and the
  deletion path (purge + Neon history window of 6 h).
- No secrets in tables; the provider key stays in the existing secret store.
- `[REV-17]` **Purge:** `python -m market_store.purge --yes` empties the three tables. It is the
  rollback tool, and from the cloud wave on it is how the 30-day deletion duty in Twelve Data's terms
  (16.2) is met.
- Legal items that only the founder or a lawyer can settle: §16 D-4.

## 12. Application changes

`[REV-18]` `[REV-19]` **v1 (plan 2026-11-12).**

Backend
- New package `backend/market_store/`: `config` (flag), `db` (reader/writer sessions, preflight),
  `symbols` (validator), `instruments`, `info_store`, `history_store`, `yahoo` (adapter),
  `history` (read API), `staleness`, `metrics`, `purge`. Models live in `backend/models.py`
  (project convention).
- `market_data.get_infos` gains the L2 step and `require_fresh`; nothing else in its API changes, so
  holdings, summary, analytics, alerts, watchlists and fundamentals are served from the store
  without edits.
- History call sites move to `market_store.history`: `fx.py` (`_load_pair_series`),
  `routers/analytics.py` (`_load_close_panel`, `_fx_to_usd_series`, `_ticker_daily_returns`),
  `routers/portfolio.py` (`_two_day_closes`, movers, heatmap, benchmarks), `routers/market.py`
  (`get_history`; `get_quote` and `get_fx_rate` go through `market_data.get_info`).
- `/portfolio/summary` gains `prices_refreshing`.
- Feature flag `PORTFYL_MARKET_STORE=on|off`, default off; **refused at startup in the cloud
  edition**. Off = today's code path.
- Hotspots, one owner each: `models.py`, `database.py`, `alembic/versions/`,
  `tests/test_plan_schema.py`, `main.py`, `market_data.py`, `tests/conftest.py`, `currency_codes.py`,
  `CLAUDE.md`.

Frontend
- Dashboard: when `summary.prices_refreshing` is true, refetch once after 3 s (at most twice per
  mount). No polling loop, no new string, no visual change — `DESIGN.md` untouched `[REV-21]`.

Not in v1: `ticker_attrs` consumers (dividends, earnings, insider-buys), fundamentals statements,
`jobs._next_dividend_info`, `dividend_growth.py`, `StockOverviewTab`'s automatic `financials` fetch
(stays until Wave 2 gives it a cached source), deleting the in-memory caches (they remain the L1).

Later waves: `PORTFYL_MARKET_PROVIDER=yfinance|twelvedata`, the Twelve Data adapter, `pending` in
the UI (8 dictionaries per new string), attribution "Data provided by Twelve Data" with a link next
to the existing price-source line.

## 13. Rollout `[REV-18]`

| Step | Edition | Content | Starts when |
|---|---|---|---|
| **v1** — durable cache | local only | §5.1–5.3, §6 v1, §12 v1; plan waves 0–3 | founder approves this spec |
| **Wave 2** — slow data | local only | snapshot kinds for dividends/earnings/insider/statements; `ticker_attrs` and `jobs._next_dividend_info` behind the store; stop the automatic `financials` fetch | v1 has run on the owner's instance for two weeks |
| **Cloud wave** — foundation | cloud, flag off | writer URL for jobs, `market_request`, `market_fill`, admission caps, catalogue, `pending` | D-1 … D-5 answered; paid Neon |
| **Wave 4** — Twelve Data | cloud | adapter, alias table, budget, `market_tick`, `market_daily`, seed, shadow mode (call both, compare, log diffs), flip the provider | written licence answer (D-4) |
| **Wave 5** | both | remove yfinance paths from the cloud build | Wave 4 stable |

The founder's decision "Wave 3 (cache in front of yfinance) ships to the local edition only" maps to
v1 and Wave 2. Each step: isolated branch per task, re-integrate upstream, re-run tests, check
`alembic heads` vs `EXPECTED_ALEMBIC_HEAD`, run the PostgreSQL suite in `backend/tests/postgres/`.

`[REV-17]` Rollback per step: v1 and Wave 2 — set the flag off and restart (optionally purge);
the migration stays (additive). Cloud wave and Wave 4 — flag off returns the cloud edition to
today's path; `PORTFYL_MARKET_PROVIDER=yfinance` is **not** a cloud rollback (no licence), so Wave 4
keeps the previous image as its rollback.

## 14. Verification

- Unit: freshness logic, deadline rule, negative caching and back-off, sanity rules, symbol
  validator, verify-then-append (agree / split / dividend / no overlap / empty fetch), completed
  sessions only, today's point, parity of `closes`/`panel` with what `yf.download` returned.
- PostgreSQL integration: §5.5 tests; whole-series replace is invisible to a concurrent reader;
  migration up/down.
- Flag off: the existing suites pass unchanged.
- `[REV-17]` Counters to watch on the owner's instance (logged once a minute when non-zero):
  `l2_hit`, `provider_fetch`, `stale_served`, `sanity_rejected`, `history_appended`,
  `history_replaced`. Success for v1: a dashboard load after a restart with the flag on makes no
  provider call when stored data is under 300 s old, and returns within the 1.5 s deadline otherwise.
- Twelve Data wave: provider adapter against recorded fixtures; one contract test against the live
  `demo` key for single-symbol `/quote`, `/time_series`, `/eod` (it rejects batches with 401).

## 15. Calls I made (check these)

- Provider-neutral store first, in front of yfinance, Twelve Data later.
- `[REV-1]` Both adjusted closes and the events are stored per bar; consumers pick the column.
  `[REV-2]` A change of basis replaces the series.
- JSONB snapshots for slow data. `[REV-18]` In v1 the snapshot is the `.info` dict itself.
- Intraday refresh = 2 min for the hot set (founder decision), EOD for the rest;
  adaptive when hot_count exceeds the per-minute job budget (§8).
- `[REV-5]` Web runtime never writes market tables; a narrow writer role does. Price: the first view
  of a never-seen instrument in the cloud edition takes one job round trip.
- Statements fetched from Twelve Data only for instruments Shibui does not cover.
- Estimates/recommendations/price targets/institutional holders are not moved to
  Twelve Data (Ultra/Enterprise-only, 20–1500 credits each).
- **Stale refresh**: `[REV-18]` v1 — worker thread behind a deadline (today's mechanism, local,
  always-on process); cloud — "mark due, drained by a job", never in-request threads.
- **Shibui stays outside the store in v1** (direct calls as today). **Valuation history / 5-year
  average P/E remains Shibui-only, exactly as today.**
- **First view of a new or imported portfolio** (cloud wave): import commit and broker sync
  call `ensure_instruments(tickers)`, `[REV-8]` inside the per-workspace daily cap. The dashboard
  shows `pending` for those tickers and, for T212 users, falls back to the
  `broker_positions.current_price` snapshot (≤ 25 h) meanwhile.
- **Tickers the provider cannot price:** `[REV-21]` today's behaviour stays — `price_status:
  "missing"`, valued at 0, flagged in the UI and in portfolio alerts.
- **Local edition uses the store too.** `PORTFYL_MARKET_STORE=off` is a migration flag, removed
  when the in-memory-only path is deleted.
- **`hot` tier** (cloud wave) = instrument held by a workspace with an authenticated session in
  the last 7 days, or viewed on a detail page in the last 24 h.
- `[REV-21]` **Freshness fields** are the existing ones; `prices_refreshing` is the only addition in v1.
- `[REV-22]` ~~Startup FX backfill moves onto the store~~ — there is no startup backfill; `fx.py`
  moves as described in §12.
- `[REV-11]` v1 instrument key = Yahoo-notation symbol.
- `[REV-10]` ILA and ZAc are added as sub-units — a behaviour change for such holdings (today they
  are valued 100× too high).

## 16. Open questions for the founder

Answered and closed (kept for the record): intraday freshness = 2 minutes for hot instruments
(2026-11-08); target plan = Twelve Data Venture (2026-11-08); Wave 3 ships to local only
(2026-11-08); ETFs on Venture get no profile/statistics data (verified 2026-11-12, §7).

Open — each blocks the cloud wave, none blocks v1:

- **D-1. Europe is end-of-day on Venture** (Prague, Xetra, London, Paris, Amsterdam; verified).
  The 2-minute decision therefore covers US listings only, and a Czech user sees yesterday's close
  all day — less than yfinance shows now. Options: (a) accept EOD for Europe and label it;
  (b) buy the Cboe Europe real-time add-on (price unknown; ask); (c) compare a second vendor
  (EODHD) before signing. Recommendation: ask Twelve Data for the add-on price and get an EODHD
  quote, as the repo's own RFI note planned; decide on numbers.
- **D-2. Venture gaps:** Warsaw is not included (Vienna and Tokyo unclear), statement history is
  limited below Ultra, no ETF data. Options: accept and show "not available"; or price Ultra /
  Enterprise for comparison. Recommendation: accept for launch, list the gaps in the product copy.
- **D-3. Neon plan.** The cloud wave needs the database awake through the US session (34.6
  CU-hours/month at the smallest size) on top of normal traffic; Free allows 100. Options:
  (a) Launch, pay-as-you-go ($0.106 per CU-hour, no minimum — a few dollars a month at this size);
  (b) stay on Free and refresh hot prices every 15 minutes with the database allowed to sleep
  between; (c) stay on Free with EOD only. Recommendation: (a).
- **D-4. Written answers from Twelve Data** (not legal advice — for the founder/lawyer): how long
  Venture may store data and whether an indefinite daily-history table counts as "temporary
  caching" (Terms 2.3(g) names no period); that a standard plan cannot be billed overage (5.2(c));
  that 2-minute polling within the minute quota is acceptable (12.4(c), 2.3(h)); what exchange fees
  or non-professional declarations apply to showing US real-time prices to end users (3.1, 3.3);
  the attribution wording and link. Recommendation: send before any cloud work.
- **D-5. Residual demand inference** (§11): accept it as documented, or pay for the hardening
  (delay every first view per workspace of a non-seeded instrument by one retry). Recommendation:
  accept for the beta, revisit before public launch.
- **D-6. Seed universe:** approve the rule in §7.1 or supply a list. Recommendation: the rule.
- **D-7. Keep the 2-minute cadence?** It is ~92 % of the credit spend and the only reason the
  database stays awake all session. Options: keep; 10–15 minutes (≈ 165,000–245,000 credits a
  month); 2 minutes only while a holder is online. Recommendation: keep the decision, but build the
  interval as a knob and start at 15 minutes until the first paying users ask for more.

## 17. Not verified (research gaps)

Closed by the 2026-11-12 check (see review §4): credit costs and plan levels of every endpoint in
§7; `/earnings_calendar` = 40 per request, 1,200 records; batching exists and is billed per symbol;
credit headers; fixed-minute reset; no daily cap; Venture price; Prague/Xetra = EOD; terms wording.

Still open:

- Maximum symbols per `/quote` or `/time_series` batch (not documented; `demo` rejects batches).
- The 429 response body; paid-tier latency.
- Minimum plan and non-US coverage of `/earnings_calendar`.
- How many periods of statements Venture returns.
- Whether Twelve Data adjusts `previous_close` on a split day (not needed after REV-2).
- Whether `adj_close` can be derived from `adjust=splits` bars plus `/dividends` to Yahoo's
  precision, or needs the second call — shadow mode.
- Everything in D-4.
- Which database role the owner's local `.env` connects as (decides whether v1 needs
  `MARKET_WRITER_DATABASE_URL`); the current Neon plan.
