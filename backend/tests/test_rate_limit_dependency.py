"""backend/rate_limit.py: the rate_limit(rule_name, by=...) dependency
factory -- edition no-op behavior, identity selection, and its response/
handler pair."""
from __future__ import annotations

from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import Request

# NB: the `rate_limit` factory below is imported by name from the
# `rate_limit` module, so a plain `import rate_limit` would be shadowed by
# it. Alias the module so monkeypatch.setattr targets the module's globals
# (RATE_LIMIT_RULES / consume_rate_limit), not the function object.
import rate_limit as rate_limit_module
from edition import Edition
from rate_limit import (
    InvalidClientIp,
    RateLimitExceeded,
    RateLimitRule,
    RateLimitUnavailable,
    invalid_client_ip_response,
    rate_limit,
    rate_limit_exceeded_response,
    rate_limit_unavailable_response,
)


def _request(edition: Edition, headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "app": Mock(state=Mock(portfyl_edition=edition)),
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    return Request(scope)


class TestByIp:
    def test_noops_in_local_edition(self, monkeypatch):
        consume = Mock()
        monkeypatch.setattr(rate_limit_module, "consume_rate_limit", consume)
        dependency = rate_limit("auth_session", by="ip")
        dependency(_request(Edition.LOCAL))
        consume.assert_not_called()

    def test_calls_consume_rate_limit_with_the_client_ip_in_cloud(self, monkeypatch):
        rule = RateLimitRule(name="auth_session", limit=10, window_seconds=60)
        monkeypatch.setattr(rate_limit_module, "RATE_LIMIT_RULES", {"auth_session": rule})
        consume = Mock()
        monkeypatch.setattr(rate_limit_module, "consume_rate_limit", consume)
        dependency = rate_limit("auth_session", by="ip")

        dependency(_request(Edition.CLOUD, {"CF-Connecting-IP": "203.0.113.9"}))

        consume.assert_called_once_with(rule=rule, identity="203.0.113.9")


class TestByWorkspace:
    def test_noops_in_local_edition(self, monkeypatch):
        consume = Mock()
        monkeypatch.setattr(rate_limit_module, "consume_rate_limit", consume)
        dependency = rate_limit("broker_sync", by="workspace")
        dependency(_request(Edition.LOCAL), context=Mock())
        consume.assert_not_called()

    def test_calls_consume_rate_limit_with_the_workspace_id_in_cloud(self, monkeypatch):
        rule = RateLimitRule(name="broker_sync", limit=5, window_seconds=60)
        monkeypatch.setattr(rate_limit_module, "RATE_LIMIT_RULES", {"broker_sync": rule})
        consume = Mock()
        monkeypatch.setattr(rate_limit_module, "consume_rate_limit", consume)
        workspace_id = uuid4()
        context = Mock(workspace=Mock(id=workspace_id))
        dependency = rate_limit("broker_sync", by="workspace")

        dependency(_request(Edition.CLOUD), context=context)

        consume.assert_called_once_with(rule=rule, identity=str(workspace_id))


def test_unknown_by_value_raises_value_error():
    with pytest.raises(ValueError):
        rate_limit("global", by="user")  # type: ignore[arg-type]


class TestResponseBuilders:
    def test_rate_limit_exceeded_response(self):
        response = rate_limit_exceeded_response(RateLimitExceeded("broker_sync", 7))
        assert response.status_code == 429
        assert response.headers["retry-after"] == "7"
        assert response.headers["cache-control"] == "no-store"

    def test_rate_limit_unavailable_response(self):
        response = rate_limit_unavailable_response(RateLimitUnavailable("global", "OperationalError"))
        assert response.status_code == 503
        assert response.headers["retry-after"] == "1"
        assert response.headers["cache-control"] == "no-store"

    def test_invalid_client_ip_response(self):
        response = invalid_client_ip_response(InvalidClientIp())
        assert response.status_code == 400
        assert response.headers["cache-control"] == "no-store"
