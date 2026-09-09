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
   at the branch's `portfyl_runtime` connection string and boot the real app
   against it, then hit it:

   ```powershell
   $env:DATABASE_URL = "<branch connection string, portfyl_runtime role>"
   $env:PORTFYL_EDITION = "cloud"   # backend/edition.py fails closed without this
   # Local drill-only values; never copy production edge/rate-limit secrets.
   $env:PORTFYL_EDGE_TOKEN = "local-restore-drill-edge-token"
   $env:RATE_LIMIT_KEY_SECRET = "local-restore-drill-rate-limit-secret"
   foreach ($rule in @("GLOBAL", "AUTH_SESSION", "BROKER_SYNC", "ASSISTANT_CHAT")) {
       [Environment]::SetEnvironmentVariable("RATE_LIMIT_${rule}_LIMIT", "100", "Process")
       [Environment]::SetEnvironmentVariable("RATE_LIMIT_${rule}_WINDOW_SECONDS", "60", "Process")
   }
   cd backend && python -m uvicorn main:app --host 127.0.0.1 --port 8123
   # in another shell: curl http://127.0.0.1:8123/ (expect 200) and
   # curl http://127.0.0.1:8123/health (database status must be "ok")
   # Direct /api/auth/me must return 403 (trusted-edge rejection).
   # With X-Portfyl-Edge-Token: local-restore-drill-edge-token and
   # CF-Connecting-IP: 127.0.0.1, /api/auth/me must return 401 with
   # code authentication_required. This writes only a drill rate-limit bucket.
   ```

   **Do not** point `tests/postgres/` fixtures at the branch — `postgres_engine`
   in `tests/postgres/conftest.py` runs `DROP SCHEMA public CASCADE` before
   every session (its `_assert_disposable_postgres_url` guard will actually
   refuse to run against a branch whose database name doesn't contain `test`,
   e.g. Neon's default `neondb` — so in practice it fails safe rather than
   destroying the branch, but it still isn't a smoke test). Confirm the
   application actually behaves correctly against the restored data (clean
   startup, no `assert_alembic_head` failure, correct 403/401 body shapes) — not
   just that the raw counts match.

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

### 2026-09-03 — first end-to-end rehearsal (Task 11 Step 8)

```
Date/time (UTC): 2026-09-03 11:53 - 15:39
Operator: Claude Code, on behalf of tom.zoubek@gmail.com (project portfyl-cloud-fstxby)
Restore timestamp targeted: current HEAD of parent branch (project was minutes old; no
    meaningful earlier point existed yet -- this rehearsal proves the mechanism, not a real
    incident recovery)
Neon branch name/ID: restore-drill-2026-09-03 / br-falling-snow-b12o5ebm (deleted after the drill)
Control file used: docs/operations/control-files/prod-20260903.json (captured via
    deploy/validate-restore.py --capture against the neondb_owner pooled URL)
validate-restore.py exit code: 0
validate-restore.py output: {"ok": true, "table_counts": {"benchmarks": 7,
    "benchmark_components": 2, all other tenant tables: 0}} -- matched the control file exactly
    (no tenant data existed yet; only preset benchmark seed rows)
Smoke test result: PASS. Booted the real backend (uvicorn) locally against the branch's
    portfyl_runtime connection string. GET / -> 200. GET /api/auth/me -> 401 with
    {"code":"authentication_required"} (correct shape, not a crash). No assert_alembic_head
    failure at startup.
Promoted to production? No -- pure rehearsal.
Notes: Surfaced and fixed two real bugs while running this for real: (1) the drill runbook's
    step 7 told the operator to run tests/postgres/test_alice_bob_matrix.py against the branch,
    but that suite's postgres_engine fixture does DROP SCHEMA public CASCADE -- its own
    _assert_disposable_postgres_url guard happens to refuse a database name without "test" in
    it (Neon's branch database is "neondb"), so it fails safe rather than destroying the branch,
    but it was never a working smoke test as written; replaced with booting the real app.
    (2) The app now requires PORTFYL_EDITION to be set (backend/edition.py, landed concurrently
    with this drill) -- added that to the smoke-test snippet above.
```

### 2026-09-09 — recovery with real portfolio data

See [operational verification](operational-verification-2026-09-09.md) for
the full evidence and unresolved operational findings.

- Verified production history retention: **21,600 seconds (6 hours)**.
- Source: `main` / `br-icy-poetry-b1p4g4w1`; WAL position `0/387CD48`,
  captured at `2026-09-09T10:07:31.066603+00:00`.
- Branch: `restore-drill-2026-09-09` / `br-twilight-block-b1yrvpgi`.
- Source contained actual transactions and 12 nonempty application tables.
- Source-to-recovery counts and transaction controls matched; Alembic head,
  forced RLS/policies, and runtime role checks passed.
- Cloud backend startup, database health, edge rejection, unauthenticated
  session response, and scoped runtime portfolio read checks passed.
- CLI capture and validation on the branch both exited 0.
- Smoke completed at `2026-09-09T10:09:36.692444+00:00` (approximately
  2 minutes 6 seconds from baseline; not a production failover RTO).
- No production promotion. Recovery branch deleted after verification;
  a subsequent branch listing contained only `main`. Local drill credentials
  removed. Exact control totals remain in ignored `control-files/`.
- This closes the real-data recovery rehearsal gap, but scheduler, monitoring,
  retention-policy approval, and human incident exercises remain open.
