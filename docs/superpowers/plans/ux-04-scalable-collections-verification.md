# UX-04 Scalable Collections Verification

Date: 2026-09-13
Branch: `codex/portfyl-ux-overhaul`

## Automated gates

| Gate | Result |
| --- | --- |
| `cd backend; python -m pytest tests/ --ignore=tests/postgres` | Exit 0 — 622 passed |
| `cd frontend; npm test` | Exit 0 — 51 files, 270 tests passed |
| `cd frontend; npm run test:cloud` | Exit 0 — 51 files, 270 tests passed |
| `cd frontend; npm run build` | Exit 0 — local production build completed |
| `cd frontend; npm run build:cloud` | Exit 0 — cloud production build completed |

The backend gained one additive, read-only endpoint
(`GET /portfolio/transactions/page`) with no schema, auth, owner-scoping, or
RLS change. The PostgreSQL/RLS suite was **not** run locally for this phase and
remains a CI-mandatory gate (per the plan's phase-verification note).

## Implementation summary

| Task | Commit | Result |
| --- | --- | --- |
| 1. Paged transactions endpoint | `dc3c22f` | `GET /portfolio/transactions/page` with SQL-side filter/count/sort/offset/limit; invalid `offset`/`limit`/`sort`/`type` → 422 |
| 2. Shared `Pagination` component | `0d0766f` | Range, Previous/Next, numbered pages ≤7, optional accessible page-size selector |
| 3. Transactions server-side paging | `e45e6d4` | URL-backed filter/sort/offset/limit, `Pagination`, offset correction on last-row deletion; startup prefetcher switched to the paged endpoint |
| 4. Allocation bounding | `89f52eb` | `groupPositions` caps at top-7 + Other; new sorted `AllocationBarList` under the chart |
| 5. Analytics correlations | `45d6c05` | Default top-10 absolute-correlation pairs; advanced matrix capped at 12 selectable holdings |
| 6. Tax Report paging | `17fb273` | Realized/unrealized tables paginate at 50 rows; tab/year/page synced to URL |
| 7. Stock Detail insider paging | `d6ddc9f` | `InsiderTransactionsSection` exported, paginated at 25 rows, filter change resets page |

## Plan corrections made during implementation

The phase plan contained several tests that contradicted the spec it quotes, or
that referenced the wrong module/provider shape. These were corrected rather
than copied verbatim:

- **Task 1 `test_offset_and_limit_slice_correctly`** used `limit=2`, which the
  spec explicitly rejects (allowed: 25/50/100). Rewritten to seed 30 rows and
  assert an offset-25/limit-25 slice, plus a separate `limit=100` acceptance
  case.
- **Task 1 cash-row test** passed `shares=None`/`price=None`, but
  `transactions.shares`/`price` are `NOT NULL`. Changed to `0`/`0`.
- **Task 3** used the react-query v4 option `keepPreviousData: true`; the repo
  is on v5, so it uses `placeholderData: (previousData) => previousData`.
- **Task 3's page test** omitted the `ConfirmProvider`/`ToastProvider`
  requirements and real `TickerLink`; the test mocks those, matching the
  existing async-state test pattern.
- **Task 6's page test** mocked `../api`'s `fetchTaxReport` and a
  `{years: [...]}` payload; the real page reads `fetchTaxReport` from
  `../editions/localApi` with a `{gains, unrealized, ...}` shape. The test was
  written against the actual contract.
- **Task 7** used `max-h-96 overflow-y-auto` removal plus `useEffect`; the
  module already imported `useEffect`.

Existing tests updated for the changed contracts (no behavior regression):
`PortfolioPages.async.test.jsx` (paged transactions mock),
`Analytics.async.test.jsx` (card renamed to "Strongest Correlations"),
`TaxReport.precision.test.jsx` (now wrapped in a router, since Tax Report uses
URL state).

## Browser matrix

**Not executed in this environment** — no browser-automation tool was
available to this session. The roadmap's per-phase browser matrix (390×844,
768×1024, 1024×768, 1440×900 against the worktree server) remains outstanding
for:

- Transactions: default page ≤50 rows; paging; filter resets to page 1 and
  updates the URL; deleting the last row returns to the nearest valid page;
  page-size selector 25/50/100.
- Allocation: ≤8 chart segments (7 named + Other); Full Breakdown lists every
  open position by weight with label/value/percentage.
- Analytics: ≤10 strongest pairs by default; advanced matrix allows ≤12
  selections and visibly refuses a 13th.
- Tax Report: both tables paginate at 50; tab/year/page survive reload and
  back/forward.
- Stock Detail: insider table paginates at 25; filter change resets to page 1.
- No horizontal overflow at any of the four viewports; no unexpected console
  errors or failed requests.

## Warnings

- Both Vite builds retain the known >500 kB main-chunk warning; the initial
  transfer comparison against the ~372 KB gzip baseline is scheduled for
  Phase 8.
- The paged endpoint's `type` filter validates against `TRADE_TYPES` and
  returns 422 for unknown types, slightly stricter than the plan's sketch.
