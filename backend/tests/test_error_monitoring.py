"""configure_sentry()'s opt-in guard and the before_send secret scrub.

Never calls the real sentry_sdk.init() -- these tests monkeypatch it to a
recording stub so no network call is made and no real DSN is needed.
"""
from __future__ import annotations

import sentry_sdk

from error_monitoring import _scrub_event, configure_sentry


class TestConfigureSentryIsOptIn:
    def test_noop_without_sentry_dsn(self, monkeypatch):
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        calls = []
        monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw))
        configure_sentry(environment="local")
        assert calls == []

    def test_noop_under_portfyl_testing_even_with_dsn(self, monkeypatch):
        monkeypatch.setenv("SENTRY_DSN", "https://example.invalid/1")
        monkeypatch.setenv("PORTFYL_TESTING", "1")
        calls = []
        monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw))
        configure_sentry(environment="local")
        assert calls == []

    def test_initializes_with_dsn_outside_testing(self, monkeypatch):
        monkeypatch.setenv("SENTRY_DSN", "https://example.invalid/1")
        monkeypatch.delenv("PORTFYL_TESTING", raising=False)
        calls = []
        monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw))
        configure_sentry(environment="cloud")
        assert len(calls) == 1
        kwargs = calls[0]
        assert kwargs["dsn"] == "https://example.invalid/1"
        assert kwargs["environment"] == "cloud"
        assert kwargs["send_default_pii"] is False
        assert kwargs["max_request_body_size"] == "never"
        assert kwargs["before_send"] is _scrub_event

    def test_sentry_environment_override_wins_over_edition(self, monkeypatch):
        monkeypatch.setenv("SENTRY_DSN", "https://example.invalid/1")
        monkeypatch.setenv("SENTRY_ENVIRONMENT", "staging")
        monkeypatch.delenv("PORTFYL_TESTING", raising=False)
        calls = []
        monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw))
        configure_sentry(environment="cloud")
        assert calls[0]["environment"] == "staging"


class TestScrubEventRedactsKnownSecretShapes:
    def test_redacts_top_level_message(self):
        event = {"message": "session Cookie: __Host-portfyl_session=abc123.def456; Path=/"}
        scrubbed = _scrub_event(event, {})
        assert "abc123.def456" not in scrubbed["message"]

    def test_redacts_logentry_message(self):
        event = {"logentry": {"message": "Authorization: Bearer private-access-token"}}
        scrubbed = _scrub_event(event, {})
        assert "private-access-token" not in scrubbed["logentry"]["message"]

    def test_redacts_exception_values(self):
        event = {"exception": {"values": [{"value": "X-CSRF-Token: super-secret-csrf-value"}]}}
        scrubbed = _scrub_event(event, {})
        assert "super-secret-csrf-value" not in scrubbed["exception"]["values"][0]["value"]

    def test_redacts_breadcrumb_messages(self):
        event = {"breadcrumbs": {"values": [{"message": "posting to https://discord.com/api/webhooks/123456789/super-secret-token"}]}}
        scrubbed = _scrub_event(event, {})
        assert "super-secret-token" not in scrubbed["breadcrumbs"]["values"][0]["message"]

    def test_non_secret_event_is_unchanged(self):
        event = {"message": "workspace=3f2c job=alerts status=ok items=4"}
        assert _scrub_event(event, {}) == event

    def test_missing_fields_do_not_raise(self):
        assert _scrub_event({}, {}) == {}
