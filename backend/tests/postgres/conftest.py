from __future__ import annotations

import os

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from database import Base, DatabaseSettings, build_engine


@pytest.fixture(scope="session")
def postgres_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://portfyl_test:portfyl_test@localhost:55441/portfyl_test",
    )


@pytest.fixture(scope="session")
def postgres_engine(postgres_url: str) -> Engine:
    engine = build_engine(DatabaseSettings.from_env({"DATABASE_URL": postgres_url}))
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def postgres_session(postgres_engine: Engine) -> Session:
    session = sessionmaker(autocommit=False, autoflush=False, bind=postgres_engine)()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
