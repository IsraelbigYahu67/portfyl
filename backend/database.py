from __future__ import annotations

import os
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
