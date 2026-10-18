# Portfyl Data Processing Inventory

Last technical review: 2026-10-18 (AI assistant removed)

This document describes the implemented Portfyl runtime. It is an engineering
record for privacy review, incident response, export/deletion maintenance, and
vendor due diligence. It is not a published privacy notice and does not choose
legal bases on behalf of the service operator.

## Current operator and release status

- The owner confirmed on 2026-09-08 that the service is currently a private,
  free test operated from the Czech Republic, with no payments and no public
  self-registration.
- `tom.zoubek@gmail.com` is the approved privacy, support, and security contact
  for this private-test stage.
- The public landing page is available at `portfyl.com`. Cloudflare Access
  currently allows only that exact e-mail to reach the complete
  `app.portfyl.com` tracker hostname by one-time PIN. The operator may add individually approved
  tester e-mails, but public sign-up and broad whole-domain/group Access rules
  remain outside the approved operating boundary.
- An admitted tester may select a workspace test plan in the Plans page. The
  selection is stored as a workspace setting and audited, but creates no
  payment, subscription, trial, invoice, or billing-customer record.
- No 18+ product restriction is intended. Because the current test admits no
  external users, the future child/minor contract, consent, parental-
  authorization, and child-readable-transparency design remains a public-
  launch gate.
- The controller's full legal identity, legal form, postal address, and any
  registration identifiers are not decided. Public legal pages remain gated;
  see `docs/compliance/private-test-legal-status.md`.

## System boundary

- **Cloud edition:** React/Vite SPA served by FastAPI on Google Cloud Run in an
  EU region, Cloudflare as the public DNS/TLS/reverse-proxy edge, Neon managed
  PostgreSQL as the source of truth, and Firebase Authentication for identity.
- **Local edition:** the same shared application and PostgreSQL data model run
  by the owner. It has no subscription requirement and additionally exposes
  the private Tax Report and Screener experiments.
- **Tenant boundary:** `User -> Membership -> Workspace`; tenant tables carry a
  workspace key and use application predicates plus forced PostgreSQL RLS.
- **Secrets:** broker credentials and Discord webhook URLs use envelope
  encryption. Production key operations use Google Cloud
  KMS; secret configuration uses Google Secret Manager.

## Data categories

| Category | Examples and source | Primary storage | External processing or recipient | Current deletion/export behaviour |
|---|---|---|---|---|
| Identity | Firebase UID, normalized e-mail, display name (from the Google profile name when the user signs in with Google), verification and disabled timestamps | Firebase Authentication and `users` | Google Firebase; Google account sign-in when the user chooses "Continue with Google" | Workspace export includes only safe membership metadata. The Portfyl/Firebase user is removed after deletion of the last workspace. |
| Sessions and security | Digests of opaque session and CSRF tokens, expiry/revocation/last-seen time, user agent | `auth_sessions` | Cloudflare and Cloud Run process request metadata in transit | Never exported. Cascades when the final Portfyl user is deleted. Expired/revoked rows are removed 30 days after becoming invalid. |
| Workspace and membership | Workspace name/public UUID, role, status, timestamps | `workspaces`, `memberships` | Neon, Cloud Run | Exported with public identifiers. Sole-owner deletion cascades after a cancellable 30-day grace period; shared workspace deletion is refused. |
| Portfolio financial data | Portfolio metadata, transactions, tickers, quantities, prices, cash, currencies, dates, notes, FX rates, current broker-reported open positions | `portfolios`, `transactions`, `broker_balances`, `broker_positions`, `cash_interest_rates`, `options_trades`, `polymarket_positions`, `trade_notes` | Neon; selected tickers/date ranges are sent to market-data sources as needed | Core portfolio and transaction data is exported, including the current `broker_positions` snapshot; current export schema intentionally does not yet include every derived/specialist table. `broker_positions` is replaced atomically on each sync and never substitutes for ledger data in historical/tax calculations. Tenant rows cascade with workspace deletion. |
| Research and organization | Watchlists/items, benchmarks/components, price alerts | Corresponding workspace tables | Market-data providers when data is requested for a ticker | Watchlists/items and alerts are exported; benchmarks are currently outside export schema v1. Tenant rows cascade with workspace deletion. |
| Broker connections | Broker, environment, sync state/coverage, keyed non-reversible upstream-account fingerprint, encrypted API credentials and key version, bounded operational state | `broker_connections`, `portfolios` | Trading 212 or IBKR when the user connects/syncs | Export contains allow-listed connection metadata and the opaque account fingerprint only. Raw provider account IDs, credentials, ciphertext, key versions, and raw error text are excluded. Rows cascade with workspace deletion. |
| Broker sync staging | Raw Trading 212 order-fill and dividend payloads staged for resumable history finalization and corporate-action review | `broker_sync_events`, linked to `broker_sync_runs` | Neon and Cloud Run; payloads originate from Trading 212 | Never logged or exported. Events for completed, failed, or cancelled runs are deleted after 14 days. Superseded `needs_review` evidence is deleted after 90 days, while the latest `needs_review` run per connection is retained as the local redacted-capture source. Non-terminal runs are never age-purged. Rows cascade with workspace deletion. |
| Notification integrations | Encrypted Discord webhook, notification preferences, delivery/dedup state and bounded errors | `discord_webhooks`, `dividend_notifications`, `notification_outbox` | Discord only when configured and triggered by the user | Secret URLs are never exported or logged. Workspace deletion cascades integration and queued delivery state. |
| User/workspace settings | Theme/display preferences, workspace configuration, deletion-request state | `user_settings`, `workspace_settings` | Normally none | Deletion state is not part of export v1. Workspace settings cascade with workspace; personal settings cascade with final user deletion. |
| Usage and abuse prevention | Capability metric/period/count, idempotency reservations, HMAC rate-limit identity/count/expiry | `usage_counters`, `usage_reservations`, `rate_limit_buckets` | Cloud Run/Neon; Cloudflare supplies edge/client-IP context | Not exported. Workspace usage rows cascade with workspace. Finalized/released reservations are deleted after 90 days; expired HMAC rate-limit buckets are deleted hourly. |
| Audit and jobs | Security action, actor, public target, bounded metadata, recurring-job status, migration validation/counts | `audit_logs`, `job_runs`, `data_migration_runs` | Neon and operator logs | Audit rows are RLS-scoped and cascade with actor/workspace deletion; no shadow copy of deleted financial data is kept. Global operational/migration record retention remains an operator decision. |
| Runtime logs | Correlation ID, route/status/timing, error classification, job outcome | Cloud Run logging | Google Cloud | Secret-shape redaction is enforced. Request bodies and raw portfolio payloads must not be logged. Production log-retention value remains an operator decision. |
| In-process market cache | Short-lived quote/fundamental responses keyed by market symbols/request parameters | Web-instance memory only | Yahoo/yfinance, Shibui Finance, SEC EDGAR or broker APIs depending on route | Not durable and not exported. Disappears on expiry or instance termination. Commercial cloud rights remain unresolved. |

## Current external services and roles to review

| Service | Implemented use | Classification needing legal confirmation | Data sent |
|---|---|---|---|
| Google Cloud Run, Logging, KMS, Secret Manager, Scheduler | Hosting, logs, encryption, secrets, scheduled jobs | Processor/subprocessor | Requests, operational metadata, encrypted/configuration material; application data is processed in memory. |
| Firebase Authentication | Registration, verified e-mail/password identity, optional Google sign-in (OAuth popup, `openid email profile` scopes only), re-authentication, identity deletion | Processor/subprocessor | E-mail, UID, display/verification/authentication data. Passwords go to Firebase, not Portfyl. For Google sign-in, Google returns the verified e-mail, name, and Google account identifier to Firebase. Portfyl stores only the e-mail and name, and receives no Google API access. The audit log records which sign-in method was used (`password` or `google.com`). |
| Neon | Managed PostgreSQL and PITR/branch recovery | Processor/subprocessor | All durable Portfyl database rows. |
| Cloudflare | DNS, TLS proxy, trusted-edge header and request protection | Processor/subprocessor | IP/network/request metadata and encrypted HTTP traffic at the edge. |
| Trading 212 / IBKR | Optional user-requested broker import/sync | Provider selected by the user; role/terms require review | Credential-authenticated account/trade requests and returned broker data. |
| Discord | Optional outbound notifications | Independent service selected by the user; role/terms require review | User-selected notification content sent to the configured webhook. |
| Yahoo/yfinance, Shibui Finance, SEC EDGAR | Market/fundamental/research data retrieval | Commercial-rights and privacy role unresolved for cloud launch | Tickers, date ranges, and request metadata; no broker credential or full portfolio is intentionally sent. |
| PostHog Cloud EU, implemented but not yet enabled in any deployed environment | Consent-gated product-analytics events measuring public-demo and registered-user activation funnels; see `docs/operations/posthog-activation-analytics.md` | Processor/subprocessor; consent basis (rejected traffic sends cookieless aggregate events by design) is subject to qualified Czech/EU legal review before the integration may be enabled | Only the frozen 12-event allow-list in `frontend/src/analytics/eventContract.js` with each event's own allow-listed properties (language/referrer/UTM-source class, demo page/symbol, source surface/type, creation path); for accepted consent only, an opaque Portfyl user id via `identify()`. Never e-mail, display name, workspace name/ID, portfolio ID, holdings, transactions, balances, free-text notes, or credentials. EU region (`eu.i.posthog.com`), one-year retention, session replay/surveys/feature-flags/exception-autocapture all disabled. |

Public pricing or an accessible API is not evidence of commercial display or
redistribution permission. The market-data workstream remains a launch blocker.

## Retention status

### Enforced in code

- A user-requested workspace deletion has a 30-day cancellable grace period.
- Only an explicit, freshly re-authenticated sole-owner request schedules it;
  plan or trial state never does.
- Workspace-owned rows cascade when the due purge runs. The Firebase/Portfyl
  identity is deleted only after the last workspace membership is gone.
- Rate-limit buckets have an expiry timestamp and a bounded cleanup job.
- Expired/revoked session rows are removed after 30 days; finalized/released
  usage reservations and completed/terminal notification-outbox rows are
  removed after 90 days; dividend-notification deduplication rows are removed
  after 400 days. Each category is bounded to 10,000 deletions per daily run.
- Staged broker events are removed 14 days after terminal completion, or after
  90 days for superseded `needs_review` runs. The latest `needs_review` run per
  connection and every non-terminal run remain available.
- In-process caches are TTL-bound or disappear with the instance.

### Approved current private-test baseline

- The exact periods, event-based rules, provider settings, cleanup bounds, and
  public-review triggers are recorded in
  [private-test-retention-policy.md](private-test-retention-policy.md).
- Neon PITR is six hours for the current private test. Cloud Logging is 30 days
  in `_Default` and 400 days in the locked `_Required` bucket.
- Audit and migration records remain for the associated user/workspace lifetime
  and cascade on deletion. `job_runs` holds only the latest success per job.
- Support and incident records are deleted 365 days after closure unless a
  documented legal hold applies.

Public/beta legal adequacy, accounting retention, and a longer recovery
objective remain separate approval gates.

## Export/deletion coverage

JSON export schema version 2 includes workspace/membership, portfolios,
transactions, watchlists/items, alerts, safe broker metadata and balances,
custom benchmarks/components, options, Polymarket positions, trade notes,
cash-interest settings, notification preferences/history, user-configured
and broker schedule values. (Schema version 6, 2026-10-18, dropped the
`user_preferences` block that only held the removed AI assistant's model
preference; migration `0024_remove_ai_assistant` deleted the stored DeepSeek
keys, model preferences, and hosted-AI quota rows.)

Security/session data, audit/job/migration state, usage/rate-limit records,
deletion workflow state, operational sync timestamps, third-party market-data
caches, credentials, ciphertext/key versions, and raw internal IDs are
deliberately excluded. Revisit that boundary during legal review rather than
assuming every operational record is portable personal data.

Deletion is broader than export: tenant-table cascades also remove internal
workspace records that are intentionally not present in the portability bundle.

## Analytics and telemetry baseline

The 2026-09-07 dependency/source review found no product-analytics, advertising,
session-replay, or tracking SDK in the active frontend/backend runtime. That
baseline has since changed: a consent-gated PostHog Cloud EU integration was
implemented on 2026-09-19 to measure public-demo and registered-user
activation funnels. The reviewed event allow-list and forbidden-data
exclusions anticipated by the prior baseline are now the enforced-in-code
contract at `frontend/src/analytics/eventContract.js`
(`sanitizeEvent()` rejects any event name outside the frozen 12-event list
and drops any property outside that event's own schema) — see the PostHog
row in the external-services table above and
`docs/operations/posthog-activation-analytics.md` for the full runbook,
allow-list, and forbidden-data list. Portfyl otherwise continues to use
operational logs, audit events, usage counters, and rate limits for service
operation and security, unrelated to this product-analytics integration.

**Production blocker:** `VITE_POSTHOG_KEY` and `VITE_POSTHOG_HOST` must
remain unset in every deployed environment until the public privacy notice
and subprocessor disclosure covering PostHog Cloud EU has received
qualified Czech/EU legal review and is published. This implementation does
not draft or publish that legal text. Until the gate is lifted, the
frontend's `AnalyticsProvider` falls back to a no-op adapter in every built
(non-dev, non-test) bundle regardless of a visitor's consent choice, so no
event reaches PostHog from any live deployment today. This mirrors the
existing pattern above for the controller-identity and child-consent gates:
implemented in code, deliberately withheld from the live environment
pending an explicit legal sign-off.

## Change-review trigger

Update this inventory in the same change whenever code adds or changes:

- a SQLAlchemy model/column or Alembic migration;
- an external API, SDK, infrastructure provider, cookie, or browser storage;
- logging, telemetry, monitoring, or support tooling;
- authentication, authorization, export, retention, or deletion behaviour;
- an e-mail, push, webhook, AI, payment, or market-data flow.
