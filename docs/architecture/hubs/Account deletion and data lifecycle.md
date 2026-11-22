---
type: hub
layer: cross
tags: [arch/hub]
generated: false
---
# Account deletion and data lifecycle

This area decides how long data lives and how a person can take it with them or erase it. A user can export their whole workspace as JSON, undo the latest CSV import for 24 hours, and delete their workspace immediately. Operational records (old sessions, outbox rows and so on) are cleaned by a daily job with fixed retention periods. Since 2026-11-18 deletion is instant: there is no grace period and no undo.

## How it works
- **Export.** `GET /api/account/export` in [[routers.account]] calls [[workspace_export]], which builds a versioned, allow-listed JSON file of the workspace (portfolios, transactions, watchlists, notes, alerts and so on). It never includes secrets such as broker keys.
- **Delete now.** `POST /api/account/deletion` checks a fresh Firebase re-authentication, then [[account_deletion]] `delete_workspace_now` validates the guards and erases the data in the same request.
  - The caller must be the workspace owner, the only active member, and must type the exact workspace name.
  - The re-authentication must be at most 5 minutes old and match the signed-in user.
  - A renewing paid subscription blocks deletion; it must be cancelled in the Customer Portal first (see [[Billing and Stripe]]).
  - If it was the user's last workspace, the user row and the Firebase identity go too, the session cookie is cleared, and a best-effort `account_deleted` e-mail is sent after the commit (see [[Emails]]). A Firebase failure rolls everything back so the user can retry.
  - No audit row is written, because audit rows belong to the workspace and user being deleted.
- **UI.** [[components.DataPrivacySettings]] (in [[pages.Settings]]) shows the export button and the delete flow, with the typed name, re-login and a 10 second countdown.
- **Legacy requests.** Requests scheduled under the old 30-day rule are still finished by `purge_due_workspace_deletions`, run by the daily `account_deletion_cleanup` job ([[jobs]], [[routers.internal_jobs]]) and also available as the command [[purge_account_deletions]]. `DELETE /api/account/deletion` cancels such a request. Nothing creates new ones.
- **Retention.** The same daily job calls [[data_retention]] `cleanup_retained_operational_data`: invalid sessions after 30 days, usage reservations and notification outbox rows after 90 days, dividend notifications after 400 days, sync staging after 14 days (review details 90 days), at most 10,000 rows per category per run. It also purges trial guard records (see [[Free trial]]).
- **Demo cleanup.** [[demo_cleanup]] removes the onboarding sample portfolio once a real broker account is connected, unless the user added their own data to it.
- **Import undo.** [[import_undo]] saves a workspace-scoped, single-use snapshot of the portfolio before each CSV import and restores it within `UNDO_WINDOW` (24 hours). See [[Onboarding and CSV import]].

## Key code
- [[account_deletion]]: guards, `delete_workspace_now`, legacy purge state machine
- [[routers.account]]: export and deletion endpoints
- [[workspace_export]]: export builder (schema version 8 at time of writing)
- [[purge_account_deletions]]: command for due legacy deletions
- [[data_retention]]: bounded operational cleanup
- [[demo_cleanup]]: sample-data removal
- [[import_undo]]: 24-hour undo snapshots
- [[firebase_identity]]: `delete_user` for the identity side
- [[components.DataPrivacySettings]]: export and delete UI
- [[jobs]]: `account_deletion_cleanup_pass`

## Data
- [[workspaces (table)]], [[users (table)]], [[memberships (table)]]
- [[workspace_settings (table)]]: holds the import undo snapshots and legacy deletion state
- [[notification_outbox (table)]], [[auth_sessions (table)]]: swept by retention

## Related hubs
- [[Auth and sessions]]
- [[Tenancy and RLS]]
- [[Jobs and Cloud Scheduler]]
- [[Emails]]
- [[Onboarding and CSV import]]
- [[Billing and Stripe]]
- [[Backend]]
- [[Portfyl]]

## Docs
- [[superpowers/specs/2026-09-07-portfyl-data-export-account-deletion-design]]: original export and deletion design (the 30-day rule is superseded)
- [[superpowers/specs/2026-09-07-portfyl-onboarding-import-safety-design]]: preview and undo for imports
- [[compliance/private-test-retention-policy]]: the retention periods
- [[compliance/data-processing-inventory]]: what data is held where
- [[operations/neon-backup-restore]]: backups, which outlive deletion for a while
- [[legal/privacy-policy-en]]: what users are told
