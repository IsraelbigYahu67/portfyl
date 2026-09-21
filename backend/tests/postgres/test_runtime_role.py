"""Task 9: the raw-SQL half of the go/no-go gate.

`test_alice_bob_matrix.py` proves the *application* refuses to serve another
tenant's rows. This file drops below it and proves the database would refuse
too: every statement here runs as the real `portfyl_runtime` role -- the same
NOBYPASSRLS, non-owner role production connects with -- and bypasses the
routers entirely, so a missing `WHERE workspace_id = ...` in some future
handler still cannot leak or corrupt another tenant's data.

Why both halves are required, and why neither is redundant:

* Application predicates alone would fall to one forgotten filter.
* RLS alone would fall to any code path that legitimately sets the context to
  a workspace the caller is not a member of -- which is precisely the last
  test in this file: the database happily serves Bob's rows to a session whose
  `portfyl.workspace_id` is Bob's, so the *membership* check in
  `tenancy.get_request_context` is the thing that must never let a non-member
  get there.

Fixture-ordering note (same reason as tests/postgres/test_job_workspace_isolation.py):
`matrix_tenants` MUST be listed before `runtime_session` in every signature.
pytest tears fixtures down in reverse setup order, so seeding first means its
cleanup DELETE runs only after `runtime_session`'s transaction has already
been rolled back and its row locks released.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import Session

from database import set_rls_context
from models import Portfolio, Transaction, Watchlist
from tests.postgres.conftest import MatrixTenants, TenantContext


# Tenant tables the matrix fixture seeds for BOTH tenants, keyed by the column
# that carries the tenant. Parametrizing over them means a new table added to
# the schema without a policy shows up here as a failing case, not a gap.
WORKSPACE_SCOPED_TABLES: tuple[str, ...] = (
    "portfolios",
    "transactions",
    "watchlists",
    "watchlist_items",
    "benchmarks",
    "broker_connections",
    "broker_balances",
    "broker_positions",
    "broker_sync_runs",
    "broker_sync_events",
    "options_trades",
    "polymarket_positions",
    "discord_webhooks",
    "trade_notes",
    "cash_interest_rates",
    "price_alerts",
    "workspace_settings",
    "usage_counters",
    "usage_reservations",
    "notification_outbox",
)


# ---------------------------------------------------------------------------
# Thin aliases so the tests below read the way the plan specifies them.
# ---------------------------------------------------------------------------


@pytest.fixture
def alice_client(matrix_client: TestClient) -> TestClient:
    return matrix_client


@pytest.fixture
def bob_portfolio(matrix_bob_portfolio: SimpleNamespace) -> SimpleNamespace:
    return matrix_bob_portfolio


@pytest.fixture
def bob_workspace(matrix_bob_workspace: SimpleNamespace) -> SimpleNamespace:
    return matrix_bob_workspace


def _as_alice(session: Session, context: TenantContext) -> None:
    set_rls_context(session, context.user_id, context.workspace_id)


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def test_missing_rls_context_sees_no_tenant_rows(
    matrix_tenants: MatrixTenants, runtime_session: Session,
):
    """Fail closed: an un-contextualized runtime session is not "everything",
    it is "nothing"."""
    assert runtime_session.scalars(select(Portfolio)).all() == []
    assert runtime_session.scalars(select(Transaction)).all() == []
    assert runtime_session.scalars(select(Watchlist)).all() == []


@pytest.mark.parametrize("table", WORKSPACE_SCOPED_TABLES)
def test_alice_runtime_role_reads_only_her_own_workspace_rows(
    table: str,
    matrix_tenants: MatrixTenants,
    runtime_session: Session,
):
    _as_alice(runtime_session, matrix_tenants.alice)

    own = runtime_session.execute(
        text(f"SELECT count(*) FROM {table} WHERE workspace_id = :workspace"),
        {"workspace": matrix_tenants.alice.workspace_id},
    ).scalar_one()
    foreign = runtime_session.execute(
        text(f"SELECT count(*) FROM {table} WHERE workspace_id = :workspace"),
        {"workspace": matrix_tenants.bob.workspace_id},
    ).scalar_one()
    unfiltered = runtime_session.execute(
        text(f"SELECT count(*) FROM {table}")
    ).scalar_one()

    assert own >= 1, f"{table}: Alice must still see her own rows"
    assert foreign == 0, f"{table}: Bob's rows are visible to Alice"
    # Nothing beyond Alice's own rows is reachable at all -- including rows
    # this fixture never created. (`benchmarks` also serves shared presets,
    # which carry no workspace, so it is excluded from the strict equality.)
    if table != "benchmarks":
        assert unfiltered == own, f"{table}: unfiltered read returned foreign rows"


def test_personal_settings_are_scoped_to_the_user_not_the_workspace(
    matrix_tenants: MatrixTenants, runtime_session: Session,
):
    _as_alice(runtime_session, matrix_tenants.alice)

    own = runtime_session.execute(
        text("SELECT count(*) FROM user_settings WHERE user_id = :user"),
        {"user": matrix_tenants.alice.user_id},
    ).scalar_one()
    foreign = runtime_session.execute(
        text("SELECT count(*) FROM user_settings WHERE user_id = :user"),
        {"user": matrix_tenants.bob.user_id},
    ).scalar_one()

    assert own == 2       # deepseek_api_key + deepseek_model
    assert foreign == 0


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def test_alice_runtime_role_cannot_update_bob(
    matrix_tenants: MatrixTenants,
    runtime_session: Session,
    bob_portfolio: SimpleNamespace,
):
    _as_alice(runtime_session, matrix_tenants.alice)

    changed = runtime_session.execute(
        update(Portfolio)
        .where(Portfolio.public_id == bob_portfolio.public_id)
        .values(name="stolen")
    ).rowcount

    assert changed == 0


def test_alice_runtime_role_cannot_delete_bob(
    matrix_tenants: MatrixTenants,
    runtime_session: Session,
    bob_portfolio: SimpleNamespace,
):
    _as_alice(runtime_session, matrix_tenants.alice)

    removed = runtime_session.execute(
        delete(Portfolio).where(Portfolio.public_id == bob_portfolio.public_id)
    ).rowcount

    assert removed == 0


def test_alice_runtime_role_can_still_update_her_own_rows(
    matrix_tenants: MatrixTenants, runtime_session: Session,
):
    """The policy must be a tenant filter, not a blanket denial -- otherwise
    the isolation tests above would pass on a database that simply refuses
    every write."""
    _as_alice(runtime_session, matrix_tenants.alice)

    changed = runtime_session.execute(
        update(Portfolio)
        .where(Portfolio.public_id == matrix_tenants.alice.portfolio_public_id)
        .values(name="renamed by its owner")
    ).rowcount

    assert changed == 1


def test_alice_runtime_role_cannot_insert_into_bobs_workspace(
    matrix_tenants: MatrixTenants, runtime_session: Session,
):
    _as_alice(runtime_session, matrix_tenants.alice)
    runtime_session.add(
        Portfolio(workspace_id=matrix_tenants.bob.workspace_id, name="Planted")
    )

    with pytest.raises(DBAPIError, match="row-level security"):
        runtime_session.flush()


def test_alice_runtime_role_cannot_reparent_her_row_into_bobs_workspace(
    matrix_tenants: MatrixTenants, runtime_session: Session,
):
    """The WITH CHECK half of the policy: moving a row you legitimately own
    into someone else's tenant is a write into their workspace."""
    _as_alice(runtime_session, matrix_tenants.alice)

    with pytest.raises(DBAPIError, match="row-level security"):
        runtime_session.execute(
            text(
                "UPDATE portfolios SET workspace_id = :bob WHERE public_id = :alice"
            ),
            {
                "bob": matrix_tenants.bob.workspace_id,
                "alice": matrix_tenants.alice.portfolio_public_id,
            },
        )


def test_alice_runtime_role_cannot_plant_a_child_under_bobs_parent(
    matrix_tenants: MatrixTenants, runtime_session: Session,
    bob_portfolio: SimpleNamespace,
):
    """A child stamped with Alice's workspace but pointing at Bob's portfolio
    must fail the foreign key -- the composite (workspace_id, portfolio_id)
    reference is what stops a row from straddling two tenants."""
    _as_alice(runtime_session, matrix_tenants.alice)
    runtime_session.add(
        Transaction(
            workspace_id=matrix_tenants.alice.workspace_id,
            portfolio_id=bob_portfolio.id,
            ticker="CROSS", type="buy", shares=1, price=1, date=date(2026, 9, 3),
        )
    )

    with pytest.raises(DBAPIError):
        runtime_session.flush()


# ---------------------------------------------------------------------------
# The role itself
# ---------------------------------------------------------------------------


def test_runtime_role_is_not_superuser_and_has_no_rls_bypass(postgres_session: Session):
    """The `postgres_engine` fixture deliberately grants
    `BYPASSRLS CREATEDB CREATEROLE` to `portfyl_runtime` BEFORE running the
    migrations, so this assertion is not tautological: it proves migration
    0002 actively strips those attributes off an existing, over-privileged
    role rather than merely creating a safe one on a clean database."""
    role = postgres_session.execute(
        text("""
            SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls, rolinherit
            FROM pg_roles WHERE rolname = 'portfyl_runtime'
        """)
    ).one()

    assert role == (False, False, False, False, False)


def test_runtime_role_owns_no_tables(postgres_session: Session):
    """A table's owner is exempt from its own policies unless FORCE is set --
    and can drop FORCE at will. The runtime role must therefore own nothing."""
    owned = postgres_session.execute(
        text("""
            SELECT class.relname
            FROM pg_class AS class
            JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
            JOIN pg_roles AS owner_role ON owner_role.oid = class.relowner
            WHERE namespace.nspname = 'public' AND owner_role.rolname = 'portfyl_runtime'
        """)
    ).scalars().all()

    assert owned == []


@pytest.mark.parametrize("table", WORKSPACE_SCOPED_TABLES)
def test_runtime_role_cannot_turn_row_level_security_off(
    table: str, matrix_tenants: MatrixTenants, runtime_session: Session,
):
    with pytest.raises((ProgrammingError, DBAPIError)):
        runtime_session.execute(
            text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        )


def test_runtime_role_cannot_grant_itself_more_privileges(
    matrix_tenants: MatrixTenants, runtime_session: Session,
):
    with pytest.raises((ProgrammingError, DBAPIError)):
        runtime_session.execute(text("ALTER ROLE portfyl_runtime BYPASSRLS"))


def test_runtime_role_has_exact_grants_on_rate_limit_buckets(runtime_session: Session):
    grants = runtime_session.execute(
        text(
            """
            SELECT privilege_type
            FROM information_schema.role_table_grants
            WHERE grantee = 'portfyl_runtime'
              AND table_schema = 'public'
              AND table_name = 'rate_limit_buckets'
            ORDER BY privilege_type
            """
        )
    ).scalars().all()
    assert grants == ["DELETE", "INSERT", "SELECT", "UPDATE"]


def test_runtime_role_has_exact_grants_on_beta_invites(runtime_session: Session):
    grants = runtime_session.execute(
        text(
            """
            SELECT privilege_type
            FROM information_schema.role_table_grants
            WHERE grantee = 'portfyl_runtime'
              AND table_schema = 'public'
              AND table_name = 'beta_invites'
            ORDER BY privilege_type
            """
        )
    ).scalars().all()
    assert grants == ["DELETE", "INSERT", "SELECT", "UPDATE"]


# ---------------------------------------------------------------------------
# Where the two layers meet
# ---------------------------------------------------------------------------


def test_forged_workspace_context_is_still_blocked_by_membership_endpoint(
    alice_client: TestClient, bob_workspace: SimpleNamespace,
):
    """RLS trusts `portfyl.workspace_id`; the application decides what may be
    put there. Asking for Bob's workspace over HTTP must never reach the
    `set_rls_context` call -- it dies on the membership lookup, with the same
    404 a nonexistent workspace produces."""
    response = alice_client.get(
        "/api/portfolios",
        headers={"X-Workspace-ID": str(bob_workspace.public_id)},
    )

    assert response.status_code == 404
    assert response.json() == {"code": "resource_not_found"}


def test_the_database_would_serve_bobs_rows_to_bobs_context(
    matrix_tenants: MatrixTenants, runtime_session: Session,
):
    """The reason the membership check above is load-bearing, stated as a
    test: RLS is a filter on the context, not an authorization system. Set the
    context to Bob and Bob's rows appear -- which is exactly why nothing but
    `tenancy.get_request_context`, after verifying an active membership, may
    ever call `set_rls_context`."""
    set_rls_context(
        runtime_session,
        matrix_tenants.bob.user_id,
        matrix_tenants.bob.workspace_id,
    )

    visible = runtime_session.scalars(select(Portfolio)).all()

    assert [row.public_id for row in visible] == [
        matrix_tenants.bob.portfolio_public_id
    ]


def test_a_random_workspace_context_sees_nothing(
    matrix_tenants: MatrixTenants, runtime_session: Session,
):
    set_rls_context(runtime_session, uuid4(), uuid4())

    assert runtime_session.scalars(select(Portfolio)).all() == []


def test_runtime_role_has_exact_grants_on_rate_limit_buckets(runtime_session: Session):
    grants = runtime_session.execute(
        text(
            """
            SELECT privilege_type
            FROM information_schema.role_table_grants
            WHERE grantee = 'portfyl_runtime'
              AND table_schema = 'public'
              AND table_name = 'rate_limit_buckets'
            ORDER BY privilege_type
            """
        )
    ).scalars().all()
    assert grants == ["DELETE", "INSERT", "SELECT", "UPDATE"]
