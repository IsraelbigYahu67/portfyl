from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import database
import models
from database import Base


def _model(name: str):
    mapped = getattr(models, name, None)
    assert mapped is not None, f"{name} must be mapped"
    return mapped


def test_identity_and_tenancy_tables_are_mapped():
    expected = {
        "users",
        "workspaces",
        "memberships",
        "auth_sessions",
        "user_settings",
        "workspace_settings",
        "data_migration_runs",
    }

    assert expected <= set(Base.metadata.tables)


def test_tenant_names_are_unique_only_inside_workspace(postgres_session: Session):
    Workspace = _model("Workspace")

    alice_workspace = Workspace(name="Alice")
    bob_workspace = Workspace(name="Bob")
    postgres_session.add_all([alice_workspace, bob_workspace])
    postgres_session.flush()

    postgres_session.add_all(
        [
            models.Portfolio(workspace_id=alice_workspace.id, name="Main"),
            models.Portfolio(workspace_id=bob_workspace.id, name="Main"),
        ]
    )
    postgres_session.commit()

    postgres_session.add(models.Portfolio(workspace_id=alice_workspace.id, name="Main"))
    with pytest.raises(IntegrityError):
        postgres_session.commit()


def test_domain_public_ids_are_uuid(postgres_session: Session):
    Workspace = _model("Workspace")

    workspace = Workspace(name="Growth workspace")
    postgres_session.add(workspace)
    postgres_session.flush()
    row = models.Portfolio(workspace_id=workspace.id, name="Growth")
    postgres_session.add(row)
    postgres_session.commit()

    assert isinstance(row.public_id, UUID)


def test_user_email_must_be_normalized(postgres_session: Session):
    postgres_session.add(models.User(email=" Alice@Example.com "))

    with pytest.raises(IntegrityError):
        postgres_session.commit()


def test_all_tenant_child_foreign_keys_include_workspace(postgres_session: Session):
    expected = {
        "fk_transaction_workspace_portfolio",
        "fk_watchlist_item_workspace_watchlist",
        "fk_benchmark_workspace_portfolio",
        "fk_benchmark_component_workspace_benchmark",
        "fk_broker_connection_workspace_portfolio",
        "fk_broker_balance_workspace_portfolio",
        "fk_options_trade_workspace_portfolio",
        "fk_polymarket_position_workspace_portfolio",
        "fk_discord_webhook_workspace_portfolio",
        "fk_trade_note_workspace_transaction",
        "fk_cash_interest_rate_workspace_portfolio",
        "fk_dividend_notification_workspace_portfolio",
        "fk_price_alert_workspace_portfolio",
    }
    actual = set(postgres_session.scalars(text("""
        SELECT constraint_name
        FROM information_schema.table_constraints
        WHERE constraint_schema = 'public'
          AND constraint_type = 'FOREIGN KEY'
          AND constraint_name = ANY(:names)
    """), {"names": sorted(expected)}))

    assert actual == expected


def test_database_head_mismatch_fails_closed(postgres_session: Session):
    checker = getattr(database, "assert_alembic_head", None)
    assert checker is not None, "assert_alembic_head must be implemented"

    postgres_session.execute(text("UPDATE alembic_version SET version_num = 'wrong_head'"))
    with pytest.raises(RuntimeError, match="Alembic.*wrong_head"):
        checker(postgres_session, expected_head="0002_tenant_rls")
