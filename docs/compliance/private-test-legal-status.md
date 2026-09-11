# Portfyl Private-Test Legal Status

Last reviewed: 2026-09-11

This record states the current operating boundary for Portfyl. It is an
internal compliance and release-control document, not a public privacy notice
or final consumer terms.

## Confirmed operator decisions

- Portfyl is currently a private, invitation-only test with no payments,
  subscriptions, trials, advertising, or marketing e-mails.
- The operating country and intended jurisdiction are the Czech Republic.
- The approved privacy, support, and security contact for the private test is
  `tom.zoubek@gmail.com`.
- The operator does not intend to impose an 18+ product rule. This does not
  remove the need for a child/minor legal-capacity and transparency design
  before access is offered to anyone other than the current adult owner.
- `portfyl.com` is a public marketing landing page. The complete tracker
  hostname `app.portfyl.com` is protected by the Cloudflare Access application
  `Portfyl private beta`. Its reusable Allow policy contains the exact e-mail
  `tom.zoubek@gmail.com`, authenticated by a one-time PIN. The operator may add
  individually approved tester e-mails, but not an Everyone, whole-domain, or
  broad group rule. The Access session duration is 24 hours. PostgreSQL
  `beta_invites` independently prevents uninvited Firebase identities from
  creating Portfyl application accounts or workspaces.

## Current release boundary

The current private-test boundary is a required risk control, not merely a
staging preference:

- Do not enable public sign-up, a broad Access rule, payments, or an Access
  bypass until the public-launch gate below is complete. Named private testers
  may be added individually by the operator.
- Authorized private testers may switch the workspace's Free, Investor, and
  Pro test entitlements without payment. This creates no purchase,
  subscription, trial, invoice, or promise of paid service, and must be
  removed or replaced by the reviewed billing flow before public launch.
- Do not describe the service as a launched business, paid SaaS, regulated
  investment service, tax service, or commercially licensed market-data
  product.
- Do not add marketing e-mail, product analytics, advertising, session replay,
  or non-essential cookies without a separate purpose, legal-basis, consent,
  retention, and vendor review.
- The existing Firebase and Portfyl login, workspace export, deletion, audit,
  encryption, RLS, and incident-response controls remain in force even though
  only the owner can currently reach the hostname.

## Personal-data purposes and candidate legal bases

Final legal bases require the identified controller's approval. Until then,
the engineering model is:

| Purpose | Candidate basis for legal review | Current boundary |
| --- | --- | --- |
| Create an account and provide requested portfolio functionality | GDPR Article 6(1)(b), steps/requested service performance | Only individually approved private-test accounts are admitted. |
| Protect sessions, prevent abuse, preserve tenant isolation, and investigate incidents | GDPR Article 6(1)(f), legitimate interests in service and data security | Minimized security metadata; no raw portfolio payloads in ordinary logs. |
| Respond to valid legal duties | GDPR Article 6(1)(c), only where a concrete duty applies | No payment/accounting retention exists yet. |
| Optional marketing, analytics, or non-essential cookies | Consent where required | None are active and none are authorized by this record. |

Consent must not be requested for processing that is necessary to provide the
requested service. Each purpose must have a documented basis before public
use.

## Children and minors

There is no 18+ product restriction. Before a private-test invitation is issued
to a minor:

1. decide whether each processing purpose relies on contract, legitimate
   interests, legal obligation, or consent;
2. obtain Czech legal review of a minor's capacity to enter the applicable
   service contract;
3. if consent under GDPR Article 6(1)(a) is used for an information-society
   service offered directly to a child, implement the Czech threshold in
   Section 7 of Act No. 110/2019 Coll. (15 years) and a reasonable parental-
   authorization process below that threshold;
4. present the relevant privacy information in clear language suitable for
   the intended child audience; and
5. test that age or parental controls cannot be bypassed through direct API or
   identity-provider flows.

This record does not claim that the present registration flow satisfies those
future requirements.

## Retention boundary

The implemented private-test schedule is recorded in
[private-test-retention-policy.md](private-test-retention-policy.md). It accepts
the verified six-hour Neon PITR window for this operator-only test, preserves
the verified 30-day `_Default` and locked 400-day `_Required` Cloud Logging
settings, and fixes the application/support periods and cleanup bounds.

The daily scheduler executes due 30-day workspace deletions and clears expired
technical records. Public/beta adequacy, final legal bases, accounting records,
and the public recovery objective remain publication blockers. Do not copy the
private-test periods into a public notice without that review.

## Private-test plan switching evidence

- The no-payment switch is workspace-scoped, requires an authenticated
  membership and CSRF token, and records each change in the audit log.
- The production deployment completed on 2026-09-08 as Cloud Run revision
  `portfyl-00004-kjd` after migration job `portfyl-migrate-jpv7m` succeeded.
- A live Cloudflare-path smoke test observed Investor, switched to Pro, and
  returned the operator workspace to Free. The final GET and both final PUT
  requests to `/api/test-plans` returned HTTP 200.

## Public-launch gate

All items below require evidence before Cloudflare Access is relaxed or public
legal routes are enabled:

- [ ] Confirm the controller's full legal name, legal form, postal address,
      registration identifiers (if any), and service address.
- [x] Confirm a working privacy/support/security contact:
      `tom.zoubek@gmail.com`.
- [x] Confirm the current service is a free private test with no payments.
- [x] Confirm the operating country is the Czech Republic.
- [ ] Approve legal bases per processing purpose and the final public retention
      schedule. The current private-test schedule is implemented and recorded.
- [x] Verify production Neon PITR and Cloud Run log-retention settings
      (2026-09-09; policy approval remains open).
- [ ] Verify every current processor/subprocessor, region, transfer safeguard,
      and applicable DPA.
- [ ] Resolve commercial market-data and broker-API rights for the intended
      public features.
- [ ] Decide and implement the minor/child access model described above.
- [ ] Approve consumer terms, complaints handling, withdrawal/cancellation
      behaviour, and mandatory Czech/EU disclosures before any paid offering.
- [ ] Obtain qualified Czech legal review of the public privacy notice and
      terms.
- [ ] Run and record a security/privacy tabletop exercise and a production-like
      restore drill.

## Legal references used for this gate

- [GDPR, Regulation (EU) 2016/679](https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng/),
  especially Articles 5, 6, 8, 12-14, 15-22, 28, 32-34, and 44-49.
- [Czech DPA methodology on transparency and customer information](https://uoou.gov.cz/profesional/metodiky-a-doporuceni-pro-spravce/metodika-k-plneni-informacni-povinnosti-a-k-souvisejicim-ujednanim-vuci-zakaznikum).
- [Czech Act No. 110/2019 Coll.](https://www.zakonyprolidi.cz/cs/2019-110),
  consolidated reference copy; Section 7 covers a child's consent to an
  information-society service.
- [EU consumer pre-contract information](https://europa.eu/youreurope/citizens/consumers/shopping/contract-information/index_en.htm)
  and [distance-selling requirements](https://europa.eu/youreurope/business/selling-in-eu/selling-goods-services/ecommerce-distance-selling/index_en.htm),
  to be applied before a public or paid consumer offer.
