# Public demo release check

Use this checklist before publishing a build that exposes the account-free demo.
The public demo is fixed synthetic data as of 2026-09-18; it must not make a
portfolio, market-data, authentication, or analytics request.

## Automated release gate

Run from `frontend` and require all commands to exit successfully:

```powershell
npm test
npm run test:cloud
npm run audit:readability
npm run build
npm run build:cloud
```

For the cloud build, confirm the emitted assets keep the two route boundaries
separate: `DemoBootstrap-*.js` for `/demo` and `TrackerBootstrap-*.js` for the
authenticated tracker. `StockDetail-*.js` must remain outside the demo route
dependency chain. Record the exact filenames and test totals in the release
handoff.

## Route and browser checks

In an anonymous browser session, test each route at 390x844, 768x1024,
1024x768, and 1440x900:

- `/demo`
- `/demo/allocation`
- `/demo/analytics`
- `/demo/dividends`
- `/demo/stock/VUAA`, `/demo/stock/MSFT`, `/demo/stock/JPM`,
  `/demo/stock/JNJ`, `/demo/stock/XOM`, `/demo/stock/PG`,
  `/demo/stock/AMZN`, `/demo/stock/CAT`, `/demo/stock/NEE`, and
  `/demo/stock/PLD`

For every route, verify the synthetic-data and as-of disclosure, a visible
Create account CTA, readable signed values, and no page-level horizontal
overflow. Keyboard-tab through navigation and the CTA, including the visible
focus state. Check an unknown demo path has a useful not-found recovery path
back to the demo.

Open the browser network and console panels while walking the routes. Allow
only static application assets. There must be no `/api`, Firebase, Yahoo,
live-market-data, portfolio, mutation, or telemetry request, and no console
errors or unhandled promise rejections. Confirm source maps do not expose
unexpected sources in the production deployment.

Repeat the representative `/demo` and one stock route in Premium, Classic
light, and Classic dark visual modes. The public demo must remain read-only:
no transaction, alert, note, import, edit, delete, AI, watchlist, settings,
screener, tax report, or options control may be visible.

## Handoff record

Record the release date, commit, browser/version, tested viewports and modes,
test totals, emitted `DemoBootstrap-*` and `TrackerBootstrap-*` filenames,
and the console/network result. Attach screenshots or HAR evidence outside the
repository when required by the release process.

## Verified in this worktree (2026-09-19)

- Local edition: 543 tests passed and 1 cloud-only isolation test skipped.
  Cloud edition: 544 tests passed. The readability audit reported 0
  violations, and both production builds completed.
- Cloud build boundary: `DemoBootstrap-BLDMxFjk.js` (17,793 bytes) and
  `TrackerBootstrap-CQmw4vWE.js` (158,042 bytes) were emitted as separate
  chunks. `StockDetail-_h_NG8Wr.js` (93,111 bytes) remains separate.
- An anonymous local cloud-edition browser check covered all valid demo routes
  plus an unknown route at 390x844. It covered `/demo` and `/demo/stock/MSFT`
  at 768x1024, 1024x768, and 1440x900. Every loaded route showed the required
  disclosure and CTA; no page-level horizontal overflow or console error was
  observed, keyboard tabbing reached demo navigation, and the unknown route
  offered recovery. Loaded stock-route assets contained no tracker, API,
  Firebase, Yahoo, or `StockDetail` module.
- No production `.map` files were emitted by the inspected cloud build.
