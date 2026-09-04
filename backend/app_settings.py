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

import base64
import json
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from models import UserSetting, WorkspaceSetting
from secrets_crypto import EncryptedValue, get_secret_cipher


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


def _encode_encrypted(value: EncryptedValue) -> str:
    return json.dumps({
        "ciphertext": base64.b64encode(value.ciphertext).decode("ascii"),
        "key_version": value.key_version,
    })


def _decode_encrypted(raw: str) -> EncryptedValue:
    data = json.loads(raw)
    return EncryptedValue(
        ciphertext=base64.b64decode(data["ciphertext"]),
        key_version=data["key_version"],
    )


def get_user_secret(db: Session, user_id: UUID, key: str) -> Optional[str]:
    """Like get_user_setting, but for a value that was written with
    set_user_secret -- the stored value is a JSON-encoded EncryptedValue,
    never plaintext."""
    raw = get_user_setting(db, user_id, key)
    if not raw:
        return None
    return get_secret_cipher().decrypt(_decode_encrypted(raw))


def set_user_secret(db: Session, user_id: UUID, key: str, plaintext: Optional[str]) -> None:
    """Like set_user_setting, but encrypts before storing. `UserSetting.value`
    is a plain string column -- no schema change needed, the ciphertext and
    key version are just JSON-encoded into it (see _encode_encrypted)."""
    if not plaintext:
        set_user_setting(db, user_id, key, None)
        return
    encrypted = get_secret_cipher().encrypt(plaintext)
    set_user_setting(db, user_id, key, _encode_encrypted(encrypted))


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
