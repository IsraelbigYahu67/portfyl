# Portfyl Onboarding and Import Safety Design

## Status

Approved for implementation by the owner on 2026-09-07 as the next
independently executable P0 product slice. This design does not activate paid
checkout, trials, e-mail delivery, or another broker integration.

## Goal

Give a newly verified user a direct route to a useful workspace and make CSV
imports understandable and recoverable before Portfyl accepts money. A user
must be able to create a clearly labelled demo, start a blank portfolio for a
real import, inspect the exact effect of a CSV, avoid exact duplicates, and
undo the last committed import during a short grace window.

## Current-state problems

- A new workspace has no portfolio. The platform landing page sends the user
  to Settings even though portfolio-scoped broker and import actions cannot yet
  succeed.
- `POST /api/portfolio/import-csv` parses and writes in one request. The UI
  cannot show additions, duplicates, removals, or the resulting count before
  the mutation.
- Native CSV appends exact duplicates. Trading 212 always replaces the whole
  portfolio, but the consequence is only explained in prose.
- Imports have no batch or pre-import snapshot, so an accidental import cannot
  be restored.

## Onboarding experience

When the current workspace contains no portfolios, the authenticated shell
shows a focused onboarding screen instead of the old platform chooser. It
offers three truthful paths:

1. **Import a CSV** creates an empty `My portfolio`, selects it, selects the
   equities platform, and opens the import screen.
2. **Explore a demo** atomically creates one portfolio named `Portfyl demo`
   with a small, deterministic set of fictional/example transactions whose
   source is `demo`. The UI calls it sample data and tells the user it can be
   replaced or cleared.
3. **Connect a broker** creates an empty portfolio and opens Settings. Existing
   plan enforcement remains authoritative, so cloud Free may explain that live
   connections require a future paid plan rather than silently bypassing the
   restriction.

The demo endpoint is workspace-scoped, CSRF-protected, available in local and
cloud editions, and refuses to create a second demo in a non-empty workspace.
It observes the same portfolio, transaction, and active-position limits as
ordinary writes. Demo creation never starts a trial.

## Import protocol

### Preview

`POST /api/portfolio/import-csv/preview` accepts the CSV and the requested
append/replace mode. It parses and normalizes the file without mutating the
database, then returns:

- detected format and whether replacement is mandatory;
- source row, recognized row, validation-error, and informational-skip counts;
- exact duplicates inside the file and against the current portfolio;
- current, added, removed, unchanged, and projected transaction counts;
- a bounded sample of normalized rows and warnings;
- a deterministic `preview_id` tied to the normalized file, effective mode,
  active portfolio, and current transaction state.

An exact transaction identity uses the persisted business fields (date, type,
ticker, shares, price, amount, currencies, settlement cash, and notes),
with stable normalization for dates, nulls, and floats. Name and generated
public/internal identifiers and origin metadata do not define equality. Repeated rows inside a
file are retained once. In append mode, rows already present in the portfolio
are not inserted. In replacement mode, the unique normalized file is the
projected final state.

### Commit

`POST /api/portfolio/import-csv/commit` requires the same file, mode, and
`preview_id`. The backend reparses the upload and recomputes both the normalized
content and current-state fingerprint. If either changed after preview, it
returns `409` and requires a new preview. Parsing, quota checks, replacement,
insert, undo-snapshot creation, broker coverage update, and audit event happen
in one database transaction.

The former mutating `/import-csv` HTTP route is retired; an internal helper may
remain temporarily for focused legacy normalization tests, but the frontend
and OpenAPI use only preview/commit.

### Undo

Before commit, Portfyl serializes the current portfolio transactions and their
trade notes. After commit it records the resulting state fingerprint. The
compressed snapshot is stored in the existing workspace-scoped settings table
under an internal per-portfolio key, so no new global or unscoped storage and
no Alembic change are required. It contains no broker credentials or other
workspace data.

`GET /api/portfolio/import-csv/undo` reports whether the last import is
undoable. `POST` to the same path restores the prior transactions and notes
only when all of these remain true:

- the caller still owns access to the same workspace and portfolio;
- the snapshot is at most 24 hours old;
- the current transaction state exactly matches the post-import fingerprint;
- the snapshot has not already been consumed or replaced by a later import.

Any manual transaction edit or broker sync after import makes the snapshot
conflicted and prevents destructive restoration. Undo itself is atomic,
preserves prior transaction public IDs so note references can be rebuilt, and
deletes the snapshot after success. A lazy read removes expired snapshots.
Only the latest successful import per portfolio is retained. Workspace/account
deletion removes it through the existing workspace cascade; plan or trial
changes never do.

## Persistence and tenant isolation

The implementation deliberately adds no table while `models.py`,
`database.py`, and the current Alembic head are reserved by another session.
Undo data uses `WorkspaceSetting(workspace_id, key, value)`, which is already
covered by application predicates, forced RLS, workspace export filtering, and
workspace deletion. Keys use an internal `import_undo:` prefix and are excluded
from the machine-readable customer export because they are temporary duplicate
recovery state, not a separate customer record.

Every query includes both workspace and portfolio predicates. Public APIs use
portfolio UUIDs from the established request context; raw integer IDs are
never accepted or returned.

## Limits and failure behaviour

- CSV uploads are capped at 5 MiB before pandas parsing.
- Preview returns bounded row samples and bounded validation messages.
- Existing backend plan limits are checked against the projected final state,
  not the raw source-row count.
- Invalid or non-lossless Trading 212 files do not write data or overwrite the
  previous undo snapshot.
- An empty or duplicate-only append is a valid no-op preview; commit reports
  zero additions and does not replace a still-useful undo snapshot.
- Snapshot decoding failure fails closed with an unavailable/conflicted status;
  it never clears current transactions.

## Frontend behaviour

The Import page becomes a two-step review flow: select file, preview, then
explicitly commit. Replacement has a high-salience warning and shows removals;
append shows exact duplicates that will be skipped. After success the page
offers **Undo last import** with its expiry. Query caches and portfolio counts
are invalidated after commit or undo.

The frontend never computes authoritative duplicate, reconciliation, quota, or
undo decisions. It only renders backend results. All flows work in local and
cloud builds and raw import remains available on Free.

## Verification

- Unit tests for canonical identity, in-file/existing duplicate detection,
  replacement reconciliation, preview drift, quota projection, snapshot
  round-trip, note restoration, expiry, conflict, consumption, and tenant key
  scoping.
- Router tests proving preview is read-only and commit/undo require the
  established CSRF dependency.
- Onboarding tests for empty-workspace rendering, blank portfolio creation,
  atomic demo creation, non-empty refusal, and demo labels.
- Frontend tests for preview-before-commit, replacement warnings, duplicate
  copy, undo success/conflict states, and onboarding navigation.
- Full fast backend and frontend suites before every commit; PostgreSQL RLS
  coverage before marking the master-plan items complete.

## Non-goals

- General-purpose import history beyond the single 24-hour recovery point.
- Fuzzy broker matching, corporate-action repair, or automatic cash balancing.
- A new broker connector, paid-plan activation, trial clock, or lifecycle
  e-mail.
- Persisting demo flags or onboarding progress in a new schema.
