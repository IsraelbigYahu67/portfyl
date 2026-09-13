# UX-02 Platform State Verification

Date: 2026-09-13  
Branch: `codex/portfyl-ux-overhaul`

## Automated gates

| Gate | Result |
| --- | --- |
| `cd frontend; npm test` | Exit 0 — 40 files, 206 tests passed |
| `cd frontend; npm run test:cloud` | Exit 0 — 40 files, 206 tests passed |
| `cd frontend; npm run build` | Exit 0 — local production build completed |
| `cd frontend; npm run build:cloud` | Exit 0 — cloud production build completed |

The phase changes only frontend routing and request-state presentation. The backend suite remained green at the integration baseline (604 tests passed in UX-01); no backend source or schema changed in UX-02.

## Browser matrix

The matrix ran in an isolated headless Chrome session against the worktree local and cloud Vite servers. API requests were intercepted at the browser network boundary with deterministic authenticated, portfolio, empty-data, and HTTP 503 fixtures. This made every failure and recovery repeatable without depending on a live account, broker, or market-data provider.

| Viewport | Routes exercised | Forced failure state | Retry recovery | Document overflow | Console exceptions |
| --- | --- | --- | --- | --- | --- |
| 390×844 | 11/11 | Passed | 11/11 issued a new successful request | None | None |
| 768×1024 | 11/11 | Passed | 11/11 issued a new successful request | None | None |
| 1024×768 | 11/11 | Passed | 11/11 issued a new successful request | None | None |
| 1440×900 | 11/11 | Passed | 11/11 issued a new successful request | None | None |

The eleven routes were Dashboard, Allocation, Transactions, Dividends, Analytics, Search, Stock, Watchlists, Settings, Assistant, and Tax Report. Each target endpoint returned HTTP 503 through the configured query retry policy until the page exposed an accessible error alert. Activating Retry then switched the endpoint to a valid empty/content response; the alert cleared and the request counter increased.

## Routing and edition evidence

- An authenticated CSV portfolio reached Dashboard without broker or obsolete platform state.
- `sb_platform=t212` was removed during authenticated startup while Dashboard remained available.
- An authenticated workspace with no portfolio rendered onboarding.
- Choosing “Connect a broker” created/selects the portfolio and reached Settings before the portfolio refetch could unmount onboarding. The browser check exposed this race; a regression test now holds the intended ordering.
- The local server exposed Tax Report and not Plans when capabilities allowed it. The cloud server exposed Plans and not Tax Report.

## Warnings and deferrals

- Both Vite builds retain the existing warning that the main application chunk exceeds 500 kB. Bundle splitting belongs to the roadmap performance work.
- The AuthProvider negative-context test intentionally logs the caught React error stack while passing.
- No UX-02 behavior is deferred.
