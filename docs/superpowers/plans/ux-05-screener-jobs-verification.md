# UX-05 Non-Blocking Screener Jobs Verification

Date: 2026-09-13
Branch: `codex/portfyl-ux-overhaul`

## Automated gates

| Gate | Result |
| --- | --- |
| `cd backend; python -m pytest tests/ --ignore=tests/postgres` | Exit 0 — 638 passed |
| `cd frontend; npm test` | Exit 0 — 53 files, 277 tests passed |
| `cd frontend; npm run test:cloud` | Exit 0 — 53 files, 277 tests passed |
| `cd frontend; npm run build` | Exit 0 — local production build completed |
| `cd frontend; npm run build:cloud` | Exit 0 — cloud production build completed |

The backend added an in-process job registry, three local-edition endpoints,
and a `_in_range` semantics fix. No SQL query, migration, table, or
owner/workspace predicate was added or changed, so the PostgreSQL/RLS suite
stays a CI-mandatory gate and was not run locally for this phase.

## Implementation summary

| Task | Commit | Result |
| --- | --- | --- |
| 1. `_in_range` missing-value fix | `b32813b` | Unset filters no longer exclude rows whose metric is missing; a missing value fails only when a bound is set |
| 2. Job registry | `0eb6048` | `backend/services/screener_jobs.py`: `ScreenerJob`, fingerprint dedup, 30-min TTL, 20-job retention, module-level registry + lock |
| 3. Job worker | `5f987ac` | Single-worker `ThreadPoolExecutor`, 12-wide ticker batches, per-row progress under lock, batch-boundary cancellation, defensive failure state |
| 4. HTTP endpoints | `8d597e5` | `POST/GET/DELETE /api/market/screener/jobs...` registered via `local_features.py` (local only), returning the spec's job JSON |
| 5. `useScreenerJob` hook | `f9a4aaf` | 1s polling, hidden-tab pause/resume, `sessionStorage` reconnect, cancel/retry, `setPage` for server-paged results |
| 6. Screener page rewire | `87b9fd6` | yfinance path runs as a job with Run Scan/Cancel/Retry, progress, and shared `Pagination`; Shibui whole-market path unchanged and synchronous |

## Edition boundary

Screener remains local-only. `frontend/src/edition.test.jsx` continues to
assert `/screener` is in `LOCAL_ROUTES` and absent from `CLOUD_ROUTES`, and a
scan of the cloud build output (`frontend/dist/assets/*.js` after
`npm run build:cloud`) finds no `Run Scan`, `Stock Screener`, or
`screener/jobs` strings.

## Plan corrections made during implementation

- **Task 6 test** rendered `<Screener />` without a `QueryClientProvider`, but
  the page legitimately keeps a `useQuery` for the synchronous Shibui path.
  The test now wraps in a provider and uses a 3s wait for the first poll.
- **Task 5 reconnect test** used `waitFor` under `vi.useFakeTimers()`, which
  stalled. Replaced with an explicit `vi.advanceTimersByTimeAsync(0)` flush.
- Unused `waitFor` import removed from the hook test.

## Browser matrix

Executed on 2026-09-14 in Chrome against the local edition.

| Check | Result |
| --- | --- |
| Non-blocking create | PASS — Run Scan returned control in about 390 ms and immediately rendered `Scanning… 0 / 6 (0%)` with Cancel. |
| Progress | PASS — a 30-ticker run visibly advanced while polling. Hidden-tab pause/resume was not separately instrumented. |
| Cancel | PASS after blocker fix — cancellation leaves the page in an explicit `Scan cancelled` state; a stale in-flight poll can no longer overwrite it. |
| Retry | PASS after blocker fix — Retry is rendered for cancelled and failed jobs and re-submits the same filters. |
| Reconnect | PASS — after navigating to Allocation and back, Screener reconnected at `Scanning… 28 / 30 (93%)` and completed with 30 rows. |
| Pagination size | PASS after blocker fix — a 30-row result exposes 25/50/100 choices. Selecting 25 rendered rows 1–25 and fetched the first page with `limit=25`. |
| Shibui Whole Market | PASS — selecting the universe synchronously returned 50 results and changed the primary action to Refresh. |
| Viewports | PASS for the empty/shell state at 390×844, 768×1024, 1024×768, and 1440×900; no document-level horizontal overflow. The populated yfinance and Shibui tables were inspected on desktop. |
| Console | PASS — no console errors or warnings were recorded. |

The Phase 5 release blockers found in the initial browser run are resolved.
Polling behavior in a truly hidden browser tab still needs a targeted browser
or integration test.

## Warnings / deferrals

- Both Vite builds retain the known >500 kB main-chunk warning (baseline
  condition; the initial-transfer comparison is Phase 8).
- Screener's local `fmtMoney`/`fmtPct` helpers were intentionally left as-is:
  this plan added no new money/date formatting, so §7.4's centralization rule
  does not require migrating them here.
- The job worker is process-local by design. On a multi-instance Cloud Run
  deployment a job would only be pollable from the instance that created it;
  this is acceptable because Screener is local-edition-only (single owner
  instance), not a cloud feature. Noted for any future scale-out.
