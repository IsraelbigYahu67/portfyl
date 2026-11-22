---
type: hub
layer: cross
tags: [arch/hub]
generated: false
---
# Edition boundary

One codebase ships two products. `PORTFYL_EDITION=local` is the owner's private instance: it keeps the Tax Report and has no billing. `PORTFYL_EDITION=cloud` is the multi-tenant SaaS with Free, Investor and Pro plans. The Tax Report and the Screener are permanently excluded from cloud; this is a deliberate product decision, not something postponed. The boundary is enforced in the backend first and fails closed, and the frontend only follows it.

## How it works
- [[edition]] is the central capability registry. Each capability key (for example `portfolio_dashboard`, `broker_sync`, `options`, `tax_report`, `screener`) has a class: `cloud_free`, `cloud_investor`, `cloud_pro` or `local_only`. `edition_allows` lets local use everything and lets cloud use everything except `local_only`.
- `PORTFYL_EDITION` must be exactly `local` or `cloud`. `edition_from_env` raises if it is missing or has any other value, so the app refuses to start rather than guess. [[start (bat)]] declares local; the [[Dockerfile]] declares cloud.
- [[routers.capabilities]] exposes `GET /api/capabilities` with the edition, the allowed keys and their classes. Shared frontend code reads it to hide or show entries.
- [[routers.local_features]] holds the owner-only routes (Tax Report and Screener). [[main]] imports and mounts it only when the edition is local, so in cloud those operations do not exist and do not even appear in OpenAPI. Never re-add Tax Report or Screener to shared routers, `App.jsx`, `Sidebar.jsx` or `api.js`.
- In [[main]], other cloud-only pieces are mounted by edition: [[routers.billing]], the no-payment [[routers.test_plans]] (only while billing is off), [[routers.internal_jobs]] and the [[cloud_gate]] middleware. In local, in-process pollers run the background jobs instead of Cloud Scheduler.
- Frontend: Vite resolves the alias `@edition-manifest` to [[editions.local]] or [[editions.cloud]] at build time ([[frontend.vite.config (js)]]). [[src.App]] takes `EDITION_ROUTES`, `EDITION_NAVIGATION` and `EditionShell` from that manifest and filters the route entries with [[editions.filter]] using the runtime capabilities. Local-only API calls live in [[editions.localApi]] and a mobile-preview toggle in [[editions.viewMode]].
- Plan limits (Free / Investor / Pro) build on these classes in [[entitlements]] and [[plans]]; see [[Billing and Stripe]].
- Build and test commands: `npm run build` / `npm test` (local) and `npm run build:cloud` / `npm run test:cloud` (cloud). Run all four for edition-sensitive changes. See [[Testing]].

## Why it is built this way
- A UI-only hide would be unsafe: a cloud user could still call a hidden endpoint. So the routes themselves are absent in cloud.
- Fail-closed means a typo in `PORTFYL_EDITION` stops startup instead of silently exposing owner-only features.
- The frontend has a second guard: even if a manifest listed a route, [[editions.filter]] drops it when the runtime capabilities from the backend do not include it.

## Key code
- [[edition]]: registry, `edition_from_env`, `capability_payload`.
- [[routers.capabilities]]: runtime capability endpoint.
- [[routers.local_features]]: local-only routes.
- [[main]]: edition-dependent mounting.
- [[editions.local]]: local manifest (includes Tax Report).
- [[editions.cloud]]: cloud manifest.
- [[editions.filter]]: capability filter for route entries.
- [[entitlements]]: server-side plan enforcement on top of the edition.

## Related hubs
- [[Portfyl]], [[Backend]], [[Frontend structure]], [[Billing and Stripe]], [[Free trial]], [[Jobs and Cloud Scheduler]], [[Deploy and operations]], [[Testing]]

## Docs
- [[superpowers/plans/2026-09-01-portfyl-saas-monetization]]: sections on tiers and why Tax Report and Screener stay out of cloud.
- [[finished]]: record of the finished edition-boundary plan (`2026-09-03-portfyl-edition-boundary`).
- [[superpowers/plans/2026-09-05-portfyl-plans-without-payments]]: plan switching before real payments.
