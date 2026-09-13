# UX-01 Data Trust Verification

Date: 2026-09-13  
Branch: `codex/portfyl-ux-overhaul`

## Automated gates

| Gate | Result |
| --- | --- |
| `cd backend; python -m pytest tests/ -v --ignore=tests/postgres` | Exit 0 — 604 passed, 133 warnings |
| `cd frontend; npm test -- --run` | Exit 0 — 33 files, 173 tests passed |
| `cd frontend; npm run test:cloud -- --run` | Exit 0 — 33 files, 173 tests passed |
| `cd frontend; npm run build` | Exit 0 — local production build completed |
| `cd frontend; npm run build:cloud` | Exit 0 — cloud production build completed |

The phase does not change schema or row-level security. PostgreSQL integration tests remain mandatory in CI and were intentionally excluded from this local gate, as specified by the phase plan.

## Browser matrix

The matrix ran in an isolated headless Chrome session against the worktree Vite build on port 5174. API responses were intercepted with deterministic fixtures so the same valid, review, unavailable, tiny-lot, null-percentage, and provider-failure states were exercised at every viewport without depending on a broker account or live market provider.

| Viewport | Dividend states | Tax precision | Keyboard focus | Document overflow | Console / transport failures |
| --- | --- | --- | --- | --- | --- |
| 390×844 | Valid, review, unavailable, and expanded provenance passed | `0.00000002`, sub-cent money, and null percentage passed | First Tab reached the portfolio button with `:focus-visible` | None | None |
| 768×1024 | Passed | Passed | Passed | None | None |
| 1024×768 | Passed | Passed | Passed | None | None |
| 1440×900 | Passed | Passed | Passed | None | None |

The forced `/api/portfolio/dividends` HTTP 503 rendered the explicit “Could not load dividend data” alert and “Try again” action. It did not render “No holdings found.” The expected HTTP 503 was fulfilled deliberately; Chrome reported no transport failure and the page emitted no console error.

## Warnings and deferrals

- Backend warnings are existing Python/FastAPI/SQLAlchemy deprecations plus one identity-map warning; all tests passed.
- Both Vite builds warn that the main application chunk exceeds 500 kB. Bundle splitting is tracked by the roadmap performance phase and is not part of UX-01.
- The AuthProvider negative-context test intentionally prints the caught React error stack in both frontend runs; it is an expected passing assertion, not a test failure.
- No phase-specific item is deferred.
