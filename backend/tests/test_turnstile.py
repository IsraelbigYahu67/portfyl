"""backend/turnstile.py: configuration (fail closed) and the siteverify call.

siteverify is always stubbed with `httpx.MockTransport`; nothing here touches
the network."""
from __future__ import annotations

import json
import logging
from urllib.parse import parse_qs

import httpx
import pytest

import turnstile
from edition import Edition
from turnstile import TurnstileConfig, verify_signup_token

REAL_SECRET = "0x4AAAAAAA-real-looking-secret-value-0000"
PASS_SECRET = "1x0000000000000000000000000000000AA"
FAIL_SECRET = "2x0000000000000000000000000000000AA"
APP_URL = "https://app.portfyl.com"
ON = TurnstileConfig(mode="on", secret=REAL_SECRET, hostname="app.portfyl.com")
TEST = TurnstileConfig(mode="test", secret=PASS_SECRET)
GOOD = {"success": True, "action": "signup", "hostname": "app.portfyl.com"}


# --- from_env -----------------------------------------------------------------


def test_local_is_always_off_even_with_a_secret():
    config = TurnstileConfig.from_env({turnstile.SECRET_ENV: REAL_SECRET}, Edition.LOCAL)
    assert config.mode == "off"


def test_cloud_with_a_real_secret_is_on_with_the_app_hostname():
    env = {turnstile.SECRET_ENV: REAL_SECRET, "PORTFYL_APP_URL": APP_URL + "/"}
    config = TurnstileConfig.from_env(env, Edition.CLOUD)
    assert (config.mode, config.secret, config.hostname) == ("on", REAL_SECRET, "app.portfyl.com")


def test_cloud_with_a_secret_needs_the_app_url():
    with pytest.raises(RuntimeError, match="PORTFYL_APP_URL"):
        TurnstileConfig.from_env({turnstile.SECRET_ENV: REAL_SECRET}, Edition.CLOUD)


@pytest.mark.parametrize("secret", [PASS_SECRET, FAIL_SECRET, "3x0000000000000000000000000000000AA"])
def test_dummy_secret_needs_the_test_keys_flag(secret):
    with pytest.raises(RuntimeError, match="TEST_KEYS"):
        TurnstileConfig.from_env({turnstile.SECRET_ENV: secret}, Edition.CLOUD)
    env = {turnstile.SECRET_ENV: secret, turnstile.TEST_KEYS_ENV: "1"}
    assert TurnstileConfig.from_env(env, Edition.CLOUD).mode == "test"


def test_cloud_without_secret_or_disable_flag_refuses_to_start():
    with pytest.raises(RuntimeError, match="PORTFYL_TURNSTILE_SECRET"):
        TurnstileConfig.from_env({}, Edition.CLOUD)
    with pytest.raises(RuntimeError):
        TurnstileConfig.from_env({turnstile.DISABLED_ENV: "0"}, Edition.CLOUD)


def test_explicit_disable_is_off_with_one_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="portfyl.turnstile"):
        config = TurnstileConfig.from_env({turnstile.DISABLED_ENV: "1"}, Edition.CLOUD)
    assert config.mode == "off"
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


def test_secret_together_with_the_disable_flag_is_an_error():
    env = {turnstile.SECRET_ENV: REAL_SECRET, turnstile.DISABLED_ENV: "1", "PORTFYL_APP_URL": APP_URL}
    with pytest.raises(RuntimeError, match="both"):
        TurnstileConfig.from_env(env, Edition.CLOUD)


# --- verify_signup_token ----------------------------------------------------------


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _answer(body, status=200):
    return _client(lambda request: httpx.Response(status, json=body))


def test_success_with_the_right_action_and_hostname():
    assert verify_signup_token(ON, "tok", remote_ip="203.0.113.9", client=_answer(GOOD)) is None


def test_wrong_action_and_wrong_hostname():
    assert verify_signup_token(ON, "tok", remote_ip=None, client=_answer({**GOOD, "action": "login"})) == "wrong_action"
    assert verify_signup_token(ON, "tok", remote_ip=None, client=_answer({**GOOD, "hostname": "evil.example"})) == "wrong_hostname"


def test_rejected_token():
    body = {"success": False, "error-codes": ["invalid-input-response"]}
    assert verify_signup_token(ON, "tok", remote_ip=None, client=_answer(body)) == "rejected"


def test_cloudflare_internal_error_is_unavailable_not_rejected():
    body = {"success": False, "error-codes": ["internal-error"]}
    assert verify_signup_token(ON, "tok", remote_ip=None, client=_answer(body)) == "unavailable"


def test_timeout_network_error_and_bad_responses_are_unavailable():
    def timeout(request):
        raise httpx.ReadTimeout("slow", request=request)

    def refused(request):
        raise httpx.ConnectError("down", request=request)

    assert verify_signup_token(ON, "tok", remote_ip=None, client=_client(timeout)) == "unavailable"
    assert verify_signup_token(ON, "tok", remote_ip=None, client=_client(refused)) == "unavailable"
    assert verify_signup_token(ON, "tok", remote_ip=None, client=_answer({}, status=500)) == "unavailable"
    not_json = _client(lambda request: httpx.Response(200, text="<html>"))
    assert verify_signup_token(ON, "tok", remote_ip=None, client=not_json) == "unavailable"
    assert verify_signup_token(ON, "tok", remote_ip=None, client=_answer(["x"])) == "unavailable"


@pytest.mark.parametrize("token", [None, "", "   ", 5, {"a": 1}])
def test_a_missing_or_non_string_token_never_calls_cloudflare(token):
    def boom(request):
        raise AssertionError("siteverify must not be called")

    assert verify_signup_token(ON, token, remote_ip=None, client=_client(boom)) == "missing_token"


def test_an_oversized_token_is_rejected_without_a_call():
    def boom(request):
        raise AssertionError("siteverify must not be called")

    assert verify_signup_token(ON, "x" * 2049, remote_ip=None, client=_client(boom)) == "rejected"


def test_test_mode_skips_action_and_hostname():
    body = {"success": True, "action": "", "hostname": "example.com"}
    assert verify_signup_token(TEST, "tok", remote_ip=None, client=_answer(body)) is None
    assert verify_signup_token(TEST, "tok", remote_ip=None, client=_answer({"success": False})) == "rejected"


def test_off_mode_passes_without_a_call():
    off = TurnstileConfig(mode="off")
    assert verify_signup_token(off, None, remote_ip=None) is None


def test_request_posts_form_fields_with_the_timeouts():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["form"] = parse_qs(request.content.decode())
        seen["timeout"] = request.extensions["timeout"]
        return httpx.Response(200, json=GOOD)

    assert verify_signup_token(ON, "tok", remote_ip="203.0.113.9", client=_client(handler)) is None
    assert seen["url"] == turnstile.SITEVERIFY_URL
    assert seen["form"] == {"secret": [REAL_SECRET], "response": ["tok"], "remoteip": ["203.0.113.9"]}
    assert seen["timeout"] == {"connect": 3.0, "read": 5.0, "write": 5.0, "pool": 5.0}


def test_remoteip_is_omitted_when_unknown():
    seen = {}

    def handler(request):
        seen["form"] = parse_qs(request.content.decode())
        return httpx.Response(200, json=GOOD)

    verify_signup_token(ON, "tok", remote_ip=None, client=_client(handler))
    assert "remoteip" not in seen["form"]


def test_logs_never_contain_the_token_or_the_secret(caplog):
    token = "very-secret-token-value"
    with caplog.at_level(logging.DEBUG):
        verify_signup_token(ON, token, remote_ip=None, client=_answer({"success": False}))
        verify_signup_token(ON, token, remote_ip=None, client=_answer({}, status=500))
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert token not in text and REAL_SECRET not in text


# --- csp and health ---------------------------------------------------------------


def test_csp_enabled_only_for_cloud_with_a_secret():
    assert turnstile.csp_enabled({"PORTFYL_EDITION": "cloud", turnstile.SECRET_ENV: REAL_SECRET})
    assert not turnstile.csp_enabled({"PORTFYL_EDITION": "cloud"})
    assert not turnstile.csp_enabled({"PORTFYL_EDITION": "local", turnstile.SECRET_ENV: REAL_SECRET})
    assert not turnstile.csp_enabled({})


def test_health_check_reports_the_mode():
    assert turnstile.health_check(ON) == {"status": "ok"}
    assert turnstile.health_check(TEST) == {"status": "test"}
    assert turnstile.health_check(TurnstileConfig(mode="off")) == {"status": "disabled"}
    assert "secret" not in json.dumps(turnstile.health_check(ON))
