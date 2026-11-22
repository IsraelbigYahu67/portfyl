---
type: hub
layer: cross
tags: [arch/hub]
generated: false
---
# Billing and Stripe

Billing decides what a cloud workspace is allowed to do and how it pays for it. There are three plans: Free, Investor (EUR 5.99 per month) and Pro (EUR 9.99 per month), monthly only, VAT included. Payments run through **Stripe Managed Payments**, where Stripe (with Link) is the merchant of record, so Portfyl never handles card data or VAT filing. Billing exists only in the cloud edition. The local edition has no billing and gets every feature (see [[Edition boundary]]).

Billing is switched off until `PORTFYL_BILLING_ENABLED=1` is set. While it is off, a no-payment plan switch is mounted so testers can try plans. When billing goes on, that switch is unmounted and its stored choice is ignored.

## How it works
- **Plans and limits** live in [[plans]]: a `PlanTier` (free, investor, pro), the limits for each (portfolios, broker connections, watchlists, alerts, autosync interval) and which capability needs which minimum plan. Positions and transactions are unlimited on every plan.
- **Config** is read from environment variable names by [[billing_config]] (for example `PORTFYL_BILLING_ENABLED`, `PORTFYL_APP_URL`, `PORTFYL_STRIPE_PRICE_INVESTOR`, `PORTFYL_STRIPE_PRICE_PRO`). The Stripe prices themselves live in Stripe, not in code.
- **Checkout**: `POST /api/billing/checkout` in [[routers.billing]] creates a Stripe Customer and a Checkout Session with Managed Payments turned on. Only the workspace owner may call it, and it refuses if a live subscription exists.
- **Consent audit**: Managed Payments checkout cannot show custom text, so the customer ticks the "start now, 14-day withdrawal" consent on [[pages.Pricing]]. The API rejects a checkout without it and writes a `billing.checkout.created` audit event ([[audit]]) with the consent version.
- **Changing plan**: `POST /api/billing/change-plan` books a switch to the other paid plan at the end of the period, with no proration. Cancelling or moving to Free goes through the Customer Portal (`POST /api/billing/portal`).
- **Webhook**: `POST /api/billing/webhook` checks Stripe's signature and records each event once in [[stripe_events (table)]]. The event only says which subscription changed. [[billing_sync]] then re-fetches the subscription from the Stripe API and writes the result into [[subscriptions (table)]]. A forged or reordered event can therefore never set a status Stripe does not report.
- **Safety net**: the daily `billing_reconcile` job (`POST /api/internal/jobs/billing_reconcile`, see [[routers.internal_jobs]] and [[Jobs and Cloud Scheduler]]) re-reads every customer's subscriptions to catch lost webhooks. A failed renewal keeps paid features on for a 14-day grace period.
- **Deciding the plan**: [[entitlements]] `resolve_entitlements` picks the effective plan in this order: live subscription, then the private test selection (only while billing is off), then an active free trial, then Free. It also enforces limits and per-capability access on every request.
- **Test switch**: [[routers.test_plans]] (`/api/test-plans`) stores a plan choice in the workspace settings. It is mounted only when billing is off (see the bottom of [[main]]).
- **Frontend**: [[pages.Pricing]] shows plans and prices ([[lib.planPrices]]) and calls billing or test-plans. [[lib.billingStatusQuery]] reads `/api/billing/status`, and [[components.UpgradePrompt]] is shown when a feature needs a higher plan.

## Key code
- [[routers.billing]]: checkout, confirm, change-plan, portal, status and the signed webhook.
- [[billing_sync]]: turns a fetched Stripe subscription into local rows; owns the daily reconcile pass and the grace period.
- [[billing_config]]: reads billing settings from the environment and checks they are valid.
- [[stripe_client]]: thin Stripe REST client and webhook signature check.
- [[entitlements]]: the single place that decides plan, capabilities and limits.
- [[plans]]: plan tiers, limits and minimum plan per capability.
- [[routers.test_plans]]: no-payment plan switch used while billing is off.
- [[trials]]: the free Pro trial that sits between a subscription and Free (see [[Free trial]]).
- [[pages.Pricing]]: pricing page with the consent checkbox.
- [[lib.planPrices]]: price display on the frontend.
- [[lib.billingStatusQuery]]: shared query for billing status.
- [[components.UpgradePrompt]]: upsell shown for locked features.
- [[components.billing (folder)]]: trial banner and entitlement refresh helpers.

## Data
- [[subscriptions (table)]]: local copy of the Stripe subscription (Stripe stays the source of truth).
- [[billing_customers (table)]]: one Stripe Customer per workspace.
- [[stripe_events (table)]]: global receipt log used to ignore duplicate webhooks.
- [[usage_counters (table)]] and [[usage_reservations (table)]]: usage tracking used by limits.
- [[0010_billing_entitlements]]: first billing, trial and usage tables.
- [[0025_stripe_billing]]: Stripe Managed Payments state.

## Related hubs
- [[Free trial]]
- [[Edition boundary]]
- [[Tenancy and RLS]]
- [[Jobs and Cloud Scheduler]]
- [[Secrets and security]]
- [[Emails]]
- [[Deploy and operations]]

## Docs
- [[superpowers/plans/2026-09-01-portfyl-saas-monetization]]: product spec, pricing and rollout for the whole SaaS conversion.
- [[superpowers/plans/2026-09-04-portfyl-billing-entitlements]]: the entitlement design.
- [[superpowers/plans/2026-09-05-portfyl-plans-without-payments]]: the no-payment plan switch.
- [[superpowers/specs/2026-09-05-portfyl-plans-without-payments-design]]: its design spec.
- [[superpowers/plans/2026-09-11-portfyl-revenue-launch-closing-plan]]: what is left before payments go live.
- [[operations/billing-verification-2026-09-05]]: billing verification record.
- [[research/mor-platforms-eu-2026-09-05/report-source]]: merchant-of-record research behind choosing Managed Payments.
- [[deploy.cloudrun (md)]]: runbook section "Stripe Managed Payments".
