# Neon PITR restore drill

Neon takes continuous WAL-based backups automatically — there is no manual
backup step. Recovery is via **branching**: you create a new branch of the
project at a past point in time, which never touches the running production
branch. This runbook is the only sanctioned way to validate that a restore
actually works, and it **never restores over production in place**.

`deploy/validate-restore.py` (see `backend/tests/test_restore_validation.py`
for its test coverage) does the actual verification: Alembic head, that every
tenant table still has forced row-level security with a policy attached, that
`portfyl_runtime` is still a non-superuser, non-`BYPASSRLS` role, and that
table counts / transaction control totals match a `--control-file` captured
earlier from the source of truth.

## 0. Keep a current control file

Before you ever need this runbook, you need a baseline to validate against.
Capture one periodically (e.g. after each production deploy, or on a
schedule) from the production database, using the **migration** connection
string (the role must see every workspace's rows, so it must have
`BYPASSRLS` — the runtime `portfyl_runtime` role does not and will
undercount):

```powershell
$env:PROD_DATABASE_URL = "<neondb_owner pooled connection string>"
python deploy/validate-restore.py --database-url-env PROD_DATABASE_URL --capture --output docs/operations/control-files/prod-YYYYMMDD.json
```

Keep captured control files out of git if they might reveal exact customer
row counts you don't want in a public history; a private ops bucket or
Secret Manager works too. The file itself contains no credentials — table
counts and transaction hash totals only.

## Drill stages

Run these in order. Do not skip a stage. Record the result of each drill
using the template at the bottom of this file.

1. **Record project retention.** Neon console → project → Settings →
   Backup/restore. Note the retention window (how far back you can branch
   from) before picking a restore point.

2. **Choose a timestamp before the incident.** Pick a point in time clearly
   before whatever you're recovering from — a few minutes of margin is
   normal; don't cut it exactly at the incident boundary.

3. **Create a new recovery branch at that timestamp.** Neon console →
   Branches → Create branch → "From a specific time" → the timestamp from
   stage 2. Name it something identifiable, e.g. `restore-drill-2026-09-03`.
   This branch is fully independent of `production` — nothing you do to it
   can affect the live database.

4. **Obtain a read-only connection string for the branch.** Neon console →
   the new branch → Connection Details. Use the pooled connection string and
   the branch's owner role (the same role class as `neondb_owner` — it needs
   `BYPASSRLS` to be readable for validation the same way the migration role
   does; see `deploy/cloudrun.md` step 3 for why).

5. **Run `deploy/validate-restore.py` against the branch:**

   ```powershell
   $env:RESTORE_DATABASE_URL = "<the branch's connection string>"
   python deploy/validate-restore.py --database-url-env RESTORE_DATABASE_URL --control-file docs/operations/control-files/prod-YYYYMMDD.json
   ```

6. **Compare the Alembic/RLS/count/control report.** A clean run prints
   `{"ok": true, ...}` and exits 0. Any failure prints every mismatch to
   stderr (revision, a specific table's RLS/policy state, a table count, or
   the transaction control totals) and exits non-zero — treat any non-zero
   exit as a failed drill; do not proceed to stage 7.

7. **Run a smoke test against the recovery branch.** Point a local backend
   at the branch (`$env:DATABASE_URL = "<branch connection string, portfyl_runtime role>"`)
   and run `cd backend && python -m pytest tests/postgres/test_alice_bob_matrix.py -v`
   plus a manual login/dashboard check — confirm the application actually
   behaves correctly against the restored data, not just that the raw counts
   match.

8. **Switch `DATABASE_URL` only after approval.** Promoting a recovery
   branch to be the new production database is a deliberate, approved
   action, not an automatic consequence of a successful drill. If this is a
   real incident recovery (not a drill), get explicit sign-off before
   pointing the live service's `portfyl-database-url` / `portfyl-migration-database-url`
   secrets at the new branch.

9. **Retain the old branch until post-restore verification** is complete —
   don't delete the pre-incident production branch immediately after
   cutting over; keep it until you've confirmed the new branch is healthy
   under real traffic.

10. **Record the result** using the template below.

## Drill record

Append one entry per drill (real or rehearsal) — do not overwrite prior
entries.

```
Date/time (UTC):
Operator:
Restore timestamp targeted:
Neon branch name/ID:
Control file used:
validate-restore.py exit code:
validate-restore.py output (or a hash of it, e.g. `Get-FileHash` on captured output):
Smoke test result (pass/fail, what was checked):
Promoted to production? (yes/no; if yes, approver):
Notes:
```
