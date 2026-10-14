"""with_job_lock's advisory-lock semantics need genuinely independent
Postgres connections (the lock is per-session) -- postgres_session's shared,
transaction-scoped connection can't represent "two concurrent invocations,"
so these tests open their own connections against the same disposable server.

The lock lives on a dedicated NullPool connection, separate from the pooled
Session a job pass runs on. The production-shaped tests below deliberately
use that pooled Session shape (sessionmaker bound to an Engine, committing
several times mid-pass while other sessions churn the pool); binding a
Session to one explicit Connection, as an earlier version of this file did,
hides the pool-return behaviour the lock has to survive."""
from __future__ import annotations

import time

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from routers.internal_jobs import with_job_lock


@pytest.fixture
def lock_engine(postgres_url: str, postgres_engine: Engine):
    # postgres_engine is requested so the schema/migrations are in place.
    engine = create_engine(postgres_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def pooled_engine(postgres_url: str, postgres_engine: Engine):
    """Shaped like the job Session's engine: a small QueuePool, so a commit
    hands the connection back and the next statement may get another one."""
    engine = create_engine(postgres_url, pool_size=2, max_overflow=0, pool_timeout=5)
    try:
        yield engine
    finally:
        engine.dispose()


def _advisory_lock_count(engine: Engine, *, wait_for_zero: bool = False) -> int:
    query = text(
        "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
        "AND database = (SELECT oid FROM pg_database WHERE datname = current_database())"
    )
    deadline = time.monotonic() + 3
    while True:
        with engine.connect() as connection:
            count = connection.execute(query).scalar_one()
        if count == 0 or not wait_for_zero or time.monotonic() > deadline:
            return count
        time.sleep(0.05)  # a closed backend takes a moment to drop its locks


def test_second_concurrent_invocation_of_the_same_job_is_skipped(lock_engine: Engine):
    with with_job_lock("alerts", lock_engine) as first_acquired:
        assert first_acquired is True
        with with_job_lock("alerts", lock_engine) as second_acquired:
            assert second_acquired is False


def test_lock_is_released_after_the_context_exits(lock_engine: Engine, postgres_engine: Engine):
    with with_job_lock("dividends", lock_engine) as acquired:
        assert acquired is True

    assert _advisory_lock_count(postgres_engine, wait_for_zero=True) == 0
    with with_job_lock("dividends", lock_engine) as acquired:
        assert acquired is True  # the first lock was released, not leaked


def test_lock_is_released_when_the_pass_raises(lock_engine: Engine, postgres_engine: Engine):
    with pytest.raises(RuntimeError, match="boom"):
        with with_job_lock("alerts", lock_engine) as acquired:
            assert acquired is True
            raise RuntimeError("boom")

    assert _advisory_lock_count(postgres_engine, wait_for_zero=True) == 0
    with with_job_lock("alerts", lock_engine) as acquired:
        assert acquired is True


def test_different_job_names_never_contend(lock_engine: Engine):
    with with_job_lock("alerts", lock_engine) as alerts_acquired:
        assert alerts_acquired is True
        with with_job_lock("autosync", lock_engine) as autosync_acquired:
            assert autosync_acquired is True


def test_lock_holds_across_pass_commits_while_the_pool_is_churned(
    lock_engine: Engine, pooled_engine: Engine, postgres_engine: Engine,
):
    """The shape that production runs: the pass uses a pooled Session that
    commits repeatedly and returns its connection to the pool each time,
    while other work checks connections out of the same pool. A concurrent
    invocation must be refused for the whole pass, and nothing may be left
    behind afterwards."""
    job_factory = sessionmaker(autocommit=False, autoflush=False, bind=pooled_engine)
    other_factory = sessionmaker(autocommit=False, autoflush=False, bind=pooled_engine)

    with with_job_lock("alerts", lock_engine) as acquired:
        assert acquired is True
        job_db = job_factory()
        try:
            for step in range(6):
                job_db.execute(text("SELECT :step"), {"step": step})
                job_db.commit()  # connection goes back to the pool here

                # Someone else takes (and returns) connections from the pool.
                other_db = other_factory()
                try:
                    other_db.execute(text("SELECT 1"))
                    other_db.commit()
                finally:
                    other_db.close()

                with with_job_lock("alerts", lock_engine) as overlapping:
                    assert overlapping is False, f"lock lost after pass commit {step}"
        finally:
            job_db.close()

    # Neither the lock connection nor the pool may keep a lock alive.
    assert _advisory_lock_count(postgres_engine, wait_for_zero=True) == 0
    with with_job_lock("alerts", lock_engine) as next_invocation:
        assert next_invocation is True


def test_lock_on_a_pooled_engine_is_still_released_explicitly(
    pooled_engine: Engine, postgres_engine: Engine,
):
    """Defence in depth: if a pooled engine is ever passed in, the explicit
    unlock still clears the lock instead of leaving it on a pooled socket."""
    with with_job_lock("dividends", pooled_engine) as acquired:
        assert acquired is True

    assert _advisory_lock_count(postgres_engine) == 0
    with with_job_lock("dividends", pooled_engine) as acquired:
        assert acquired is True
