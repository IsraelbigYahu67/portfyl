# Portfyl tenant isolation matrix

**Status: this document is executable.** Every row below is backed by a named
test. If a row and its test ever disagree, the test is right and this file is
stale — fix the file, never the assertion.

## The go/no-go gate

No multi-user beta ships until this command passes, with no failures and
**no skips**:

```bash
cd backend && python -m pytest tests/postgres/test_alice_bob_matrix.py tests/postgres/test_runtime_role.py -v
```

It requires a disposable PostgreSQL 16 (`docker compose -f
deploy/docker-compose.postgres-test.yml up -d --wait`, or an explicit
`TEST_DATABASE_URL` whose database name contains `test`). SQLite has no
row-level security, so the fast unit suite can neither prove nor disprove
anything in this document — it is not a substitute and must never be treated
as one.

The full backend suite (`cd backend && python -m pytest tests/ -v`) must also
be green; it adds the calculation regressions and the task-scoped tenancy
suites from Tasks 5–8 around this gate.

## The two layers, and why both are required

| Layer | Where | What it stops | What it would miss alone |
| --- | --- | --- | --- |
| Application predicates | `tenancy.py` + every router query | A request that asks for another tenant's row | One forgotten `WHERE workspace_id = …` |
| Forced PostgreSQL RLS | `alembic/versions/0002_tenant_rls.py`, enforced against the `portfyl_runtime` role | Any statement — including one from a future, buggy handler | A code path that legitimately sets the RLS context to a workspace the caller is not a member of |

RLS is a **filter on the transaction's context**, not an authorization system:
`test_runtime_role.py::test_the_database_would_serve_bobs_rows_to_bobs_context`
proves the database serves Bob's rows to any session whose
`portfyl.workspace_id` is Bob's. The membership check inside
`tenancy.get_request_context` is therefore the only thing standing between a
forged `X-Workspace-ID` header and another customer's data — which is what
`test_runtime_role.py::test_forged_workspace_context_is_still_blocked_by_membership_endpoint`
asserts.

Consequently: **application-level workspace predicates remain mandatory even
though RLS is active.** Removing one is not "covered by RLS"; it is one
context-setting bug away from a breach.

## Status contract

| Condition | Status | Body |
| --- | --- | --- |
| No session cookie | **401** | `{"code": "authentication_required"}` |
| Valid session, missing/incorrect `X-CSRF-Token` on a CSRF-gated route | **403** | `{"code": "csrf_failed"}` |
| Foreign resource UUID (another tenant's row) | **404** | identical to a random UUID |
| Nonexistent UUID | **404** | identical to the foreign case |
| Foreign `portfolio_id` query parameter | **404** | identical to a random UUID |
| Forged / unknown / malformed `X-Workspace-ID` | **404** | `{"code": "resource_not_found"}` |
| Duplicate name **inside** one workspace | **409** | — |
| Same name in **another** workspace | **2xx** | it is a different customer's data |
| Business-rule refusal on the caller's own row (e.g. deleting the last portfolio) | **400** | never confused with the 404 tenancy contract |

Foreign resources return the *same* 404 as nonexistent ones on purpose. A
distinguishable 403 would confirm that some other tenant owns that ID and turn
the API into an enumeration oracle. `FOREIGN_STATUS` in
`backend/tests/postgres/matrix_cases.py` is a single constant for this reason,
and every foreign case is paired with a random-UUID case asserting the two
responses are byte-identical.

Public API identifiers are UUID strings only. Internal integer primary keys are
neither accepted nor serialized anywhere in the table below.

## Resource matrix

Route inventory: `backend/tests/postgres/matrix_cases.py` (literal data).
Assertions: `backend/tests/postgres/test_alice_bob_matrix.py` (application layer)
and `backend/tests/postgres/test_runtime_role.py` (raw SQL, `portfyl_runtime`).

Application test names are abbreviated below; each is parametrized by the
`resource` id in the first column, e.g.
`test_own_list_returns_2xx_and_never_a_foreign_uuid[watchlists]`.

| Resource | Routes | Own (Alice) | Foreign (Bob) | Application test | RLS test |
| --- | --- | --- | --- | --- | --- |
| `portfolios` | `GET/POST /api/portfolios`, `PATCH/DELETE /api/portfolios/{uuid}` | list 200, create 200, update 200, delete 200 (400 on the last one) | 404 | `test_own_list_…`, `test_own_create_…`, `test_own_update_succeeds`, `test_own_portfolio_delete_succeeds_once_a_second_one_exists`, `test_deleting_the_last_portfolio_is_refused_with_400_not_404`, `test_foreign_resource_uuid_update_…`, `test_foreign_resource_uuid_delete_…` | `test_alice_runtime_role_cannot_update_bob`, `test_alice_runtime_role_cannot_delete_bob`, `test_alice_runtime_role_reads_only_her_own_workspace_rows[portfolios]` |
| `transactions` | `GET/POST /api/portfolio/transactions`, `DELETE /api/portfolio/transactions/{uuid}`, `DELETE /api/portfolio/transactions` | list 200, create 200, delete 200, delete-all 200 | 404 | `test_own_list_…[transactions]`, `test_own_create_…[transactions]`, `test_own_delete_succeeds[transactions]`, `test_own_mutation_succeeds[transactions-delete-all]`, `test_foreign_resource_uuid_delete_…[transactions]`, `test_foreign_portfolio_mutation_…[transactions-delete-all]` | `…reads_only_her_own_workspace_rows[transactions]`, `test_alice_runtime_role_cannot_plant_a_child_under_bobs_parent` |
| `notes` | `GET/PUT/DELETE /api/notes/transaction/{uuid}`, `GET /api/notes/all` | read 200, upsert 200, delete 200 | 404 | `test_own_list_…[notes]`, `test_own_update_succeeds[notes]`, `test_own_delete_succeeds[notes]`, `test_foreign_resource_uuid_update_…[notes]`, `test_foreign_resource_uuid_delete_…[notes]` | `…reads_only_her_own_workspace_rows[trade_notes]` |
| `benchmarks` | `GET/POST /api/analytics/benchmarks`, `PATCH/DELETE /api/analytics/benchmarks/{uuid}` | list 200 (own + shared presets), create 200, update 200, delete 200 | 404 | `test_own_list_…[benchmarks]`, `test_own_create_…[benchmarks]`, `test_own_update_succeeds[benchmarks]`, `test_own_delete_succeeds[benchmarks]`, `test_foreign_resource_uuid_*[benchmarks]` | `…reads_only_her_own_workspace_rows[benchmarks]` (presets excluded from the strict count — they are shared, workspace-less rows) |
| `cash` | `GET/POST /api/cash`, `PUT/DELETE /api/cash/{uuid}` | list 200, create 200, update 200, delete 200 | 404 | `test_own_list_…[cash]`, `test_own_create_…[cash]`, `test_own_update_succeeds[cash]`, `test_own_delete_succeeds[cash]`, `test_foreign_resource_uuid_*[cash]` | `…reads_only_her_own_workspace_rows[transactions]` (cash rows live in `transactions`) |
| `cash-interest-rates` | `GET/PUT /api/cash/interest-rates` | read 200, write 200 | 404 | `test_own_list_…[cash-interest-rates]`, `test_own_mutation_succeeds[cash-interest-rates]`, `test_foreign_portfolio_read_…[cash-interest-rates]`, `test_foreign_portfolio_mutation_…[cash-interest-rates]` | `…reads_only_her_own_workspace_rows[cash_interest_rates]` |
| `watchlists` | `GET/POST /api/watchlists`, `PATCH/DELETE /api/watchlists/{uuid}` | list 200, create 200, update 200, delete 200; duplicate name **409** | 404 | `test_own_list_…[watchlists]`, `test_own_create_…[watchlists]`, `test_own_update_succeeds[watchlists]`, `test_own_delete_succeeds[watchlists]`, `test_foreign_resource_uuid_*[watchlists]`, `test_duplicate_watchlist_name_is_409_inside_one_workspace`, `test_the_same_watchlist_name_already_lives_in_both_workspaces` | `…reads_only_her_own_workspace_rows[watchlists]` |
| `watchlist-items` | `POST /api/watchlists/{uuid}/items`, `DELETE /api/watchlists/{uuid}/items/{uuid}` | create 200, delete 200 | 404 | `test_own_create_…[watchlist-items]`, `test_own_delete_succeeds[watchlist-items]`, `test_foreign_resource_uuid_delete_…[watchlist-items]` | `…reads_only_her_own_workspace_rows[watchlist_items]` |
| `alerts` | `GET/POST /api/alerts`, `PATCH/DELETE /api/alerts/{uuid}` | list 200, create 200, update 200, delete 200 | 404 | `test_own_list_…[alerts]`, `test_own_create_…[alerts]`, `test_own_update_succeeds[alerts]`, `test_own_delete_succeeds[alerts]`, `test_foreign_resource_uuid_*[alerts]` | `…reads_only_her_own_workspace_rows[price_alerts]` |
| `user-settings` (personal) | `GET/PUT/DELETE /api/assistant/config` | read 200, write 200, delete 200 | n/a — keyed by the session's **user**, unreachable by URL | `test_own_list_…[user-settings]`, `test_own_update_succeeds[user-settings]`, `test_own_delete_succeeds[user-settings]`, `test_personal_settings_never_surface_another_users_key` | `test_personal_settings_are_scoped_to_the_user_not_the_workspace` |
| `workspace-settings` | `GET/PUT /api/settings/sync-schedule` | read 200, write 200 | reached only via `X-Workspace-ID` → 404 for a non-member | `test_own_list_…[workspace-settings]`, `test_own_update_succeeds[workspace-settings]`, `test_workspace_settings_never_surface_another_workspaces_value`, `test_forged_workspace_header_is_404_for_a_non_member` | `…reads_only_her_own_workspace_rows[workspace_settings]` |
| `broker-connections` (T212) | `GET /api/broker/trading212/status`, `POST /connect`, `POST /auto-sync`, `POST /sync`, `DELETE /connect` | status 200, auto-sync 200, disconnect 200 | 404 | `test_own_list_…[broker-connections]`, `test_own_mutation_succeeds[broker-auto-sync]`, `test_own_mutation_succeeds[broker-disconnect]`, `test_foreign_portfolio_read_…[broker-connections]`, `test_foreign_portfolio_mutation_…[broker-sync\|broker-auto-sync\|broker-disconnect]` | `…reads_only_her_own_workspace_rows[broker_connections]` |
| `broker-connections` (IBKR) | `GET /api/broker/ibkr/status`, `POST /connect`, `POST /auto-sync`, `POST /sync`, `DELETE /connect` | status 200, auto-sync 200, disconnect 200 | 404 | `test_own_portfolio_scoped_read_succeeds[broker-ibkr-status]`, `test_own_mutation_succeeds[ibkr-auto-sync\|ibkr-disconnect]`, `test_foreign_portfolio_mutation_…[ibkr-sync\|ibkr-auto-sync\|ibkr-disconnect]` | `…reads_only_her_own_workspace_rows[broker_connections]` |
| `broker-balances` | `GET /api/broker/ibkr/balance` | 200 | 404 | `test_own_list_…[broker-balances]`, `test_foreign_portfolio_read_…[broker-balances]` | `…reads_only_her_own_workspace_rows[broker_balances]` |
| `options` | `GET /api/options/{trades,summary,by-underlying,calendar}` | 200 | 404 | `test_own_portfolio_scoped_read_succeeds[options-*]`, `test_foreign_portfolio_read_…[options-*]` | `…reads_only_her_own_workspace_rows[options_trades]` |
| `polymarket` | `GET /api/polymarket/{positions,summary}`, `GET /api/broker/polymarket/status`, `POST /sync`, `DELETE /connect` | reads 200, disconnect 200 | 404 | `test_own_portfolio_scoped_read_succeeds[polymarket-*]`, `test_own_mutation_succeeds[polymarket-disconnect]`, `test_foreign_portfolio_read_…[polymarket-*]`, `test_foreign_portfolio_mutation_…[polymarket-sync\|polymarket-disconnect]` | `…reads_only_her_own_workspace_rows[polymarket_positions]` |
| `discord` | `GET/POST/PATCH/DELETE /api/discord/webhook`, `POST /api/discord/webhook/test` | read 200, create 200, update 200, delete 200 | 404 | `test_own_list_…[discord]`, `test_own_create_…[discord]`, `test_own_update_succeeds[discord]`, `test_own_delete_succeeds[discord]`, `test_foreign_portfolio_mutation_…[discord-create\|discord-update\|discord-delete\|discord-test]` | `…reads_only_her_own_workspace_rows[discord_webhooks]` |
| `imports` | `POST /api/portfolio/import-csv` | replaces only `(workspace_id, portfolio_id)` rows | 404 before the file is parsed | `test_foreign_portfolio_mutation_is_not_addressable[import]` | `…reads_only_her_own_workspace_rows[transactions]` |
| workspace-dependent jobs | `POST /api/alerts/check` (same coroutine the poller runs) | 200 | 404 | `test_own_mutation_succeeds[jobs-alert-check]`, `test_foreign_portfolio_mutation_…[jobs-alert-check]` | `tests/postgres/test_job_workspace_isolation.py` (the whole file: explicit workspace enumeration + RLS context survival across the passes' internal commits) |

### Cross-cutting cases

| Case | Expected | Test |
| --- | --- | --- |
| Any list endpoint with no session | 401 `authentication_required` | `test_unauthenticated_request_is_401[*]` |
| CSRF-gated write with no CSRF token | 403 `csrf_failed` | `test_missing_csrf_token_is_403_not_a_silent_success[*]` |
| `X-Workspace-ID` = another tenant's workspace | 404 `resource_not_found` | `test_forged_workspace_header_is_404_for_a_non_member` |
| `X-Workspace-ID` unknown / not a UUID | 404, identical bodies | `test_unknown_and_malformed_workspace_headers_match_the_foreign_contract` |
| Foreign UUID vs random UUID | identical status **and** body | `test_foreign_resource_uuid_is_indistinguishable_from_a_random_uuid[*]`, `test_foreign_portfolio_read_is_not_addressable[*]`, `test_foreign_portfolio_mutation_is_not_addressable[*]` |
| Nothing of Bob's changed after a rejected mutation | transaction count, webhook URL, alert status unchanged | assertions inside `test_foreign_portfolio_mutation_is_not_addressable` |
| Portfolio name already used by another tenant | 200 | `test_a_name_bob_already_uses_is_free_for_alice` |
| Portfolio name already used in this workspace | 409 | `test_duplicate_portfolio_name_is_409_inside_one_workspace` |

### Database-role invariants

| Invariant | Test |
| --- | --- |
| `portfyl_runtime` is not superuser and has no `BYPASSRLS`, `CREATEDB`, `CREATEROLE`, or `INHERIT` | `test_runtime_role_is_not_superuser_and_has_no_rls_bypass` |
| `portfyl_runtime` owns no table in `public` (an owner is exempt from its own policies unless FORCE is set, and can drop FORCE) | `test_runtime_role_owns_no_tables` |
| `portfyl_runtime` cannot `ALTER TABLE … DISABLE ROW LEVEL SECURITY` | `test_runtime_role_cannot_turn_row_level_security_off[*]` |
| `portfyl_runtime` cannot grant itself `BYPASSRLS` | `test_runtime_role_cannot_grant_itself_more_privileges` |
| RLS is enabled **and forced** on every tenant table | `tests/postgres/test_rls.py::test_all_tenant_tables_enable_and_force_rls` |
| No RLS context ⇒ no tenant rows (fail closed) | `test_missing_rls_context_sees_no_tenant_rows` |
| RLS context is transaction-local | `tests/postgres/test_rls.py::test_rls_context_is_transaction_local` |
| Alice's context cannot insert into, re-parent into, or write to Bob's workspace | `test_alice_runtime_role_cannot_insert_into_bobs_workspace`, `test_alice_runtime_role_cannot_reparent_her_row_into_bobs_workspace`, `test_alice_runtime_role_cannot_update_bob`, `test_alice_runtime_role_cannot_delete_bob` |
| The policy is a filter, not a blanket denial (Alice can still write her own rows) | `test_alice_runtime_role_can_still_update_her_own_rows` |
| A random context sees nothing | `test_a_random_workspace_context_sees_nothing` |

The `postgres_engine` fixture deliberately grants `BYPASSRLS CREATEDB
CREATEROLE` to `portfyl_runtime` **before** running the migrations, so the
role-invariant assertions are not tautological: they prove
`0002_tenant_rls.py` actively strips those attributes off an existing,
over-privileged role rather than merely creating a safe one on a clean
database.

### Non-tenant infrastructure tables

Not every table is workspace-scoped, and not every non-tenant table needs
RLS. `job_runs` (recurring-job heartbeats) and `rate_limit_buckets`
(fixed-window rate-limit counters,
`docs/superpowers/specs/2026-09-05-portfyl-rate-limiting-design.md`) are
process-wide infrastructure state, never keyed by workspace, and are
deliberately excluded from `RLS_TABLES` (`tests/postgres/test_rls.py`) and
`WORKSPACE_SCOPED_TABLES` (`tests/postgres/test_runtime_role.py`). Each
grants `portfyl_runtime` exactly the privileges its access pattern needs:
`job_runs` never deletes rows, so it has no DELETE grant; `rate_limit_buckets`
is upserted by every request and deleted by its hourly cleanup job, so it
has all four (`SELECT, INSERT, UPDATE, DELETE`).

| Table | Grants | Test |
| --- | --- | --- |
| `job_runs` | `SELECT, INSERT, UPDATE` | absent from `RLS_TABLES`/`WORKSPACE_SCOPED_TABLES` by design (no dedicated grants test) |
| `rate_limit_buckets` | `SELECT, INSERT, UPDATE, DELETE` | `test_runtime_role_has_exact_grants_on_rate_limit_buckets` (`tests/postgres/test_runtime_role.py`); absent from `RLS_TABLES`/`WORKSPACE_SCOPED_TABLES` by design |

## Adding a resource

1. Add the literal row to `RESOURCE_CASES` (or the appropriate list) in
   `backend/tests/postgres/matrix_cases.py`. The parametrized tests pick it up
   automatically — there is no second place to register it.
2. Seed one row for **both** tenants in `_seed_tenant` in
   `backend/tests/postgres/conftest.py`, and add its `public_id` to the `ids`
   map so foreign-URL templating can reach it.
3. If the new table carries `workspace_id`, add it to `WORKSPACE_SCOPED_TABLES`
   in `backend/tests/postgres/test_runtime_role.py` and to `RLS_TABLES` in
   `backend/tests/postgres/test_rls.py`.
4. Add the row to the table above.

A new tenant table with no RLS policy fails
`test_rls.py::test_all_tenant_tables_enable_and_force_rls`; a new table with a
policy but no application predicate fails nothing automatically — which is why
step 1 is not optional.
