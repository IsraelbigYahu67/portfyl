# Portfyl private-test retention policy

Effective: 2026-09-09

Scope: the free, invitation-only private test described in
`private-test-legal-status.md`. This is the implemented technical baseline for
the current operator-only environment. It is not a public privacy notice and
does not approve legal bases, public processing, payments, or retention for a
future commercial service.

## Approved technical periods

| Record | Retention and deletion rule |
| --- | --- |
| Live workspace and portfolio data | Retained while the workspace exists. An explicit, freshly reauthenticated sole-owner deletion request has a 30-day cancellation period, then the daily cleanup deletes the workspace and all cascading tenant data. |
| Neon recovery history | The current six-hour PITR history is accepted for the private test. Deleted rows can remain recoverable until that rolling history expires. Recovery branches are deleted immediately after a successful drill unless an active incident record requires otherwise. A public beta requires a separately approved recovery objective and at least seven days of recoverability where the selected Neon plan supports it. |
| Portfyl authentication sessions | A session is valid for at most 30 days. Expired or revoked rows are deleted 30 days after they became invalid, in a bounded daily cleanup. |
| Rate-limit buckets | Retained until their configured window expires, then removed by the bounded hourly cleanup. Keys are HMAC digests rather than raw IP or workspace identifiers. |
| Usage reservations | Open reservations remain until finalized or released. Finalized and released rows are deleted after 90 days by the bounded daily cleanup. Usage counters remain for the workspace lifetime pending public billing/metrics design. |
| Notification outbox | Pending and retryable rows remain until resolved. Sent rows and terminal failures are deleted after 90 days. |
| Dividend notification deduplication | Deleted after 400 days, long enough to prevent repeat annual-date notifications. |
| Audit events | Retained for the user/workspace lifetime and removed by the existing user/workspace cascade. This event-based period preserves the current private-test security trail; public use requires legal review and may replace it with a fixed period. |
| Recurring-job health | One latest-success row per job; updates replace the previous timestamp, so history does not accumulate in the database. Scheduler execution logs follow Cloud Logging retention. |
| Migration records | Retained with the associated workspace and deleted by workspace cascade. They are bounded by explicit migration executions rather than request volume. |
| Cloud Logging `_Default` | 30 days, as verified in production on 2026-09-09. Application logging excludes request bodies, holdings, transaction payloads, and secrets. |
| Cloud Logging `_Required` | 400 days, provider-managed and locked for Google Cloud administrative audit records. |
| Support and incident records outside the application | Delete 365 days after closure, unless a documented legal claim or statutory duty requires a longer hold. Do not copy raw financial data or credentials into these records. |
| Artifact Registry images | Keep the five newest images, all images younger than seven days, and images carrying `production` or `rollback` tags. Move/remove protected tags as part of each release. |

The daily application cleanup processes at most 10,000 rows per category per
run. A remaining backlog is handled by later idempotent runs. Active sessions,
open usage reservations, pending/retryable notifications, customer financial
records, and audit evidence are excluded from age-only cleanup.

## Review triggers

Review and replace this private-test policy before any of these changes:

- admitting external beta users or relaxing Cloudflare Access;
- publishing a privacy notice or consumer terms;
- accepting payment or creating accounting records;
- adding marketing, analytics, session replay, support tooling, or a new
  processor/subprocessor;
- changing the Neon plan, recovery objective, log buckets, deletion workflow,
  or data model.

The public review must confirm controller identity, legal bases, processor
agreements, international transfers, data-subject request handling, recovery
needs, incident evidence, and statutory retention. The current six-hour PITR
acceptance applies only to the private test.
