# Trading 212 Snapshot-First Synchronization Plan

**Status:** In progress. §10 Task 1 (contract-locking fixtures/tests), Task 2
(fast snapshot plus durable T212 account binding), a scoped Task 3 (resumable
history runs), scoped Task 4 slices (finalize into ledger rows, account-identity
guards, CSV event identity/timestamps, serialized ledger mutations, and
provenance preservation through undo/export), and scoped Task 6 frontend slices
are implemented. The earlier backend slice passed the fast and PostgreSQL/RLS
suites; the 2026-09-24 additions pass the 899-test fast suite and the existing
frontend local/cloud gates, but PostgreSQL could not be rerun because Docker was
unavailable.

- **Task 2**: `backend/t212_sync.py`, the `BrokerPosition` model and
  `0014_broker_positions` migration (forced RLS, grants, cascade, workspace
  export), concurrent summary+positions fetch wired into
  `POST /trading212/sync`, the new `GET /trading212/positions` read endpoint,
  and the 25-hour freshness rule. The `0017_position_snapshot_time` migration
  records successful empty position snapshots separately from never fetched;
  unknown instrument currency now leaves converted monetary values null.
  `backend/account_identity.py` and the `0018_t212_account_binding` migration
  add a keyed, non-reversible upstream account identity (HMAC over
  `PORTFYL_ACCOUNT_FINGERPRINT_KEY`, no raw provider account ID stored) across
  portfolio, connection, run, staged-event, and finalized-transaction rows.
  Connect and sync verify the chain end-to-end and reject a different account
  with HTTP 409; disconnect retains the portfolio binding while removing
  credentials/snapshots; same-account credential rotation preserves ledger,
  snapshots, and the snapshot-freshness marker; and background backfill
  cancels any run whose identity drifts from its connection or portfolio.
  Cloud deploy now provisions `portfyl-account-fingerprint-key` (see
  `deploy/cloudrun.md`).
- **Task 3**: `BrokerSyncRun`/`BrokerSyncEvent` + `0015_broker_sync_runs`
  migration (forced RLS, grants, cascade, and the partial-unique-index
  one-active-run-per-connection DB backstop); `BrokerConnection.credential_generation`
  fencing (`connect()` cancels active runs and bumps generation on rotation);
  `t212_sync.claim_or_create_run`/`claim_lease`/`advance_run` (rate-limit
  parsing, `nextPagePath` validation against forged/absolute/cross-endpoint
  URLs, per-page staging and checkpointing, lease-loss detection); the new
  minutely `broker_backfill` job (`jobs.py`, registered in
  `RECURRING_JOB_NAMES`, the local poller, `/internal/jobs/broker_backfill`,
  `/health`, and `deploy/cloudrun.md`); `sync_transactions` starts/returns the
  active run (structured `snapshot`/`history` response); the new
  `GET /trading212/history-status` read endpoint.
- **Task 4 (scoped slice)**: `Transaction` provenance columns
  (`source_event_id`/`source_event_stream`/`source_credential_generation`/
  `source_instrument_id`/`source_fill_type`/`executed_at`/`source_payload_hash`/
  `source_mapper_version`) + `0016_transaction_provenance` migration
  (including a partial-unique-index idempotency backstop on
  `(workspace_id, portfolio_id, source, source_event_stream, source_event_id)`);
  `backend/transaction_ordering.py`'s shared chronological sort key, now wired
  into holdings, summary realized P/L, capital-gains/FIFO, performance value
  series, lifetime returns, and assistant recent activity; and
  `t212_sync.finalize_run`, which turns a "finalizing" run's staged
  `BrokerSyncEvent` rows into `Transaction` rows with exact settlement
  (`fill.walletImpact.netValue` when the provider gives it) and the actual
  paid dividend amount (provider `amount`) instead of guessing withholding.
  A staged dividend without a usable paid amount now fails finalization;
  gross quantity and per-share value remain separate from received cash.
  Valid fills survive partial/cancelled parent-order statuses, distinct
  same-day fills retain their provider IDs, and one legacy/CSV row can match
  only one fill. Exact native settlement survives a missing CZK FX rate.
  Provider `amount` uses `items.currency` (account currency), while gross
  per-share price uses `items.instrument.currency`; price and settlement FX
  are resolved separately, including when those currencies differ.
  Received-dividend totals in holdings, summary, forecast, tax report, and
  lifetime returns now prefer actual `cash_amount` over gross `shares*price`.
  `finalize_run` fail-closes unless portfolio, connection, run, and every
  staged event share one account fingerprint and the credential generation
  still matches; imported rows record `source_account_fingerprint`.
  Transaction provenance (event IDs, timestamps, account fingerprint,
  mapper/hash fields) now survives CSV import undo via undo schema v2 — still
  accepting still-live v1 recovery points — and is included in the workspace
  export (export schema bumped to 3). T212 CSV normalization now preserves the
  full UTC execution timestamp and export ID; multi-leg currency conversions
  and split rows receive deterministic per-leg event IDs. Preview/import
  canonicalization prefers durable source identity and otherwise includes the
  full timestamp, so distinct same-day fills no longer collapse. Finalization
  treats the latest portfolio/connection T212 CSV coverage timestamp as an
  account-wide authoritative cutoff and does not resurrect older API events.
  A shared
  PostgreSQL workspace ledger lock now serializes CSV commit/undo, manual and
  cash CRUD, clear-all, demo/portfolio deletion, and staged finalization.
  Broker-managed rows are immutable through single-row
  CRUD, while clear-all cancels recorded history runs and invalidates T212
  coverage before committing.
  `jobs.broker_backfill_pass` invokes `finalize_run` after every required
  stream is staged, and resumes a run already in `finalizing` without fetching
  history again. The run's `completed` transition, finalized ledger rows, and
  connection `last_synced_at` update share the same atomic commit. The legacy
  unbounded full-history writer has been removed from the production route.
  `backend/broker_reconciliation.py` adds the §6.3 read-only comparison of
  ledger open quantities with the position snapshot (matched / different /
  unavailable per normalized ticker, direction and likely-cause hints, never an
  adjustment row). It is exposed as `reconciliation` on
  `GET /trading212/history-status`, is `unavailable` until the latest run
  completed and a positions snapshot exists, and has no UI consumer yet.
- **Task 6 (scoped slices)**: Settings and Cash share
  `frontend/src/hooks/useT212Sync.js` for portfolio-scoped
  connection/history/position queries, adaptive polling, manual-sync
  invalidation, and a derived workflow phase. Settings, Dashboard, and
  Allocation show current T212 positions in a distinct snapshot panel with
  freshness, quantity, value availability, empty, and retry states. Historical
  charts remain ledger-derived. Dividend notifications prefer fresh snapshot
  quantities and fall back to the ledger; assistant context explicitly warns
  that bound T212 history may be incomplete, including after disconnect. The
  run's `completed` label now means staged history was atomically imported;
  final completion invalidates ledger analytics exactly once per run.

Deliberately deferred within Task 2: the §2.3 stable
`/portfolio/holdings` / `/portfolio/summary` response envelope and "migrate
all callers" — that is a much larger, separately reviewable change touching
most of the frontend, not bundled into this slice.

Deliberately deferred/simplified within Task 3 (see `backend/t212_sync.py`'s
own "Task 3: resumable history runs" section docstring for the authoritative
list): the `/equity/history/transactions` cash-movement stream is not
fetched (a new provider surface, not resumability of an existing fetch); run
  fencing uses `credential_generation` plus the HMAC account fingerprint
  (§4.1/§5.1) — a different T212 account is detected and rejected; and
  `mode="audit"` runs are never created. Reaching `finalizing` means every
  required page is staged; `completed` now means ledger finalization committed.

Deliberately deferred/simplified within Task 4 (see `t212_sync.py`'s "Task 4
(scoped slice)" section docstring for the authoritative list): split and
corporate-action detection/adjustment (§6) — a fill whose `fill.type` isn't
"TRADE" (and isn't already covered by an authoritative CSV export) sends the
run to terminal `needs_review` (§6.2.8): nothing is imported, no completion or
`last_synced_at` is set, and `history-status` reports a dedicated non-retry
message. The provider docs list the `fill.type` values (`STOCK_SPLIT`,
`STOCK_DISTRIBUTION`, `FOP`, `SPIN_OFF`, `STOCK_ACQUISITION`, ...) but do not
document how a split pair encodes quantity, sign, or price, so the mechanical
same-instrument `STOCK_SPLIT` mapper, `BrokerCorporateAction` records, and
their application identities wait for real provider payloads (Task 1's
corporate-action fixtures). Until then a portfolio whose history contains any
such action gets the snapshot but no imported history; every new sync re-stages
the history and lands in `needs_review` again. Per-ticker heuristics are
deliberately not treated as authoritative history coverage. The finalizer is
wired into `broker_backfill`; full split/corporate-action processing and
cash-movement history remain deferred.

Task 5 (incremental sync + audits) is not started. Task 6 still needs a real
authenticated browser check, blocked by the missing local backend and verified
Firebase test login. Migrations `0017`/`0018` still need the real
PostgreSQL/RLS suite; Docker Desktop did not respond under this account. The
current `POST /trading212/sync` now returns after the summary/positions snapshot
and active-run creation; bounded backfill and atomic finalization continue in
the independent minutely worker.

**Goal:** Make a newly connected Trading 212 portfolio useful within seconds.
Load current positions and account value first, then backfill complete,
split-aware history safely in the background. Later syncs must be incremental
instead of downloading the full history and discarding known rows.

**Core decision:** Current broker state and historical ledger state are separate
contracts.

- `/equity/account/summary` and `/equity/positions` provide the current snapshot.
- Orders, dividends, and cash movements build the historical ledger through a
  persisted, resumable background run.
- Snapshots power current-value views only. They never replace transactions in
  historical performance, FIFO, tax, or cash-flow calculations.
- Portfyl does not create adjustment transactions to force the snapshot and
  ledger to agree.

**Tech stack:** FastAPI, SQLAlchemy 2.0, PostgreSQL forced RLS, Alembic,
`httpx.AsyncClient`, Cloud Scheduler, React 18, TanStack Query, pytest, Vitest.

**Related plans:**

- `docs/superpowers/plans/2026-09-04-portfyl-secrets-jobs.md` for external cloud
  jobs, advisory locks, RLS job context, and dead-letter behavior.
- `docs/superpowers/plans/2026-09-07-portfyl-onboarding-import-safety.md` for
  T212 CSV coverage, replace imports, duplicate handling, and guarded undo.

## 1. Why This Change

Portfyl currently does the expensive work first in
`backend/routers/broker.py`:

1. It exhausts every page from `/equity/history/orders`.
2. Only then does it fetch `/equity/account/summary`.
3. It discards already known historical rows locally.
4. It exhausts every page from `/equity/history/dividends`.
5. It performs yfinance split work and commits only at the end.

It does not call `/equity/positions`, although that endpoint returns current
quantity, average price, current price, total cost, current value, unrealized
P/L, instrument identity, and currency in one request.

The result is avoidable first-load latency and repeated full-history downloads.
The waste is not mainly unused JSON fields because T212 offers no field
projection. The waste is downloading every historical page on every sync and
ignoring authoritative response fields such as fill identity/type,
`walletImpact`, and the actual paid dividend amount.

## 2. User-Facing Data Contract

### 2.1 Available after the fast snapshot

As soon as summary and positions are available, Portfyl may show:

- current holdings and quantities;
- average price and broker total cost;
- current price, value, and unrealized P/L;
- current cash and net liquidation value;
- current allocation and exposure;
- position-based dividend forecasts and upcoming events.

These values identify their source as `Trading 212 snapshot` and expose the
last successful timestamp.

### 2.2 Unavailable until initial history completes

These remain ledger-based and must show an importing or unavailable state:

- realized P/L and closed positions;
- lifetime and period performance based on actual activity;
- TWR, XIRR, risk history, and benchmark comparison;
- complete dividend and cash-flow history;
- FIFO lots and local-edition tax reporting;
- assistant claims about complete historical performance.

Snapshot values must never silently substitute for these calculations.

### 2.3 Stable holdings and summary responses

The current `/portfolio/holdings` response is a bare array. Change it to one
stable envelope for every portfolio and migrate all callers:

```json
{
  "items": [],
  "sources": {
    "positions": {
      "source": "broker_snapshot",
      "as_of": "2026-09-20T14:30:04Z",
      "status": "fresh"
    },
    "account": {
      "source": "broker_snapshot",
      "as_of": "2026-09-20T14:30:03Z",
      "status": "fresh"
    },
    "history": {
      "status": "importing",
      "complete": false
    }
  },
  "closed_positions_available": false
}
```

The envelope shape never depends on whether a portfolio uses broker, CSV, or
manual data.

For a fresh broker snapshot, `items` gets ticker, name, quantity, average cost,
current price, market value, total cost, and unrealized P/L from T212.
Ledger-only fields such as realized P/L, received dividends, and holding-period
return are `null` until history completes. `include_closed=true` reports
`closed_positions_available=false` rather than returning an empty result that
looks authoritative.

`/portfolio/summary` remains an object but gains the same source, freshness,
and history metadata. Current cash, stock value, total value, total cost, and
unrealized P/L may come from the snapshot. Realized P/L, historical dividends,
fees, total historical P/L, TWR/XIRR, and history-dependent percentages are
`null` until history completes. Frontend formatters treat `null` as unavailable,
never as zero.

Manual and CSV-only portfolios use the same response envelope with ledger
source metadata and today's values.

Each item keeps the current field names and units so existing consumers can be
migrated without semantic guesses:

| Field | Snapshot source and unit while history imports |
|---|---|
| `ticker`, `name` | normalized T212 instrument identity |
| `shares` | T212 `quantity` |
| `avg_cost` | T212 `averagePricePaid`, instrument currency |
| `current_price` | T212 `currentPrice`, instrument currency |
| `market_value` | wallet `currentValue`, converted account currency to requested display currency |
| `cost_basis` | wallet `totalCost`, converted account currency to requested display currency |
| `pnl` | wallet `unrealizedProfitLoss`, converted to requested display currency |
| `pnl_percent` | `pnl / cost_basis`, or `null` when cost basis is unavailable |
| `weight` | converted `market_value` divided by total converted market value |
| `currency` | instrument currency, preserving existing per-share display semantics |
| `dividends` | `null` until history is complete |
| `closed` | `false` for snapshot positions |

`live_price`, `pnl_if_held`, `pnl_if_held_pct`, and `pnl_if_held_delta` remain
closed-position/history fields and are absent or `null` while unavailable.
Wallet values use the account's primary currency and are converted server-side
through the existing CZK pivot into the endpoint's `currency` query parameter.
Per-share prices remain in instrument currency, matching current behavior.

Summary and positions freshness are independent. Both holdings and summary
return the component-level `sources.positions`, `sources.account`, and
`sources.history` object; one aggregate `current_source` or timestamp is not
sufficient when one provider call succeeds and the other fails.

### 2.4 Freshness

Summary and positions keep independent `last_attempt_at`, `last_success_at`,
and bounded error state.

- A successful snapshot is fresh for 25 hours.
- A failed refresh does not delete the last successful snapshot.
- A failed refresh does not make a younger-than-25-hours snapshot stale; status
  reports it as fresh but degraded by the latest attempt error.
- A snapshot older than 25 hours is stale. If history is complete, current APIs
  fall back to the ledger. If history is incomplete, an old snapshot remains
  the only current-state evidence and is returned explicitly as stale with a
  warning; if no snapshot exists, current data is unavailable. An incomplete
  ledger is never presented as authoritative current holdings.

### 2.5 Progress copy

T212 does not provide a total row count. The UI may say:

> Loaded 300 orders and 84 dividends. More history remains. Continuing after
> Trading 212 resets the request limit.

It must not show a percentage or `300 of 900` without a provider total.

## 3. Non-Negotiable Constraints

- All persisted snapshot, run, and staging rows are workspace/portfolio scoped
  with application predicates and forced PostgreSQL RLS.
- Public APIs expose UUID `public_id` values, never integer database IDs.
- Cloud requests never sleep until a provider reset. State is persisted and a
  scheduler resumes due work.
- The initial backfill has a dedicated minutely job independent of `auto_sync`
  and the user's daily/interval sync schedule.
- Foreground and background page commits both reassert transaction-local RLS
  context before any subsequent tenant query. Background scans enumerate active
  workspaces first and claim runs only after setting each workspace context;
  they never issue a global tenant-run query under forced RLS.
- HTTP requests may run concurrently. SQLAlchemy sessions and database writes
  remain serial and transactional.
- A provider rate-limit wait is normal state, not a failed sync or dead-letter
  failure.
- `last_synced_at` means all required streams finalized successfully. Snapshot
  and partial-progress timestamps are separate.
- Follow the complete T212 `nextPagePath`; do not reconstruct it from only the
  cursor.
- Connecting or rotating credentials never deletes transactions.
- A different upstream T212 account cannot replace the account inside an
  existing portfolio. The user must create a new portfolio. This avoids mixing
  histories and avoids a hidden destructive replacement workflow.
- No synthetic trade, deposit, or corporate-action row is created merely to
  reconcile current and historical quantities.

## 4. Persistence Design

### 4.1 `BrokerPosition`

Add a tenant table with:

- `public_id`, `workspace_id`, `portfolio_id`, and broker;
- raw provider instrument identity and normalized Portfyl ticker;
- ISIN, name, and instrument currency;
- quantity, quantity available, and quantity in pies;
- average price and current price;
- wallet currency, total cost, current value, FX impact, and unrealized P/L;
- snapshot timestamp.

Use a unique key across workspace, portfolio, broker, and provider instrument.
Replace a portfolio's position rows atomically. A successful empty response
clears previous positions. A failed request retains previous rows and records
the attempt error; the 25-hour last-success rule determines staleness.

Keep the existing `BrokerBalance` for account summary. Add independent summary
and positions status metadata to `BrokerConnection`, together with:

- a salted/hash upstream-account fingerprint;
- monotonically increasing `credential_generation`;
- durable per-stream completed coverage/checkpoints;
- `history_complete_at`.

Never expose the raw upstream account number.

Persist the account fingerprint binding on `Portfolio` as well as the active
connection so disconnect cannot erase account identity while broker-origin
ledger rows remain. Disconnect fences/cancels active runs, removes current
position/balance snapshots and credentials, and stops snapshot serving, but it
retains the portfolio account binding and history. Reconnect is accepted only
for the same fingerprint; a different account requires a new portfolio.

Extend `BrokerBalance` so a successful summary survives independently of a
positions failure. Persist the provider components explicitly:

| Column | T212 summary field |
|---|---|
| `cash_available` | `cash.availableToTrade` |
| `cash_in_pies` | `cash.inPies` |
| `cash_reserved` | `cash.reservedForOrders` |
| existing `cash` | sum of the three cash components |
| existing `stock` | `investments.currentValue` |
| `stock_total_cost` | `investments.totalCost` |
| `stock_unrealized_pnl` | `investments.unrealizedProfitLoss` |
| `broker_realized_pnl` | `investments.realizedProfitLoss`, reconciliation metadata only |
| existing `net_liquidation` | `totalValue` |

All are in `base_currency`. In `/portfolio/summary`, convert current values via
the CZK pivot to the requested display currency: `total_value=stock`,
`total_invested=stock_total_cost`, `unrealized_pnl=stock_unrealized_pnl`,
`cash=cash`, and `net_worth=net_liquidation`. While history is incomplete,
`total_pnl`, `total_pnl_percent`, `total_dividends`, `accrued_interest`, and
history-derived day change remain `null`. Do not substitute broker realized P/L
for Portfyl FIFO realized P/L.

The account fingerprint is deterministic HMAC-SHA256 over broker, environment,
and provider account ID using a dedicated secret supplied through the existing
local secret/cloud Secret Manager configuration. A random per-row salt is not
used because identity must remain stable across credential rotations. For a
legacy connection without a fingerprint, populate it only after validating the
old credentials. If old credentials cannot be validated, fail closed: retain
the old portfolio/ledger and require a new portfolio for the new account.

### 4.2 `BrokerSyncRun`

Add a tenant table containing:

- connection, workspace, portfolio, and public run ID;
- immutable account fingerprint and credential generation copied at creation;
- mode: `initial`, `incremental`, or `audit`;
- state: `pending`, `fetching`, `waiting_rate_limit`, `finalizing`,
  `completed`, `needs_review`, `failed`, or `cancelled`;
- independent stream state for `orders`, `dividends`, and `transactions`;
- complete next-page path, completion flag, loaded count, and reset time for
  each stream;
- start, progress, completion, retry, and bounded error timestamps;
- finalization idempotency marker;
- short-lived worker lease token and expiry.

Only one non-terminal run may exist per connection. A repeated user action
returns the existing run.

This uniqueness does not serialize workers. Foreground and background workers
must use the same claim operation: `SELECT ... FOR UPDATE SKIP LOCKED`, assign
a bounded lease, and verify its token when committing progress. Expired leases
are recoverable after process death.

The `transactions` stream calls `/equity/history/transactions` for deposits,
withdrawals, fees, interest, and lending interest. It runs in the background
and does not delay current holdings.

### 4.3 `BrokerSyncEvent`

Stage raw events with:

- workspace, portfolio, run, account fingerprint, and stream;
- stable provider event identity;
- provider timestamp;
- raw JSON payload;
- received timestamp.

Use `fill.id` for order fills rather than only `order.id`, because one order may
have multiple fills. Use dividend and transaction `reference` values. If an ID
is absent, use a versioned stable payload fingerprint.

The staging unique key includes run ID, account fingerprint, credential
generation, stream, and provider identity. It deduplicates retries within one
run but permits a later audit run to stage and compare the same provider event.
Inserting one page and advancing to its returned next path happen in one
transaction. Re-reading a committed page is harmless. Failed work reopens and
resumes the same run; a deliberate new run may stage the IDs again and durable
transaction identity handles cross-run idempotency.

Raw staging payloads are transient operational data. Exclude them from normal
workspace export, cascade them on account deletion, document them in the data
processing inventory, never log them, and delete them after bounded completed
or failed-run retention.

### 4.4 Durable transaction provenance

Extend `Transaction` with nullable:

- `source_event_id` and `source_event_stream`;
- `source_account_fingerprint`;
- optional credential-generation provenance;
- `source_instrument_id` such as raw T212 ticker;
- aware `executed_at`;
- bounded source event type/provenance needed for audit and reconciliation.
- deterministic source payload hash and mapper/schema version.

The durable unique event key includes workspace, portfolio, source, upstream
account, stream, and event ID. Credential generation is deliberately not part
of durable identity, so rotating keys for the same account cannot duplicate
every event.

Do not infer fill IDs from legacy notes. The first run under this engine uses
existing exact fingerprints and account-wide authoritative T212 CSV coverage.
It must not treat a ticker's newest existing row as proof that older history is
covered: manual or partial history may contain a recent row while still missing
valid old fills. Only a precise completed T212 replacement-export coverage
timestamp may exclude older API events globally. After a successful full
bootstrap, provider IDs and completed coverage drive later syncs.

Preserve new provenance and timestamps in workspace export and
`backend/import_undo.py`. Undoing a CSV replace must not restore API rows
without their event IDs and make them importable again.

The import undo snapshot also captures/restores T212 history checkpoints,
history completeness, durable `BrokerCorporateAction` rows, and per-transaction
action application records associated with the portfolio. Restore them in the
same workspace-locked transaction as ledger rows. An adjusted transaction may
never be restored without the marker proving which action was already applied.

T212 CSV normalization also preserves full `Time`/`Time (UTC)` as
`executed_at` and the export `ID` as structured source identity. Update import
preview canonicalization and duplicate fingerprints to prefer source identity
and otherwise include full timestamp, not only date/quantity/price. This keeps
distinct identical same-day fills and gives CSV rows the same chronological
ordering guarantees as API rows. Because one CSV event may normalize into
multiple rows, durable identity is `export ID + deterministic leg`, for example
`fx_out`, `fx_in`, and `fee` for a currency conversion and explicit action/leg
labels for split pairs. One-to-many normalization must never collapse rows onto
the bare export ID.

### 4.5 Timestamp ordering

Adding `executed_at` alone is insufficient because current consumers order by
date and fixed transaction type.

Create one shared chronological sort key:

- use aware `executed_at` when present;
- otherwise use date plus the documented existing type-order fallback for
  date-only CSV/manual rows.

Migrate holdings/FIFO, realized P/L, cash timelines, performance, analytics,
assistant context, and split processing to the shared helper. Date-only CSV
behavior remains deterministic.

### 4.6 Durable corporate-action identity

Use one canonical API representation: normalized trade rows plus durable
corporate-action application records. Do not also persist position-changing
`split_open`/`split_close` API rows for the same action.

Add a tenant-scoped `BrokerCorporateAction` record keyed by upstream account,
provider instrument, action type, effective time, and provider event identity.
Add an idempotent application record linking that action to each affected
`Transaction.source_event_id`, including before/after shares and price and the
applying run/audit reference.

When a newly imported old trade predates an already applied split, finalization
applies every missing action in chronological order and records each
action/transaction application. When a new split arrives, finalization updates
eligible existing API trade rows once and records the applications. This state
survives staging cleanup and later syncs. Existing CSV split rows keep their
current representation and are not combined with API normalized-trade actions
without explicit reconciliation logic.

### 4.7 PostgreSQL requirements

Every new tenant table requires:

- composite workspace-parent foreign keys;
- forced RLS and workspace policy;
- explicit `portfyl_runtime` table grants;
- explicit sequence grants if an integer sequence is used;
- cascade/account-deletion coverage.

Migrations cannot rely on static table lists in `0002_tenant_rls.py` to cover
tables created later.

## 5. Synchronization Flow

### 5.1 Connect and credential rotation

1. Validate credentials without mutating ledger data.
2. Fetch the upstream account identity and store only its fingerprint.
3. Reject connection to a different account for an already connected
   portfolio; instruct the user to create a new portfolio.
4. Before mutating credentials, cancel/fence active runs and increment
   `credential_generation`, even for the same account.
5. Clear connection dead-letter state after validation.
6. Start a new snapshot/history run from durable completed coverage.

An incomplete run is never resumed under a new credential generation. Any
in-flight worker must verify account fingerprint and generation before commit.

This replaces the current destructive connect behavior that deletes portfolio
transactions before a sync succeeds.

### 5.2 Fast snapshot

Fetch `/equity/account/summary` and `/equity/positions` concurrently through
one `httpx.AsyncClient`. Each result independently preserves its previous
snapshot on failure.

Persist balance and positions atomically per snapshot type. Return snapshot
availability immediately and create or return the active history run. The
normal response is `202 Accepted` while history remains incomplete.

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

The foreground request may make one bounded history pass, but it has a strict
wall-clock deadline and never waits for a reset.

### 5.3 Pagination and rate limits

Orders, dividends, and cash transactions advance independently and may fetch
concurrently. After each response:

1. Stage unique events.
2. Store the complete returned `nextPagePath`.
3. Read `x-ratelimit-remaining` and `x-ratelimit-reset`.
4. Mark the stream complete when `nextPagePath` is null.
5. Mark only that stream waiting when its remaining count reaches zero.

Do not assume buckets are shared or independent. Obey each response. Convert a
`429` into persisted waiting state rather than a connection failure.

Before following `nextPagePath`, parse and validate it as a relative URL with
no scheme, host, user info, or fragment. Its path must equal the expected T212
history endpoint for that stream, and query keys must be from that endpoint's
documented pagination/filter set. Preserve the complete validated query string.
Never forward authorization headers to an absolute or unexpected origin/path.

### 5.4 Dedicated continuation job

Add a new minutely recurring job named `broker_backfill`. It is not an extension
of `autosync_tick()` and does not filter by `auto_sync` or user schedule. It only
claims already-created due runs.

Add it to:

- `RECURRING_JOB_NAMES` and subsystem health;
- the local edition poller;
- authenticated cloud internal-job routes;
- Cloud Scheduler deployment and operations runbook.

Auto-sync may create an incremental run when due. `broker_backfill` drains it.
This also guarantees that a manual initial import finishes after the browser
closes with `auto_sync=false`.

Every page commit or rollback clears transaction-local RLS context. Background
code must call `_set_job_workspace_context()` again before the next tenant
query. The job first enumerates active workspace IDs through the established
non-tenant path, then sets one workspace context before selecting/claiming its
due runs. It never scans `BrokerSyncRun` globally under forced RLS.

The foreground service receives the authenticated workspace/user context and
reasserts both transaction-local settings after every page commit or rollback
before touching tenant data again. Real PostgreSQL tests cover foreground and
background multi-page commits across multiple workspaces.

### 5.5 Atomic finalization and CSV serialization

Finalization begins only when all required streams are complete.

Before reading ledger state, acquire a PostgreSQL workspace row lock through a
new shared ledger-mutation helper. T212 CSV commit already follows this pattern;
CSV undo currently does not and must be changed to acquire the lock before its
availability/fingerprint check and hold it through restoration. After locking,
re-read:

- current transactions;
- T212 CSV coverage;
- import undo/current-state fingerprint;
- provider event identity and durable coverage.

Every route that mutates `Transaction` rows must use the helper, including CSV
commit/undo, individual create/update/delete, clear-all, cash mutations, and API
finalization. This prevents a manual or clear operation from interleaving with
finalization's duplicate/coverage read. Preview remains read-only and unlocked;
commit still rechecks its fingerprint after acquiring the lock.

Broker-managed `t212_api` and `t212_csv` rows are immutable through ordinary
single-row edit/delete routes in this phase; return `409` rather than silently
invalidating provider or CSV coverage. A future explicit suppression workflow
may create audited durable tombstones. `clear-all` remains an explicit
portfolio-wide action, but while holding the lock it cancels active runs,
clears all durable T212 history checkpoints/`history_complete_at`, and forces
the next sync to perform a full bootstrap. T212 CSV history is changed through
the previewed replacement workflow, which recomputes coverage and invalidates
incompatible API checkpoints. Manual non-broker rows remain editable under the
same lock.

Finalization then:

1. Parses all events with timestamp precision.
2. Imports every valid fill, even when its parent order later became partial or
   cancelled; a valid fill does not require final `order.status == FILLED`.
3. Maps exact trade settlement from `fill.walletImpact.netValue` and currency
   into `cash_amount`/`cash_currency`; verifies FX orientation with fixtures.
4. Preserves taxes, fees, and broker realized P/L as bounded reconciliation
   provenance without double-counting taxes already included in net settlement.
5. Stores dividend quantity and gross amount per share as `shares`/`price`, and
   provider paid `amount` plus account currency as
   `cash_amount`/`cash_currency`.
6. Removes the universal 15% withholding assumption.
7. Maps cash transaction events explicitly:
   `DEPOSIT -> deposit`, `WITHDRAW -> withdrawal`, `FEE -> fee`, and
   `INTEREST_ON_FREE_CASH`/`LENDING_INTEREST -> interest` with preserved source
   subtype. Amount direction is locked by provider fixtures and normalized to
   Portfyl's positive-magnitude plus type-direction convention.
8. Treats `TRANSFER` and every unknown type as unresolved until provider
   direction/source semantics are proven. The run becomes terminal
   `needs_review`, does not mark cash history complete, and does not silently
   classify the transfer as an external flow.
9. Applies CSV coverage and legacy cross-source duplicate rules.
10. Inserts ledger rows and durable stream checkpoints in one transaction.
11. Sets `last_synced_at` only after final commit.

If finalization fails, the existing ledger remains unchanged and staging can
retry. Current snapshot views remain available with incomplete-history status.

### 5.6 Gross versus received dividends

All received-income and cash consumers prefer `cash_amount` when present, with
`shares * price` only as legacy fallback. This includes summary, analytics,
assistant context, historical dividend totals, and cash ledger.

Forecast and DPS consumers may use gross per-share values. They must not
present gross forecast data as received net cash. Provider dividend type and
reference remain available for audit and tax/report decisions.

## 6. Split and Corporate-Action Handling

### 6.1 Snapshot behavior

T212 positions are authoritative for current open quantities and broker cost.
Current holdings can render before historical split normalization. No yfinance
call blocks the first view.

### 6.2 Historical normalization

Use provider evidence first:

- retain `fill.type` values such as `STOCK_SPLIT`, `STOCK_DISTRIBUTION`,
  `SPIN_OFF`, and acquisition/distribution events;
- treat only `TRADE` fills as user trading activity;
- do not infer a user trade from a provider-labelled corporate-action fill.

After all pages are staged:

1. Collect affected normalized tickers.
2. Fetch yfinance split history once per ticker through a shared lookup.
3. Cache positive and negative results with bounded TTL; negative cache is
   never permanent.
4. Collapse provider-labelled close/open evidence into one durable
   `BrokerCorporateAction`; do not persist those API fills as additional
   position-changing transaction rows.
5. For each provider-confirmed action, apply `shares *= ratio` and
   `price /= ratio` to each eligible pre-split T212-origin trade exactly once
   through its durable action/transaction application record. This includes
   API rows, `t212_csv` rows, and positively identified legacy T212 CSV rows.
   Preserve notional and exact broker cash settlement.
6. Match provider evidence across the complete staged set and relevant existing
   T212-origin rows, including page and rate-window boundaries.
7. Before applying a provider action, detect whether authoritative T212 CSV
   `split_open`/`split_close` rows already represent it. If they do, record the
   action as represented by those rows and do not normalize trades for the same
   action. One action has exactly one quantity-changing representation.
8. Only same-instrument `STOCK_SPLIT` receives the mechanical ratio transform.
   Distributions, spin-offs, acquisitions, symbol changes, and any action with
   cross-instrument/cash terms enter `needs_review` until an action-specific
   mapper exists.
9. A yfinance date may validate ratio/effective-date plausibility but cannot by
   itself create/apply an action or delete a trade. Yfinance-only evidence
   produces `needs_review`.
10. Preserve provider action type, date, terms, affected event IDs, and finalizer
   audit reference.

Provider-labelled actions are authoritative import transformations and may be
applied automatically with audit provenance. Inferred or ambiguous actions are
reported for a later review/confirmation workflow and keep reconciliation in a
needs-review state.

Raw staged events stay immutable. Atomic finalization plus durable
action/transaction application identities make retries, later overlap runs,
late pre-split fills, and staging cleanup idempotent.

### 6.3 Reconciliation

After finalization, compare ledger open quantities with `BrokerPosition` by raw
provider instrument and normalized ticker:

- `matched` within documented fractional-share tolerance;
- `different` with per-ticker broker and ledger values;
- `unavailable` if either side lacks data.

A mismatch creates no adjustment. It identifies likely causes such as
incomplete provider history, unsupported action, ticker mapping, or CSV/API
overlap.

## 7. Incremental Sync

After successful bootstrap, store separate completed coverage for orders,
dividends, and transactions.

Later syncs:

- refresh summary and positions independently;
- fetch the newest history page first;
- stage unknown provider IDs;
- verify page timestamps are monotonic in the observed direction;
- continue through a bounded time/page overlap beyond the last contiguous
  completed frontier;
- stop only after consecutive fully known pages cross that frontier and all
  ordering invariants still hold;
- never stop solely because one event is older than `max(Transaction.date)`;
- use a deeper/full fallback if ordering or coverage invariants fail.

This preserves older events for previously unseen tickers while making the
normal later sync one page plus bounded overlap.

T212 documents cursor pagination but does not guarantee immutable ordering or
forbid late historical corrections. Therefore incremental stopping is an
optimization, not the only integrity mechanism. For `auto_sync=true`
connections, run a complete provider-ID and payload-hash audit no more than 30
days after the previous audit. For `auto_sync=false`, the first manual sync
after that 30-day age becomes an audit; Portfyl does not create unrequested
recurring broker access. Also audit immediately after reconciliation mismatch
or ordering/checkpoint invariant failure in a user-requested/auto-sync workflow.
The audit uses the same rate-limit-aware resumable machinery and does not block
current snapshots. This gives eventual detection of old dividends, cash events,
and corrections that current-position reconciliation cannot reveal.

Audit creation respects user sync intent:

- a manual sync creates an `audit` run instead of a normal incremental run when
  `last_full_audit_at` is older than 30 days;
- the scheduled auto-sync pass does the same for `auto_sync=true` connections;
- `broker_backfill` drains created audit runs but does not create recurring work
  for connections whose auto-sync is disabled;
- reconciliation or ordering/checkpoint failure creates an immediate audit run
  within the workflow that detected it.

Audit staging compares provider identity plus deterministic canonical payload
hash and mapper/schema version. A changed payload under an existing ID is
staged as a revision and finalization updates the durable transaction/action
under the workspace ledger lock. ID equality alone is not proof that provider
data is unchanged.

## 8. API and Frontend Work

### 8.1 Backend

- Keep `POST /api/broker/trading212/sync`, but make it start/resume the workflow
  and return snapshot/history state.
- Extend `GET /api/broker/trading212/status` with independent snapshot status,
  history progress, resume time, and reconciliation.
- Do not expose raw cursors or staged payloads.
- Move synchronization into `backend/t212_sync.py`; jobs do not call FastAPI
  route handlers.
- Foreground and scheduler advancement share the same run lease/claim service.
  A global scheduler advisory lock does not replace per-run concurrency control.

### 8.2 Frontend

Create one shared `useT212Sync` state machine for connect, manual sync, active
run discovery, polling, retry, and final invalidation.

- Connect follows the returned run instead of immediately claiming success.
- Retire the existing `total_imported` synchronous success contract.
- Invalidate current holdings/allocation/summary/cash when snapshot becomes
  ready.
- Poll active work more slowly while waiting for a provider reset.
- Show fetching snapshot, importing history, waiting for T212, processing
  splits, reconciling, complete, and action-required failure.
- Keep snapshot-backed pages usable during history import.
- Invalidate all ledger analytics once on final completion.
- Dividend notification jobs use fresh snapshot positions with ledger fallback.
- Assistant context carries `history_complete` and qualifies or refuses
  history-wide claims while incomplete.

## 9. File Responsibility Map

- `backend/t212_sync.py` (new): provider client, response mapping, rate-limit
  parsing, snapshot fetch, run advancement, and finalization.
- `backend/models.py`: position, run, staging, connection state, durable
  corporate-action/application identity, and transaction provenance.
- `backend/alembic/versions/`: schema, constraints, grants, and forced RLS.
- `backend/routers/broker.py`: thin connect/status/sync/disconnect routes.
- `backend/transaction_ordering.py` (new): shared timestamp/date fallback key.
- `backend/routers/portfolio.py`, `backend/routers/analytics.py`,
  `backend/cash_ledger.py`: explicit snapshot versus ledger selection and
  chronological ordering.
- `backend/jobs.py`, `backend/routers/internal_jobs.py`, `backend/main.py`:
  dedicated local/cloud `broker_backfill` job.
- `backend/import_undo.py`, CSV commit/undo, transaction CRUD, and cash CRUD:
  shared ledger lock and new field preservation.
- `backend/workspace_export.py`, account deletion, retention, and compliance:
  snapshot/provenance export and staging lifecycle.
- `backend/routers/assistant.py` and dividend jobs: completeness-aware source.
- `frontend/src/api.js`, `Settings.jsx`, `Cash.jsx`, Dashboard/Allocation, and a
  shared progress component: stable envelopes and workflow UX.

## 10. Delivery Sequence

### Task 1: Lock contracts and provider mappings

- [ ] Add fixtures for summary, positions, multi-fill orders, corporate-action
      fills, dividends, and cash transactions.
- [ ] Lock current CSV/API overlap and unseen-ticker behavior with tests.
- [ ] Specify exact wallet FX orientation and dividend field mapping.
- [ ] Specify every `/history/transactions` type; unresolved `TRANSFER` or
      unknown types must enter `needs_review`, never silent classification.
- [x] Specify deterministic keyed account fingerprinting and the fail-closed
      legacy-connection migration.
- [ ] Document provider-labelled automatic transformations versus inferred
      actions requiring review.

### Task 2: Ship the fast snapshot

- [ ] Add `BrokerPosition`, expanded `BrokerBalance`, connection snapshot state,
      migration, grants, RLS, cascade, export, and tenant tests.
- [x] Persist portfolio-level account fingerprint binding and define disconnect
      cleanup without erasing ledger identity.
- [ ] Fetch summary and positions concurrently and replace snapshots atomically.
- [ ] Migrate holdings to the stable envelope and summary to explicit nullable
      history fields, exact units, conversion, and component-level sources.
- [ ] Update all callers and verify 25-hour stale/degraded behavior.

### Task 3: Add resumable history runs

- [x] Add run/staging models, one-active-run constraint, provider identity, and
      per-run lease.
- [x] Follow full next paths and commit each page with its progress.
- [x] Validate next paths as relative expected-origin endpoint paths before
      attaching authorization.
- [x] Parse rate-limit headers and convert `429` to waiting state.
- [x] Add minutely local/cloud `broker_backfill`, independent of auto-sync.
- [x] Reassert RLS context after every page commit/rollback.
- [x] Enumerate workspaces before background run claims; do not perform a global
      tenant-run scan under RLS.

### Task 4: Finalize exact split-aware history

- [ ] Add provider identity/time fields and migrate all chronological consumers.
- [x] Preserve T212 CSV timestamp/ID in normalization, preview canonicalization,
      deduplication, undo, and export.
- [x] Add deterministic per-leg identity for one-to-many CSV events.
- [ ] Import fills by `fill.id`, exact settlement, actual dividend amount, and
      cash transactions.
- [ ] Process splits once per ticker over the complete staged run.
- [ ] Add durable corporate-action and per-transaction application identities;
      use normalized API trades as the sole canonical split representation.
- [ ] Handle corporate-action pairs across pages and rate windows.
- [x] Share the workspace ledger lock with CSV commit/undo.
- [x] Preserve provenance through import undo and workspace export.
- [ ] Snapshot/restore corporate-action applications and broker coverage in
      import undo.
- [x] Finalize atomically and reconcile against current positions.

### Task 5: Make subsequent syncs incremental

- [ ] Persist per-stream completed coverage and overlap checkpoints.
- [ ] Stop on provider identity plus known complete coverage, not global date.
- [ ] Keep a safe deeper-walk fallback.
- [ ] Add a 30-day complete audit walk and immediate audit after reconciliation
      or ordering/checkpoint invariant failure.
- [ ] Create due audit runs from manual/auto-sync entry points and detect changed
      payload hashes under existing provider IDs.
- [x] Remove old full-history and duplicate yfinance request paths.

### Task 6: Complete workflow UX and operations

- [ ] Add shared progress/polling and historical-data availability states.
- [ ] Update connect, Settings, Cash, Dashboard, Allocation, assistant, and
      dividend notifications.
- [ ] Add job health, runbook, cloud schedule, and staging cleanup.
- [ ] Run fast backend, frontend local/cloud, both builds, and PostgreSQL/RLS
      suites.
- [ ] Verify against a disposable T212 demo account with enough history to cross
      a reset and at least one historical split.

## 11. Required Tests

At minimum:

- snapshot data appears while history remains incomplete;
- holdings always use the same envelope for broker, CSV, and manual portfolios;
- unavailable historical values remain `null`, not zero;
- fresh/degraded/stale source selection follows the 25-hour rule;
- stale snapshot plus incomplete history returns stale current evidence or
  unavailable, never incomplete-ledger current holdings;
- summary failure preserves positions and positions failure preserves summary;
- persisted summary cash components, stock cost/value, unrealized P/L, and net
  liquidation map to exact response fields and requested display currency;
- successful empty positions clear stale holdings;
- initial backfill resumes with `auto_sync=false` and no user schedule due;
- reset between pages resumes from the stored full path;
- absolute, cross-origin, wrong-endpoint, or unexpected-query next paths are
  rejected without forwarding authorization;
- `429` waits without dead-letter increments;
- duplicate clicks return one active run;
- foreground and scheduler workers cannot advance the same run concurrently;
- foreground commits reassert workspace/user RLS context, and background
  workers enumerate/set workspace context before claiming runs;
- credential rotation fences every old worker before commit;
- account fingerprint remains stable across credential rotation and distinct
  across live/demo accounts and upstream account IDs;
- a legacy connection with unverifiable old credentials fails closed without
  attaching new-account history;
- a different T212 account is rejected for the existing portfolio;
- disconnect retains portfolio account binding, removes snapshots/credentials,
  and rejects later reconnection to another account;
- crash around page/cursor commit remains idempotent;
- two identical fills with distinct IDs both survive;
- all fills of a partially filled/cancelled order survive;
- distinct identical same-day T212 CSV fills survive through source ID or full
  timestamp fingerprints;
- one T212 currency-conversion ID produces distinct stable `fx_out`, `fx_in`,
  and `fee` identities;
- paid dividend amount uses provider `amount`, not fixed tax estimation;
- received totals use net cash while forecasts retain gross per-share meaning;
- a split pair crossing page/reset boundaries is handled once;
- normalized trade rows and position-changing API split rows are never both
  persisted for one provider action;
- a T212 CSV split followed by the matching API action is represented once;
- an API split adjusts eligible T212 CSV trades when no CSV split rows already
  represent the action;
- spin-offs, distributions, and acquisitions remain `needs_review` until an
  action-specific mapper exists;
- durable action/application identity prevents reapplication after staging
  cleanup, later overlap, and late pre-split fills;
- yfinance-only evidence never deletes a trade;
- legitimate same-day round trips survive;
- timestamp-aware FIFO/cash ordering works while date-only fallback is stable;
- CSV replace/undo racing finalization serializes on the workspace lock;
- all transaction/cash CRUD shares the workspace lock, broker rows reject
  ordinary single-row mutation, and clear-all invalidates history coverage;
- undo restores provider IDs/timestamps and does not cause re-import;
- undo restores split application markers/checkpoints with adjusted rows so an
  action cannot be applied twice;
- older events for unseen tickers are not skipped;
- initial bootstrap does not use a per-ticker newest-date cutoff as coverage;
- monthly full audit detects an old late-inserted dividend/cash event beyond the
  ordinary incremental overlap;
- monthly audit detects corrected payload under an unchanged event ID;
- retained failed-run staging does not block staging the same IDs in a later
  audit run;
- `TRANSFER` and unknown cash event types produce `needs_review` and never
  silently affect external-flow/TWR classification;
- snapshot/ledger mismatch is reported without adjustment rows;
- every page commit reasserts RLS context before the next tenant query;
- Alice cannot inspect or advance Bob's snapshots, runs, or staging;
- local and cloud UI states work at mobile and desktop widths.

## 12. Definition of Done

- Current cash and positions appear after only summary/positions snapshot calls.
- History continues after browser close and Cloud Run restart.
- Provider reset windows pause and resume without false errors.
- Initial history finalizes atomically with provider identity, timestamp, exact
  settlement/dividend cash, and split-aware normalization.
- Current snapshot and historical ledger remain visibly distinct.
- Subsequent sync normally reads new pages plus bounded overlap.
- Connect/sync never deletes ledger history or fabricates reconciliation rows.
- Complete backend, PostgreSQL/RLS, frontend local/cloud, and build gates pass.

## 13. External References

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
- Snowball broker snapshot/history behavior:
  https://help.snowball-analytics.com/yodlee/
- Snowball T212 incremental CSV guidance:
  https://help.snowball-analytics.com/import-trading212/
