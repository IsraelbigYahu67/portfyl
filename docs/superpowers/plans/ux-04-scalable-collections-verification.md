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

Executed on 2026-09-14 in Chrome against the local Vite and FastAPI servers.
An isolated 130-transaction, 13-holding fixture portfolio was created for the
run and deleted afterwards.

| Surface | Result |
| --- | --- |
| Transactions | PASS — 50 rows on the first page, 50 on the second (`?offset=50`), and 25 after selecting the 25-row size. Filtering for AAPL reset to offset 0, produced 10 AAPL rows, and wrote `limit=25&q=AAPL` to the URL. Back/forward restored the URL-backed state. |
| Allocation | PASS for collection bounds — 8 chart segments (7 named + Other) and all 13 holdings in Full Breakdown. |
| Analytics | PASS for collection bounds — 10 strongest pairs; 12 matrix selections allowed, the thirteenth disabled, and replacing one selection kept the cap at 12. |
| Tax Report | PASS for exercised data — 65 realized rows paginate 50/15 and page 2 uses `?page=1`; the unrealized tab showed all 39 fixture rows. `tab=unrealized&year=2024` survived a full reload. The fixture did not contain more than 50 unrealized lots, so a second unrealized page was not browser-exercised. |
| Stock Detail | PASS for pagination — AAPL showed 79 insider rows in 25-row pages; Next produced 26–50 and switching to the 33-row SELL filter reset to 1–25. |
| Console/network | PASS after blocker fix — the browser console stayed clean and `GET /api/market/history/NVDA?period=1y` returned 200 after non-finite close values were filtered from the history response. |

The four-viewport overflow check produced these results:

| Surface | 390×844 | 768×1024 | 1024×768 | 1440×900 |
| --- | --- | --- | --- | --- |
| Transactions | PASS | PASS | PASS | PASS |
| Allocation | PASS | PASS | PASS | PASS |
| Analytics | PASS | PASS | PASS | PASS |
| Tax Report | PASS | PASS | PASS | PASS |
| Stock Detail | PASS | PASS | PASS | PASS |

The initial run found three mobile overflow defects at 390 px. The 2026-09-14
fix recheck passed after these changes:

- Allocation stacks its chart and breakdown on narrow screens and lets legend
  values shrink within the card.
- Analytics wraps the page heading, benchmark selector, and period controls.
- Stock Detail wraps the quote/actions row and provides an explicit horizontal
  scroller for wide insider rows. At 390 px the document width stayed bounded;
  only the intended insider and DCF regions scrolled internally.

Deleting the last transaction from the last page was not exercised in the
browser; its automated regression coverage remains the evidence for that
path. Tax Report history navigation was represented by direct URL reload;
back/forward was exercised on Transactions.

## Warnings

- Both Vite builds retain the known >500 kB main-chunk warning; the initial
  transfer comparison against the ~372 KB gzip baseline is scheduled for
  Phase 8.
- The paged endpoint's `type` filter validates against `TRADE_TYPES` and
  returns 422 for unknown types, slightly stricter than the plan's sketch.
