---
type: hub
layer: cross
tags: [arch/hub]
generated: false
---
# Portfyl

Portfyl is a portfolio analytics app for an investor who uses Trading 212 or Interactive Brokers (IBKR). You import broker CSV files (or sync through a broker API), and then you see performance, allocation, dividends and tax reports for one or more portfolios. It used to be a single-user app called "Snowball Analytics". It is now a multi-tenant product: every user belongs to a workspace, and every row of data is scoped to a workspace. This note is the start page of the architecture map, and every other hub is linked from here.

## How it works
- There are two editions built from one codebase: `local` (the owner's private instance, keeps Tax Report, no billing) and `cloud` (the multi-tenant SaaS with Free / Investor / Pro plans). See [[Edition boundary]] and [[edition]].
- Request path in the cloud edition: browser -> Cloudflare (adds a secret edge token, checked by [[edge_trust]]) -> Cloud Run container -> FastAPI app in [[main]] -> middleware such as [[cloud_gate]] and [[rate_limit]] -> [[tenancy]] (session cookie + `X-Workspace-ID` + membership) -> PostgreSQL (Neon) with forced row-level security. See [[Tenancy and RLS]].
- The same container serves the built React single-page app ([[spa_serving]]), so one origin serves both `/api` and the pages.
- Identity comes from Firebase; Portfyl then issues its own opaque session. See [[Auth and sessions]] and [[firebase_identity]].
- Background work (alerts, broker sync, dividends, cleanup) runs from Cloud Scheduler in the cloud edition. See [[Jobs and Cloud Scheduler]].
- Schema changes are Alembic migrations that run explicitly, never at web startup. See [[Database and migrations]].

## Key code
- [[main]]: creates the FastAPI app and mounts every router under `/api`.
- [[tenancy]]: turns a request into a workspace-scoped context.
- [[database]]: engine, sessions, RLS context, Alembic head check.
- [[models]]: all SQLAlchemy tables.
- [[edition]]: the capability registry that decides what each edition may do.
- [[src.api]]: the frontend axios client that adds portfolio, workspace and CSRF context.
- [[src.App]]: the frontend routes.

## All hubs
- [[Backend]]: the FastAPI application and its rules.
- [[Frontend structure]]: the React single-page app.
- [[Database and migrations]]: PostgreSQL, Alembic and the tables.
- [[Deploy and operations]]: Cloud Run, Neon, Cloudflare, runbooks.
- [[Testing]]: fast suite, PostgreSQL gate, Vitest, CI.
- [[Edition boundary]]: local vs cloud, fail-closed capabilities.
- [[Auth and sessions]]: Firebase login and Portfyl sessions.
- [[Tenancy and RLS]]: workspaces, memberships, row-level security.
- [[Secrets and security]]: encrypted secrets, headers, rate limits, logging.
- [[Account deletion and data lifecycle]]: export, immediate deletion, retention.
- [[Emails]]: Brevo e-mails and their templates.
- [[Jobs and Cloud Scheduler]]: periodic background passes.
- [[Billing and Stripe]]: plans, Stripe checkout, entitlements.
- [[Free trial]]: the 10-day Pro trial without a card.
- [[Broker importers and sync]]: file importers and broker API syncs.
- [[Market data]]: prices, FX, fundamentals and their sources.
- [[Portfolio analytics]]: performance, allocation, dividends, tax.
- [[Onboarding and CSV import]]: first-run flow and the safe import preview.
- [[Alerts and integrations]]: price alerts, Discord, notifications.

## Where to start reading
- First read `CLAUDE.md` ([[CLAUDE (md)]]) in the repo root; it is the main source of truth.
- For the big picture of the SaaS conversion read [[superpowers/plans/2026-09-01-portfyl-saas-monetization]].
- To follow one request end to end: [[main]], then [[tenancy]], then a router such as [[routers.portfolio]].
- For the look of the UI read [[DESIGN (md)]] before any frontend change.

## Docs
- [[finished]]: records of the finished workstreams (B, C, D and the edition boundary).
- [[superpowers/plans/2026-09-01-portfyl-saas-monetization]]: spec, market research, pricing and rollout plan.
- [[superpowers/specs/2026-09-01-portfyl-multiuser-foundation-design]]: design of the multi-user foundation.
- [[security/tenant-isolation-matrix]]: the Alice/Bob tenant isolation matrix.
