# Market-data cache design — adversarial review

Date: 2026-11-12 · Reviews: `2026-11-08-portfyl-market-data-cache-design.md` (draft, commit `b140ecc`)
· Code read at `12dfe14` · Outcome: **the draft must not be built as written.** The revised spec
(same file, `[REV-n]` marks) and the plan `docs/superpowers/plans/2026-11-12-portfyl-market-data-cache.md`
implement the fixes below.

How to read this: every claim is labelled **VERIFIED** (seen in code, in an official page, or
computed here), **INFERRED** (logical consequence) or **UNKNOWN** (needs the founder, a lawyer or a
paid call). Line numbers are `file:line` at `12dfe14`. "Subagent" means a Sonnet agent gathered the
fact; everything a finding depends on was re-read by the reviewer unless it says otherwise.
Legal readings are **not legal advice**.

Severity: **BLOCKER** = change before the code it touches is written · **SHOULD** = change in this
design · **LATER** = note for a later wave · **NOTE**. The "Gates" column says which wave a finding
blocks: `v1` = the local-edition slice, `cloud` = anything that turns the store on in the cloud edition.

## 1. Summary of findings

| Id | Sev. | Gates | Title | Status in revised spec |
|---|---|---|---|---|
| F-01 | BLOCKER | v1 | Price basis is wrong: performance needs as-traded closes, most other pages need dividend-adjusted | Fixed, REV-1 |
| F-02 | BLOCKER | v1 | Split detection by a price-jump threshold lets mixed-basis history through | Fixed, REV-2 |
| F-03 | BLOCKER | v1 | A mid-session bar can be stored as the day's close; `/quote.timestamp` is not the quote time | Fixed, REV-3 |
| F-04 | BLOCKER | v1 | The advisory transaction lock cannot survive the project's own connection-release rule | Fixed, REV-4 |
| F-05 | BLOCKER | v1 | Runtime role writes global tables; "jobs own cleanup" assumes a job role that does not exist | Fixed, REV-5 |
| F-06 | BLOCKER | cloud | The job schedule keeps Neon awake around the clock (182.5 CU-h vs 100 free) | Fixed, REV-6 |
| F-07 | BLOCKER | cloud | On Venture every European exchange is end-of-day; the 2-minute decision covers US only | Open → founder (D-1) |
| F-08 | BLOCKER | cloud | Twelve Data permits "temporary caching"; the store keeps history indefinitely | Open → founder/lawyer (D-4) |
| F-09 | SHOULD | cloud | `market_demand` is observable through timing, freshness and negative-cache state | Redesigned, REV-7; residual risk recorded |
| F-10 | SHOULD | v1 | Free-text tickers and imports can inflate the universe and burn credits; the caps do not exist yet | Fixed, REV-8 |
| F-11 | SHOULD | v1 | Isolation tests named in the draft are not enough | Fixed, REV-9 |
| F-12 | SHOULD | v1 | Minor currency units: only GBX is handled; ILA and ZAc are quoted 100× | Fixed, REV-10 |
| F-13 | SHOULD | v1 | Identity: `alias` as a primary key is wrong; `SYMBOL:MIC` is not needed in v1 | Fixed, REV-11 |
| F-14 | SHOULD | v1 | No sanity bounds; an empty answer would overwrite a good price | Fixed, REV-12 |
| F-15 | SHOULD | — | Cost model: four wrong figures, one misleading headline | Fixed, REV-13 |
| F-16 | SHOULD | cloud | Budget row: no refund rule, wrong clock, hot row | Fixed, REV-14 |
| F-17 | SHOULD | cloud | Five new jobs collide with `RECURRING_JOB_NAMES`, `/health` and the 300 s deadline | Fixed, REV-15 |
| F-18 | SHOULD | v1 | Local loop is safe, but job sessions are not auto-released before outbound calls | Fixed, REV-16 |
| F-19 | SHOULD | v1 | No rollback, purge or success metric per wave | Fixed, REV-17 |
| F-20 | SHOULD | v1 | Scope: 12 tables and a canonical shape per kind is too big for v1 | Fixed, REV-18 (thin slice) |
| F-21 | SHOULD | v1 | The waves are not file-disjoint and §12 misses 12 files | Fixed, REV-19 |
| F-22 | SHOULD | cloud | Seed is not resumable as described and has no universe | Fixed, REV-20 |
| F-23 | SHOULD | v1 | A price-freshness contract already exists end to end; the draft invents a second one | Fixed, REV-21 |
| F-24 | SHOULD | v1 | §3 "facts" that are wrong or stale | Fixed, REV-22 |
| F-25 | SHOULD | cloud | Alerts and FX stamping must never consume stale or provisional values | Fixed, REV-23 |
| F-26 | SHOULD | cloud | Venture: no ETF data, limited statement history, Warsaw absent, US feed ≈ 5 % of volume | Open → founder (D-2) |
| F-27 | LATER | cloud | Earnings-calendar-driven refresh rests on unverified non-US coverage | Kept behind a safety net, REV-24 |
| F-28 | LATER | cloud | Caching `/market/fundamentals` payloads may leak plan-gated content | Deferred, REV-18 |
| F-29 | SHOULD | v1 | Compliance records describe the cache as "not durable" | Fixed, REV-25 |
| F-30 | NOTE | — | Pre-existing: `billing_reconcile` is missing from `RECURRING_JOB_NAMES` | Out of scope; reported |
| F-31 | NOTE | — | Smaller items | — |

Parts of the draft that are right (one line each, no change): provider-neutral store first and
yfinance before Twelve Data (§15); JSONB for slow data; no WebSocket; Shibui outside the store;
additive migration; "mark due, drained by a job, never `BackgroundTasks`" **for the cloud edition**;
keeping `transactions.fx_to_czk` untouched; Wave 3 local-only (it matches the monetization plan,
see F-08).

## 2. Attack list — one line per item

| # | Item | Answer |
|---|---|---|
| A1 | `market_demand` leak, side channels | Not enough. Timing (`pending` vs instant), quote freshness and negative-cache state all reveal "someone else asked for X". → F-09 |
| A2 | Runtime role writes global tables | Real cross-tenant write vector, and the draft's own cleanup rule contradicts the deployed roles. Recommend a separate narrow writer role + job-only writes + enqueue table. → F-05 |
| A3 | Universe poisoning | Possible today: `/market/quote/{ticker}` and `/market/history/{ticker}` take any string, imports have no ticker cap, rate limits are cloud-only and rule-per-env-var. → F-10 |
| A4 | "No tenant columns" test | Necessary, not sufficient. → F-11 |
| B5 | Split-adjusted basis | Wrong premise and unsafe detection. → F-01, F-02 |
| B6 | Today's daily row | Confirmed against the live `demo` key: the first `/time_series` bar is today's in-progress bar. → F-03 |
| B7 | Currency units, FX direction | GBX handled; ILA/ZAc not. FX direction is consistent (`XXXCZK=X` = CZK per 1 XXX). → F-12 |
| B8 | Identity | `SYMBOL:MIC` + alias table is a Twelve Data concern; `alias` alone cannot be a key. → F-13 |
| B9 | Garbage in | No bounds anywhere in the draft; the code base already records an FX poisoning incident. → F-14 |
| B10 | Recompute §10 | Done by script, §5 below. 195 not 210 refreshes; 1.29 M not 1.44 M; splits 6,667 not 1,000; "6 % of headroom" is the wrong yardstick. → F-15 |
| C11 | Advisory lock across a provider call | Unworkable here, for a reason worse than the one the prompt names. → F-04 |
| C12 | `market_budget` upsert | Fixable; needs DB clock, no refunds, header reconciliation. → F-16 |
| C13 | Neon compute of the per-minute job | 182.5 CU-h/month at the smallest compute for the draft's schedule; Free allows 100. → F-06 |
| C14 | Five scheduler jobs | Names must be registered in three places or the job returns 500; `/health` cannot express a weekday-only job. → F-17 |
| C15 | Local in-process loop | Fine: `_periodic_loop` → `asyncio.to_thread` → `run_on_private_loop` (`main.py:348-384`). One gap. → F-18 |
| C16 | Observability, kill switches | Missing. → F-19 |
| D17 | Too big for v1? | Yes. Thin slice = 3 tables, no jobs, no budget, store placed *under* `market_data.py`. → F-20 |
| D18 | File-disjoint waves? | No. → F-21 |
| D19 | Seed | Needs its own progress rows and an approved list. → F-22 |
| D20 | Frontend | Reuse `price_status`/`price_as_of`; one-shot refetch instead of polling; 8 dictionaries per new string. → F-23 |
| E21 | Legal | Three items for the founder/lawyer. → F-08, F-26, F-29 |

Failure classes the list missed, added here: alerts and FX stamping reading stale data (F-25);
plan-gated payloads in a global cache (F-28); provider "empty" overwriting a good value (F-14);
the wrong `/quote` timestamp field (F-03); attribution duty for displayed data (F-08, D-4).

## 3. Findings in detail

### F-01 — Price basis is wrong (BLOCKER, v1)

**Evidence (VERIFIED).** Draft §5.2: "`basis = 'split_adjusted'` … the same basis as today's
`performance` input". The performance input is not split-adjusted. `routers/analytics.py:46-52`
downloads with `auto_adjust=False, actions=True`, then `:71-82` multiplies every close by the product
of all *later* split ratios — it **undoes** Yahoo's split adjustment, because the ledger holds the
share count valid on each historical day (docstring `:34-42`). The exception is a T212 API ledger that
was already rescaled (`_ledger_normalized_splits`, `:90-122`). Every other history call uses
`auto_adjust=True`, i.e. **dividend-adjusted** closes: `fx.py:48-54`, `routers/portfolio.py:2471`
(2-day change), `:2545` (movers), heatmap and benchmarks (subagent: `:2631`, `:2635`, `:2710`),
`routers/analytics.py:155`, `:911`; `routers/market.py:1048` uses `Ticker.history`, whose default is
also dividend-adjusted. Draft §5.2 also says "Dividend and split events are stored for the dividend
features, not to rebuild prices" — the split events are exactly what rebuilds the as-traded series.

**Why it matters.** Owner holds 10 NVDA bought before the 10:1 split of June 2024, imported by CSV
(as-traded share counts + split rows). The store returns split-adjusted closes and a reader that
trusts §5.2 values the pre-split days at 10 shares × ~$120 instead of 10 × ~$1,200: the performance
chart shows a −90 % cliff that never happened. In the other direction, a 1-month heatmap window over
an ex-dividend date changes by the dividend yield (~0.5–1 %) once the basis silently moves from
dividend-adjusted to split-only.

**Fix.** One daily row carries both provider bases and the events, exactly as one
`yf.download(auto_adjust=False, actions=True)` call returns them: `close` (split-adjusted),
`adj_close` (split- and dividend-adjusted), `split_ratio`, `dividend`. `auto_adjust=True` consumers
read `adj_close`; correlation/basket read `close`; `_load_close_panel` keeps its existing un-adjust
code and reads `close` + `split_ratio`. Result: v1 numbers are identical to today's by construction.
No `basis` column. For Twelve Data later: `adjust=splits` → `close`, `adjust=all` → `adj_close`
(2 credits per symbol per refresh instead of 1; decided in shadow mode).

### F-02 — Split detection by threshold (BLOCKER, v1)

**Evidence.** Draft §7: splits are "anomaly-triggered (`previous_close` ≠ last stored close by >X %)
+ 90 days"; §5.2: "a new split triggers a full history refetch". INFERRED: any `X` large enough to
ignore earnings gaps (say 25 %) misses a 5:4 split (−20 %) and a 5 % stock dividend; any smaller `X`
fires on every bad earnings day. Whether Twelve Data adjusts `previous_close` on the split day is
UNKNOWN. A dividend is never an "anomaly", yet it rescales every earlier `adj_close` (F-01). The draft
does not say what a reader sees during the refetch.

**Why it matters.** 5:4 split on Monday; the daily pass appends Monday's post-split close under
rows on the old basis; volatility, 1-month change and performance show a phantom −20 % day for up to
90 days.

**Fix — verify, then append.** Every tail refresh fetches the last ~30 daily bars (1 credit at Twelve
Data, same as an append — `/time_series` costs "1 per symbol" independent of `outputsize`, VERIFIED
§4). For every date present both in the store and in the fetch, `close` and `adj_close` must agree
within 1e-4 relative. Agreement → insert only the new completed bars. Any disagreement, or no
overlapping date → **replace the whole series** of that instrument in one transaction (instrument row
locked `FOR UPDATE`, delete, bulk insert). Any split or dividend rescales the bars before it, so it is
always inside the overlap; no threshold, no `/splits` polling, no anomaly rule. Readers run one
`SELECT` per panel under READ COMMITTED and therefore see the old or the new series, never a mix.

### F-03 — Provisional vs final daily bar (BLOCKER, v1)

**Evidence (VERIFIED).** Live `demo` key, 2026-11-12 18:53 UTC (market open):
`/time_series?symbol=AAPL&interval=1day&outputsize=3` returned a first bar dated `2026-11-12` with
volume 917,677 against a 51.9 M average — the in-progress bar. `/eod` returned `2026-11-11`. Today's
code does the same with Yahoo: `routers/portfolio.py:2471` and `:2545` take the last row of a daily
download and nothing excludes a running session (subagent, spot-checked). In memory that error
expires in 300 s (`market_data.py:95`); in a table it is permanent. Separately, Twelve Data documents
`/quote.timestamp` as "Unix timestamp representing the opening candle of the specified interval" and
`last_quote_at` as "Unix timestamp of last minute candle open" (docs/market-data) — draft §5.2's
`quote_time (provider timestamp)` does not say which.

**Why it matters.** The process stops at 14:00 with a bar for today in the table; it restarts next
week offline. The performance chart shows 14:00's price as that day's close forever. With the wrong
timestamp field the UI would stamp every US quote "15:30", the session open.

**Fix.** `market_price_daily` holds **completed sessions only**, enforced in the schema:
`CHECK (trade_date < (fetched_at AT TIME ZONE 'UTC')::date)`. A bar becomes storable on the first
fetch after UTC midnight following its session. This is exact for every exchange whose regular session
does not cross UTC midnight on the closing side (Americas close by 21:00 UTC; Asia/Pacific sessions
are dated *ahead* of UTC, so they are held back, never stored early) — no time-zone or holiday table
needed, half days and holidays need no special case. "Today" is supplied at read time from the stored
quote and is never written to the daily table. Quote time = `last_quote_at` (Twelve Data) /
`regularMarketTime` (Yahoo).

### F-04 — Advisory transaction lock (BLOCKER, v1)

**Evidence (VERIFIED).** Draft §6: `pg_try_advisory_xact_lock(hash(instrument_id, kind))` around a
provider call of up to 3 s. (1) `market_data` calls `release_request_connections()` right before every
provider call (`market_data.py:69-77`, `:135`, `:186`, `:235`), and `release_connection`
**commits** the request session when it has no pending ORM writes (`database.py:195-206`). A commit
releases a transaction-level advisory lock, so the lock is gone before the provider is reached.
(2) If the store skipped the release to keep the lock, it would re-create the incident that function
documents: "a few concurrent dashboard requests exhausted the pool" (`database.py:181-184`); the pool
is 10 + 5 per instance (`database.py:24-26`) and one dashboard fires ~13 requests (`:20`).
(3) The runtime URL is Neon's pooled endpoint (PgBouncer transaction pooling, `deploy/cloudrun.md:137`),
where session-level locks cannot work at all; `routers/internal_jobs.py:149-163` explains why the job
lock lives on a dedicated NullPool connection to the *direct* host.

**Why it matters.** Either two instances both call the provider for the same miss (the lock silently
does nothing — double credits, and nobody notices), or 15 cold fills pin all 15 connections for 3 s
and login times out.

**Fix.** v1 (one local process): single-flight is the in-process future map that already exists
(`market_data.py:59`, `:236-240`); the only database lock is a row lock on the instrument row inside
the short write transaction, taken *after* the provider answered. Cloud wave: request path never
calls the provider (F-05); the fill job claims work with a **lease row** — `UPDATE … SET
lease_owner=:id, leased_until=now()+interval '90 s' WHERE leased_until IS NULL OR leased_until <
now() RETURNING …`, commit, call the provider with no transaction open, then write guarded by
`lease_owner`. The repo already uses leases for `BrokerSyncRun` (`jobs.py:107-110`).

### F-05 — Who may write global tables (BLOCKER, v1 because grants live in the migration)

**Evidence (VERIFIED).** Draft §5.5 grants `portfyl_runtime` `INSERT, UPDATE` and says "Jobs
(`JOB_DATABASE_URL`) own cleanup". Jobs connect as **the same role**: "Job URL (direct/unpooled) —
the same `portfyl_runtime` role and database" (`deploy/cloudrun.md:139-140`). So either the runtime
role gets `DELETE` after all, or `market_cache_gc` cannot delete. No precedent exists for a global
table that tenants read but must not write: every existing global table is infrastructure state
(`job_runs`, `rate_limit_buckets`, `stripe_events`, `beta_invites` —
`docs/security/tenant-isolation-matrix.md:141-162`, subagent).

**Why it matters.** RLS and the application predicates protect tenants from *application bugs*.
With runtime write access, one such bug — an import handler that stores a broker-supplied price or
name, a "correct the ticker" feature, a refresh endpoint that trusts a query parameter — changes a
number that **every** tenant's net worth is computed from. It is the only write in the system with
that blast radius.

**Alternatives.**

| Option | Protects against | First view of an unseen ticker | Cost |
|---|---|---|---|
| A. Runtime `INSERT/UPDATE` (draft) | nothing at DB level | inline, 0.3–3 s | none |
| B. `SECURITY DEFINER` upsert function | arbitrary updates/deletes; still accepts any "plausible" value the caller passes | inline | first PL/pgSQL in the repo (none today, subagent grep); cannot run in the SQLite fast suite |
| C. Separate role `portfyl_market_writer`, job-only writes, runtime `SELECT` + append-only enqueue | every request-path bug; the writer role has no grant on any tenant table, so a compromised market job cannot read tenant data either | enqueue → immediate Cloud Task → job, ≈ 2–6 s incl. cold start (INFERRED from the existing `backfill_trigger.py` pattern) | one role, one secret, one table in the cloud wave; one optional env var in v1 |

**Recommendation: C.** The latency cost is paid once per never-seen instrument and is hidden by the
seed and by `ensure_instruments` at import. v1 creates the role and the least-privilege grants now
(additive; nothing to revoke later) and writes through a `writer_session()` bound to
`MARKET_WRITER_DATABASE_URL`, falling back to `DATABASE_URL`. The dev compose database user is a
superuser (`deploy/docker-compose.postgres-dev.yml:5-7`), so a default local setup needs no extra
step; which role the owner's `.env` really uses is UNKNOWN, so startup runs a privilege preflight and
fails with an instruction instead of failing on the first write.

### F-06 — Neon compute (BLOCKER, cloud)

**Evidence.** VERIFIED in code: "`/health`'s SELECT 1 every 5 minutes kept Neon awake around the
clock and burned the compute quota" (`main.py:266-269`); "a 1-minute cron kept the Neon compute awake
around the clock and exhausted the free 100 CU-hour quota" (`deploy/cloudrun.md:452-454`); all
scheduled jobs are now hourly or slower (`deploy/operations.json:3-9`). VERIFIED at neon.com/docs
(subagent): Free = 100 CU-hours per project per month, idle timeout fixed at 5 minutes; "Each
connection resets the scale to zero timer"; minimum compute 0.25 CU; Launch $0.106 per CU-hour, no
minimum. Draft §9 schedules `market_refresh` "every 5 min" (no weekday limit) and `market_prices`
"every minute on weekdays", and calls the latter "acceptable, but count it in cost" without counting.

**Computed (§5).**

| Schedule | Hours awake / month | CU-h at 0.25 CU | Free quota | Launch |
|---|---|---|---|---|
| Draft: `market_refresh` every 5 min, 24×7 | 730 | **182.5** | 182 % → out on day 17 | $19.34 ($77 if it autoscales to 1 CU) |
| Draft: `market_prices` every minute, weekdays | 522 | 130.5 | 130 % | $13.83 |
| Tick only inside the US session | 138 | 34.6 | 35 % | $3.66 |
| Tick 09:00–22:00 CET on weekdays | 273 | 68.2 | 68 % | $7.23 |
| One daily after-close pass | 5 | 1.3 | 1 % | $0.14 |

The Free quota also has to carry all user traffic. The current Neon plan is UNKNOWN (the repo only
says "free 100 CU-hour quota").

**Why it matters.** Shipping the draft's schedule on the current plan repeats 2026-10-19 in the third
week of every month: database suspended, product down.

**Fix.** (1) v1 has **no scheduled job at all** (F-20). (2) Cloud wave gate: a paid Neon plan
(founder decision D-3). (3) One self-chaining **market tick** instead of two crons: it runs only
while at least one hot instrument's exchange is open, each pass enqueues its own continuation through
Cloud Tasks exactly like `backend/backfill_trigger.py:9-20` does today, and stops by itself at the
close; an hourly scheduler entry is the safety net. (4) `market_refresh`, `market_demand`,
`market_earnings_watch` and `market_cache_gc` collapse into **one daily after-close pass**; cold fills
are woken by an immediate task, not by a 5-minute cron. On Venture only US instruments are real-time
(F-07), so the tick window is the US session: 34.6 CU-h.

### F-07 — Venture is end-of-day for Europe (BLOCKER, cloud; founder decision D-1)

**Evidence (VERIFIED, twelvedata.com/exchanges and pricing-business, subagent).** Venture includes
"US real-time, EOD global"; "Real-time EU market data … Available via Data add-ons". Exchange rows:
`XPRA Czech Republic EOD … Pro Venture`; Xetra, Frankfurt, London, Paris, Amsterdam, Toronto: EOD;
Warsaw: minimum plan Ultra / **Enterprise**; Vienna and Tokyo: conflicting pages. US real-time is
"roughly 5 % of this total market activity" (support article 9935903), not the consolidated tape.
Today yfinance shows European prices intraday (delayed; the UI already labels "delayed up to N min",
`frontend/src/lib/priceFreshness.js:31-45`, subagent).

**Why it matters.** A Czech investor with ČEZ, VWCE.DE and CSPX.L opens the dashboard at 11:00 and
sees yesterday's close until tomorrow — a visible step back from the free data he has now — while
95 % of the credit spend (§5) buys 2-minute prices for US stocks only. Draft §16.3 asks whether EOD
is "acceptable"; it is not a detail, it is the product for the home market.

**Fix.** None available to the design. The spec states it plainly and routes it to D-1.

### F-08 — Storage terms (BLOCKER, cloud; founder/lawyer decision D-4)

**Evidence (VERIFIED, twelvedata.com/terms, "Last updated: January 1, 2026", subagent).** 2.2(a):
"store Data solely for Internal Use (or as otherwise permitted by your Subscription Tier or
add-ons)". 2.3(g): may not "Store or cache Data beyond permitted timeframes specified in the
Documentation"; no timeframe was found in the docs or in ~12 support articles; the commercial-usage
article says Venture allows "temporary caching". 16.2(a): "All Data must be deleted within 30 days"
of termination. Public display needs the attribution "Data provided by Twelve Data" with a dofollow
link (support article 12647398). Repo: the monetization plan forbids a personal-use data path to be
"used to fill a shared cache" (`2026-09-01-portfyl-saas-monetization.md:885-888`, subagent) — which is
why Wave 3 local-only is the right call.

**Why it matters.** The store's value is 20 years of daily closes kept indefinitely. If "temporary"
means days, the history table is a breach from day one and the performance chart has no licensed
source.

**Fix (design side).** Purge is a first-class, tested command from v1; every row carries `source`;
the cloud wave cannot start before a written answer from Twelve Data to the questions in §7 (D-4).

### F-09 — Demand side channels (SHOULD, cloud)

**Evidence (INFERRED from draft §5.4, §6, §15).** Hiding the `market_demand` table does not hide
demand: (1) a first view answers `pending` only if nobody asked before; (2) "hot" = held by an active
workspace or viewed in the last 24 h, and hot instruments have 2-minute-fresh quotes — a fresh quote
on an obscure US ticker says "an active customer holds this"; (3) `fetched_at` in `meta` says when
someone last triggered a fetch; (4) an instantly "unresolvable" answer says someone tried that string.

**Why it matters.** With a few dozen beta users who know each other, "someone holds the micro-cap
Alice keeps talking about" identifies Alice. No quantity or identity leaks, but the anti-goal in §2
("any way for one tenant to learn what another holds/views") is not met.

**Fix.** The API exposes only `price_as_of` (the provider's market timestamp) and `price_status`;
never `fetched_at`, tier, or a held flag. A viewer's own request promotes the instrument, so
"it is fresh now" proves nothing after the first response. The seed makes common tickers
indistinguishable. The residual oracle (first response for a non-seeded instrument) is written into
the isolation matrix as an accepted, bounded inference for the founder to sign (D-5); optional
hardening — delay every first view per workspace of a non-seeded instrument — is described, not built.

### F-10 — Universe poisoning and credit burn (SHOULD, v1 for validation; cloud for caps)

**Evidence (VERIFIED).** `routers/market.py:1017-1022` and `:1043-1048` pass the path parameter
straight to `yf.Ticker(ticker.upper())`; a ticker regex exists only on the Shibui routes
(`shibui_client.TICKER_RE`, subagent). Import has a 5 MiB size cap but no row or ticker cap; Investor
and Pro have no position limit (subagent: `routers/portfolio.py:61`, `plans.py:43-46`). Rate limiting
is cloud-only (`rate_limit.py:85-90`, `:200`) with three rules, each defined by two **required** env
vars (`:54`), and the global limit is 120 requests per 60 s per IP. The draft's "200 tickers per
import, outside the per-workspace cap" has no per-day bound.

**Why it matters.** One logged-in user loops `/market/history/ZZ{n}` at 120/min: 120 instrument rows,
120 negative-cache rows and 120+ credits per minute — a fifth of the plan — indefinitely. Ten imports
of 200 invented tickers do the same without touching the rate limit.

**Fix.** v1: one validator (`^[A-Z0-9^][A-Z0-9.\-=^]{0,19}$` after upper-casing) in front of every
store entry, and a hard instrument cap (tripwire, default 20,000 rows) that fails closed and logs.
Cloud wave: new instruments are admitted only through the enqueue table, counted per workspace per
day from plan entitlements (`plans.py`), with a global daily ceiling that pages; imports are
**inside** the cap; symbol validation runs against a locally stored catalogue, not `/symbol_search`
per request. Note that the catalogue itself is plan-limited (`/etfs` returns "up to 50 records" below
Ultra — F-26).

### F-11 — Isolation tests (SHOULD, v1)

**Evidence (VERIFIED, subagent for the test names).** No test asserts "every table has RLS"; the
lists are positive (`tests/postgres/test_rls.py:25-58`, `test_runtime_role.py:47-73`), so a new
global table fails nothing by itself. Exact-grant tests exist per global table
(`test_runtime_role.py:335-350`).

**Fix — required tests** (all in `backend/tests/postgres/`): no column named `workspace_id`,
`user_id`, `portfolio_id` on any `market_*` table and no foreign key from a `market_*` table to any
non-market table; exact grants per table for both roles; `portfyl_market_writer` cannot `SELECT` from
`transactions`, `users` or `workspaces`; `portfyl_runtime` cannot `INSERT`/`UPDATE`/`DELETE` any
`market_*` table; the finality `CHECK` rejects a same-day row. Cloud wave adds to the Alice/Bob
matrix: Bob's request for a symbol Alice holds returns the same market payload as for a symbol nobody
holds. New matrix section "Global reference data (market store)" in
`docs/security/tenant-isolation-matrix.md`.

### F-12 — Currency units (SHOULD, v1)

**Evidence.** VERIFIED: `currency_codes.py:11` has one sub-unit, `{"GBX": ("GBP", 100.0)}`;
`routers/analytics.py:140`, `:151`, `:172` test only for the spelling `"GBp"`. VERIFIED (Twelve Data
support article 12383853): LSE is "mostly quoted in GBp", JSE in ZAc, TASE in ILA. FX direction is
consistent: `{c}CZK=X` is CZK per one unit and values multiply by it (`fx.py:24-28`,
`routers/portfolio.py:680`).

**Why it matters.** A Tel Aviv or Johannesburg holding is valued 100× too high today; the store would
freeze that into a table and a second provider would spell the unit differently.

**Fix.** The store never converts units; it stores the provider's price and the provider's currency
string, and `currency_codes.normalize_currency`/`subunit` stay the single place that knows units.
v1 adds `ILA→ILS` and `ZAC→ZAR` (input spelling `ZAc`) to `SUBUNITS` with tests. Flagged as a
behaviour change for holders of such instruments (today wrong by 100×).

### F-13 — Identity (SHOULD, v1)

**Evidence (VERIFIED via subagent, models spot-checked).** `Transaction` has no ISIN or exchange
column; `source_instrument_id` sometimes holds an ISIN (`models.py:489-530`). T212 **CSV** stores the
bare upper-cased ticker (`routers/portfolio.py:276`), T212 **API** stores Yahoo-suffixed symbols
(`t212_sync.py:113-126`), the other importers resolve to Yahoo symbols
(`importers/instruments.py:95-122`). `yf_symbol` is a one-entry table (`ticker_map.py:10-14`).
Twelve Data accepts `isin` on all plans (docs/market-data).

**Why it matters.** `alias` as a primary key (§5.1) says bare `VUSA` means one instrument for
everyone; from T212 it is the London line in GBP, elsewhere the Amsterdam line in EUR.

**Fix.** v1 key = the listing symbol **in Yahoo notation after `yf_symbol()`**, which is what every
call site already passes. `market_instrument` gets a surrogate `id` now so identity can grow without
re-keying. The alias table arrives with Twelve Data, keyed `(namespace, alias)` with the transaction
currency as a tie-breaker and ISIN when present. Ticker reuse/merger: deferred, but the instrument
keeps `kind` and the info payload keeps the name so a later check can detect an identity change.

### F-14 — Garbage in (SHOULD, v1)

**Evidence (VERIFIED).** The code base records the incident: a deadline miss cached as "no data"
"once poisoned USDCZK=X for 60s and every position rendered at ≈ -95%" (`market_data.py:56-58`,
`routers/portfolio.py:664-666`). Today an empty answer is cached for 60 s and the holding is valued
at 0 (`market_data.py:298`). The draft has no bounds.

**Fix — one write choke point, three rules.** (1) Empty or unpriced answers never replace a good
payload: the last good one keeps being served with its true `price_as_of`; attempts and
`next_attempt_at` back off 60 s → 15 min. (2) A price outside ×[0.5, 2.0] of the stored one
(FX: ×[0.8, 1.25]) is parked as a candidate and served only after a second fetch confirms it within
2 %. (3) Daily bars with a non-finite or non-positive close are dropped, and an empty fetch never
deletes stored history.

### F-15 — Cost model (SHOULD)

Recomputed in §5. Wrong or misleading in the draft: 210 refreshes per US session (it is 195; 210
needs a 7-hour session); 22 trading days (21); hot pass 1,386,000 → **1,228,500**; splits "~1,000"
contradicts §7's own "+ 90 days" rule → 6,667 (and → ~0 with F-02's fix); total 1.44 M → **1.29 M**;
"≈ 190/min during the US session" → 150/min for the hot pass; "the plan uses ≈ 6 %" compares against
a 24×7 ceiling — inside US sessions the ceiling is 4,995,900 and the hot pass alone is **25 %** of it
and **44 %** of the job share. Unstated assumptions: 60 % dividend payers; FX at 8 refreshes a day
although §7 says "same as prices" (122,850 if taken literally); statistics ×1 although §7.1 re-checks
at +1/+3/+7 days (up to 15,000); one earnings-calendar request although the endpoint is "limited to
1200 records" (4,200 with five country calls). Correct as written: 26,352,000 ceiling, 488 cap, 341.6
job share, ~683 hot instruments, 122 credits per seeded instrument, 36,600 and 60,000, 1.8 h and
2.9 h. The Venture price and credit figure are VERIFIED (§4), but Venture has three tiers.

### F-16 — Budget row (SHOULD, cloud)

**Evidence (INFERRED).** `INSERT … ON CONFLICT DO UPDATE … WHERE credits_used + :c <= :cap` is correct
arithmetic, but: the bucket must come from the database clock (`date_trunc('minute', now())`), not
from five instance clocks; Twelve Data's minute is its own ("your quota … will reset at 17:00:00",
support article 5615854), so the authoritative number is the `api-credits-left` header; a failed call
may still be charged (`/batch`: credits include "attempted failures"), so **no refunds**; one row per
minute is 43,200 rows a month. With job-only writes (F-05) at most three writers touch the row, so
contention disappears.

**Fix.** Reserve from the DB clock; after every response set `credits_used = GREATEST(credits_used,
cap_total − api_credits_left)`; never decrement; trim rows older than 48 h in the daily pass; a
single 100-credit call must fit under the soft cap or it is deferred to the next minute.

### F-17 — Scheduler jobs (SHOULD, cloud)

**Evidence (VERIFIED).** `_run_job` calls `mark_job_succeeded(db, job_name)`
(`routers/internal_jobs.py:226-228`), which raises `ValueError` for a name not in
`RECURRING_JOB_NAMES` (`jobs.py:92-99`, `:144-145`). `/health` reads `_JOB_MAX_AGES`
(`main.py:238-255`, `:298-310`). Async passes must be listed in
`tests/test_event_loop_not_blocked.py:152-165`. Attempt deadline 300 s, 3 retries
(`deploy/operations.json:12-13`); an overlapping attempt returns HTTP 200 "skipped"
(`internal_jobs.py:217-220`). A killed pass releases its lock because the socket closes (`:161-163`).

**Why it matters.** A job added only to `operations.json` and the router returns 500 on every run
after doing all its work — and Cloud Scheduler retries it three more times.

**Fix.** Each new job is registered in five places owned by one task (`jobs.py`, `main.py`,
`internal_jobs.py`, `operations.json`, the event-loop test); passes are time-boxed to 240 s, commit
per batch and are idempotent; a weekday-only job gets a 96 h max age, and the real health signal is
"oldest hot quote while its exchange is open", not the heartbeat.

### F-18 — Local loop (SHOULD, v1)

**Evidence (VERIFIED).** Local passes run through `_periodic_loop` → `asyncio.to_thread` →
`run_on_private_loop` (`main.py:348-384`), so the event-loop rule holds. But
`release_request_connections` only touches request sessions: "Sessions outside a request (background
jobs) are never touched" (`database.py:209-219`).

**Fix.** Store code never receives the caller's session. Reads and writes use their own short
sessions that are closed before any provider call; a rule in the spec and a test that fails if a
public `market_store` function has a `Session` parameter.

### F-19 — Observability and rollback (SHOULD, v1)

**Fix.** Flag semantics: `PORTFYL_MARKET_STORE=on|off`, default off, **refused at startup in the
cloud edition until the cloud wave**; off = today's code path. Rollback of v1 = set the flag off and
restart (data stays, unused). Purge = `python -m market_store.purge --yes` (empties the three tables;
the 30-day deletion duty for a licensed provider uses the same command, plus the Neon history
window). Proof it works: counters logged once a minute when non-zero — L2 hits, provider fetches,
stale-served, rejected-by-sanity, history replacements.

### F-20 — Scope and the thin slice (SHOULD, v1)

**Evidence.** Draft: 12 tables, 13 snapshot kinds with a new canonical shape each, 5 jobs, a limiter,
and the rewrite of 60+ call sites (subagent census) in two files of 2,712 and 2,832 lines. None of
budget, demand, seed, earnings watch or the alias table can run before a metered provider exists, and
the founder has decided the cloud flag stays off until then.

**Fix — v1 = a durable second cache level under the existing `market_data` facade, local edition,
yfinance, no jobs.** `get_infos` reads memory → PostgreSQL → provider; history readers get a small
typed API. Every caller of `get_infos`/`get_info` (holdings, summary, alerts, watchlists, analytics,
fundamentals) is served from the database without being edited.

| Draft table | Verdict | Why |
|---|---|---|
| `market_instrument` | **Keep (v1)** | identity anchor with a surrogate id; cannot be cut |
| `market_snapshot` | **Keep (v1)**, one kind `info` | the sanitised `.info` dict *is* the shape every consumer already reads; a new canonical shape is the Twelve Data adapter's problem |
| `market_price_daily` | **Keep (v1)**, + `adj_close`, `split_ratio`, `dividend` | F-01 |
| `market_price_latest` | Merge → snapshot | the quote is inside `info` for Yahoo; split into its own kind with Twelve Data |
| `market_dividend_event`, `market_split_event` | Merge → daily row | they arrive with the bars in one call |
| `market_fetch_state` | Merge → columns on snapshot/instrument | one row per thing fetched already exists |
| `market_instrument_alias` | Defer (cloud wave) | F-13 |
| `market_demand` | Defer, redesign | F-09 |
| `market_budget`, `market_provider_state`, `market_usage_daily` | Defer | no metered provider in v1 |

Deferred to named later waves: statements/estimates/ownership snapshots and `ticker_attrs`
(calendar, earnings dates, insider) — Wave 2; everything Twelve Data — Wave 4. **Never cut:**
surrogate instrument id; one write choke point with F-14's rules; completed-sessions-only daily rows
with verify-then-append; no tenant columns and the grant tests; the flag and the purge command.

### F-21 — File ownership (SHOULD, v1)

**Evidence (VERIFIED by census, spot-checked).** `backend/analytics.py` and `backend/alerts.py` do
not exist; they are `backend/routers/analytics.py` and `backend/routers/alerts.py`. §12 misses files
that reach the provider or its helpers: `market_data.py` itself, `ticker_map.py`,
`routers/watchlists.py:47,132`, `routers/cash.py:75,100`, `routers/broker.py:217-220`,
`t212_sync.py:1863`, `ledger_import.py:42-49`, `routers/benchmarks.py`, `routers/portfolios.py`,
`routers/allocation_targets.py`, `routers/local_features.py` + `services/screener_jobs.py` (local
Tax Report/Screener), and `/portfolio/insider-buys`. Three files import `yfinance` only so tests can
patch `routers.portfolio.yf.download` / `routers.analytics.yf.download`. Hotspots the draft's Wave 2
would hit from two tasks at once: `main.py` (`_JOB_MAX_AGES`, local loops), `jobs.py`
(`RECURRING_JOB_NAMES`), `routers/internal_jobs.py`, `deploy/operations.json`,
`tests/conftest.py:46-53`, `tests/test_plan_schema.py:27-28` (hard-codes the Alembic head),
`models.py`, and the eight i18n dictionaries.

**Fix.** The plan assigns every one of these to exactly one task per wave and lists "must not touch"
per task.

### F-22 — Seed (SHOULD, cloud)

**Fix.** A table `market_seed_item(symbol, step, status, attempts, last_error)` drives the command:
restartable at any step, idempotent upserts, throttled by the same budget reservation, `--dry-run`
prints the credit total first. Default universe proposal for the founder to approve as a file
(`deploy/market-seed-universe.csv`), built by rule, not by invented tickers: (a) every distinct
symbol held or watched in the owner's local database, (b) the constituents of the indices the app
already ships as benchmarks, (c) nothing else until measured demand says so. The dress rehearsal runs
on local with yfinance.

### F-23 — Frontend contract (SHOULD, v1)

**Evidence (VERIFIED).** `market_data.price_freshness` returns `price_status`
(`missing|stale|live|delayed|closed|unknown`), `price_as_of`, `price_delay_minutes`, `price_source`
(`market_data.py:295-333`); `/portfolio/holdings` and `/summary` expose them
(`routers/portfolio.py:1409`, `:1616-1623`); the frontend renders them
(`frontend/src/lib/priceFreshness.js`, `portfolioAlerts.js`). Query defaults are `staleTime` 30 s,
refetch on focus; nothing polls market data (subagent). A new user-visible string needs entries in
eight dictionaries or the build fails (`i18n/messages.test.js`, subagent).

**Fix.** No new `meta` object. v1 keeps the four fields and adds one additive boolean,
`prices_refreshing`, on `/portfolio/summary`; the dashboard does **one** delayed refetch (3 s, at most
two attempts per mount) when it is true — no polling loop, no new string, no visual change, so
`DESIGN.md` is untouched. `pending` belongs to the cloud wave, as a new `price_status` value plus
dictionary entries. `StockOverviewTab`'s automatic `financials` fetch stays until Wave 2 gives it a
cached source.

### F-24 — Draft §3 corrections (SHOULD)

VERIFIED wrong or incomplete: there is **no startup FX backfill** — `main.py:387-393` only asserts the
Alembic head; `bulk_fetch_fx` is called from import and T212 finalisation (subagent) — so §15's
"Startup FX backfill moves onto the store" has nothing to move (CLAUDE.md repeats the stale claim).
`download()` also has in-flight de-duplication (`market_data.py:141-148`); the attribute cache is
2,048 entries, `fx._DAILY_CACHE` 512. `/market/quote` has its own 120 s cache and `/market/history`
30 min (`routers/market.py:31-33`, `:1018`, `:1044`) on top of raw, ungated `yf.Ticker` calls.
`jobs._next_dividend_info` is confirmed raw (`jobs.py:856-857`). `ticker_attrs` waits without a
timeout (`market_data.py:189`). Confirmed as written: cache sizes and TTLs for info/download, head
`0025_stripe_billing`, per-table grants, job pattern.

### F-25 — Consumers that must not see stale data (SHOULD, cloud; rule stated in v1)

**Evidence (VERIFIED).** Price alerts evaluate `get_infos` (`routers/alerts.py:136`, subagent);
manual transactions and imports stamp `fx_to_czk` permanently from `fetch_fx_to_czk`
(`fx.py:67-89`).

**Why it matters.** Stale-while-revalidate that is right for a dashboard fires a "below 100" alert on
yesterday's price, or stamps last week's rate into a ledger row forever.

**Fix.** `get_infos(..., require_fresh=True)` for alerts: full deadline, and a value older than the
TTL is treated as unavailable. FX stamping keeps today's semantics exactly (completed bars
forward-filled; today's point from the live quote, as now).

### F-26 — What Venture does not include (SHOULD, cloud; founder decision D-2)

**Evidence (VERIFIED, OpenAPI `x-starting-plan` and docs, subagent).** Statements: "Full access to
historical data requires the Ultra plan … or the Enterprise plan" — how many periods Venture returns
is UNKNOWN; the provider spreadsheet requires "≥10 years annual and ≥20 quarters" (D-043, subagent).
ETF and fund data, analyst data, institutional holders, market cap: Ultra/Enterprise. `/etfs` list:
"up to 50 records" below Ultra. Answers draft §16.4: ETFs get no profile- or statistics-like data on
Venture.

### F-27 — Earnings-driven refresh (LATER)

`/earnings_calendar` is "40 per request" and "limited to 1200 records" (VERIFIED); non-US coverage
and the minimum plan are NOT FOUND in the docs. Keep the founder's design, keep the draft's safety
nets as the mechanism that is known to work, and measure in shadow mode how many European reporters
the calendar actually lists before relying on it.

### F-28 — Fundamentals payload cache (LATER)

`/market/fundamentals` sits behind a `standard_research` capability and the plan table differentiates
Free/Investor/Pro content (subagent). Whether its response is identical for every plan is UNKNOWN. A
global cache of that response must first prove it is tenant- and plan-independent, or key by plan.
Not in v1.

### F-29 — Compliance records (SHOULD, v1)

`docs/compliance/data-processing-inventory.md:66` describes the market cache as "Web-instance memory
only … Not durable and not exported" (subagent). v1 makes it durable in the local database: update
that row in the same change. For the cloud wave add Twelve Data as a recipient (sent: instrument
identifiers only) and state the deletion path (purge command; Neon history retention 6 h per
`docs/operations/operational-verification-2026-09-09.md:45`).

### F-30 — Pre-existing defect (NOTE, out of scope)

VERIFIED by reading, not by running: `RECURRING_JOB_NAMES` (`jobs.py:92-99`) lacks
`billing_reconcile`, while `_run_job("billing_reconcile", …)` (`routers/internal_jobs.py:294`) ends in
`mark_job_succeeded`, which raises for unknown names (`jobs.py:144-145`). If no test or wrapper
intervenes, that job answers 500 after every pass and `/health` reports it missing. Worth a
five-minute check before billing is switched on. Not touched by this work.

### F-31 — Smaller notes

- Storing the whole `.info` dict is correct for a local, single-owner store and wrong for a licensed
  one ("the raw provider response is not stored", §5.3). The cloud wave narrows it.
- Float columns, not Numeric: values go straight back into pandas and must equal today's.
- `datetime.now().date()` (server-local) is used for "today" in `routers/portfolio.py:686`; the store
  uses UTC everywhere and says so.
- The repo's own vendor note prices Venture at USD 499 (`docs/research/market-data-vendor-requirements-2026-09-07.md:143-146`,
  subagent); that is the top Venture tier, the entry tier is USD 149.

## 4. Verified Twelve Data facts

Sources: twelvedata.com/docs (section pages), /pricing.md, /pricing-business, /exchanges, /terms,
api.twelvedata.com/doc/swagger/openapi.json, support.twelvedata.com. Fetched 2026-11-12 by two
subagents; six `demo`-key GETs with public symbols only; no paid credits, no project data sent.

| Claim in the draft | Status | What the page says |
|---|---|---|
| `/quote`, `/time_series`, `/eod`, `/price`, `/exchange_rate` = 1 credit | VERIFIED | "1 per symbol" (docs/market-data, docs/currencies) |
| `/time_series` cost independent of `outputsize` | VERIFIED | cost line has no size term; `outputsize` 1–5000 |
| `/time_series` default `adjust=splits` | VERIFIED | values `all, splits, dividends, none`; default `splits` |
| `/profile` 10, Grow/Venture | VERIFIED | "available on the Grow plan (individual) and the Venture plan (business) and above" |
| `/statistics` 50 | VERIFIED | Pro / Venture and above |
| `/dividends`, `/splits`, `/earnings` 20 each | VERIFIED | Grow / Venture |
| `/earnings_calendar` 40 per request, 1,200 records | VERIFIED | "40 per request"; "This endpoint is limited to 1200 records." |
| `/earnings_calendar` minimum plan, non-US coverage | NOT FOUND | no plan note; only a NYSE sample |
| Statements 100 each, Pro/Venture | VERIFIED | plus "Full access to historical data requires the Ultra plan" |
| `/symbol_search` 1 | VERIFIED | "1 per request" |
| `/insider_transactions` 200 | VERIFIED | Pro / Venture |
| Estimates 20, recommendations 100, price target 75, institutional holders 1500, Enterprise-only | VERIFIED | Ultra (individual) / Enterprise (business) |
| ETF endpoints 200, Ultra/Enterprise | VERIFIED | `/etfs/world` 800; summary/performance/risk/composition 200 each |
| `/splits_calendar`, `/dividends_calendar` (not in the draft) | VERIFIED | 40 "per symbol", Grow / Venture |
| Multi-symbol batches on `/quote`, `/time_series` | PARTLY | supported and billed per symbol (support article 5203360); **maximum per request NOT FOUND**; `demo` answers 401 |
| `api-credits-used` / `api-credits-left` headers | VERIFIED (docs), not observable with `demo` | support article 5713553 |
| 429 on limit, fixed clock minute | VERIFIED | "reset at 17:00:00"; body sample NOT FOUND |
| No daily cap on paid plans | VERIFIED | "paid plans have no daily limits" |
| Venture $149, 610 credits/min | VERIFIED | entry tier; also $299/1,597 and $499/2,584 |
| Venture needed for display to users | VERIFIED | "Display the data to end users in external applications" |
| Prague, Xetra real-time or EOD on Venture | VERIFIED: **EOD** | `XPRA … EOD … Pro Venture`; `XETR … EOD`; real-time EU "via Data add-ons" (Cboe Europe) |
| Terms 2.2(a), 2.3(g), 16.2 | VERIFIED wording | see F-08; no caching timeframe found anywhere |
| Overage | PARTLY | Terms 5.2(c) "Overage charges apply for exceeding subscription limits" under usage-based pricing; nothing on the pricing pages |
| `/quote` fields | VERIFIED | `close`, `previous_close`, `is_market_open`, `timestamp`, `last_quote_at`, `fifty_two_week`, … (F-03) |
| ISIN lookup | VERIFIED | `isin` parameter "Available on all plans" |
| Minor units | VERIFIED | GBp, ZAc, ILA (support article 12383853) |

## 5. Recomputed cost model

Script: `cost_model.py` in the review session's scratchpad (pure arithmetic, not committed). Output,
abridged:

```
US regular session minutes        6.5 h * 60            =        390
2-min refreshes per US session    390 / 2               =        195   draft 210
Trading days per month            252 / 12              =         21   draft 22
Monthly ceiling, 24x7             610 * 60 * 24 * 30    = 26,352,000   draft ~26M
Ceiling inside US sessions only   610 * 390 * 21        =  4,995,900
80% soft cap                      610 * 0.8             =        488   draft 488
Job share                         488 * 0.7             =      341.6   draft ~342
Hot instruments at a 2-min cycle  341.6 * 2             =      683.2   draft ~680
Hot pass at 300 hot               300 / 2               =  150 / min   = 43.9% of the job share

EOD pass, all held                1000 * 21             =     21,000   draft 22,000
Hot 2-min pass                    300 * 195 * 21        =  1,228,500   draft 1,386,000
FX at the draft's 8/day           30 * 8 * 21           =      5,040   draft 5,300
Profile                           1000 * 10 / 3         =      3,333   draft 3,300
Statistics                        300 * 50 * 4 / 12     =      5,000   draft 5,000
Dividends                         600*20 + 400*20/3     =     14,667   draft 14,700
Splits, the draft's "+90 days"    1000 * 20 / 3         =      6,667   draft 1,000
Earnings calendar                 40 * 21               =        840   draft 900
Statements                        30 * 600 / 3          =      6,000   draft 6,000
TOTAL                                                   =  1,291,047   draft 1,440,000
Average per minute, 30 days       total / 43,200        =       29.9   draft ~33
Hot pass share                                          =      95.2%   draft ~93%

Sensitivities: FX "same as prices" 122,850 · FX every 10 min 52,920 ·
statistics with re-checks 15,000 · earnings calendar in 5 calls 4,200

Seed: 1+1+10+50+20+20+20 = 122 · 300 names 36,600 (1.8 h at 340/min) ·
100 x 6 statements 60,000 (2.9 h) · one instrument's 600 statement credits
need >= 1.2 minutes under the 488 cap

Neon at 0.25 CU: draft 5-min job 24x7 = 730 h = 182.5 CU-h (Free 100; $19.34 on Launch)
per-minute weekdays = 522 h = 130.5 CU-h · US-session tick = 138 h = 34.6 CU-h ($3.66)
09:00-22:00 CET tick = 273 h = 68.2 CU-h ($7.23) · daily pass = 1.3 CU-h
Free is exhausted after 16.7 days of an always-awake 0.25 CU compute
```

Credits are not the constraint (4.9 % of the 24×7 ceiling); the per-minute cap inside the US session
and the database's awake hours are.

## 6. Decisions to revisit (founder decisions kept; this is their price)

| Decision | Price of keeping it | Alternatives |
|---|---|---|
| 2-minute hot refresh | 95 % of all credits, the only reason the database must stay awake through the US session (34.6 CU-h), and it reaches **US instruments only** on Venture | 10–15 min cadence (≈ 164,000–246,000 credits; same awake hours unless the tick is also spaced); or 2 min only while a holder has an open session |
| Venture | Europe is end-of-day, Warsaw absent, no ETF data, limited statement history (F-07, F-26) | Venture + Cboe Europe add-on (price UNKNOWN); compare EODHD as the repo's own RFI note recommends; accept EOD and say so in the UI |
| Seed, then refresh after results | Works where the earnings calendar has coverage; elsewhere the safety nets carry the load (F-27) | none needed — keep, measure |
| Wave 3 local-only | The cloud edition gains nothing until a licence exists; right call (F-08) | — |
| 5-year average P/E, Shibui outside | none | — |

## 7. Could not verify

- **Maximum symbols per batch request** and the **429 body**: not in the docs; `demo` refuses batches.
- **How long Venture may cache**, and whether an indefinite daily-history table is "temporary caching":
  only Twelve Data can answer (D-4).
- **Statement history depth on Venture**; **non-US earnings-calendar coverage**; **price of the EU
  real-time add-on**; exchange-licence duties for displaying US real-time data to end users.
- **Which database role the owner's local `.env` uses** and the **current Neon plan**: not in the repo.
- **Whether F-30 fails in production**: needs a log look or a test run; nothing was executed in this
  review (no tests, servers or migrations were run, by instruction).
- Paid-tier latency, and whether Twelve Data adjusts `previous_close` on a split day: need a paid key.
