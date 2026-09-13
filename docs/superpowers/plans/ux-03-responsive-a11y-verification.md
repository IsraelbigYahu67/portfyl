# UX-03 Responsive Shell and Accessibility Verification

Date: 2026-09-13
Branch: `codex/portfyl-ux-overhaul`

## Automated gates

| Gate | Result |
| --- | --- |
| `cd frontend; npm test` | Exit 0 — 45 files, 240 tests passed |
| `cd frontend; npm run test:cloud` | Exit 0 — 45 files, 240 tests passed |
| `cd frontend; npm run build` | Exit 0 — local production build completed |
| `cd frontend; npm run build:cloud` | Exit 0 — cloud production build completed |

The backend is unchanged in UX-03. Its integration baseline remains the 604 passing tests recorded for UX-01.

## Browser matrix

An isolated headless Chrome session exercised the worktree server with deterministic authenticated API fixtures. The checks used real browser layout, focus, keyboard, media-query, and history behavior.

| Viewport | Navigation mode | Drawer keyboard behavior | Skip link | Route focus | `/overview` | Horizontal overflow | Console exceptions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 390×844 | Mobile top bar + drawer | Tab/Shift+Tab trapped; Escape restored trigger; body scroll locked/unlocked | Hidden at −64px, visible at 8px on focus; activation focused `#main-content` | Allocation `<h1>` focused | Redirected to Dashboard | None | None |
| 768×1024 | Mobile top bar + drawer | Tab/Shift+Tab trapped; Escape restored trigger; body scroll locked/unlocked | Passed | Passed | Passed | None | None |
| 1024×768 | Grouped desktop sidebar | Not applicable | Passed | Passed | Passed | None | None |
| 1440×900 | Grouped desktop sidebar | Not applicable | Passed | Passed | Passed | None | None |

All capability-enabled primary destinations were present in both navigation variants. Desktop widths showed no mobile header; sub-`lg` widths showed no desktop sidebar. Every viewport contained exactly one `main#main-content` landmark.

## QA findings fixed

- Dashboard's performance-period controls originally forced the 390px document to 479px. `SectionHeader` now stacks actions below `sm`, its action area wraps, and the performance controls wrap internally.
- Selecting a drawer destination originally let focus restoration overwrite route-change focus and return to the hamburger. Route-driven drawer closure now suppresses trigger restoration, while Escape and explicit dismissal still restore it.

Both findings have regression coverage in the shared primitive, focus-trap, drawer, and AppShell tests.

## Warnings

- Both Vite builds retain the known warning that the main application chunk exceeds 500 kB. Bundle splitting remains scheduled for the roadmap's performance work.
- The AuthProvider negative-context test intentionally logs the caught React error stack while passing.
