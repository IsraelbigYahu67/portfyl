import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DB_FILE = "portfyl.db"
_LEGACY_DB_FILE = "snowball.db"  # pre-rename name; migrate existing data on first run

# One-time migration: if the database still lives under the old "snowball.db"
# name and no portfyl.db exists yet, rename it so existing portfolio data
# carries over transparently.
if os.path.exists(_LEGACY_DB_FILE) and not os.path.exists(DB_FILE):
    os.rename(_LEGACY_DB_FILE, DB_FILE)

# DB location is configurable so production can point at the mounted GCS volume,
# while local dev keeps ./portfyl.db (relative to the backend dir).
# Absolute paths work too: DATABASE_PATH=/mnt/data/portfyl.db -> sqlite:////mnt/data/...
DATABASE_PATH = os.getenv("DATABASE_PATH", f"./{DB_FILE}")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
