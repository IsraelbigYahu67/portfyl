---
type: hub
layer: cross
tags: [arch/hub]
generated: false
---
# Tenancy and RLS

Portfyl is multi-tenant: many people use one database, and nobody may see anyone else's data. Each person is a `User`, who belongs to one or more `Workspace` rows through a `Membership`. All portfolio data hangs off a workspace. Isolation is enforced twice on purpose: once in application code (queries filtered by workspace) and once in PostgreSQL itself (forced row-level security). Both layers are mandatory; neither replaces the other.

## How it works
- **User, Membership, Workspace.** A new sign-in creates all three together (see [[Auth and sessions]]). `Membership` carries a role (`owner`) and a status (`active`). Tables: [[users (table)]], [[memberships (table)]], [[workspaces (table)]], created in [[0001_multiuser_schema]].
- **Request context.** [[tenancy]] `get_request_context()` reads the session cookie, loads the active memberships, picks the workspace named by the `X-Workspace-ID` header (or the only one) and returns a `RequestContext` (user, workspace, membership, session). An unknown or foreign workspace id gives 404 `resource_not_found`, never 403. Several workspaces and no header gives 400 `workspace_required`.
- **RLS identity.** `set_rls_context` in [[database]] sets two transaction-local settings, `portfyl.user_id` and `portfyl.workspace_id`, and re-applies them at the start of each new transaction in the same session.
- **Portfolio guard.** `require_portfolio()` in [[tenancy]] finds a portfolio by its UUID `public_id` but always inside `Portfolio.workspace_id == context.workspace.id`; with no id it takes the default portfolio. Routers use it, or an equivalent workspace-filtered query, never a global owner value.
- **UUID public ids only.** The API never accepts or returns raw integer keys. Every tenant model has a `public_id` UUID ([[models]]). See [[routers.portfolios]].
- **Forced RLS.** [[0002_tenant_rls]] enables and **forces** row-level security on the tenant tables. The `portfyl_runtime` role is NOBYPASSRLS, so even a buggy handler cannot read across tenants. Policies compare each row with `portfyl.workspace_id` or `portfyl.user_id`. Tables such as [[memberships (table)]] and [[user_settings (table)]] are user-scoped; [[portfolios (table)]], `transactions`, `watchlists` and the rest are workspace-scoped.
- **Jobs need a narrow exception.** Background jobs must list every active workspace before they can pick one, so [[0003_job_workspace_enumeration]] adds a SELECT-only policy on `workspaces`, gated by a separate `portfyl.job_context` flag. It does not weaken per-request isolation. See [[Jobs and Cloud Scheduler]].
- **Frontend scoping.** The axios interceptor in [[src.api]] adds `X-Workspace-ID` and `X-CSRF-Token`, and injects the active `portfolio_id` into every request except the prefixes in `PORTFOLIO_AGNOSTIC_PREFIXES`. [[auth.AuthProvider]] supplies the workspace; [[components.PortfolioSwitcher]] changes the active portfolio.
- **Settings stores.** [[app_settings]] holds scoped key/value settings per workspace and per user ([[workspace_settings (table)]], [[user_settings (table)]]).

## Key code
- [[tenancy]]: `get_request_context`, `require_portfolio`, `require_csrf`, `csrf_guard`
- [[database]]: engine, `set_rls_context`, `release_connection`, Alembic head check
- [[models]]: every table, with `public_id` columns
- [[0002_tenant_rls]]: the forced policies
- [[0003_job_workspace_enumeration]]: job-only workspace listing policy
- [[app_settings]]: scoped settings
- [[routers.portfolios]]: portfolio CRUD inside a workspace
- [[src.api]]: request headers and portfolio scoping
- [[components.PortfolioSwitcher]]: active portfolio picker

## Data
- [[users (table)]], [[workspaces (table)]], [[memberships (table)]], [[portfolios (table)]]
- [[workspace_settings (table)]], [[user_settings (table)]]
- [[0001_multiuser_schema]], [[0002_tenant_rls]], [[0003_job_workspace_enumeration]]

## Related hubs
- [[Auth and sessions]]
- [[Database and migrations]]
- [[Testing]]
- [[Jobs and Cloud Scheduler]]
- [[Account deletion and data lifecycle]]
- [[Secrets and security]]
- [[Backend]]
- [[Portfyl]]

## Docs
- [[security/tenant-isolation-matrix]]: the Alice/Bob matrix, one row per route, with application and RLS tests (the beta go/no-go gate)
- [[superpowers/specs/2026-09-01-portfyl-multiuser-foundation-design]]: design of users, workspaces and RLS
- [[superpowers/plans/2026-09-01-portfyl-saas-monetization]]: the wider SaaS plan
- [[finished]]: records of the finished multi-user foundation work
