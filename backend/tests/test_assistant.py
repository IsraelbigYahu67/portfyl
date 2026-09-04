"""The DeepSeek AI API key is stored only as an encrypted UserSetting value
(app_settings.get_user_secret/set_user_secret), never plaintext."""
from __future__ import annotations

from models import UserSetting
from routers.assistant import (
    KEY_SETTING,
    ConfigPayload,
    delete_config,
    get_config,
    save_config,
)


class TestAiKeyEncryptedAtRest:
    def test_saved_key_is_not_plaintext_in_the_setting_row(self, db_session, request_context):
        save_config(
            ConfigPayload(api_key="sk-live-1234567890abcdef"),
            db=db_session, request_context=request_context,
        )
        db_session.commit()

        row = db_session.query(UserSetting).filter(
            UserSetting.user_id == request_context.user.id,
            UserSetting.key == KEY_SETTING,
        ).first()
        assert row is not None
        assert "sk-live-1234567890abcdef" not in row.value

    def test_get_config_reports_configured_and_a_masked_preview(self, db_session, request_context):
        save_config(
            ConfigPayload(api_key="sk-live-1234567890abcdef"),
            db=db_session, request_context=request_context,
        )
        db_session.commit()

        result = get_config(db=db_session, request_context=request_context)
        assert result["configured"] is True
        assert "sk-live-1234567890abcdef" not in result["key_preview"]

    def test_delete_config_clears_the_secret(self, db_session, request_context):
        save_config(
            ConfigPayload(api_key="sk-live-1234567890abcdef"),
            db=db_session, request_context=request_context,
        )
        db_session.commit()

        delete_config(db=db_session, request_context=request_context)
        db_session.commit()

        row = db_session.query(UserSetting).filter(
            UserSetting.user_id == request_context.user.id,
            UserSetting.key == KEY_SETTING,
        ).first()
        assert row is None or row.value is None
        assert get_config(db=db_session, request_context=request_context)["configured"] is False
