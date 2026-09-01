"""Enable and force tenant row-level security.

Revision ID: 0002_tenant_rls
Revises: 0001_multiuser_schema
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0002_tenant_rls"
down_revision: Union[str, Sequence[str], None] = "0001_multiuser_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_WORKSPACE_TABLES = (
    "data_migration_runs",
    "portfolios",
    "transactions",
    "watchlists",
    "watchlist_items",
    "workspace_settings",
    "broker_connections",
    "broker_balances",
    "options_trades",
    "polymarket_positions",
    "discord_webhooks",
    "trade_notes",
    "cash_interest_rates",
    "dividend_notifications",
    "price_alerts",
)

_USER_TABLES = (
    "memberships",
    "user_settings",
)

_RUNTIME_TABLES = (
    "users",
    "workspaces",
    "memberships",
    "auth_sessions",
    "user_settings",
    "workspace_settings",
    "portfolios",
    "transactions",
    "watchlists",
    "watchlist_items",
    "benchmarks",
    "benchmark_components",
    "broker_connections",
    "broker_balances",
    "options_trades",
    "polymarket_positions",
    "discord_webhooks",
    "trade_notes",
    "cash_interest_rates",
    "dividend_notifications",
    "price_alerts",
)

_RUNTIME_SEQUENCES = tuple(f"{table}_id_seq" for table in (
    "portfolios",
    "transactions",
    "watchlists",
    "watchlist_items",
    "benchmarks",
    "benchmark_components",
    "broker_connections",
    "broker_balances",
    "options_trades",
    "polymarket_positions",
    "discord_webhooks",
    "trade_notes",
    "cash_interest_rates",
    "dividend_notifications",
    "price_alerts",
))

_WORKSPACE_SETTING = (
    "NULLIF(current_setting('portfyl.workspace_id', true), '')::uuid"
)
_USER_SETTING = "NULLIF(current_setting('portfyl.user_id', true), '')::uuid"


def _quoted(objects: tuple[str, ...]) -> str:
    return ", ".join(f'"{name}"' for name in objects)


def _enable_forced_rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')


def _disable_forced_rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF current_user = 'portfyl_runtime' THEN
                RAISE EXCEPTION 'RLS migration cannot run as portfyl_runtime';
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'portfyl_runtime') THEN
                CREATE ROLE portfyl_runtime
                    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE
                    NOINHERIT NOREPLICATION NOBYPASSRLS;
            ELSE
                EXECUTE 'ALTER ROLE portfyl_runtime '
                    'NOSUPERUSER NOCREATEDB NOCREATEROLE '
                    'NOINHERIT NOREPLICATION NOBYPASSRLS';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM pg_auth_members AS membership
                JOIN pg_roles AS member_role ON member_role.oid = membership.member
                WHERE member_role.rolname = 'portfyl_runtime'
            ) THEN
                RAISE EXCEPTION 'portfyl_runtime must not inherit another database role';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM pg_class AS class
                JOIN pg_namespace AS namespace ON namespace.oid = class.relnamespace
                JOIN pg_roles AS owner_role ON owner_role.oid = class.relowner
                WHERE namespace.nspname = 'public'
                  AND owner_role.rolname = 'portfyl_runtime'
            ) THEN
                RAISE EXCEPTION 'portfyl_runtime must not own public schema objects';
            END IF;
        END
        $$
    """)

    op.execute("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM portfyl_runtime")
    op.execute("REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM portfyl_runtime")
    op.execute("REVOKE ALL PRIVILEGES ON SCHEMA public FROM portfyl_runtime")
    op.execute("GRANT USAGE ON SCHEMA public TO portfyl_runtime")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE "
        f"{_quoted(_RUNTIME_TABLES)} TO portfyl_runtime"
    )
    op.execute("GRANT SELECT ON TABLE alembic_version TO portfyl_runtime")
    op.execute(
        "GRANT USAGE, SELECT ON SEQUENCE "
        f"{_quoted(_RUNTIME_SEQUENCES)} TO portfyl_runtime"
    )

    _enable_forced_rls("workspaces")
    op.execute(f"""
        CREATE POLICY workspace_tenant_policy ON workspaces
        USING (id = {_WORKSPACE_SETTING})
        WITH CHECK (id = {_WORKSPACE_SETTING})
    """)

    for table in _WORKSPACE_TABLES:
        _enable_forced_rls(table)
        op.execute(f"""
            CREATE POLICY {table}_tenant_policy ON {table}
            USING (workspace_id = {_WORKSPACE_SETTING})
            WITH CHECK (workspace_id = {_WORKSPACE_SETTING})
        """)

    for table in _USER_TABLES:
        _enable_forced_rls(table)
        op.execute(f"""
            CREATE POLICY {table}_user_policy ON {table}
            USING (user_id = {_USER_SETTING})
            WITH CHECK (user_id = {_USER_SETTING})
        """)

    _enable_forced_rls("benchmarks")
    op.execute(f"""
        CREATE POLICY benchmarks_select_policy ON benchmarks
        FOR SELECT
        USING (
            workspace_id = {_WORKSPACE_SETTING}
            OR (workspace_id IS NULL AND is_preset IS TRUE)
        )
    """)
    op.execute(f"""
        CREATE POLICY benchmarks_write_policy ON benchmarks
        FOR ALL
        USING (workspace_id = {_WORKSPACE_SETTING} AND is_preset IS FALSE)
        WITH CHECK (workspace_id = {_WORKSPACE_SETTING} AND is_preset IS FALSE)
    """)

    _enable_forced_rls("benchmark_components")
    op.execute(f"""
        CREATE POLICY benchmark_components_select_policy ON benchmark_components
        FOR SELECT
        USING (
            workspace_id = {_WORKSPACE_SETTING}
            OR (
                workspace_id IS NULL
                AND EXISTS (
                    SELECT 1 FROM benchmarks
                    WHERE benchmarks.id = benchmark_components.benchmark_id
                      AND benchmarks.workspace_id IS NULL
                      AND benchmarks.is_preset IS TRUE
                )
            )
        )
    """)
    op.execute(f"""
        CREATE POLICY benchmark_components_write_policy ON benchmark_components
        FOR ALL
        USING (
            workspace_id = {_WORKSPACE_SETTING}
            AND EXISTS (
                SELECT 1 FROM benchmarks
                WHERE benchmarks.id = benchmark_components.benchmark_id
                  AND benchmarks.workspace_id = {_WORKSPACE_SETTING}
                  AND benchmarks.is_preset IS FALSE
            )
        )
        WITH CHECK (
            workspace_id = {_WORKSPACE_SETTING}
            AND EXISTS (
                SELECT 1 FROM benchmarks
                WHERE benchmarks.id = benchmark_components.benchmark_id
                  AND benchmarks.workspace_id = {_WORKSPACE_SETTING}
                  AND benchmarks.is_preset IS FALSE
            )
        )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS benchmark_components_write_policy ON benchmark_components")
    op.execute("DROP POLICY IF EXISTS benchmark_components_select_policy ON benchmark_components")
    _disable_forced_rls("benchmark_components")
    op.execute("DROP POLICY IF EXISTS benchmarks_write_policy ON benchmarks")
    op.execute("DROP POLICY IF EXISTS benchmarks_select_policy ON benchmarks")
    _disable_forced_rls("benchmarks")

    for table in reversed(_USER_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_user_policy ON {table}")
        _disable_forced_rls(table)

    for table in reversed(_WORKSPACE_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_policy ON {table}")
        _disable_forced_rls(table)

    op.execute("DROP POLICY IF EXISTS workspace_tenant_policy ON workspaces")
    _disable_forced_rls("workspaces")
    op.execute(
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE "
        f"{_quoted(_RUNTIME_TABLES)} FROM portfyl_runtime"
    )
    op.execute("REVOKE SELECT ON TABLE alembic_version FROM portfyl_runtime")
    op.execute(
        "REVOKE USAGE, SELECT ON SEQUENCE "
        f"{_quoted(_RUNTIME_SEQUENCES)} FROM portfyl_runtime"
    )
    op.execute("REVOKE USAGE ON SCHEMA public FROM portfyl_runtime")
    # The cluster-scoped role may predate this database; never drop it implicitly.
