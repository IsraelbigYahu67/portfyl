# Trial fingerprints: legitimate-interest balancing test

Status: 2026-11-24, written by the engineering side from the code
(`backend/trials.py`, tables `trial_identities`, `trial_ip_marks`,
`trial_broker_marks`). It is an internal accountability record (GDPR art.
5(2), art. 6(1)(f), recital 47), **not legal advice**; a Czech lawyer should
confirm it (question 8 in
[../legal/poznamky-pro-pravnika.md](../legal/poznamky-pro-pravnika.md)).

## 1. Purpose

Every new cloud workspace gets a 10-day Pro trial without a card. The purpose
is to give **one trial per person**, so that the free trial cannot be
repeated indefinitely with new accounts. The operator is a sole trader whose
only revenue is the paid plans; unlimited repeated trials would defeat the
paid plans (a real, lawful and specific interest, not a speculative one).

## 2. What is processed

Keyed hashes (HMAC-SHA256, secret key in Secret Manager, never the raw value):

| Fingerprint | Of what | Table | Kept |
|---|---|---|---|
| mailbox | canonical e-mail (lower-case, no `+tag`, Gmail dots folded) | `trial_identities` | 365 days from the grant |
| network | client IP (IPv6 reduced to /64) | `trial_ip_marks` | 30 days; the 4th trial from one IP in 30 days is withheld |
| broker | broker account number, or the ids of the 5 oldest imported transactions (3 of 5 must match to end a trial) | `trial_broker_marks` | 365 days from first sight |

They survive deletion of the account on purpose. Because the operator holds
the key and can recompute a hash from a value somebody supplies, they are
treated as **pseudonymised personal data**, not as anonymous data. A
disposable-domain check at registration stores nothing.

## 3. Necessity

- A hash of the e-mail is the minimum that can recognise a repeat; no name,
  address or document is collected for this purpose.
- Raw values are never stored; hashes are one-way and the key is separate
  from the database.
- Less intrusive alternatives are weaker: a card on file contradicts the
  "no card" promise and would shut out honest users; a phone number is more
  data, not less; relying only on the 30-day IP count does not catch an
  e-mail reuse after a month.

## 4. Balancing

For the controller: protection of the only revenue model against trivial
abuse. Against: the person's interest in not being tracked after leaving, in
erasure on closing the account (art. 17), and the risk of a wrong refusal
(a shared network, a changed broker).

- Reasonable expectations: a person who signs up for a "one free trial per
  person" offer, and is told so in the Terms (art. 4.5) and the Privacy
  Policy, can expect a check that the offer is not repeated. The hashes are
  not used for anything else, not shown to anyone, and not combined with
  other data.
- Impact is low: no legal or similarly significant effect (art. 22 is not
  engaged). A refusal only means the account starts on the Free plan and a
  paid plan can be bought at any time; the data stays.
- Impact is not zero: the e-mail and broker hashes outlive the account for
  12 months, which is long compared with a 10-day trial; the IP hash is kept
  only 30 days.

**Conclusion (provisional):** the processing is justified under art. 6(1)(f)
for the purpose, with the safeguards below; the **12-month period is the
weakest point** of the balance (see 6).

## 5. Safeguards

- Keyed hash only, version- and purpose-separated, no raw e-mail/IP stored or
  logged; the audit record of a refusal carries only a reason code.
- The user is told in the Terms (4.5) and the Privacy Policy (sections 2, 3,
  6, 7) and in the app; which guard fired is not revealed.
- Objection and erasure: the user writes to support@portfyl.com; the operator
  recomputes the hash from the address the user supplies and deletes the row
  (manual today). After removal a repeated trial may no longer be recognised;
  there is no other consequence.
- Automatic purge by the daily `account_deletion_cleanup` job
  (`trials.IDENTITY_RETENTION`, `BROKER_MARK_RETENTION`, `IP_WINDOW`).
- Access limited to the application's runtime role; global tables outside
  tenant RLS (see `docs/security/tenant-isolation-matrix.md`).

## 6. Retention: OPEN DECISION for the owner

Today: **12 months (365 days)** for the mailbox and broker hashes, 30 days
for IP hashes. A shorter period would improve the balance. **Owner decision
needed:** keep 12 months, or shorten, for example to **90 days** (a repeat
more than 90 days after the first trial would then no longer be recognised).
Recommendation: shorten to 90 days unless there is evidence of abuse beyond
that horizon. No code constant has been changed; if the decision is to
shorten, change `IDENTITY_RETENTION` and `BROKER_MARK_RETENTION` in
`backend/trials.py`, update Privacy Policy section 6 (CS and EN), the notes
for the lawyer and the inventory in the same change, and bump
`LEGAL_PRIVACY_VERSION`.

## Related

- Architecture: [[Free trial]] · [[Account deletion and data lifecycle]] · [[Portfyl]]
- Code: [[trials]]
- Docs: [[compliance/data-processing-inventory]] · [[legal/zasady-ochrany-osobnich-udaju-cs]]
