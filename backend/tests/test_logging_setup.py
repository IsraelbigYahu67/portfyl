"""Secret redaction and correlation-id stamping. Tests the formatter/filter
building blocks directly rather than calling configure_logging() (a no-op
under PORTFYL_TESTING, and mutating the root logger's handlers would break
pytest's own log capture for every other test module)."""
from __future__ import annotations

import logging

from logging_setup import RedactingFormatter, _CorrelationIdFilter, correlation_id_var, redact


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord(
        name="portfyl.test", level=logging.INFO, pathname=__file__, lineno=1,
        msg=message, args=(), exc_info=None,
    )


class TestRedactsKnownSecretShapes:
    def test_discord_webhook_url_token_is_redacted(self):
        line = "posting to https://discord.com/api/webhooks/123456789/super-secret-token-value"
        redacted = redact(line)
        assert "super-secret-token-value" not in redacted
        assert "discord.com/api/webhooks/" in redacted  # shape stays legible

    def test_authorization_header_is_redacted(self):
        line = 'sending headers {"Authorization": "Bearer private-access-token"}'
        redacted = redact(line)
        assert "private-access-token" not in redacted
        assert "Authorization" in redacted

    def test_session_cookie_value_is_redacted(self):
        line = "Cookie: __Host-portfyl_session=abc123.def456.ghi789; Path=/"
        redacted = redact(line)
        assert "abc123.def456.ghi789" not in redacted
        assert "portfyl_session=" in redacted

    def test_csrf_token_header_is_redacted(self):
        line = "X-CSRF-Token: super-secret-csrf-value-1234"
        redacted = redact(line)
        assert "super-secret-csrf-value-1234" not in redacted

    def test_stripe_keys_and_webhook_secrets_are_redacted(self):
        line = "key=sk_live_51AbCdEf restricted=rk_test_9xYz signing=whsec_Q1w2E3"
        redacted = redact(line)
        for secret in ("51AbCdEf", "9xYz", "Q1w2E3"):
            assert secret not in redacted
        assert "sk_live_[REDACTED]" in redacted

    def test_ibkr_flex_token_in_url_is_redacted(self):
        line = ('HTTP Request: GET https://gdcdyn.interactivebrokers.com/Universal/servlet/'
                'FlexStatementService.SendRequest?t=123456789012345678901234&q=1519214&v=3 "200 OK"')
        redacted = redact(line)
        assert "123456789012345678901234" not in redacted
        assert "SendRequest?t=[REDACTED]&q=1519214" in redacted
        get = "FlexStatementService.GetStatement?q=999&t=123456789012345678901234&v=3"
        assert "123456789012345678901234" not in redact(get)

    def test_non_secret_context_is_preserved(self):
        line = "autosync pass: workspace=3f2c job=alerts status=ok items=4"
        assert redact(line) == line


class TestFormatterAppliesRedaction:
    def test_format_redacts_the_rendered_message(self):
        formatter = RedactingFormatter("%(message)s")
        record = _record("token leaked: Authorization: Bearer private-access-token")
        output = formatter.format(record)
        assert "private-access-token" not in output


class TestCorrelationIdFilter:
    def test_filter_stamps_the_current_correlation_id(self):
        token = correlation_id_var.set("job-alerts-abc123")
        try:
            record = _record("hello")
            assert _CorrelationIdFilter().filter(record) is True
            assert record.correlation_id == "job-alerts-abc123"
        finally:
            correlation_id_var.reset(token)

    def test_default_correlation_id_outside_any_context(self):
        record = _record("hello")
        assert _CorrelationIdFilter().filter(record) is True
        assert record.correlation_id == "-"
