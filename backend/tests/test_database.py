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


NEON_URL = "postgresql+psycopg://u:p@ep-test-pooler.eu.neon.tech/portfyl?sslmode=require"


def test_pool_defaults_cover_a_dashboard_burst_and_fail_fast():
    # One dashboard load fires ~13 requests at once; the old 5 + 2 pool with a
    # 30s wait queued most of them. DATABASE_URL is Neon's pooled endpoint,
    # so a larger client-side pool is cheap.
    settings = DatabaseSettings.from_env({"DATABASE_URL": NEON_URL})
    engine = build_engine(settings)

    assert (settings.pool_size, settings.max_overflow, settings.pool_timeout) == (10, 5, 10.0)
    assert engine.pool.size() == 10
    assert engine.pool._max_overflow == 5
    assert engine.pool._timeout == 10.0


def test_pool_can_be_tuned_from_the_environment():
    settings = DatabaseSettings.from_env({
        "DATABASE_URL": NEON_URL,
        "DB_POOL_SIZE": "12",
        "DB_MAX_OVERFLOW": "0",
        "DB_POOL_TIMEOUT": "4.5",
    })

    assert (settings.pool_size, settings.max_overflow, settings.pool_timeout) == (12, 0, 4.5)


@pytest.mark.parametrize("key, value", [
    ("DB_POOL_SIZE", "0"),
    ("DB_POOL_SIZE", "ten"),
    ("DB_MAX_OVERFLOW", "-1"),
    ("DB_POOL_TIMEOUT", "0"),
])
def test_invalid_pool_settings_fail_closed(key, value):
    with pytest.raises(RuntimeError, match=key):
        DatabaseSettings.from_env({"DATABASE_URL": NEON_URL, key: value})
