# Portfyl SaaS & Monetization Master Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform Portfyl from a single-user portfolio application into a
secure multi-user SaaS with a low-cost paid offering, a seven-day trial, and
grandfathered founder pricing, while preserving a separate private local
edition for owner-only experimental features.

**Architecture:** One codebase produces two explicitly configured editions.
`PORTFYL_EDITION=local` runs the owner's private home installation and enables
local-only modules; `PORTFYL_EDITION=cloud` runs the customer SaaS and excludes
those modules at both backend-route and frontend-navigation level. In the
cloud edition, a user belongs to one or more workspaces and the workspace is
the billing and authorization tenant. PostgreSQL, revocable authentication,
encrypted secrets, idempotent background jobs, edition capabilities, and
server-side plan entitlements replace the current single-user assumptions.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, PostgreSQL, SQLite for the private
local profile, Alembic, React, a backend-owned edition/capability registry,
Stripe Billing, Cloud Run, an external scheduler/job queue, transactional
e-mail, and a commercially licensed market-data provider for cloud features.

**Spec:** This is the self-contained master product, pricing, research, and
architecture specification at
`docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md`. Each major
workstream must receive a separate task-level implementation plan before code
execution because auth/tenancy, database migration, billing, data licensing,
and paid product functionality are independently reviewable subsystems.

## Global Constraints

- Existing user changes in the repository must be preserved.
- No paid cloud launch may depend on `yfinance` or another data source without
  explicit commercial display/redistribution rights.
- `PORTFYL_EDITION` has exactly two accepted values: `local` and `cloud`.
  Unknown or missing values fail startup in deployed environments; local
  development commands set `local` explicitly.
- The initial definitive `local_only` capability list is `tax_report` and
  `screener`. No subscription, admin role, URL manipulation, or frontend call
  can enable either capability in the cloud edition.
- Additional owner-only experiments can be classified `local_only` in one
  central capability registry; a new feature must declare its edition before
  it can be exposed.
- Edition availability is checked before paid-plan entitlement:
  `available = edition_allows(capability) && plan_allows(capability)`. The local
  edition does not require Stripe or a subscription.
- Cloud must not register local-only API routes, include local-only navigation,
  or advertise local-only features. Frontend hiding alone is insufficient.
- Keep one shared codebase and one main branch; do not create a permanent
  private fork that would drift away from cloud security and portfolio logic.
- No multi-user beta may launch until cross-tenant authorization tests prove
  that one user cannot read, mutate, enumerate, or trigger jobs for another
  user's resources.
- Raw export and deletion of a user's own data remain available on every plan.
- Trial expiration never deletes imported customer data.
- Founder pricing remains unchanged while the subscription stays continuous;
  taxes and separately priced variable-cost add-ons are excluded.
- Hosted AI, real-time exchange data, e-mail/SMS/push delivery, and other
  variable-cost features must have enforceable server-side quotas.
- Tax-report and screener code remains an owner-only local experiment. It is
  not marketed, sold, trialled, or represented as a cloud capability.
- Public customer prices are displayed with the applicable VAT treatment and
  billing complies with EU B2C VAT/OSS requirements.
- Security and plan enforcement happen on the backend; the frontend is never
  the source of truth for ownership, subscription status, or quota usage.

---

## 1. Executive decision

Portfyl already contains enough functional value to become a paid product.
The immediate bottleneck is not another chart or research widget, but the
foundation required for trust and safe multi-user operation.

### Recommended launch strategy

- Position the cloud edition first for Czech/EU self-directed investors using
  Trading 212 and Interactive Brokers.
- Lead with consolidated accounts, correct return measurement, dividends,
  portfolio analytics, CZK, and trustworthy automation.
- Use advanced stock-detail research, AI, options, and Polymarket as Pro
  differentiation. Tax Report and Screener remain private local tools and are
  absent from every cloud tariff.
- Launch three public plans: Free, Investor, and Pro.
- Offer seven days of Pro without a payment card, starting only after a
  successful import or broker connection.
- Keep the original base software price for continuously subscribed founder
  customers.
- Preserve one private `local` edition for the owner without billing or cloud
  exposure of its experimental capabilities.

### Recommended founder pricing

| Plan | Monthly | Annual | Target user |
|---|---:|---:|---|
| Free | EUR 0 | EUR 0 | Trying Portfyl or maintaining one simple manual portfolio |
| Investor | EUR 4.99 | EUR 49 | Long-term investor who needs sync, analytics, dividends, and automation |
| Pro | EUR 7.99 | EUR 79 | Active investor who uses advanced research, AI, options, or Polymarket |
| Family, later | EUR 12.99 | EUR 129 | Household with shared portfolios and several members |

After product-market fit, the working target for new customers is Investor at
EUR 5.99 / EUR 59 and Pro at EUR 9.99 / EUR 99. Existing continuously active
founder subscriptions keep their original software price.

Removing Tax Report and Screener weakens two common competitor upgrade levers,
so these prices remain hypotheses rather than a reason to add those features
back to cloud. Validation must test whether customers will pay EUR 4.99 for
broker automation, consolidated analytics, risk, and dividends, and EUR 7.99
for advanced stock-detail research, hosted AI, options, and Polymarket. If not,
change the cloud package or price; do not silently expose local-only modules.

---

## 2. Current product audit

### Existing value

Portfyl already includes:

- multiple portfolios and transaction CRUD;
- manual and CSV imports;
- Trading 212 and IBKR synchronization;
- options and Polymarket positions;
- TWR, XIRR, CAGR, Sharpe, Sortino, drawdown, VaR, beta, alpha, benchmarks,
  and correlation;
- Czech tax reporting, retained only in the target `local` edition;
- dividend history, calendar, forecast, and growth;
- multi-currency and CZK reporting;
- fundamentals, ratios, DCF, valuation history, ownership, insiders, filings,
  politician trades, stock details, and a screener (the screener is retained
  only in the target `local` edition);
- an AI portfolio assistant;
- price/dividend alerts and Discord delivery;
- cash tracking and a responsive React interface.

Reference: `README.md:5-13`, `README.md:131-168`.

### Edition boundary decision

| Behavior | Private `local` edition | Customer `cloud` edition |
|---|---|---|
| Intended users | Owner at home | Registered customers |
| Billing | None | Free/Investor/Pro via Stripe |
| Database | SQLite is acceptable for the private installation | Managed PostgreSQL (Neon) |
| Authentication | Local access mode mapped to one local workspace | Verified identities and revocable sessions |
| Tax Report | Enabled | Unavailable in every plan |
| Screener | Enabled | Unavailable in every plan |
| Additional experiments | Enabled only after explicit `local_only` classification | Denied unless explicitly classified for cloud |
| Market-data basis | Personal/local use subject to provider terms | Explicit commercial customer-display rights |

The edition boundary is a security/product boundary, not a cosmetic feature
flag. The initial implementation must guarantee:

- `/api/analytics/tax-report` and `/api/market/screener` are not registered in
  cloud OpenAPI and return 404 in cloud deployments;
- `/tax-report` and `/screener` are not registered as cloud frontend routes and
  do not appear in the cloud sidebar, command palette, search, sitemap, help,
  pricing, or trial messaging;
- both routes and navigation remain available in `local`;
- a backend capabilities endpoint is the runtime source of truth for shared UI,
  while the cloud build configuration also omits local-only route entries;
- automated tests boot both editions and assert the positive local behavior and
  negative cloud behavior;
- adding a future feature requires choosing `local_only`, `cloud_free`,
  `cloud_investor`, or `cloud_pro` in the central capability registry.

The existing tax and screener implementation can remain in the repository and
share portfolio/market services. Their route modules should be separated from
the mixed analytics/market routers so `backend/main.py` can register them only
for `PORTFYL_EDITION=local`. Frontend imports/routes should follow the same
edition-specific manifest instead of relying only on hidden sidebar items.

### Critical multi-user gaps

#### Authentication is still single-user

- `backend/auth.py:28` defines `DEFAULT_OWNER_ID = "default"`.
- `backend/auth.py:56-63` returns that value from `get_current_user()`.
- `CLAUDE.md:48-50` explicitly documents that the application is single-user.
- The shared-password session is not a complete customer identity system.

Required outcome:

- user registration and verified e-mail;
- password reset and strong password hashing, or a managed identity provider;
- server-side revocable sessions;
- logout from all devices;
- optional OAuth after core e-mail auth works;
- MFA for account security as a follow-up.

#### Tenant isolation is incomplete

- `backend/routers/portfolios.py:49-50` lists portfolios without owner scope.
- Portfolio update/delete paths around lines 72-91 query only by numeric ID.
- `require_portfolio()` at `backend/routers/portfolios.py:175-191` does not
  consistently include the current owner in the lookup.
- `backend/routers/watchlists.py:80-83` lists global watchlists and their items.
- Settings carry `owner_id`, but `backend/app_settings.py:15-24` queries only
  by key.
- The test suite does not contain systematic Alice/Bob authorization cases.

Adding registration without correcting this would create an IDOR risk in
which one authenticated customer could read or mutate another customer's
objects.

Required outcome:

- one central request-scoped workspace/tenant context;
- every object lookup scoped by `workspace_id` or through a workspace-owned
  parent;
- list endpoints return only the current workspace's rows;
- update/delete return 404 for foreign objects to prevent enumeration;
- background jobs, imports, alerts, and caches include tenant identity;
- PostgreSQL row-level security as defense in depth;
- a route-by-route cross-tenant test matrix.

#### Current uniqueness constraints are global

- `Portfolio.name` is globally unique at `backend/models.py:14`.
- `Watchlist.name` is globally unique at `backend/models.py:53`.
- `AppSetting.key` is globally unique at `backend/models.py:227`.

Required outcome:

- replace these with composite tenant constraints such as
  `(workspace_id, name)` and `(user_id, key)`;
- distinguish personal user settings from shared workspace settings;
- expose non-sequential UUID/ULID identifiers to API clients.

#### Secrets are plaintext

- `backend/models.py:104-105` stores broker `api_key` and `api_secret` as
  ordinary strings.
- `backend/models.py:215-220` explicitly documents plaintext app settings,
  including the AI API key.

Required outcome:

- envelope encryption with a cloud KMS-managed key;
- ciphertext and key version stored in the database;
- secrets removed from logs, errors, analytics, and support exports;
- an explicit rotation and disconnect flow;
- broker connection tests that never use real customer credentials.

#### SQLite and single-instance deployment block SaaS scaling

- `backend/database.py:19-21` builds a SQLite engine.
- `deploy/cloudrun.md:146-149` says `--max-instances=1` is load-bearing and
  must not be raised while using GCS-mounted SQLite.
- `backend/main.py:488-556` launches periodic work inside the web process.

Required outcome:

- managed PostgreSQL (Neon), replacing the SQLite engine at
  `backend/database.py:19-21`;
- Alembic migrations instead of startup-time imperative schema changes;
- automated backups and point-in-time recovery;
- a tested restore procedure;
- Cloud Scheduler/Tasks or a dedicated queue/worker for scheduled work;
- idempotency keys and database locks for sync, alerts, and billing events;
- multiple stateless web instances without duplicate jobs — PostgreSQL removes
  the GCS-mounted-SQLite single-instance constraint that made
  `deploy/cloudrun.md`'s `--max-instances=1` load-bearing, so Cloud Run can run
  with `--max-instances` > 1 once the service targets Neon.

---

## 3. Market and competitor research

Research date: 2026-09-01. Prices are public official list prices and can vary
by market, VAT, currency, and app-store region.

| Product | Free/trial | Public paid positioning | Lesson for Portfyl |
|---|---|---|---|
| [Sharesight](https://www.sharesight.com/uk/pricing/) | Free: 1 portfolio / 10 holdings | Roughly GBP 6-21 per month on annual billing | Multi-portfolio and advanced reports are natural paid gates |
| [Parqet](https://parqet.com/en/pricing) | Basic free; 14-day paid trials | Plus EUR 11.99, Investor EUR 29.99 monthly | Broker sync, tax dashboard, full analysis, and integrations sell |
| [Delta](https://delta.app/en/pro) | Free: 1 portfolio / 10 assets | PRO USD 6.99, PRO+ USD 13.99 monthly; lower annual equivalents | Clear two-step mobile upsell; tax and unlimited portfolios sit higher |
| [Snowball Analytics](https://snowball-analytics.com/pricing) | Free: 1 portfolio / 10 holdings; 14 days without a card | USD 79.99-249.99 annually | Downgrade without deleting data and licensed data/vendor integrations build trust |
| [Portseido](https://www.portseido.com/pricing/) | Free: 1 portfolio / 100 transactions; 14 days without a card | USD 8 or USD 12 monthly on annual billing | A genuinely useful Free plan can still convert multi-portfolio users |
| [DivvyDiary](https://divvydiary.com/en/pricing) | Free plan; seven-day trial | About EUR 7.50 monthly on annual billing | Direct precedent for the requested seven-day trial |
| [Stock Events](https://stockevents.app/en/pricing) | Free: 15 stocks; seven-day trial | USD 49.99 annually plus optional sync add-on | Low-price consumer plan works when expensive integrations are controlled |
| [Koyfin](https://www.koyfin.com/pricing/) | Useful free research tier | Roughly USD 39 and USD 79 monthly on annual billing | A research terminal supports much higher ARPU but faces a different market |
| [Kubera](https://www.kubera.com/) | 14-day trial | USD 250 annually, with a much higher premium tier | Household wealth, permissions, beneficiaries, and service create a premium segment |
| [Simply Wall St](https://simplywall.st/plans) | Free quotas; seven-day Premium trial without card | Portfolio/report quotas by tier | Trial expiry should hide excess access, not destroy customer data |
| [Portfolio Performance](https://www.portfolio-performance.info/en/) | Free and open source | No paid tier | Charts alone do not monetize; convenience, automation, trust, and support do |

### Market conclusions

- The mainstream consumer portfolio-tracker corridor is approximately
  EUR 4-13 per month.
- Research terminals start much higher, around USD 39+ per month.
- Annual discounts commonly land around 17-30%.
- A useful Free plan usually permits one portfolio and 10-15 active holdings.
- Paid gates cluster around broker sync, multiple portfolios, tax reporting,
  advanced analytics, deeper research, exports, alerts, and priority support.
- Seven- to fourteen-day no-card trials are normal.
- Most competitors downgrade expired trials without deleting data.
- Consumer trackers normally do not charge based on assets under management;
  Portfyl should avoid AUM pricing.

Competitors frequently monetize tax reports and screeners, but Portfyl makes a
deliberate product decision not to do so: neither feature is part of the cloud
value proposition or any cloud tariff. The remaining paid package must convert
on consolidation, broker automation, performance/risk analytics, dividends,
advanced stock-detail research, alerts, AI, options, and Polymarket.

### Grandfathering precedent

Koyfin documented moving existing Pro users while keeping their prior price:
[Koyfin Pro discontinuation](https://www.koyfin.com/help/pro-discontinuation/amp/).

---

## 4. Product positioning

### Options considered

1. **Global all-in-one tracker**
   - Largest theoretical market.
   - Highest broker-integration, support, localization, and data-license cost.
   - Not recommended as the initial wedge.

2. **Czech/EU account consolidation and analytics product**
   - Builds directly on T212, IBKR, CZK, dividend, performance, risk, and
     automation features without making tax claims.
   - Lower initial market size but better differentiation and messaging.
   - Recommended launch position.

3. **Low-cost research terminal**
   - Higher potential willingness to pay.
   - Direct competition with Koyfin and Simply Wall St and greater data cost.
   - Recommended as the Pro expansion, not the first identity.

### Recommended promise

> Portfyl unifies investment accounts, measures performance after deposits and
> withdrawals, tracks dividend progress, and makes portfolio risk and company
> research understandable in one CZK-friendly application.

### UX consequence

The current platform-first entry (`frontend/src/components/PlatformLanding.jsx`)
should become a unified workspace/account experience:

1. Create account.
2. Use a demo or import/connect a real account.
3. See a consolidated portfolio result immediately.
4. Add further broker accounts inside the workspace.
5. Reveal broker-specific pages, such as options, only when relevant data
   exists.

The broker is a data source, not the identity of the whole application.

---

## 5. Tier specification

| Capability | Free | Investor EUR 4.99 | Pro EUR 7.99 |
|---|---|---|---|
| Portfolios | 1 | 5 | 15 |
| Active positions | 15 | No product limit | No product limit |
| Transactions | 250 | No product limit | No product limit |
| Manual entry and CSV | Yes | Yes | Yes |
| Broker connections | 0 | 2 | 5 |
| Automatic sync | No | Daily | Approximately every six hours |
| Dashboard/allocation/cash | Basic | Complete | Complete plus custom dashboard |
| TWR/XIRR/CAGR | Basic result | Complete | Complete |
| Sharpe/Sortino/drawdown/VaR/correlation | No | Yes | Yes |
| Benchmarks | One default | Multiple | Custom blended benchmarks |
| Dividend calendar | Basic | History, forecast, growth | Scenarios and goals |
| Tax Report | Not available in cloud | Not available in cloud | Not available in cloud |
| Fundamentals | Basic held-symbol snapshot | Complete standard analysis | DCF, valuation history, filings, insiders, ownership |
| Screener | Not available in cloud | Not available in cloud | Not available in cloud |
| Watchlists | 1 / 15 symbols | 5 | Fair-use high limit |
| Alerts | 3 | 20 via e-mail/Discord | 100 via e-mail/Discord/push |
| Options and Polymarket | Summary only | No advanced analytics | Complete analytics |
| AI assistant | No hosted AI | Bring your own key | 100 hosted messages/month plus BYOK |
| Raw customer-data export | Always | Always | Always |
| Support | Documentation | Standard | Priority |

### Tier rules

- Limits are stored as backend entitlements, not frontend conditions.
- Every expensive capability has a usage counter and reset period.
- Free does not include automatic broker synchronization.
- Tax Report and Screener are rejected by the cloud edition before plan
  entitlement is evaluated; even Pro cannot access them.
- The local edition enables Tax Report and Screener directly and never enters
  the Stripe/trial/plan entitlement flow.
- A privacy/export request is never counted as a paid report.
- Marketing avoids the word `unlimited` for variable-cost services.
- Exact research and quote quotas remain configurable so they can match the
  signed data-provider contract without a schema change.

---

## 6. Trial and subscription lifecycle

### Trial policy

- [ ] Offer full Pro for seven days without a payment card.
- [ ] Start the clock after the first successful real-data import or broker
      connection, not account creation.
- [ ] Verify the e-mail before activating the trial.
- [ ] Apply CAPTCHA, rate limits, and a one-trial policy per verified identity.
- [ ] Limit hosted AI to 15 messages during the trial.
- [ ] Send activation, day-three, and day-six lifecycle e-mails.
- [ ] Show a value summary: successful syncs, analyses used, portfolio/risk
      insights, upcoming dividends, and automation performed.
- [ ] On day eight, downgrade automatically to Free.
- [ ] Keep all data; objects beyond Free limits become read-only.
- [ ] Keep raw export and account deletion available.

Stripe supports trials without a payment method and configurable end behavior:
[Stripe trial documentation](https://docs.stripe.com/billing/subscriptions/trials).

### Founder price policy

Customer-facing promise:

> As long as the subscription remains continuous, the base software price at
> signup will not increase.

Implementation requirements:

- [ ] Create immutable Stripe Price IDs for every pricing generation.
- [ ] Persist `price_version` and subscribed interval on the subscription.
- [ ] Never edit or delete an active legacy Price ID.
- [ ] Give failed recurring payments a 14-day dunning/grace period without
      losing founder status.
- [ ] A voluntary cancellation followed by a later resubscription uses the
      current public price.
- [ ] Explain that statutory taxes and separately priced, variable-cost
      add-ons are outside the base-price guarantee.
- [ ] Do not promise that every future paid feature is included forever;
      existing customers keep their purchased plan capabilities, while new
      high-cost services may be explicit add-ons.

---

## 7. Product improvements by priority

### P0: required before accepting money

- [ ] Central edition/capability registry with fail-closed `local`/`cloud`
      startup configuration.
- [ ] Backend route-registration and frontend route/navigation tests proving
      Tax Report and Screener exist only in `local`.
- [ ] Cloud pricing, onboarding, help, sitemap, analytics events, and upgrade
      prompts contain no Tax Report or Screener claims.
- [ ] Unified account/import onboarding with a demo portfolio.
- [ ] Import preview, duplicate detection, reconciliation, and undo.
- [ ] Consolidated view across broker accounts.
- [ ] Czech and English localization.
- [ ] Source and last-updated status for market/fundamental data.
- [ ] Explainable TWR/XIRR, benchmark, risk, and data methodology.
- [ ] E-mail delivery in addition to Discord.
- [ ] Public marketing, pricing, documentation, status, privacy, and terms
      pages.
- [ ] Responsive PWA behavior.
- [ ] Support/contact and incident-response process.

### P1: strongest likely paid value

- [ ] Target allocation and allocation drift.
- [ ] Cash-aware rebalancing proposals.
- [ ] Realized/unrealized gain, contribution, and cash-flow breakdown without
      tax treatment or tax advice.
- [ ] ETF look-through, fund overlap, and TER/fee analysis.
- [ ] Investment and passive-income goals.
- [ ] Weekly/monthly portfolio digest.
- [ ] Custom dashboard widgets.
- [ ] Data-quality checks for missing FX, duplicate or suspicious
      transactions, and inconsistent cash.
- [ ] Portfolio scenarios for market, FX, and allocation changes.

### P2: expansion after retention is proven

- [ ] Family workspace with owner/editor/viewer/accountant roles.
- [ ] Household consolidated view and audit log.
- [ ] Custom assets, property, liabilities, and net worth.
- [ ] Additional broker connectors selected from customer demand.
- [ ] Native mobile applications only after PWA behavior is validated.
- [ ] Read-only share links.
- [ ] Advisor/B2B product as a separate security and pricing project.

### Explicitly deferred

- Social network/community.
- Trade execution.
- Included real-time exchange feeds.
- Unlimited hosted AI.
- Broad advisor/B2B permissions in the consumer launch.

Tax Report and Screener are not deferred cloud features. They are deliberately
out of cloud scope and remain owner-only in the private local edition unless a
future product decision explicitly changes this master plan.

These items introduce disproportionate cost, regulation, or operational risk
before core retention is known.

---

## 8. Target multi-user architecture

### Edition and capability layer

- `Edition` is a closed enum with `local` and `cloud` values.
- One backend module owns the immutable edition capability map.
- `tax_report` and `screener` map only to `local`.
- Cloud capabilities map separately to Free, Investor, or Pro entitlements.
- The backend exposes a read-only capability manifest for rendering shared UI,
  but authorization always re-evaluates capability access server-side.
- Local-only API routers are registered only while booting `local`; cloud
  OpenAPI therefore contains no local-only endpoint.
- Frontend edition route manifests ensure cloud navigation and routes do not
  import or advertise local-only pages.
- Edition tests boot both application factories rather than mutating a global
  flag inside one process.
- The local profile maps the owner to one local workspace so shared portfolio
  services remain tenant-aware even when SQLite and local authentication are
  used.

```text
User
└── Membership
    └── Workspace                 # authorization + billing tenant
        ├── Subscription
        ├── Portfolio
        │   └── InvestmentAccount
        │       ├── BrokerConnection
        │       ├── Transaction
        │       ├── CashMovement
        │       └── Position-derived data
        ├── Watchlist
        ├── Alert
        ├── WorkspaceSetting
        ├── UsageCounter
        └── AuditEvent
```

### Identity and authorization

- `User` represents login identity and personal settings.
- `Workspace` owns financial data and one subscription.
- `Membership` connects users to workspaces with a role.
- Solo launch accounts receive one workspace and one owner membership.
- Every API operation obtains a trusted user/session and current workspace.
- Every data access includes the workspace predicate or a verified parent.
- PostgreSQL RLS protects tenant tables if an application predicate is missed.
- Public API identifiers are UUID/ULID values.

### Data model and migrations

- PostgreSQL becomes the cloud source of truth; the private local edition may
  continue using SQLite.
- Alembic owns forward and rollback-capable schema migrations.
- Migration rehearsals run on copies of existing SQLite data.
- Composite uniqueness replaces app-wide uniqueness.
- Foreign keys define deletion behavior explicitly.
- Billing events and sync imports retain idempotency identifiers.
- Shared performance/analytics calculation rules carry version identifiers.
- Local tax-calculation implementation and fixtures remain isolated from
  cloud product claims and cloud launch criteria.

### Background work

- Web instances remain stateless.
- A scheduler enqueues sync, alert, dividend, and billing reconciliation jobs.
- Jobs identify both workspace and target resource.
- Database uniqueness/advisory locks prevent duplicate execution.
- Retries are bounded and visible to the customer.
- Poison jobs enter a dead-letter/review state.
- Job logs never contain broker credentials or full portfolio payloads.

### Secrets and observability

- KMS-backed envelope encryption protects broker, webhook, and AI secrets.
- Structured logs use correlation IDs but redact sensitive values.
- Error monitoring groups failures without sending private holdings by
  default.
- Audit events record security and financial-data mutations.
- Health checks distinguish web, database, scheduler, broker, and market-data
  availability.

---

## 9. Workstream decomposition

This master plan spans independent systems. Create and approve a focused
task-level implementation plan for each workstream before modifying code.

### Workstream A: product/data validation and edition boundary

Deliverable: signed or explicitly approved commercial data path, positioning
evidence, a validated founder-pricing page, and an approved local/cloud
capability matrix.

Primary artifacts:

- data-vendor requirements and quotes;
- broker API terms matrix;
- explicit capability registry with `tax_report` and `screener` marked
  `local_only`;
- tests specifying positive local and negative cloud route/navigation behavior;
- interview notes and decision summary;
- pricing/landing copy.

### Workstream B: PostgreSQL and migration foundation

> Scoped kickoff prompt already written (combined with Workstream C, targeting
> Cloud Run + Neon + Cloudflare specifically):
> `docs/superpowers/plans/2026-09-01-portfyl-multiuser-foundation-prompt.md`.

Likely touchpoints:

- `backend/database.py`;
- `backend/models.py`;
- `backend/main.py` startup migrations;
- a new Alembic configuration and migrations;
- deployment configuration and restore documentation;
- database-focused tests and migration fixtures.

Deliverable: PostgreSQL-backed application with a rehearsed SQLite migration,
automated backups, and a successful restore drill.

### Workstream C: identity, workspaces, and tenant isolation

> Scoped kickoff prompt already written (combined with Workstream B, targeting
> Cloud Run + Neon + Cloudflare specifically):
> `docs/superpowers/plans/2026-09-01-portfyl-multiuser-foundation-prompt.md`.

Likely touchpoints:

- `backend/auth.py`;
- `backend/models.py`;
- every router containing direct model queries;
- dependencies that resolve portfolio/workspace access;
- frontend session/account state;
- new Alice/Bob integration-test modules.
- application-factory/edition tests proving local-only routers are never
  mounted in cloud.

Deliverable: revocable user sessions and demonstrably complete tenant
isolation across API, jobs, settings, caches, imports, and alerts.

### Workstream D: secrets, jobs, and operational security

Likely touchpoints:

- broker and assistant configuration;
- `backend/main.py` background loops;
- alert/dividend/sync job code;
- cloud deployment and KMS integration;
- logging, monitoring, and audit models.

Deliverable: encrypted credentials, stateless web instances, idempotent
external jobs, redacted monitoring, and incident-ready operations.

### Workstream E: billing, trial, and entitlements

Likely touchpoints:

- new subscription/price/webhook/usage models;
- Stripe service and webhook router;
- backend entitlement dependency/service;
- frontend pricing, checkout, portal, and upgrade surfaces;
- transactional trial/billing e-mails;
- webhook replay and quota tests.

Deliverable: monthly/annual subscriptions, no-card Pro trial, reliable
downgrade, immutable founder prices, and backend-enforced quotas.

### Workstream F: onboarding and paid product packaging

Likely touchpoints:

- platform landing and app shell;
- portfolio/account/broker connection flows;
- CSV import and reconciliation;
- pricing and plan-comparison UI;
- e-mail/notification channels;
- localization and trust/methodology pages.

Deliverable: a new user can import/connect data, understand the first result,
experience Pro value, and choose a plan without support intervention.

### Workstream G: private beta and launch operations

Deliverable: evidence from 20-50 beta users, security review, restore and
failure drills, support playbook, launch metrics, and a documented go/no-go
decision.

---

## 10. Phased roadmap and gates

### Phase 0: validation, edition boundary, and licensing — estimated 1-2 weeks

- [ ] Interview 10-15 Czech T212/IBKR investors.
- [ ] Rank sync, performance/risk analytics, research, dividends, alerts, and
      consolidation by demonstrated willingness to pay.
- [ ] Obtain written commercial market-data quotes and rights.
- [ ] Review broker API terms and credential-storage obligations.
- [ ] Approve the local/cloud feature matrix with Tax Report and Screener
      definitively marked local-only.
- [ ] Publish a waitlist/pricing test using the proposed plans.

**Exit gate:** There is a financially viable cloud data source, the edition
boundary is unambiguous, and evidence shows that the non-tax/non-screener
cloud positioning solves a paid problem.

### Phase 1: secure SaaS foundation — estimated 4-6 weeks

- [ ] Complete Workstream B: PostgreSQL and migrations.
- [ ] Complete Workstream C: identity and tenant isolation.
- [ ] Complete Workstream D: encrypted secrets and external jobs.
- [ ] Implement edition-specific backend and frontend route manifests.
- [ ] Configure backups, monitoring, audit, rate limits, and EU deployment.

**Exit gate:** Cross-tenant tests pass for every resource class, multiple web
instances run without duplicate work, and a production-like backup restores
successfully. Cloud OpenAPI, navigation, and direct URL tests contain neither
Tax Report nor Screener, while both remain usable in the private local build.

### Phase 2: monetization and onboarding — estimated 3-4 weeks

- [ ] Complete Workstream E: Stripe, trial, entitlements, and quotas.
- [ ] Build unified onboarding and demo/import activation.
- [ ] Add lifecycle e-mails and billing recovery.
- [ ] Complete privacy, terms, export, deletion, and support surfaces.

**Exit gate:** A test customer can register, import, trial Pro, subscribe,
change billing, fail/retry payment, downgrade, export, and delete safely.

### Phase 3: paid value and trust — estimated 3-5 weeks

- [ ] Ship clear performance, risk, dividend, and portfolio reports without tax
      treatment.
- [ ] Package advanced stock-detail research for Pro without exposing the
      local Screener.
- [ ] Add data-source/freshness and reconciliation UX.
- [ ] Add e-mail digest and high-value P1 improvements selected by interviews.
- [ ] Complete Czech/English localization and PWA polish.

**Exit gate:** The paid upgrade is driven by a repeatable customer outcome,
not only arbitrary limits.

### Phase 4: private beta — estimated 2-4 weeks

- [ ] Invite 20-50 users.
- [ ] Perform an authorization/security review.
- [ ] Load-test imports, analytics, and concurrent syncs.
- [ ] Simulate broker, market-data, e-mail, and Stripe outages.
- [ ] Run a restore drill and document recovery time.
- [ ] Record activation, retention, conversion, churn reasons, support load,
      and data cost per active user.

**Exit gate:** No unresolved critical security/data-integrity issue and the
economics support the proposed founder prices.

### Phase 5: public founder launch

- [ ] Publish Free, Investor EUR 4.99 / EUR 49, and Pro EUR 7.99 / EUR 79.
- [ ] Publish the founder-price promise and its exclusions plainly.
- [ ] Monitor sync reliability, activation, D7/D30 retention, trial-to-paid,
      churn, data cost, AI cost, and support tickets by cohort.
- [ ] Raise prices only for new customers after retention and support burden
      justify the change.

Working solo-developer estimate: approximately 3-5 months to a safe private
beta, excluding vendor-contract and legal-review delays.

---

## 11. Data licensing: launch blocker

The current `yfinance` path must not be treated as a commercial SaaS license.

- The [yfinance README](https://github.com/ranaroussi/yfinance/blob/main/README.md?plain=1)
  describes the tool as intended for research/education and Yahoo data as
  intended for personal use.
- [Yahoo Developer Guidelines](https://legal.yahoo.com/us/en/yahoo/guidelines/ydn/index.html)
  restrict non-commercial APIs in paid/hosted applications without suitable
  rights.
- [Yahoo Terms](https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html)
  also restrict unauthorized commercial exploitation.
- [Twelve Data business pricing](https://twelvedata.com/pricing-business) shows
  that client-facing display belongs to commercial plans.
- [EODHD terms](https://eodhd.com/financial-apis/terms-conditions) distinguish
  ordinary access from commercial display/redistribution rights.
- [Alpha Vantage terms](https://www.alphavantage.co/terms_of_service/) direct
  commercial users to an explicit commercial arrangement.

Vendor due diligence must obtain written answers for:

- commercial SaaS display rights;
- delayed/EOD versus real-time rights;
- exchange attribution requirements;
- caching and storage duration;
- derived analytics and PDF export;
- per-user/device limits;
- redistribution to customer browsers and mobile clients;
- historical and fundamental data coverage;
- EU data processing and subprocessors;
- termination and data-deletion obligations.

Recommended launch path: licensed delayed/EOD data in the included plans;
real-time exchange data only as a separately priced add-on if later demanded.

The private local Screener may keep a personal-use data path only on the
owner's home machine and only within that provider's terms. It must never be
proxied through the cloud, called by a cloud job, or used to populate a
customer-facing shared cache. Removing the Screener from cloud reduces bulk
query volume, but cloud stock details, prices, fundamentals, dividends, and
derived analytics still require suitable commercial rights.

---

## 12. Compliance and customer trust

### GDPR and privacy

- [ ] Define controller/processor roles and legal bases.
- [ ] Publish privacy notice and subprocessor list.
- [ ] Minimize collected financial and identity data.
- [ ] Implement machine-readable export.
- [ ] Implement verified account deletion and retention workflow.
- [ ] Encrypt data in transit and sensitive secrets at rest.
- [ ] Define breach/incident handling and support identity verification.
- [ ] Keep analytics free of raw holdings, transactions, and credentials by
      default.

Reference: [European Commission GDPR principles](https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/principles-gdpr_en).

### VAT and billing

- [ ] Display applicable consumer VAT correctly.
- [ ] Collect billing-country evidence required by the selected VAT flow.
- [ ] Support invoices/receipts, refunds, cancellation, and billing history.
- [ ] Register/use OSS or select an equivalent compliant operational model.
- [ ] Have a Czech accountant/lawyer review the final billing flow.

Reference: [EU VAT One Stop Shop](https://europa.eu/youreurope/business/finance-and-tax/vat/one-stop-shop/).

### Cloud financial wording and local-only tax tooling

- [ ] Cloud marketing, pricing, onboarding, trials, plan metadata, e-mails, and
      support documentation make no Tax Report claim.
- [ ] Cloud route/OpenAPI tests prove that the local tax endpoint is absent.
- [ ] The private local Tax Report is visibly labeled as an owner-only
      experimental calculation, not tax advice or a customer product.
- [ ] Keep local tax rules and fixtures versioned by year if the owner continues
      relying on the report, but do not make this a cloud launch gate.
- [ ] Display assumptions, unresolved data quality, and excluded asset types in
      the local Tax Report.
- [ ] Distinguish cloud portfolio analytics/AI explanations from regulated
      personalized investment advice.
- [ ] Any future proposal to offer tax reporting in cloud requires a new product
      decision, professional review, updated licensing/compliance scope, and a
      revision of this master plan before implementation.

---

## 13. Economics and metrics

### Price-floor considerations

Stripe's Czech pricing combines percentage and fixed payment fees, while
Stripe Billing adds a billing-volume fee:

- [Stripe Czech pricing](https://stripe.com/en-cz/pricing)
- [Stripe Billing pricing](https://stripe.com/en-cz/billing/pricing)

VAT, payment fees, market data, AI, e-mail, monitoring, backups, and support
all come out of the public customer price. This is why the launch plan does
not recommend a EUR 1.99-2.99 paid tier.

### Metrics to instrument

- Signup to verified e-mail.
- Verified e-mail to successful import/connect.
- Time to first useful dashboard/performance/dividend insight.
- Broker connection and scheduled-sync success rates.
- Import duplicate/reconciliation error rate.
- Trial activation and feature usage.
- Trial-to-paid conversion by acquisition source.
- D7 and D30 active retention.
- Monthly and annual-plan churn.
- Failed-payment recovery.
- Market-data and AI cost per active user and per plan.
- Support tickets per 100 active users.
- Local/cloud capability-denial errors, which should remain zero for ordinary
  cloud customer flows.
- Upgrade/downgrade reasons and cancellation reasons.

Do not optimize only for signup count. The primary product signal is a user
who imports real data, returns after the first week, and repeatedly receives a
trusted result or automated update.

---

## 14. Go/no-go checklist for accepting payments

Portfyl is ready to accept public payments only when every item below is true:

- [ ] Written commercial market-data rights cover the launched features.
- [ ] PostgreSQL is production source of truth and migrations are reversible
      or have a documented recovery path.
- [ ] Production-like backup restore has succeeded.
- [ ] Authentication supports verified users and revocable sessions.
- [ ] The complete Alice/Bob isolation test matrix passes.
- [ ] Broker, AI, and webhook secrets are encrypted and absent from logs.
- [ ] Background jobs are external, tenant-aware, and idempotent.
- [ ] Stripe webhook replay cannot duplicate or corrupt subscription state.
- [ ] Every plan capability and quota is backend-enforced.
- [ ] Cloud OpenAPI, frontend routes, navigation, pricing, help, and direct-URL
      tests expose neither Tax Report nor Screener.
- [ ] The private local build still exposes and tests Tax Report and Screener
      without requiring Stripe.
- [ ] Trial expiry downgrades without deleting data.
- [ ] Founder pricing behavior is covered by subscription tests.
- [ ] Privacy, terms, export, deletion, cancellation, and support flows work.
- [ ] Monitoring, incident response, and customer communication paths exist.
- [ ] A private beta found no unresolved critical security or data-integrity
      issue.
- [ ] Measured unit economics support Investor at EUR 4.99 and Pro at EUR
      7.99; otherwise pricing or included data must change before launch.

---

## 15. Immediate next actions

1. [ ] Approve the edition matrix: Tax Report and Screener are `local_only`;
       classify every other current page as local-only or cloud tier eligible.
2. [ ] Interview 10-15 target users and rank non-tax paid pains.
3. [ ] Request commercial-display quotes from at least three data providers for
       the exact remaining cloud feature set.
4. [ ] Publish/test the proposed Free, Investor, and Pro pricing page without
       Tax Report or Screener claims.
5. [ ] Write the focused edition/capability-boundary implementation plan.
6. [ ] Write the focused PostgreSQL migration plan.
7. [ ] Write the focused identity/workspace/tenant-isolation plan.
8. [ ] Write the focused encrypted-secrets/jobs and Stripe/entitlements plans.
9. [ ] Execute those plans in dependency order with test and review gates.
10. [ ] Run a 20-50-user private beta before public billing.

### Dependency order

```text
Cloud product validation + commercial data
                │
                ▼
Local/cloud edition boundary
                │
                ▼
PostgreSQL migration
                │
                ▼
Identity + workspace + tenant isolation
                │
                ├──────────────┐
                ▼              ▼
Secrets + external jobs   Unified onboarding
                │              │
                └──────┬───────┘
                       ▼
            Stripe + trial + entitlements
                       │
                       ▼
                Paid-value packaging
                       │
                       ▼
                 Private beta + launch
```

This order deliberately prevents billing and acquisition work from getting
ahead of edition isolation, authorization, data rights, and calculation trust.
