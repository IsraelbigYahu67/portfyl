# Trading 212 Snapshot-First Synchronization Plan

**Status:** Proposed

**Goal:** Make a newly connected Trading 212 portfolio useful within seconds by
loading the current account summary and open positions first, while complete
orders, dividends, cash movements, FX settlement, and split-aware history are
backfilled safely in the background. Subsequent syncs must be incremental and
must never download the complete history merely to discard already known rows.

**Architecture:** Trading 212 synchronization is split into two data contracts.
The **current snapshot** contract uses `/equity/account/summary` and
`/equity/positions` to power current holdings, allocation, current value,
unrealized P/L, and broker cash as soon as those two calls finish. The
**historical ledger** contract imports broker events through a persisted,
resumable sync run. It stages raw pages, follows each endpoint's full
`nextPagePath`, pauses according to returned rate-limit headers, and finalizes
history only after all required streams are complete. Split normalization and
corporate-action cleanup run over the complete staged event set, never over one
rate-limit batch in isolation. Historical analytics remain ledger-based;
snapshots never fabricate transactions or rewrite history to force agreement.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, PostgreSQL forced RLS, Alembic,
`httpx.AsyncClient`, Cloud Scheduler internal jobs, React 18, TanStack Query,
pytest, PostgreSQL integration tests, Vitest.

**Related specifications and plans:**

- `docs/superpowers/specs/2026-09-20-portfyl-snowball-gap-roadmap-design.md`
  sections 2, 4.1, 4.8, and 6. In particular: snapshots are not history and
  Portfyl does not invent reconciliation transactions. This plan does not
  implement section 4.8's full user-facing corporate-action register. It
  treats provider-labelled T212 actions as authoritative import evidence,
  records their application in sync provenance, and defers discovered or
  ambiguous actions to that later review workflow.
- `docs/superpowers/plans/2026-09-20-portfyl-cash-reconciliation.md` for the
  existing `BrokerBalance` snapshot and snapshot-versus-ledger presentation.
- `docs/superpowers/plans/2026-09-04-portfyl-secrets-jobs.md` for cloud job
  authentication, advisory locks, dead-letter behavior, and local/cloud job
  execution boundaries.
- `docs/superpowers/plans/2026-09-07-portfyl-onboarding-import-safety.md` for
  T212 CSV coverage, duplicate-aware import, and undo behavior that broker sync
  must preserve.

## 1. Evidence and current problem

Snowball's public broker-connection documentation describes a snapshot-first
trade-off: current holdings are imported immediately, broker history is often
limited, and users who need exact historical analytics import complete broker
reports separately. Snowball explicitly lists realized P/L, full performance,
benchmark comparisons, and dividend history as incomplete without full
history. Its T212 CSV documentation also tells users to import only the period
since their previous import.

Portfyl currently takes the opposite path in `backend/routers/broker.py`:

1. `_fetch_all_orders()` exhausts every order page.
2. Only then is `/equity/account/summary` fetched.
3. Every returned order is parsed and most old rows are discarded locally.
4. `_fetch_all_dividends()` then exhausts every dividend page.
5. Split lookups and database writes finish before the HTTP response returns.

This blocks current portfolio data behind history that is not required for the
first screen. It also repeats the full download on every later sync. The code
does not call `/equity/positions`, even though that endpoint returns current
quantity, average price, current price, total cost, current value, unrealized
P/L, instrument identity, and currency in one request.

The problem is not simply that Portfyl requests too many JSON fields. T212 does
not expose field projection on these endpoints. The material waste is that
Portfyl requests every historical page repeatedly and ignores authoritative
fields already present in the responses, including fill identity/type,
`walletImpact`, and the paid dividend amount.

## 2. Product contract

### 2.1 Data available immediately

After the current snapshot succeeds, Portfyl may show:

- open holdings and quantities;
- average price and broker total cost;
- current price and value;
- unrealized P/L;
- current cash and net liquidation value;
- current allocation and exposure;
- current-position dividend forecasts and upcoming events.

These surfaces must identify the source as `Trading 212 snapshot` and expose a
freshness timestamp. A fresh broker snapshot is preferred for current-value
surfaces. Portfolios without a broker snapshot continue to use the transaction
ledger exactly as today.

For this plan, `fresh` means a successful snapshot no older than 25 hours.
Summary and positions track independent `last_attempt_at`, `last_success_at`,
and bounded error state. A failed refresh does not delete the last successful
snapshot. A snapshot older than 25 hours remains visible in reconciliation and
status responses as stale, but current portfolio APIs fall back to the ledger
instead of silently letting it override the ledger indefinitely.

### 2.2 Data unavailable until history completes

The following remain ledger-based and must show an importing/unavailable state
until the initial historical backfill is complete:

- realized P/L and closed-position history;
- lifetime and period performance derived from actual cash flows;
- TWR, XIRR, risk history, and benchmark comparisons;
- complete dividend history;
- cash-flow history and reconciliation confidence;
- FIFO lots and local-edition tax reporting;
- any assistant answer that claims complete historical performance.

No current snapshot value may silently substitute for those calculations.

### 2.3 Current API field contract

Existing current endpoints mix current and historical fields, so snapshot
selection must be explicit rather than swapping their backing data invisibly.

While a fresh position snapshot exists, `/portfolio/holdings` returns ticker,
name, quantity, average cost, current price, market value, total cost, and
unrealized P/L from the snapshot. It adds top-level `current_source`,
`current_as_of`, `history_status`, and `history_complete`. Per-holding realized
P/L, received dividends, holding-period returns, and other ledger-only fields
are `null` until history completes. `include_closed=true` returns a clear
history-unavailable state rather than presenting an empty list as proof that no
closed positions exist.

While a fresh account snapshot exists, `/portfolio/summary` returns current
cash, stock value, total value, broker total cost, and snapshot unrealized P/L
from the broker snapshot. Realized P/L, historical dividends, fees, total
historical P/L, TWR/XIRR, and history-dependent percentages are `null` with the
same history metadata until finalization. Frontend formatters must treat these
as unavailable, never as zero.

After complete history exists, current fields may continue to prefer a fresh
broker snapshot while historical fields come from the ledger. Every mixed
response identifies both sources and timestamps. Manual and CSV-only
portfolios retain today's ledger response behavior.

### 2.4 Progress language

T212 does not return a total row count. The UI may say:

> Loaded 300 orders and 84 dividends. More history remains. Continuing after
> Trading 212 resets the request limit.

It must not show a percentage or `300 of 900` unless a real total becomes
available from the provider.

## 3. Non-negotiable constraints

- Preserve workspace predicates and forced PostgreSQL RLS on every persisted
  snapshot, run, and staged-event row.
- Public APIs use UUID `public_id` values only. Integer IDs remain internal.
- Cloud Run requests do not sleep until a provider limit resets. Progress and
  cursors are persisted; an external job resumes the run.
- Local edition may use its existing single-instance poller, but it consumes
  the same persisted run state and service functions as cloud.
- Never share a SQLAlchemy session across concurrent HTTP workers. HTTP fetches
  may run concurrently; database mutation remains serial and transactional.
- Never create synthetic trades, deposits, or split rows to force snapshot and
  ledger quantities to match.
- Never delete existing portfolio transactions merely because credentials are
  connected or rotated.
- A waiting provider rate limit is normal state, not a failed sync and not a
  dead-letter failure.
- `last_synced_at` means a complete successful synchronization. Partial
  snapshot/backfill timestamps use separate fields.
- History backfill has a dedicated minutely `broker_backfill` pass. It is
  independent of `auto_sync` and the user's recurring broker schedule; an
  initial user-requested run must finish even when auto-sync is disabled.
- Use the complete `nextPagePath` returned by T212. Do not reconstruct it from
  only the cursor.
- The first full historical bootstrap may read the complete available history.
  A successful bootstrap establishes durable checkpoints; later syncs are
  incremental.

## 4. Persistence design

### 4.1 Current position snapshots

Add a tenant table `broker_positions` with at least:

- `public_id`, `workspace_id`, `portfolio_id`, `broker`;
- raw provider ticker and normalized Portfyl ticker;
- ISIN, name, and instrument currency;
- quantity, quantity available, and quantity in pies;
- average price paid and current price;
- broker wallet currency, total cost, current value, FX impact, and unrealized
  P/L where supplied;
- `as_of`/`updated_at` freshness fields.

Use a uniqueness constraint on workspace, portfolio, broker, and provider
instrument identity. Replace one portfolio's position snapshot atomically: a
successful empty positions response deletes prior open-position rows; a failed
request leaves the previous snapshot intact and marked stale.

Keep `BrokerBalance` as the account-level summary snapshot. Add connection-level
snapshot metadata for independent summary and positions attempts/successes,
bounded errors, and stale-state calculation. Store a hash/fingerprint of the
upstream account identity and a monotonically increasing `credential_generation`.
Do not persist the raw broker account number in API-visible form.

### 4.2 Resumable sync runs

Add a tenant table `broker_sync_runs` with:

- workspace, portfolio, broker connection, and public run ID;
- immutable upstream-account fingerprint and credential generation copied from
  the connection when the run is created;
- mode: `initial` or `incremental`;
- state: `pending`, `fetching`, `waiting_rate_limit`, `finalizing`,
  `completed`, `failed`, or `cancelled`;
- independent stream state for `orders`, `dividends`, and `transactions`;
- the full next-page path, completion flag, loaded count, and reset timestamp
  for each stream;
- start, last-progress, completion, retry, and bounded error fields;
- a finalization generation/idempotency marker.
- a short-lived advancement lease token and expiry used by both foreground and
  background workers.

Only one non-terminal run may exist for a connection. A second user click
returns the existing run rather than creating concurrent pagination walks.
One-active-run uniqueness does not itself serialize workers: every worker must
atomically claim the run with `SELECT ... FOR UPDATE SKIP LOCKED`, issue a
bounded lease, and verify the lease token when committing a page. An expired
lease is recoverable after process death. The foreground route and scheduler
use exactly the same claim path.

The `transactions` stream uses `/equity/history/transactions` to capture
deposits, withdrawals, fees, interest, and lending interest. This is required
for API-only cash history to become reconcilable; it runs in the background and
does not delay the current snapshot.

### 4.3 Raw event staging

Add `broker_sync_events`, scoped to workspace, portfolio, and run, containing:

- stream name;
- stable provider event ID;
- provider event timestamp;
- raw JSON payload;
- received timestamp.

Use `fill.id` as the order-fill identity, not only `order.id`, because one order
may have multiple fills. Use dividend `reference` and transaction `reference`
for their streams. When a provider ID is absent, use a versioned stable payload
fingerprint. Uniqueness across upstream-account fingerprint, credential
generation, stream, and provider identity makes page retries idempotent.

The page payload insert and advancement to its returned `nextPagePath` happen
in one database transaction. A crash either leaves both unapplied or commits
both. Re-reading a committed page is harmless because of the unique event key.

Completed staging rows are transient operational data. Delete them after a
short bounded retention period; failed runs may retain them longer for safe
resume. Exclude raw staging payloads from normal workspace export, cascade them
on account deletion, document them in the processing inventory, and never put
payloads in logs or audit metadata.

### 4.4 Durable transaction identity and time

Extend `Transaction` with nullable structured provider provenance:

- `source_event_id`;
- `source_event_stream`;
- `source_account_fingerprint` and optional credential generation provenance;
- `source_instrument_id` such as the raw T212 instrument ticker;
- `executed_at` as an aware timestamp;
- optionally `source_event_type` where needed for audit/debugging.

Add a partial unique constraint for non-null provider IDs within workspace,
portfolio, source, source account, and stream. Credential generation fences
requests but is deliberately not part of durable event identity, so rotating
keys for the same upstream account cannot duplicate every event. Existing
CSV/manual rows remain valid. Preserve current cross-source fingerprint and
T212 CSV coverage logic because legacy rows do not have provider IDs.

Define one shared chronological sort key and migrate every ledger consumer to
it: use aware `executed_at` when present, otherwise date plus the existing
documented type-order fallback for date-only CSV/manual rows. Holdings/FIFO,
realized P/L, cash timelines, performance, analytics, assistant context, and
split processing must all consume this helper. Adding the column without
changing these consumers is not considered timestamp support.

Do not attempt an unsafe migration that infers fill IDs from existing notes.
The first run under the new engine uses the existing dedup/cutoff rules once,
then marks full API coverage and uses provider IDs for future runs.

Add fields needed to keep gross analytical values distinct from actual cash:
dividend quantity and gross amount per share remain `shares` and `price`, while
the provider-paid amount and account currency use `cash_amount` and
`cash_currency`. Preserve provider dividend type and trade tax/fee breakdown in
bounded structured provenance; preserve broker realized P/L as reconciliation
metadata, not as the source of Portfyl FIFO P/L. All received-income and cash
consumers use `cash_amount` when present, with `shares * price` only as a legacy
fallback. Forecast/DPS consumers may use gross per-share data and must not
confuse it with received net cash.

Every new tenant table uses composite workspace-parent foreign keys, forced
RLS, explicit runtime-role table grants, and sequence grants when integer
sequences are used. A migration cannot rely on the static table lists in
`0002_tenant_rls.py` to cover tables created later.

## 5. Synchronization flow

### 5.1 Connect or rotate credentials

1. Validate credentials without deleting transactions.
2. Fetch a non-public upstream-account fingerprint.
3. If credentials point to a different account than an existing connection,
   require an explicit replace/new-portfolio decision rather than silently
   mixing or deleting data.
4. Before any credential mutation, cancel and fence active runs. Increment the
   connection's credential generation even when the upstream account is the
   same, so no request made with old credentials can commit afterward.
5. Clear dead-letter state after successful credential validation.
6. Start a fresh snapshot/history run from durable completed coverage. An
   incomplete cancelled run's staged rows are never resumed under new
   credentials.

This replaces the current destructive connect behavior in
`backend/routers/broker.py`, which deletes all portfolio transactions before a
sync has succeeded.

### 5.2 Fast snapshot phase

Fetch `/equity/account/summary` and `/equity/positions` concurrently through a
single `httpx.AsyncClient`. Each request independently preserves the previous
snapshot on failure.

Persist balance and positions atomically per snapshot type. Return snapshot
availability as soon as this phase finishes. The response starts or references
the active history run and normally returns `202 Accepted` while backfill is
pending.

Example response:

```json
{
  "snapshot": {
    "status": "ready",
    "positions": 14,
    "as_of": "2026-09-20T14:30:04Z"
  },
  "history": {
    "run_id": "9ee9994a-8dd3-4c42-b76d-c29109141d34",
    "status": "fetching",
    "orders_loaded": 50,
    "dividends_loaded": 34,
    "transactions_loaded": 50,
    "complete": false,
    "resume_at": null
  }
}
```

The foreground request may make a bounded first history pass so the user sees
immediate progress, but it has a strict wall-clock deadline. It never waits for
a reset window.

### 5.3 History pagination and rate limits

Orders, dividends, and cash transactions advance independently and may fetch
concurrently. After every response:

1. Stage unique events.
2. Store the complete next-page path.
3. Read `x-ratelimit-remaining` and `x-ratelimit-reset`.
4. Mark a stream complete when `nextPagePath` is null.
5. Mark only that stream waiting when its remaining count reaches zero.

Do not assume that rate-limit buckets are shared or independent. Obey the
headers returned for each request. If a `429` occurs, parse the provider reset
information, persist a waiting state, and do not count it as a connection
failure.

In cloud, an authenticated external scheduler job scans due runs and advances
them under the existing workspace/RLS discipline and an advisory lock. In
local, the existing single-instance poller invokes the same operation. A user
keeping the page open may poll progress, but browser presence is never required
for completion.

This is a new `broker_backfill` recurring job, not an extension of
`autosync_tick()`. It runs minutely, regardless of a connection's `auto_sync`
flag or configured daily/interval schedule, and only advances already-created
due runs. Add it to `RECURRING_JOB_NAMES`, subsystem-health expectations, local
poller startup, the cloud internal-jobs router, Cloud Scheduler deployment, and
the operations runbook. Auto-sync may create an incremental run when due; the
dedicated backfill pass is what drains that run afterward.

Every per-page commit/rollback clears transaction-local RLS context. The job
must reassert `_set_job_workspace_context()` immediately after each commit or
rollback before touching tenant data again. A real PostgreSQL test must cover
multiple pages, internal commits, and more than one workspace.

### 5.4 Historical finalization

Finalization starts only after every required stream is complete. It is
idempotent and runs against the complete staged event set.

Before reading ledger state, finalization acquires the same PostgreSQL
workspace row lock used by T212 CSV commit and undo flows. Extract that locking
discipline into a shared ledger-mutation helper. After acquiring the lock,
finalization re-reads CSV coverage, current transactions, and the import-undo
fingerprint before deduplication. CSV replacement, undo, API finalization, and
other whole-ledger mutations may not interleave.

1. Parse all events with timestamp precision intact.
2. Import every actual fill, including fills whose parent order later became
   partially filled or cancelled. Do not require final `order.status == FILLED`
   when a valid fill exists.
3. Use `fill.walletImpact.netValue` as `cash_amount`, wallet currency as
   `cash_currency`, and the supplied FX orientation as verified by fixtures.
   Preserve taxes/fees and broker realized P/L as structured reconciliation
   provenance. Do not replace exact broker settlement with
   `shares * price * market FX` and do not double-count taxes as separate cash
   rows when they are already included in net settlement.
4. Store dividend quantity and gross amount per share as `shares` and `price`,
   and store provider `amount` plus account currency as the received
   `cash_amount`/`cash_currency`. Preserve type and reference. Remove the
   universal `15%` withholding assumption and update all received-dividend
   consumers to prefer actual cash.
5. Normalize transaction-stream cash movements into the existing cash-ledger
   event types.
6. Apply CSV coverage and legacy cross-source dedup rules before insertion,
   while holding the shared ledger-mutation lock.
7. Insert/update ledger rows in one database transaction.
8. Mark durable stream checkpoints and `last_synced_at` only after commit.

If finalization fails, the existing ledger remains unchanged and the staged run
can retry. Current snapshot views remain available with a warning that history
is not complete.

## 6. Split and corporate-action handling

### 6.1 Snapshot behavior

The positions endpoint is authoritative for the current open quantity and
broker cost snapshot. Current holdings can therefore render before historical
split normalization finishes. No yfinance request is required to show the
first current portfolio view.

### 6.2 Historical normalization

Use provider evidence first:

- preserve `fill.type` values such as `STOCK_SPLIT`, `STOCK_DISTRIBUTION`,
  `SPIN_OFF`, and acquisition/distribution events in staging;
- treat `TRADE` fills as user trading activity;
- do not infer a user trade from a provider-labelled corporate-action fill.

For historical trade normalization that still requires a split timeline:

1. Collect affected normalized tickers after all pages are staged.
2. Fetch yfinance split history once per ticker through one shared lookup.
3. Cache positive and negative results with a bounded TTL; negative results are
   never permanent.
4. Apply `shares *= ratio` and `price /= ratio` only to eligible pre-split
   trades, preserving notional value and exact broker cash settlement.
5. Match broker-generated close/open or give-back pairs across the complete
   staged history and relevant existing API rows, not only the current page.
6. Remove or transform a pair automatically only when T212 labels the event as
   a corporate action. A yfinance date alone may adjust the representation of
   a provider `TRADE` when the guarded price-ratio invariant is met, but it may
   not delete a trade or pair. Ambiguous/yfinance-only corporate actions become
   reconciliation warnings for the later reviewable corporate-action workflow.
7. Preserve provider action type, effective date, ratio/terms, and the
   finalizer audit reference so the later register can expose what happened.

Raw staged events remain immutable. Final transactions are produced from raw
events on each retry, and the final ledger commit is atomic. This makes split
finalization idempotent without a second split-specific generation counter.

### 6.3 Reconciliation after finalization

Recompute ledger open quantities and compare them with `broker_positions` by
provider instrument identity and normalized ticker. Return a non-mutating
reconciliation result:

- `matched` within a documented fractional-share tolerance;
- `different` with per-ticker broker and ledger quantities;
- `unavailable` when either side lacks data.

A mismatch does not create an adjustment transaction. It keeps history marked
as needing review and exposes likely causes such as incomplete broker history,
an unsupported corporate action, ticker mapping, or CSV/API overlap.

## 7. Incremental sync after bootstrap

After a successful full backfill, store separate durable coverage/checkpoint
state for orders, dividends, and transactions.

On later syncs:

- fetch the newest page first;
- stage unknown provider event IDs;
- continue with an overlap until a page is fully inside known covered history;
- do not stop merely because one event is older than the newest database date;
- fall back to a deeper walk if ordering or coverage invariants are violated;
- always refresh current summary and positions independently of history.

This preserves the existing requirement that an old event for a previously
unseen ticker must not be lost. A global `max(Transaction.date)` cutoff is not
sufficient. Provider IDs plus a completed-coverage checkpoint are the stopping
condition.

## 8. API and frontend changes

### Backend API

- Keep `POST /api/broker/trading212/sync` as the user action, but make it start
  or resume the new workflow and return snapshot/history state.
- Extend `GET /api/broker/trading212/status` with snapshot freshness, active
  run progress, history completeness, resume time, and reconciliation status.
- Add a narrowly scoped cancel/retry action only if operational testing proves
  it is needed; do not expose raw cursors or staged payloads.
- Refactor synchronization into a service module. Jobs must not call a FastAPI
  route handler directly.
- Add an authenticated internal endpoint/job pass that advances due backfills
  in cloud under an advisory lock.
- Use the same lease/claim service in the user route and internal job; the
  global scheduler advisory lock is not a substitute for per-run concurrency
  control.

### Frontend behavior

- Settings and Cash use one shared `useT212Sync` state machine for connect,
  manual sync, active-run discovery, polling, retry, and completion
  invalidation. Connect follows the run returned by the backend instead of
  reporting completion immediately; the existing `total_imported` success
  contract is retired.
- After snapshot readiness, invalidate current holdings, allocation, summary,
  and cash queries immediately.
- Poll status while a history run is active, with slower polling while waiting
  for a provider reset.
- Show distinct states: fetching snapshot, importing history, waiting for T212,
  processing splits, reconciling, complete, and action-required failure.
- Keep current snapshot-backed pages usable during backfill.
- Gate or label historical metrics explicitly until history is complete.
- On completion, invalidate all ledger-derived analytics once rather than
  maintaining the current incomplete per-page invalidation lists.
- Dividend notifications use current snapshot positions when fresh, with the
  same ledger fallback as current holdings. Assistant context includes
  `history_complete` and must refuse or qualify history-wide claims while a
  backfill is incomplete.

## 9. File responsibility map

- `backend/t212_sync.py` (new): T212 HTTP client, response mapping, rate-limit
  parsing, snapshot fetch, run advancement, and finalization orchestration.
- `backend/models.py`: `BrokerPosition`, `BrokerSyncRun`, `BrokerSyncEvent`, and
  structured transaction provenance fields.
- `backend/alembic/versions/`: schema, tenant indexes, uniqueness, cascade, and
  forced-RLS migration, explicit runtime table grants, and sequence grants.
- `backend/routers/broker.py`: thin HTTP/status/connect/disconnect layer; remove
  destructive connect and direct full-history implementation.
- `backend/broker_cash.py`, `backend/routers/portfolio.py`, and
  `backend/routers/analytics.py`: explicit current-snapshot versus historical-
  ledger source selection.
- `backend/transaction_ordering.py` (new), `backend/cash_ledger.py`, and every
  FIFO/performance consumer: timestamp-first chronological ordering with
  date/type fallback.
- `backend/jobs.py`, `backend/routers/internal_jobs.py`, `backend/main.py`: due
  run advancement through a dedicated minutely `broker_backfill` job using the
  established local/cloud scheduler boundary, independent of auto-sync.
- `backend/workspace_export.py`, account deletion, retention, compliance docs:
  position snapshot handling and transient-stage lifecycle.
- `backend/import_undo.py` and import commit/undo paths: shared workspace ledger
  lock plus round-trip preservation of provider provenance and timestamps.
- `backend/routers/assistant.py` and dividend notification jobs: explicit
  snapshot source and history-completeness behavior.
- `frontend/src/api.js`: workflow/status contracts.
- `frontend/src/pages/Settings.jsx`, `frontend/src/pages/Cash.jsx`, shared sync
  progress component, and historical metric surfaces: progress and data-quality
  states.
- `backend/tests/`, `backend/tests/postgres/`, and frontend tests: behavior,
  tenancy, recovery, and UI state coverage.

## 10. Delivery sequence

### Task 1: Lock provider mappings and current behavior

- [ ] Add fixtures for summary, positions, multi-fill orders, all relevant
      corporate-action fill types, dividends, and cash transactions.
- [ ] Add regression tests for current CSV/API overlap and unseen-ticker
      behavior before refactoring.
- [ ] Add tests proving exact dividend amount and wallet settlement fields are
      preferred over estimates.

### Task 2: Add current position snapshots

- [ ] Add `BrokerPosition`, migration, forced RLS, cascade, export/retention,
      and tenant-isolation coverage.
- [ ] Implement concurrent summary/positions fetch and atomic snapshot replace.
- [ ] Update current-value surfaces to prefer a fresh snapshot while preserving
      ledger fallback for manual/CSV portfolios.
- [ ] Define exact holdings/summary nullable-field, source, freshness, and
      `include_closed` behavior while history is incomplete.
- [ ] Prove historical analytics remain ledger-only and stale snapshots older
      than 25 hours do not silently override them.

### Task 3: Add persisted resumable runs

- [ ] Add run and event staging models, migrations, RLS, unique event identity,
      and one-active-run enforcement.
- [ ] Follow full `nextPagePath` values and commit each page with its cursor.
- [ ] Parse rate-limit headers and represent waiting without failure.
- [ ] Add per-run leases used by both foreground and background advancement.
- [ ] Add a dedicated minutely due-run pass to local polling and authenticated
      cloud jobs, independent of connection auto-sync and user schedule.
- [ ] Reassert transaction-local RLS context after every page commit/rollback.

### Task 4: Implement exact split-aware finalization

- [ ] Map fills by `fill.id`, preserve timestamps, and handle partial/cancelled
      parent orders correctly.
- [ ] Use exact wallet/dividend fields and import cash transaction history.
- [ ] Normalize splits once per ticker over the complete run.
- [ ] Handle corporate-action pairs across page and rate-window boundaries.
- [ ] Use the shared workspace ledger lock, re-read CSV/import state, finalize
      atomically, and reconcile ledger quantities to snapshot positions.
- [ ] Introduce timestamp-first ordering across every chronological consumer.
- [ ] Preserve new transaction fields through import undo and workspace export.

### Task 5: Make later syncs incremental

- [ ] Persist per-stream completed coverage and overlap checkpoints.
- [ ] Stop only on provider identity plus known complete coverage.
- [ ] Preserve fallback full/deeper walks when invariants fail.
- [ ] Remove duplicate full-history fetch paths and duplicate yfinance lookups.

### Task 6: Ship progress and data-quality UX

- [ ] Return `202` plus snapshot/history state from sync.
- [ ] Add shared progress UI and status polling.
- [ ] Make current data available immediately and gate historical claims.
- [ ] Handle close/reopen/browser-away flows without losing progress.
- [ ] Update dividend notifications and assistant claims for snapshot/history
      source state.

### Task 7: Operational and end-to-end verification

- [ ] Update Cloud Scheduler runbook and subsystem health for stalled runs.
- [ ] Add the `broker_backfill` recurring job name, endpoint, heartbeat, cloud
      schedule, and local loop.
- [ ] Add cleanup for completed/abandoned staging data.
- [ ] Run fast backend, frontend local/cloud, build, and PostgreSQL/RLS suites.
- [ ] Verify on a disposable T212 demo account with enough history to cross a
      rate-limit reset, including a ticker with a historical split.

## 11. Required tests

At minimum, cover:

- snapshot is visible when history is still importing;
- holdings/summary expose snapshot-backed and unavailable historical fields
  without converting `null` to zero;
- snapshots older than 25 hours are reported stale and current APIs fall back
  according to the documented source rule;
- summary failure does not discard a valid positions snapshot and vice versa;
- an empty successful positions response clears stale open positions;
- a provider reset between any two pages resumes from the stored full path;
- `429` becomes waiting state and does not increment dead-letter failures;
- process termination after event insert but before/after cursor advancement is
  idempotent;
- duplicate user clicks return the active run;
- two Cloud Run workers cannot advance/finalize one run concurrently;
- a foreground request and scheduler invocation cannot advance one run
  concurrently;
- an initial run resumes with `auto_sync=false` and no broker schedule due;
- credential rotation fences an old run before any page can commit with the new
  account or credential generation;
- two identical same-day fills with distinct fill IDs both survive;
- one order with multiple fills imports every fill;
- dividend received amount uses provider `amount`, not a fixed tax estimate;
- split pair divided between pages and rate windows is handled correctly;
- split retry applies the ratio exactly once;
- yfinance-only evidence never deletes a user trade;
- legitimate same-day buy/sell is retained;
- current broker quantity and finalized ledger quantity reconcile;
- a mismatch is reported without a synthetic adjustment;
- existing CSV-covered history is not duplicated or resurrected;
- CSV replace/undo racing API finalization serializes on the shared workspace
  ledger lock and preserves a coherent undo snapshot;
- API transactions restored by CSV undo retain event IDs and timestamps;
- an older event for an unseen ticker is not skipped;
- timestamp ordering changes same-day FIFO/cash/split behavior correctly while
  date-only CSV rows retain the documented fallback order;
- received dividend totals use provider cash amount while gross DPS/forecast
  logic retains gross per-share semantics;
- Alice cannot read, advance, cancel, or inspect Bob's run/snapshot/staging rows;
- every page commit reasserts RLS context before the next tenant query;
- disconnect/account deletion cascades operational snapshots and run data but
  follows the explicit product decision for durable transaction history;
- local and cloud frontend states remain correct at mobile and desktop widths.

## 12. Definition of done

- A newly connected account shows current cash and positions after only the
  summary/positions snapshot phase.
- Historical import continues after the browser closes and across Cloud Run
  instance restarts.
- Rate-limit resets pause and resume work without user retries or false failure
  alerts.
- Complete initial history is finalized atomically with exact provider identity,
  settlement, dividend amount, timestamp, and split-aware normalization.
- Current snapshot and ledger history are visibly distinct and reconcilable.
- Subsequent syncs normally read only new pages plus a bounded overlap.
- No connect/sync path deletes existing transactions or fabricates adjustment
  transactions.
- PostgreSQL forced-RLS tests, fast backend tests, frontend local/cloud tests,
  and both builds pass.

## 13. External references

- T212 positions: https://docs.trading212.com/api/positions/getpositions
- T212 account summary:
  https://docs.trading212.com/api/accounts/getaccountsummary
- T212 orders history:
  https://docs.trading212.com/api/historical-events/orders_1
- T212 dividends history:
  https://docs.trading212.com/api/historical-events/dividends
- T212 transactions history:
  https://docs.trading212.com/api/historical-events/transactions
- T212 rate limiting:
  https://docs.trading212.com/api/section/rate-limiting
- Snowball broker connection behavior:
  https://help.snowball-analytics.com/yodlee/
- Snowball T212 incremental CSV guidance:
  https://help.snowball-analytics.com/import-trading212/
