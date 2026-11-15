import io
import json
import logging

import httpx
import pytest

from edition import Edition
from emails.transport import (
    COOLDOWN_SECONDS,
    BrevoTransport,
    ConsoleTransport,
    EmailSendError,
    MailerSettings,
    load_mailer_settings,
)

SETTINGS = MailerSettings(api_key="xkeysib-secret", sender_email="noreply@mail.portfyl.com",
                          sender_name="Portfyl", reply_to="support@portfyl.com",
                          app_url="https://app.portfyl.com", console=False)


class Mail:  # stands in for RenderedEmail
    subject, html, text = "S", "<p>H</p>", "T"


def _transport(handler, clock=lambda: 0.0):
    return BrevoTransport(SETTINGS, client=httpx.Client(transport=httpx.MockTransport(handler)), clock=clock)


def test_request_shape_and_message_id():
    seen = {}

    def handler(request):
        seen["headers"], seen["json"] = request.headers, json.loads(request.content)
        return httpx.Response(201, json={"messageId": "<m1>"})

    assert _transport(handler).send(to="jana@example.com", email=Mail, tag="verify_email") == "<m1>"
    assert seen["headers"]["api-key"] == "xkeysib-secret"
    assert seen["json"] == {
        "sender": {"email": "noreply@mail.portfyl.com", "name": "Portfyl"},
        "to": [{"email": "jana@example.com"}],
        "replyTo": {"email": "support@portfyl.com", "name": "Portfyl"},
        "subject": "S", "htmlContent": "<p>H</p>", "textContent": "T", "tags": ["verify_email"],
    }


def test_201_without_message_id_is_success():
    assert _transport(lambda r: httpx.Response(201, json={})).send(to="a@b.cz", email=Mail, tag="t") is None


def test_201_with_unreadable_body_is_success():
    assert _transport(lambda r: httpx.Response(201, content=b"not json")).send(to="a@b.cz", email=Mail, tag="t") is None


def test_posts_to_the_brevo_url_with_the_documented_timeouts():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["timeout"] = request.extensions["timeout"]
        return httpx.Response(201, json={})

    _transport(handler).send(to="a@b.cz", email=Mail, tag="t")
    assert seen["url"] == "https://api.brevo.com/v3/smtp/email"
    assert seen["timeout"] == {"connect": 3.0, "read": 5.0, "write": 5.0, "pool": 5.0}


def test_unusual_address_is_sent_to_the_exact_address():
    seen = {}

    def handler(request):
        seen["json"] = json.loads(request.content)
        return httpx.Response(201, json={})

    _transport(handler).send(to='a<b>"c@příklad.cz', email=Mail, tag="t")
    assert seen["json"]["to"] == [{"email": 'a<b>"c@příklad.cz'}]


@pytest.mark.parametrize("status", [400, 401, 429, 500])
def test_http_error_raises_without_leaking(status):
    with pytest.raises(EmailSendError) as info:
        _transport(lambda r: httpx.Response(status, json={"message": "xkeysib-secret a@b.cz"})).send(to="a@b.cz", email=Mail, tag="t")
    assert str(info.value) == f"brevo_http_{status}"


def test_timeout_raises():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(EmailSendError, match="brevo_timeout"):
        _transport(handler).send(to="a@b.cz", email=Mail, tag="t")


def test_network_error_raises_a_reason_code_only():
    def handler(request):
        raise httpx.ConnectError("boom xkeysib-secret a@b.cz", request=request)

    with pytest.raises(EmailSendError) as info:
        _transport(handler).send(to="a@b.cz", email=Mail, tag="t")
    assert str(info.value) == "brevo_network"
    assert info.value.__cause__ is None


def test_auth_failure_switches_off_for_the_cooldown():
    now = [0.0]
    transport = _transport(lambda r: httpx.Response(401), clock=lambda: now[0])
    assert transport.available()
    with pytest.raises(EmailSendError):
        transport.send(to="a@b.cz", email=Mail, tag="t")
    assert not transport.available()
    now[0] = COOLDOWN_SECONDS + 1
    assert transport.available()


def test_forbidden_also_switches_off_at_once():
    transport = _transport(lambda r: httpx.Response(403))
    with pytest.raises(EmailSendError):
        transport.send(to="a@b.cz", email=Mail, tag="t")
    assert not transport.available()


def test_three_failures_in_a_row_switch_off_and_a_success_resets():
    answers = iter([500, 500, 201, 500, 500, 500])
    transport = _transport(lambda r: httpx.Response(next(answers), json={}))
    for expect_ok in (False, False, True, False, False):
        try:
            transport.send(to="a@b.cz", email=Mail, tag="t")
        except EmailSendError:
            assert not expect_ok
        assert transport.available()
    with pytest.raises(EmailSendError):
        transport.send(to="a@b.cz", email=Mail, tag="t")
    assert not transport.available()


@pytest.mark.parametrize("status", [400, 404, 422])
def test_a_rejected_request_never_switches_the_mailer_off(status):
    # Brevo answered and the key works: it refused this one message (for
    # example an address it will not accept). A caller who can cause that must
    # not be able to switch e-mail off for everyone.
    transport = _transport(lambda r: httpx.Response(status, json={}))
    for _ in range(10):
        with pytest.raises(EmailSendError, match=f"brevo_http_{status}"):
            transport.send(to="a@b.cz", email=Mail, tag="t")
        assert transport.available()


def test_rejected_requests_do_not_hide_a_real_outage():
    answers = iter([500, 400, 500, 400, 500])
    transport = _transport(lambda r: httpx.Response(next(answers), json={}))
    for _ in range(4):
        with pytest.raises(EmailSendError):
            transport.send(to="a@b.cz", email=Mail, tag="t")
        assert transport.available()
    with pytest.raises(EmailSendError):
        transport.send(to="a@b.cz", email=Mail, tag="t")
    assert not transport.available()


def test_three_rate_limited_answers_in_a_row_switch_off():
    transport = _transport(lambda r: httpx.Response(429, json={}))
    for _ in range(3):
        with pytest.raises(EmailSendError):
            transport.send(to="a@b.cz", email=Mail, tag="t")
    assert not transport.available()


def test_three_hangs_in_a_row_switch_off():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    transport = _transport(handler)
    for _ in range(3):
        assert transport.available()
        with pytest.raises(EmailSendError):
            transport.send(to="a@b.cz", email=Mail, tag="t")
    assert not transport.available()


def test_one_failure_after_the_cooldown_does_not_switch_off_again():
    now = [0.0]
    transport = _transport(lambda r: httpx.Response(500), clock=lambda: now[0])
    for _ in range(3):
        with pytest.raises(EmailSendError):
            transport.send(to="a@b.cz", email=Mail, tag="t")
    assert not transport.available()
    now[0] = COOLDOWN_SECONDS + 1
    assert transport.available()
    with pytest.raises(EmailSendError):
        transport.send(to="a@b.cz", email=Mail, tag="t")
    assert transport.available()


def test_switching_off_logs_a_reason_code_and_nothing_secret(caplog):
    transport = _transport(lambda r: httpx.Response(401, json={"message": "xkeysib-secret a@b.cz"}))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(EmailSendError):
            transport.send(to="a@b.cz", email=Mail, tag="t")
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "xkeysib-secret" not in text and "a@b.cz" not in text


def test_console_transport_prints_subject_and_text():
    out = io.StringIO()
    transport = ConsoleTransport(out=out)
    assert transport.available()
    transport.send(to="a@b.cz", email=Mail, tag="t")
    assert "S" in out.getvalue() and "T" in out.getvalue()


@pytest.mark.parametrize("env,edition,expected", [
    ({}, Edition.CLOUD, None),
    ({"PORTFYL_BREVO_API_KEY": "k"}, Edition.CLOUD, None),                                             # no app URL
    ({"PORTFYL_BREVO_API_KEY": "k", "PORTFYL_EMAIL_APP_URL": "http://app.portfyl.com"}, Edition.CLOUD, None),
    ({"PORTFYL_BREVO_API_KEY": "k", "PORTFYL_EMAIL_APP_URL": "https://app.portfyl.com/"}, Edition.CLOUD, "https://app.portfyl.com"),
    ({"PORTFYL_EMAIL_TRANSPORT": "console", "PORTFYL_BREVO_API_KEY": "k", "PORTFYL_EMAIL_APP_URL": "https://a.b"}, Edition.CLOUD, "https://a.b"),
    ({"PORTFYL_EMAIL_TRANSPORT": "console"}, Edition.LOCAL, "http://localhost:5173"),
    ({}, Edition.LOCAL, None),
])
def test_load_mailer_settings(env, edition, expected):
    settings = load_mailer_settings(env, edition)
    assert (settings.app_url if settings else None) == expected
    if settings and edition is Edition.CLOUD:
        assert settings.console is False


def test_cloud_settings_use_the_documented_defaults():
    settings = load_mailer_settings(
        {"PORTFYL_BREVO_API_KEY": "k", "PORTFYL_EMAIL_APP_URL": "https://app.portfyl.com"}, Edition.CLOUD)
    assert settings == MailerSettings(
        api_key="k", sender_email="noreply@mail.portfyl.com", sender_name="Portfyl",
        reply_to="support@portfyl.com", app_url="https://app.portfyl.com", console=False)


def test_cloud_settings_take_overrides_and_trim_whitespace():
    settings = load_mailer_settings({
        "PORTFYL_BREVO_API_KEY": " k ", "PORTFYL_EMAIL_APP_URL": " https://app.portfyl.com// ",
        "PORTFYL_EMAIL_FROM": "hi@x.cz", "PORTFYL_EMAIL_FROM_NAME": "X", "PORTFYL_EMAIL_REPLY_TO": "r@x.cz",
    }, Edition.CLOUD)
    assert (settings.api_key, settings.app_url, settings.sender_email, settings.sender_name, settings.reply_to) == (
        "k", "https://app.portfyl.com", "hi@x.cz", "X", "r@x.cz")


def test_local_with_a_key_and_no_console_uses_brevo():
    settings = load_mailer_settings({"PORTFYL_BREVO_API_KEY": "k"}, Edition.LOCAL)
    assert settings.api_key == "k" and settings.console is False
    assert settings.app_url == "http://localhost:5173"


def test_local_console_has_no_key_needed():
    settings = load_mailer_settings({"PORTFYL_EMAIL_TRANSPORT": "console"}, Edition.LOCAL)
    assert settings.console is True and settings.api_key is None


def test_a_key_with_unusable_settings_logs_one_error_without_the_key(caplog):
    env = {"PORTFYL_BREVO_API_KEY": "xkeysib-secret", "PORTFYL_EMAIL_APP_URL": "http://app.portfyl.com"}
    with caplog.at_level(logging.DEBUG):
        assert load_mailer_settings(env, Edition.CLOUD) is None
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert "xkeysib-secret" not in errors[0].getMessage()


def test_no_key_is_the_normal_state_and_logs_no_error(caplog):
    with caplog.at_level(logging.DEBUG):
        assert load_mailer_settings({}, Edition.CLOUD) is None
        assert load_mailer_settings({}, Edition.LOCAL) is None
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


class _ExplodingEnv(dict):
    def get(self, *args, **kwargs):
        raise RuntimeError("boom")


@pytest.mark.parametrize("env", [
    _ExplodingEnv(),
    {"PORTFYL_BREVO_API_KEY": None, "PORTFYL_EMAIL_APP_URL": None},
    {"PORTFYL_BREVO_API_KEY": "k", "PORTFYL_EMAIL_APP_URL": "https://[::1"},
    {"PORTFYL_BREVO_API_KEY": "k", "PORTFYL_EMAIL_APP_URL": "https://"},
])
@pytest.mark.parametrize("edition", [Edition.CLOUD, Edition.LOCAL])
def test_load_mailer_settings_never_raises(env, edition):
    load_mailer_settings(env, edition)
