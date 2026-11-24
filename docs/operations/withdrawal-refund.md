# Withdrawal refund on workspace deletion

Status: implemented on branch `feat/withdrawal-refund` (2026-11-24), **not
deployed, never run against Stripe**. Payments are off in production
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
the row. A lost webhook that is only repaired by the daily `billing_reconcile`
can push it later, which favours the customer. No migration was needed.

`GET /api/billing/status`: the `subscription` object has `ordered_at`,
`withdrawal_ends_at` (ISO UTC) and `withdrawal_open` (bool); the whole object is
`null` without a subscription. `consent_version` is `2026-11-24`
(`CHECKOUT_CONSENT_VERSION`), changed with the new checkout consent text.

`POST /api/settings/account/deletion` (`account_deletion.py`):

1. All guards as before (owner, typed name, fresh re-authentication, sole
   member). A renewing subscription (active/trialing, not ending) without
   `cancel_subscription: true` is still **409 `active_subscription`**.
2. With the flag and the window open (also for a subscription that is already
   `cancel_at_period_end`, or `past_due`): **refund first**, then **cancel**,
   then **erase**. With the flag and the window closed: cancel, then erase, no
   refund call. A `cancel_at_period_end` or `past_due` subscription outside the
   window, or without the flag, is left untouched as before.
3. Refund = every successful payment of the subscription, 100 %, no `amount`
   (`POST /v1/refunds` with `payment_intent`, or `charge`). Payments are found
   with `GET /v1/invoices?subscription=&status=paid`, then
   `GET /v1/invoice_payments?invoice=&status=paid` (since API version 2025-03-31
   the invoice no longer carries `payment_intent`/`charge`; the pinned
   `2026-09-30.endive` returns InvoicePayments with `payment.type` of
   `payment_intent` or `charge`). A legacy `payment_intent`/`charge` on the
   invoice is used only when no InvoicePayment comes back. Zero-amount payments
   are skipped. Nothing paid: no refund, cancel still happens, `refunded: false`.
4. Retry safety: idempotency key `withdrawal-refund-<subscription id>-<payment id>`;
   Stripe's `charge_already_refunded` counts as success. Order refund, cancel,
   erase means a failure between steps is repaired by retrying the same request
   (the retry refunds idempotently, then cancels; a cancel that is already done
   in Stripe is success via 404/`resource_missing`).
5. Failures: refund step (any other `StripeError`, billing off, no client) is
   **503 `subscription_refund_failed`**, nothing cancelled, nothing erased.
   Cancel step is **503 `subscription_cancel_failed`** as before.
6. The response gains `refunded` (bool), `refunded_amount_cents` and `currency`
   (null unless refunded). Existing fields are unchanged.

Logs carry only status/code/counts, never ids, amounts or e-mail addresses.

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

## Open points

- The legal basis (deleting the workspace as withdrawal, 100 % refund) is the
  operator's decision; the lawyer questions live in
  `docs/legal/poznamky-pro-pravnika.md`.
- Subscriptions the customer already ended (cancelled via the Customer Portal,
  `ended_at` set) inside the 14 days are not refunded by the deletion: there is
  no live subscription to act on. Withdrawal by e-mail is handled by support,
  and Link may also refund.
- Without `cancel_subscription: true` a subscription that is already
  `cancel_at_period_end` is deleted untouched and **not** refunded, even inside
  the window. The dialog must send the flag whenever the status says
  `withdrawal_open` or a paid subscription exists.
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
