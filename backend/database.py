from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
