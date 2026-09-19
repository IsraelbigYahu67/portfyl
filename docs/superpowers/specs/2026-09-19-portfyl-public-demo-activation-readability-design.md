# Portfyl Public Demo, Activation Analytics, and Readability Design

**Date:** 2026-09-19

**Status:** Approved in chat; awaiting written-spec review

**Scope:** Cloud public site, cloud authenticated app, shared application UI

## 1. Purpose

Portfyl already presents the product through localized marketing screenshots and
has a mature authenticated portfolio tracker. The next release should close the
gap between those surfaces by adding a real, public, read-only product demo,
measuring the path from first visit to useful portfolio data, and improving the
readability of financial values across every supported appearance.

The work has three connected outcomes:

1. A visitor can experience Portfyl on `portfyl.com/demo` without registering.
2. The team can measure public-demo and registered-user activation without
   collecting portfolio contents or direct identity data.
3. Numbers, labels, tables, and charts remain readable in Premium, Classic,
   Classic dark, the public landing page, and the public demo.

## 2. Goals and non-goals

### Goals

- Publish an anonymous demo containing Dashboard, Allocation, Analytics,
  Dividends, and stock-detail flows.
- Reuse production presentation components and design tokens so the demo stays
  visually aligned with the real product.
- Keep all demo data deterministic, synthetic, versioned, and client-side.
- Add privacy-conscious PostHog Cloud EU measurement for the public and
  authenticated activation funnels.
- Add a consent flow that supports both cookieless aggregate measurement and a
  consented, cross-subdomain journey.
- Establish measurable typography and contrast rules for financial data.
- Preserve the local/cloud edition boundary and all existing tenant protections.

### Non-goals

- No guest account, temporary workspace, shared database portfolio, Firebase
  identity, or server-side demo session.
- No live market-data request from the public demo.
- No import, broker connection, transaction editing, settings, watchlists,
  alerts, AI assistant, tax report, screener, or account-management flow in the
  demo.
- No session replay, form capture, broad click autocapture, or capture of real
  holdings, tickers, balances, transactions, e-mail addresses, or names.
- No redesign of Portfyl's visual identity and no wholesale rewrite of existing
  page containers.
- No paid PostHog plan and no payment card attached to the PostHog account.

## 3. Public demo architecture

### 3.1 Routing and loading boundary

The cloud build gains these public routes:

- `/demo` — portfolio overview
- `/demo/allocation`
- `/demo/analytics`
- `/demo/dividends`
- `/demo/stock/:ticker`

`Root.jsx` must resolve the public demo boundary before mounting
`TrackerBootstrap`, `AuthProvider`, Firebase, portfolio providers, or any
authenticated API prefetch. The demo bundle is lazy-loaded independently of the
landing page and authenticated tracker. The local edition does not expose public
demo routes.

Unknown `/demo/*` routes return to `/demo` with a clear in-product empty/error
state rather than entering the authenticated router or rendering a blank page.

### 3.2 Component boundaries

The public demo consists of:

- `DemoShell`: compact public navigation, demo disclosure, language-aware CTA,
  appearance controls where appropriate, and a route outlet.
- `DemoDataProvider`: a read-only interface over validated static fixtures.
- Demo page containers: route-level composition and demo-specific narrative.
- Shared presentation components: charts, allocation lists, metric cards,
  stock sections, formatters, and semantic typography primitives extracted from
  existing pages where necessary.

Shared components receive data and display state through props. They must not
silently read authenticated portfolio context, issue axios requests, or expose
mutations. Existing authenticated page containers retain ownership of queries,
mutations, and permission-dependent behavior.

This separation avoids a parallel mini-application while preventing public demo
routes from inheriting authenticated side effects.

### 3.3 Read-only behavior

Write actions are omitted rather than shown disabled. The demo does not render
import, refresh, synchronize, customize-and-save, create, edit, delete, alert,
note, assistant, or settings controls. Safe local interactions remain available:

- change chart period or display mode;
- toggle demo benchmarks;
- inspect chart tooltips and accessible data summaries;
- navigate between the five demo areas;
- open one of the ten demo assets;
- change supported visual appearance;
- follow the registration CTA.

A persistent but unobtrusive disclosure states that the portfolio and values are
synthetic and that no account or live portfolio is being accessed.

## 4. Demo portfolio and fixtures

### 4.1 Holdings

The fixture contains exactly ten assets:

| Symbol | Display name | Role / sector |
|---|---|---|
| VUAA | Vanguard S&P 500 UCITS ETF | Diversified European-listed core ETF |
| MSFT | Microsoft | Information technology |
| JPM | JPMorgan Chase | Financials |
| JNJ | Johnson & Johnson | Health care |
| XOM | Exxon Mobil | Energy |
| PG | Procter & Gamble | Consumer staples |
| AMZN | Amazon | Consumer discretionary |
| CAT | Caterpillar | Industrials |
| NEE | NextEra Energy | Utilities |
| PLD | Prologis | Real estate |

The VUAA display identity is stable and exchange-neutral inside the synthetic
fixture. The demo must not imply that a live quote for a particular listing is
being delivered.

### 4.2 Dataset shape

The versioned fixture covers approximately 24 months and includes:

- staggered buy transactions and at least one additional purchase;
- deterministic daily or weekly price history sufficient for every period
  control shown in the demo;
- cash contributions and a non-zero cash balance;
- dividends from multiple holdings across multiple calendar quarters;
- benchmark history for the portfolio-performance comparison;
- sector, country, currency, and asset-type metadata;
- fundamentals and valuation fields needed by the selected stock-detail tabs;
- an upcoming-earnings sample and meaningful gainers/losers;
- a generated-at/as-of date that is displayed consistently.

Values are plausible but synthetic. No fixture is copied from a real user's
portfolio, and the demo does not refresh from Yahoo Finance or another provider.

### 4.3 Validation

A pure schema validator runs in tests and as part of the relevant build path. It
rejects fixtures with:

- a holdings count other than ten;
- duplicate symbols or missing required sector metadata;
- weights that do not reconcile within the documented rounding tolerance;
- transaction/holding quantity inconsistencies;
- missing chart history, benchmark history, or as-of metadata;
- dividend totals that do not reconcile with dividend rows;
- non-finite numeric values or impossible dates.

## 5. Demo experience

### 5.1 Entry points

The public landing page gains a primary or co-primary localized CTA to launch the
demo. Existing screenshot previews remain useful secondary evidence. The demo CTA
must be visible without requiring the visitor to reach the FAQ or page footer.

Demo navigation retains a clear route back to the public landing page and a clear
localized CTA to create an account. The CTA targets the cloud app registration
route and records `source=demo` through the analytics layer; it does not place
personal data in the URL.

### 5.2 Activation definition

A public demo visitor becomes activated after starting the demo and then either:

- viewing at least three distinct demo analysis routes; or
- viewing a stock detail after at least one other demo route.

The activation event fires once per analytics identity/session and is not tied to
scroll depth or time alone.

A registered user becomes activated after all of the following:

1. an account and workspace exist;
2. a portfolio has usable data from demo creation, CSV import, or broker sync;
3. the first populated Dashboard has rendered successfully.

The final activation event fires once per user/workspace activation lifecycle.

## 6. Product analytics

### 6.1 Provider and plan

Use one PostHog Cloud EU free project with no payment card. As of the design date,
the free plan provides one project, one-year retention, unlimited team members,
and one million analytics events per month. Portfyl uses only the capacity needed
for explicit activation events.

The integration is enabled only when `VITE_POSTHOG_KEY` and the EU ingestion host
are configured. A missing key produces a no-op analytics client and never affects
the product.

### 6.2 Consent states

Analytics starts in `pending` state and sends nothing before the visitor decides.

- `rejected`: use PostHog cookieless server-hash measurement with no browser
  persistence and no person profile.
- `accepted`: use a first-party identifier scoped to `.portfyl.com` so an
  opted-in journey can continue from `portfyl.com` to `app.portfyl.com`.
- `pending`: do not initialize capture or queue behavioral events for later
  transmission.

The localized consent surface explains essential storage separately from optional
product analytics. Consent can be changed later. Rejecting analytics must not
reduce product functionality.

### 6.3 Event contract

Only these initial events are permitted:

| Event | Allowed properties |
|---|---|
| `landing_viewed` | `language`, `referrer_class`, `utm_source`, `utm_medium`, `utm_campaign` |
| `demo_started` | `language`, `entry_point` |
| `demo_page_viewed` | `demo_page`, `language` |
| `demo_stock_viewed` | `demo_symbol` |
| `demo_activation_reached` | `activation_path`, `distinct_demo_pages` |
| `signup_cta_clicked` | `source_surface`, `language` |
| `signup_started` | `source_surface`, `language` |
| `signup_completed` | `source_surface` |
| `portfolio_created` | `creation_path` |
| `portfolio_data_imported` | `source_type` (`demo`, `csv`, or `broker`) |
| `dashboard_first_value_rendered` | `source_type` |
| `user_activation_reached` | `source_type` |

No arbitrary property spreading is allowed. Event names and property builders live
in one analytics module with runtime/test allowlists. Unknown event names or
properties are dropped in production and fail tests in development/test.

Authenticated identification uses a stable opaque internal UUID only after
analytics consent. It never uses an e-mail address, display name, Firebase token,
workspace name, portfolio ID, or financial value. `reset()` runs on logout and
workspace/account transitions where identities must not be joined.

### 6.4 Disabled PostHog capabilities

The initial integration disables:

- autocapture;
- automatic pageview/pageleave capture;
- session replay;
- form and text capture;
- surveys;
- heatmaps and dead-click capture;
- GeoIP-dependent reporting for cookieless traffic;
- broad exception capture already owned by the opt-in Sentry integration.

### 6.5 Funnels

The setup runbook defines three saved funnels:

1. `landing_viewed` → `demo_started` → `demo_activation_reached` →
   `signup_cta_clicked`
2. `signup_cta_clicked` → `signup_started` → `signup_completed`
3. `signup_completed` → `portfolio_data_imported` →
   `dashboard_first_value_rendered` → `user_activation_reached`

Cookieless visitors are measurable in aggregate but cannot be assumed to retain a
stable identity across dates or hostnames. End-to-end person-level conversion is
reported only for visitors who accepted analytics.

## 7. Readability system

### 7.1 Semantic typography

Introduce semantic financial-data styles instead of continuing to add arbitrary
font sizes or opacity utilities:

- headline financial values: minimum 16 CSS px, larger where hierarchy requires;
- normal table, chart, list, and card values: minimum 14 CSS px;
- secondary metadata: minimum 12 CSS px and only for non-critical information;
- no critical value, axis tick, legend label, input value, or actionable label
  below 12 CSS px at any viewport;
- tabular numerals for aligned financial values;
- consistent locale-aware separators, precision, signs, and compact units.

Mobile layouts preserve these floors. They may abbreviate units, wrap supporting
copy, stack label/value pairs, or use bounded horizontal table scrolling rather
than shrinking text.

### 7.2 Semantic color and contrast

Premium, Classic light, and Classic dark expose semantic tokens for primary text,
secondary text, tertiary metadata, borders, chart axes, chart grid lines, gains,
losses, and focus indicators. Components consume these tokens instead of raw gray
values or opacity-based text.

Minimum targets:

- 4.5:1 for normal text;
- 3:1 for large text and meaningful non-text UI/chart elements;
- gain/loss meaning is reinforced with sign, wording, icon, pattern, or position;
- disabled controls remain distinguishable but are not used to communicate
  important readable data;
- focus indicators maintain at least 3:1 state contrast.

The audit includes hard-coded landing-page colors and the warm Premium surfaces,
not only Tailwind theme variables.

### 7.3 Charts and dense data

- Axis ticks and legends follow the same minimum text rules.
- Important series receive direct labels where space permits.
- Multi-series charts add line style, marker, or explicit labels so hue is not the
  only differentiator.
- Hairline axes and grid lines are strengthened when they fall below the non-text
  contrast target.
- Existing accessible chart summaries/data tables remain available and receive
  the same numeric formatting.
- Tables keep stable numeric alignment and do not encode positive/negative state
  only through red/green.

### 7.4 Scope

The audit covers the public landing page, demo routes, authentication pages, shell,
Dashboard, Allocation, Analytics, Dividends, Transactions, Cash, Watchlists,
Options, stock detail, local-only Tax Report/Screener, cloud Pricing, Assistant,
Import, Onboarding, and Settings. Fixes should be token/component-level first;
page-specific exceptions require a documented reason.

## 8. Failure behavior and privacy safeguards

- PostHog script blocking, network errors, quota exhaustion, or invalid
  configuration never blocks rendering, navigation, registration, or activation.
- Analytics calls are non-throwing from product code.
- Demo data parsing failures render a branded unavailable state and are also caught
  by tests/build validation before deployment.
- The content security policy permits only the configured EU PostHog endpoints
  needed for script delivery and ingestion.
- Development and test builds use a memory adapter that exposes captured events
  for assertions without sending them externally.
- Logs and Sentry breadcrumbs must not duplicate analytics payloads containing
  identifiers.
- The public privacy/subprocessor record must name PostHog Cloud EU before public
  analytics is enabled in production.

## 9. Testing and acceptance

### 9.1 Automated tests

- Routing proves `/demo/*` is cloud-only, public, lazy, and outside authenticated
  providers.
- Demo-route tests fail on any portfolio API request or Firebase initialization.
- Every demo page renders from the validated fixture.
- The fixture contains exactly the ten approved assets and reconciles all derived
  totals.
- Mutation controls and links to excluded private features are absent.
- Consent tests cover pending, rejected/cookieless, accepted/persistent, changed,
  and reset states.
- Analytics contract tests cover every event/property allowlist, no-op behavior,
  identity reset, and once-only activation.
- Contrast tests calculate actual token/color pairs for every supported theme.
- Component tests cover the semantic numeric typography classes and formatting.
- Existing local/cloud Vitest suites and both production builds remain required.
- Existing backend fast and PostgreSQL/RLS gates remain required when backend code
  is touched.

### 9.2 Browser matrix

Run the public landing, all demo routes, representative authenticated screens, and
consent flow at 390×844, 768×1024, 1024×768, and 1440×900. Exercise Premium,
Classic light, and Classic dark. Verify:

- no unintended horizontal page scrolling;
- critical values remain at or above their size floor;
- computed contrast meets the stated targets;
- keyboard navigation and focus remain visible;
- charts retain labels and accessible summaries;
- rejected analytics creates no persistent analytics storage;
- accepted analytics joins the public and app subdomains;
- the product still works when the PostHog endpoint is blocked.

Keep a small set of browser screenshots for the highest-density dashboard, table,
and stock-detail states as regression evidence.

### 9.3 Release acceptance

The release is acceptable when:

1. an unauthenticated production visitor can complete the approved demo flow
   without a backend portfolio request;
2. the two activation definitions fire once and can be reproduced in the PostHog
   live event debugger without sensitive properties;
3. the three saved funnels are documented and reproducible;
4. all audited critical numeric text and meaningful visual elements meet the
   stated size and contrast floors in every supported appearance;
5. local/cloud test and build gates pass;
6. PostHog remains on the no-card free plan and product behavior is unaffected at
   its usage limit.

## 10. Deployment and operations

- Add documented cloud build variables for the public PostHog project token and EU
  ingestion host. The project token is not treated as a secret, but it is scoped
  to the intended project and environment.
- Keep analytics disabled in production until the consent copy, privacy notice,
  and subprocessor entry have been reviewed and published.
- Configure one production project only; development/test uses the memory/no-op
  adapter to preserve the free event budget and clean data.
- Do not attach a payment card. The PostHog free plan stops ingestion at its limit,
  which is the desired failure mode.
- Document event-volume monitoring and review the first month after launch. At the
  approved explicit event count, normal private-beta/public-preview traffic should
  remain far below one million events per month.

## 11. Implementation sequence

This design should be implemented as three coordinated workstreams in this order:

1. semantic readability tokens/components and shared presentational boundaries;
2. static demo fixture, public routing, and demo experience;
3. consent-aware analytics, funnel events, documentation, and full browser matrix.

Readability and shared-component extraction comes first so the demo launches on
the corrected visual foundation. Analytics comes last so events are attached to
stable route and activation boundaries rather than temporary implementation
details.
