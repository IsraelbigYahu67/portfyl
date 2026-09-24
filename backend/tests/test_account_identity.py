from __future__ import annotations

import pytest

from account_identity import account_fingerprint


ENV = {"PORTFYL_ACCOUNT_FINGERPRINT_KEY": "a-fixed-test-secret-with-32-characters"}


def test_account_fingerprint_is_deterministic_and_hides_provider_id():
    first = account_fingerprint(
        broker="trading212", environment="live", provider_account_id=12345, env=ENV,
    )
    second = account_fingerprint(
        broker="Trading212", environment="LIVE", provider_account_id="12345", env=ENV,
    )

    assert first == second
    assert len(first) == 64
    assert "12345" not in first


def test_account_fingerprint_separates_accounts_and_environments():
    live = account_fingerprint(
        broker="trading212", environment="live", provider_account_id=1, env=ENV,
    )
    demo = account_fingerprint(
        broker="trading212", environment="demo", provider_account_id=1, env=ENV,
    )
    other = account_fingerprint(
        broker="trading212", environment="live", provider_account_id=2, env=ENV,
    )

    assert len({live, demo, other}) == 3


@pytest.mark.parametrize("env", [{}, {"PORTFYL_ACCOUNT_FINGERPRINT_KEY": "short"}])
def test_account_fingerprint_fails_closed_without_strong_secret(env):
    with pytest.raises(RuntimeError, match="PORTFYL_ACCOUNT_FINGERPRINT_KEY"):
        account_fingerprint(
            broker="trading212", environment="live", provider_account_id=1, env=env,
        )


def test_account_fingerprint_rejects_missing_provider_id():
    with pytest.raises(ValueError, match="account ID"):
        account_fingerprint(
            broker="trading212", environment="live", provider_account_id=None, env=ENV,
        )
