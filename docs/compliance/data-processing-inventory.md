# Portfyl Data Processing Inventory

Last technical review: 2026-09-08

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
- Cloudflare Access currently allows only that exact e-mail to reach
  `portfyl.com` by one-time PIN. The operator may add individually approved
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
- **Secrets:** broker credentials, Discord webhook URLs, and user-supplied AI
  keys use envelope encryption. Production key operations use Google Cloud
  KMS; secret configuration uses Google Secret Manager.

## Data categories

| Category | Examples and source | Primary storage | External processing or recipient | Current deletion/export behaviour |
|---|---|---|---|---|
| Identity | Firebase UID, normalized e-mail, display name, verification and disabled timestamps | Firebase Authentication and `users` | Google Firebase | Workspace export includes only safe membership metadata. The Portfyl/Firebase user is removed after deletion of the last workspace. |
| Sessions and security | Digests of opaque session and CSRF tokens, expiry/revocation/last-seen time, user agent | `auth_sessions` | Cloudflare and Cloud Run process request metadata in transit | Never exported. Cascades when the final Portfyl user is deleted. Expired/revoked-row cleanup policy remains to be fixed. |
| Workspace and membership | Workspace name/public UUID, role, status, timestamps | `workspaces`, `memberships` | Neon, Cloud Run | Exported with public identifiers. Sole-owner deletion cascades after a cancellable 30-day grace period; shared workspace deletion is refused. |
| Portfolio financial data | Portfolio metadata, transactions, tickers, quantities, prices, cash, currencies, dates, notes, FX rates | `portfolios`, `transactions`, `broker_balances`, `cash_interest_rates`, `options_trades`, `polymarket_positions`, `trade_notes` | Neon; selected tickers/date ranges are sent to market-data sources as needed | Core portfolio and transaction data is exported; current export schema intentionally does not yet include every derived/specialist table. Tenant rows cascade with workspace deletion. |
| Research and organization | Watchlists/items, benchmarks/components, price alerts | Corresponding workspace tables | Market-data providers when data is requested for a ticker | Watchlists/items and alerts are exported; benchmarks are currently outside export schema v1. Tenant rows cascade with workspace deletion. |
| Broker connections | Broker, environment, sync state/coverage, encrypted API credentials and key version, bounded operational state | `broker_connections` | Trading 212 or IBKR when the user connects/syncs | Export contains allow-listed connection metadata only. Credentials, ciphertext, key versions, and raw error text are excluded. Rows cascade with workspace deletion. |
| Notification integrations | Encrypted Discord webhook, notification preferences, delivery/dedup state and bounded errors | `discord_webhooks`, `dividend_notifications`, `notification_outbox` | Discord only when configured and triggered by the user | Secret URLs are never exported or logged. Workspace deletion cascades integration and queued delivery state. |
| User/workspace settings | Theme/display preferences, workspace configuration, deletion-request state | `user_settings`, `workspace_settings` | Normally none | Deletion state is not part of export v1. Workspace settings cascade with workspace; personal settings cascade with final user deletion. |
| Usage and abuse prevention | Capability metric/period/count, idempotency reservations, HMAC rate-limit identity/count/expiry | `usage_counters`, `usage_reservations`, `rate_limit_buckets` | Cloud Run/Neon; Cloudflare supplies edge/client-IP context | Not exported. Workspace usage rows cascade with workspace. Rate-limit buckets contain opaque HMAC keys, not raw IP/workspace IDs, and are deleted by bounded expiry cleanup. |
| Audit and jobs | Security action, actor, public target, bounded metadata, recurring-job status, migration validation/counts | `audit_logs`, `job_runs`, `data_migration_runs` | Neon and operator logs | Audit rows are RLS-scoped and cascade with actor/workspace deletion; no shadow copy of deleted financial data is kept. Global operational/migration record retention remains an operator decision. |
| Runtime logs | Correlation ID, route/status/timing, error classification, job outcome | Cloud Run logging | Google Cloud | Secret-shape redaction is enforced. Request bodies and raw portfolio payloads must not be logged. Production log-retention value remains an operator decision. |
| In-process market cache | Short-lived quote/fundamental responses keyed by market symbols/request parameters | Web-instance memory only | Yahoo/yfinance, Shibui Finance, SEC EDGAR or broker APIs depending on route | Not durable and not exported. Disappears on expiry or instance termination. Commercial cloud rights remain unresolved. |

## Current external services and roles to review

| Service | Implemented use | Classification needing legal confirmation | Data sent |
|---|---|---|---|
| Google Cloud Run, Logging, KMS, Secret Manager, Scheduler | Hosting, logs, encryption, secrets, scheduled jobs | Processor/subprocessor | Requests, operational metadata, encrypted/configuration material; application data is processed in memory. |
| Firebase Authentication | Registration, verified e-mail/password identity, re-authentication, identity deletion | Processor/subprocessor | E-mail, UID, display/verification/authentication data. Passwords go to Firebase, not Portfyl. |
| Neon | Managed PostgreSQL and PITR/branch recovery | Processor/subprocessor | All durable Portfyl database rows. |
| Cloudflare | DNS, TLS proxy, trusted-edge header and request protection | Processor/subprocessor | IP/network/request metadata and encrypted HTTP traffic at the edge. |
| Trading 212 / IBKR | Optional user-requested broker import/sync | Provider selected by the user; role/terms require review | Credential-authenticated account/trade requests and returned broker data. |
| Discord | Optional outbound notifications | Independent service selected by the user; role/terms require review | User-selected notification content sent to the configured webhook. |
| Yahoo/yfinance, Shibui Finance, SEC EDGAR | Market/fundamental/research data retrieval | Commercial-rights and privacy role unresolved for cloud launch | Tickers, date ranges, and request metadata; no broker credential or full portfolio is intentionally sent. |
| Hosted AI provider, when configured | Assistant responses | Processor/subprocessor and DPA/region review required before paid/public use | User prompt and the minimum context assembled for the request; exact provider/runtime configuration must be documented before enabling broadly. |

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
- In-process caches are TTL-bound or disappear with the instance.

### Must be decided and then enforced or documented

- Neon production PITR/backup retention and the treatment of deleted data in
  expiring backups.
- Cloud Run log retention and access policy.
- Expired/revoked authentication-session cleanup.
- Audit-log, job-run, migration-record, usage-reservation, notification-outbox,
  and broker-sync diagnostic retention.
- Support and security-incident evidence retention.
- Any legal/accounting record retention introduced with a future payment
  provider.

No open-ended period should be published until it matches both provider
configuration and application cleanup behaviour.

## Export/deletion coverage

JSON export schema version 2 includes workspace/membership, portfolios,
transactions, watchlists/items, alerts, safe broker metadata and balances,
custom benchmarks/components, options, Polymarket positions, trade notes,
cash-interest settings, notification preferences/history, user-configured
broker schedule values, and the non-secret assistant model preference.

Security/session data, audit/job/migration state, usage/rate-limit records,
deletion workflow state, operational sync timestamps, third-party market-data
caches, credentials, ciphertext/key versions, and raw internal IDs are
deliberately excluded. Revisit that boundary during legal review rather than
assuming every operational record is portable personal data.

Deletion is broader than export: tenant-table cascades also remove internal
workspace records that are intentionally not present in the portability bundle.

## Analytics and telemetry baseline

The 2026-09-07 dependency/source review found no product-analytics, advertising,
session-replay, or tracking SDK in the active frontend/backend runtime. Portfyl
uses operational logs, audit events, usage counters, and rate limits for service
operation and security. Introducing analytics requires a separate reviewed
event allow-list and must exclude raw holdings, transactions, free-text notes,
credentials, request bodies, and stable cross-service identifiers by default.

## Change-review trigger

Update this inventory in the same change whenever code adds or changes:

- a SQLAlchemy model/column or Alembic migration;
- an external API, SDK, infrastructure provider, cookie, or browser storage;
- logging, telemetry, monitoring, or support tooling;
- authentication, authorization, export, retention, or deletion behaviour;
- an e-mail, push, webhook, AI, payment, or market-data flow.
