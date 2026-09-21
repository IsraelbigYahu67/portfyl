# T212 snapshot-first sync — session handoff (2026-09-21)

Session implementing
`docs/superpowers/plans/2026-09-20-t212-snapshot-first-sync.md`. That plan
file carries the authoritative, up-to-date per-task status note (top of the
file) — this document is the narrative handoff: what shipped, what's
verified and how, and what's explicitly still open, including one real
blocker.

## What shipped this session

**Task 1 (contracts)** — `backend/tests/fixtures/t212.py`: fixture builders
for `/equity/account/summary` and `/equity/positions`, scoped to what Task 2
actually consumes.

**Task 2 (fast snapshot)** — `backend/t212_sync.py` (new module), the
`BrokerPosition` model, migration `0014_broker_positions` (forced RLS,
grants, cascade, workspace export). `POST /trading212/sync` now fetches
account summary and positions concurrently; new `GET /trading212/positions`
read endpoint; 25-hour snapshot freshness rule.

**Task 3 (resumable history runs, scoped)** — `BrokerSyncRun` /
`BrokerSyncEvent` models, migration `0015_broker_sync_runs` (forced RLS,
grants, cascade, partial-unique-index one-active-run-per-connection
backstop). `BrokerConnection.credential_generation` fencing. New minutely
`broker_backfill` job (`jobs.py`, `RECURRING_JOB_NAMES`, local poller,
`/internal/jobs/broker_backfill`, `/health`, `deploy/cloudrun.md`).
`sync_transactions` starts/returns the active run; new
`GET /trading212/history-status` read endpoint.

**Task 4 (finalize into ledger, scoped slice)** — `Transaction` provenance
columns + migration `0016_transaction_provenance`;
`backend/transaction_ordering.py` (shared chronological sort key, built and
tested standalone); `t212_sync.finalize_run` (exact settlement via
`fill.walletImpact.netValue` when present, actual paid dividend amount
instead of the legacy 15%-withholding guess).
**`finalize_run` is not called from anywhere in the app.** It's a
standalone, directly-tested function. The existing full fetch-and-import
path in `routers.broker.sync_transactions` remains the only thing writing to
the ledger in production.

**Task 6 (frontend, one slice)** — `frontend/src/api.js`:
`fetchT212Positions`, `fetchT212HistoryStatus`. `Settings.jsx`: new
`HistoryBackfillStatus` component in the Trading 212 connections card,
polling history-backfill progress every 5s while active.

## What's verified, and how

- Backend fast suite (SQLite, `PORTFYL_TESTING=1`): **811 passed**.
- Backend PostgreSQL/RLS suite (disposable `postgres:16` via
  `deploy/docker-compose.postgres-test.yml`, real forced-RLS
  `portfyl_runtime` role): **344 passed**. This suite caught and let us fix
  a real bug (`broker_backfill_pass` missing its initial RLS context
  assertion before the due-run query — would have silently processed zero
  runs in production). It also proves `advance_run`'s per-page commits
  survive real transaction boundaries under forced RLS, and that the
  partial unique index genuinely rejects a concurrent duplicate run at the
  database level.
- Migrations `0014`→`0016` apply and downgrade cleanly against real
  PostgreSQL (tested manually with `alembic upgrade head` /
  `alembic downgrade -1` round trips, independent of the test suite's own
  schema lifecycle).
- Frontend suite (Vitest): **670 passed, 1 pre-existing skip**. One
  `src/demo/DemoApp.test.jsx` failure appeared in a single full-suite run;
  it passes standalone and on a full-suite re-run, is unrelated code this
  session never touched, and is a pre-existing flake, not a regression.
- `npm run build` (local edition): succeeds.

## What's explicitly NOT done

Per-task deferrals are documented in the plan file's status note and in
`backend/t212_sync.py`'s own section docstrings (search "scoped slice" /
"deliberately"). Summary:

- The stable `/portfolio/holdings` / `/portfolio/summary` response envelope
  and "migrate all callers" (plan §2.3) — large, separately-reviewable,
  touches most of the frontend.
- The `/equity/history/transactions` cash-movement stream (deposits,
  withdrawals, fees, interest) — never fetched.
- The full HMAC account-fingerprint system (plan §4.1/§5.1) — run fencing
  uses `credential_generation` alone; "a different T212 account connected
  into this portfolio" is not detected.
- `mode="audit"` runs — schema accepts the value, nothing creates one.
- Split/corporate-action detection and mechanical share/price adjustment
  (plan §6) — a fill whose `fill.type` isn't `"TRADE"` is left staged, never
  finalized.
- The `t212_csv_covered_through` / per-ticker-latest-date history cutoff the
  legacy sync path uses to stop a replace-imported CSV export's history from
  being resurrected — `finalize_run` doesn't implement this yet.
- The shared workspace ledger lock (plan §5.5) across CSV commit/undo, cash
  CRUD, and `finalize_run`.
- Import-undo / workspace-export provenance preservation for the new
  provenance fields.
- Wiring `finalize_run` into `broker_backfill` or any other automatic
  trigger — deliberate, pending the split-handling item above (wiring it in
  today would regress split-heavy portfolios relative to the legacy path,
  which already does split adjustment).
- Task 5 (incremental sync + 30-day audits) and Task 6's remainder (the
  rest of `useT212Sync`, Cash/Dashboard/Allocation wiring, assistant
  `history_complete` awareness) are not started.

## Open blocker: no real-browser verification of the Settings UI change

CLAUDE.md's UI-verification convention (start the dev servers, log in,
screenshot/inspect) could not be completed this session: `backend/auth.py`'s
`/auth/session` endpoint requires `identity.email_verified` from the
**Firebase-verified token itself** (`routers/auth.py:181`), checked via the
Firebase Admin SDK before any Portfyl session is issued — there is no
backend-side or local-edition bypass. This session has no Firebase test
account and no email inbox to complete a verification-link flow, so the new
`HistoryBackfillStatus` component in `Settings.jsx` is verified only by
Vitest component tests against mocked API responses (all four run states:
none, in-progress, completed, error-while-retrying) plus a clean production
build — not by an actual browser render.

**Next session with a real Firebase test account (or a human driving the
login step) should**: start `start.bat`, connect/sync a real or demo T212
account, and visually confirm the history-backfill panel in
Settings → Connections renders and polls correctly at at least one
viewport, per the existing browser-check docs' format (e.g.
`docs/operations/activation-analytics-browser-check.md`).

## Suggested next steps, in order of value/risk

1. **Continue Task 6** (frontend) — lower risk, makes existing backend work
   visible. `useT212Sync` state machine, wiring `GET /trading212/positions`
   into a "fast snapshot" surface (without touching the deferred
   `/portfolio/holdings` envelope).
2. **Shared workspace ledger lock** — moderate risk, touches several
   existing files outside T212 code (CSV commit/undo, cash CRUD,
   `portfolio.py`'s transaction CRUD) but is mostly mechanical, not
   financial-math risk. Prerequisite the plan calls out before split work.
3. **Split/corporate-action handling** — highest risk in the whole plan
   (mechanically rewrites share counts/prices for real financial data).
   Needs `BrokerCorporateAction` + application-record models, yfinance
   integration, and a `needs_review` UX path for anything not a clean
   same-instrument `STOCK_SPLIT`.
