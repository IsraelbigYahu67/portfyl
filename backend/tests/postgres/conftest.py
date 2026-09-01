from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from database import DatabaseSettings, build_engine


BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _assert_disposable_postgres_url(url: str) -> None:
    database = make_url(url).database or ""
    normalized = database.casefold()
    if not (
        normalized == "test"
        or normalized.startswith("test_")
        or normalized.endswith("_test")
    ):
        raise RuntimeError(
            "PostgreSQL integration tests require a disposable database whose name contains 'test'"
        )


@pytest.fixture(scope="session")
def postgres_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://portfyl_test:portfyl_test@localhost:55441/portfyl_test",
    )


@pytest.fixture(scope="session")
def postgres_engine(postgres_url: str) -> Engine:
    _assert_disposable_postgres_url(postgres_url)
    engine = build_engine(DatabaseSettings.from_env({"DATABASE_URL": postgres_url}))
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
        connection.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_roles WHERE rolname = 'portfyl_runtime'
                ) THEN
                    CREATE ROLE portfyl_runtime NOLOGIN;
                END IF;
            END
            $$
        """))
        connection.execute(text(
            "ALTER ROLE portfyl_runtime BYPASSRLS CREATEDB CREATEROLE"
        ))

    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with patch.dict(os.environ, {"DATABASE_URL": postgres_url}):
        command.upgrade(alembic_config, "head")
    try:
        yield engine
    finally:
        with patch.dict(os.environ, {"DATABASE_URL": postgres_url}):
            command.downgrade(alembic_config, "base")
        engine.dispose()


@pytest.fixture
def postgres_session(postgres_engine: Engine) -> Session:
    connection = postgres_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()


@pytest.fixture
def runtime_session(postgres_engine: Engine) -> Session:
    connection = postgres_engine.connect()
    transaction = connection.begin()
    connection.execute(text("SET LOCAL ROLE portfyl_runtime"))
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
