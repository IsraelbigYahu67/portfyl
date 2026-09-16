# UX-07 Product Flows — Verification Record

Date: 2026-09-16  
Branch: `codex/ux-07-product-flows`

## Status

Implementation is complete and all available automated local/cloud gates pass. Final phase verification remains pending on two environment-dependent gates:

- PostgreSQL tenancy/CSRF tests require the Docker engine or the repository CI job.
- The interactive browser/viewport matrix requires an authenticated browser automation session. The Computer Use runtime required by the available skill (`node_repl` with `@oai/sky`) was not exposed in this session.

The phase is therefore **not yet marked fully verified**.

## Automated gates

| Gate | Result | Count / duration | Notes |
| --- | --- | --- | --- |
| `backend\.venv\Scripts\python.exe -m pytest backend/tests -q --ignore=backend/tests/postgres` | PASS (0) | 655 tests, 31.23 s | 111 existing deprecation/SQLAlchemy warnings |
| `npm.cmd test -- --reporter=dot --maxWorkers=1` | PASS (0) | 73 files / 349 tests, 155.42 s | Existing React `fetchPriority` warning and intentional `useAuth`-outside-provider test output |
| `npm.cmd run test:cloud -- --reporter=dot --maxWorkers=1` | PASS (0) | 73 files / 349 tests, 156.39 s | Same two known console outputs as local |
| `npm.cmd run build` | PASS (0) | 8.34 s | Vite warns that the main chunk exceeds 500 kB |
| `npm.cmd run build:cloud` | PASS (0) | 7.99 s | Vite warns that the main chunk exceeds 500 kB |

Focused checks also passed:

- Backend activation/onboarding/import/export: 33 tests.
- Backend pending activation and import: 26 tests after capacity and foreign-tenant cases were added.
- Frontend routing/onboarding/import/settings: 32 tests.
- Watchlists: 11 tests.
- Settings/data privacy: 19 tests.

## PostgreSQL gate

Local command attempted:

```powershell
docker version --format "{{.Server.Version}}"
```

Result: exit 1. Docker Desktop's Linux engine pipe was unavailable, so the PostgreSQL compose stack and `backend/tests/postgres/` were not run locally.

This gate is not waived. It must pass in the repository's `backend-postgres` CI job:

<https://github.com/IsraelbigYahu67/portfyl/actions/workflows/ci.yml>

Required local commands once Docker is running:

```powershell
docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait
cd backend
python -m pytest tests/postgres/ -v
```

## Interactive browser matrix

Not executed in this session. Do not treat the following as verified until a browser pass records the edition, viewport, and result for each row.

Required viewports:

- 390×844
- 768×1024
- 1024×768
- 1440×900

Required coverage:

- Stock: direct/reload/back-forward URL tabs, keyboard operation, invalid canonicalization, owned/unowned Overview, all tab async states, and inactive-request checks.
- Watchlists: quick start, local search/sort, alert capability/disconnect reasons, confirmations, optimistic rollback, and narrow layout.
- Import/onboarding: pending reload, Leave import, explicit blank activation, all four stages, preview invalidation, drift recovery, result/undo, and hidden pending switcher row.
- Settings: all direct section URLs, invalid fallback, desktop/mobile navigation, focus movement, isolated queries, preferences, notifications, and destructive Data & Privacy dialogs.
- Every viewport: no page-level horizontal overflow, clipped primary action, unexpected console error, or unexpected failed request.

Run both `edition-local` and `edition-cloud` browser passes against the phase worktree servers on ports 8001/5174 as specified in the implementation plan.
