# Portfyl Data Processing Inventory

Last technical review: 2026-11-24 (withdrawal/full-refund policy and deletion with a subscription, retention of unfinished registrations, trial fingerprints with a documented balancing test, `stripe_events`, export schema 9; earlier: 2026-11-22 Stripe Managed Payments billing, Brevo transactional e-mail, immediate account deletion, retention periods and the Terms-acceptance record; 2026-11-19 free-trial guards and Turnstile bot check; 2026-10-18 AI assistant removed)

> **WARNING - Sentry.** The code can optionally send error reports to Sentry
> (`SENTRY_DSN` for the backend, `VITE_SENTRY_DSN` baked into the frontend
> build; `backend/error_monitoring.py`, `frontend/src/errorMonitoring.js`). It
> is **not enabled in production**, and the public privacy policy deliberately
> does not mention it. **Do not set either variable until the privacy policy
> (CS and EN), its recipients and transfers sections and this inventory have
> been updated and published.**

This document describes the implemented Portfyl runtime. It is an engineering
record for privacy review, incident response, export/deletion maintenance, and
vendor due diligence. It is not a published privacy notice and does not choose
legal bases on behalf of the service operator.

## Current operator and release status

- The service is operated from the Czech Republic. On 2026-09-08 the owner
  confirmed a private, free test with no payments and no public
  self-registration; the code has since gained Stripe Managed Payments billing
  (below). Billing stays off until `PORTFYL_BILLING_ENABLED=1`
  (`backend/billing_config.py`); until then the no-payment test-plan switch is
  the only way to change plans. Whether the public launch has happened is an
  operator decision recorded outside this file; treat the statements below
  about Cloudflare Access as the last documented state, not as a guarantee.
- `support@portfyl.com` is the privacy, support, and security contact (operator
  decision recorded in `docs/legal/poznamky-pro-pravnika.md`; the private-test
  stage used a private mailbox that is no longer the contact).
- The public landing page is available at `portfyl.com`. Cloudflare Access
  currently allows only that exact e-mail to reach the complete
  `app.portfyl.com` tracker hostname by one-time PIN. The operator may add individually approved
  tester e-mails, but public sign-up and broad whole-domain/group Access rules
  remain outside the approved operating boundary.
- While billing is off, an admitted tester may select a workspace test plan in
  the Plans page. The selection is stored as a workspace setting and audited,
  but creates no payment, subscription, trial, invoice, or billing-customer
  record. Once billing is on, that switch is unmounted and ignored.
- Paid plans (Investor EUR 5.99, Pro EUR 9.99 per month, VAT included) are sold
  through **Stripe Managed Payments**: Stripe/Link is the merchant of record
  and acts as an independent controller for the payment itself (role needs
  legal confirmation). Every new cloud workspace also gets a 10-day Pro trial
  without a card (`backend/trials.py`, migration `0027_free_trial`).
- The Service is for people aged at least 18 only (privacy policy "Children"
  section and terms). This is a contractual condition, not a GDPR Art. 8 /
  Section 7 of Act 110/2019 age rule, because the main legal basis is contract.
  Registration requires confirming 18+ and acceptance of the Terms and Privacy
  Policy (`frontend/src/pages/Register.jsx`). The server records that
  confirmation with the terms and privacy-notice versions and the time in
  `terms_acceptances` (`backend/legal_acceptance.py`, migration
  `0029_terms_acceptances`); the checkout consent is audited separately
  (`billing.checkout.created`, `consent_version`).
- The controller is Jakub Zoubek, IČO 67772366, Brusinková 1983, 252 28
  Černošice (as named in the draft privacy policy, 2026-11-06). Public legal
  pages remain gated until a Czech lawyer approves them; see
  `docs/compliance/private-test-legal-status.md`.

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
| Terms acceptance at sign-up | Terms version, privacy-notice version, "18 or older" confirmation, acceptance time (UTC) and sign-up path (e-mail or Google), written by the server only. For e-mail sign-up the Firebase UID is kept until the first sign-in links the row to the Portfyl user. The privacy notice is information (GDPR art. 13), not consent: the row records which text was shown | `terms_acceptances` (user-level, no tenant policy) | Neon, Cloud Run | Included in the workspace export (`legal_acceptance`). Deleted with the account (`user_id` cascades). Accounts created before this record have none. A pending row (never linked to a user) is removed 30 days after `accepted_at` by the daily `account_deletion_cleanup` job (`legal_acceptance.purge_stale_pending`, `PENDING_ACCEPTANCE_MAX_AGE_DAYS = 30`; implemented on the 2026-11-24 branch `fix/gdpr-signup-cleanup`, confirm after merge). Privacy Policy Section 6 states 30 days. |
| Sessions and security | Digests of opaque session and CSRF tokens, expiry/revocation/last-seen time, user agent | `auth_sessions` | Cloudflare and Cloud Run process request metadata in transit | Never exported. Cascades when the final Portfyl user is deleted. Expired/revoked rows are removed 30 days after becoming invalid. |
| Workspace and membership | Workspace name/public UUID, role, status, timestamps | `workspaces`, `memberships` | Neon, Cloud Run | Exported with public identifiers. Sole-owner deletion is immediate and cascades at once (`backend/account_deletion.py`; no grace period, no undo); shared workspace deletion is refused. |
| Portfolio financial data | Portfolio metadata, transactions, tickers, quantities, prices, cash, currencies, dates, notes, FX rates, current broker-reported open positions | `portfolios`, `transactions`, `broker_balances`, `broker_positions`, `cash_interest_rates`, `options_trades`, `polymarket_positions`, `trade_notes` | Neon; selected tickers/date ranges are sent to market-data sources as needed | Core portfolio and transaction data is exported, including the current `broker_positions` snapshot; current export schema intentionally does not yet include every derived/specialist table. `broker_positions` is replaced atomically on each sync and never substitutes for ledger data in historical/tax calculations. Tenant rows cascade with workspace deletion. |
| Research and organization | Watchlists/items, benchmarks/components, price alerts | Corresponding workspace tables | Market-data providers when data is requested for a ticker | Watchlists/items and alerts are exported; benchmarks are currently outside export schema v1. Tenant rows cascade with workspace deletion. |
| Allocation targets and broker requests | Target allocation percentages; broker names the user asks Portfyl to support (free text typed by the user) | `allocation_targets` (migration 0023), `broker_requests` (migration 0026) | Neon, Cloud Run | Both are in the JSON export (schema 9). Rows cascade with workspace deletion. |
| Broker connections | Broker, environment, sync state/coverage, keyed non-reversible upstream-account fingerprint, encrypted API credentials and key version, bounded operational state | `broker_connections`, `portfolios` | Trading 212 or IBKR when the user connects/syncs | Export contains allow-listed connection metadata and the opaque account fingerprint only. Raw provider account IDs, credentials, ciphertext, key versions, and raw error text are excluded. Rows cascade with workspace deletion. |
| Broker sync staging | Raw Trading 212 order-fill and dividend payloads staged for resumable history finalization and corporate-action review | `broker_sync_events`, linked to `broker_sync_runs` | Neon and Cloud Run; payloads originate from Trading 212 | Never logged or exported. Events for completed, failed, or cancelled runs are deleted after 14 days. Superseded `needs_review` evidence is deleted after 90 days, while the latest `needs_review` run per connection is retained as the local redacted-capture source. Non-terminal runs are never age-purged. Rows cascade with workspace deletion. |
| Notification integrations | Encrypted Discord webhook, notification preferences, delivery/dedup state and bounded errors | `discord_webhooks`, `dividend_notifications`, `notification_outbox` | Discord only when configured and triggered by the user | Secret URLs are never exported or logged. Workspace deletion cascades integration and queued delivery state. |
| User/workspace settings | Theme/display preferences, workspace configuration, deletion-request state | `user_settings`, `workspace_settings` | Normally none | Deletion state is not part of export v1. Workspace settings cascade with workspace; personal settings cascade with final user deletion. |
| Usage and abuse prevention | Capability metric/period/count, idempotency reservations, HMAC rate-limit identity/count/expiry | `usage_counters`, `usage_reservations`, `rate_limit_buckets` | Cloud Run/Neon; Cloudflare supplies edge/client-IP context | Not exported. Workspace usage rows cascade with workspace. Finalized/released reservations are deleted after 90 days; expired HMAC rate-limit buckets are deleted hourly. |
| Trial record | Start and end time, `ended_reason` of the workspace's free Pro trial | `trial_grants` (tenant, RLS) | Neon, Cloud Run | Not exported. Cascades with the workspace. |
| Trial guard: mailbox | HMAC-SHA256 (keyed, version- and purpose-separated) of the canonical e-mail (lower-case, no `+tag`, Gmail dots and `googlemail.com` folded) and the grant time. No raw e-mail | `trial_identities` (global, no tenant link) | Neon | Not exported. **Survives account deletion by design** (one trial per mailbox). Purged 365 days after the grant by the daily `account_deletion_cleanup` job (`trials.IDENTITY_RETENTION`). Legal basis: legitimate interest; balancing test in [trial-fingerprint-balancing-test.md](trial-fingerprint-balancing-test.md), which also records the OPEN owner decision to shorten the period (for example to 90 days). Objection/erasure: the operator recomputes the hash from the e-mail the person supplies and deletes the row (manual). |
| Trial guard: network | HMAC of the client IP (IPv6 reduced to /64) and the grant time. No raw IP | `trial_ip_marks` (global) | Neon | Not exported. Purged 30 days after the grant by `account_deletion_cleanup`. |
| Trial guard: broker | HMAC of the broker account fingerprint, or of each of the 5 oldest imported transaction keys (source, stream, event id), the kind and first-seen time; workspace link is cleared when the workspace is deleted | `trial_broker_marks` (global) | Neon | Not exported. Survives account deletion by design. Purged 365 days after first sight by `account_deletion_cleanup` (`trials.BROKER_MARK_RETENTION`). Same legal basis, balancing test and open retention decision as the mailbox guard. |
| Trial withheld marker | Workspace setting `trial_withheld` = `1`, written when a guard withheld the trial; carries no reason | `workspace_settings` (tenant, RLS) | Neon | Cascades with the workspace. The reason is only in the `trial.withheld` audit event. |
| Terms acceptance record | Confirmation of age 18+, terms version, privacy-notice version shown, time, source (`email_signup` or `google_signup`), Firebase UID for the pending row written before the e-mail is verified | `terms_acceptances` (user-level, no tenant policy) | Neon | Deleted with the user on account deletion; included in the export. A pending row whose e-mail is never verified has no purge yet (open item). |
| Billing: customer and subscription | Stripe customer ID, Stripe subscription ID and price ID, plan, status, period end, scheduled plan change, grace and end timestamps | `billing_customers`, `subscriptions` (tenant, RLS; migration `0025_stripe_billing`) | Neon; Stripe (see external services) | Not exported. Cascade with the workspace, so deleting an account removes Portfyl's copy; Stripe/Link keeps its own records as a separate controller (receipts, payments, refunds). Portfyl itself issues no invoices. Deleting a workspace that has a renewing subscription requires the owner's explicit consent to cancel it: within 14 days of the first paid order the cancellation is a withdrawal and every payment is refunded in full, later the subscription is cancelled without refund of the remaining period (decision 2026-11-24; code on branch `feat/withdrawal-refund`, see `docs/operations/withdrawal-refund.md`). No card data is ever received or stored. |
| Billing: webhook receipts | Stripe event ID, type, related object ID (a Stripe customer/subscription/invoice id, so a pseudonymous identifier of a data subject), status, attempts, last error. No payload and no name or e-mail | `stripe_events` (global, outside RLS) | Neon | Not exported. **Not removed by workspace deletion and no retention job exists yet** (operator decision pending; the Privacy Policy marks the period as to be filled in). Candidate rule: purge a fixed number of days after `processed_at`. |
| Billing: checkout consent audit | Plan, immediate-start consent flag and consent version at checkout | `audit_logs` (`billing.checkout.created`) | Neon | Follows audit-log retention. |
| Transactional e-mail | Recipient e-mail address and message content of the verification, password-reset, password-changed and account-deleted e-mails (a fifth kind, `account_deletion_scheduled`, exists in the catalog but is no longer sent). No outbox, no retry and no copy are stored; logs carry only kind, language and a reason code | none (outbound call from Cloud Run to Brevo; Firebase's fallback e-mails also pass through Brevo SMTP) | Brevo (see external services) | Not applicable. Retention at Brevo is not under Portfyl's control. |
| Sign-up bot check | Turnstile token and the client IP, sent once to Cloudflare siteverify when a new identity would be created. Nothing is stored; only a reason code is logged on failure | none (outbound call from Cloud Run) | Cloudflare (`challenges.cloudflare.com`); the widget runs in the browser | Not applicable. Role of Cloudflare for Turnstile (processor or independent controller) needs legal confirmation. |
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
| Stripe Managed Payments (Stripe/Link as merchant of record) | Checkout, Customer Portal, signed webhook, daily reconcile job (`backend/stripe_client.py`, `routers/billing.py`, `billing_sync.py`) | Merchant of record and independent controller for the payment; Portfyl also sends it data. Role and transfer position need legal confirmation | **Sent by Portfyl:** the account e-mail address (customer create), the workspace public UUID (customer metadata, checkout `client_reference_id`, subscription metadata), the plan (checkout metadata) and the price ID. The customer enters card data directly at Stripe. **Received:** customer, subscription, invoice and checkout events and objects. |
| Brevo (France) | Transactional e-mail over the HTTPS API `api.brevo.com` (`backend/emails/transport.py`, `routers/auth_email.py`, `emails/notify.py`); Firebase's fallback e-mails also go out through Brevo SMTP | Processor. DPA, processing location and transfers outside the EEA are not verified (open item) | Recipient e-mail address and the rendered message (subject, text, HTML with a one-time link or the event date/time), sender `noreply@mail.portfyl.com`, tag = e-mail kind. Brevo rewrites links for click tracking (`sendibt2.com`, see `deploy/cloudrun.md`). The API key is in Secret Manager (`portfyl-brevo-api-key`). Without the key the mailer is off and Firebase's own e-mails are used. |
| Trading 212 / IBKR / eToro (API sync) and Degiro, XTB (file import only) | Optional user-requested broker import/sync | Provider selected by the user; role/terms require review | Credential-authenticated account/trade requests and returned broker data. |
| Discord | Optional outbound notifications | Independent service selected by the user; role/terms require review | User-selected notification content sent to the configured webhook. |
| Yahoo/yfinance, Shibui Finance, SEC EDGAR | Market/fundamental/research data retrieval | Commercial-rights and privacy role unresolved for cloud launch | Tickers, date ranges, and request metadata; no broker credential or full portfolio is intentionally sent. |
| PostHog Cloud EU, implemented but not yet enabled in any deployed environment | Consent-gated product-analytics events measuring public-demo and registered-user activation funnels; see `docs/operations/posthog-activation-analytics.md` | Processor/subprocessor; consent basis; nothing is sent while consent is pending or rejected (the SDK is not even imported; changed 2026-11-06 after the privacy review, finding A1) | Only the frozen 12-event allow-list in `frontend/src/analytics/eventContract.js` with each event's own allow-listed properties (language/referrer/UTM-source class, demo page/symbol, source surface/type, creation path); an opaque Portfyl user id via `identify()` (the data is therefore pseudonymous, not anonymous). Never e-mail, display name, workspace name/ID, portfolio ID, holdings, transactions, balances, free-text notes, or credentials. EU region (`eu.i.posthog.com`), one-year retention, session replay/surveys/feature-flags/exception-autocapture all disabled. |

Public pricing or an accessible API is not evidence of commercial display or
redistribution permission. The market-data workstream remains a launch blocker.

## Retention status

### Enforced in code

- A user-requested workspace deletion is **immediate** and cannot be undone
  (changed 2026-11-18; `delete_workspace_now` in `backend/account_deletion.py`).
  It requires a sole owner, the typed workspace name, a fresh re-authentication
  (within 5 minutes) and no renewing subscription; plan or trial state never
  triggers it. The earlier 30-day cancellable grace period no longer exists;
  the daily job only completes requests scheduled before the change.
- Workspace-owned rows cascade in the same request. The Firebase/Portfyl
  identity is deleted in that request when the last workspace membership is
  gone, and an `account_deleted` e-mail is then sent best-effort through Brevo.
- Trial-guard hashes survive deletion by design and are purged by the daily
  `account_deletion_cleanup` job: e-mail and broker hashes after 365 days, IP
  hashes after 30 days. The 365-day period is under review (open owner
  decision in [trial-fingerprint-balancing-test.md](trial-fingerprint-balancing-test.md)).
- Pending Terms-acceptance rows that were never linked to a user (unfinished
  e-mail registration) are removed after 30 days by the same job (see the
  Terms acceptance row above).
- `stripe_events` has no retention job yet (see its row above).
- Rate-limit buckets have an expiry timestamp and a bounded cleanup job.
- Expired/revoked session rows are removed after 30 days; finalized/released
  usage reservations and completed/terminal notification-outbox rows are
  removed after 90 days; dividend-notification deduplication rows are removed
  after 400 days. Each category is bounded to 10,000 deletions per daily run.
- Staged broker events are removed 14 days after terminal completion, or after
  90 days for superseded `needs_review` runs. The latest `needs_review` run per
  connection and every non-terminal run remain available.
- In-process caches are TTL-bound or disappear with the instance.

### Approved technical baseline (set during the private test; see its status note)

- The exact periods, event-based rules, provider settings, cleanup bounds, and
  public-review triggers are recorded in
  [private-test-retention-policy.md](private-test-retention-policy.md).
- Neon PITR is six hours today. The privacy policy states the public maximum
  as **7 days** for deleted data in recovery backups ("at most 7 days"), which
  is true both now (6 hours) and after the planned move to 7 days; do not
  lengthen recovery history beyond 7 days without updating the policy. Cloud
  Logging is 30 days in `_Default` and 400 days in the locked `_Required`
  bucket.
- Audit and migration records remain for the associated user/workspace lifetime
  and cascade on deletion. `job_runs` holds only the latest success per job.
- Support and incident records are deleted 365 days after closure unless a
  documented legal hold applies.

Public/beta legal adequacy, accounting retention, and a longer recovery
objective remain separate approval gates.

## Export/deletion coverage

JSON export schema version 9 (`backend/workspace_export.py`, `EXPORT_SCHEMA_VERSION`) includes
workspace/membership, portfolios, transactions, watchlists/items, alerts, safe
broker metadata and balances, custom benchmarks/components, options,
Polymarket positions, trade notes, cash-interest settings, notification
preferences/history, user-configured and broker schedule values, allocation
targets, broker requests, the workspace's free-trial dates (schema 8) and
the Terms acceptance record (schema 9, 2026-11-22). (Schema version 6, 2026-10-18, dropped the
`user_preferences` block that only held the removed AI assistant's model
preference; migration `0024_remove_ai_assistant` deleted the stored DeepSeek
keys, model preferences, and hosted-AI quota rows.) Billing records
(`billing_customers`, `subscriptions`) are not exported.

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

## Related

- Architecture: [[Account deletion and data lifecycle]] · [[Secrets and security]] · [[Database and migrations]]
- Code: [[data_retention]] · [[workspace_export]] · [[account_deletion]] · [[secrets_crypto]] · [[audit]] · [[error_monitoring]] · [[emails.transport]]
- Docs: [[legal/privacy-policy-en]] · [[legal/zasady-ochrany-osobnich-udaju-cs]]
