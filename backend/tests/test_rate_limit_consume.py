"""backend/rate_limit.py: client_ip() validation and consume_rate_limit()'s
race-free upsert, transaction boundary, and fixed-window arithmetic."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

import rate_limit
from rate_limit import (
    InvalidClientIp,
    RateLimitExceeded,
    RateLimitRule,
    RateLimitUnavailable,
    client_ip,
    consume_rate_limit,
)


def _request(headers: dict[str, str] | list[tuple[str, str]]):
    if isinstance(headers, dict):
        headers = list(headers.items())
    from starlette.requests import Request

    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
    }
    return Request(scope)


class TestClientIp:
    def test_accepts_canonical_ipv4(self):
        assert client_ip(_request({"CF-Connecting-IP": "203.0.113.9"})) == "203.0.113.9"

    def test_canonicalizes_ipv6(self):
        expanded = _request({"CF-Connecting-IP": "2001:0db8:0000:0000:0000:0000:0000:0001"})
        compressed = _request({"CF-Connecting-IP": "2001:db8::1"})
        assert client_ip(expanded) == client_ip(compressed)

    def test_rejects_missing_header(self):
        with pytest.raises(InvalidClientIp):
            client_ip(_request({}))

    def test_rejects_duplicated_header(self):
        req = _request([("CF-Connecting-IP", "203.0.113.9"), ("CF-Connecting-IP", "198.51.100.4")])
        with pytest.raises(InvalidClientIp):
            client_ip(req)

    def test_rejects_comma_separated_value(self):
        with pytest.raises(InvalidClientIp):
            client_ip(_request({"CF-Connecting-IP": "203.0.113.9, 198.51.100.4"}))

    def test_rejects_overlong_value(self):
        with pytest.raises(InvalidClientIp):
            client_ip(_request({"CF-Connecting-IP": "2001:db8::1" + "0" * 60}))

    def test_rejects_garbage(self):
        with pytest.raises(InvalidClientIp):
            client_ip(_request({"CF-Connecting-IP": "not-an-ip"}))


@pytest.fixture(autouse=True)
def _consume_env(monkeypatch, db_session):
    monkeypatch.setattr(rate_limit, "SessionLocal", lambda: db_session)
    monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")


class TestConsumeRateLimit:
    RULE = RateLimitRule(name="test_rule", limit=2, window_seconds=60)
    NOW = datetime(2026, 1, 1, 0, 0, 30, tzinfo=timezone.utc)

    def test_nth_succeeds_and_n_plus_1_is_exceeded_with_retry_after(self):
        consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)
        consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)
        with pytest.raises(RateLimitExceeded) as exc_info:
            consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)
        assert exc_info.value.rule_name == "test_rule"
        assert exc_info.value.retry_after_seconds >= 1

    def test_repeated_denied_requests_remain_denied(self):
        for _ in range(2):
            consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)
        for _ in range(3):
            with pytest.raises(RateLimitExceeded):
                consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)

    def test_distinct_identities_use_distinct_buckets(self):
        consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)
        consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)
        consume_rate_limit(rule=self.RULE, identity="bob", now=self.NOW)  # bob's own bucket, not exceeded

    def test_bucket_persists_across_a_later_rollback_on_the_same_session(self, db_session):
        consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)  # commits internally
        db_session.rollback()  # simulates the route's own later rollback
        consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)
        with pytest.raises(RateLimitExceeded):
            consume_rate_limit(rule=self.RULE, identity="alice", now=self.NOW)

    def test_minimum_retry_after_is_one_second(self):
        # now sits 59.9s into a 60s window -- expires_at - now < 1s, must clamp up.
        just_before_boundary = datetime(2026, 1, 1, 0, 0, 59, 900000, tzinfo=timezone.utc)
        consume_rate_limit(rule=self.RULE, identity="carol", now=just_before_boundary)
        consume_rate_limit(rule=self.RULE, identity="carol", now=just_before_boundary)
        with pytest.raises(RateLimitExceeded) as exc_info:
            consume_rate_limit(rule=self.RULE, identity="carol", now=just_before_boundary)
        assert exc_info.value.retry_after_seconds == 1

    def test_new_window_resets_the_count(self):
        rule = RateLimitRule(name="test_window", limit=1, window_seconds=60)
        first_window = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        second_window = datetime(2026, 1, 1, 0, 1, 0, tzinfo=timezone.utc)
        consume_rate_limit(rule=rule, identity="dave", now=first_window)
        with pytest.raises(RateLimitExceeded):
            consume_rate_limit(rule=rule, identity="dave", now=first_window)
        consume_rate_limit(rule=rule, identity="dave", now=second_window)  # new window, not exceeded

    def test_db_error_raises_rate_limiter_unavailable(self, monkeypatch):
        class _BrokenSession:
            def execute(self, *args, **kwargs):
                raise SQLAlchemyError("boom")

            def rollback(self):
                pass

            def close(self):
                pass

        monkeypatch.setattr(rate_limit, "SessionLocal", lambda: _BrokenSession())
        with pytest.raises(RateLimitUnavailable) as exc_info:
            consume_rate_limit(rule=self.RULE, identity="erin", now=self.NOW)
        assert exc_info.value.rule_name == "test_rule"
        assert exc_info.value.original_exception_type == "SQLAlchemyError"
