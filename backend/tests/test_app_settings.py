"""Tests for the shared AppSetting key/value helpers."""

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app_settings import get_setting, set_setting


def test_get_missing_key_returns_none(db_session):
    assert get_setting(db_session, "nope") is None


def test_set_then_get_roundtrip(db_session):
    set_setting(db_session, "k", "v1")
    db_session.commit()
    assert get_setting(db_session, "k") == "v1"


def test_set_updates_existing_row(db_session):
    set_setting(db_session, "k", "v1")
    db_session.commit()
    set_setting(db_session, "k", "v2")
    db_session.commit()
    assert get_setting(db_session, "k") == "v2"
    # still a single row, not a duplicate key
    from models import AppSetting
    assert db_session.query(AppSetting).filter(AppSetting.key == "k").count() == 1
