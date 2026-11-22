---
type: hub
layer: backend
tags: [arch/hub]
generated: false
---
# Broker importers and sync

This area gets an investor's trades, dividends and cash into Portfyl's transaction ledger. There are two paths. A user can upload a broker export file (CSV, XML or XLSX), or connect a broker API so Portfyl syncs by itself. Both paths end in the same [[transactions (table)]] rows, and both avoid duplicates so a file and a daily sync can run side by side.

Supported today: Trading 212 (CSV and API), Interactive Brokers (Flex XML upload and Flex sync), eToro (API), Degiro (two CSV files) and XTB (XLSX). The US-only brokers Charles Schwab and Fidelity were removed on 2026-11-15 and now sit in the "not supported" list until real exports can be verified (git history has their importers). All broker test fixtures are still synthetic.

## How it works
- **File importers are plugins.** Each broker file format is one module in `backend/importers/formats/` that exposes a `FORMAT` object (a detector plus a parser, defined by [[importers.base]]). [[importers.registry]] finds them with `pkgutil`, so adding a broker does not touch a shared file. Modules starting with `_` are shared helpers, not formats. If a file matches two formats the registry raises an "ambiguous" error.
- **Formats today**: [[importers.formats.ibkr_flex]] (IBKR Activity Flex XML), [[importers.formats.degiro_transactions]] and [[importers.formats.degiro_account]] (sharing [[importers.formats._degiro_common]]) and [[importers.formats.xtb]] (XTB xStation 5 XLSX).
- **Shared helpers**: [[importers.numbers]] (locale-aware numbers), [[importers.ids]] (stable event ids when a file has no transaction id), [[importers.dividends]] (merge the gross dividend and the withholding tax into one net row), [[importers.instruments]] with [[importers.openfigi]] (ISIN and venue to a Yahoo ticker; an unresolved instrument is a preview error, never an ISIN used as a ticker), and [[currency_codes]].
- **Preview then commit.** `POST /api/portfolio/import-csv/preview` and `/commit` in [[routers.portfolio]] try the plugin registry first, then the native and Trading 212 CSV path. The preview compares the file to the portfolio ([[import_workflow]]) and returns a `preview_id`; commit refuses if the file or portfolio changed since. The user-facing flow is described in [[Onboarding and CSV import]].
- **Append, except Trading 212 CSV.** Plugin imports append. Only the Trading 212 CSV forces a full replace (it is the complete history), and it records how far the CSV reaches so the API sync can continue after it.
- **Dedupe.** A row with a provider event id is identified by `(source, source_event_stream, source_event_id)`, backed by a partial unique index added in [[0016_transaction_provenance]]. Rows without one fall back to a content match on date, type, ticker, amounts and notes. `Transaction.source` is one of `t212_csv`, `t212_api`, `ibkr`, `etoro`, `degiro`, `xtb` or `demo`; a file upload and an API sync of the same broker share a source, see [[broker_sources]].
- **API syncs write through** `insert_new_provider_rows` in [[ledger_import]]. It holds the workspace ledger lock, skips events already known, refuses to mix a second source into tickers another broker already holds (status "needs_review"), and never commits (the caller does).
- **IBKR Flex**: [[routers.ibkr]] connects with a Flex token and query, and [[ibkr_ledger]] writes the statement events using the same parser as the XML upload, so older yearly statements and the daily sync do not clash.
- **eToro**: [[routers.etoro]] uses the user's personal read-only key. [[etoro_client]] spaces its calls to respect the rate limit and [[etoro_mapper]] turns positions and history into ledger rows. Only plain long stock, ETF and crypto positions are imported; CFDs, shorts and copy trading are counted, not imported.
- **Trading 212**: [[routers.broker]] handles connect, status, positions, sync and history retry. The sync is "snapshot first": [[t212_sync]] makes current positions and account value available quickly, while the slower full history runs as a resumable backfill ([[broker_sync_runs (table)]], advanced by the broker backfill pass in [[jobs]]). [[t212_cash]] maps cash events, [[t212_corporate_actions]] normalizes splits, [[t212_incremental]] decides when an incremental history walk can stop, and [[broker_reconciliation]] compares ledger quantities with the broker snapshot (it reports a gap and never invents a trade).
- **Auto-sync**: connections with `auto_sync` on are synced by the autosync job for Trading 212, IBKR and eToro, on the schedule from [[routers.settings]] (see [[Alerts and integrations]] and [[Jobs and Cloud Scheduler]]). Connecting or syncing a broker needs the `broker_sync` capability (Investor plan or higher, see [[Billing and Stripe]]).
- **Cash**: [[broker_cash]] provides current broker cash snapshots used by the dashboard and allocation views.
- **Demo cleanup**: connecting a real Trading 212 account removes the onboarding sample data ([[demo_cleanup]]).
- **Frontend**: [[pages.Import]] (upload, preview, undo), [[components.import (folder)]] (broker guides), [[lib.onboardingBrokers]] (supported and unsupported lists), [[hooks.useT212Sync]], [[components.BrokerPositionSnapshot]] and [[components.SyncScheduleSettings]].

## Key code
- [[importers.registry]]: discovers and detects plugin formats.
- [[importers.base]]: the contract a format module must meet.
- [[importers.formats.ibkr_flex]]: IBKR Flex XML parser.
- [[importers.formats.xtb]]: XTB XLSX parser.
- [[importers.formats.degiro_transactions]]: Degiro trades CSV.
- [[importers.formats.degiro_account]]: Degiro account (dividends, fees, FX) CSV.
- [[ledger_import]]: idempotent insert for API sync rows.
- [[ibkr_ledger]]: IBKR Flex statement to ledger.
- [[etoro_client]] and [[etoro_mapper]]: eToro API and mapping.
- [[t212_sync]]: Trading 212 snapshot-first sync.
- [[t212_cash]]: Trading 212 cash event mapping.
- [[t212_corporate_actions]]: Trading 212 split handling.
- [[broker_reconciliation]]: ledger versus broker position check.
- [[broker_sources]]: which broker a portfolio's data belongs to.
- [[routers.broker]]: Trading 212 endpoints.
- [[routers.ibkr]]: IBKR endpoints.
- [[routers.etoro]]: eToro endpoints.

## Data
- [[transactions (table)]]: the ledger every import writes to.
- [[broker_connections (table)]]: one connection per portfolio and broker (secrets are encrypted).
- [[broker_sync_runs (table)]] and [[broker_sync_events (table)]]: resumable history backfill and its staged events.
- [[broker_positions (table)]] and [[broker_balances (table)]]: latest broker position and cash snapshots.
- [[broker_corporate_actions (table)]] and [[broker_corporate_action_applications (table)]]: recorded corporate actions.
- Migrations: [[0014_broker_positions]], [[0015_broker_sync_runs]], [[0016_transaction_provenance]], [[0020_broker_corporate_actions]], [[0022_t212_cash_stream]].

## Related hubs
- [[Onboarding and CSV import]]
- [[Portfolio analytics]]
- [[Free trial]]
- [[Secrets and security]]
- [[Jobs and Cloud Scheduler]]
- [[Billing and Stripe]]

## Docs
- [[superpowers/plans/2026-10-16-portfyl-broker-integrations]]: plan for the plugin importers and API syncs.
- [[research/2026-10-16-broker-integrations]]: research on broker export formats and APIs.
- [[superpowers/plans/2026-09-20-t212-snapshot-first-sync]]: snapshot-first Trading 212 sync.
- [[superpowers/plans/2026-09-24-t212-corporate-actions-incremental-sync]]: corporate actions and incremental sync.
- [[research/t212-cash-transaction-encoding]]: signed-off Trading 212 cash encoding.
- [[research/t212-corporate-action-encoding]]: signed-off Trading 212 corporate action encoding.
- [[operations/2026-09-21-t212-snapshot-first-sync-session]]: session record for the first sync work.
- [[superpowers/specs/2026-07-13-broker-sync-schedule-design]]: auto-sync schedule design.
