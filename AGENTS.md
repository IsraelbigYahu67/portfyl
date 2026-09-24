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
