"""with_job_lock's advisory-lock semantics need two genuinely independent
Postgres connections (the lock is per-session) -- postgres_session's shared,
transaction-scoped connection can't represent "two concurrent invocations,"
so this test opens its own connections against the same disposable server."""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from routers.internal_jobs import with_job_lock


@contextmanager
def _independent_session(engine: Engine):
    """A Session bound to its own checked-out connection -- Session.close()
    doesn't close a connection it didn't open itself, so this closes both
    explicitly to actually return the connection (and release any advisory
    lock still held on it) to the pool."""
    connection = engine.connect()
    session = sessionmaker(autocommit=False, autoflush=False, bind=connection)()
    try:
        yield session
    finally:
        session.close()
        connection.close()


def test_second_concurrent_invocation_of_the_same_job_is_skipped(postgres_engine: Engine):
    with _independent_session(postgres_engine) as first, \
         _independent_session(postgres_engine) as second:
        with with_job_lock(first, "alerts") as first_acquired:
            assert first_acquired is True
            with with_job_lock(second, "alerts") as second_acquired:
                assert second_acquired is False


def test_lock_is_released_after_the_context_exits(postgres_engine: Engine):
    with _independent_session(postgres_engine) as first:
        with with_job_lock(first, "dividends") as acquired:
            assert acquired is True

    with _independent_session(postgres_engine) as second:
        with with_job_lock(second, "dividends") as acquired:
            assert acquired is True  # first's lock was released, not leaked


def test_different_job_names_never_contend(postgres_engine: Engine):
    with _independent_session(postgres_engine) as first, \
         _independent_session(postgres_engine) as second:
        with with_job_lock(first, "alerts") as alerts_acquired:
            assert alerts_acquired is True
            with with_job_lock(second, "autosync") as autosync_acquired:
                assert autosync_acquired is True
