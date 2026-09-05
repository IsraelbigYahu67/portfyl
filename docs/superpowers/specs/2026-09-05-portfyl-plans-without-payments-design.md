# Portfyl Plans Without Payments Design

## Status

Approved in conversation on 2026-09-05.

## Goal

Keep Portfyl's cloud plan catalogue and server-enforced Free-plan limits while
removing the unused Stripe payment runtime and the seven-day trial. The cloud
UI continues to advertise Free, Investor, and Pro, but clearly states that paid
plans are not yet available and never starts a network checkout.

## Product behaviour

- Every cloud workspace resolves to the Free plan until a future payment
  provider is deliberately implemented.
- The local edition remains unrestricted and does not query plan state.
- Investor and Pro remain visible as planned products with the existing EUR
  monthly and annual prices and feature lists.
- Paid-plan CTAs say that availability is forthcoming. Activating a CTA opens
  an accessible in-page dialog explaining that payments are not supported yet.
- The pricing page has no billing-management button, checkout-success state,
  payment-failure state, trial countdown, or subscription polling.
- Real-data import and broker connection never start a trial.

## Backend architecture

`plans.py` becomes the provider-neutral source of truth for plan names,
capability requirements, and resource/usage limits. `entitlements.py` keeps the
existing enforcement dependencies and usage reservation primitives, but cloud
resolution has a single Free source and no subscription/trial database lookup.

The Stripe adapter, webhook/reconciliation code, payment API router, payment
scheduler endpoint, provider configuration, catalogue verification script, and
Stripe dependency are removed. The cloud app continues to mount the general
internal jobs router for alerts, autosync, and dividends.

## Persistence

A new Alembic revision drops the five payment/trial tables created by revision
0010: `billing_customers`, `subscriptions`, `trial_grants`, `stripe_events`, and
`billing_actions`. Provider-neutral `usage_counters`, `usage_reservations`, and
`notification_outbox` remain.

The downgrade recreates only the removed 0010 tables and their original
indexes, grants, and RLS policies. It never drops or rewrites the retained
usage/outbox tables, so their data survives a development rollback. The
application does not preserve payment/trial rows during the upgrade because no
production payment provider was enabled and trial activation is intentionally
retired.

## Frontend design

The page keeps Portfyl's existing dark glass surfaces, typography, spacing, and
green status colour instead of introducing a new visual system. The information
hierarchy changes from account billing management to a product comparison:

```text
Tarify                         Platby připravujeme
Krátké vysvětlení              bez skrytého checkoutu

[ Free ]       [ Investor ]       [ Pro ]
 current       coming soon        coming soon

                   [ informational dialog ]
```

The status notice is the single visual emphasis. Plan cards stay quiet and
comparable. The dialog uses `role="dialog"`, an accessible name, keyboard focus,
and explicit close controls. Copy is in English to match the existing product
UI, with no simulated checkout error.

## Documentation

The Cloud Run runbook removes Stripe secrets, environment variables, webhook,
catalogue, and billing scheduler setup. Historical Workstream E verification is
retained as a dated record but receives a superseding note. `CLAUDE.md` and the
active SaaS plan describe payments as deferred and provider undecided, with
Paddle noted only as the likely future choice rather than an implemented fact.

## Verification

- Focused frontend tests prove the static catalogue and informational dialog.
- Backend route tests prove no payment endpoints are registered in either
  edition.
- Entitlement tests prove cloud is always Free and local remains unrestricted.
- Trial call-site tests prove successful imports/connections have no activation
  side effect through the absence of the trial integration.
- Migration tests and PostgreSQL RLS/runtime-role lists cover only retained
  tenant tables.
- Full backend tests, local/cloud frontend tests, and local/cloud builds pass.

## Non-goals

- Implementing Paddle, Paddle webhooks, checkout, refunds, taxes, or a customer
  portal.
- Adding a wait-list or collecting contact details from the pricing dialog.
- Introducing manual paid-plan grants.
- Changing plan prices, limits, or feature allocation.
