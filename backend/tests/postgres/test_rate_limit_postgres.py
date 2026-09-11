"""consume_rate_limit's upsert and transaction-boundary guarantees need
real concurrent Postgres commits and real row locks -- postgres_session's
shared, rolled-back transaction can't represent either, so this opens
independent connections the same way test_job_advisory_lock.py does, and
runs its own isolated migration round-trip for 0012."""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

import rate_limit
from rate_limit import RateLimitRule, consume_rate_limit

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def _independent_session(engine: Engine):
    connection = engine.connect()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()
    try:
        yield session
    finally:
        session.close()
        connection.close()


def test_concurrent_increments_produce_the_exact_final_count(
    postgres_engine: Engine, postgres_url: str, monkeypatch
):
    monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
    # NB: str(engine.url) renders the password as "***", so building the
    # second engine from it would fail to authenticate -- use the raw URL
    # fixture the postgres_engine fixture itself was built from.
    concurrency_engine = create_engine(postgres_url, pool_size=20, max_overflow=0)
    monkeypatch.setattr(
        rate_limit, "SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=concurrency_engine),
    )
    rule = RateLimitRule(name="test_concurrency", limit=1000, window_seconds=3600)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    errors: list[Exception] = []

    def _worker():
        try:
            consume_rate_limit(rule=rule, identity="shared-bucket", now=now)
        except Exception as exc:  # RateLimitExceeded would also be a bug here (limit=1000, 20 workers)
            errors.append(exc)

    threads = [threading.Thread(target=_worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    key = rate_limit._bucket_key(
        rule_name=rule.name, identity="shared-bucket",
        window_index=int(now.timestamp() // rule.window_seconds),
    )
    with concurrency_engine.connect() as conn:
        count = conn.execute(text("SELECT count FROM rate_limit_buckets WHERE key = :key"), {"key": key}).scalar_one()
    assert count == 20
    concurrency_engine.dispose()


def test_limiter_transaction_releases_the_row_lock_before_returning(postgres_engine: Engine, monkeypatch):
    monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
    monkeypatch.setattr(
        rate_limit, "SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=postgres_engine),
    )
    rule = RateLimitRule(name="test_lock_release", limit=100, window_seconds=3600)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    consume_rate_limit(rule=rule, identity="lock-test", now=now)  # commits and closes internally

    key = rate_limit._bucket_key(
        rule_name=rule.name, identity="lock-test",
        window_index=int(now.timestamp() // rule.window_seconds),
    )
    with _independent_session(postgres_engine) as second:
        # FOR UPDATE NOWAIT raises immediately instead of blocking if any
        # other session still holds the row lock -- proving the limiter's
        # own transaction already committed and released it. scalar_one()
        # additionally requires the row to actually be there, so dropping
        # the limiter's commit() fails this test loudly instead of passing
        # vacuously on an empty result set.
        locked = second.execute(
            text("SELECT 1 FROM rate_limit_buckets WHERE key = :key FOR UPDATE NOWAIT"), {"key": key}
        ).scalar_one()
        assert locked == 1
        second.rollback()


def test_0012_migration_upgrades_and_downgrades_cleanly(postgres_engine: Engine, postgres_url: str):
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    with patch.dict(os.environ, {"DATABASE_URL": postgres_url}):
        command.downgrade(alembic_config, "0011_remove_payment_runtime")
        with postgres_engine.connect() as conn:
            assert conn.execute(text("SELECT to_regclass('public.rate_limit_buckets')")).scalar() is None

        command.upgrade(alembic_config, "0012_rate_limit_buckets")
        with postgres_engine.connect() as conn:
            assert conn.execute(text("SELECT to_regclass('public.rate_limit_buckets')")).scalar() == "rate_limit_buckets"
            grants = conn.execute(text(
                "SELECT privilege_type FROM information_schema.role_table_grants "
                "WHERE grantee = 'portfyl_runtime' AND table_name = 'rate_limit_buckets' "
                "ORDER BY privilege_type"
            )).scalars().all()
            assert grants == ["DELETE", "INSERT", "SELECT", "UPDATE"]
            indexes = conn.execute(text(
                "SELECT indexname FROM pg_indexes WHERE tablename = 'rate_limit_buckets'"
            )).scalars().all()
            assert "ix_rate_limit_buckets_expires_at" in indexes

        # postgres_engine is session-scoped and shared by every other test file.
        # Re-upgrade to head (not just this revision) so a later migration added
        # after 0012 -- e.g. 0013_private_beta_invites -- isn't left permanently
        # un-applied for the rest of the test session.
        command.upgrade(alembic_config, "head")
