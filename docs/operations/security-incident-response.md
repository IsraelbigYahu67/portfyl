# Portfyl Security and Privacy Incident Response

Last reviewed: 2026-09-07

This is the operator playbook for suspected confidentiality, integrity,
availability, authentication, tenant-isolation, credential, or personal-data
incidents. It complements the Cloud Run, Neon restore, KMS, scheduler, audit,
and account-deletion runbooks.

## Priorities

1. Protect people and stop ongoing unauthorized access or destructive writes.
2. Preserve the minimum reliable evidence without copying raw customer data
   into tickets, chat, or personal devices.
3. Keep tenant boundaries and deletion commitments intact during recovery.
4. Assess notification obligations using verified facts and timestamps.
5. Restore safely, communicate accurately, and record corrective actions.

## Severity

- **SEV-1:** confirmed or credible cross-tenant access, exposed credentials or
  signing/encryption keys, unauthorized destructive action, active account
  takeover at scale, or material loss/corruption of production data.
- **SEV-2:** contained single-account compromise, failed tenant boundary with no
  evidence of access, prolonged production outage, broker/webhook secret misuse,
  or recovery objective at risk.
- **SEV-3:** degraded integration/job, excessive errors, policy/test regression,
  or suspicious activity without confirmed customer impact.

When uncertain between two levels, start at the higher one and downgrade only
after evidence supports it.

## First 30 minutes

- Record UTC detection time, reporter, affected service/revision, and a concise
  symptom. Assign one incident lead.
- Do not paste tokens, credentials, request bodies, holdings, transaction rows,
  or database dumps into the incident record.
- For suspected application compromise, preserve the deployed image digest and
  revision metadata before changing traffic.
- Contain using the narrowest reversible control: disable an affected route or
  integration, revoke one session/identity, rotate one secret, pause one job,
  or shift traffic to a known-good revision.
- Do not disable PostgreSQL RLS, weaken trusted-edge checks, restore over the
  production database, or bypass migration-head assertions to recover faster.
- If destructive writes are possible, stop the responsible job/route and record
  a restore point before repair attempts.

## Investigation and evidence

Collect only what answers the incident questions:

- Cloud Run revision/image, request correlation IDs, status/error class, and
  bounded time window;
- relevant audit actions and public resource IDs;
- authentication/session creation, revocation, and Firebase identity events;
- job name/run status and scheduler invocation metadata;
- database schema head, aggregate counts, and control totals;
- Cloudflare rule/DNS/TLS configuration and security events;
- KMS/Secret Manager access events when credential exposure is suspected.

Prefer hashes, counts, timestamps, and public/opaque IDs. If a raw customer row
is essential, restrict access, record why it was needed, keep it out of general
chat/tickets, and delete the working copy after the incident retention decision.

## Containment patterns

- **Session/account:** revoke the affected Portfyl session(s), disable the
  Firebase identity when justified, and require fresh verified login.
- **Secret:** rotate through Secret Manager/KMS and the upstream provider;
  redeploy a revision that references the new version; verify the old value is
  rejected. Never print the value during verification.
- **Tenant isolation:** stop the affected API/job, preserve evidence, add a
  failing Alice/Bob test, fix both application predicate and RLS policy where
  applicable, and run the complete PostgreSQL isolation suite before reopening.
- **Cloud edge:** retain Cloudflare proxying and `Full (strict)` TLS. Direct
  Cloud Run requests must continue to fail trusted-edge verification.
- **Database integrity:** use a Neon recovery branch and
  `deploy/validate-restore.py`; never restore over production in place. Switch
  `DATABASE_URL` only after explicit review of schema, RLS, counts, controls,
  and smoke tests.
- **External provider:** disable only the failing connector/capability when
  possible; do not make fabricated/stale market data appear current.

## Support identity verification

Support must never use knowledge of holdings, a portfolio UUID, a screenshot,
or a broker account number as proof of identity. It must never ask for a
password, broker API secret, Discord webhook URL, session cookie, CSRF token,
Firebase ID token, trusted-edge token, or AI key.

For an account-sensitive request:

1. Prefer the authenticated in-product control using the current Portfyl
   session and CSRF protection.
2. Use fresh Firebase password re-authentication for destructive actions that
   already support it.
3. If account access is unavailable, communicate only through the verified
   Firebase e-mail identity using the operator's approved support channel, then
   require a fresh login before changing account state.
4. Escalate conflicting identity, shared-workspace, deceased-user, legal-order,
   or takeover claims; do not improvise ownership transfer or deletion.

## Notification assessment

The incident lead records:

- what happened and whether personal data was accessed, changed, lost, or made
  unavailable;
- affected data categories, tenants, people, systems, countries, and time span;
- likelihood and severity of harm, including financial-account linkage and
  credential risk;
- containment status and evidence confidence;
- advice or protective action available to affected users;
- processor/subprocessor notifications and contractual deadlines.

The controller/operator and qualified counsel decide regulator and customer
notification duties and timing. Record the decision, owner, rationale, and
deadline even when the conclusion is that notification is not required. Do not
delay containment while waiting for legal review.

## Recovery gate

Before closing or restoring normal traffic:

- the exploited path is contained and old credentials/sessions are rejected;
- migrations and forced RLS are at the expected head;
- relevant focused tests plus the complete fast/PostgreSQL suites pass;
- edge 200/direct-origin 403 behaviour is verified when cloud routing changed;
- scheduled jobs are idempotent and any replay range is explicit;
- data integrity is checked with counts and financial control totals;
- monitoring covers the original detection gap;
- customer-facing status does not overstate recovery.

## Post-incident record

Within a reasonable review window, record:

- UTC timeline, detection source, scope, root cause, and contributing controls;
- data/tenants affected and how that conclusion was established;
- containment, eradication, recovery, and notification decisions;
- tests, alerts, runbooks, code, configuration, and training changed;
- owners and due dates for every corrective action;
- sanitized lessons that can be shared without exposing customer data.

## Tabletop drill record

For each drill, capture:

```text
Date / participants:
Scenario and injected symptoms:
Detection path:
Severity and incident lead:
Containment chosen:
Evidence collected (no secrets/raw customer payloads):
Tenant/data scope conclusion:
Notification assessment owner and outcome:
Recovery checks performed:
Gaps / corrective actions / owners / due dates:
```

Run at least one cross-tenant scenario and one restore/credential-rotation
scenario before private beta. A written runbook alone does not close the drill
or monitoring launch gates.
