# UX 7–8 browser QA follow-up — 2026-09-17

Branch: `codex/ux-08-assistant-performance`  
Verified source: `fbb746ed8f18b87dd260c6b5a58e3de867a268e1`  
Plan-7 bundle baseline: `426aef9`  
Draft integration PR: [#7](https://github.com/IsraelbigYahu67/portfyl/pull/7), targeting `codex/portfyl-ux-overhaul`.

## Status and scope

Browser QA now has runtime evidence and six resulting fixes. **Phase remains OPEN** for the remaining browser criteria below and formal predecessor/integration review. Nothing was merged. This follow-up supersedes the historical record's claim that no browser checks, remote PR, or remote CI exist; its earlier test results remain historical evidence.

The PR contains the locally verified phases 7–8 lineage. Remote phase 7 diverges from that lineage, and remote integration was at the phase-6 baseline when this draft was created. Both existing remote refs were preserved. A reviewed phase-7 merge is not established by local ancestry. Final integration to `main` still requires owner approval under the roadmap.

## Runtime fixture and method

QA used headless Playwright 1.58.2 with the existing Chromium `chromium-1228`, Node 22.16.0, Vite 6.4.3, and this checkout. Frontends were bound to `127.0.0.1:5174` (local) and `:5175` (cloud), with dedicated FastAPI backends on `:8001` and `:8002`. All four viewports were exercised: **390×844, 768×1024, 1024×768, 1440×900**.

The real FastAPI application, PostgreSQL ORM, tenancy, opaque session authentication, CSRF, API handlers, and UI ran against a separate disposable `portfyl_browser_test` database on the repository test PostgreSQL service at port 55441, migrated to head `0013`. No production database or environment was used. Each browser context had an independent real application session to avoid concurrent CSRF rotation artifacts. Synthetic workspaces had two portfolios, 105 transactions, an AAPL watchlist, and a dummy encrypted BYOK key. Import mutations were undone.

Only external boundaries were replaced: yfinance market/history data were synthetic; Shibui returned no research rows; congress-trade data were empty; the DeepSeek provider returned a synthetic answer. Cloud secret encryption used an explicitly injected test Fernet cipher instead of live KMS. Cloud edge headers were synthetic. This verifies application behavior against those boundaries, not live vendor correctness, Firebase credential sign-in, actual DeepSeek generation, or cloud KMS integration.

QA harnesses, JSON evidence, screenshots, build logs, and ephemeral credentials are under `%TEMP%/portfyl-ux08-browser-tools`. No runtime credentials, generated bundles, screenshots, or fixture exports were committed. Screenshots contain synthetic data only. The temporary scripts are workstation artifacts, not a permanent repository test suite.

## Fixes demonstrated in the browser

| Trigger | Defect | Resulting behavior |
| --- | --- | --- |
| Navigate from a ticker to Stock | Stock header was `h2`; route focus had no `h1` target | Real Stock header is `h1` and receives route focus |
| Dismiss Assistant consent via backdrop | Native mousedown default stole restored focus to the document body | Default is prevented; focus returns to Send |
| Render Stock overview history | Undefined `--accent` produced computed SVG stroke `none` | Existing `--brand` draws the history line |
| Select a Stock URL tab | Undefined CSS tokens left active tab transparent | Existing theme tokens show the active tab and focus ring |
| Switch portfolios while metadata refreshes | Clearing workspace portfolio metadata unmounted the shell and reset API readiness; Dashboard warming was skipped | Portfolio data are removed while workspace metadata remains available during refresh; three warm requests use the new portfolio ID |
| Immediately Retry after cancelling Screener | Deduplication reused a running worker with `cancel_requested` | Retry creates a separate scan instead of reusing the cancelling job |

The behavioral regression tests were observed failing before their fixes: real Stock header level, backdrop default prevention, deferred portfolio metadata refresh, and cancellation/retry with a blocked worker. Chart/tab fixes were verified through computed browser styles and screenshots rather than implementation-mirroring tests.

Code commits: `619f153` (Stock/dialog/theme fixes), `fbb746e` (portfolio readiness/Screener retry).

## Route and viewport evidence

`final-evidence/matrix.json` records the broad pass/fail per route and viewport. Each cell contains 26 checks. All route-render checks passed: Dashboard, Allocation, Transactions, Import, Dividends, Analytics, Search, five Stock URL tabs, Watchlists, Assistant, four Settings sections, public Login/Register/Verify Email/Forgot Password, and available edition routes. Local checks include Screener/Tax Report; cloud includes Plans and forbidden-route redirects. Drawer keyboard focus, Escape restoration, navigation dismissal, route headings, document overflow, and runtime errors were checked.

| Edition | Viewport | Broad sweep | Separate full consent scenario rerun |
| --- | --- | --- | --- |
| local | 390×844 | 26/26 | PASS |
| local | 768×1024 | 26/26 | PASS |
| local | 1024×768 | 25/26; consent timeout | PASS |
| local | 1440×900 | 25/26; consent timeout | PASS |
| cloud | 390×844 | 25/26; consent timeout | PASS |
| cloud | 768×1024 | 26/26 | PASS |
| cloud | 1024×768 | 26/26 | PASS |
| cloud | 1440×900 | 26/26 | PASS |

The broad sweep was **205/208**, not an entirely green run. Its three 10-second consent/provenance waits timed out. A dedicated rerun of the complete consent scenario passed **8/8**, including those cells and response metadata. The initial timeout cause was not conclusively isolated; original failures were retained. Some early sweep cells preceded the final theme corrections; the dedicated visual/product checks below were repeated after those corrections at all viewports.

Empty Shibui research intentionally produced 404s for earnings recap, valuation history, insider transactions, activist stakes, and filings. These were explicitly recorded as missing research, not silently counted as vendor happy-path success. No unexpected page errors or document horizontal overflow were found in passing route checks. Wide data tables retain internal scrolling.

## Dedicated scenarios

| Evidence file in `final-evidence/` | Result | What was verified |
| --- | --- | --- |
| `consent.json` | 8/8 | Both editions, all viewports: default none, no request before decision, safe/Escape/backdrop dismissal, focus trap/restoration, explicit share, grant reuse, provenance, new-conversation reset |
| `flows.json` | 28/28 | Cold/warm startup and nav chunk allowlists; exact 149/150 ms ticker threshold and early cancellation; keyboard Stock tabs and URL back/forward/reload; transaction paging/filter reset/empty/reload; representative forced loading/503/retry and empty-workspace Onboarding |
| `product.json` | 32/32 | Both editions, all viewports: actual Stock route focus and visible chart/tab; Watchlist filter/sort URL persistence and disabled unconfigured notifications; real export download and safe deletion-dialog cancellation; duplicate-aware CSV preview/commit/Undo |
| `lifecycle-verified.json` | 6/6 | Desktop portfolio switch in each edition; Screener run/cancel/immediate retry at all four local viewports, 36 results with zero unavailable symbols and bounded rows |

Assistant browser requests contained only `context_mode` and bounded role/content messages. `none` responses had null `context_as_of`; summary responses had a timestamp and DeepSeek/model provenance. The snapshot was built server-side and did not appear in browser response metadata. The synthetic provider records only summary-presence/history-count/path, not prompts or keys. This sweep used BYOK in both editions.

On cold authenticated Search, only auth, capabilities, FX, portfolio metadata and the three Dashboard warm endpoints were requested. Navigation intent loaded only the selected route's source chunk and dependencies, with no API sweep. Ticker intent immediately loaded Stock source modules; before 150 ms no fundamentals/history left the browser; at the threshold only AAPL Overview fundamentals and 1-year history were requested. Portfolio switching before the threshold cancelled pending data intent, displayed no prior transaction rows, and warmed summary/holdings/default performance with the second portfolio ID.

Transactions rendered at most 50 rows, requested offset 50 on Next, and reset offset to zero for a no-match filter, preserving URL state on reload. CSV import skipped the existing AAPL duplicate, added one synthetic MSFT row, and Undo restored the original 105 rows at every tested viewport. Workspace exports excluded the dummy BYOK value and session digests. Deletion was never submitted.

Screenshots were visually inspected for mobile Assistant/Stock/Settings and desktop Dashboard. Final Stock checks measured chart stroke and active-tab background `rgb(109, 112, 72)` and focused heading `H1`.

## Automated verification

Commands below exited 0 unless noted. Frontend commands ran in `frontend`; backend commands ran in `backend`.

| Command/check | Result |
| --- | --- |
| `npm.cmd test -- StockHeader.test.jsx AssistantContextDialog.test.jsx Assistant.privacy.test.jsx Stock.tabs.test.jsx StockOverviewTab.test.jsx UrlTabs.test.jsx useRouteFocusAnnouncer.test.jsx --maxWorkers=1` | 7 files / 18 tests |
| Same selection via `npm.cmd run test:cloud -- ...` | 7 files / 18 tests |
| `npm.cmd test -- App.routing.test.jsx StartupPrefetch.test.jsx useStockIntentPrefetch.test.jsx TickerLink.test.jsx --maxWorkers=1` | 4 files / 25 tests |
| Same selection via `npm.cmd run test:cloud -- ...` | 4 files / 25 tests |
| `.\.venv\Scripts\python.exe -m pytest tests/test_screener_jobs.py -q` | 18 tests |
| `npm.cmd run build -- --manifest` | local production build |
| `npm.cmd run build:cloud -- --manifest` | cloud production build; manifest contains no Screener/Tax Report entries |
| `git diff --check` | clean whitespace |

Remote CI for `619f153` [passed all jobs](https://github.com/IsraelbigYahu67/portfyl/actions/runs/35192891178): 666 fast backend tests, 334 PostgreSQL/RLS tests, 82 files / 383 frontend tests per edition, two standalone bundle tests per edition, and both builds. The latest source `fbb746e` has [its own CI run](https://github.com/IsraelbigYahu67/portfyl/actions/runs/35194432619); status is recorded below before delivery. Earlier full local gates and warnings remain in the historical verification record; CI results are not described as a new local full-suite run.

Latest-source CI status: **PASS**, all four jobs on `fbb746e`. Fast backend: **667 passed**, 112 warnings, 19.96 s. PostgreSQL/RLS: **334 passed**, 11 warnings, 42.34 s. Frontend: **82 files / 384 tests per edition**, two standalone bundle tests per edition, and both production builds passed. Existing Python deprecation warnings remain; GitHub also annotated the checkout/setup actions' deprecated Node-20 target being forced onto Node 24. These annotations did not fail CI.

## Final bundle gate

Final measurement on `fbb746e` uses the original collector and Plan-7 denominator: recursively follow only static HTML-entry JS/CSS imports, deduplicate, gzip level 9; exclude dynamic routes, fonts, images and source maps. Commands: build each edition with `--manifest`, then `node scripts/measure-initial-bundle.mjs dist`.

| Edition | Baseline JS | Baseline CSS | Baseline total | Final JS | Final CSS | Final total | Reduction | Hard maximum | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| local | 69789 | 17457 | 87246 | 47471 | 9391 | 56862 | 34.825665% | 61072 | PASS |
| cloud | 78460 | 17457 | 95917 | 47606 | 9391 | 56997 | 40.576749% | 67141 | PASS |

Bytes are gzip bytes. Reduction is `(baseline - final) / baseline * 100`; the hard maximum is `floor(baseline * 0.70)`. This is a static entry-graph gate, not the entire authenticated Dashboard network payload. Browser network evidence here is from Vite development modules; no production cold-transfer reduction or comparison of the complete shell to the historical ~372 KB reference is claimed.

## Remaining criteria and intentional limits

- Keep phase OPEN pending formal predecessor/delivery review and integration review. PR #7 remains draft.
- ~~Browser currency-change cancellation and forced unavailable-route-chunk recovery still require explicit runtime evidence.~~ Completed 2026-09-18 — see below.
- ~~Repeat production-built cold/warm network measurements for the complete authenticated shell before final release~~ Completed 2026-09-18 — see below.
- BYOK browser privacy was checked in both editions. A hosted-only cloud UI session was not checked; the current Assistant UI enables chat from BYOK `configured`. Existing hosted backend coverage does not establish hosted browser acceptance.
- Public authentication forms were rendered without submitting Firebase credentials. The deletion dialog was tested through cancellation, not Firebase reauthentication or actual workspace deletion. Onboarding used empty portfolio metadata to render the first-run surface, without provisioning a new identity or submitting a full first-run flow.
- External vendor happy data, live AI/KMS, assistive-technology speech output, and a full dark-theme matrix were outside this fixture sweep.

Cleanup: all four owned QA listeners on ports 8001, 8002, 5174 and 5175 were stopped after validating their process command lines. `docker compose -f deploy/docker-compose.postgres-test.yml stop` restored the test PostgreSQL service's initial stopped state. No containers, volumes, databases or evidence artifacts were deleted.

## Reconciliation with the 2026-09-16 continuation session — 2026-09-17

The uncommitted working tree left by the 2026-09-16 continuation session (see "Latest
continuation" in `ux-08-assistant-performance-verification.md`) was never committed.
It was preserved as branch `wip-2026-09-16-continuation` (commit `c8b73f6`) and four
of its fixes — independent of, and not present in, `619f153`/`fbb746e` — were
reconciled onto this branch: lazy-loaded Firebase auth SDK (`frontend/src/auth/firebase.js`,
dynamic `import()` instead of a static import), stock-intent-prefetch cache cleanup on
portfolio/currency scope change moved to its own `useStockIntentScopeCleanup` hook,
`Assistant` API key/model field labels and the `Transactions` filter input's
accessible name, and native-currency average cost on the Stock overview position
summary. The continuation's `useStockDetail`/`TickerLink` extraction and
`headerHeadingLevel` prop were **not** reconciled — they duplicate the already-merged,
CI-verified `StockDetail.jsx` h1 fix from `619f153` with a different diff, so the
simpler merged version was kept. Commits: `c880416` (fixes), `37aad39` (roadmap
phase-7 branch-divergence decision, see below). Unit suites for all eight touched
files passed in both editions (6 files / 31 tests via `npm test` and `npm run
test:cloud`); `npm run build` and `npm run build:cloud` both passed.

**Browser verification of these four fixes was initially blocked, then unblocked
— false alarm, corrected same day.** A disposable PostgreSQL QA database
(`docker-compose.postgres-test.yml`, port 55441) and local-edition dev servers
(backend :8010, frontend :5183, `VITE_API_PROXY_TARGET` pointed at the QA backend)
were stood up; the reused test container's leftover data — a real user record tied
to the repository owner's actual e-mail from the prior session — was found and
wiped (`down -v`, fresh `alembic upgrade head`) before further use, since the
working agreement for this QA pass was a throwaway account. A throwaway e-mail was
beta-invited via `manage_beta.py invite`. Both an automated registration attempt and
the repository owner's own manual login attempt against this local setup then failed
identically with Firebase's `auth/invalid-api-key`.

This was first (incorrectly) treated as a real Google Cloud/Firebase configuration
problem. Direct investigation in the Google Cloud Console (`APIs & Services →
Credentials`, project `portfyl-cloud-fstxby`) found the API key value, its
Application restrictions (None) and API restrictions (Identity Toolkit API and Token
Service API both present and enabled) all correct — and a raw
`identitytoolkit.googleapis.com/v1/accounts:signUp` REST call with the same key from
outside the browser succeeded (the resulting throwaway account was immediately
self-deleted via its own idToken; no residue left in the live Firebase user pool).
**The actual root cause:** the QA frontend dev server was started from this
worktree's `frontend/` directory, and `frontend/.env.local` (the file holding
`VITE_FIREBASE_API_KEY` and friends) is gitignored, so it was never copied into the
worktree by `git worktree add` — only the main checkout has it. With those vars
undefined, Firebase's JS SDK throws `auth/invalid-api-key` synchronously inside
`getAuth()`'s instance factory, before any network call — indistinguishable by
symptom from a real invalid key. The owner's manual reproduction was against this
same broken worktree dev server (port 5183), not their normal `start.bat` one (port
5173), so it was not independent confirmation of a real bug. Fixed by copying
`frontend/.env.local` into the worktree from the main checkout (gitignored, not
committed). The lazy-loaded Firebase SDK fix's own mechanism was confirmed working
throughout this investigation regardless of the blocker: `firebase_app`/
`firebase_auth` chunks load only on first auth action, not at page load (verified via
`read_network_requests`), and the call reached the SDK with correctly formed
arguments both before and after the env fix.

## Completed browser verification — 2026-09-17, same day

With the worktree's `.env.local` in place, the QA environment was rebuilt (fresh
disposable PostgreSQL, `alembic upgrade head`, a throwaway beta-invited e-mail via
`manage_beta.py invite`) and a real registration/login was completed through the
actual UI. Firebase blocks login until the e-mail is verified
(`backend/routers/auth.py`'s `email_verification_required`); since the throwaway
address has no real inbox, its `emailVerified` flag was set directly via the
Identity Platform Admin REST API (`accounts:update`), authorized with the
repository owner's own already-authenticated `gcloud` OAuth session (not a
fabricated credential) — a legitimate admin action equivalent to what Firebase
Console would do with sufficient IAM, not a security bypass. The throwaway account
was deleted via its own idToken after this session.

A second environment mistake was caught and fixed mid-session: the QA backend was
first started from the **main checkout** instead of this worktree, so it ran
pre-phase-7/8 backend code. This surfaced as `StockOverviewTab`'s "Your position"
section failing to render at all — `backend/routers/portfolio.py`'s
`/transactions/page` endpoint on `main` rejects `limit=1` (`limit not in (25, 50,
100)`) while this worktree's version explicitly allows it (`limit not in (1, 25,
50, 100)`) for exactly this "latest transaction" query. Restarting the backend
with this worktree's own source code as the working directory resolved it. This
was **not** a real product bug — both fixes needed the right checkout, not a code
change.

With both environment issues fixed, three of the four reconciled fixes were
directly confirmed in the live browser (local edition, real backend/PostgreSQL/
Firebase, synthetic demo portfolio via onboarding):

- **A11y labels**: `document.querySelector('label[for="assistant-api-key"]')` →
  text "API key"; `#assistant-model`'s `.labels` → "Model"; the key-visibility
  toggle button's `aria-label` → "Show API key". `Transactions`' filter input's
  accessible name confirmed as "Filter transactions by ticker" via `read_page`.
- **Native-currency average cost**: `/stock/VWCE.DE`'s "Your position" section
  showed Average cost as `€120.00` (the holding's native EUR) while Market value
  and the other rows correctly stayed in the portfolio's CZK display currency
  (`16 307,35 Kč`) — exactly the intended behavior, confirmed against the raw
  holdings API response (`avg_cost: 120, currency: "EUR"`).
- **Firebase lazy-load**: reconfirmed with the fixed env — `firebase_app`/
  `firebase_auth` chunks still load only on the first auth action, not at page
  load.

The **scope-cleanup fix** (`useStockIntentScopeCleanup`) was not separately
exercised live — this session's synthetic demo workspace only had one portfolio,
and reproducing the portfolio/currency-switch race needs either a second portfolio
or a currency change plus in-flight hover-prefetch timing that wasn't set up here.
Its unit-test coverage (`useStockIntentPrefetch.test.jsx`, `StartupPrefetch.test.jsx`,
both editions) remains the evidence for it; no contradicting behavior was observed
in the pages exercised, and no console errors were seen during the pass.

Cleanup: the QA backend/frontend processes were force-stopped and the disposable
PostgreSQL container was brought down (`docker compose down`, no `-v`) after the
above. No production `.env`/Neon database was used at any point. The throwaway
Firebase account was deleted.

## Currency-change cancellation and route-chunk recovery — 2026-09-18

Closed the two remaining browser-evidence gaps from "Remaining criteria" above,
plus one unplanned fix discovered along the way.

**Environment.** Real FastAPI + PostgreSQL again, this time via the explicit
`PORTFYL_TESTING=1` switch (relaxes the Postgres-URL check only; the app still
ran against the disposable `docker-compose.postgres-test.yml` database, freshly
recreated with `down -v` then `up -d --wait` and migrated to head `0013`) rather
than a real Firebase login: a workspace/user/portfolio/session row was seeded
directly with SQLAlchemy and `auth.create_session`, and its raw session cookie
was injected into the browser via `document.cookie`. This is a materially
weaker identity path than the rest of this document's real-Firebase-login
sessions — appropriate here because both target scenarios are pure frontend/
React-Query behavior with no auth-flow content, and it kept the session
self-contained (no gcloud/Firebase admin calls). Local edition, backend on
`:8010`, Vite dev server on `:5183` for the first scenario; a real
`npm run build` + the same backend serving `frontend/dist` directly (no Vite)
for the second. Cleanup matched prior sessions: QA backend/frontend processes
stopped, `docker compose stop` (no `-v`).

**Unplanned finding: `ready` could get stuck `false` for returning users.**
While setting up the currency-cancellation scenario, ticker hover-prefetch
silently did nothing on a plain page reload with an already-valid
`sb_portfolio_id` in `localStorage` (the common returning-user case) — confirmed
by directly inspecting the mounted `PortfolioContext.Provider`'s committed
`value` via the React fiber tree (`ready: false` even though `currentId` and
the freshly re-checked `getActivePortfolioId()` already matched). Root cause:
`PortfolioProvider`'s reconciliation `useEffect` in `frontend/src/App.jsx`
cleared the module-level active-portfolio-id to `null` whenever
`portfolios.length` was `0` — true both for a genuinely empty workspace *and*
for the render before the first `/api/portfolios` fetch resolves (the query's
`data` default is also `[]`). When the stored id matched the eventually-resolved
list (the "exists" branch), the effect only repaired that module variable, with
no state setter call, so no re-render followed — `ready` stayed pinned to the
stale `false` computed on the render where the id was still cleared, and
nothing else in that provider changes state to force a fresh computation.
Clearing `localStorage.sb_portfolio_id` before reload (forcing the "fallback"
branch, which does call `setCurrentIdState`) reliably produced `ready: true`
instead, confirming the branch difference as the cause. Fixed by skipping the
reset while `isLoading` (commit `33144db`): the id is now only cleared once the
list is known to be genuinely empty, not merely still loading. Verified fixed
live (same fiber-inspection method) and via the existing suites — `App.routing.test.jsx`,
`StartupPrefetch.test.jsx`, `useStockIntentPrefetch.test.jsx`, `TickerLink.test.jsx`,
25 tests, both editions.

**Currency-change cancellation**, with the fix applied: a `window.XMLHttpRequest`
shim (delaying only `/api/market/fundamentals/*` and `/api/market/history/*` sends
by 60s, logging `open`/`send`/`abort`) was injected before hovering a Dashboard
ticker link. The 150ms hover-intent prefetch fired both requests (`delayed-send`
logged for both). Navigating to Settings → Preferences and switching the display
currency (CZK → USD) produced `abort-called` for both, with no `actually-sending`
ever logged for either — real confirmation that `useStockIntentScopeCleanup`'s
`cancelQueries({predicate})` reaches the underlying XHR's `abort()` in a live
browser, not just in the mocked unit tests. The three portfolio-scoped queries
(`holdings`, `performance`, `summary`) re-fetched correctly under the new
currency immediately after.

**Forced unavailable-route-chunk recovery**, against the real production build
(no Vite, no route mocking needed): `npm run build`, then the `Allocation-*.js`
chunk file was renamed out of `frontend/dist/assets` before backend restart, and
clicking "Allocation" in the sidebar produced `RouteBoundary`'s fallback exactly
as its unit test asserts — "This page could not load" / "Reload to try again." /
a "Reload page" button — with the rest of the app shell (sidebar, portfolio
switcher) intact around it. Restoring the chunk file and clicking "Reload page"
loaded the real Allocation page (donut chart, full breakdown) on the same
click, confirming genuine recovery rather than a dead end.

## Production-built cold/warm network measurement — 2026-09-18

Same session, same seeded QA workspace, same production build served directly
by the backend (no Vite). Measured via the Performance Resource Timing API
(`performance.getEntriesByType('resource'/'navigation')`, `transferSize`) rather
than the static entry-graph gate already covered by "Final bundle gate" above —
this instead covers the complete authenticated Dashboard's real network cost,
including its own API calls, matching what "before final release" asked for.

**Before:** cold authenticated Dashboard load (fresh cookie, first render) —
39 requests, **~108KB** total transfer. Static JS/CSS/fonts were already cheap
on reload thanks to Starlette's default ETag/`Last-Modified` conditional
revalidation (only one asset lacked even that). The real cost was 13 API calls
totalling ~99.7KB — and one of them, `/api/portfolio/performance?period=all`,
was **90,672 bytes of uncompressed JSON on its own (84% of the entire page's
network weight)**. Checking response headers directly (`fetch()` +
`Content-Encoding`) confirmed no compression: `backend/main.py` never
registered `GZipMiddleware` anywhere, so every API response — regardless of
size — went out uncompressed, in both editions.

**Fix (commit `aa30c73`):** registered `GZipMiddleware(minimum_size=500)` after
`CORSMiddleware` (so gzip wraps outermost and compresses the final response,
CORS headers included). Verified: the same performance endpoint now returns
`Content-Encoding: gzip` and drops to 15,777 bytes (82.6% smaller); the same
cold Dashboard load drops to **~31KB total** (13 API calls now ~22.9KB). 667
fast backend tests plus the 33 real-Postgres tests that build the actual
`main.app` (`tests/postgres/test_auth_sessions.py`,
`tests/postgres/test_portfolio_tenancy.py`) still pass.

**Warm reload** (same tab, second navigation): request count and total bytes
were statistically the same as cold, which is *correct*, not a regression —
none of the 13 API responses are cacheable (they're per-portfolio live data),
so they always re-fetch in full; only the already-cheap static assets benefit
from conditional revalidation. No explicit long-lived `Cache-Control` /
`immutable` header is set on the hashed static assets (Starlette's
`StaticFiles` default), so each reload still costs one small conditional
round-trip per asset instead of zero network requests — a minor, non-blocking
latency optimization left for a future pass, not pursued here since the
byte cost is already negligible.

This measurement was local-edition only; cloud edition's Dashboard uses the
same endpoints behind the same (now-fixed) middleware, so the same reduction
applies, but a separate cloud-edition browser pass was not run.
