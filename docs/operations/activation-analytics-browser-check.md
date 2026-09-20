# Activation analytics browser check

Manual verification companion to
`docs/operations/posthog-activation-analytics.md` §6 (live-debugger
checklist). Automated suites (Vitest, pytest, both production builds) prove
the consent gate, event contract, and instrumentation wiring are *correct
code*; they run against jsdom, not a real browser, and cannot see actual
network requests, real `localStorage`/cookie writes, or cross-viewport
layout. This checklist is what closes that gap before the two
`VITE_POSTHOG_*` build variables are ever set in a real deployment (see the
production blocker in the runbook).

## Viewports and appearances

Same matrix as `docs/operations/readability-browser-check.md`: 390×844,
768×1024, 1024×768, 1440×900, each in Premium / Classic light / Classic
dark where the page in question is themeable.

## Pages in scope

Landing (`/`), all demo routes (`/demo`, `/demo/allocation`,
`/demo/analytics`, `/demo/dividends`, `/demo/stock/:ticker`), Register
(direct and `?source=demo`), Onboarding, Import, Dashboard, Settings
(Connections and Data & Privacy sections), and logout.

## Per-page checks

For every page in scope:

- [ ] **Pending consent, no request.** With the consent banner untouched,
      the Network panel shows zero requests to `eu.i.posthog.com` on load
      or on any interaction that would otherwise capture an event.
- [ ] **Rejected consent, cookieless events only.** After clicking Reject,
      `localStorage` contains no PostHog keys and no
      `portfyl_captured_once:*` entries; `document.cookie` contains only
      `portfyl_analytics_consent=rejected` (plus Portfyl's own session/CSRF
      cookies) — no PostHog cookie.
- [ ] **Accepted consent, first-party persistence.** After clicking Accept,
      a PostHog identity key appears in `localStorage`, and expected
      `portfyl_captured_once:*` keys appear for any once-per-session event
      already fired on that page.
- [ ] **No forbidden data in any request payload.** Inspect the request
      body of each `/e/` (capture) call in the Network panel; diff its
      `event`/`properties` against
      `docs/operations/posthog-activation-analytics.md` §4, and confirm none
      of the forbidden fields listed there appear anywhere in the payload.
- [ ] **Blocked PostHog does not change UI behavior.** With
      `eu.i.posthog.com` blocked at the network level, every button,
      navigation, and form on the page behaves identically to the unblocked
      case — no error state, no disabled control, no console error thrown
      from application code (a blocked/failed fetch inside the PostHog SDK
      itself is expected and fine).

## Recording results

Note the commit/build hash, date, browser/OS, and any deviations (with a
linked follow-up) here for the release under review.

### 2026-09-19 — worktree `worktree-demo-activation-readability`, commit range HEAD~2..HEAD (Tasks 5–7)

**What was verified in this session, with real command output:**

- `npx vitest run --mode edition-local` / `--mode edition-cloud`: full
  frontend suite green in both editions (651/651, 1 skipped in local only —
  see the Task 6 checkpoint commit for the exact count) after Tasks 5–7's
  changes, including the consent/identify/reset/workspace-transition
  behavior in `AuthProvider.test.jsx`, the signup funnel in
  `AuthPages.test.jsx`, and the full activation funnel in
  `useRegisteredActivation.test.jsx`/`activationState.test.js`.
- `npm run build` / `npm run build:cloud`: both editions build cleanly.
- `npm run audit:readability`: 0 violations.
- `python -m pytest tests/ -v --ignore=tests/postgres`: 685/685 passing,
  including the new `test_security_headers.py` (CSP exact-match, HTML-only
  scoping, pre-existing-header replacement, EU-only PostHog host allow-list,
  no wildcard script/connect sources).
- Source-level review of every `capture()`/`identify()` call site added in
  Tasks 3–6 confirmed each passes only allow-listed properties matching
  `eventContract.js`'s schema for that event (this is also mechanically
  enforced at runtime by `sanitizeEvent()`, which drops unknown properties
  and, in dev/test mode, throws on an unknown event name or property).

**What could not be verified in this session, and why:**

- **The manual per-page browser matrix above (network/storage panel
  inspection across viewports/appearances).** This session's Browser pane
  tool previews the shared main checkout, not this git worktree, and
  writing a worktree-scoped dev-server launch config outside the worktree
  is blocked by this session's isolation guard. There is no way from this
  session to preview *this worktree's* frontend build in a real browser.
  A human operator (or a session running directly in this worktree's
  checkout, e.g. after merge) must complete this matrix with `start.bat`
  and a real browser before the production blocker in the runbook is
  lifted.
- **PostHog live-debugger verification (runbook §6, all 9 items).** No live
  PostHog Cloud EU project exists yet — §1 of the runbook (project setup)
  is itself still unactioned, and `VITE_POSTHOG_KEY`/`VITE_POSTHOG_HOST` are
  correctly unset everywhere. Every non-dev/non-test build therefore uses
  the no-op adapter (`defaultAdapterFactory` in `AnalyticsProvider.jsx`),
  so there is nothing to observe in a live debugger yet by design.
- **Firebase-authenticated flows (Register → verify → Onboarding → Import →
  Dashboard → Settings → logout).** These need a real Firebase test account
  and a running backend against a migrated PostgreSQL database; no
  `DATABASE_URL` is configured and no Postgres instance is reachable in this
  session (Docker Desktop is not running here).
- **`python -m pytest tests/postgres/ -v`.** Same blocker — no disposable
  `TEST_DATABASE_URL` / Docker Desktop available in this session. Must be
  run before this work is considered release-ready; see
  `backend/tests/postgres/conftest.py` for the setup requirement and
  `deploy/docker-compose.postgres-test.yml`.

**Conclusion:** code-level correctness (automated suites, both builds, CSP
unit tests, event-contract enforcement) is fully green. Real-browser manual
verification and the PostgreSQL integration suite remain outstanding and
are not claimed as done here — do not treat this session's work as
release-ready until a follow-up session with real preview/DB/PostHog access
completes the items above.
