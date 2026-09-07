# Portfyl Public Trust and Compliance Design

## Status

Approved for the independently executable scope by the owner's instruction on
2026-09-07. Publication of legal text remains gated on the operator inputs
listed below; this design does not invent them.

## Goal

Turn the already implemented security, export, and deletion behaviour into an
auditable compliance baseline and, once operator facts are supplied, public
privacy, terms, subprocessor, support, and security surfaces. The work must be
accurate for both editions, must not imply that Portfyl has commercial market-
data rights it does not yet have, and must never advertise Tax Report or
Screener as cloud features.

## Product and publication boundary

The technical baseline is a prerequisite for legal publication, not a
substitute for legal advice. Portfyl can independently maintain:

- a source-backed inventory of data categories, purposes, storage, recipients,
  deletion behaviour, and unresolved retention decisions;
- an incident-response and support-identity-verification playbook;
- a market-data vendor due-diligence pack;
- tests that keep public cloud copy free of local-only product claims and keep
  telemetry free of raw holdings and credentials.

Public legal pages must not be enabled until all of these operator-controlled
facts are known and reviewed:

1. controller/legal entity name, postal address, registration identifiers, and
   applicable jurisdiction;
2. working privacy, support, and security-reporting contact channels;
3. approved legal bases and the final retention schedule;
4. the exact Neon backup/PITR retention shown by the production plan;
5. current subprocessors, regions, transfer safeguards, and DPA links;
6. approved consumer terms, complaints process, and any Czech/EU mandatory
   disclosures;
7. whether optional analytics or non-essential cookies will be introduced.

Until then, authenticated users continue to receive the truthful operational
controls already shipped in Settings: versioned JSON export and verified,
cancellable workspace deletion.

## Data inventory source of truth

`docs/compliance/data-processing-inventory.md` records the implemented system,
not intended future behaviour. Every entry distinguishes:

- data supplied by the user from derived and operational data;
- workspace-scoped data from personal and non-tenant infrastructure data;
- encrypted secrets from ordinary metadata;
- a code-enforced retention/deletion rule from an operator policy still to be
  decided;
- a processor from an independent third-party service selected by the user.

The inventory is updated whenever a model, integration, log field, analytics
event, export collection, deletion cascade, or infrastructure provider changes.

## Privacy and telemetry rules

- No third-party product analytics SDK is part of the current frontend or
  backend runtime. Adding one requires a separate design, event allow-list,
  cookie/legal-basis decision, and documentation update.
- Logs may contain correlation IDs, route/status/timing information, opaque
  workspace/public resource IDs, and bounded error classifications. They must
  not contain raw holdings, transactions, broker credentials, webhook URLs,
  session/CSRF tokens, Firebase ID tokens, AI keys, or the trusted-edge token.
- Rate-limit identities remain HMAC digests rather than raw IP addresses or
  workspace IDs.
- Error monitoring, if introduced, defaults to no request bodies, no database
  row payloads, and no user-entered notes.
- Privacy/export/deletion actions never consume a plan quota.

## Incident and support identity verification

`docs/operations/security-incident-response.md` defines severity, containment,
evidence handling, notification assessment, recovery, and a post-incident
record. Support must not accept possession of a public portfolio UUID, a
browser screenshot, or knowledge of holdings as proof of identity.

Account-sensitive support actions require either a fresh authenticated Portfyl
session plus CSRF and re-authentication where available, or a reply through the
verified Firebase e-mail identity followed by a fresh login. Support never asks
for a broker API secret, webhook URL, password, session cookie, CSRF token, or
Firebase token.

## Public surfaces after the publication gate

The cloud build will eventually expose public routes for Privacy, Terms,
Subprocessors, Support, and Security. They must be reachable without login and
linked consistently from landing, login/register, pricing, and authenticated
settings/footer surfaces. Local builds may link the privacy/data-controls
explanation but do not pretend the private installation is the hosted cloud
service.

Content will come from a small, tested source-of-truth module rather than being
duplicated across pages. Each page shows an effective date and a stable heading
hierarchy. The subprocessor page separates mandatory hosting/identity providers
from optional user-triggered integrations.

## Verification

- Review the inventory against SQLAlchemy models, external HTTP clients,
  deployment configuration, and the export/deletion allow-lists.
- Grep runtime dependencies and source for analytics/telemetry SDKs.
- Run the existing logging-redaction, tenant-isolation, export, deletion,
  edition-route, and cloud-build tests.
- Before publication, add route/link/content tests and obtain an explicit legal
  review record with the approved operator facts.

## Non-goals

- Selecting or contracting a market-data provider.
- Sending vendor enquiries or representing the owner to third parties.
- Enabling payments, trials, marketing analytics, advertising pixels, or
  non-essential cookies.
- Claiming legal compliance solely because the technical controls exist.
- Publishing placeholder legal identity or contact information.
