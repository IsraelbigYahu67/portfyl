from __future__ import annotations

import contextvars
import os
import weakref
from dataclasses import dataclass
from typing import Mapping
from uuid import UUID

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


@dataclass(frozen=True)
class DatabaseSettings:
    url: str
    pool_pre_ping: bool = True
    pool_recycle: int = 300
    pool_size: int = 5
    max_overflow: int = 2

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "DatabaseSettings":
        url = env.get("DATABASE_URL", "").strip()
        if not url:
            raise RuntimeError("DATABASE_URL is required")
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url.removeprefix("postgres://")
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
        if not url.startswith("postgresql+psycopg://") and env.get("PORTFYL_TESTING") != "1":
            raise RuntimeError("DATABASE_URL must use PostgreSQL")
        return cls(url=url)


def build_engine(settings: DatabaseSettings) -> Engine:
    if settings.url.startswith("sqlite:"):
        return create_engine(settings.url, connect_args={"check_same_thread": False})
    return create_engine(
        settings.url,
        pool_pre_ping=settings.pool_pre_ping,
        pool_recycle=settings.pool_recycle,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
    )


settings = DatabaseSettings.from_env(os.environ)
engine = build_engine(settings)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


EXPECTED_ALEMBIC_HEAD = "0023_allocation_targets"


def assert_alembic_head(
    session: Session,
    expected_head: str = EXPECTED_ALEMBIC_HEAD,
) -> None:
    try:
        actual_head = session.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()
    except SQLAlchemyError as exc:
        raise RuntimeError(
            "Alembic schema state is unavailable; run `alembic upgrade head` before startup"
        ) from exc
    if actual_head != expected_head:
        raise RuntimeError(
            f"Alembic revision mismatch: expected {expected_head}, got {actual_head or 'none'}"
        )


_RLS_CONTEXT_INFO_KEY = "portfyl_rls_context"


def set_rls_context(
    session: Session,
    user_id: UUID,
    workspace_id: UUID | None,
) -> None:
    """Set the RLS identity for this session's current and later transactions.

    `set_config(..., true)` is transaction-local, so on its own the context
    would vanish at the first commit or rollback and every later read in the
    same request would see nothing under forced RLS. The values are remembered
    on the session and re-applied at the start of each new transaction by
    `_reapply_rls_context`. They stay transaction-local, so nothing outlives
    this Session object or leaks to another session on a pooled connection.
    """
    values = {
        "portfyl.user_id": str(user_id),
        "portfyl.workspace_id": "" if workspace_id is None else str(workspace_id),
    }
    session.info[_RLS_CONTEXT_INFO_KEY] = values
    for key, value in values.items():
        session.execute(
            text("SELECT set_config(:key, :value, true)"),
            {"key": key, "value": value},
        )


@event.listens_for(Session, "after_begin")
def _reapply_rls_context(session: Session, _transaction, connection) -> None:
    values = session.info.get(_RLS_CONTEXT_INFO_KEY)
    if not values or connection.dialect.name != "postgresql":
        return
    for key, value in values.items():
        connection.execute(
            text("SELECT set_config(:key, :value, true)"),
            {"key": key, "value": value},
        )


_REQUEST_SCOPED_KEY = "portfyl_request_scoped"
_FLUSHED_WRITES_KEY = "portfyl_flushed_writes"
# Request sessions used by the current call. Starlette runs every sync
# dependency and endpoint through anyio, which gives each call its own copy
# of the caller's context, so this only ever sees the sessions of the
# request running in this thread right now, never another request's.
_request_sessions: contextvars.ContextVar[tuple[weakref.ref, ...]] = contextvars.ContextVar(
    "portfyl_request_sessions", default=()
)


@event.listens_for(Session, "do_orm_execute")
def _track_request_session(orm_execute_state) -> None:
    session = orm_execute_state.session
    if not session.info.get(_REQUEST_SCOPED_KEY):
        return
    refs = _request_sessions.get()
    if any(ref() is session for ref in refs):
        return
    _request_sessions.set(refs + (weakref.ref(session),))


@event.listens_for(Session, "after_flush")
def _mark_flushed_writes(session: Session, _flush_context) -> None:
    session.info[_FLUSHED_WRITES_KEY] = True


@event.listens_for(Session, "after_transaction_end")
def _clear_flushed_writes(session: Session, transaction) -> None:
    if transaction.parent is None:
        session.info.pop(_FLUSHED_WRITES_KEY, None)


def release_connection(session: Session, *, commit_pending: bool = False) -> None:
    """Give this session's pooled connection back before slow network I/O.

    A Session holds its connection from the first query until the
    transaction ends. An endpoint that read the database and then waited on
    Yahoo Finance kept a pool slot busy the whole time, so a few concurrent
    dashboard requests exhausted the pool (5 + 2) and every other request,
    login included, timed out. Ending the read transaction returns the
    connection. Loaded objects stay attached and readable: the commit skips
    expire_on_commit, so touching them does not reopen a transaction. The
    next query begins a new transaction and `_reapply_rls_context` restores
    the RLS identity, so tenant scoping is unchanged.

    A session with pending or flushed-but-uncommitted writes is left alone,
    so a write is never committed early. `commit_pending=True` is for a
    caller that owns those writes and wants them committed here (the auth
    dependency's last-seen touch, see tenancy.get_request_context).
    """
    if not session.in_transaction():
        return
    if not commit_pending and (
        session.new or session.dirty or session.deleted or session.info.get(_FLUSHED_WRITES_KEY)
    ):
        return
    expire = session.expire_on_commit
    session.expire_on_commit = False
    try:
        session.commit()
    finally:
        session.expire_on_commit = expire


def release_request_connections() -> None:
    """Release the connection of every request session this call has used.

    Called by market_data right before it reaches Yahoo Finance, so the
    routers do not have to thread `db` into every helper that fetches quotes.
    Sessions outside a request (background jobs) are never touched.
    """
    for ref in _request_sessions.get():
        session = ref()
        if session is not None:
            release_connection(session)


def get_db():
    db = SessionLocal()
    db.info[_REQUEST_SCOPED_KEY] = True
    try:
        yield db
    finally:
        db.close()
