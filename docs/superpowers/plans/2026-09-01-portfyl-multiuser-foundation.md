# Portfyl Multi-user Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver Workstreams B and C by moving Portfyl to Neon PostgreSQL, migrating the owner's SQLite data, adding verified Firebase identities and revocable Portfyl sessions, and proving workspace isolation through application checks and PostgreSQL RLS.

**Architecture:** Firebase Authentication verifies e-mail identities, while Portfyl stores opaque revocable sessions and owns the `User -> Membership -> Workspace` authorization graph in PostgreSQL. Every tenant row carries `workspace_id`, every public resource uses UUID, and both application predicates and forced PostgreSQL RLS prevent cross-tenant access.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16, psycopg 3, Neon, Firebase Admin/JS SDKs, React 18, Vite 6, Vitest, pytest, Testcontainers/Docker Compose, Google Cloud Run.

**Spec:** `docs/superpowers/specs/2026-09-01-portfyl-multiuser-foundation-design.md`

## Global Constraints

- Implement only Workstreams B and C; do not add Stripe, billing, trials, plan entitlements, onboarding, edition capability boundaries, KMS, or a new scheduler architecture.
- Firebase owns credentials, e-mail verification, and password resets; Portfyl never stores password hashes.
- OAuth, MFA, invitations, and multi-member workspace management UI remain deferred.
- `Workspace` is the authorization tenant and every customer-owned database row must be reachable only through a verified workspace context.
- Public API identifiers are UUID strings; raw integer primary and foreign keys are never accepted or serialized.
- RLS is forced on tenant tables and the runtime database role must not own tables or have `BYPASSRLS`.
- Application-level workspace predicates remain mandatory even when RLS is active.
- Foreign resource IDs return the same 404 contract as nonexistent UUIDs.
- The real owner SQLite database is migrated through an explicit, rehearsable CLI; web startup never performs data or schema migration.
- Existing repository changes, including concurrent EDGAR/market work, must be preserved.
- No multi-user beta is acceptable until the complete PostgreSQL Alice/Bob matrix passes.
- Frontend build/test `spawn EPERM` is a known sandbox limitation; it does not waive final verification in a normal shell.
- PostgreSQL integration tests require Docker Desktop or an explicit disposable `TEST_DATABASE_URL`; they must not be replaced by SQLite-only assertions.

## File responsibility map

- `backend/database.py`: runtime URL validation, engine/session construction, and transaction-local RLS context.
- `backend/models.py`: final PostgreSQL-compatible identity, tenancy, session, settings, and tenant domain schema.
- `backend/auth.py`: opaque session lifecycle, cookie/CSRF primitives, and authenticated user resolution.
- `backend/firebase_identity.py`: narrow Firebase Admin verification/revocation adapter.
- `backend/tenancy.py`: typed request/workspace context and authorized portfolio dependency.
- `backend/routers/auth.py`: Firebase-token exchange, session bootstrap, logout, and logout-all endpoints.
- `backend/app_settings.py`: explicitly personal or workspace-scoped setting access.
- `backend/alembic/`: schema and RLS migrations; no business runtime code.
- `backend/migrations/sqlite_to_postgres.py`: one-off legacy data importer and reconciliation report.
- `backend/tests/postgres/`: Alembic, importer, RLS, and full-stack Alice/Bob integration tests.
- `frontend/src/auth/`: Firebase browser adapter, account provider, and auth pages.
- `frontend/src/api.js`: UUID portfolio state plus workspace and CSRF headers.
- `deploy/`: disposable test PostgreSQL, Cloud Run migration/deploy, and Neon recovery operations.

---

### Task 1: PostgreSQL runtime, Alembic bootstrap, and test database

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/requirements-dev.txt`
- Modify: `backend/database.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/.gitkeep`
- Create: `deploy/docker-compose.postgres-test.yml`
- Create: `backend/tests/test_database.py`
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/postgres/conftest.py`
- Create: `backend/tests/postgres/test_smoke.py`

**Interfaces:**
- Produces `DatabaseSettings.from_env(env: Mapping[str, str]) -> DatabaseSettings`.
- Produces `build_engine(settings: DatabaseSettings) -> Engine` and the existing `engine`, `SessionLocal`, `Base`, `get_db` exports.
- Produces PostgreSQL fixtures `postgres_url`, `postgres_engine`, and `postgres_session`.

- [ ] **Step 1: Write failing database configuration tests**

```python
def test_database_settings_requires_url_in_runtime():
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        DatabaseSettings.from_env({})

def test_database_settings_accepts_neon_postgresql_url():
    settings = DatabaseSettings.from_env({
        "DATABASE_URL": "postgresql+psycopg://u:p@ep-test-pooler.eu.neon.tech/portfyl?sslmode=require"
    })
    assert settings.url.startswith("postgresql+psycopg://")
    assert settings.pool_pre_ping is True
```

- [ ] **Step 2: Run the focused tests and verify the missing interface fails**

Run: `cd backend && python -m pytest tests/test_database.py -v`

Expected: collection fails because `DatabaseSettings` does not exist.

- [ ] **Step 3: Add dependencies and the minimal database settings implementation**

Add runtime dependencies `alembic>=1.13`, `psycopg[binary]>=3.2`, and `firebase-admin>=6.5`. Add dev dependencies `pytest>=8.0`, `testcontainers[postgres]>=4.8`, and `httpx>=0.27`.

Implement this public shape in `database.py`:

```python
@dataclass(frozen=True)
class DatabaseSettings:
    url: str
    pool_pre_ping: bool = True
    pool_recycle: int = 300
    pool_size: int = 5
    max_overflow: int = 2

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "DatabaseSettings":
        url = env.get("DATABASE_URL", "").strip()
        if not url:
            raise RuntimeError("DATABASE_URL is required")
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url.removeprefix("postgres://")
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
        if not url.startswith("postgresql+psycopg://") and env.get("PORTFYL_TESTING") != "1":
            raise RuntimeError("DATABASE_URL must use PostgreSQL")
        return cls(url=url)
```

`build_engine()` omits queue-pool arguments only for test SQLite URLs; production receives the bounded pool settings.

Before `database.py` is imported, `backend/tests/conftest.py` sets
`PORTFYL_TESTING=1` and `DATABASE_URL=sqlite:///:memory:` with `setdefault`,
so existing fast unit tests remain self-contained while deployed runtime stays
fail-closed.

- [ ] **Step 4: Add Alembic and disposable PostgreSQL scaffolding**

Configure `backend/alembic/env.py` to import `Base.metadata`, read the URL through `DatabaseSettings`, enable `compare_type=True`, and wrap migrations in transactions. Configure the Compose service as PostgreSQL 16 with database/user/password `portfyl_test`, health check `pg_isready`, and host port `55441` (outside the Windows reserved range observed on the development machine).

Add `test_postgres_connection_reports_version()` in
`backend/tests/postgres/test_smoke.py`; execute `select version()` through the
`postgres_session` fixture and assert the returned string contains
`PostgreSQL`.

- [ ] **Step 5: Run unit and PostgreSQL fixture smoke tests**

Run: `cd backend && python -m pytest tests/test_database.py -v`

Run after Docker Desktop is available: `docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait && cd backend && python -m pytest tests/postgres/test_smoke.py -v`

Expected: unit tests pass and fixture connects to PostgreSQL 16.

- [ ] **Step 6: Commit Task 1**

```bash
git add backend/requirements.txt backend/requirements-dev.txt backend/database.py backend/alembic.ini backend/alembic deploy/docker-compose.postgres-test.yml backend/tests/test_database.py backend/tests/conftest.py backend/tests/postgres/conftest.py backend/tests/postgres/test_smoke.py
git commit -m "feat(db): add PostgreSQL runtime and Alembic foundation"
```

---

### Task 2: Final tenant schema and forced RLS migrations

**Files:**
- Modify: `backend/models.py`
- Modify: `backend/main.py`
- Create: `backend/alembic/versions/0001_multiuser_schema.py`
- Create: `backend/alembic/versions/0002_tenant_rls.py`
- Create: `backend/tests/postgres/test_schema.py`
- Create: `backend/tests/postgres/test_rls.py`

**Interfaces:**
- Produces models `User`, `Workspace`, `Membership`, `AuthSession`, `UserSetting`, `WorkspaceSetting`, and `DataMigrationRun`.
- Adds `workspace_id: UUID` and `public_id: UUID` to tenant/API-visible models while retaining integer `id` on domain tables.
- Produces `set_rls_context(session: Session, user_id: UUID, workspace_id: UUID | None) -> None` in `database.py`.

- [ ] **Step 1: Write failing schema tests**

```python
def test_tenant_names_are_unique_only_inside_workspace(postgres_session, alice_workspace, bob_workspace):
    postgres_session.add_all([
        Portfolio(workspace_id=alice_workspace.id, name="Main"),
        Portfolio(workspace_id=bob_workspace.id, name="Main"),
    ])
    postgres_session.commit()
    postgres_session.add(Portfolio(workspace_id=alice_workspace.id, name="Main"))
    with pytest.raises(IntegrityError):
        postgres_session.commit()

def test_domain_public_ids_are_uuid(postgres_session, alice_workspace):
    row = Portfolio(workspace_id=alice_workspace.id, name="Growth")
    postgres_session.add(row)
    postgres_session.commit()
    assert isinstance(row.public_id, UUID)
```

- [ ] **Step 2: Run schema tests and verify the new models/columns are absent**

Run: `cd backend && python -m pytest tests/postgres/test_schema.py -v`

Expected: collection or first insert fails because `Workspace`/`workspace_id` are absent.

- [ ] **Step 3: Implement the final SQLAlchemy schema**

Use SQLAlchemy `Uuid(as_uuid=True)` for UUID columns and `default=uuid.uuid4`. Identity tables use UUID primary keys. Every tenant domain table listed in the spec receives non-null `workspace_id`; every entity returned or accepted by the API receives unique indexed `public_id`. Replace global uniqueness with named composite constraints:

```python
class Portfolio(Base):
    __tablename__ = "portfolios"
    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_portfolio_workspace_name"),)
    id = Column(Integer, primary_key=True)
    public_id = Column(Uuid(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4, index=True)
    workspace_id = Column(Uuid(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
```

Use separate `UserSetting` and `WorkspaceSetting` models; remove `AppSetting`. Preserve existing business fields and explicit cascade behavior.

- [ ] **Step 4: Create the schema migration and verify upgrade/downgrade**

`0001_multiuser_schema.py` creates the complete final PostgreSQL schema from an empty database, including `pgcrypto` only if server-side UUID generation is used, named indexes/constraints, and a runtime role grant block that does not embed credentials. Its downgrade drops objects in reverse dependency order.

Run: `cd backend && alembic upgrade head && alembic downgrade base && alembic upgrade head`

Expected: all three commands succeed on the disposable PostgreSQL database.

- [ ] **Step 5: Write failing RLS tests**

```python
def test_runtime_role_cannot_read_foreign_workspace(runtime_session, alice, alice_workspace, bob_portfolio):
    set_rls_context(runtime_session, alice.id, alice_workspace.id)
    assert runtime_session.query(Portfolio).filter_by(public_id=bob_portfolio.public_id).all() == []

def test_missing_rls_context_matches_no_private_rows(runtime_session, alice_portfolio):
    assert runtime_session.query(Portfolio).all() == []
```

- [ ] **Step 6: Add RLS policies and transaction-local context**

`0002_tenant_rls.py` enables and forces RLS on every tenant table and creates policies equivalent to:

```sql
USING (workspace_id = NULLIF(current_setting('portfyl.workspace_id', true), '')::uuid)
WITH CHECK (workspace_id = NULLIF(current_setting('portfyl.workspace_id', true), '')::uuid)
```

Membership/user-setting policies compare `user_id` with `portfyl.user_id`. Preset benchmark reads additionally require `is_preset IS TRUE`; writes never use that exception. `set_rls_context()` uses parameterized `SELECT set_config(:key, :value, true)` calls.

- [ ] **Step 7: Run schema and RLS tests**

Run: `cd backend && python -m pytest tests/postgres/test_schema.py tests/postgres/test_rls.py -v`

Expected: all schema, runtime-role, missing-context, read, and write isolation cases pass.

- [ ] **Step 8: Remove imperative startup schema/data mutation**

Delete `Base.metadata.create_all()` and every `_ensure_*` / `_backfill_*` call
and helper from `main.py`. Keep preset creation and FX repair only as explicit
operator/data commands or Alembic seed data; application import/startup must
perform no `CREATE TABLE`, `ALTER TABLE`, schema backfill, or owner sentinel
backfill. Add an application-startup assertion that the `alembic_version`
value equals the code's expected head and fail with an operator-facing message
when it does not.

Run: `cd backend && python -m pytest tests/postgres/test_schema.py -v`

Expected: startup imports no longer mutate schema and the head-mismatch test
fails closed.

- [ ] **Step 9: Commit Task 2**

```bash
git add backend/models.py backend/database.py backend/main.py backend/alembic/versions backend/tests/postgres/test_schema.py backend/tests/postgres/test_rls.py
git commit -m "feat(db): add workspace schema and forced tenant RLS"
```

---

### Task 3: Rehearsable SQLite-to-PostgreSQL owner migration

**Files:**
- Create: `backend/migrations/__init__.py`
- Create: `backend/migrations/sqlite_to_postgres.py`
- Create: `backend/tests/fixtures/legacy_portfyl.sql`
- Create: `backend/tests/postgres/test_sqlite_migration.py`
- Create: `deploy/migrate-sqlite.ps1`
- Create: `docs/operations/sqlite-to-neon-migration.md`

**Interfaces:**
- Produces `MigrationOptions(source: Path, target_url: str, owner_email: str, dry_run: bool)`.
- Produces `MigrationReport(source_sha256: str, workspace_id: UUID, table_counts: dict[str, int], control_totals: dict[str, str], status: str)`.
- Produces `migrate_sqlite(options: MigrationOptions) -> MigrationReport` and CLI exit code 0 only after reconciliation passes.

- [ ] **Step 1: Create a deterministic legacy fixture and failing importer test**

The fixture contains two portfolios, transactions including nullable cash/trade fields, a watchlist/item, benchmark/component, broker rows, options, Polymarket, webhook, assistant/sync settings, note, cash rate, dividend notification, and price alert with realistic foreign keys.

```python
def test_migration_preserves_rows_and_assigns_one_workspace(legacy_db, empty_postgres_url):
    report = migrate_sqlite(MigrationOptions(legacy_db, empty_postgres_url, "owner@example.com", False))
    assert report.status == "succeeded"
    assert report.table_counts["transactions"] == 4
    with admin_session(empty_postgres_url) as db:
        assert db.query(Workspace).count() == 1
        assert {row.workspace_id for row in db.query(Transaction)} == {report.workspace_id}
```

- [ ] **Step 2: Run the importer test and verify the module is missing**

Run: `cd backend && python -m pytest tests/postgres/test_sqlite_migration.py::test_migration_preserves_rows_and_assigns_one_workspace -v`

Expected: import fails because `migrations.sqlite_to_postgres` does not exist.

- [ ] **Step 3: Implement fingerprinting, dependency-order copy, and settings classification**

Read SQLite through a separate `sqlite3` connection with `row_factory=sqlite3.Row`. Require an Alembic-head target with no tenant data. Normalize owner e-mail with `strip().casefold()`. Copy in an explicit table order and maintain dictionaries mapping legacy integer IDs to target integer IDs/public UUIDs. Classify `deepseek_api_key` and `deepseek_model` as personal; classify `sync_mode`, `sync_daily_time`, `sync_interval_hours`, and `sync_last_run` as workspace settings.

- [ ] **Step 4: Add transactionality, duplicate-run protection, and reconciliation**

Calculate SHA-256 before opening the target transaction. Reject a successful `data_migration_runs.source_fingerprint` duplicate. Compare source/target table counts, run PostgreSQL foreign-key checks through catalog-backed queries, and calculate canonical SHA-256 control totals over ordered transaction business fields. Roll back all imported business rows when any check differs.

- [ ] **Step 5: Add dry-run and owner claim tests**

```python
def test_dry_run_writes_no_rows(legacy_db, empty_postgres_url):
    report = migrate_sqlite(MigrationOptions(legacy_db, empty_postgres_url, "owner@example.com", True))
    assert report.status == "dry_run"
    assert count_rows(empty_postgres_url, "workspaces") == 0

def test_duplicate_source_is_rejected(legacy_db, empty_postgres_url):
    migrate_sqlite(MigrationOptions(legacy_db, empty_postgres_url, "owner@example.com", False))
    with pytest.raises(MigrationAlreadyApplied):
        migrate_sqlite(MigrationOptions(legacy_db, empty_postgres_url, "owner@example.com", False))
```

- [ ] **Step 6: Add PowerShell wrapper and operator runbook**

The wrapper requires `-Source`, `-TargetDatabaseUrl`, `-OwnerEmail`, and optional `-DryRun`; it invokes `python -m migrations.sqlite_to_postgres` without echoing the target URL. The runbook prescribes copying the source DB, dry run, disposable rehearsal, count/control-total review, production import, and verified Firebase owner claim.

- [ ] **Step 7: Run all migration tests**

Run: `cd backend && python -m pytest tests/postgres/test_sqlite_migration.py -v`

Expected: successful import, dry run, duplicate protection, rollback-on-mismatch, and exact owner binding tests pass.

- [ ] **Step 8: Commit Task 3**

```bash
git add backend/migrations backend/tests/fixtures/legacy_portfyl.sql backend/tests/postgres/test_sqlite_migration.py deploy/migrate-sqlite.ps1 docs/operations/sqlite-to-neon-migration.md
git commit -m "feat(migration): add reconciled SQLite owner import"
```

---

### Task 4: Firebase exchange and Portfyl-owned revocable sessions

**Files:**
- Create: `backend/firebase_identity.py`
- Replace: `backend/auth.py`
- Create: `backend/routers/auth.py`
- Modify: `backend/main.py`
- Replace: `backend/tests/test_auth.py`
- Create: `backend/tests/postgres/test_auth_sessions.py`

**Interfaces:**
- Produces `VerifiedIdentity(uid: str, email: str, email_verified: bool, display_name: str | None)`.
- Produces `FirebaseIdentityVerifier.verify_id_token(token: str) -> VerifiedIdentity` and `revoke_refresh_tokens(uid: str) -> None`.
- Produces `IssuedSession(raw_token: str, csrf_token: str, expires_at: datetime)`.
- Produces `create_session`, `resolve_session`, `revoke_session`, and `revoke_all_sessions`.
- Produces `/api/auth/session`, `/api/auth/me`, `/api/auth/logout`, and `/api/auth/logout-all`.

- [ ] **Step 1: Write failing opaque-session tests**

```python
def test_create_session_stores_only_hash(postgres_session, alice):
    issued = create_session(postgres_session, alice.id, user_agent="pytest")
    row = postgres_session.query(AuthSession).one()
    assert issued.raw_token not in row.token_digest
    assert row.token_digest == hashlib.sha256(issued.raw_token.encode()).hexdigest()

def test_revoked_session_cannot_resolve(postgres_session, alice):
    issued = create_session(postgres_session, alice.id)
    revoke_session(postgres_session, issued.raw_token)
    assert resolve_session(postgres_session, issued.raw_token) is None
```

- [ ] **Step 2: Run focused tests and verify old signed-cookie behavior fails the contract**

Run: `cd backend && python -m pytest tests/postgres/test_auth_sessions.py -v`

Expected: imports fail because database-backed session functions do not exist.

- [ ] **Step 3: Implement Firebase adapter and session primitives**

Use `firebase_admin.auth.verify_id_token(token, check_revoked=True)` and map only `uid`, normalized `email`, `email_verified`, and `name`. Generate 32 random bytes for session and CSRF tokens with `secrets.token_urlsafe(32)`, store SHA-256 hex digests, and compare digests with `hmac.compare_digest`. Set cookie name `__Host-portfyl_session` in HTTPS environments and `portfyl_session` in explicit local test mode.

- [ ] **Step 4: Write failing endpoint tests for verified/unverified/legacy identities**

```python
def test_verified_identity_creates_user_workspace_membership_and_session(client, verified_token):
    response = client.post("/api/auth/session", json={"id_token": verified_token})
    assert response.status_code == 201
    assert response.json()["user"]["email"] == "alice@example.com"
    assert len(response.json()["workspaces"]) == 1
    assert "portfyl_session" in response.headers["set-cookie"]

def test_unverified_identity_is_rejected(client, unverified_token):
    response = client.post("/api/auth/session", json={"id_token": unverified_token})
    assert response.status_code == 403
    assert response.json()["code"] == "email_verification_required"
```

- [ ] **Step 5: Implement auth router and remove shared-password routes**

Provision a new user/workspace/membership atomically. Claim a pending migrated user only when normalized verified e-mail matches. Return user/workspace public UUIDs and CSRF token. Logout endpoints revoke Portfyl rows; logout-all also invokes Firebase revocation. Remove `DEFAULT_OWNER_ID`, `APP_PASSWORD`, HMAC cookie issuance, server-rendered password page, and `/api/auth/login` from `main.py`.

- [ ] **Step 6: Add CSRF and logout-all tests**

Assert missing/wrong CSRF returns `403 csrf_failed`, current logout revokes one session, logout-all revokes every database session and calls the narrow Firebase adapter once with the user's UID.

- [ ] **Step 7: Run auth suites**

Run: `cd backend && python -m pytest tests/test_auth.py tests/postgres/test_auth_sessions.py -v`

Expected: every identity, cookie, expiry, CSRF, owner-claim, logout, and logout-all case passes.

- [ ] **Step 8: Commit Task 4**

```bash
git add backend/firebase_identity.py backend/auth.py backend/routers/auth.py backend/main.py backend/tests/test_auth.py backend/tests/postgres/test_auth_sessions.py
git commit -m "feat(auth): add Firebase exchange and revocable sessions"
```

---

### Task 5: Trusted request context and workspace-scoped portfolios

**Files:**
- Create: `backend/tenancy.py`
- Modify: `backend/routers/portfolios.py`
- Modify: `backend/main.py`
- Create: `backend/tests/postgres/test_portfolio_tenancy.py`
- Modify: `backend/tests/conftest.py`

**Interfaces:**
- Produces `RequestContext(user: User, workspace: Workspace, membership: Membership, session: AuthSession)`.
- Produces `get_request_context(request, db, x_workspace_id) -> RequestContext`.
- Produces `require_csrf(request, context) -> RequestContext`.
- Produces `require_portfolio(portfolio_id: UUID | None, context, db) -> Portfolio`.

- [ ] **Step 1: Write failing Alice/Bob portfolio tests through FastAPI**

```python
def test_alice_lists_only_alice_portfolios(alice_client, alice_portfolio, bob_portfolio):
    response = alice_client.get("/api/portfolios")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [str(alice_portfolio.public_id)]

@pytest.mark.parametrize("method", ["patch", "delete"])
def test_alice_cannot_mutate_bob_portfolio(alice_client, bob_portfolio, method):
    response = getattr(alice_client, method)(f"/api/portfolios/{bob_portfolio.public_id}", json={"name": "stolen"})
    assert response.status_code == 404
```

- [ ] **Step 2: Run the focused tests and confirm global list/update behavior fails**

Run: `cd backend && python -m pytest tests/postgres/test_portfolio_tenancy.py -v`

Expected: Alice sees or can address Bob's current integer/global resources.

- [ ] **Step 3: Implement typed request context and RLS setup order**

Resolve the session digest without tenant context, set `portfyl.user_id`, load the user/memberships, validate `X-Workspace-ID`, set `portfyl.workspace_id`, and return `RequestContext`. Reuse FastAPI dependency caching so routes and CSRF checks share one SQLAlchemy session/transaction.

- [ ] **Step 4: Scope portfolio CRUD, counts, overview, and default selection**

Every portfolio query includes `Portfolio.workspace_id == context.workspace.id`. `_counts_by_portfolio()` receives `workspace_id`. Delete counts only the current workspace and selects a replacement default only there. Serialize `public_id` as `id`; accept UUID route/query values and return foreign/nonexistent resources as identical 404 responses.

- [ ] **Step 5: Replace global login middleware with dependency-aware API handling**

Mount the auth router without session dependency. Protected `/api` routers use `get_request_context` or dependencies built on it. API failures remain JSON 401/403/404. SPA auth pages are frontend routes rather than server-rendered forms.

- [ ] **Step 6: Run portfolio tenancy and existing portfolio tests**

Run: `cd backend && python -m pytest tests/postgres/test_portfolio_tenancy.py tests/test_portfolio.py -v`

Expected: Alice/Bob cases pass and existing calculations remain green after fixture adaptation.

- [ ] **Step 7: Commit Task 5**

```bash
git add backend/tenancy.py backend/routers/portfolios.py backend/main.py backend/tests/conftest.py backend/tests/postgres/test_portfolio_tenancy.py backend/tests/test_portfolio.py
git commit -m "feat(tenancy): add trusted workspace context and scoped portfolios"
```

---

### Task 6: Portfolio-child UUIDs and tenant-aware core financial routes

**Files:**
- Modify: `backend/schemas.py`
- Modify: `backend/routers/portfolio.py`
- Modify: `backend/routers/analytics.py`
- Modify: `backend/routers/benchmarks.py`
- Modify: `backend/routers/cash.py`
- Modify: `backend/routers/notes.py`
- Modify: `backend/cache.py`
- Modify: `backend/tests/test_portfolio.py`
- Modify: `backend/tests/test_analytics.py`
- Modify: `backend/tests/test_cash_api.py`
- Create: `backend/tests/postgres/test_financial_route_tenancy.py`

**Interfaces:**
- `require_portfolio` now returns an authorized `Portfolio`; call sites use `portfolio.id` internally and `portfolio.public_id` externally.
- Transaction, benchmark, benchmark component, cash rate, and trade-note serializers expose public UUIDs.
- Tenant-dependent cache keys begin with `(workspace_id, resource_public_id, ...)`.

- [ ] **Step 1: Write failing cross-tenant child tests**

Cover transaction read/update/delete, note read/update/delete, custom benchmark selection/update/delete, cash mutation, analytics benchmark selection, and cross-portfolio overview. Each known Bob UUID must produce 404 through Alice's client.

```python
def test_foreign_transaction_uuid_is_not_addressable(alice_client, alice_portfolio, bob_transaction):
    response = alice_client.delete(
        f"/api/portfolio/transactions/{bob_transaction.public_id}",
        params={"portfolio_id": str(alice_portfolio.public_id)},
    )
    assert response.status_code == 404
```

- [ ] **Step 2: Run the new route matrix and observe integer/unscoped failures**

Run: `cd backend && python -m pytest tests/postgres/test_financial_route_tenancy.py -v`

Expected: failures identify routes still accepting integers or omitting workspace predicates.

- [ ] **Step 3: Convert serializers and path/query parameters to public UUIDs**

Use UUID-typed FastAPI parameters. Resolve each child with both `workspace_id` and authorized internal parent ID. Return public UUIDs for `id`, `transaction_id`, `benchmark_id`, and related API references. Keep internal integer IDs only inside service calculations.

- [ ] **Step 4: Add workspace predicates and tenant cache keys**

Every direct query adds `workspace_id` or traverses a parent already loaded with `(workspace_id, public_id)`. Update portfolio, analytics, cash, notes, and benchmark caches so Alice and Bob cannot share cached holdings, allocations, summaries, or notes for equal legacy integer IDs.

- [ ] **Step 5: Run focused and regression suites**

Run: `cd backend && python -m pytest tests/postgres/test_financial_route_tenancy.py tests/test_portfolio.py tests/test_analytics.py tests/test_cash_api.py -v`

Expected: tenant matrix and calculation regressions pass.

- [ ] **Step 6: Commit Task 6**

```bash
git add backend/schemas.py backend/routers/portfolio.py backend/routers/analytics.py backend/routers/benchmarks.py backend/routers/cash.py backend/routers/notes.py backend/cache.py backend/tests/test_portfolio.py backend/tests/test_analytics.py backend/tests/test_cash_api.py backend/tests/postgres/test_financial_route_tenancy.py
git commit -m "feat(api): scope financial routes and expose UUID resources"
```

---

### Task 7: Watchlists, personal/workspace settings, and alerts isolation

**Files:**
- Replace: `backend/app_settings.py`
- Modify: `backend/routers/watchlists.py`
- Modify: `backend/routers/settings.py`
- Modify: `backend/routers/assistant.py`
- Modify: `backend/routers/alerts.py`
- Modify: `backend/jobs.py`
- Replace: `backend/tests/test_app_settings.py`
- Modify: `backend/tests/test_settings.py`
- Modify: `backend/tests/test_alerts.py`
- Create: `backend/tests/postgres/test_watchlist_settings_alert_tenancy.py`

**Interfaces:**
- Produces `get_user_setting(db, user_id, key)` / `set_user_setting(...)`.
- Produces `get_workspace_setting(db, workspace_id, key)` / `set_workspace_setting(...)`.
- Watchlist, item, and alert endpoints accept/return UUIDs and require `RequestContext`.
- `run_check(db, workspace_id: UUID, portfolio_id: int | None)` never performs a global customer scan without an explicit workspace iteration owned by the job caller.

- [ ] **Step 1: Write failing scoped-setting tests**

```python
def test_same_setting_key_has_independent_user_values(postgres_session, alice, bob):
    set_user_setting(postgres_session, alice.id, "deepseek_model", "a")
    set_user_setting(postgres_session, bob.id, "deepseek_model", "b")
    assert get_user_setting(postgres_session, alice.id, "deepseek_model") == "a"
    assert get_user_setting(postgres_session, bob.id, "deepseek_model") == "b"

def test_same_sync_key_has_independent_workspace_values(postgres_session, alice_workspace, bob_workspace):
    set_workspace_setting(postgres_session, alice_workspace.id, "sync_mode", "daily")
    set_workspace_setting(postgres_session, bob_workspace.id, "sync_mode", "weekly")
    assert get_workspace_setting(postgres_session, alice_workspace.id, "sync_mode") == "daily"
```

- [ ] **Step 2: Write the Alice/Bob watchlist and alert route matrix**

For list/read/create/update/delete/item operations and alert list/create/update/delete/check, assert tenant-only lists, foreign 404s, cross-tenant duplicate-name success, same-tenant duplicate-name 409, and random UUID indistinguishability.

- [ ] **Step 3: Run focused tests and confirm global key/list lookups fail**

Run: `cd backend && python -m pytest tests/test_app_settings.py tests/postgres/test_watchlist_settings_alert_tenancy.py -v`

Expected: old key-only settings and global watchlist list fail assertions.

- [ ] **Step 4: Implement explicit setting scopes**

Remove generic `get_setting`/`set_setting`. Assistant API key/model callers use user settings; sync schedule/last-run callers use workspace settings. Every call supplies the owner UUID directly. Preserve caller-owned transaction boundaries.

- [ ] **Step 5: Scope watchlist and alert operations and jobs**

Resolve list/item/alert UUIDs with `workspace_id`. Stamp all created parent/child rows with the current workspace. Make alert execution require a workspace and ensure notification dedup queries carry it. Jobs enumerate workspaces explicitly before invoking tenant work and reset RLS context for each transaction.

- [ ] **Step 6: Run settings, alerts, jobs, and route tests**

Run: `cd backend && python -m pytest tests/test_app_settings.py tests/test_settings.py tests/test_alerts.py tests/test_jobs.py tests/postgres/test_watchlist_settings_alert_tenancy.py -v`

Expected: all personal/shared settings, alert behavior, and Alice/Bob cases pass.

- [ ] **Step 7: Commit Task 7**

```bash
git add backend/app_settings.py backend/routers/watchlists.py backend/routers/settings.py backend/routers/assistant.py backend/routers/alerts.py backend/jobs.py backend/tests/test_app_settings.py backend/tests/test_settings.py backend/tests/test_alerts.py backend/tests/test_jobs.py backend/tests/postgres/test_watchlist_settings_alert_tenancy.py
git commit -m "feat(tenancy): isolate watchlists settings alerts and jobs"
```

---

### Task 8: Broker, options, Polymarket, Discord, and remaining query audit

**Files:**
- Modify: `backend/routers/broker.py`
- Modify: `backend/routers/ibkr.py`
- Modify: `backend/routers/options.py`
- Modify: `backend/routers/polymarket.py`
- Modify: `backend/routers/discord.py`
- Modify: `backend/tests/test_broker.py`
- Modify: `backend/tests/test_t212_import.py`
- Modify: `backend/tests/test_discord.py`
- Create: `backend/tests/postgres/test_integration_tenancy.py`

**Interfaces:**
- All broker/position/webhook operations consume authorized `Portfolio` and stamp/query `workspace_id`.
- Options endpoints accept the portfolio public UUID through `require_portfolio`, not unchecked integer query parameters.
- Background notification and import helpers accept `workspace_id` plus internal portfolio ID.

- [ ] **Step 1: Write failing broker/integration isolation tests**

Create equal broker types and equal internal IDs across Alice/Bob fixtures. Assert Alice cannot read status, sync, disconnect, import into, enumerate options/Polymarket positions, read balances, or send through Bob's webhook using Bob public UUIDs.

```python
def test_sync_cannot_target_foreign_portfolio(alice_client, bob_portfolio):
    response = alice_client.post(
        "/api/broker/sync",
        params={"portfolio_id": str(bob_portfolio.public_id)},
    )
    assert response.status_code == 404
```

- [ ] **Step 2: Run integration tests and inventory every remaining direct model query**

Run: `cd backend && python -m pytest tests/postgres/test_integration_tenancy.py -v`

Run audit: `rg -n "db\.query|select\(" backend/routers backend/jobs.py backend/app_settings.py`

Expected: tests fail on remaining unchecked IDs; every audit hit is classified as tenant-filtered, authorized-parent-filtered, or public market/system data.

- [ ] **Step 3: Add workspace identity to all integrations and imports**

Remove `get_current_user` sentinel dependencies. Resolve portfolio public UUID once, then use its internal ID plus workspace ID. Stamp imported transactions, broker connections/balances, options, Polymarket positions, webhooks, and dedup rows with the current workspace. Ensure replacement imports delete only rows matching both workspace and portfolio.

- [ ] **Step 4: Convert remaining exposed IDs to UUIDs**

Options trades, Polymarket positions, broker-visible connection references, webhook records, and related responses serialize `public_id`. Route parameters use UUID and include workspace predicates.

- [ ] **Step 5: Run integration and existing broker suites**

Run: `cd backend && python -m pytest tests/postgres/test_integration_tenancy.py tests/test_broker.py tests/test_t212_import.py tests/test_discord.py -v`

Expected: cross-tenant integration cases and existing broker behavior pass.

- [ ] **Step 6: Commit Task 8**

```bash
git add backend/routers/broker.py backend/routers/ibkr.py backend/routers/options.py backend/routers/polymarket.py backend/routers/discord.py backend/tests/test_broker.py backend/tests/test_t212_import.py backend/tests/test_discord.py backend/tests/postgres/test_integration_tenancy.py
git commit -m "feat(tenancy): scope integrations imports and remaining resources"
```

---

### Task 9: Complete PostgreSQL Alice/Bob and RLS go/no-go matrix

**Files:**
- Create: `backend/tests/postgres/test_alice_bob_matrix.py`
- Create: `backend/tests/postgres/test_runtime_role.py`
- Create: `backend/tests/postgres/matrix_cases.py`
- Modify: `backend/tests/postgres/conftest.py`
- Create: `docs/security/tenant-isolation-matrix.md`

**Interfaces:**
- Produces reusable literal matrix cases `(resource, list_url, foreign_url, create_payload, update_payload)`.
- Produces one command that returns success only when app-layer and raw runtime-role isolation both pass.

- [ ] **Step 1: Encode the complete route matrix as literal cases**

Include portfolios, transactions, notes, benchmarks, cash rates, watchlists/items, user/workspace settings, alerts, broker connections/balances, options, Polymarket, Discord, imports, and workspace-dependent jobs. For each supported operation encode expected Alice-own status and Bob-foreign status; foreign reads/updates/deletes are always 404.

- [ ] **Step 2: Write raw SQL mutation/read RLS tests**

```python
def test_alice_runtime_role_cannot_update_bob(runtime_session, alice_context, bob_portfolio):
    set_rls_context(runtime_session, alice_context.user_id, alice_context.workspace_id)
    changed = runtime_session.execute(
        update(Portfolio).where(Portfolio.public_id == bob_portfolio.public_id).values(name="stolen")
    ).rowcount
    assert changed == 0

def test_forged_workspace_context_is_still_blocked_by_membership_endpoint(alice_client, bob_workspace):
    response = alice_client.get("/api/portfolios", headers={"X-Workspace-ID": str(bob_workspace.public_id)})
    assert response.status_code == 404
```

- [ ] **Step 3: Run the full matrix and fix only uncovered tenant gaps through failing cases**

Run: `cd backend && python -m pytest tests/postgres/test_alice_bob_matrix.py tests/postgres/test_runtime_role.py -v`

Expected: all list/read/create/update/delete/enumeration and raw SQL cases pass; no case is skipped.

- [ ] **Step 4: Run the entire backend suite**

Run: `cd backend && python -m pytest tests/ -v`

Expected: all existing unit tests and new PostgreSQL suites pass. Existing deprecation warnings may remain, but no tenant/auth/database warning or error is accepted.

- [ ] **Step 5: Record the executable security matrix**

Document each resource/operation, application test name, RLS test name, and expected 401/403/404/409 behavior. State that the PostgreSQL command above is the beta go/no-go gate.

- [ ] **Step 6: Commit Task 9**

```bash
git add backend/tests/postgres/test_alice_bob_matrix.py backend/tests/postgres/test_runtime_role.py backend/tests/postgres/matrix_cases.py backend/tests/postgres/conftest.py docs/security/tenant-isolation-matrix.md
git commit -m "test(security): prove complete Alice Bob tenant isolation"
```

---

### Task 10: React registration, session, account, workspace, and UUID state

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/src/auth/firebase.js`
- Create: `frontend/src/auth/AuthProvider.jsx`
- Create: `frontend/src/auth/AuthProvider.test.jsx`
- Create: `frontend/src/pages/Login.jsx`
- Create: `frontend/src/pages/Register.jsx`
- Create: `frontend/src/pages/VerifyEmail.jsx`
- Create: `frontend/src/pages/ForgotPassword.jsx`
- Create: `frontend/src/pages/AuthPages.test.jsx`
- Create: `frontend/src/components/AccountMenu.jsx`
- Modify: `frontend/src/api.js`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/Sidebar.jsx`
- Create: `frontend/src/api.auth.test.js`

**Interfaces:**
- Produces `AuthProvider` and `useAuth()` with `{user, workspaces, currentWorkspace, csrfToken, ready, loginWithIdToken, logout, logoutAll, selectWorkspace}`.
- Produces `configureRequestContext({workspaceId, csrfToken})` in `api.js`.
- Portfolio IDs remain strings end-to-end.

- [x] **Step 1: Write failing Axios context tests**

```javascript
it("keeps UUID portfolio IDs and attaches workspace plus CSRF headers", async () => {
  setActivePortfolioId("11111111-1111-4111-8111-111111111111");
  configureRequestContext({
    workspaceId: "22222222-2222-4222-8222-222222222222",
    csrfToken: "csrf-token",
  });
  const config = await applyRequestInterceptors({ method: "post", url: "/alerts", params: {} });
  expect(config.params.portfolio_id).toBe("11111111-1111-4111-8111-111111111111");
  expect(config.headers["X-Workspace-ID"]).toBe("22222222-2222-4222-8222-222222222222");
  expect(config.headers["X-CSRF-Token"]).toBe("csrf-token");
});
```

- [x] **Step 2: Run focused frontend tests and verify numeric coercion fails**

Run in a normal shell: `cd frontend && npm test -- src/api.auth.test.js`

Expected: UUID becomes `NaN` or the new request context function is absent.

- [x] **Step 3: Add Firebase JS SDK and browser adapter**

Add the current Firebase JS package. Initialize from `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, and `VITE_FIREBASE_APP_ID`. Set browser persistence to `inMemoryPersistence`. Export wrappers for e-mail/password signup, login, verification mail, reset mail, ID token retrieval, and client sign-out.

- [x] **Step 4: Implement account provider and API exchange**

On mount call `/api/auth/me`. On verified Firebase login POST the ID token to `/api/auth/session`, then sign out the Firebase browser client and retain only backend user/workspace/CSRF state. Configure Axios headers, clear React Query on identity/workspace changes, and expose logout/logout-all.

- [x] **Step 5: Write and implement auth page behavior tests**

Test registration sends verification and navigates to `/verify-email`; unverified login shows verification instructions; verified login exchanges token and navigates to `/`; forgot-password always shows a neutral success message; 401 navigates to `/login` only outside public auth routes.

- [x] **Step 6: Remove numeric portfolio assumptions**

In `App.jsx`, `api.js`, analytics benchmark state, and resource route helpers, preserve UUID strings. `sb_portfolio_id` remains the backwards-compatible localStorage key but its value is now a UUID. Clear stale numeric values when no matching server portfolio exists.

- [x] **Step 7: Add account menu and protected route composition**

Mount public auth routes outside protected providers. Mount the existing application only when `AuthProvider.ready` has an authenticated user/workspace. Add current e-mail plus logout/logout-all to `AccountMenu`; do not add billing, plan, onboarding, OAuth, or MFA UI.

- [x] **Step 8: Run frontend test and build verification**

Run in a normal shell: `cd frontend && npm test`

Run in a normal shell: `cd frontend && npm run build`

Expected: all Vitest tests pass and Vite produces `frontend/dist`. In this sandbox, record `spawn EPERM` and rerun both commands outside the sandbox before completion.

- [x] **Step 9: Commit Task 10**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/auth frontend/src/pages/Login.jsx frontend/src/pages/Register.jsx frontend/src/pages/VerifyEmail.jsx frontend/src/pages/ForgotPassword.jsx frontend/src/pages/AuthPages.test.jsx frontend/src/components/AccountMenu.jsx frontend/src/api.js frontend/src/App.jsx frontend/src/components/Sidebar.jsx frontend/src/api.auth.test.js
git commit -m "feat(frontend): add accounts sessions workspaces and UUID state"
```

---

### Task 11: Cloud Run multi-instance deploy, Neon restore drill, and documentation

**Files:**
- Modify: `Dockerfile`
- Modify: `deploy/cloudrun.md`
- Create: `deploy/run-migrations.ps1`
- Create: `deploy/validate-restore.py`
- Create: `docs/operations/neon-backup-restore.md`
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md`
- Create: `backend/tests/test_restore_validation.py`

**Interfaces:**
- `deploy/validate-restore.py --database-url-env RESTORE_DATABASE_URL --expected-alembic-head 0002_tenant_rls --control-file <json>` exits nonzero on revision/count/control-total mismatch and never prints credentials.
- `deploy/run-migrations.ps1` creates/executes a Cloud Run Job using the same image and `alembic upgrade head` before service deployment.

- [ ] **Step 1: Write failing restore validator tests**

```python
def test_restore_validator_rejects_wrong_alembic_revision(fake_database, control_file):
    result = validate_restore(fake_database, control_file, expected_head="0002_tenant_rls")
    assert result.ok is False
    assert result.errors == ["alembic revision mismatch: expected 0002_tenant_rls, got 0001_multiuser_schema"]

def test_restore_validator_never_includes_database_url(monkeypatch, capsys):
    monkeypatch.setenv("RESTORE_DATABASE_URL", "postgresql://secret@example/db")
    main(["--database-url-env", "RESTORE_DATABASE_URL", "--control-file", "missing.json"])
    assert "secret@example" not in capsys.readouterr().out
```

- [ ] **Step 2: Run focused validator tests and verify the script is absent**

Run: `cd backend && python -m pytest tests/test_restore_validation.py -v`

Expected: import fails because `deploy.validate_restore` does not exist.

- [ ] **Step 3: Implement migration job and restore validator**

The PowerShell script requires project, region, image, service account, and secret-backed `DATABASE_URL`; it deploys/executes a uniquely named Cloud Run Job whose command is `alembic -c backend/alembic.ini upgrade head`, waits for success, and exits before service deployment on failure. The validator checks Alembic head, required RLS flags/policies, table counts, and transaction control totals using read-only SQL.

- [ ] **Step 4: Update Cloud Run for Neon and multiple instances**

Remove `DATABASE_PATH`, the GCS volume/mount, and every statement that `--max-instances=1` is load-bearing. Document request-based billing, `--min-instances=0`, initial `--max-instances=5`, Neon pooled runtime URL, separate owner migration URL where needed, runtime non-owner role, Firebase ADC/project configuration, and migration-job-before-traffic order.

- [ ] **Step 5: Write the Neon PITR restore drill**

Document these exact operator stages: record project retention shown in Neon Console; choose a timestamp before the incident; create a new recovery branch at that timestamp; obtain a read-only connection string for the branch; run `validate-restore.py`; compare Alembic/RLS/count/control report; run a smoke test against the recovery branch; switch `DATABASE_URL` only after approval; retain the old branch until post-restore verification; record timestamp, branch ID, validator output hash, operator, and result. The procedure never restores over production in place.

- [ ] **Step 6: Update repository guidance and master-plan stack wording**

Update `CLAUDE.md` to describe Neon PostgreSQL, Alembic, Firebase identity, workspace scoping, UUID API IDs, migration commands, and both test suites. Replace remaining Cloud SQL wording in the master plan with Neon and state that PostgreSQL removes the SQLite single-instance constraint. Preserve out-of-scope workstream language.

- [ ] **Step 7: Run documentation-adjacent and full verification**

Run: `cd backend && python -m pytest tests/test_restore_validation.py tests/ -v`

Run with Docker/Neon test target: `cd backend && python -m pytest tests/postgres/ -v`

Run outside sandbox: `cd frontend && npm test && npm run build`

Run: `git diff --check`

Expected: all backend/PostgreSQL/frontend checks pass and diff check reports no whitespace errors.

- [ ] **Step 8: Perform the production-like recovery branch drill**

Using access to the actual Neon project, create a non-production recovery branch, run the validator and application smoke suite, and record the result in `docs/operations/neon-backup-restore.md`. Do not change production traffic during this proof drill.

- [ ] **Step 9: Commit Task 11**

```bash
git add Dockerfile deploy/cloudrun.md deploy/run-migrations.ps1 deploy/validate-restore.py docs/operations/neon-backup-restore.md CLAUDE.md docs/superpowers/plans/2026-09-01-portfyl-saas-monetization.md backend/tests/test_restore_validation.py
git commit -m "docs(deploy): add Neon migrations restore drill and multi-instance Cloud Run"
```

---

## Final verification gate

- [ ] `alembic downgrade base && alembic upgrade head` passes on disposable PostgreSQL.
- [ ] SQLite rehearsal imports the full fixture and a copy of the owner's real database with matching reconciliation report.
- [ ] Complete backend unit suite passes.
- [ ] Complete PostgreSQL Alice/Bob and raw RLS matrix passes with no skips.
- [ ] Frontend Vitest suite and Vite production build pass outside the restricted sandbox.
- [ ] Runtime Neon URL uses a non-owner role without `BYPASSRLS`.
- [ ] Cloud Run migration job succeeds before a multi-instance service deployment.
- [ ] Production-like Neon recovery branch validates successfully and the drill record is complete.
- [ ] `CLAUDE.md`, master plan, migration runbook, isolation matrix, and restore runbook match the implemented commands and schema.
