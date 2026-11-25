---
type: hub
layer: cross
tags: [arch/hub]
generated: false
---
# Free trial

Every new cloud workspace can get a 10-day Pro trial without entering a card. The trial exists so a new investor can try broker sync and analytics before paying. It is Portfyl-owned state, not a Stripe feature, so it can be granted, ended and audited without any payment provider. Because a trial costs nothing, there are guards that stop one person from collecting many trials. The trial exists only in the cloud edition.

A guard that fails never blocks sign-up. The workspace simply starts on Free, and the app can say that a trial was already used (it never says which guard fired).

## How it works
- **Granting**: when a new workspace is created in the cloud edition, `_provision_identity` in [[routers.auth]] calls `grant_trial` in [[trials]]. The length comes from `PORTFYL_TRIAL_DAYS` (default 10, `0` turns trials off). The registration page also runs a bot check ([[turnstile]], [[auth.TurnstileWidget]]).
- **Guards at sign-up** (checked in this order by `trial_block_reason`): the e-mail domain is on a disposable-domain list, the canonical e-mail already had a trial, or 3 trials were already granted from the same IP within 30 days. A failed guard writes a `trial.withheld` event to the [[audit]] log (reason only) and the workspace setting `trial_withheld`.
- **Fingerprints, never raw data**: e-mails, IPs and broker account numbers are stored only as HMAC fingerprints. The HMAC key is read from `PORTFYL_TRIAL_FINGERPRINT_KEY`; it is required while trials are on and must be at least 32 characters. The global guard rows survive account deletion on purpose (one trial per mailbox) and are purged on a schedule.
- **Broker check**: the broker account is unknown at sign-up, so `check_broker` in [[trials]] runs for a workspace whose trial is active after every CSV import commit ([[routers.portfolio]]), every Trading 212 connect ([[routers.broker]]), and every IBKR or eToro sync ([[routers.ibkr]], [[routers.etoro]]). If the same broker account, or the same oldest ledger history, was already seen in another trial, the trial ends early with a reason (`broker_account_reused` or `history_reused`). IBKR paper accounts and Trading 212 demo accounts are skipped. The check is best effort inside a savepoint, so it can never fail an import.
- **Using the trial**: [[entitlements]] asks `trial_state`. While a grant is active the workspace is treated as Pro; afterwards it falls back to Free with an "ended" reason. A live subscription always wins (see [[Billing and Stripe]]).
- **Cleanup**: the daily account-deletion cleanup pass in [[jobs]] calls `purge_trial_records`: identities and broker marks after 12 months, IP marks after 30 days. See [[Jobs and Cloud Scheduler]].
- **Frontend**: [[lib.trial]] turns the `/api/billing/status` payload into a phase (active, ended, not eligible). [[components.billing (folder)]] holds the `TrialBanner` countdown, and [[pages.Pricing]] shows the same message. The landing page ([[pages.Welcome]]) advertises the trial.

## Key code
- [[trials]]: grant, abuse guards, lookup, broker check and purge. The only module that writes the trial tables.
- [[entitlements]]: calls `trial_state` when resolving the plan.
- [[routers.auth]]: grants the trial when it creates a new cloud user and workspace.
- [[account_identity]]: builds the broker account fingerprints.
- [[turnstile]]: bot check at registration.
- [[jobs]]: the cleanup pass that purges old guard rows.
- [[lib.trial]]: frontend phase and message logic.
- [[pages.Pricing]]: shows trial status and the upgrade path.
- [[components.billing (folder)]]: trial banner component.

## Data
- [[trial_grants (table)]]: one row per workspace, with start, end and optional ended reason. Tenant table with forced RLS.
- [[trial_identities (table)]]: global, fingerprint of each e-mail that ever had a trial.
- [[trial_ip_marks (table)]]: global, one row per trial granted from an IP fingerprint.
- [[trial_broker_marks (table)]]: global, broker account or history fingerprints seen during a trial.
- [[0027_free_trial]]: creates all four tables (additive only, safe while older instances run).
- [[0010_billing_entitlements]]: the earlier migration that first introduced `trial_grants`.

## Related hubs
- [[Billing and Stripe]]
- [[Broker importers and sync]]
- [[Auth and sessions]]
- [[Tenancy and RLS]]
- [[Secrets and security]]
- [[Account deletion and data lifecycle]]

## Docs
- [[superpowers/plans/2026-11-15-portfyl-landing-redesign-free-trial]]: the plan that introduced the trial and its landing copy.
- [[superpowers/plans/2026-11-22-free-trial-findings]]: result of the live walkthrough (scenarios a to i) and findings.
- [[compliance/data-processing-inventory]]: what personal data is processed, including trial fingerprints.
- [[deploy.cloudrun (md)]]: runbook, including the trial settings.
