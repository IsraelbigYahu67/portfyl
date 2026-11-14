# Kickoff prompt — market-data cache: adversarial design review + implementation plan

Date: 2026-11-12 · For: Claude Fable 5.2 · Paste everything below the line into a fresh session
opened in the Portfyl repo. Input: `docs/superpowers/specs/2026-11-08-portfyl-market-data-cache-design.md`.

---

## 0. Your role and the one-line mission

You are the senior architect and adversarial reviewer for Portfyl, a multi-tenant portfolio-analytics
SaaS (FastAPI + SQLAlchemy 2.0 + PostgreSQL/Neon + React, deployed on Cloud Run). The founder has
written a **draft design** for a PostgreSQL-backed market-data cache. Your mission:

1. **Break the draft** — find everything that would be wrong, unsafe, unaffordable or unbuildable
   *before* any code is written.
2. **Fix it** — produce a revised spec that survives your own review.
3. **Make it executable** — produce an implementation plan that several cheaper Sonnet agents can
   run in parallel without colliding, with tests and acceptance criteria per task.

You do **not** implement the feature. You write three documents (see §6) and nothing else.

The founder is a coding beginner, Czech, and wants simple explanations. All documents are written in
English (the repo's language), but the **final message to the user is in Czech** and in plain language (§7).

## 1. Context you must internalise

- Portfyl ingests broker CSVs/API syncs and shows performance, allocation, dividends and tax reports.
  Two editions: `local` (the owner's private instance) and `cloud` (multi-tenant SaaS, Free /
  Investor EUR 5.99 / Pro EUR 9.99). Billing is built but switched off.
- Today market data (prices, FX, profile, fundamentals, dividends) comes from **yfinance on the request
  path**, cached only in process memory. The founder plans to move to **Twelve Data (Venture plan,
  $149/mo, 610 credits/minute, credit-metered per minute)**. A naive port would cost ~2,500 credits per
  cold dashboard open; the draft's answer is a shared PostgreSQL store with scheduled refresh jobs.
- Research already done (in the draft, §7/§10/§17): per-endpoint credit costs, plan gating, terms of use.
  **Treat all of it as claims to verify, not facts.**

### Founder decisions — respect these, do not re-litigate
You may flag their *consequences* (in a "Decisions to revisit" section with the cost of keeping them),
but you may not silently override them:
- Hot instruments refresh every **2 minutes** while their exchange is open; the rest at end of day.
- Target plan is **Twelve Data Venture**.
- **Wave 3 (cache in front of yfinance) ships to the local edition only**; the cloud edition keeps the
  flag off until Twelve Data is licensed and live (draft §16.5).
- Valuation keeps the **5-year average P/E**; Shibui (US fundamentals/ownership/insiders) stays outside
  the store in v1.
- "Seed a few hundred companies up front, then refresh slow data after each earnings report" (draft §7.1).
- No AI features (a DPA/transfer review is required first).

### Hard project rules (violations are automatic review findings)
Read `CLAUDE.md` fully. The ones that matter most here:
- **Never run database work on the event loop.** Endpoints/dependencies touching a `Session` are plain
  `def`; async job helpers are driven via `private_loop.run_on_private_loop`; call
  `database.release_connection` before slow outbound calls. (An `async def` + `Session` froze the whole
  Cloud Run instance on 2026-10-11.)
- **Alembic only, never at startup.** Every migration must update `EXPECTED_ALEMBIC_HEAD` in
  `backend/database.py` (currently `0025_stripe_billing`) in the same change, and must be
  **forward-compatible** with older instances still running (expand-then-migrate).
- **Tenant isolation is two-layer** (application predicates + forced RLS). The draft proposes global
  tables outside RLS — that exception needs a rigorous justification.
- **Parallel-session safety**: isolated branch/worktree per task, disjoint files per task, hotspots
  (`database.py`, `alembic/versions/`, lockfiles, `package.json`, config) owned by one task at a time,
  no shared resource-mutating steps (dev servers :8000/:5173, test-postgres, `alembic upgrade`).
- Money is normalised to **CZK** via `transactions.fx_to_czk`; don't change that role.
- `DESIGN.md` governs any frontend work; no hardcoded hex colours.
- yfinance noise is expected; don't "fix" it by re-enabling logging.

## 2. Reading list (in this order; stop reading a file once you have what you need)

Docs: `CLAUDE.md` · the draft spec · `docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md`
(market-data rights / Workstream A) · `docs/compliance/data-processing-inventory.md` ·
`docs/security/tenant-isolation-matrix.md` · `deploy/cloudrun.md` · `deploy/operations.json` · the
financial-data-providers spreadsheet added in commit `5da49b9` (find it with `git show --stat 5da49b9`) ·
the Neon outage notes (search `docs/` for the 2026-10-19 incident: Neon free CU-hour quota exhausted by a
per-minute backfill job).

Code (verify the draft's §3 "facts" against these — do not trust them):
`backend/market_data.py`, `fx.py`, `jobs.py`, `ticker_map.py`, `dividend_growth.py`, `alerts.py`,
`broker_cash.py`, `analytics.py`, `database.py`, `routers/market.py`, `routers/portfolio.py`,
`alembic/versions/0002_tenant_rls.py` and `0025_stripe_billing.py` (how grants to `portfyl_runtime` and
RLS are actually written), `main.py` (startup, in-process loop for local), the rate-limiting module,
`frontend/src/components/stock/StockOverviewTab.jsx`, `useStockIntentPrefetch`, `frontend/src/api.js`.

Also run a repo-wide search for every import/use of `yfinance`, `market_data`, `yf_symbol`, `fx.` helpers
and `ticker_attrs`, and **diff that list against draft §12**. Anything the draft misses is a finding.

## 3. External verification (official sources only)

Use web tools on **https://twelvedata.com/docs** and **https://twelvedata.com/pricing** and
**https://twelvedata.com/terms**. Verify, with a quote or URL for each item, and mark each as
`VERIFIED / PARTLY / NOT FOUND`:
- credit cost per endpoint used in draft §7 (`/quote`, `/time_series`, `/profile`, `/statistics`,
  `/dividends`, `/splits`, `/earnings_calendar`, `/earnings`, statements, `/symbol_search`);
- which plan each endpoint needs (esp. `/earnings_calendar`, `/statistics`, statements, ETF endpoints);
- multi-symbol batching on `/quote` and `/time_series` and the max batch size;
- the `api-credits-left` / `api-credits-used` response headers and the 429 behaviour;
- real-time vs EOD-only exchanges **on Venture** — especially **Prague (XPRA) and Xetra**, since the
  founder is Czech (draft §16.3);
- terms 2.2/2.3(g)/16.2 on storing, caching and deleting data, and external display (draft §17).
You may call the free `demo` key for contract checks on the endpoints it allows. **Never spend paid
credits and never send any Portfyl user data, project names or internal details to an outside service** —
documentation lookups and public symbols only. Legal readings are *not legal advice*: flag them for the
founder/lawyer instead of settling them.

Delegate pure fact-gathering (greps, documentation lookups, listing call sites) to Sonnet subagents
(`model: "sonnet"`) in parallel, as the founder's standing instruction requires. Keep the adversarial
reasoning and the design decisions for yourself. Re-verify anything a subagent reports that a finding
depends on.

## 4. Attack list — you must address each item explicitly (a line per item, even if the answer is "fine")

**A. Tenant isolation and information leaks**
1. `market_demand` leaks "someone holds/views X". Is the proposed mitigation enough? Consider timing and
   state side-channels: does `pending` vs instant data reveal that no other tenant has requested a ticker?
   Does negative caching or `unresolvable` status leak anything?
2. The draft lets `portfyl_runtime` INSERT/UPDATE global tables. That makes any app-level bug a
   **cross-tenant write vector** (one tenant corrupting prices every tenant sees). Evaluate alternatives
   (writes only through a SECURITY DEFINER function, a separate narrow role, job-only writes + enqueue
   table) and recommend one, with the latency/complexity trade-off.
3. Universe poisoning and abuse: can a tenant inflate the instrument table or burn credits via
   `/symbol_search`, imports (200 tickers each), or crafted tickers? Are the per-workspace caps real?
4. Is "global reference data, no RLS" correctly guarded by tests (no `workspace_id`/`user_id` columns)?
   What else must go into the Alice/Bob matrix?

**B. Money correctness (silent errors are the worst kind)**
5. Split-adjusted basis: readers during a full-history refetch (mixed bases?), detection of a split via a
   `previous_close` anomaly threshold (false positives/negatives), dividend adjustment, and parity of
   today's `performance(actions=True)` numbers with stored events.
6. Today's daily row: a 14:00 quote must never be stored as the day's close. Define provisional vs final.
   Trade-date per exchange timezone, holidays, half days.
7. Currency units (GBp vs GBP, ILA vs ILS, etc.), FX pair direction, and CZK normalisation.
8. Identity: `symbol_key = SYMBOL:MIC`, ticker changes, reuse of delisted symbols, ISIN as a secondary key,
   mergers; how aliases are resolved for the T212/IBKR/Degiro/XTB/Schwab/Fidelity importers.
9. Garbage in: provider returns 0, null or a 100× price. Where are sanity bounds, and what is served?
10. Recompute **every number in draft §10** (script it; show the arithmetic): trading-minutes per US
    session (195 vs 210 refreshes/day), 1.386 M intraday credits, ~26 M credits/month headroom, seed cost,
    ~342 credits/min job share, ~680-instrument 2-minute coverage. Fix wrong figures.

**C. Concurrency, cost and infrastructure**
11. `pg_try_advisory_xact_lock` held across a provider call: it pins a transaction and a Neon connection
    for up to 3 s. Check against `release_connection`, the pool size, and Cloud Run concurrency. Propose a
    lock/lease design that does not hold a transaction open (e.g. a lease row with expiry).
12. The `market_budget` per-minute upsert: hot-row contention, bucket growth, clock skew between
    instances, what happens when a request reserves credits and then the call fails (refund?).
13. **Neon compute cost of the per-minute job.** The `market_prices` job runs every minute on weekdays and
    will keep Neon compute awake; a similar per-minute job already exhausted the Neon free CU-hours on
    2026-10-19. Quantify CU-hours/month for the proposed schedule on the current and the paid Neon plan,
    and propose a cheaper cadence or batching if needed. This may be the most expensive hidden cost.
14. The 5 new Cloud Scheduler jobs: 300 s attempt deadline, idempotency, overlap (`with_job_lock`),
    behaviour when a pass is killed mid-way, dead-letter state, and what the existing subsystem health shows.
15. Local edition: the in-process asyncio loop in `main.py` — does it respect the event-loop rule? Which
    parts must run via `run_on_private_loop`?
16. Observability and kill switches: which metrics/alerts prove the cache works, and what is the
    one-command rollback for each wave (flag semantics, data purge for the Twelve Data 30-day deletion).

**D. Scope and buildability**
17. The draft has ~13 tables and a canonical JSONB shape per snapshot kind, and admits the canonical
    shapes are "the largest sizing risk". Is it too big for v1? **Propose the thinnest vertical slice that
    delivers the user-visible win** (dashboard + stock detail from the database, behind yfinance, local
    edition only), what is explicitly deferred to later waves, and what can never be cut without breaking
    the design. Justify each table: keep / defer / merge / drop.
18. Are the draft's waves truly file-disjoint? Check real import graphs; Wave 3 serialises hotspot files —
    is that enough, and where do two tasks still collide (e.g. `deploy/operations.json`, `database.py`)?
19. Seed (`market_seed`): resumability, idempotency, throttling, and the universe list. Suggest a sensible
    default universe and how the founder approves it (draft §16.6) — don't invent tickers.
20. Frontend: `as_of`/`stale`/`pending` as additive fields; polling for `pending` (cost!); what the UI shows
    for unresolvable tickers and EOD-only exchanges. Anything touching look and feel must follow `DESIGN.md`.

**E. Legal/commercial** (flag, don't decide)
21. yfinance data in a persistent store (local edition only — confirm what is and isn't allowed to be
    shown to anyone but the owner), Twelve Data storage/caching/purge/display terms, fair-use of 2-minute
    polling 24×5, and processor entries for `data-processing-inventory.md`.

Also look for what this list missed. If you find a class of failure not covered above, add it.

## 5. How to judge and report findings

- Severity: **BLOCKER** (must change before any code), **SHOULD** (change in this design), **LATER**
  (note for a later wave), **NOTE**.
- Every finding has: id, title, severity, **evidence** (`file:line`, doc URL + quote, or your recomputation),
  **why it matters** in one concrete failure scenario (inputs → wrong outcome), and a **specific fix**.
- Label every claim `VERIFIED` (you saw it in code/docs/ran it), `INFERRED` (logical consequence), or
  `UNKNOWN` (cannot be known without the founder or a paid call). Never present UNKNOWN as fact.
- If a part of the draft is right, say so in one line and move on. Do not redesign for taste; challenge
  only with a concrete reason. No padding, no restating the draft.
- When you disagree with a founder decision, put it under "Decisions to revisit" with the price of keeping it.
- Ask yourself before finishing: "What would I regret not having caught if this shipped?" and add it.

## 6. Deliverables (the only files you create or edit)

Work in a **dedicated git worktree/branch** named `docs/market-cache-review`, never on `main`; commit
there, **do not push or merge** (the founder decides). The draft spec is currently *uncommitted* in the
main checkout (`C:\Users\tomzo\claude\ptf\portfyl`); if it is missing in your worktree, copy it in first.
Do not run `alembic`, start dev servers, touch `requirements*`, migrations or app code.

1. **Review** — `docs/superpowers/specs/2026-11-08-portfyl-market-data-cache-review.md`
   Summary table of findings first (id · severity · title · status), then detail, then the
   "Verified Twelve Data facts" table (§3) and the recomputed cost model (B10) with arithmetic.
2. **Revised spec** — edit `docs/superpowers/specs/2026-11-08-portfyl-market-data-cache-design.md` in
   place (git keeps the old text). Add a changelog at the top; mark every changed or new passage `[REV-n]`
   linking to the finding id; keep the section numbering; move resolved questions out of §16/§17 and leave
   only genuinely open ones. Include the thin-slice (D17) as the **v1 scope** and the rest as later waves.
3. **Implementation plan** — `docs/superpowers/plans/2026-11-12-portfyl-market-data-cache.md`, written
   with the `superpowers:writing-plans` skill. Requirements:
   - Waves → tasks. Each task: goal, **owned files (disjoint from every concurrent task)**, files it must
     not touch, exact steps, tests to write first (TDD), commands to run, acceptance criteria, rollback.
   - Hotspots (`database.py`, `alembic/versions/`, `operations.json`, lockfiles) each owned by one task at a
     time; later tasks sequenced after it. State which tasks may run in parallel and which must not.
   - Per-session isolation: branch/worktree name, ports, test-database name for every task that needs them.
   - Migrations additive and forward-compatible; the revision id and `EXPECTED_ALEMBIC_HEAD` update in the
     same task; PostgreSQL integration tests (`backend/tests/postgres/`) are part of the gate.
   - Tasks small enough for a Sonnet agent to finish from the task text alone; mark the few tasks that
     need a stronger model (isolation/security, money-correctness) and say why.
   - A final "re-integrate and re-verify" task per wave (tests, `alembic heads` == `EXPECTED_ALEMBIC_HEAD`,
     edition builds when the frontend is touched).

## 7. Final message to the user (in Czech, plain language, max ~1 page)

1. The 5 findings that matter most, each in one or two sentences a beginner can follow (no jargon
   without a short explanation), with severity.
2. What changed in the design and what the smallest first version (v1) now is.
3. A short list of **decisions only the founder can make**, each with 2–3 options and your recommendation
   (open questions from draft §16, the Neon cost trade-off, legal items to confirm with Twelve Data).
4. The paths of the three documents and the branch name, and the exact commands to review/merge them.
5. What you could not verify and why.

Do not ask the user questions during the run unless you are truly blocked; record your assumptions in the
review instead. Quality over speed: a smaller set of well-evidenced findings beats a long list of guesses.
