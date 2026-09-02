"""Tests for the user- and workspace-scoped setting helpers."""

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app_settings import (
    get_user_setting, set_user_setting,
    get_workspace_setting, set_workspace_setting,
)
from models import UserSetting, WorkspaceSetting


# -------- user settings -----------------------------------------------------

def test_get_missing_user_key_returns_none(db_session, test_user):
    assert get_user_setting(db_session, test_user.id, "nope") is None


def test_user_set_then_get_roundtrip(db_session, test_user):
    set_user_setting(db_session, test_user.id, "deepseek_model", "v1")
    db_session.commit()
    assert get_user_setting(db_session, test_user.id, "deepseek_model") == "v1"


def test_user_set_updates_existing_row(db_session, test_user):
    set_user_setting(db_session, test_user.id, "k", "v1")
    db_session.commit()
    set_user_setting(db_session, test_user.id, "k", "v2")
    db_session.commit()
    assert get_user_setting(db_session, test_user.id, "k") == "v2"
    # still a single row, not a duplicate key
    assert db_session.query(UserSetting).filter(UserSetting.key == "k").count() == 1


# -------- workspace settings -------------------------------------------------

def test_get_missing_workspace_key_returns_none(db_session, test_workspace):
    assert get_workspace_setting(db_session, test_workspace.id, "nope") is None


def test_workspace_set_then_get_roundtrip(db_session, test_workspace):
    set_workspace_setting(db_session, test_workspace.id, "sync_mode", "daily")
    db_session.commit()
    assert get_workspace_setting(db_session, test_workspace.id, "sync_mode") == "daily"


def test_workspace_set_updates_existing_row(db_session, test_workspace):
    set_workspace_setting(db_session, test_workspace.id, "k", "v1")
    db_session.commit()
    set_workspace_setting(db_session, test_workspace.id, "k", "v2")
    db_session.commit()
    assert get_workspace_setting(db_session, test_workspace.id, "k") == "v2"
    assert db_session.query(WorkspaceSetting).filter(WorkspaceSetting.key == "k").count() == 1


# -------- cross-scope isolation ----------------------------------------------
# Same key string, different owner -- must never collide. This is the SQLite
# fast-path mirror of the postgres Alice/Bob matrix in
# tests/postgres/test_watchlist_settings_alert_tenancy.py.

def test_same_key_isolated_across_users(db_session, test_user):
    from uuid import uuid4
    other_user_id = uuid4()

    set_user_setting(db_session, test_user.id, "deepseek_model", "a")
    set_user_setting(db_session, other_user_id, "deepseek_model", "b")
    db_session.commit()

    assert get_user_setting(db_session, test_user.id, "deepseek_model") == "a"
    assert get_user_setting(db_session, other_user_id, "deepseek_model") == "b"


def test_same_key_isolated_across_workspaces(db_session, test_workspace):
    from uuid import uuid4
    from models import Workspace

    other_workspace = Workspace(id=uuid4(), name="Other workspace")
    db_session.add(other_workspace)
    db_session.flush()

    set_workspace_setting(db_session, test_workspace.id, "sync_mode", "daily")
    set_workspace_setting(db_session, other_workspace.id, "sync_mode", "weekly")
    db_session.commit()

    assert get_workspace_setting(db_session, test_workspace.id, "sync_mode") == "daily"
    assert get_workspace_setting(db_session, other_workspace.id, "sync_mode") == "weekly"
