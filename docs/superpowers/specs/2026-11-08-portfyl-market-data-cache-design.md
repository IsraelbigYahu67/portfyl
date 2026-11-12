# Market-data cache in PostgreSQL — design

Date: 2026-11-08 · Status: **draft for founder review** · Next step after approval: `superpowers:writing-plans`

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

## 2. Goals, non-goals, anti-goals

Goals
- Dashboard and stock detail served from PostgreSQL with no provider call when
  data is within its freshness window.
- Credits consumed ≈ distinct instruments × refresh frequency, tunable by knobs.
- Provider-agnostic: the same store works in front of yfinance first and in front
  of Twelve Data later; switching is a flag, not a rewrite.
- Every number shown can say how old it is (`as_of`) and where it came from.
- Never exceed the provider's per-minute budget; degrade to stale data, never to
  errors.

Non-goals
- Real-time streaming / WebSocket (1 WS credit per symbol, capped at 500 on Pro;
  portfolio views do not need ticks).
- Intraday candles/history for charts (daily closes only).
- Replacing Shibui (US fundamentals, ownership, insiders stay there).
- Changing valuation methodology (valuation keeps the **5-year average P/E**, see
  CLAUDE.md; locally derived "current P/E" is display only).

Anti-goals (a failure even if it "works")
- Any tenant-specific data (positions, quantities, who holds what) in these
  tables, or any way for one tenant to learn what another holds/views.
- A request path that can still burn unbounded credits (arbitrary ticker strings,
  refresh buttons that bypass the cache, hover prefetch that calls the provider).
- Silently showing stale numbers as if live.

## 3. Current state (facts, from code reading 2026-11-08)

- No price/FX/history/info tables exist. Only `transactions.fx_to_czk` and
  `broker_positions.current_price` (T212 snapshot, 25 h freshness) are persisted.
- In-memory caches: `market_data.py` info (300 s ok / 60 s empty, 6 h stale
  fallback, 1024 entries), `download()` (300 s, 128 entries), `ticker_attrs`
  (6 h), `fx._DAILY_CACHE` (6 h), `/market/fx` (`ttl_cache` 600 s), others.
- Call sites that talk to the provider directly: `routers/market.py` (quote,
  history, fundamentals, dividend growth via `dividend_growth.py`),
  `routers/portfolio.py` (summary, holdings, movers, heatmap, earnings,
  insider-buys, dividends, forecast, benchmarks), `analytics.py` (performance,
  risk, sector), `fx.py`, `jobs.py` (`_next_dividend_info` calls `yf.Ticker`
  directly, no gate/timeout), `alerts.py`, `broker_cash.py`.
- Symbol handling is inconsistent: summary/movers pass raw broker tickers to
  `download`, heatmap/performance pass `yf_symbol(...)` (`ticker_map.py`).
- Jobs run via Cloud Scheduler → `/internal/jobs/*` (OIDC verified,
  `with_job_lock` advisory lock, `JOB_DATABASE_URL`), schedules in
  `deploy/operations.json`. Cross-tenant job work iterates workspaces and sets
  `portfyl.workspace_id` per workspace (`jobs.py`).
- Migrations: Alembic head `0025_stripe_billing`; runtime role `portfyl_runtime`
  gets explicit per-table grants; tenant tables use forced RLS.

## 4. Principles

1. **PostgreSQL is the source of truth for market data; memory is only an L1.**
2. **Request path = read DB.** Stale data is returned (flagged) and refreshed in
   the background (stale-while-revalidate). Only a true miss may trigger a
   synchronous fill, under budget and lock.
3. **One gateway.** All market-data reads go through one module
   (`backend/market_store/`); routers/analytics/jobs stop importing `yfinance`
   or `market_data` directly.
4. **Freshness by data type**, not one TTL for everything (§7).
5. **Store raw facts, derive the rest locally** (market cap,
   P/E, yield, 52-week range) so price-dependent figures never need a provider
   call.
6. **Provider-neutral schema.** Provider is a column and an adapter, not a table
   name.
7. **Global public data only.** No `workspace_id`; nothing about users.

## 5. Data model (new Alembic revision `0026_market_data_store`)

All tables are global (no tenant column). UUID `public_id` is not needed (never
exposed by id); internal `bigint` ids are fine because nothing serializes them.
Provider-neutral names; `source` records which adapter wrote a row.

### 5.1 Reference

`market_instrument`
- `id` PK, `symbol_key` UNIQUE (canonical, e.g. `AAPL:XNAS`, `CEZ:XPRA`,
  `USD/CZK`), `kind` (`stock|etf|fund|index|fx|crypto`), `name`, `exchange_mic`,
  `currency`, `country`, `isin`, `status` (`active|delisted|unresolvable`),
  `data_latency` (`realtime|delayed|eod`), profile fields (`sector`, `industry`,
  `description`, `employees`, `website`), `profile_fetched_at`, `history_fetched_at`, `created_at`.

`market_instrument_alias`
- `alias` PK (broker ticker such as the T212 form, bare `AAPL`, yfinance symbol,
  Twelve Data `SYMBOL:MIC`), `instrument_id` FK, `alias_kind`. This replaces
  today's scattered `yf_symbol` / raw-ticker mix with one resolver.

### 5.2 Prices and events

`market_price_daily` — PK (`instrument_id`, `trade_date`): `open, high, low,
close, volume`, `basis = 'split_adjusted'`, `source`, `fetched_at`.
Basis: this is the same basis as today's `performance` input (yfinance `Close`
with `auto_adjust=False` is split-adjusted but not dividend-adjusted) and as
Twelve Data's default `adjust=splits`. Rows fetched before a split are therefore
on a different basis than rows fetched after it, so **a new split triggers a
full history refetch** of that instrument (1 credit; tracked by
`market_instrument.history_fetched_at`). Dividend and split events are stored for
the dividend features, not to rebuild prices.

`market_price_latest` — PK `instrument_id`: `price, previous_close, change,
percent_change, week52_low, week52_high, volume, average_volume, currency,
is_market_open, quote_time` (provider timestamp), `is_eod`, `source`,
`fetched_at`.

`market_dividend_event` — PK (`instrument_id`, `ex_date`): `amount, currency,
source, fetched_at`.
`market_split_event` — PK (`instrument_id`, `split_date`): `from_factor,
to_factor, source, fetched_at`.

FX pairs are `market_instrument` rows with `kind='fx'` and reuse the same price
tables (no separate FX schema). `transactions.fx_to_czk` keeps its role (trade-date
rate stamped at import) and is not touched.

### 5.3 Slow-moving blobs

`market_snapshot` — PK (`instrument_id`, `kind`): `payload` JSONB, `schema_ver`
int, `source`, `fetched_at`, `fresh_until`, `next_refresh_after`.
`kind` ∈ `statistics`, `income_annual`, `income_quarterly`, `balance_annual`,
`balance_quarterly`, `cashflow_annual`, `cashflow_quarterly`, `earnings_dates`,
and (kept on current sources, see §7) `estimates`, `recommendations`,
`price_target`, `institutional_holders`, `insider_transactions`.
JSONB on purpose: these are consumed whole by the stock page; only hot fields
(§5.2) are typed columns. **The payload is a canonical, provider-neutral shape,
not the provider's.** Each adapter (yfinance, Twelve Data, Shibui) normalizes into
the same structure and consumers (`_ratios_from_info`, `_metric_block`, the
valuation builders) read only that. The canonical shapes are designed in Wave 2A
from what the consumers need today; this is the largest sizing risk in the plan
and the reason the yfinance adapter comes first. `schema_ver` lets a shape change
not break old rows. The raw provider response is not stored.

### 5.4 Operations

`market_fetch_state` — PK (`instrument_id`, `kind`): `status`
(`ok|empty|error|unsupported`), `attempts`, `last_error`, `last_attempt_at`,
`next_attempt_at`. **Negative caching**: "no data" / "unsupported for this plan"
is remembered (e.g. 24 h → 7 d with backoff) so dead tickers don't burn credits.

`market_demand` — PK `instrument_id`: `last_viewed_at`, `held_flag`,
`tier` (`hot|warm|cold`), `updated_at`. Written by the request path (touch on
detail view) and by the demand job (held set). **Requirement:** tenants must not
be able to read this table through any API or grant (it leaks "someone holds/views
X"). The builder picks the mechanism (separate grants / `INSERT`-only function).

`market_budget` — PK `minute_bucket` timestamptz: `credits_used`, `cap`;
`market_provider_state` (single row): `cooldown_until`, `last_429_at`,
`credits_left_hint`. Used for the cross-instance limiter (§8).

`market_usage_daily` — PK (`day`, `endpoint`): `calls, credits, cache_hits,
cache_misses, errors` for cost visibility.

### 5.5 Grants and RLS

- These are **not tenant tables**: no `workspace_id`, no RLS policies. This is a
  deliberate exception to "RLS on every tenant table"; record the tables as
  "global reference data" in `docs/security/tenant-isolation-matrix.md` and add a
  test asserting none of them has a `workspace_id`/`user_id` column.
- `portfyl_runtime`: `SELECT` on reference/price/snapshot tables;
  `INSERT, UPDATE` where the fill-on-miss path writes; no `DELETE` and no
  `TRUNCATE`; demand/budget tables per §5.4. Jobs (`JOB_DATABASE_URL`) own
  cleanup.
- Migration is additive only (new tables) → forward-compatible with running
  instances. Update `EXPECTED_ALEMBIC_HEAD` in the same change (project rule).

## 6. Read path

```
router / analytics / job
        │  MarketStore.get_quotes([...]) / get_history() / get_profile() /
        │  get_snapshot(kind) / get_dividends() / get_fx(pair)
        ▼
 L1 in-process (30–60 s, tiny)  →  PostgreSQL tables
        │                              │
        │ fresh  ───────────────────────┘ return (data, meta)
        │ stale  → return stale + mark due (no refresh inside the request)
        │ miss   → validate symbol → budget check → advisory lock →
        │          provider adapter (timeout ≤ 3 s) → upsert → return
        │          (on timeout/429/limit: return `pending`)
```

- Return type carries `meta = {as_of, fetched_at, stale, source, pending}`; every
  API response that shows market data exposes `as_of` and `stale`.
- Batch-first API (`get_quotes(list)`) so a 30-holding dashboard is one SQL query.
- **Background refresh = "due" marking drained by a job, never in-request
  threads or `BackgroundTasks`.** Cloud Run may throttle CPU after the response
  and has frozen before on blocking work in the request process. A stale read only
  sets `next_refresh_after = now` (and touches `market_demand`); the
  `market_refresh` job (§9, every 5 min) picks due rows in priority order. No
  separate queue table is needed: `market_snapshot.next_refresh_after` and
  `market_instrument` timestamps are the queue. Only a true **miss** (no row at
  all) may fill synchronously, under the limiter and lock.
- **Single-flight:** `pg_try_advisory_xact_lock(hash(instrument_id, kind))`; the
  loser serves stale/pending instead of calling the provider.
- **Symbol validation on miss:** only identifiers resolvable through the symbol
  catalogue (`/symbol_search`, 1 credit, cached as an alias row) can create an
  instrument; free text from users never goes straight to a data endpoint.
- **Per-workspace limit on cold fills** (e.g. N new instruments per hour) using
  the existing rate-limiting infrastructure.
- The refresh button and hover prefetch become "request revalidation" with a
  per-instrument cooldown (default 5 min); they never bypass the store.

## 7. Refresh policy (defaults; all are config knobs)

Credit costs are from the official docs (quoted in the research log, 2026-11-08).

| Data | Endpoint (credits) | Freshness / trigger | Notes |
|---|---|---|---|
| Latest price | `/quote` (1/symbol) | `hot`: every 2 min while a real-time exchange is open (founder decision; adaptive, see §8); all held: once after close | EOD-only exchanges (many EU incl. Prague, Xetra) refresh once after close |
| Daily close history | `/time_series` 1day (1, any `outputsize`) | full history once at first sight; later append yesterday's close from the daily quote pass; refetch only to repair gaps | split-adjusted (`adjust=splits`); **full refetch on any new split** |
| FX | `/quote` or `/exchange_rate` (1) | same as prices; only pairs actually needed | ~30 pairs |
| Profile | `/profile` (10) | 90 days | sector/industry/description |
| Statistics | `/statistics` (50) | **after each earnings report** (§7.1); safety net 120 days | seeded universe + instruments viewed in the last 30 days |
| Dividends | `/dividends` (20) | after each earnings report; safety net 30 days for payers, 90 days for known non-payers | feeds dividend tab and forecast |
| Splits | `/splits` (20) | **anomaly-triggered** (`previous_close` ≠ last stored close by >X%) + 90 days | avoids 20 credits × everyone monthly |
| Earnings dates / who reported | `/earnings_calendar` (**40 per request**, not per symbol) daily; `/earnings` period=next (20) only for single-instrument fills | daily watch job | drives all results-based refreshes (§7.1) |
| Statements (6 calls × 100) | `/income_statement`, `/balance_sheet`, `/cash_flow` (annual + quarterly) | once after each earnings date | **skip for instruments Shibui covers** (US common stock); Pro/Venture plan needed |
| Estimates, recommendations, price targets, institutional holders | 20 / 100 / 75 / 1500 | **not fetched from Twelve Data** | Enterprise-only; remain on Shibui/yfinance behind the same store, or are dropped |
| Insider transactions | `/insider_transactions` (200) | on click, 24 h | Shibui first for US |

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
- Universe: a list of several hundred instruments approved by the founder.
  Suggested sources (my guess, to be confirmed): tickers held in the owner's
  portfolios, the most common Trading 212 / IBKR holdings, and heavyweights of
  major indices (e.g. S&P 500, DAX, PX). Open question §16.6.
- Per instrument: resolve and store aliases (this validates the symbol mapping up
  front), `/profile`, full daily history, `/dividends`, `/splits`,
  `/statistics`, next earnings date. Statements (6 × 100) only for instruments
  Shibui does not cover.
- One-off cost per instrument ≈ 122 credits (1 + 1 + 10 + 50 + 20 + 20 + 20) plus
  600 for statements where needed. Example: 300 US names ≈ 36,600 credits; 100
  non-Shibui names add 60,000. At ~340 credits/min for jobs this is roughly 1.8 h
  and 3 h respectively (run overnight, throttled by the limiter of §8, resumable
  via `market_fetch_state`).
- Benefit: the first view of any seeded company is instant for every user, and
  the dress rehearsal can run on the local edition with the free yfinance adapter
  before any credits are spent.
- Non-seeded tickers still use the on-demand fill-on-miss path (§6) and join the
  universe automatically once someone holds or opens them.

**Results-driven updates**
- Store each instrument's next report date (`market_snapshot` kind
  `earnings_dates`). Do **not** poll per instrument for it. Use one cheap
  market-wide call: `/earnings_calendar` costs **40 credits per request** (not per
  symbol; limited to 1,200 records, filterable by date, exchange, country). A daily
  `market_earnings_watch` job (§9) fetches yesterday's/today's reporters, matches
  them to our instruments, and marks `statistics`, `dividends`, the statements (if
  provider-sourced) and `earnings_dates` as due. Plan requirement for that
  endpoint was not stated on its page — verify (§17).
- Data lags the announcement. After a report, re-check at +1, +3 and +7 days until
  the latest fiscal period in the snapshot changes, then stop (bounded retries,
  recorded in `market_fetch_state`).
- Safety nets only if nothing changed: profile 90 days, statistics and statements
  120 days, dividends 30 days (some companies declare dividends outside earnings).
- Prices are unaffected: they follow §7 (2-minute hot set, EOD for the rest).
- Effect on cost (§10): statistics ≈ 4 refreshes a year, the earnings-date lookups
  drop from 20 credits per instrument to 40 credits per day for everyone.

## 8. Credit budget and protection

- **Cross-instance limiter:** before a provider call, atomically reserve credits
  in `market_budget` for the current minute
  (`INSERT … ON CONFLICT DO UPDATE SET credits_used = credits_used + :c WHERE
  credits_used + :c <= :cap RETURNING …`). `cap` = plan limit × 0.8.
- **Priority:** interactive fills may use up to the full cap; jobs only the part
  not reserved for interactive (default 30 % reserved).
- **Learn from the provider:** read `api-credits-left`/`api-credits-used`
  headers; on HTTP 429 set `cooldown_until` to the next minute boundary and serve
  stale. Circuit breaker on repeated 5xx.
- **Adaptive cadence for hot prices.** Target is a 2-minute refresh, but the real
  interval is `max(2 min, hot_count ÷ job_credits_per_minute)`. With the Venture
  plan (610/min, cap 80 % = 488, 30 % reserved for interactive → ~342/min for
  jobs) a 2-minute cycle covers ~680 hot instruments; beyond that the interval
  stretches automatically instead of hitting 429. Instruments whose exchange is
  `eod`/closed are skipped (no intraday refresh). The achieved age is exposed in
  `as_of`, so the UI never claims freshness it does not have.
- **Cost visibility:** `market_usage_daily`, surfaced in the existing subsystem
  health; alert at 70 % of monthly/minute budget.
- Batch sizes in jobs are bounded so a pass finishes inside the 300 s Cloud
  Scheduler attempt deadline and resumes next tick.

## 9. Jobs (existing pattern: `/internal/jobs/<name>`, OIDC, `with_job_lock`)

| Job | Schedule (UTC) | Does |
|---|---|---|
| `market_demand` | daily | per-workspace iteration (same pattern as the dividends job) collects the **set of distinct held tickers only**, resolves aliases, sets `held_flag`/`tier`; creates missing instruments |
| `market_prices` | every minute on weekdays (Cloud Scheduler minimum) | picks what is due (hot set targets a 2-min cadence while its exchange is open; one after-close pass for the rest), batches `/quote`, upserts latest + daily close. Running every minute keeps a Cloud Run instance warm during market hours — acceptable, but count it in cost |
| `market_refresh` | every 5 min | drains rows marked due (stale reads, new imports, expired snapshots) by priority (interactive-marked first), within the leftover budget; replaces the earlier hourly `market_slow_refresh` |
| `market_earnings_watch` | daily, after US close | one `/earnings_calendar` request (40 credits, split by country/exchange if over 1,200 records); matches reporters to our instruments and marks their slow data due (§7.1) |
| `market_cache_gc` | daily | drops snapshots of instruments not requested for 180 days; downgrades tier; trims `market_budget` |

Add the five entries to `deploy/operations.json`. The one-off `market_seed`
command (§7.1) is an admin command, not a scheduled job. In the **local edition** there is
no Cloud Scheduler; the same job passes are driven by the existing in-process
asyncio loop in `main.py` (like alerts/dividends today). The Discord dividend job
(`jobs._next_dividend_info`) and alerts read through the store instead of calling
`yfinance`.

## 10. Cost model (with stated assumptions)

Assumptions: 1,000 distinct held instruments, 300 "hot", 300 with a detail page
opened per month, 30 pairs of FX, 22 trading days, US data real-time, 10 % of
detail-opened instruments not covered by Shibui.

| Item | Credits / month |
|---|---|
| Daily latest/close for all held (1,000 × 22) | 22,000 |
| 2-minute intraday for hot (300 × 210 refreshes/day × 22) | 1,386,000 |
| FX (30 × 8 × 22) | 5,300 |
| Profile (refresh 90 d + new) | ~3,300 |
| Statistics (300 × 50, ~4 refreshes/yr after results) | ~5,000 |
| Dividends (payers 30 d safety net, others 90 d) | ~14,700 |
| Splits (anomaly-triggered) | ~1,000 |
| Earnings calendar (40/day × 22) | ~900 |
| Statements for non-Shibui (30 × 600 / quarter) | ~6,000 |
| **Total (steady state, excl. one-off seed)** | **≈ 1.44 M ≈ 33 credits/min average, ≈ 190/min during the US session** |

(The earlier hourly-intraday variant would have been ≈ 150,000/month; the 2-minute
cadence chosen by the founder makes the hot-price pass ~93 % of all spend.)

For comparison the naive port costs ≈ 2,500 credits per cold dashboard open and
repeats it every 5 min per user. A 610 credits/min plan (Twelve Data Venture,
$149/mo, needed for commercial display) has ≈ 26 M credits/month of headroom (the plan above uses ≈ 6 %); the constraint
is the **per-minute** budget (hot prices alone take ≈ 150/min of the ~342/min job
share at 300 hot instruments), hence the limiter and the adaptive cadence (§8).

## 11. Security, privacy, compliance

- Tables hold public market data only; see §5.5 for isolation tests (Alice/Bob
  matrix gains "market tables contain no tenant columns" and "tenant cannot read
  `market_demand`").
- Provider receives only instrument identifiers and our API key — no user data.
  Still update `docs/compliance/data-processing-inventory.md` for the new
  processor (Twelve Data) and check the commercial-use/display terms of the
  chosen plan before cloud launch.
- No secrets in tables; the provider key stays in the existing secret store.

## 12. Application changes

Backend
- New package `backend/market_store/`: `models`, `store` (read API), `service`
  (SWR, locks, limiter), `adapters/yfinance.py`, later `adapters/twelvedata.py`,
  `resolver` (alias → instrument; replaces ad-hoc `yf_symbol` use).
- Replace direct provider usage in: `routers/market.py`, `routers/portfolio.py`,
  `analytics.py`, `fx.py`, `dividend_growth.py`, `jobs.py`, `alerts.py`,
  `broker_cash.py`. Delete the in-memory info/download caches once migrated.
- Feature flags: `PORTFYL_MARKET_STORE=on|off` (off = old behaviour while
  migrating), `PORTFYL_MARKET_PROVIDER=yfinance|twelvedata`.

Frontend
- Show `as_of` / "stale" on prices and ratios; a `pending` state for first-time
  tickers with short polling.
- Stop `StockOverviewTab` auto-fetching the `financials` view; keep tabs lazy.
- `useStockIntentPrefetch` becomes harmless (reads the store).
- Refresh button triggers revalidation, not provider calls.

## 13. Rollout (waves; each wave owns disjoint files — parallel-session rules)

1. **Wave 1 (single owner of migrations):** migration `0026`, models, grants,
   `EXPECTED_ALEMBIC_HEAD`, isolation tests.
2. **Wave 2 (parallel, disjoint files):** (A) `market_store` core + yfinance
   adapter + resolver; (B) jobs + `operations.json` + limiter/budget; (C)
   frontend `as_of`/pending components.
3. **Wave 3 (sequential per hotspot file):** migrate `routers/market.py`, then
   `routers/portfolio.py`, then `analytics.py`/`fx.py`/`jobs.py`/`alerts.py`. At
   this point the cache is in front of **yfinance** — performance win, zero credit
   cost, easy rollback. **Local edition only**; in cloud the flag stays off until Wave 4.
4. **Wave 4:** Twelve Data adapter, one-off seed run (§7.1; rehearsed earlier on
   local with the yfinance adapter), symbol mapping (`SYMBOL:MIC`), shadow mode
   (call both, compare fields, log diffs), then flip `PORTFYL_MARKET_PROVIDER`.
5. **Wave 5 (optional, later):** remove yfinance code paths.

Each wave: re-integrate upstream, re-run tests, check `alembic heads` vs
`EXPECTED_ALEMBIC_HEAD`, run the PostgreSQL suite in `backend/tests/postgres/`.

## 14. Verification

- Unit: freshness logic, SWR, negative caching, limiter arithmetic, split/anomaly
  trigger, derived-metric formulas (incl. missing inputs → null).
- PostgreSQL integration: concurrent single-flight (N sessions, one provider
  call), grants (runtime cannot DELETE; tenant cannot read demand), migration
  up/down, no-tenant-columns assertion.
- Provider adapters against recorded fixtures; one contract test against the live
  `demo` key for the endpoints it allows (`/quote`, `/time_series`, `/profile`,
  `/statistics`, `/dividends`, `/income_statement`).
- Metrics to watch after launch: cache hit rate, credits/day vs budget, p95 of
  dashboard and stock-detail endpoints, share of `pending` responses.

## 15. Calls I made (check these)

- Provider-neutral store first, in front of yfinance, Twelve Data later (my call:
  de-risks the migration and gives the speed win immediately).
- Split-adjusted closes (today's basis); full history refetch on a new split.
- JSONB snapshots for slow data; typed columns only for hot fields.
- Intraday refresh = 2 min for the hot set (founder decision), EOD for the rest;
  adaptive when hot_count exceeds the per-minute job budget (§8).
- Runtime role may write the cache tables (fill-on-miss); alternative is
  job-only writes with an enqueue table — simpler product, slower first view.
- Statements fetched from Twelve Data only for instruments Shibui does not cover.
- Estimates/recommendations/price targets/institutional holders are not moved to
  Twelve Data (Enterprise-only, 75–1500 credits each).
- **Stale refresh** is "mark due, drained by the 5-minute `market_refresh` job",
  never in-request threads (§6). Only a true miss fills synchronously.
- **Canonical snapshot payloads**, adapters normalize (§5.3); designed in Wave 2A.
- **Shibui stays outside the store in v1** (direct calls as today); caching Shibui
  data as extra snapshot kinds is a later step. **Valuation history / 5-year
  average P/E remains Shibui-only, exactly as today**: instruments Shibui does not
  cover keep the current degraded behaviour, no regression and no new source.
- **First view of a new or imported portfolio:** import commit and broker sync
  call `ensure_instruments(tickers)`, which creates instrument rows and marks them
  due with interactive priority (outside the per-workspace cold-fill cap, but
  limited to 200 tickers per import). The dashboard shows `pending` for those
  tickers and, for T212 users, falls back to the `broker_positions.current_price`
  snapshot (≤ 25 h) meanwhile. A one-off `market_demand` run backfills existing
  holdings at cutover.
- **Tickers the resolver cannot map** (`status='unresolvable'`): the position row
  stays visible with cost basis, price shows "unavailable", it is excluded from
  market-value totals with a visible notice, and the user can correct the ticker.
  (Product behaviour is my default; change if you disagree.)
- **Local edition uses the store too** (§9: in-process loop instead of Cloud
  Scheduler). `PORTFYL_MARKET_STORE=off` is a **temporary** migration flag,
  removed in Wave 5; it is not a permanent fallback.
- **`hot` tier** = instrument held by a workspace with an authenticated session in
  the last 7 days, or viewed on a detail page in the last 24 h. The 300-of-1,000
  cost assumption in §10 depends on this definition.
- **`as_of` / `stale` / `pending` are added to existing response shapes as
  optional additive fields** (no API versioning); clients that ignore them keep
  working.
- **Startup FX backfill** (`fx.bulk_fetch_fx`) moves onto the store with the rest
  of `fx.py`.

## 16. Open questions for the founder

1. ~~Intraday freshness?~~ **Answered 2026-11-08:** every 2 minutes for frequently
   viewed instruments while the exchange is open (the provider limit resets each
   minute). Costs and limits in §8/§10.
2. ~~Target plan?~~ **Answered 2026-11-08:** Twelve Data Venture $149 (610/min, no
   analyst data).
3. For exchanges that are EOD-only at the provider (Prague, Xetra, London on
   Grow), is "price as of yesterday's close" acceptable in the UI?
4. Should ETFs/funds (many T212 holdings) show profile/statistics-like data? The
   stock endpoints may not cover them; ETF endpoints cost 200 credits and need
   Ultra/Enterprise. Not verified.
6. **Seed universe (§7.1):** which several hundred companies go into the first
   bulk load? Suggested: owner's holdings + most common T212/IBKR holdings + index
   heavyweights. The founder supplies or approves the list.
5. **Release gate for Wave 3** (cache in front of yfinance): a persistent shared
   database of Yahoo-sourced data served to paying tenants is a different legal
   exposure from today's per-process cache, and commercial market-data rights are
   still open (Workstream A). May Wave 3 ship to cloud users, or only to the
   owner/dev until Twelve Data (Wave 4) replaces yfinance? Until answered, Wave 3
   is behind `PORTFYL_MARKET_STORE`, default off in cloud.
   **Answered 2026-11-08: local edition only for now.** Wave 3 ships to local;
   cloud keeps the flag off until Wave 4 (Twelve Data) is licensed and live.

## 17. Not verified (research gaps)

- `/profile` and `/statistics` behaviour for ETFs/funds/non-US tickers.
- Latency of paid-tier calls (only the `demo` key was measured: 0.25–0.6 s).
- Minimum plan for `/earnings_calendar` (its page states no plan note) and
  whether it covers non-US exchanges well enough to drive §7.1.
- Whether `/quote` multi-symbol batches are accepted on the chosen plan (the
  `demo` key rejected them with 401) and the maximum symbols per request (not
  stated in the docs).
- Twelve Data terms (https://twelvedata.com/terms, read 2026-11-08) — to confirm
  with their support before cloud launch:
  - **No monthly call cap is stated** for any plan; limits are per-minute credits
    (plus 800/day on Basic only). The Terms mention "overage charges" for
    usage-based pricing without tying them to any plan or rate — confirm that a
    standard plan cannot be billed overage.
  - **Storage/caching:** storing data for internal use is allowed (2.2a), but 2.3(g)
    forbids caching "beyond permitted timeframes specified in the Documentation"
    and no such timeframes were found; 16.2 requires **deleting all Data within 30
    days after termination** (the store therefore needs a documented purge
    procedure). Derived data we create is allowed (2.2c, 6.2).
  - **Display to our users** counts as external display: needs Venture or above
    (already the target plan). Redistribution (e.g. exposing raw data via a public
    API) needs a separate add-on/agreement.
  - **Fair use:** no explicit clause, but 12.4(c) allows immediate suspension for
    "excessive usage impacting other customers" and 2.3(h) bans "excessive load";
    neither is quantified. Staying within the per-minute quota 24/7 is not
    prohibited by any text read; ask support to confirm the 2-minute polling
    pattern is acceptable.
- Whether `performance` (`actions=True`) needs more than stored dividend/split
  events to reproduce today's numbers — verify in shadow mode.
