---
type: hub
layer: cross
tags: [arch/hub]
generated: false
---
# Onboarding and CSV import

A new workspace has no portfolio, so the app cannot show a dashboard yet. Instead the frontend shows a first-run onboarding screen with three choices: connect a broker, try a demo portfolio, or import a file. The CSV import is built to be safe for a beginner: every import shows a preview first, duplicates are skipped, and the last import can be undone for 24 hours.

The same preview, commit and undo steps are used by onboarding and by the normal Import page.

## How it works
- **When onboarding shows.** In [[src.App]], if the workspace has no active portfolio, [[pages.Onboarding]] is rendered instead of the app. A failed portfolio load is treated as an error, not as "empty", so it never reaches onboarding. A separate preview route ([[pages.OnboardingPreview]]) replays the flow locally without creating anything.
- **Choice 1, demo.** `POST /api/portfolios/demo` in [[routers.portfolios]] creates one fixed, removable sample portfolio (transactions with source `demo`). It only works in an empty workspace and respects plan limits.
- **Choice 2, import.** `POST /api/portfolios/pending-import` creates an empty portfolio and marks it as pending. [[portfolio_activation]] keeps this marker in the workspace settings. The user is sent to the focused [[pages.Import]] page. A successful CSV commit clears the marker and audits `onboarding.portfolio.activated`. An empty pending portfolio can also be activated as a blank portfolio with `POST /api/portfolios/{id}/activate`.
- **Choice 3, broker.** A connect step ([[components.onboarding (folder)]], [[hooks.useOnboardingConnect]], [[lib.onboardingConnect]]) lets the user paste API credentials. The brokers and their order per language are in [[lib.onboardingBrokers]]; Charles Schwab and Fidelity are in its unsupported list. After a real Trading 212 account is connected, [[demo_cleanup]] removes the sample data.
- **"Notify me" for other brokers.** If the broker has no importer, the user can leave its name. `POST /api/broker-requests` in [[routers.broker_requests]] stores it as plain text (trimmed, at most 60 characters, at most 20 per workspace) in [[broker_requests (table)]].
- **Preview before commit.** `POST /api/portfolio/import-csv/preview` in [[routers.portfolio]] parses the file and returns counts (added, duplicates in file, duplicates already present, removed) and a short sample, without changing data. [[import_workflow]] does the comparison and builds a `preview_id` that fingerprints the file, the mode and the current portfolio.
- **Commit.** `/import-csv/commit` recomputes the preview and returns 409 if the `preview_id` no longer matches ("Preview again"). It takes the workspace ledger lock ([[ledger_mutation]]), checks plan capacity, writes the rows, saves an undo snapshot, audits `portfolio.import.committed` and runs the free-trial broker check (see [[Free trial]]). Any error rolls the whole import back.
- **Append or replace.** Plugin formats and the native CSV append. The Trading 212 CSV forces replace mode (it is the full history). The importers themselves are covered in [[Broker importers and sync]].
- **24-hour undo.** [[import_undo]] saves the portfolio state before and after an import as a compressed snapshot in the workspace settings, valid for 24 hours. `POST /api/portfolio/import-csv/undo` restores the "before" state, but only if the portfolio has not changed since the import (otherwise 409), and returns 410 after the window. Undo is audited as `portfolio.import.undone`.
- **Frontend pieces.** [[pages.Import]] (dropzone, preview table, undo), [[components.import (folder)]] (per-broker how-to guides with images, see [[lib.brokerGuideImages]]), [[lib.gettingStarted]] and [[components.dashboard (folder)]] (welcome panel and demo-data banner). The public landing page is [[pages.Welcome]], which leads to registration.
- **Sample data for the landing page.** The landing page mini demos ([[components.landing (folder)]]) use a separate client-side sample portfolio in [[demo (folder)]], not the backend demo.

## Key code
- [[pages.Onboarding]]: the first-run choice screen.
- [[components.onboarding (folder)]]: onboarding view and broker connect step.
- [[pages.Import]]: upload, preview, commit and undo UI.
- [[routers.portfolio]]: preview, commit and undo endpoints.
- [[routers.portfolios]]: demo, pending-import and activate endpoints.
- [[import_workflow]]: preview comparison and fingerprints.
- [[import_undo]]: 24-hour recovery snapshot.
- [[portfolio_activation]]: pending portfolio marker.
- [[demo_cleanup]]: removes sample data after a real connection.
- [[routers.broker_requests]]: "notify me" requests.
- [[ledger_mutation]]: workspace ledger lock.
- [[lib.onboardingBrokers]]: supported and unsupported broker lists.
- [[pages.Welcome]]: public landing page.

## Data
- [[portfolios (table)]]: the portfolio created by each choice.
- [[transactions (table)]]: rows written by the import (source `demo` for the sample).
- [[workspace_settings (table)]]: holds the pending marker and the undo snapshot.
- [[broker_requests (table)]]: "notify me" names.
- [[audit_logs (table)]]: records demo, activation, import and undo events.
- Migration [[0026_broker_requests]].

## Related hubs
- [[Broker importers and sync]]
- [[Portfolio analytics]]
- [[Free trial]]
- [[Auth and sessions]]
- [[Frontend structure]]
- [[Tenancy and RLS]]

## Docs
- [[superpowers/specs/2026-09-07-portfyl-onboarding-import-safety-design]]: design of preview, duplicate handling and undo.
- [[superpowers/specs/2026-11-14-onboarding-broker-connect-design]]: connecting a broker inside onboarding.
- [[operations/onboarding-funnel]]: how the onboarding funnel is measured.
- [[superpowers/specs/2026-09-19-portfyl-public-demo-activation-readability-design]]: public demo and activation.
- [[superpowers/plans/2026-10-16-portfyl-broker-integrations]]: preview, commit and undo for broker files.
