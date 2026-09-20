# UX-08 Assistant Privacy and Performance — Verification Record

## Latest continuation — 2026-09-16 (OPEN)

This section is the current continuation status; the earlier implementation-session
record below is retained as historical evidence. Baseline HEAD is `88a2219` on
`codex/ux-08-assistant-performance`, in
`C:/Users/tomzo/claude/ptf/portfyl/.claude/worktrees/ux-08-closeout`. Main was not
changed. A targeted correction wave is in progress; baseline results below do not
automatically certify its working-tree changes.

### Fresh baseline gates

| Command (from the phase worktree) | Exit | Actual result |
| --- | ---: | --- |
| `cd frontend; npm.cmd ci` | 0 | Lockfile dependencies installed |
| `cd frontend; node --test scripts/measure-initial-bundle.test.mjs` | 0 | 2 passed |
| `cd backend; <main-checkout>/backend/.venv/Scripts/python.exe -m pytest tests/ -v --ignore=tests/postgres` | 0 | 666 passed; 111 warnings; 25.77 s |
| `cd frontend; npm.cmd test -- --maxWorkers=1` | 0 | 81 files / 382 passed; 170.84 s |
| `cd frontend; npm.cmd run test:cloud -- --maxWorkers=1` | 0 | 81 files / 382 passed; 120.46 s |
| `cd frontend; npm.cmd run build -- --manifest` | 0 | Local production build |
| `cd frontend; npm.cmd run build:cloud -- --manifest` | 0 | Cloud production build |
| `docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait` (main checkout compose project) | 0 | Disposable PostgreSQL healthy |
| `cd backend; <main-checkout>/backend/.venv/Scripts/python.exe -m pytest tests/postgres/ -q` | 0 | 334 passed; 10 warnings; 78.43 s |

Only the disposable `portfyl_test` database on `localhost:55441` was used. The
integration fixture recreated and subsequently downgraded its disposable schema.
`alembic upgrade head` then succeeded on that same test database for interactive QA.
The existing `.env` points at remote Neon and was **not** used for QA. No production
data, database, credentials, or model-provider calls were used. Background broker,
alert, and dividend pollers were disabled on the QA server.

Cloud build manifest exclusion passed: no TaxReport/Screener entry or asset; local
contains both. Frontend negative-provider tests emitted their expected useAuth
diagnostics; backend warnings remain existing deprecation/SQLAlchemy warnings.

### Performance metric correction

The static HTML-entry metric required by the implementation plan remains a useful
secondary measurement, but does not supersede the original design specification
section 4.3 requirement for the authenticated shell **plus its initial route**.
Both metrics are retained; a static-entry PASS alone is not a program performance
PASS.

| Edition | Static entry JS/CSS gzip (B) | Static entry total | Recorded Plan-7 static baseline | Static reduction | Authenticated Dashboard union JS/CSS gzip | Union total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| local | 47,470 / 9,475 | 56,945 | 87,246 | 34.730532% | 331,320 / 14,655 | 345,975 |
| cloud | 47,604 / 9,475 | 57,079 | 95,917 | 40.490320% | 332,089 / 14,655 | 346,744 |

Authenticated union method: deduplicate the asset sets from `collectInitialAssets`
for `index.html`, the manifest's actual TrackerBootstrap root, and
`src/pages/Dashboard.jsx`, including every recursive static JS/CSS dependency; gzip
each unique file at level 9. Fonts/images/maps remain excluded. These baseline union
totals exceed 70% of the historical approximately 372 KB under either KB or KiB
interpretation. A freshly measured Plan-7 **union** baseline has not been established.
No authenticated-startup 30% pass is claimed at this point. Eager Firebase SDK and
StockDetail barrel edges are being corrected and will be remeasured.

### Interactive QA completed so far

Available browser runtime was initialized successfully in this continuation. The
user signed in manually; no password was read or submitted by the agent. The built-in
synthetic demo portfolio was activated through first-run onboarding. All checks used
local backend `8001` and local frontend `5174`; cloud frontend `5175` used the same
**local-edition** QA backend, so its results certify frontend behavior only, not a
production/cloud-backend walkthrough.

At exact CSS viewports **390×844, 768×1024, 1024×768, and 1440×900**:

- Login/Register/Forgot Password: rendered, associated e-mail/password labels and
  no viewport horizontal overflow. Registration keyboard e-mail → password checked.
  No registration or reset e-mail was submitted.
- First-run onboarding: four start options visible without viewport overflow;
  synthetic sample activation completed.
- Local route layout smoke: Dashboard, Allocation, Transactions, Watchlists, Import,
  Dividends, Analytics, Search, Assistant, Settings, Screener, Tax Report.
- Stock/AAPL: all five URL tabs selected correctly and sampled without viewport
  overflow; tab back/forward and reload retained selection.
- Settings: all four URL sections selected and sampled without viewport overflow;
  section back/forward retained URL. Initial reload observation was still loading,
  so it is not a complete section-reload stability pass.
- Shared cloud-frontend routes: 40 layout samples, no viewport overflow or alert;
  Screener/Tax Report links absent and direct routes redirected to Dashboard.

Mobile drawer initial focus, Shift+Tab wrap, Escape close, and focus restoration
were verified. SPA navigation to Dashboard focused its h1. Both browser tabs'
captured warning/error console logs were empty before intentional outage testing.
Some route samples remained loading: these are layout **smoke checks**, not full
happy/loading/empty/error acceptance for every surface.

A controlled outage stopped only this turn's QA backend. Transactions displayed
the real error alert and Retry control at 1440×900. Hot reload during the outage
temporarily cleared frontend account state; after backend restart and page reload,
the existing cookie session and AAPL transaction data recovered at 390×844. Explicit
Retry activation and the other error-state viewport cells remain unverified.

Server-side request evidence for an authenticated Dashboard reload contained account,
capabilities, FX, portfolios, summary/holdings/default performance and Dashboard's
visible widgets/local tax signal. It contained no per-holding fundamentals/history
sweep or Transactions/Watchlists/Settings queue. This is server request-log evidence,
not DevTools timing or a cold/warm compressed-transfer measurement.

### Findings and remaining gates

The reviewed correction wave addresses orphaned intent requests after originating
links unmount, native average-cost currency, the Stock route's missing h1, and unnamed
Assistant connection/Transactions filter controls, alongside startup import edges.
Tests, measurements, review and browser rechecks for those edits are pending.

Assistant defaults visibly to No portfolio data. This QA workspace has no configured
DeepSeek key, so chat/consent/provider-response/browser-wire scenarios were not run.
No live model request or portfolio sharing occurred. Cloud Plans, cloud backend gates,
full four-viewport async/error/keyboard/network matrix, exact 150 ms browser timing,
cold/warm network captures, required remote PR CI and formal predecessor delivery
remain open. Read-only GitHub CLI checks found no UX phase PR or UX-08 CI run; the
workflow triggers branch CI through PRs (push trigger covers main only). No PR, push,
merge, security bypass, or deployment was performed.

Date: 2026-09-16
Branch: `codex/ux-08-assistant-performance`
Implementation/CI head: `0cc337c`
Plan-7 baseline: `426aef9`
Workspace: `C:\Users\tomzo\claude\portfyl`
Node: `22.16.0`; Vite: `6.4.3`

## Status

**2026-09-17 follow-up:** browser/runtime evidence, six resulting fixes, final bundle measurements, and draft PR [#7](https://github.com/IsraelbigYahu67/portfyl/pull/7) are recorded in [the browser QA follow-up](ux-08-browser-closeout-2026-09-17.md). Remote CI now exists. The phase remains OPEN for the explicitly recorded remaining criteria and delivery review. The sections below preserve the earlier verification snapshot; their statements that browser QA, PR creation and remote CI are pending are historical, not current status.

Implementation, all local automated gates, and both measured bundle targets pass. The phase remains **OPEN** until the authenticated four-viewport browser/network matrix, formal predecessor delivery, and required remote CI are complete. No phase or integration PR was merged.

The continuation started from a clean Plan-7 checkout. A local integration ref, `codex/portfyl-ux-overhaul`, was created at that HEAD; the phase branch starts there. `git merge-base --is-ancestor codex/ux-07-product-flows HEAD` passes. This establishes local ancestry; it does not claim a reviewed predecessor PR merged. The read-only remote check returned only `main` (`e252933c3562f9f634e964b9476204c6aa89e31f`). Remote integration/phase delivery is pending.

## Automated gates

Commands run from the repository root unless a directory is stated.

| Command | Exit | Result |
| --- | ---: | --- |
| `node --test frontend/scripts/measure-initial-bundle.test.mjs` | 0 | 2 tests |
| `cd backend; .\.venv\Scripts\python.exe -m pytest tests/ -q --ignore=tests/postgres` | 0 | 666 tests, 38.38 s; 111 existing warnings |
| `docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait` | 0 | PostgreSQL test service Healthy |
| `cd backend; .\.venv\Scripts\python.exe -m pytest tests/postgres/ -q` | 0 | 334 tests; 10 existing warnings; reported 3132.58 s |
| `cd frontend; npm.cmd test -- --reporter=dot --maxWorkers=1` | 0 | 81 files / 382 tests, 226.69 s |
| `cd frontend; npm.cmd run test:cloud -- --reporter=dot --maxWorkers=1` | 0 | 81 files / 382 tests, 226.69 s |
| `cd frontend; npm.cmd run build -- --manifest` | 0 | Local production build, 30.92 s |
| `cd frontend; npm.cmd run build:cloud -- --manifest` | 0 | Cloud production build |
| `git diff --check` / `git status --short` | 0 | No whitespace errors; clean implementation checkout |
| `docker compose -f deploy/docker-compose.postgres-test.yml stop` | 0 | Restored the test service's initial stopped state |

Only the disposable repository `portfyl_test` PostgreSQL database on port 55441 was addressed. No container, image, or volume was deleted. No production database was used.

Focused checks also passed: Assistant/dialog/research, 11 local tests; focused 14-file cloud gate, 61 tests; ticker/startup/research/Stock/Watchlists/format, 56 tests; follow-up consent focus/ticker/mobile, 15 tests; route recovery/Assistant/routing/edition/Root, 24 tests; final backend Assistant contracts, 9 tests.

Initial full frontend runs failed because Vitest collected the standalone Node test and an AllocationBarList worker timed out on startup. They passed 375 individual tests but were not green gates. Vitest now includes only `src/**/*.test.{js,jsx}`; the standalone Node suite is separately executed and wired into both frontend CI matrix editions. The final full passes supersede those failures. Initial frontend wall times (~3247 s, including ~1057 s imports) and PostgreSQL wall time are retained as reported, without treating them as performance benchmarks.

## Bundle method and acceptance

Baselines were captured before backend/UI/routing behavior changed. The same collector follows `index.html` and recursive static `imports`, deduplicates JS/CSS files, and compresses each using Node `gzipSync(..., { level: 9 })`. Dynamic imports, font binaries, images, and source maps are explicitly excluded.

Baseline and final commands use the same method:

```powershell
cd frontend
npm.cmd run build -- --manifest
node scripts/measure-initial-bundle.mjs dist
npm.cmd run build:cloud -- --manifest
node scripts/measure-initial-bundle.mjs dist
```

`npm run measure:bundle` exposes the same CLI. Baseline/final JSON, manifests, and build/test logs are under `%TEMP%/portfyl-ux08-*`; no generated bundle, manifest, baseline JSON, screenshot, or runtime credential is committed.

| Edition | Baseline JS gzip | Baseline CSS gzip | Baseline total | Final JS gzip | Final CSS gzip | Final total | Saved bytes | Reduction | Hard maximum | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| local | 69789 | 17457 | 87246 | 47470 | 9475 | 56945 | 30301 | 34.730532% | 61072 | PASS |
| cloud | 78460 | 17457 | 95917 | 47609 | 9475 | 57084 | 38833 | 40.486045% | 67141 | PASS |

All values except percentages are bytes. Each hard maximum is `floor(baseline * 0.70)`. Reductions are `(87246 - 56945) / 87246 * 100` and `(95917 - 57084) / 95917 * 100`; neither target was rounded into acceptance.

The specification's historical approximately 372 KB gzip figure is a reference, not this gate's denominator. Plan 7 already loaded the whole App dynamically, making its static HTML entry smaller than that historical shell figure. Final HTML entries are approximately 55.6/55.7 KiB gzip. They do **not** represent the complete authenticated Dashboard network transfer.

For transparency, the final cloud tracker bootstrap and all its static dependencies measure **160032 bytes gzip**, and the cloud Dashboard plus its shell/static dependencies measure **346909 bytes gzip**, using the same collector and level 9. Route chunks add to the HTML entry; font binaries remain excluded. These are build-graph measurements, not cold/warm browser observations. No 30% reduction in the complete Dashboard payload is claimed.

The initial graph became smaller by moving private router/query providers into TrackerBootstrap, making all authenticated routes lazy, keeping Welcome conditional/lazy in cloud, and loading font definitions with their tracker/public-page consumers. No static imports were merely renamed.

## Manifest and edition evidence

Both manifests mark Dashboard, Allocation, Transactions, Import, Dividends, Analytics, Search, Stock, Watchlists, Assistant, Settings, and Onboarding as dynamic page entries. Local additionally contains dynamic Screener/TaxReport; cloud contains dynamic Pricing/Welcome. Cloud manifest assertions confirm **no Screener or TaxReport entry**. Local Welcome is absent.

Edition loaders remain in their build-time manifests and share their stable preload function with navigation. Shared TickerLink was extracted to `components/TickerLink.jsx` and re-exported by the existing StockDetail barrel so Search/WatchlistCard do not import charts merely to render an anchor.

## Assistant privacy evidence

- Omitted mode validates as `none`; unknown modes fail validation. The snapshot builder is never called for `none`.
- Explicit summary builds once for the injected portfolio. A 30-position fixture plus another portfolio and a forged foreign-workspace row proves the existing 25-position/15-recent-trade caps and both scope predicates.
- Provider messages contain one system prompt and at most 20 allowed history messages. Summary data appears only in the server-to-provider system message. Responses contain exactly reply, usage, model, provider, context_mode, context_as_of; none has null context time and summary has timezone-aware UTC ISO time.
- BYOK does not reserve hosted quota. Four hosted cases prove success finalizes one unit and provider failure releases it for both modes.
- New conversations visibly default to No portfolio data. First summary send pauses before the API call. Explicit share reuses an in-memory conversation grant; New conversation clears messages, provenance, pending text, mode, and grant.
- Ask without portfolio data, Escape, and backdrop each submit exactly once with none. Dialog copy names DeepSeek/configured model, all data categories including dividend income, transaction-derived values, and potential delays. Tab/Shift+Tab are trapped and Send message receives focus after dismissal.
- Response details show provider/model, returned sharing mode, and formatted context time only when present. History serialization strips provenance to role/content. Consent has no persistence.

Request bodies verified by mocks, not browser captures:

```json
{"messages":[{"role":"user","content":"Question"}],"context_mode":"none"}
{"messages":[{"role":"user","content":"Question"}],"context_mode":"portfolio_summary"}
```

## Startup and intent evidence

- AutoLoad and its holdings/sidebar sweep are deleted. Startup imports only summary, holdings, performance. Exact keys: summary/currency, holdings/currency, performance/currency/All; request period is all. Portfolio metadata remains owned by PortfolioProvider.
- Unready/missing portfolios make no warm. Currency changes use new keys. A regression exercises PortfolioProvider's existing full cache removal before activating a switched portfolio, followed by new warms.
- Desktop/mobile hover/focus invokes only the visible destination's stable loader; rejected preloads are caught. RouteBoundary provides a reload action for foreground chunk failure. Route focus waits for a heading arriving after fallback.
- Ticker intent loads Stock immediately once, coalesces hover/focus, makes zero data requests at 149 ms, and at 150 ms warms exactly stock-view/TICKER/overview and history/TICKER/1y with five-minute stale times.
- Plan 7 changed Overview to `fetchStockView(ticker, "overview")`. Phase 8 preserves that bounded endpoint/key instead of reviving the older full-fundamentals interface printed in Task 6.
- Leave/blur, unmount, ticker, portfolio, and currency changes cancel pending timers. Scope changes cancel Axios-signalled requests and remove incompatible tagged queries without observers; unrelated and foreground queries remain. Completed tagged entries are conservatively removed even though these market endpoints are portfolio-agnostic.
- Real encoded uppercase anchors, arbitrary children/props, click propagation handling, and new-tab targets remain. Search and the extracted WatchlistCard use the shared link.

These are automated checks. DevTools startup allowlist, cold/warm request captures, exact browser timing, and console evidence remain pending.

## Four-viewport browser matrix — OPEN

Read skill: `C:/Users/tomzo/.codex/plugins/cache/openai-bundled/computer-use/26.903.61454/skills/computer-use/SKILL.md`. It requires importing `@oai/sky` inside `node_repl`. Available tool metadata exposes no node_repl/Playwright/browser runtime, so the required initialization cannot run. No custom helper/protocol client was built.

Phase servers on 8001/5174/5175 were not started without an authenticated browser runtime to exercise them. Every cell below is PENDING, not a pass.

| Route / flow | Edition | 390×844 | 768×1024 | 1024×768 | 1440×900 |
| --- | --- | --- | --- | --- | --- |
| Login/Register/Verify Email/Forgot Password | both | PENDING | PENDING | PENDING | PENDING |
| First-run Onboarding | both | PENDING | PENDING | PENDING | PENDING |
| Dashboard | both | PENDING | PENDING | PENDING | PENDING |
| Allocation | both | PENDING | PENDING | PENDING | PENDING |
| Transactions paging/filtering | both | PENDING | PENDING | PENDING | PENDING |
| Import preview/duplicates/undo | both | PENDING | PENDING | PENDING | PENDING |
| Dividends | both | PENDING | PENDING | PENDING | PENDING |
| Analytics | both | PENDING | PENDING | PENDING | PENDING |
| Search | both | PENDING | PENDING | PENDING | PENDING |
| Stock: all five URL tabs | both | PENDING | PENDING | PENDING | PENDING |
| Watchlists filters/sort/alerts | both | PENDING | PENDING | PENDING | PENDING |
| Assistant consent/none/summary/reset/BYOK/hosted | both | PENDING | PENDING | PENDING | PENDING |
| Settings: all four URL sections | both | PENDING | PENDING | PENDING | PENDING |
| Export / account deletion | both | PENDING | PENDING | PENDING | PENDING |
| Screener jobs/progress/cancel/retry | local | PENDING | PENDING | PENDING | PENDING |
| Tax Report | local | PENDING | PENDING | PENDING | PENDING |
| Plans | cloud | PENDING | PENDING | PENDING | PENDING |
| Unavailable Screener/Tax Report routes/assets | cloud | PENDING | PENDING | PENDING | PENDING |

Every pending surface includes loading, empty, forced error/retry, URL reload/back/forward, keyboard/focus, dialogs/drawers, horizontal overflow, and console/request checks. Assistant browser bodies/provenance, safe dismissal at all viewports, local/hosted configurations, and startup/intent network captures remain mandatory. Phases 4–7 collection, import, and data-deletion browser checks are not waived.

## CI and remaining release criteria

Required workflow: <https://github.com/IsraelbigYahu67/portfyl/actions/workflows/ci.yml>. No phase-specific CI run or PR exists from this local session. Mandatory backend-postgres CI remains required despite the local pass. Standalone bundle tests were added to both frontend CI editions.

Open: browser/network matrix; formal Plan-7/integration remote delivery; phase PR review and remote CI; owner approval before a later main integration. Privacy, consent/reset, lazy edition routes, 150 ms cancellation, AutoLoad removal, and both static-entry bundle targets are implemented and locally tested. Browser observations and remote gates are explicitly unverified.

Existing output remains: React fetchPriority warning in Welcome tests, intentional useAuth-outside-provider errors, and backend datetime/SQLAlchemy deprecations. No schema migration, new component/router library, service worker, consent persistence, or investment recommendation feature was added.

## Asset evidence appendix

### Complete measured initial JS/CSS tables

**local / baseline**

| Asset | Raw bytes | Gzip bytes (level 9) |
| --- | ---: | ---: |
| assets/index-CrpvTMCQ.css | 68356 | 17457 |
| assets/index-DEiRl95Q.js | 214617 | 69789 |

Excluded dynamic entry identifiers: src/App.jsx.

**local / final**

| Asset | Raw bytes | Gzip bytes (level 9) |
| --- | ---: | ---: |
| assets/index-BbHIHu79.js | 146550 | 47470 |
| assets/index-SJuhp3JJ.css | 46394 | 9475 |

Excluded dynamic entry identifiers: _TrackerBootstrap-ByIuDf53.js.

**cloud / baseline**

| Asset | Raw bytes | Gzip bytes (level 9) |
| --- | ---: | ---: |
| assets/index-BjmEQLKD.js | 240019 | 78460 |
| assets/index-CrpvTMCQ.css | 68356 | 17457 |

Excluded dynamic entry identifiers: src/App.jsx.

**cloud / final**

| Asset | Raw bytes | Gzip bytes (level 9) |
| --- | ---: | ---: |
| assets/index-CDHj4zUT.js | 146825 | 47609 |
| assets/index-SJuhp3JJ.css | 46394 | 9475 |

Excluded dynamic entry identifiers: _TrackerBootstrap-D6hAO884.js, src/pages/Welcome.jsx.

Baseline Vite also emitted excluded whole-App assets: local App-Dw-fTp53.js 1204.97 kB / 316.14 kB gzip; cloud App-CySPRuyx.js 1171.63 kB / 309.53 kB gzip; App-ChDF2ngo.css 2.40 kB / 0.58 kB gzip in both. Those are rounded Vite display values, separate from the level-9 initial gate.

### Full final Vite asset displays

Font binaries and dynamic chunks below are explicitly excluded from initial totals. Vite display values are rounded and do not replace level-9 measurements.

**local**

```text
dist/index.html                                                        1.04 kB │ gzip:   0.57 kB
dist/assets/jetbrains-mono-vietnamese-wght-normal-Bt-aOZkq.woff2       7.50 kB
dist/assets/plus-jakarta-sans-vietnamese-wght-normal-qRpaaN48.woff2    8.35 kB
dist/assets/jetbrains-mono-greek-wght-normal-Bw9x6K1M.woff2            9.00 kB
dist/assets/inter-vietnamese-wght-normal-CBcvBZtf.woff2               10.25 kB
dist/assets/inter-greek-ext-wght-normal-DlzME5K_.woff2                11.23 kB
dist/assets/jetbrains-mono-cyrillic-wght-normal-D73BlboJ.woff2        12.11 kB
dist/assets/jetbrains-mono-latin-ext-wght-normal-DBQx-q_a.woff2       15.20 kB
dist/.vite/manifest.json                                              16.13 kB │ gzip:   1.91 kB
dist/assets/inter-cyrillic-wght-normal-DqGufNeO.woff2                 18.75 kB
dist/assets/inter-greek-wght-normal-CkhJZR-_.woff2                    19.00 kB
dist/assets/plus-jakarta-sans-latin-ext-wght-normal-DmpS2jIq.woff2    21.73 kB
dist/assets/inter-cyrillic-ext-wght-normal-BOeWTOD4.woff2             25.96 kB
dist/assets/plus-jakarta-sans-latin-wght-normal-eXO_dkmS.woff2        27.35 kB
dist/assets/jetbrains-mono-latin-wght-normal-B9CIFXIH.woff2           40.40 kB
dist/assets/inter-latin-wght-normal-Dx4kXJAl.woff2                    48.26 kB
dist/assets/inter-latin-ext-wght-normal-DO1Apj_S.woff2                85.07 kB
dist/assets/Dashboard-ChDF2ngo.css                                     2.40 kB │ gzip:   0.58 kB
dist/assets/TrackerBootstrap-CMnTSQoN.css                             10.29 kB │ gzip:   4.61 kB
dist/assets/index-SJuhp3JJ.css                                        46.39 kB │ gzip:   9.52 kB
dist/assets/ChartSummary-DG0bLH2N.js                                   0.35 kB │ gzip:   0.25 kB
dist/assets/rotate-ccw-B8orZvVV.js                                     0.38 kB │ gzip:   0.29 kB
dist/assets/download-Zd5u4ExY.js                                       0.44 kB │ gzip:   0.33 kB
dist/assets/send-Ms0Ay9DL.js                                           0.47 kB │ gzip:   0.34 kB
dist/assets/trending-up-O7gLzYE-.js                                    0.71 kB │ gzip:   0.34 kB
dist/assets/SegmentedControl-BnFDR06k.js                               0.86 kB │ gzip:   0.51 kB
dist/assets/index-Da1h-Jmr.js                                          0.94 kB │ gzip:   0.57 kB
dist/assets/eye-DDu60aWo.js                                            0.99 kB │ gzip:   0.46 kB
dist/assets/Pagination-oWZEnErj.js                                     1.33 kB │ gzip:   0.66 kB
dist/assets/TickerLink-Cm_VluQf.js                                     1.86 kB │ gzip:   0.95 kB
dist/assets/AsyncSection-BPZmJHg7.js                                   1.98 kB │ gzip:   1.04 kB
dist/assets/format-fXt-eXjU.js                                         2.25 kB │ gzip:   0.89 kB
dist/assets/useStockReportConfig-Ce1ywvBK.js                           2.55 kB │ gzip:   1.05 kB
dist/assets/Search-BIEVgZjI.js                                         3.02 kB │ gzip:   1.43 kB
dist/assets/Onboarding-nbxkYc02.js                                     4.17 kB │ gzip:   1.84 kB
dist/assets/MetricCard-CPQn_-S0.js                                     4.49 kB │ gzip:   2.01 kB
dist/assets/Assistant-D_64UU2w.js                                     11.89 kB │ gzip:   4.19 kB
dist/assets/Transactions-vpaC7rtw.js                                  12.19 kB │ gzip:   3.89 kB
dist/assets/Dividends-C5EEGA8v.js                                     12.94 kB │ gzip:   3.79 kB
dist/assets/Allocation-C44lzdbU.js                                    13.27 kB │ gzip:   4.09 kB
dist/assets/Stock-9SMAdqxB.js                                         13.51 kB │ gzip:   4.83 kB
dist/assets/Screener-C5DI1F_b.js                                      17.24 kB │ gzip:   4.77 kB
dist/assets/Watchlists-BWGqE1uk.js                                    18.60 kB │ gzip:   5.62 kB
dist/assets/TaxReport-CE69iAHU.js                                     18.73 kB │ gzip:   4.90 kB
dist/assets/Analytics-Dg-JUGKN.js                                     25.46 kB │ gzip:   7.80 kB
dist/assets/Settings-7kYqnd5k.js                                      35.25 kB │ gzip:   9.26 kB
dist/assets/Import-CX-w280n.js                                        74.06 kB │ gzip:  20.88 kB
dist/assets/Dashboard-CQeVobb-.js                                    102.15 kB │ gzip:  32.07 kB
dist/assets/StockDetail-CodCQLS_.js                                  144.19 kB │ gzip:  37.64 kB
dist/assets/index-BbHIHu79.js                                        146.55 kB │ gzip:  47.54 kB
dist/assets/TrackerBootstrap-ByIuDf53.js                             367.28 kB │ gzip:  97.90 kB
dist/assets/chartTheme-CylSouRV.js                                   395.48 kB │ gzip: 108.41 kB
```

**cloud**

```text
dist/index.html                                                        1.04 kB │ gzip:   0.57 kB
dist/assets/jetbrains-mono-vietnamese-wght-normal-Bt-aOZkq.woff2       7.50 kB
dist/assets/plus-jakarta-sans-vietnamese-wght-normal-qRpaaN48.woff2    8.35 kB
dist/assets/jetbrains-mono-greek-wght-normal-Bw9x6K1M.woff2            9.00 kB
dist/assets/inter-vietnamese-wght-normal-CBcvBZtf.woff2               10.25 kB
dist/assets/inter-greek-ext-wght-normal-DlzME5K_.woff2                11.23 kB
dist/assets/jetbrains-mono-cyrillic-wght-normal-D73BlboJ.woff2        12.11 kB
dist/assets/jetbrains-mono-latin-ext-wght-normal-DBQx-q_a.woff2       15.20 kB
dist/.vite/manifest.json                                              15.99 kB │ gzip:   1.95 kB
dist/assets/inter-cyrillic-wght-normal-DqGufNeO.woff2                 18.75 kB
dist/assets/inter-greek-wght-normal-CkhJZR-_.woff2                    19.00 kB
dist/assets/plus-jakarta-sans-latin-ext-wght-normal-DmpS2jIq.woff2    21.73 kB
dist/assets/inter-cyrillic-ext-wght-normal-BOeWTOD4.woff2             25.96 kB
dist/assets/plus-jakarta-sans-latin-wght-normal-eXO_dkmS.woff2        27.35 kB
dist/assets/jetbrains-mono-latin-wght-normal-B9CIFXIH.woff2           40.40 kB
dist/assets/inter-latin-wght-normal-Dx4kXJAl.woff2                    48.26 kB
dist/assets/inter-latin-ext-wght-normal-DO1Apj_S.woff2                85.07 kB
dist/assets/Dashboard-ChDF2ngo.css                                     2.40 kB │ gzip:   0.58 kB
dist/assets/plus-CMnTSQoN.css                                         10.29 kB │ gzip:   4.61 kB
dist/assets/Welcome-BBSHf9Y3.css                                      12.04 kB │ gzip:   3.24 kB
dist/assets/index-SJuhp3JJ.css                                        46.39 kB │ gzip:   9.52 kB
dist/assets/arrow-up-right-B_QawYkO.js                                 0.33 kB │ gzip:   0.26 kB
dist/assets/ChartSummary-Bj9Xah8z.js                                   0.35 kB │ gzip:   0.25 kB
dist/assets/rotate-ccw-Cr5hzhNk.js                                     0.37 kB │ gzip:   0.29 kB
dist/assets/download-DbdAmTEH.js                                       0.43 kB │ gzip:   0.32 kB
dist/assets/send-CyJtjeQd.js                                           0.46 kB │ gzip:   0.33 kB
dist/assets/trending-up-D6qlnJqJ.js                                    0.70 kB │ gzip:   0.33 kB
dist/assets/SegmentedControl-n5IpCmwg.js                               0.86 kB │ gzip:   0.51 kB
dist/assets/index-zKUrM6ba.js                                          0.94 kB │ gzip:   0.57 kB
dist/assets/eye-I6lvzRYE.js                                            0.97 kB │ gzip:   0.45 kB
dist/assets/Pagination-D6CVo2VV.js                                     1.33 kB │ gzip:   0.66 kB
dist/assets/TickerLink-CzsDY1Vh.js                                     1.86 kB │ gzip:   0.95 kB
dist/assets/AsyncSection-Br6-gyUd.js                                   2.01 kB │ gzip:   1.06 kB
dist/assets/format-fXt-eXjU.js                                         2.25 kB │ gzip:   0.89 kB
dist/assets/useStockReportConfig-XzTHHek_.js                           2.55 kB │ gzip:   1.05 kB
dist/assets/Search-BBWdwuSI.js                                         3.05 kB │ gzip:   1.45 kB
dist/assets/plus-B02DUYJF.js                                           3.64 kB │ gzip:   1.14 kB
dist/assets/Pricing-SmWA0Sj3.js                                        4.17 kB │ gzip:   1.91 kB
dist/assets/Onboarding-BnvK_K7u.js                                     4.20 kB │ gzip:   1.86 kB
dist/assets/Assistant-CkND5IdH.js                                     11.92 kB │ gzip:   4.21 kB
dist/assets/Transactions-yYqAgfuc.js                                  12.22 kB │ gzip:   3.90 kB
dist/assets/Dividends-COf2URCY.js                                     12.98 kB │ gzip:   3.81 kB
dist/assets/Allocation-DV5Dltve.js                                    13.30 kB │ gzip:   4.11 kB
dist/assets/Stock-Bw9TkyCq.js                                         13.54 kB │ gzip:   4.84 kB
dist/assets/Watchlists-D0ATAtLg.js                                    18.63 kB │ gzip:   5.63 kB
dist/assets/Welcome-ovXV2UAs.js                                       21.49 kB │ gzip:   7.80 kB
dist/assets/Analytics-Bo7KPCa8.js                                     25.45 kB │ gzip:   7.79 kB
dist/assets/Settings-DTRMziBZ.js                                      35.28 kB │ gzip:   9.28 kB
dist/assets/Import-BmY42z-q.js                                        74.54 kB │ gzip:  21.13 kB
dist/assets/Dashboard-DPndWiyL.js                                    102.18 kB │ gzip:  32.08 kB
dist/assets/StockDetail-COasEubp.js                                  143.96 kB │ gzip:  37.61 kB
dist/assets/index-CDHj4zUT.js                                        146.83 kB │ gzip:  47.68 kB
dist/assets/TrackerBootstrap-D6hAO884.js                             364.63 kB │ gzip:  97.33 kB
dist/assets/chartTheme-D4GXYxdw.js                                   399.98 kB │ gzip: 110.30 kB
```
