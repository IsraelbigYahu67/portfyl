# Portfyl Terms of Service

> **DRAFT – DO NOT PUBLISH.** Items marked `[[TODO]]` must be filled in and
> the text reviewed by a Czech lawyer. Open points are listed in
> [poznamky-pro-pravnika.md](poznamky-pro-pravnika.md). This English version
> mirrors [podminky-uzivani-cs.md](podminky-uzivani-cs.md).

Effective from: `[[TODO: publication date]]` \
Text last updated: 24 November 2026 \
Version: 0.2 (draft)

## 1. Who operates the service

The Portfyl service available at `portfyl.com` and `app.portfyl.com` (the
"**Service**") is operated by:

**Jakub Zoubek**, a sole trader under the Czech Trade Licensing Act \
Registered business address: Brusinková 1983, 252 28 Černošice, Czech Republic \
Company ID (IČO): 67772366 \
`[[TODO: VAT registered / not VAT registered, VAT ID if any]]` \
E-mail: **support@portfyl.com** \
`[[TODO: telephone number if the Operator has one (the model withdrawal notice lists it); otherwise delete this line]]`

(the "**Operator**", "**we**", "**us**").

These terms govern the relationship between the Operator and everyone who
creates an account in the Service (the "**User**", "**you**"). By
registering, you confirm that you have read and accept them.

You conclude the contract for the Service, including the paid plans, with the
Operator. Payments for paid plans are accepted, and receipts for them issued,
by the Payment Partner (Section 5.1). You can exercise your right of
withdrawal under Section 6 towards the Operator.

## 2. What the Service is – and what it is not

2.1 Portfyl is a software tool for **tracking and analysing your own
investment portfolio**. It lets you import transactions from brokers (by file
or API connection) and calculate performance, allocation, dividends and
other metrics.

2.2 **Portfyl is not an investment adviser or a securities dealer.** The
Service does not provide investment advice, investment recommendations or any
other investment service within the meaning of Czech Act No. 256/2004 Coll.,
on Capital Market Undertakings, does not execute, receive or transmit orders,
does not hold your money or financial instruments, and does not provide tax
or accounting advice.

2.3 All data, charts and calculations (such as valuations, fair value,
dividend forecasts) are **for information only**. They are based on data from
brokers and third parties and on estimates, so (especially third-party data)
they may be delayed or incomplete; we tell you this in advance and it is the
nature of such data. You make every investment decision yourself and at your
own risk. Past performance does not guarantee future returns. This does not
affect your rights for defects under Section 7 where the Service itself does
not work as we described it or as you can reasonably expect.

2.4 **Functionality and compatibility.** The Service is a web application. You
use it in a current version of a common web browser with JavaScript enabled,
with the cookies needed to sign in (see the Privacy Policy, Section 8) and an
internet connection; you install nothing. Importing from a broker depends on
the export format or interface of that broker (Section 9). We list the
supported brokers and file formats in the Service.

## 3. Account, registration and workspace

3.1 The Service is only for people **aged 18 or over** with full legal
capacity. By registering you confirm this. If we learn that an account belongs to someone under 18, we
will close it and delete its data, and we will refund the price paid for the
unused part of the period.

3.2 You can register with an e-mail and password or sign in with Google.
Technical details of identity verification and of the data processed at
sign-in are in the [Privacy Policy](privacy-policy-en.md).

3.3 Your account is personal. Do not share your login details; you are
responsible for keeping them secure. Please report any suspected misuse
immediately to support@portfyl.com.

3.4 Provide accurate details when registering, especially a working e-mail
address – we use it for important account notices and changes to these
terms.

3.5 To protect the Service from automated sign-ups, creating a new account
may require an automated bot check (Cloudflare Turnstile). It is shown only
when a new account is created. `[[LAWYER: confirm that this check needs no
separate consent; see notes, point 10.]]`

3.6 **Workspace.** Your data is stored in your workspace, which only you
manage as its **Owner**. The Service does not currently offer sharing a
workspace with other users. If we introduce it, we will add sharing rules
following the procedure in Section 16.

3.7 If you upload data of other people to the Service (for example
transactions of a joint account, or of a broker account held by another
person), you are responsible for having the right to do so and for not
infringing the rights or obligations owed to those people or to the broker.
Personal data is processed in accordance with the
[Privacy Policy](privacy-policy-en.md).

## 4. Plans and free trial

4.1 The Service is offered as a **Free** plan and the paid **Investor** and
**Pro** plans. The current features, limits and prices are always shown on
the Pricing page (`[[TODO: pricing URL once published]]`). Prices are final and include VAT
where applicable.

4.2 Paid plans are paid **monthly**.

4.3 A new account may try the **Pro** plan once **free of charge**. The
length of the trial is shown at registration (currently 10 days). No payment
card is needed and nothing is charged automatically. When the trial ends, the
account **switches to the Free plan** unless you explicitly order a
subscription. A trial never turns into a paid subscription by itself, and your
data is not deleted when it ends.
`[[DECIDE: if the trial requires a payment card and converts automatically,
this clause must be rewritten and the User reminded before the first
charge.]]`

4.4 When you move to a lower plan or to Free, your data is kept; features
beyond the new plan simply become unavailable.

4.5 **One trial per person.** The trial may be withheld at registration, or
ended early, when the same e-mail mailbox, network address, broker account or
transaction history already had a trial in another Portfyl account. The
account itself is not affected: it stays on the Free plan and you can order a
paid plan at any time. We do not say which of these signals applied.
`[[LAWYER: is withholding or ending a trial on these signals compatible with
consumer law and with the landing claim "every new account gets 10 days"?]]`

4.6 After the trial, or on the Free plan, your data is kept. Items beyond the
Free limits become read-only (as in 4.4) until you subscribe or remove them.

## 5. Payments and subscriptions

5.1 Payments for paid plans are processed and accepted, as the seller
(*Merchant of Record*), by a Stripe group company trading under the **Link**
brand (the Stripe Managed Payments service), `[[TODO: exact name and address
of the selling Stripe/Link entity as shown in the buyer terms at checkout]]`
(the "**Payment Partner**"). The Payment Partner issues receipts, handles
VAT, payment support and payment disputes under its buyer terms, which you
will see at checkout; it may also carry out refunds (Section 6.4). The
Operator provides the content and delivery of the Service. The charge appears
on your statement as `LINK.COM* PORTFYL`. The Operator never sees your card
details.

5.2 Subscriptions **renew automatically** for another month until
cancelled. The price for the next month is charged at its start.

5.3 You can cancel at any time in your account settings or on the Link
website (link.com), where you manage your orders; the link is also in your
payment receipt. Cancellation takes effect at the end of the period already
paid for; until then you keep paid features. The account then moves to the
Free plan. Cancelling a subscription does not refund the price already paid
for the running period (unless Section 6 on withdrawal or Section 7 on defects
applies). You can also end a subscription at once by deleting the workspace
(Section 8.3).

5.4 We may change the price of a paid plan only for these reasons: (a) a
change in tax law or the VAT rate, or in other charges set by law; (b) a
material change in the costs of suppliers the Service depends on (in
particular hosting, payment services and market-data licences); (c) a change in
the scope or content of the plan that the price reflects. We will notify you
of a price change by e-mail at least **30 days** in advance and state the
reason. The new price applies only from your next subscription period. If you
disagree, you may cancel without any penalty within 30 days of the notice or
of the change taking effect, whichever is later; we will refund any higher
price already paid for the time after cancellation.

5.5 **Failed payment.** If the payment for the next subscription period
cannot be collected, you keep the paid features for **14 days** (grace
period), during which you can correct your payment details and the payment
can be retried. If the payment is not made by the end of this period, the
account **moves to the Free plan**. Your data is kept (as in 4.4 and 4.6) and
you can subscribe again at any time.

## 6. Right of withdrawal (consumers)

6.1 **Right of withdrawal.** You have the right to withdraw from this contract
within 14 days without giving any reason. The withdrawal period expires 14
days after the day following the day the contract is concluded. The contract
is concluded by your **first order of a paid subscription**; the period does not
start at registration or during the free trial. You have this right **only
once** per subscription contract; an automatic monthly renewal does not start
a new withdrawal period.

6.2 **How to withdraw.** You may withdraw from this contract by any clear
statement addressed to the Operator (Jakub Zoubek, Brusinková 1983, 252 28
Černošice, Czech Republic, support@portfyl.com), for example by letter or
e-mail. You may use the model withdrawal form attached to these terms, but it
is not obligatory. You may also withdraw by **deleting your workspace** in
your account settings within the 14 days (Section 8.3); such deletion counts as
withdrawal from the contract. To meet the withdrawal deadline, it is
sufficient that you send your withdrawal before the period expires. We will
confirm receipt of your withdrawal by e-mail.

6.3 **Effects of withdrawal: full refund.** If you withdraw from this contract,
we will reimburse to you without undue delay, and at the latest within 14 days
of the day we receive your withdrawal, **the full price paid**, even if you
have used the paid features since ordering and even if you expressly asked for
them to start immediately. In that case the law would allow us to charge an
amount proportionate to what has already been provided (Section 1834 of the
Czech Civil Code); the Operator does not charge it. This is the **Operator's
policy, which goes beyond the legal minimum**. We will use the same means of
payment you used for the payment, unless you expressly agree otherwise; you
will not incur any fees as a result. On withdrawal the subscription ends and
the account moves to the Free plan (your data is kept, as in Section 4.4),
unless you deleted the workspace.

6.4 **Who pays the refund.** The payment was accepted through the Payment
Partner, so the Operator makes the refund through the Payment Partner, or the
Payment Partner makes it directly; you may also ask the Payment Partner's
support (link.com). This does not affect your right of withdrawal under this
Section or your rights for defects under Section 7. The Payment Partner's
terms on refunds may be more favourable to you than this Section.

6.5 **After the 14 days.** After the period in Section 6.1 has expired, when you
end the contract yourself (cancelling the subscription under Section 5.3 or
deleting the workspace under Section 8.3) the remaining part of the paid period
is not refunded; you can cancel the subscription so that it runs to the end of
the paid period. This does not affect your rights for defects (Section 7) or
other statutory consumer rights.

`[[LAWYER: open questions (not to be resolved without a lawyer): (a) who is
the "trader" towards the consumer under the Merchant of Record model – the
Payment Partner or the Operator – and therefore against whom withdrawal is
exercised, who meets the information duties under Directive 2011/83/EU and who
confirms the withdrawal on a durable medium; (b) whether the paid subscription
is a "service" (Article 16(a) of the Directive, proportionate payment) or
"digital content" (Article 16(m)); the press release in case C-234/25 Sky
Österreich (9 July 2026) speaks of a service, the full judgment has not been
read; (c) whether an in-app tick box before the redirect to Stripe is enough
for the express request for immediate start (Article 8(8) of the Directive);
(d) whether deleting the workspace is a withdrawal and whether a record of the
withdrawal and payment must be kept; (e) whether the withdrawal function
(button) under Article 11a of Directive 2011/83/EU (inserted by Directive (EU)
2023/2673; Section 1830a of the Civil Code, in the Czech Republic reportedly
from 1 January 2027) is already mandatory; see notes.]]`
`[[VERIFY: wording of the notice and form against the current Government
Regulation No. 29/2023 Coll. as amended by No. 66/2026 Coll., and Section 1832
of the Civil Code (refund period).]]`

## 7. Defects and complaints

7.1 The Service is a digital service. You have statutory rights for defects
under Section 2389a et seq. of the Czech Civil Code for as long as we provide
the Service to you.

7.2 Send complaints to support@portfyl.com, describing what does not work,
when it happened and which browser or device you used. We will confirm
receipt by e-mail and resolve the complaint without undue delay, within
**30 days** at the latest.

7.3 If we do not remedy a defect within a reasonable time, you are entitled
to a reasonable price reduction or – unless the defect is minor – to
terminate the contract. On termination we will refund the proportionate price
for the period the Service was defective **and the price paid for the period
after termination**.

7.4 **Out-of-court dispute resolution:** consumers may contact the Czech
Trade Inspection Authority (Česká obchodní inspekce), Štěpánská 567/15,
120 00 Prague 2, `https://adr.coi.cz`. A consumer may also go to court; if
you are a consumer resident in another EU Member State, you may under
Regulation (EU) No 1215/2012 also sue in the courts of the place where you
live.

## 8. Your data

8.1 Data you upload to the Service (transactions, notes, portfolios, etc.)
**belongs to you**. You only grant us the permission we need to run the
Service (storage, calculation, display, backup).

8.2 You can **export** your data at any time in your account settings, in a
machine-readable format (JSON). The export contains the data of your
workspace, in particular portfolios, transactions, notes, watchlists, alerts,
allocation targets, custom benchmarks, options and Polymarket positions,
cash-interest settings and notifications, and basic data about connected
brokers (including balances and positions from the last sync). The export
**does not contain** access keys, tokens and other secrets, security and
operational records (for example sign-in sessions, usage counters, deletion
state), market-data caches or internal identifiers. Values the Service
continuously calculates from your data (for example performance) are not
included; they can be recalculated from the exported data. Details are in the
[Privacy Policy](privacy-policy-en.md).

8.3 You can **delete** your account and workspace at any time in your account
settings. **Deletion is immediate and irreversible:** once confirmed (by
typing the workspace name and re-authenticating), your data is removed and
cannot be restored. **Please export your data first (Section 8.2).** Deleting a
workspace with an active subscription ends the subscription immediately. If
you are within 14 days of the order, the deletion counts as withdrawal from
the contract and we will refund the full price paid (Section 6). After 14 days
the remaining part of the paid period is not refunded, because you are ending
the contract yourself; this does not affect your rights for defects. If you
want to use the paid features until the end of the period, cancel the
subscription first (Section 5.3) and delete the workspace only after it has
ended. We will point out the consequences of deleting a workspace with a
subscription in the deletion dialog and ask for your express consent before
deleting. Payment receipts and records are kept by the Payment Partner as an
independent controller (Section 5.1). Copies of deleted data may remain for
at most **7 days** in database backups kept for disaster recovery and are then
overwritten; we do not restore data from backups on request. Which data is
kept even after deletion (for example technical marks that prevent repeated
use of the trial) and for how long is described in the
[Privacy Policy](privacy-policy-en.md).

8.4 You are responsible for the accuracy and completeness of the data you
upload. We recommend keeping your original broker statements.

8.5 Personal data is processed in accordance with the
[Privacy Policy](privacy-policy-en.md).

## 9. Broker connections and third-party services

9.1 If you connect a broker account (e.g. Trading 212, Interactive Brokers,
eToro) or another service (e.g. Discord), you do so at your own choice. Your
relationship with that third party is governed by its terms; we are not
responsible for its services. Make sure the broker's terms allow a third-party
service to use your API key.

9.2 A broker is connected with your own API key or token. We recommend using
**read-only** keys. By connecting, you **authorise** us to use the key solely
to read data about your account and to synchronise your portfolio. Portfyl
never places trades. Keys are stored encrypted.

9.3 Market data (prices, exchange rates, fundamentals) comes from third
parties. We tell you in advance that such data tends to be delayed or incomplete and
that we cannot guarantee its availability; that is its nature. This does not
affect your rights for defects under Section 7 where we display or process the
data incorrectly ourselves.

9.4 **Revoking access.** You can end Portfyl's access to your broker at any
time (a) at the broker – by revoking or deleting the API key or token in its
settings, and/or (b) in the Service – by disconnecting the broker in the
settings, which deletes the stored key. Data already downloaded into Portfyl
stays in your portfolio until you remove it or delete your account
(Section 8.3).

9.5 We are not responsible for outages or changes of a broker's API, or for a
broker revoking, restricting or discontinuing your key; in that case
synchronisation stops until you restore the connection. This does not affect
your rights for defects under Section 7 where the cause is a defect of the
Service itself.

## 10. Acceptable use

10.1 When using the Service you must not:

- circumvent security, plan limits or the separation of other users' data;
- upload or distribute malicious code through the Service, or use it to send
  unsolicited messages (spam);
- scrape, overload or disrupt the Service;
- reverse-engineer the Service except where the law allows it;
- use the Service, its outputs or data from it to build a competing product
  or service;
- resell or mass-distribute the Service or data from it (especially
  third-party market data);
- upload unlawful content or content that infringes third-party rights;
- use the Service in breach of the law.

10.2 **Exception:** you may freely share your own results and screenshots of
your own portfolio (for example on social media or with your adviser). You
may not, however, mass-distribute the third-party market data the Service
displays.

## 11. Intellectual property and licence

11.1 The software, design, the Portfyl name and logo, texts and other content
of the Service (other than data you upload) are protected by Czech Act No.
121/2000 Coll. (the Copyright Act) and other laws and belong to the Operator
or its licensors.

11.2 For the duration of the contract the Operator grants you a
**non-exclusive, non-transferable and non-sublicensable licence** to use the
Service for your own purposes within the scope and under the conditions of
these terms. The licence ends with the contract. Users' statutory rights
(for example under Section 66 of the Copyright Act) are not affected.

11.3 Rights to the data you upload remain yours (Section 8.1). No further
rights in the Service pass to you under these terms.

`[[VERIFY: the exact provision on licence contracts (Section 2358 et seq. of
the Civil Code, or Section 46 et seq. of the Copyright Act) and Section 66 of
the Copyright Act.]]`

## 12. Feedback

You send us ideas, comments and suggestions for improving the Service
voluntarily. We may use them freely and without remuneration, and, where they
are protected by copyright, you grant us a non-exclusive, royalty-free
licence to do so; we are, however, not obliged to use them or to respond.

## 13. Availability and changes

13.1 We aim to keep the Service available at all times but **do not
guarantee** any particular level of availability. The Service may be
temporarily unavailable because of maintenance, updates or supplier outages.
This does not affect your statutory rights for defects (Section 7).

13.2 We continuously develop the Service and may change features for valid
reasons (security, legal requirements, technical development, changes to
third-party data or interfaces, improvement of the Service) and at no extra
cost to you. If a change materially and negatively affects your access to or
use of the Service, we will tell you at least 30 days in advance by e-mail. You
may then terminate the contract without any penalty within 30 days of the
notice or of the change, whichever is later, and we will refund the
proportionate price for the time after termination; where technically
possible, you may instead keep the Service unchanged.

## 14. Liability

14.1 We are not liable for investment or other decisions you make based on
data in the Service, or for losses resulting from them, unless the damage
was caused by a breach of our obligations.

14.2 We are not liable for errors, outages or incompleteness of data supplied
by brokers or market-data providers that we cannot influence; this does not
apply where we took the data over or processed it incorrectly. This provision
points out the nature of such data and does not exclude a consumer's rights for
defects (Section 7).

14.3 If you act as a business, our total liability for damage is limited to
the amount you paid us in the previous 12 months, but at least
`[[LAWYER: amount of the cap – a fixed minimum so that the cap is not zero on
the Free plan]]`. If you are a consumer, we are liable to the extent provided
by law and this limit does not apply to you.

14.4 Nothing in these terms excludes or limits liability for damage caused
intentionally or by gross negligence, liability for harm to a person's natural
rights (Section 2898 of the Civil Code), or a consumer's statutory rights, in
particular rights for defects (Section 7) and the right of withdrawal
(Section 6).

`[[LAWYER: amount of the cap for businesses, and whether any cap should be
introduced for consumers at all (it must be compatible with Section 1814 of
the Civil Code and point 1(b) of the Annex to Directive 93/13/EEC); until
decided, only the statute applies to consumers.]]`

## 15. Termination

15.1 You can close your account at any time in your account settings.
Closing the account means deleting the account and data, which is
**immediate and irreversible** (Section 8.3); we recommend exporting your
data first (Section 8.2). If you have a paid subscription, it ends at once
on deletion; whether the price paid is refunded is governed by Section 8.3
(within 14 days of the order in full, afterwards not) and Section 6.

15.2 We may suspend or close your account if you materially breach these
terms (especially Section 10) or where security or the law requires it.
Except in urgent cases we will warn you first. We will refund any unused
part of the paid period, unless we closed the account because of your material
breach of these terms.

15.3 We may discontinue the Service as a whole with at least **60 days'**
notice. During that time you can export your data, and we will refund any
unused prepaid period.

## 16. Changes to these terms

We may change these terms because of changes to the Service, the law or our
business terms. We will notify you by e-mail at least **30 days** before a
change takes effect and give the reason. If you disagree, you may terminate
the contract without penalty before that date, or within 30 days of the notice
or of the change taking effect, whichever is later, and we will refund any
unused prepaid period.

## 17. Contact and disputes

17.1 All communication, including the single point of contact under
Regulation (EU) 2022/2065 (Digital Services Act), is handled at
**support@portfyl.com** in Czech or English.

17.2 The contract is governed by Czech law. If you are a consumer resident in
another EU country, you keep the protection of the mandatory laws of your
country.

17.3 The contract is concluded in Czech or English at your choice. Both
language versions are equally valid. `[[LAWYER: confirm]]`

17.4 If any provision of these terms is or becomes invalid or unenforceable,
the validity of the other provisions is not affected (Section 576 of the Civil
Code).

---

## Annex: Model withdrawal form

*(complete and return this form only if you wish to withdraw from the
contract; using the form is not obligatory. The wording follows the model
withdrawal form in the annex to Czech Government Regulation No. 29/2023 Coll.
as amended by No. 66/2026 Coll., which implements Annex I(B) of Directive
2011/83/EU; there is no official English text of the Czech regulation.)*

**Withdrawal from the contract**

- To: Jakub Zoubek, Brusinková 1983, 252 28 Černošice, Czech Republic, e-mail
  support@portfyl.com
- I hereby give notice that I withdraw from my contract for the provision of
  the following service: paid subscription to the Portfyl service (plan:
  ……………)
- Ordered on: ……………
- Name of consumer: ……………
- Address of consumer: ……………
- Portfyl account e-mail (to help us find the order): ……………
- Date: ……………
- Signature of consumer (only if this form is notified on paper): ……………

## Related

- Architecture: [[Portfyl]] · [[Billing and Stripe]] · [[Account deletion and data lifecycle]]
- Docs: [[legal/podminky-uzivani-cs]]
