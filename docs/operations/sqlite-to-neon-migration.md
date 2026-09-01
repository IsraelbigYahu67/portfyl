# SQLite-to-Neon owner migration

This runbook migrates one stopped Portfyl SQLite database into an empty,
already-migrated PostgreSQL/Neon database. The command is operator-only and
never runs during application startup.

## Safety requirements

- Use a copy of `portfyl.db`; never point the importer at the live file.
- The target must be at Alembic head `0002_tenant_rls` and contain no users or
  tenant workspaces. System benchmark presets are expected.
- Use the migration-owner connection URL. It must be a schema owner/admin role
  with `BYPASSRLS`; never use Portfyl's pooled runtime URL.
- Keep the URL in a secret variable and never paste it into logs, tickets, or
  the saved validation report.
- Stop the legacy application before taking the final production copy so no
  writes occur after the snapshot.

The importer fingerprints the source before opening its target transaction,
preserves integer IDs and relationships, generates public UUIDs, classifies
settings, resets identity sequences, and commits only after row-count, foreign
key, and transaction-control reconciliation succeeds.

## 1. Prepare a source copy

Stop the legacy application, then copy the database to a dedicated migration
path:

```powershell
Copy-Item -LiteralPath .\backend\portfyl.db -Destination C:\portfyl-migration\portfyl-copy.db
```

Keep that copy unchanged through rehearsal and production. Any byte change
produces a different SHA-256 fingerprint.

## 2. Dry-run against a disposable target

Create a fresh disposable Neon branch/database, run Alembic through head, and
load its migration-owner URL from the secret manager into a PowerShell
variable. Avoid putting the literal credential in shell history.

```powershell
$targetUrl = '<migration-owner URL loaded from secret storage>'
.\deploy\migrate-sqlite.ps1 `
  -Source C:\portfyl-migration\portfyl-copy.db `
  -TargetDatabaseUrl $targetUrl `
  -OwnerEmail owner@example.com `
  -DryRun
```

Expected result: exit code `0`, JSON status `dry_run`, and no users,
workspaces, migration-run rows, or sequence changes in PostgreSQL. Save the
JSON output without the database URL.

## 3. Rehearse a committed import

Recreate the disposable target from empty, apply Alembic head, and run the same
command without `-DryRun`. Review all of the following before production:

- every reported table count matches the legacy inventory;
- `transactions_sha256` and the transaction count/sums are present;
- the validation report has no foreign-key errors;
- the owner e-mail is normalized to the intended Firebase e-mail;
- a second run with the identical source is rejected as already imported.

Smoke-test the disposable imported database with the application using its
separate non-owner runtime URL.

## 4. Production import

1. Confirm the legacy app is stopped and take the final SQLite copy.
2. Confirm the production target is empty and at Alembic head.
3. Record the Neon branch/restore point before import.
4. Run `migrate-sqlite.ps1` once without `-DryRun` using the migration-owner
   URL and the exact intended owner e-mail.
5. Require exit code `0` and archive the machine-readable JSON report,
   timestamp, source SHA-256, target branch ID, and operator identity.
6. Switch application configuration only after the report has been reviewed.

Any exception or reconciliation mismatch rolls back all imported rows. Do not
manually patch a partial target; investigate, recreate the empty target, and
rehearse again from the unchanged source copy.

## 5. Verified Firebase owner claim

The imported user remains pending with no Firebase UID. The owner must sign in
through Firebase with the exact normalized e-mail recorded in the report and
complete e-mail verification. Portfyl binds the Firebase UID only after a
verified token presents that same normalized address. A different address must
not be allowed to claim the workspace.

After the claim, verify login, portfolio/transaction counts, settings,
broker/watchlist/benchmark data, and logout-all. Keep the legacy copy and the
pre-import Neon recovery point until post-cutover verification is signed off.
