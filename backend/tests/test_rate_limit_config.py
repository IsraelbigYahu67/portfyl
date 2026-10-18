"""backend/rate_limit.py: rule config parsing and the two cloud-only
module-level globals it feeds (RATE_LIMIT_RULES, KEY_SECRET)."""
from __future__ import annotations

import pytest

import rate_limit
from rate_limit import RateLimitRule, load_key_secret, load_rate_limit_rules

VALID_CLOUD_ENV = {
    "PORTFYL_EDITION": "cloud",
    "RATE_LIMIT_GLOBAL_LIMIT": "120",
    "RATE_LIMIT_GLOBAL_WINDOW_SECONDS": "60",
    "RATE_LIMIT_AUTH_SESSION_LIMIT": "10",
    "RATE_LIMIT_AUTH_SESSION_WINDOW_SECONDS": "60",
    "RATE_LIMIT_BROKER_SYNC_LIMIT": "5",
    "RATE_LIMIT_BROKER_SYNC_WINDOW_SECONDS": "60",
}


def test_load_rate_limit_rules_returns_all_three_rules_when_valid():
    rules = load_rate_limit_rules(VALID_CLOUD_ENV)
    assert set(rules) == {"global", "auth_session", "broker_sync"}
    assert rules["global"] == RateLimitRule(name="global", limit=120, window_seconds=60)
    assert rules["broker_sync"] == RateLimitRule(name="broker_sync", limit=5, window_seconds=60)


@pytest.mark.parametrize("bad_value", ["", "0", "-1", "not-a-number", "  "])
def test_load_rate_limit_rules_rejects_bad_limit(bad_value):
    env = {**VALID_CLOUD_ENV, "RATE_LIMIT_GLOBAL_LIMIT": bad_value}
    with pytest.raises(RuntimeError, match="RATE_LIMIT_GLOBAL_LIMIT"):
        load_rate_limit_rules(env)


@pytest.mark.parametrize("bad_value", ["", "0", "-5", "soon"])
def test_load_rate_limit_rules_rejects_bad_window(bad_value):
    env = {**VALID_CLOUD_ENV, "RATE_LIMIT_BROKER_SYNC_WINDOW_SECONDS": bad_value}
    with pytest.raises(RuntimeError, match="RATE_LIMIT_BROKER_SYNC_WINDOW_SECONDS"):
        load_rate_limit_rules(env)


def test_load_key_secret_rejects_blank():
    with pytest.raises(RuntimeError, match="RATE_LIMIT_KEY_SECRET"):
        load_key_secret({"RATE_LIMIT_KEY_SECRET": "  "})


def test_load_key_secret_rejects_missing():
    with pytest.raises(RuntimeError, match="RATE_LIMIT_KEY_SECRET"):
        load_key_secret({})


def test_load_key_secret_returns_bytes_when_set():
    assert load_key_secret({"RATE_LIMIT_KEY_SECRET": "abc123"}) == b"abc123"


def test_rate_limit_rule_rejects_non_positive_limit():
    with pytest.raises(ValueError):
        RateLimitRule(name="x", limit=0, window_seconds=60)


def test_rate_limit_rule_rejects_non_positive_window():
    with pytest.raises(ValueError):
        RateLimitRule(name="x", limit=1, window_seconds=0)


def test_local_edition_module_level_globals_are_empty():
    # The whole fast suite boots under PORTFYL_EDITION=local (tests/conftest.py);
    # rate_limit.py must never have parsed cloud-only config as a result.
    assert rate_limit.RATE_LIMIT_RULES == {}
    assert rate_limit.KEY_SECRET is None
