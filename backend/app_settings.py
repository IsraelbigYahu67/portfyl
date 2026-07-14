"""Shared helpers for the AppSetting key/value store (global app config).

Extracted from routers/assistant.py so background jobs and the settings
router can reuse them without importing a router module.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from models import AppSetting


def get_setting(db: Session, key: str) -> Optional[str]:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row else None


def set_setting(db: Session, key: str, value: Optional[str]) -> None:
    """Upsert without committing — callers own the transaction."""
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
