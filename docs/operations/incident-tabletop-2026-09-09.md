# Portfyl technical incident rehearsal — 2026-09-09

This record exercises the technical decision paths in the
[incident-response playbook](security-incident-response.md). It combines the
day's real recovery and monitoring evidence with two hypothetical incident
injects. No customer incident occurred, no credential was exposed, and no
production secret was rotated. This technical rehearsal does not satisfy the
remaining operator-attended exercise or legal notification decision gate.

## Participants and scope

- Automated technical operator: Codex, acting under the repository owner's
  authorization on 2026-09-09.
- Human incident lead and notification decision maker: not assigned in this
  rehearsal; required before private beta.
- Systems covered: Cloud Run, Cloud Scheduler, Cloud Monitoring, Neon recovery,
  Firebase session/identity deletion, Secret Manager/KMS, and tenant RLS.

## Scenario A: credible cross-tenant access

- **Injected symptom:** an Alice/Bob authorization test unexpectedly exposes a
  portfolio identifier belonging to the other workspace.
- **Detection path:** test failure, API correlation ID, Cloud Run revision and
  image digest, followed by bounded RLS and audit-log checks. The scenario is
  classified SEV-1 until evidence supports a downgrade.
- **Containment selected:** disable the narrow affected route or job, preserve
  the serving digest and request window, revoke affected sessions, and keep
  forced RLS and trusted-edge checks enabled. Do not copy raw holdings into the
  incident record.
- **Scope method:** compare opaque workspace IDs, aggregate row counts, audit
  actions, and the complete Alice/Bob matrix. Treat scope as unknown until both
  application predicates and database policies pass.
- **Recovery gate exercised:** the backend fast suite passed 584 tests; the
  previously completed disposable PostgreSQL isolation suite passed 321 tests;
  the real Neon restore check proved unscoped runtime reads invisible and the
  selected workspace count correct. Live direct-origin `/api/auth/me` returned
  403 and an unauthenticated internal cleanup POST returned 401.
- **Notification path:** the operator and qualified counsel must decide whether
  personal data was accessed and record the regulator/customer outcome. That
  human decision was intentionally not simulated as completed.

## Scenario B: database recovery plus suspected credential compromise

- **Injected symptom:** destructive writes are suspected after a database or
  provider credential may have been exposed.
- **Detection path:** Secret Manager/KMS audit events, Cloud Run revision and
  request window, migration head, job invocation metadata, and financial
  control totals. Initial severity is SEV-1.
- **Containment selected:** pause only the responsible job or connector, record
  a recovery point, create a Neon recovery branch, rotate the affected upstream
  and Secret Manager value, deploy a revision referencing the new version, and
  prove rejection of the old credential before resuming work.
- **Real recovery evidence:** the 2026-09-09 Neon branch drill restored from an
  explicit WAL position. Schema head, forced RLS, runtime-role privileges,
  application table counts, and transaction control totals matched. The backend
  booted against the branch and smoke checks passed; the branch was deleted
  after verification. Observed elapsed time was about 2 minutes 6 seconds and
  is not an RTO promise.
- **Credential boundary:** no secret was rotated because there was no exposure.
  A future attended drill must choose a disposable credential, execute both
  versions of the rejection check, and record the owner without printing the
  secret.

## Monitoring and communication evidence

- Dependency health checks parse JSON `status=ok` from six locations.
- Scheduler error, HTTP 5xx, and dependency-health policies are enabled.
- A deliberately failing temporary Scheduler job produced status code 9 and a
  matching Google Cloud alert in the operator Gmail inbox. The job was removed.
- The operator e-mail proves internal alert delivery. A public status/support
  channel and customer-message approval path still need named human owners.

## Corrective actions

| Action | Owner | Due |
| --- | --- | --- |
| Run both scenarios with a named human incident lead and record decisions | Product/operator | Before private beta |
| Perform a disposable credential rotation and old-value rejection check | Security/operator | Before private beta |
| Name the controller and notification decision owner | Product/legal | Before external users |
| Establish public support/status and approved customer-message paths | Product/operator | Before external users |
| Set and fund a public-beta recovery objective beyond the private-test six-hour history | Product/operator | Before public beta |
