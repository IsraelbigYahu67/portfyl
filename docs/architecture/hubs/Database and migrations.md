---
type: hub
layer: db
tags: [arch/hub]
generated: false
---
# Database and migrations

Portfyl stores its data in PostgreSQL (Neon in production, a Docker container in local development). The schema is managed only by Alembic migrations in `backend/alembic/versions/`. There is no SQLite runtime path any more; the only exception is the in-memory SQLite fixture used by the fast unit tests under `PORTFYL_TESTING=1`. Every tenant table has forced row-level security (RLS) as a second line of defense behind the application checks.

## How it works
- Migrations run explicitly, never at web startup. On startup [[main]] only calls `assert_alembic_head` in [[database]], which compares the database's `alembic_version` with the constant `EXPECTED_ALEMBIC_HEAD` and fails closed on a mismatch. The app never runs `CREATE TABLE` or `ALTER TABLE` itself.
- Rule: every change under `backend/alembic/versions/` must update `EXPECTED_ALEMBIC_HEAD` in [[database]] to the exact current `alembic heads` revision in the same change. Alembic must have exactly one head. Today that head is `0028_password_changed_seen` ([[0028_password_changed_seen]]).
- Run `alembic upgrade head` (config: [[backend.alembic (ini)]]) with the migration-owner credential, never the restricted runtime credential. In Cloud Run use the migration job [[deploy.run-migrations (ps1)]] before every service deploy.
- Migrations must be forward-compatible, because several Cloud Run instances run old code while a migration is applied. Use expand then contract: add the new column or table first, move the data, and drop the old thing in a later, separate wave. Example pair: [[0004_broker_secrets_expand]] then [[0006_broker_secrets_contract]]; and [[0005_discord_webhook_expand]] then [[0007_discord_webhook_contract]].
- RLS is set per transaction through `set_config('portfyl.user_id' ...)` and `portfyl.workspace_id`; [[database]] re-applies it after each commit. Policies were created in [[0002_tenant_rls]]. See [[Tenancy and RLS]].
- The runtime role is a non-superuser without `BYPASSRLS`, which the restore drill checks (see [[deploy.validate-restore (py)]]).
- Local dev database: [[deploy.docker-compose.postgres-dev (yml)]]. Test database for the PostgreSQL suite: [[deploy.docker-compose.postgres-test (yml)]].

## Key code
- [[database]]: settings, engine, RLS context, head check.
- [[models]]: SQLAlchemy models for every table below.
- [[0001_multiuser_schema]]: the first migration (users, workspaces, memberships and the tenant tables).
- [[0002_tenant_rls]]: forced row-level security policies.
- [[0009_audit_log]]: audit trail table.
- [[0010_billing_entitlements]] and [[0025_stripe_billing]]: plans and Stripe state.
- [[0027_free_trial]]: trial tables and HMAC guard tables.
- [[migrations.sqlite_to_postgres]]: one-off import of the owner's old SQLite data.
- [[migrations.encrypt_existing_secrets]]: one-off encryption of stored secrets.

## Data
- Migration chain, in order: [[0001_multiuser_schema]], [[0002_tenant_rls]], [[0003_job_workspace_enumeration]], [[0004_broker_secrets_expand]], [[0005_discord_webhook_expand]], [[0006_broker_secrets_contract]], [[0007_discord_webhook_contract]], [[0008_broker_failure_tracking]], [[0009_audit_log]], [[0010_billing_entitlements]], [[0011_remove_payment_runtime]], [[0012_rate_limit_buckets]], [[0013_private_beta_invites]], [[0014_broker_positions]], [[0015_broker_sync_runs]], [[0016_transaction_provenance]], [[0017_position_snapshot_time]], [[0018_t212_account_binding]], [[0019_sync_run_review_details]], [[0020_broker_corporate_actions]], [[0021_t212_history_coverage]], [[0022_t212_cash_stream]], [[0023_allocation_targets]], [[0024_remove_ai_assistant]], [[0025_stripe_billing]], [[0026_broker_requests]], [[0027_free_trial]], [[0028_password_changed_seen]].
- Identity and tenancy: [[users (table)]], [[workspaces (table)]], [[memberships (table)]], [[auth_sessions (table)]], [[workspace_settings (table)]], [[user_settings (table)]].
- Portfolio data: [[portfolios (table)]], [[transactions (table)]], [[allocation_targets (table)]], [[trade_notes (table)]], [[watchlists (table)]], [[watchlist_items (table)]], [[benchmarks (table)]], [[benchmark_components (table)]], [[cash_interest_rates (table)]], [[options_trades (table)]], [[polymarket_positions (table)]].
- Brokers: [[broker_connections (table)]], [[broker_positions (table)]], [[broker_balances (table)]], [[broker_sync_runs (table)]], [[broker_sync_events (table)]], [[broker_corporate_actions (table)]], [[broker_corporate_action_applications (table)]], [[broker_requests (table)]].
- Billing and trial: [[subscriptions (table)]], [[billing_customers (table)]], [[stripe_events (table)]], [[usage_counters (table)]], [[usage_reservations (table)]], [[trial_grants (table)]], [[trial_identities (table)]], [[trial_ip_marks (table)]], [[trial_broker_marks (table)]].
- Alerts and notifications: [[price_alerts (table)]], [[discord_webhooks (table)]], [[dividend_notifications (table)]], [[notification_outbox (table)]].
- Operations and security: [[job_runs (table)]], [[audit_logs (table)]], [[rate_limit_buckets (table)]], [[beta_invites (table)]], [[data_migration_runs (table)]].

## Related hubs
- [[Portfyl]], [[Backend]], [[Tenancy and RLS]], [[Deploy and operations]], [[Testing]], [[Billing and Stripe]], [[Free trial]], [[Broker importers and sync]]

## Docs
- [[operations/sqlite-to-neon-migration]]: one-off import of the owner's data into Neon.
- [[operations/neon-backup-restore]]: point-in-time restore drill on a Neon branch.
- [[security/tenant-isolation-matrix]]: what RLS and app checks must guarantee.
- [[finished]]: the finished B/C/D workstreams that built this foundation.
