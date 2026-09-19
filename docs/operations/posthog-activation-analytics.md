# PostHog Cloud EU: activation analytics runbook

Last updated: 2026-09-19

This document is the operational runbook for the consent-gated PostHog Cloud
EU integration that measures Portfyl's public-demo and registered-user
activation funnels. It complements
`docs/compliance/data-processing-inventory.md` (the compliance record) with
the concrete setup, allow-list, funnels, and verification steps an operator
needs to actually run this safely.

**Production blocker — read first:** `VITE_POSTHOG_KEY` and
`VITE_POSTHOG_HOST` must **not** be set in any deployed environment
(Cloud Run build args, `.env` files consumed by a production build, or any
CI/CD secret) until the public privacy notice and subprocessor disclosure
covering PostHog Cloud EU has received qualified Czech/EU legal review and
is published. This document does not draft that legal text — do not invent
it here or anywhere else in the implementation. Until the gate is lifted,
`frontend/src/analytics/AnalyticsProvider.jsx`'s `defaultAdapterFactory`
falls back to a no-op adapter in every built (non-dev, non-test) bundle
whenever the key is absent or the host isn't exactly
`https://eu.i.posthog.com`, so no event ever leaves the browser regardless
of what a visitor chooses in the consent banner.

## 1. PostHog project setup

1. Sign up / sign in at <https://posthog.com> and select the **EU Cloud**
   region explicitly at account creation (the region cannot be changed
   afterwards without migrating to a new project).
2. Create exactly **one production project** (e.g. "Portfyl production").
   Do not create a second project for staging/dev — local development and
   the Vitest suite already use an in-memory adapter
   (`createMemoryAdapter()`) and never talk to PostHog at all (see
   `AnalyticsProvider.jsx`'s `defaultAdapterFactory`: `import.meta.env.DEV`
   or `MODE === "test"` always short-circuits to the in-memory adapter).
3. **Do not add a payment method.** This integration is designed to run
   entirely on PostHog's free tier indefinitely; see §2 for the recorded
   free allowance and the desired behavior at the limit.
4. In Project Settings, copy the **project API key** (the public token,
   safe to ship in a client bundle — this is `VITE_POSTHOG_KEY`). Do not
   copy or use a personal/organization API key here.
5. Verify these are **disabled** for the project (Portfyl does not use
   them and must not accidentally start sending data to them):
   - Session replay
   - Surveys
   - Feature flags (beyond whatever ships disabled by default)
   - Exception autocapture
   - Autocapture of clicks/pageviews (the frontend adapter already passes
     `autocapture: false`, `capture_pageview: false`,
     `capture_pageleave: false`, `disable_session_recording: true` — see
     `analyticsClient.js`'s `buildOptions()` — but confirm the project-level
     toggles agree, since a project-level autocapture setting is a second,
     independent layer of protection).
6. Add both production web origins under Project Settings → "Authorized
   URLs": `https://portfyl.com` and `https://app.portfyl.com`.
7. Restrict team membership to the individuals who actually need PostHog
   access (dashboards, live debugger, funnels). Do not grant broad
   organization-level access by default.

## 2. Free tier allowance (recorded at design date, 2026-09-19)

| Resource | Free allowance |
|---|---|
| Analytics events | 1,000,000 / month |
| Projects | 1 |
| Data retention | 1 year |
| Team members | Unlimited |
| Session replays | 5,000 (unused — replay stays disabled) |
| Feature-flag requests | 1,000,000 (unused — flags stay disabled) |
| Exceptions | 100,000 (unused — exception autocapture stays disabled) |
| Surveys | 1,500 (unused — surveys stay disabled) |

Portfyl only ever sends the 12 allow-listed **analytics events** below —
every other free-tier resource category is left completely unused by
design, which is what keeps this sustainably inside the free tier as usage
grows.

**No-card rule and desired quota behavior:** with no payment method on
file, PostHog stops ingesting events once the monthly event allowance is
exhausted and resumes at the next billing cycle. This is the desired
behavior — event ingestion pausing at the free limit must never change
Portfyl's own product behavior (every `capture()` call is fire-and-forget
and already swallows adapter failures; see `AnalyticsProvider.jsx`'s
`.catch(() => {})` on every adapter call). If usage approaches the limit,
that is a signal to review §6 (first-month monitoring), not a reason to add
a card reactively.

## 3. Environment configuration

- `VITE_POSTHOG_KEY` — the project's public API token from §1 step 4.
- `VITE_POSTHOG_HOST` — must be exactly `https://eu.i.posthog.com` (the EU
  ingestion host; `analyticsClient.js` also separately hard-codes
  `ui_host: "https://eu.posthog.com"` for the PostHog UI link the SDK
  builds internally).

Both are **Vite build-time variables**, not backend runtime secrets — they
are compiled into the static frontend bundle by `npm run build:cloud` and
are not read from `backend/`'s environment at any point. See
`deploy/cloudrun.md` for where these are (not yet) wired into the Cloud Run
build, and note there that changing a Cloud Run *service's* runtime
environment variables has **no effect** on these two values, since Vite has
already baked them into the built JS by the time the container runs.

## 4. The 12-event allow-list

The full contract lives in `frontend/src/analytics/eventContract.js`
(frozen; do not modify without updating this document and re-running the
plan-completion gate below). `sanitizeEvent()` rejects any event name not
in this list and drops any property not in that event's own schema — this
allow-list is enforced in code, not just documented convention.

| Event | Properties | Fires when |
|---|---|---|
| `landing_viewed` | `language`, `referrer_class`, `utm_source`, `utm_medium`, `utm_campaign` | The public landing page (`Welcome.jsx`) is viewed, once analytics is ready |
| `demo_started` | `language`, `entry_point` (`landing_hero`\|`landing_closing`\|`direct`) | A visitor enters `/demo/*` |
| `demo_page_viewed` | `demo_page`, `language` | Each distinct demo page/route is viewed (deduped per page) |
| `demo_stock_viewed` | `demo_symbol` (one of the 10 fixture tickers) | A demo stock detail page is viewed |
| `demo_activation_reached` | `activation_path` (`three_pages`\|`stock_after_page`), `distinct_demo_pages` | The demo activation milestone is reached (once per session) |
| `signup_cta_clicked` | `source_surface`, `language` | The registration CTA is clicked from the landing page or demo shell |
| `signup_started` | `source_surface` (`landing_hero`\|`landing_closing`\|`demo`\|`direct`), `language` | The `/register` route mounts |
| `signup_completed` | `source_surface` | Firebase account creation succeeds, before navigating to `/verify-email` |
| `portfolio_created` | `creation_path` (`blank`\|`demo`\|`csv`\|`broker`) | A portfolio is created in Onboarding, after the create call succeeds |
| `portfolio_data_imported` | `source_type` (`demo`\|`csv`\|`broker`) | Data actually lands in a portfolio (demo creation, a committed CSV import, or a broker sync with `total_imported > 0`) |
| `dashboard_first_value_rendered` | `source_type` | The first populated Dashboard render occurs once an import source and a rendered dashboard both exist |
| `user_activation_reached` | `source_type` | Fires immediately after `dashboard_first_value_rendered`, once per user/workspace |

### Forbidden data — never sent, by design

The following must never appear in any event property, in `identify()`, or
anywhere else this integration touches, and every payload should be spot
checked against this list during verification (§5) and monitoring (§6):

- E-mail address, display name, or any other directly identifying string
- Firebase UID (only Portfyl's own opaque `user.id` is ever passed to
  `identify()`, and only as a bare string — see `AuthProvider.jsx`)
- Workspace name or workspace ID (workspace existence gates *when*
  `identify()`/activation events fire, but the ID itself is never a
  property — see `AuthProvider.jsx`'s identify effect and
  `useRegisteredActivation.js`)
- Portfolio ID, holdings, transactions, balances, or any other financial
  figure
- Free-text notes, CSV file contents, or broker credentials
- Raw query-string values beyond the strict allow-listed enums above (e.g.
  `Register.jsx` only ever derives `demo` or `direct` from `?source=`, never
  forwarding the literal query string)

## 5. Identity model

- **Pending** consent: nothing is captured, no adapter is initialized, no
  PostHog request of any kind is made.
- **Rejected** consent: PostHog runs in cookieless mode
  (`cookieless_mode: "on_reject"`, `persistence: "memory"`) — events are
  still sent (for aggregate, anonymous funnel counts) but with no
  persistent client-side identity. `captureOnce()`'s de-duplication for
  rejected sessions lives in an in-memory `Set`, not `localStorage`.
- **Accepted** consent: PostHog persists a first-party
  `localStorage+cookie` identity, and once a user registers and consent is
  accepted, `AuthProvider.jsx` calls `identify(String(user.id))` — Portfyl's
  own opaque user id only.

**Person-level cross-host/date conversion in PostHog (i.e. stitching a
visitor's landing-page session to their later signup and activation) is
only valid for accepted-consent traffic.** Rejected/cookieless traffic
produces real aggregate event counts (funnel step volumes are still
meaningful), but must never be interpreted as tracking a persistent person
across sessions, hosts, or dates — there is no identity to stitch.

## 6. Live-debugger verification checklist

Run this whenever the event contract, consent flow, or identity wiring
changes, using PostHog's live event debugger (Activity → Live events) with
`portfyl.com`/`app.portfyl.com` open in a real or test browser:

1. **Accept path** — accept the consent banner, walk the demo and/or
   register; confirm each expected event arrives with only its allow-listed
   properties (§4) and nothing else.
2. **Reject path** — reject consent, repeat the same walk; confirm events
   still arrive (aggregate) but with no persistent `$device_id`/identity
   carried across a page reload.
3. **Pending path** — leave the banner untouched; confirm **zero** requests
   reach `eu.i.posthog.com` in the browser's network panel.
4. **Event property inspection** — open several captured events in the live
   debugger and manually diff their property list against §4's table; flag
   anything not on the list immediately (it indicates the schema was
   weakened or bypassed).
5. **Logout reset** — sign in (accepted consent), confirm `identify()` fired
   (§5), then log out; confirm the next event after logout carries a fresh
   anonymous identity, not the previous user's.
6. **Workspace transition** — switch workspaces on a multi-workspace
   account; confirm the adapter resets and re-`identify()`s with the *same*
   opaque user id (not a new one, and never the workspace id itself — see
   `AuthProvider.jsx`'s `selectWorkspace`).
7. **Blocked endpoint** — block `eu.i.posthog.com` at the network level (a
   browser extension or DevTools request blocking) and confirm the app
   behaves identically — no error states, no broken buttons; `capture()`
   fire-and-forgets and swallows adapter failures by design.
8. **Invalid key** — temporarily build with a garbage `VITE_POSTHOG_KEY` in
   a throwaway preview build; confirm the app still behaves identically
   (the adapter's `init()` catches and no-ops on failure).
9. **Free-limit behavior** — not independently testable pre-launch; instead
   confirm by re-reading PostHog's own documented behavior at ingestion
   limit (events queue/drop server-side, no client-visible error) each time
   this runbook is revisited.

## 7. Three saved funnels

Create and save exactly these three funnels in PostHog (Insights → Funnel):

1. **Demo activation:** `landing_viewed` → `demo_started` →
   `demo_activation_reached` → `signup_cta_clicked`
2. **Signup completion:** `signup_cta_clicked` → `signup_started` →
   `signup_completed`
3. **Registered activation:** `signup_completed` →
   `portfolio_data_imported` → `dashboard_first_value_rendered` →
   `user_activation_reached`

## 8. First-month monitoring

For the first month after enabling (i.e. after the production blocker
above is lifted and the two Vite variables are actually set), check weekly:

- **Event volume** — total events/week, trending toward but comfortably
  under the 1,000,000/month allowance (§2).
- **Unexpected-property audit** — spot check a sample of each of the 12
  event types in the live debugger against §4; the schema should make this
  structurally impossible, but verify anyway.
- **Funnel sanity** — the three funnels in §7 should show plausible,
  monotonically-decreasing step counts; a funnel step with more people than
  the step before it indicates an instrumentation bug.
- **Consent split** — accepted vs. rejected vs. pending-abandoned ratio,
  purely informational (not a target to optimize).
- **Quota remaining** — remaining event allowance for the current billing
  month, from the PostHog billing/usage page.
- **No payment card** — confirm the account still has no payment method on
  file (Settings → Billing).

## See also

- `docs/compliance/data-processing-inventory.md` — the compliance record
  (external-services table entry and the analytics/telemetry baseline
  section) and the authoritative production blocker statement.
- `docs/operations/activation-analytics-browser-check.md` — the manual
  browser verification matrix and its recorded results.
- `frontend/src/analytics/eventContract.js` — the enforced event schema.
- `frontend/src/analytics/consent.js` — the consent cookie
  (`portfyl_analytics_consent`) and state machine.
- `frontend/src/analytics/AnalyticsProvider.jsx` — the consent-gated
  provider, adapter selection, and identity lifecycle.
