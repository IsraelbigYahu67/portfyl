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
- Browser currency-change cancellation and forced unavailable-route-chunk recovery still require explicit runtime evidence. Currency cancellation and route recovery have automated coverage; they are not claimed as completed browser checks here.
- Repeat production-built cold/warm network measurements for the complete authenticated shell before final release; development request allowlists and the static bundle gate do not replace that measurement.
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

**Browser verification of these four fixes is incomplete**, blocked by an
environment issue unrelated to the code changes: a disposable PostgreSQL QA
database (`docker-compose.postgres-test.yml`, port 55441) and local-edition
dev servers (backend :8010, frontend :5183, `VITE_API_PROXY_TARGET` pointed at
the QA backend) were stood up correctly, and the reused test container's leftover
data — a real user record tied to the repository owner's actual e-mail from the
prior session — was found and wiped (`down -v`, fresh `alembic upgrade head`)
before further use, since the working agreement for this QA pass was a throwaway
account, not the owner's real identity. A throwaway e-mail was beta-invited via
`manage_beta.py invite`. Both an automated registration attempt and the repository
owner's own manual login attempt against this same local setup then failed
identically with Firebase's `auth/invalid-api-key`, confirmed via direct
`registerWithEmailPassword()` invocation in the page console (not a network-capture
gap — no request to any `google*` origin was ever made). This reproduced for the
owner too, so it is not an artifact of automation. The lazy-loaded Firebase SDK
fix's own mechanism was still confirmed working before this blocker: `firebase_app`/
`firebase_auth` chunks load only on first auth action, not at page load (verified via
`read_network_requests`), and the call reached the SDK with correctly formed
arguments. Root cause of `auth/invalid-api-key` was not diagnosed further — it needs
Google Cloud/Firebase console access (API key validity/restrictions) that this
session did not have. The scope-cleanup, a11y-label, and native-currency fixes
remain unverified in a live browser pending that Firebase access; their unit-test
coverage above is the only current evidence for them.

Cleanup: the QA backend/frontend processes were force-stopped and the disposable
PostgreSQL container was brought down (`docker compose down`, no `-v`) after the
above. No production `.env`/Neon database was used at any point.
