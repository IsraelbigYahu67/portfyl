---
type: hub
layer: backend
tags: [arch/hub]
generated: false
---
# Backend

The backend is a FastAPI application in the `backend/` folder. It exposes a JSON API under `/api`, talks to PostgreSQL through SQLAlchemy 2.0, pulls market data with `yfinance` and other sources, and in the cloud edition also serves the built React app. Almost all business rules live in router modules and small helper modules next to `main.py`. The code is deliberately synchronous around the database, so FastAPI runs it in a thread pool.

## How it works
- [[main]] builds the `FastAPI` app, adds middleware (cloud API gate, CORS, GZip, security headers, correlation id) and mounts routers with `prefix="/api"`. State-changing routes get the central CSRF check (`csrf_guard`) from [[tenancy]].
- Some routers are mounted by edition: billing and the no-payment test plans only in cloud, `local_features` only in local, `internal_jobs` only in cloud (outside `/api`, with its own scheduler auth).
- On startup, [[main]] only checks the database revision with `assert_alembic_head` from [[database]]. It never creates or alters tables.
- Rule: an endpoint or dependency that touches a `Session` is a plain `def`, never `async def`. An `async def` one froze a whole Cloud Run instance on 2026-10-11. Async helpers that mix awaits and database work are run from sync code by [[private_loop]] (`run_on_private_loop`). Call `release_connection` in [[database]] before slow outbound calls.
- Money is normalized to CZK: transactions carry `fx_to_czk`, and [[fx]] fetches and backfills the rates (`bulk_fetch_fx`).
- Valuation rule (a product decision): fair value is judged against the 5-year average P/E, not today's P/E. The product copy states this (for example `pages.welcomeCopy`), but I did not find one backend function named for it, so read [[routers.market]] before changing valuation logic.
- `yfinance` is noisy ("possibly delisted", "no earnings dates"). Its logger is set to CRITICAL in [[main]]; handle missing data with empty/null checks instead of adding noise back. See [[Market data]].
- [[schemas]] holds the Pydantic request/response models; [[models]] holds the tables. All public IDs are UUID `public_id` values, never raw integers.

## Key code
- [[main]]: app assembly, middleware, startup checks, `/livez` and `/health`.
- [[database]]: settings, sessions, RLS context, `EXPECTED_ALEMBIC_HEAD`.
- [[models]]: SQLAlchemy tables.
- [[schemas]]: Pydantic schemas.
- [[tenancy]]: request context, workspace and portfolio authorization.
- [[private_loop]]: runs async helpers from sync threads.
- [[fx]]: FX rates into CZK.
- [[cache]]: small TTL cache for expensive yfinance endpoints.
- [[logging_setup]]: secret redaction and correlation ids.
- [[spa_serving]]: serves the built SPA and decides what is `noindex`.

## Routers (all under /api)
- Identity and account: [[routers.auth]], [[routers.auth_email]], [[routers.account]], [[routers.settings]]
- Portfolio data: [[routers.portfolios]], [[routers.portfolio]], [[routers.cash]], [[routers.allocation_targets]], [[routers.notes]]
- Analytics and market: [[routers.analytics]], [[routers.market]], [[routers.benchmarks]], [[routers.watchlists]], [[routers.options]], [[routers.polymarket]]
- Brokers: [[routers.broker]], [[routers.ibkr]], [[routers.etoro]], [[routers.broker_requests]]
- Alerts and chat: [[routers.alerts]], [[routers.discord]]
- Plans and edition: [[routers.billing]], [[routers.test_plans]], [[routers.capabilities]], [[routers.local_features]]
- Not under /api: [[routers.internal_jobs]] (Cloud Scheduler)

## Data
- Tables are listed in [[Database and migrations]].

## Related hubs
- [[Portfyl]], [[Database and migrations]], [[Tenancy and RLS]], [[Auth and sessions]], [[Edition boundary]], [[Jobs and Cloud Scheduler]], [[Billing and Stripe]], [[Market data]], [[Portfolio analytics]], [[Testing]]

## Docs
- [[superpowers/plans/2026-10-14-portfyl-code-review-fixes]]: code-review fixes.
- [[superpowers/specs/2026-09-01-portfyl-multiuser-foundation-design]]: tenancy and session design.
- [[superpowers/specs/2026-09-05-portfyl-rate-limiting-design]]: how [[rate_limit]] works.
