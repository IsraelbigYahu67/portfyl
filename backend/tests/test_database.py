from __future__ import annotations

import pytest
from sqlalchemy import text

from database import DatabaseSettings, build_engine


def test_database_settings_requires_url_in_runtime():
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        DatabaseSettings.from_env({})


def test_database_settings_accepts_neon_postgresql_url():
    settings = DatabaseSettings.from_env({
        "DATABASE_URL": "postgresql+psycopg://u:p@ep-test-pooler.eu.neon.tech/portfyl?sslmode=require"
    })

    assert settings.url.startswith("postgresql+psycopg://")
    assert settings.pool_pre_ping is True


def test_database_settings_allows_sqlite_only_for_explicit_test_mode():
    settings = DatabaseSettings.from_env({
        "DATABASE_URL": "sqlite:///:memory:",
        "PORTFYL_TESTING": "1",
    })

    assert settings.url == "sqlite:///:memory:"


def test_build_engine_connects_to_test_sqlite_url():
    settings = DatabaseSettings.from_env({
        "DATABASE_URL": "sqlite:///:memory:",
        "PORTFYL_TESTING": "1",
    })

    with build_engine(settings).connect() as connection:
        assert connection.execute(text("select 1")).scalar_one() == 1
