# Withdrawal refund on workspace deletion

Status: implemented on branch `feat/withdrawal-refund` (2026-11-24) and revised
after an independent review (`fix/refund-review-backend`), **not deployed, never
run against Stripe**. Payments are off in production
(`PORTFYL_BILLING_ENABLED` unset). Run the test-mode checklist below before
payments go live.

## Policy (operator decision, 2026-11-24)

- The paid subscription is a digital service. Within **14 days of the first paid
  order** of a subscription the customer may withdraw and gets **100 %** of what
  was paid (more generous than the proportionate amount the law allows; no
  calculation).
- Deleting a workspace that has a paid subscription ends the subscription at
  once:
  - inside the 14 days it counts as a **withdrawal**: refund everything paid,
    cancel, erase;
  - after the 14 days: cancel at once, **no** refund of the rest of the period
    (the customer consented in the dialog and can instead cancel first and
    delete after the paid period ends).
- Registration and the free trial do not start the window; only the first paid
  order does. Rights for defects of the digital service are unaffected.

## What the code does

One rule, one place: `billing_config.py` (`WITHDRAWAL_DAYS = 14`,
`withdrawal_ends_at`, `withdrawal_open`). The window is open while
`now < ordered_at + 14 days`, always on the **server clock**.

`ordered_at` is `subscriptions.created_at` of the live subscription row. The row
is written when Portfyl first projects the Stripe Subscription (checkout
confirmation or first webhook, seconds after the order) and a plan change reuses
the row. No migration was needed. Two consequences, both accepted:

- A lost webhook that is only repaired by the daily `billing_reconcile` pushes
  `created_at` later, which favours the customer.
- A payment that starts as `incomplete` (3DS / SCA, up to about 23 hours until
  it is paid or expires) can have its row BEFORE the money is paid, so the window
  can end up to those hours earlier than 14 days after the paid order. It never
  starts later than the order for this reason. Rows in `incomplete` or `paused`
  hold no paid invoice: a deletion with consent still cancels them (a late 3DS
  success must not be charged), but there is nothing to refund and `refunded` is
  `false`.

`GET /api/billing/status`: the `subscription` object has `ordered_at`,
`withdrawal_ends_at` (ISO UTC) and `withdrawal_open` (bool); the whole object is
`null` without a subscription. `consent_version` is `2026-11-24`
(`CHECKOUT_CONSENT_VERSION`), changed with the new checkout consent text.

`POST /api/settings/account/deletion` (`account_deletion.py`). Request fields
that matter here: `cancel_subscription` (bool, the owner's consent) and
`refund_expected` (bool, what the dialog promised; default `false`).

1. All guards as before (owner, typed name, fresh re-authentication, sole
   member). **Contract without consent** (`cancel_subscription` not `true`):
   a live subscription answers **409 `active_subscription`** when it is renewing
   (active/trialing, not ending) and also when it is `cancel_at_period_end` or
   `past_due` **while the withdrawal window is open** (the customer has a refund
   right the UI must show). Outside the window a `cancel_at_period_end` or
   `past_due` subscription proceeds untouched, as before.
2. With consent, **every live subscription row is cancelled whatever its
   status** (`past_due` is still retried by Stripe, `cancel_at_period_end` bills
   until the period end, so leaving them would charge a deleted customer). If the
   window is open: **refund first**, then **cancel**, then **erase**. If it is
   closed: cancel, then erase, no refund call.
3. **`refund_expected`.** The UI decides "full refund" when the dialog opens; the
   server decides again minutes later. If `refund_expected` is `true` and no
   refund would happen any more (window closed, or no live subscription and no
   trace of an earlier refund, see point 7), the answer is **409
   `withdrawal_window_changed`** before any Stripe call or erasure, so the UI
   reloads the status and shows the no-refund text. For this request only a
   **15-minute tolerance** applies: the window counts as open for the refund
   while `now < ends_at + 15 min`, which protects a customer who opened the
   dialog in time. Without `refund_expected` there is no tolerance and nothing
   else changes.
4. Refund = every successful payment of the subscription, 100 %, no `amount`
   (`POST /v1/refunds` with `payment_intent`, or `charge`). Payments are found
   with `GET /v1/invoices?subscription=&status=paid`, then
   `GET /v1/invoice_payments?invoice=&status=paid` (since API version 2025-03-31
   the invoice no longer carries `payment_intent`/`charge`; the pinned
   `2026-09-30.endive` returns InvoicePayments with `payment.type` of
   `payment_intent` or `charge`). A legacy `payment_intent`/`charge` on the
   invoice is used only when no InvoicePayment comes back. Zero-amount payments
   are skipped. Nothing paid: no refund, cancel still happens, `refunded: false`.
   A 200 from `POST /v1/refunds` is checked: status `failed`, `canceled` or
   `requires_action` is a failure (503 `subscription_refund_failed`, logged
   without personal data); `succeeded` and `pending` are success.
5. Retry safety. Stripe stores the first response for an idempotency key for
   24 h **including errors** (500, lock timeout, balance), so a permanent key
   would replay a failure to every retry for a day. The key is therefore
   `withdrawal-refund-<subscription id>-<payment id>-<UTC minute bucket>`: it
   only stops two concurrent requests from both creating a refund. A double
   refund is prevented by Stripe itself: the refund has no `amount`, and a
   second attempt on a fully refunded payment fails with
   `charge_already_refunded`, which counts as success. In that case the amount
   is not known from the response, so `refunded_amount_cents` is `null` (with
   `refunded: true`) unless the trace of point 7 holds it. Order refund, cancel,
   erase means a failure between steps is repaired by retrying the same request.
6. Cancel. A 404 / `resource_missing` from `DELETE /v1/subscriptions/{id}` is
   not trusted: the subscription is retrieved and accepted only when its status
   is `canceled` (a 404 on the retrieve also counts as gone). A subscription that
   is still live, or a retrieve that fails otherwise, is **503
   `subscription_cancel_failed`**. A cancel failure after a successful refund is
   logged at ERROR with the workspace public id (no e-mail, no Stripe ids) so
   support can see that money was returned while the subscription lives. A
   refund failure is **503 `subscription_refund_failed`**, nothing cancelled,
   nothing erased. One Stripe client is built per deletion, used for both calls
   and closed afterwards.
7. **Refund trace (retry visibility).** After the refund succeeds and before the
   erasure, a `workspace_settings` row `privacy.withdrawal_refund`
   (`amount_cents`, `currency`, `at`) is committed. If the erasure then fails
   (Firebase), the `customer.subscription.deleted` webhook ends the subscription
   row, so the retry sees no live subscription; it finds the trace and answers
   `refunded: true` with the stored amount and currency, without calling Stripe.
   The trace is only honoured for 14 days, is deleted with the workspace, and a
   failure to write it never blocks the deletion. No migration.
8. The response has `refunded` (bool), `refunded_amount_cents` and `currency`
   (null unless refunded; the amount can be null even when refunded, see 5).

Logs carry only status/code/counts, never ids, amounts or e-mail addresses (the
one ERROR line of point 6 carries the workspace public id).

## Stripe TEST-MODE checklist (must pass before payments go live)

Use a test-mode account with Managed Payments enabled, a real test checkout with
`4242 4242 4242 4242`, and `PORTFYL_BILLING_ENABLED=1` on a throwaway deployment
or local instance. Record the result of each line here.

1. `DELETE /v1/subscriptions/{id}` (prorate=false, invoice_now=false) under
   Managed Payments: does it succeed, or does Stripe reject it for a Managed
   Payments subscription? The docs do not confirm it. If it is rejected the
   cancel step (already in production code since c3fea12) must switch to another
   mechanism before go-live.
2. `GET /v1/invoices?subscription=...&status=paid` and
   `GET /v1/invoice_payments?invoice=...&status=paid` on the Managed Payments
   invoice: is the payment (`payment.payment_intent`) returned and is it the
   PaymentIntent that `POST /v1/refunds` accepts? If the Managed Payments order
   exposes the payment only as a charge or differently, adjust
   `StripeClient.list_paid_payments`.
3. `POST /v1/refunds` with `payment_intent` (no `amount`) and `reason=requested_by_customer`:
   does it succeed under Managed Payments, is the **sales tax included** in the
   refunded amount (the refund must equal the full amount the customer paid),
   does `refunded_amount_cents` equal that amount, and how does the Stripe
   balance change (the refund reduces the balance; Stripe/Link is the merchant
   of record).
4. Same request twice with the same idempotency key (replay) and again after
   the 24 h key expiry (expect `charge_already_refunded`): confirm the second
   call does not refund twice and the error code really is
   `charge_already_refunded` for a PaymentIntent refund.
5. Refund then cancel, then delete: run the whole flow from the UI inside the
   window, and the same after back-dating `subscriptions.created_at` by 15 days
   (no refund, cancel only).
6. Link-initiated refunds: Link support can refund the customer too (Stripe may
   refund within 60 days, and after 48 hours without the merchant's reply).
   Check what a customer-initiated refund through Link looks like in the
   Dashboard and that a later Portfyl refund attempt on the same payment ends
   in `charge_already_refunded`, not in an error.
7. Webhooks after erasure: `charge.refunded` / `customer.subscription.deleted`
   / `invoice.*` events for the erased workspace. The workspace metadata no
   longer maps to a workspace, so the event is expected to be **quarantined**
   (`stripe_events.status = quarantined`), not retried forever and not an error
   page. Confirm that in the logs and that Stripe gets HTTP 200.
8. Disputed payment: refund of a disputed charge returns `charge_disputed` or
   `refund_disputed_payment`; the deletion then stops with 503
   `subscription_refund_failed` (nothing erased). Decide what support does.
9. Cancel while a **subscription schedule** is attached (a booked plan change):
   does `DELETE /v1/subscriptions/{id}` succeed, or must the schedule be
   released first? Run it with a booked change, inside the window.
10. The key scheme: a refund that failed with a stored error (force one, for
    example a blocked balance), then retry after more than a minute and again
    after more than 24 h. The retry must not replay the stored error and must
    end in a refund or `charge_already_refunded`.
11. Refund `status` under Managed Payments: does `POST /v1/refunds` answer
    `succeeded` or `pending` (and does it ever answer `requires_action` or
    `failed`)? Confirm that `pending` still reaches the customer and that
    `refunded_amount_cents` is the amount.
12. Failed erase after a refund: make the Firebase deletion fail once, confirm
    the retry answers `refunded: true` with the amount from the trace even
    though the webhook has already ended the subscription.

## Open points

- The legal basis (deleting the workspace as withdrawal, 100 % refund) is the
  operator's decision; the lawyer questions live in
  `docs/legal/poznamky-pro-pravnika.md`.
- Subscriptions the customer already ended (cancelled via the Customer Portal,
  `ended_at` set) inside the 14 days are not refunded by the deletion: there is
  no live subscription to act on. Withdrawal by e-mail is handled by support,
  and Link may also refund.
- Without `cancel_subscription: true` a paid subscription inside the window is
  never deleted silently: renewing, `cancel_at_period_end` and `past_due` all
  answer 409 `active_subscription`, so the dialog can show the refund. The dialog
  must send the flag (and `refund_expected: true` when it promised a refund)
  whenever the status says `withdrawal_open` or a paid subscription exists.
- **Known, accepted risk: repeated withdrawal.** A new Stripe subscription
  creates a new row and so a new 14-day window. Subscribe, delete the workspace,
  create a new workspace, subscribe again, delete again gets a 100 % refund each
  time. The trial guards (`trial_identities`, `trial_ip_marks`,
  `trial_broker_marks`) only cover the free trial, not refunds. Owner decision:
  monitor refunds in the Stripe Dashboard; a cheap safeguard if it happens is a
  refund counter per HMAC of the e-mail (like the trial guards) that logs or
  alerts from the second refund, or that routes it to manual review.
- Invoices paid only from the customer balance or credit notes are not
  refunded by this code (no payment to refund); partial earlier refunds are
  topped up to the full amount by the no-`amount` refund.
- Only one page (100) of invoices and of payments is read; a subscription inside
  14 days has one or two.
- Not built: the on-site withdrawal button (art. 11a, Directive 2023/2673; Czech
  `s. 1830a OZ` expected 1 Jan 2027).
- The Stripe docs were read on 2026-11-24 for the `2026-11-18.endive` reference
  while Portfyl pins `2026-09-30.endive`; the shapes used here (InvoicePayments,
  Refund create) are the same family, but nothing was run against the real API.

## Related

- Architecture: [[Billing and Stripe]]
- Architecture: [[Account deletion and data lifecycle]]
