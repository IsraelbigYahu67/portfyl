# UX-07 Product Flows — Verification Record

Date: 2026-09-16  
Branch: `codex/ux-07-product-flows`
Verified implementation/test head: `d69c80d4cb0a4feae315c7eff3265da77d221597`
Worktree: `C:\Users\tomzo\claude\portfyl`

## Status

All automated gates pass at the recorded implementation/test head: fast backend, full PostgreSQL tenancy/CSRF, both frontend editions, and both production builds. Final phase verification still requires the browser matrix:

- The interactive browser/viewport matrix requires an authenticated browser automation session. The Computer Use runtime required by the available skill (`node_repl` with `@oai/sky`) was not exposed in this session.

PR delivery is also pending: neither `codex/portfyl-ux-overhaul` nor the phase branch exists on `origin` at the time of the read-only remote check. The integration target must be restored with owner approval; this phase must not target `main`.

The phase is therefore **not yet marked fully verified**.

## Automated gates

| Gate | Result | Count / duration | Notes |
| --- | --- | --- | --- |
| `backend\.venv\Scripts\python.exe -m pytest backend/tests -q --ignore=backend/tests/postgres` | PASS (0) | 657 tests, 27.33 s | 111 existing deprecation/SQLAlchemy warnings |
| `cd backend; .\.venv\Scripts\python.exe -m pytest tests/postgres/ -q` | PASS (0) | 334 tests, 81.11 s | 10 existing deprecation warnings; PostgreSQL 16.15 |
| `npm.cmd test -- --reporter=dot --maxWorkers=1` | PASS (0) | 73 files / 353 tests, 175.88 s | Existing React `fetchPriority` warning and intentional `useAuth`-outside-provider test output |
| `npm.cmd run test:cloud -- --reporter=dot --maxWorkers=1` | PASS (0) | 73 files / 353 tests, 173.59 s | Same two known console outputs as local |
| `npm.cmd run build` | PASS (0) | 9.87 s | Vite warns that the main chunk exceeds 500 kB |
| `npm.cmd run build:cloud` | PASS (0) | 10.25 s | Vite warns that the main chunk exceeds 500 kB |

Focused checks also passed:

- Backend activation/onboarding/import/export: 33 tests.
- Backend pending activation and import: 26 tests after capacity and foreign-tenant cases were added.
- Frontend routing/onboarding/import/settings: 32 tests.
- Watchlists: 11 tests.
- Settings/data privacy: 19 tests.
- Follow-up Watchlists flows/card/quick-start: 10 tests, 7.99 s, exit 0.
- PostgreSQL pending-activation HTTP tests: 3 tests, 4.83 s, exit 0.

## Follow-up fixes and regression evidence

- `1a1892d`: Watchlist search and sort now live in per-list URL parameters (`wl.<id>.q`, `wl.<id>.sort`). They survive stock navigation, browser back, and direct reload without losing unrelated parameters or affecting another list. Default controls remove their own URL parameter, and editing replaces history rather than adding a history entry per keystroke. Filtering remains entirely client-side.
- `1a1892d`: Alert creation stays disabled with an explanatory reason until capabilities and Discord status are known. Only explicit `connected: true` and the notification capability enable it.
- Before these fixes, `npm.cmd test -- Watchlists.flows.test.jsx --maxWorkers=1` failed in exactly three new regression cases: restored filter and both unresolved status requests. Afterward, the focused three-file gate passed.
- `d69c80d`: PostgreSQL HTTP coverage proves pending creation is idempotent, foreign activation matches an unknown UUID, a forged workspace cannot replace Bob's marker, explicit blank activation clears only Alice's marker, failed import preserves pending state, successful import clears only the matching marker alongside undo state, and importing another active portfolio leaves pending state intact.

## PostgreSQL gate

The first attempt failed because Docker Desktop's Linux engine pipe was unavailable. Docker Desktop was subsequently started in the background and the existing repository test compose service reached Healthy. No production database was addressed.

Environment: Docker engine `29.5.3`; PostgreSQL `16.15`; compose service `deploy-postgres-1`; disposable database/user `portfyl_test`; port `55441`. The test fixture intentionally recreates its disposable schema and exercises migrations and tenant isolation.

After the final pass, only the test PostgreSQL service was stopped, restoring its initial stopped state. Docker Desktop was left running; no container, image, or volume was deleted.

Commands:

```powershell
docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait
cd backend
.\.venv\Scripts\python.exe -m pytest tests/postgres/ -q
.\.venv\Scripts\python.exe -m pytest tests/postgres/test_portfolio_activation.py -q
```

Initial full PostgreSQL run: exit 0, 331 tests, 73.11 s, 10 existing deprecation warnings. New pending-activation tests: exit 0, 3 tests, 4.83 s. Final full rerun after the additions: exit 0, **334 tests**, 81.11 s, 10 existing deprecation warnings.

The local gate is not a waiver of the mandatory `backend-postgres` CI job:

<https://github.com/IsraelbigYahu67/portfyl/actions/workflows/ci.yml>

## Branch / delivery gate

`git ls-remote --heads origin main codex/portfyl-ux-overhaul codex/ux-07-product-flows` returned only `main` at `e252933c3562f9f634e964b9476204c6aa89e31f`, also the phase merge base. The existing checkout already contained the phase implementation when this continuation began. Its history was preserved rather than retroactively recreating the worktree or rebasing. No push, PR, integration-branch creation, or merge was attempted. Owner direction is needed to restore the integration target; browser QA and required PR CI remain prerequisites for merging.

## Interactive browser matrix

Not executed in this session. Do not treat the following as verified until a browser pass records the edition, viewport, and result for each row.

Browser server ports `8001`/`5174` are reserved by the plan but were not started for this pass. No browser account/workspace or screenshots were used; the HTTP suite uses isolated Alice/Bob test workspaces. Console/network/overflow observations are therefore still pending, not inferred from component tests.

The Computer Use skill and its runtime guidance were read before reporting the missing `node_repl` capability. Plugin-directory searches for browser automation and Browser Use found unconnected third-party browser/connector options, but no connected local automation runtime for this matrix. No software/plugin was installed and no local server or authenticated data was exposed externally.

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
