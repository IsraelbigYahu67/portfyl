"""Scoped key/value setting stores.

Two independent tables back these helpers:
  * ``user_settings``      -- one row per (user_id, key). Personal preferences
    that follow the signed-in user across every workspace they belong to
    (currently just the DeepSeek assistant API key + model).
  * ``workspace_settings`` -- one row per (workspace_id, key). Shared config
    for everyone in a workspace (currently the broker auto-sync schedule).

There is deliberately no generic key-only get_setting/set_setting anymore --
every caller states explicitly which scope (and whose id) a setting belongs
to, so a setting can never leak between two users or two workspaces sharing
the same key string.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from models import UserSetting, WorkspaceSetting


def get_user_setting(db: Session, user_id: UUID, key: str) -> Optional[str]:
    row = db.query(UserSetting).filter(
        UserSetting.user_id == user_id, UserSetting.key == key
    ).first()
    return row.value if row else None


def set_user_setting(db: Session, user_id: UUID, key: str, value: Optional[str]) -> None:
    """Upsert without committing -- callers own the transaction. Flushes (but
    does not commit) so a read of the same key later in the same session --
    even one with autoflush off -- sees this write immediately."""
    row = db.query(UserSetting).filter(
        UserSetting.user_id == user_id, UserSetting.key == key
    ).first()
    if row is None:
        db.add(UserSetting(user_id=user_id, key=key, value=value))
    else:
        row.value = value
    db.flush()


def get_workspace_setting(db: Session, workspace_id: UUID, key: str) -> Optional[str]:
    row = db.query(WorkspaceSetting).filter(
        WorkspaceSetting.workspace_id == workspace_id, WorkspaceSetting.key == key
    ).first()
    return row.value if row else None


def set_workspace_setting(db: Session, workspace_id: UUID, key: str, value: Optional[str]) -> None:
    """Upsert without committing -- callers own the transaction. Flushes (but
    does not commit) so a read of the same key later in the same session --
    even one with autoflush off -- sees this write immediately."""
    row = db.query(WorkspaceSetting).filter(
        WorkspaceSetting.workspace_id == workspace_id, WorkspaceSetting.key == key
    ).first()
    if row is None:
        db.add(WorkspaceSetting(workspace_id=workspace_id, key=key, value=value))
    else:
        row.value = value
    db.flush()
