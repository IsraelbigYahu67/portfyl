# Portfyl agent instructions

## Database migration invariant

Every Alembic migration change must keep the application's expected schema
revision in sync. A migration is incomplete until all of the following are true:

1. Add, remove, or rebase the revision under `backend/alembic/versions/`.
2. Set `backend/database.py`'s `EXPECTED_ALEMBIC_HEAD` to the exact current
   revision reported by `alembic heads`. Do this in the same change as the
   migration; never leave the previous revision in application code.
3. Verify that Alembic has exactly one head and that its revision equals
   `EXPECTED_ALEMBIC_HEAD`.
4. Apply `alembic upgrade head` with the migration-owner database credential,
   not the restricted runtime credential, before starting or deploying Portfyl.
5. Start the backend and confirm that `assert_alembic_head()` passes.

Do not commit, deploy, or report a migration task complete while the Alembic
head and `EXPECTED_ALEMBIC_HEAD` differ.

## Parallel session safety

Every plan must be structured so that multiple agent sessions can work in this
repository at the same time without blocking or corrupting each other's work:

1. Each session works on its own dedicated git branch (or git worktree).
   Never commit directly to the shared integration branch; merge/rebase it
   into the shared branch only when the work is finished and verified.
2. Split the plan into independent tasks that touch disjoint sets of files.
   Shared hotspots — `backend/database.py`, `backend/alembic/versions/`,
   config, lockfiles (`package.json`, `requirements.txt`) — must be owned by
   at most one concurrent task. If two tasks must touch the same file, the
   plan must serialize them (assign to different sessions/separate waves)
   instead of running them concurrently.
3. Do not start dev servers, apply migrations, or run other
   resource-mutating commands (DB writes, port-bound processes) while another
   session may depend on the same resources. Prefer isolated instances
   (distinct ports, distinct DB names) or sequence such steps in the plan.
4. After integrating upstream changes, re-run the affected verification
   (tests, `alembic heads` check, lint/typecheck) before reporting a task
   complete. Conflicts introduced by concurrent sessions are resolved locally
   and re-verified, not reported as upstream issues.
