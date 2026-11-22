---
type: hub
layer: cross
tags: [arch/hub]
generated: false
---
# Testing

Portfyl has three layers of tests. A fast backend suite runs against an in-memory SQLite database. A slower PostgreSQL suite exercises the real migrations, forced row-level security and the full tenant isolation matrix; this one is the go/no-go gate for opening the product to more users. The frontend uses Vitest. CI runs all of them on every pull request and on pushes to `main`.

## How it works
- Fast backend suite: `backend/tests/*.py` (not the `postgres/` folder). [[backend.tests.conftest (py)]] sets `PORTFYL_TESTING=1`, an in-memory `DATABASE_URL`, `PORTFYL_EDITION=local` and some test-only keys with `setdefault` before anything imports [[database]]. Most tests call router functions directly (helpers in `tests/helpers.py`) and skip HTTP and session middleware. Run from `backend/`: `python -m pytest tests/ -v --ignore=tests/postgres`.
- PostgreSQL integration suite: `backend/tests/postgres/`, configured by [[backend.tests.postgres.conftest (py)]]. It runs real Alembic migrations and a disposable PostgreSQL 16 database ([[deploy.docker-compose.postgres-test (yml)]] or an explicit `TEST_DATABASE_URL` whose database name contains `test`). It covers forced RLS and the Alice/Bob matrix in [[security/tenant-isolation-matrix]]. Run: `cd backend && python -m pytest tests/postgres/ -v`. Never replace these with SQLite-only checks, because RLS and role behavior do not exist in SQLite.
- Install test tools from the hashed lock `requirements-dev.lock` (it includes the runtime lock). Neither pytest nor the Postgres extras are in `requirements.txt`.
- Event-loop guard: `tests/test_event_loop_not_blocked.py` enforces that database-touching endpoints are plain `def` (see [[private_loop]] and [[Backend]]).
- Frontend: Vitest with jsdom, set up in [[frontend.vite.config (js)]] and `src/test/setup.js`, using Testing Library. Run from `frontend/`: `npm test` (local edition) and `npm run test:cloud` (cloud edition).
- Edition-sensitive frontend changes: run `npm test`, `npm run test:cloud`, `npm run build` and `npm run build:cloud`. For ordinary shared UI changes the local test and build pair is the minimum. See [[Edition boundary]].
- CI ([[github.workflows.ci (yml)]]) has four job groups: `backend-lock` (the hashed locks match the requirement specs), `backend-fast` (matrix Python 3.12 and 3.14), `backend-postgres` (PostgreSQL 16 service, matrix 3.12 and 3.14) and `frontend` (matrix local and cloud: tests, script tests for bundle size, readability audit and prerender, then the production build on Node 22).
- Dev stays on Python 3.12 (`start.bat`) while production runs 3.14, so run the fast suite on both when touching dependencies.
- UI changes should also be checked in a real browser (Playwright) against the dev servers, not judged from the diff alone.

## Data
- The PostgreSQL suite creates the whole schema by running the migrations listed in [[Database and migrations]], so a broken migration fails there first.
- Restore validation ([[deploy.validate-restore (py)]]) has its own tests in `backend/tests/test_restore_validation.py`.

## Key code
- [[backend.tests.conftest (py)]]: fast-suite fixtures and environment switches.
- [[backend.tests.postgres.conftest (py)]]: disposable PostgreSQL fixtures and the matrix client.
- [[github.workflows.ci (yml)]]: the CI pipeline.
- [[frontend.vite.config (js)]]: Vitest settings and the edition alias.
- [[deploy.docker-compose.postgres-test (yml)]]: test database container.
- [[database]]: `PORTFYL_TESTING` switch in `DatabaseSettings.from_env`.
- [[edition]]: capability registry that the edition tests check.

## Related hubs
- [[Portfyl]], [[Backend]], [[Frontend structure]], [[Database and migrations]], [[Tenancy and RLS]], [[Edition boundary]], [[Deploy and operations]]

## Docs
- [[security/tenant-isolation-matrix]]: the isolation cases the PostgreSQL suite must pass.
- [[operations/neon-backup-restore]]: restore validation is also tested.
- [[superpowers/plans/2026-10-14-portfyl-code-review-fixes]]: review fixes that added regression tests.
