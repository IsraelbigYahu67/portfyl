import logging
from datetime import date, datetime, timedelta, timezone

import pytest

from emails import notify
from emails.catalog import EmailKind, format_date, format_datetime
from emails.transport import EmailSendError

ADDRESS = "secret.person@example.com"
URL = "https://app.portfyl.com/forgot-password?token=SECRETTOKEN"
WHEN = datetime(2026, 11, 16, 14, 5, tzinfo=timezone.utc)


class FakeTransport:
    def __init__(self, *, available=True, error=None, message_id="msg-1"):
        self._available, self._error, self._message_id = available, error, message_id
        self.sent = []

    def available(self):
        return self._available

    def send(self, *, to, email, tag):
        if self._error is not None:
            raise self._error
        self.sent.append((to, email, tag))
        return self._message_id

    def probe(self):
        return None


class FakeMailer:
    def __init__(self, transport):
        self.transport = transport


@pytest.fixture(autouse=True)
def _no_default_mailer():
    notify.set_default_mailer(None)
    yield
    notify.set_default_mailer(None)


def _send(mailer, kind=EmailKind.PASSWORD_CHANGED, **overrides):
    args = dict(to=ADDRESS, lang="en", params={"email": ADDRESS, "datetime": WHEN}, action_url=URL, mailer=mailer)
    args.update(overrides)
    return notify.send_account_notice(kind, **args)


def test_success_sends_once_with_the_kind_as_tag():
    transport = FakeTransport()
    assert _send(FakeMailer(transport)) is True
    (to, email, tag), = transport.sent
    assert to == ADDRESS and tag == "password_changed"
    assert email.subject == "Your Portfyl password was changed"
    assert "16 November 2026, 14:05 UTC" in email.text and URL in email.text


def test_params_dates_are_formatted_in_the_language():
    transport = FakeTransport()
    assert _send(FakeMailer(transport), lang="cs") is True
    assert "16. listopadu 2026, 14:05 UTC" in transport.sent[0][1].text


def test_scheduled_notice_formats_the_date_for_the_subject():
    transport = FakeTransport()
    ok = notify.send_account_notice(
        EmailKind.ACCOUNT_DELETION_SCHEDULED, to=ADDRESS, lang="de",
        params={"email": ADDRESS, "date": WHEN + timedelta(days=30)},
        action_url="https://app.portfyl.com/settings", mailer=FakeMailer(transport))
    assert ok is True
    assert transport.sent[0][1].subject == "Ihr Portfyl-Konto wird am 16. Dezember 2026 gelöscht"


def test_notice_without_a_button_needs_no_url():
    transport = FakeTransport()
    ok = notify.send_account_notice(
        EmailKind.ACCOUNT_DELETED, to=ADDRESS, lang="en", params={"email": ADDRESS},
        mailer=FakeMailer(transport))
    assert ok is True and transport.sent[0][2] == "account_deleted"


def test_unknown_language_falls_back_to_english():
    transport = FakeTransport()
    assert _send(FakeMailer(transport), lang="xx") is True
    assert transport.sent[0][1].subject == "Your Portfyl password was changed"


def test_mailer_missing_returns_false_and_does_not_raise(monkeypatch):
    monkeypatch.setattr(notify, "_resolve_default_mailer", lambda: None)
    assert _send(None) is False


def test_default_mailer_is_used_when_none_is_passed():
    transport = FakeTransport()
    notify.set_default_mailer(FakeMailer(transport))
    assert _send(None) is True and len(transport.sent) == 1


def test_default_mailer_is_built_once_from_the_environment(monkeypatch):
    calls = []
    transport = FakeTransport()

    def fake_build(env, edition):
        calls.append(1)
        return FakeMailer(transport)

    monkeypatch.setenv("PORTFYL_EDITION", "local")
    monkeypatch.setattr("routers.auth_email.build_mailer", fake_build)
    assert _send(None) is True and _send(None) is True
    assert calls == [1] and len(transport.sent) == 2


def test_a_broken_edition_setting_does_not_raise(monkeypatch):
    monkeypatch.setenv("PORTFYL_EDITION", "nonsense")
    assert _send(None) is False


def test_unavailable_transport_makes_no_send():
    transport = FakeTransport(available=False)
    assert _send(FakeMailer(transport)) is False
    assert transport.sent == []


@pytest.mark.parametrize("error", [
    EmailSendError("brevo_timeout"), EmailSendError("brevo_http_503"), RuntimeError(ADDRESS + URL),
    ValueError("boom"),
])
def test_a_failing_send_returns_false(error):
    assert _send(FakeMailer(FakeTransport(error=error))) is False


def test_a_broken_mailer_object_returns_false():
    assert _send(object()) is False


def test_render_failure_returns_false_and_sends_nothing():
    transport = FakeTransport()
    assert _send(FakeMailer(transport), action_url=None) is False  # button without URL
    assert _send(FakeMailer(transport), params={}) is False        # missing placeholder
    assert transport.sent == []


def test_a_bad_kind_does_not_raise():
    assert notify.send_account_notice("nope", to=ADDRESS, lang="en", params={}, mailer=FakeMailer(FakeTransport())) is False


@pytest.mark.parametrize("transport", [
    FakeTransport(),
    FakeTransport(available=False),
    FakeTransport(error=EmailSendError("brevo_http_500")),
    FakeTransport(error=RuntimeError("to=" + ADDRESS + " url=" + URL)),
])
def test_logs_carry_no_address_link_or_code(transport, caplog):
    caplog.set_level(logging.DEBUG)
    _send(FakeMailer(transport))
    _send(FakeMailer(transport), action_url=None)
    assert "account_notice" in caplog.text  # the lines exist, so this is not vacuous
    for secret in (ADDRESS, "secret.person", "SECRETTOKEN", "forgot-password", "example.com"):
        assert secret not in caplog.text


def test_log_lines_name_the_kind_and_a_reason_only(caplog):
    caplog.set_level(logging.DEBUG)
    _send(FakeMailer(FakeTransport(error=EmailSendError("brevo_http_500"))))
    assert "kind=password_changed lang=en outcome=failed error=brevo_http_500" in caplog.text


def test_a_hostile_send_reason_is_logged_as_a_class_name(caplog):
    caplog.set_level(logging.DEBUG)
    _send(FakeMailer(FakeTransport(error=EmailSendError(ADDRESS))))
    assert ADDRESS not in caplog.text and "error=EmailSendError" in caplog.text


def test_the_helper_is_a_plain_function():
    import inspect

    assert not inspect.iscoroutinefunction(notify.send_account_notice)


# --- date formatting --------------------------------------------------------


@pytest.mark.parametrize("lang,expected", [
    ("en", "16 November 2026"), ("cs", "16. listopadu 2026"), ("de", "16. November 2026"),
    ("fr", "16 novembre 2026"), ("es", "16 de noviembre de 2026"), ("it", "16 novembre 2026"),
    ("pt", "16 de novembro de 2026"), ("pl", "16 listopada 2026"), ("nl", "16 november 2026"),
])
def test_format_date_per_language(lang, expected):
    assert format_date(WHEN, lang) == expected
    assert format_date(date(2026, 11, 16), lang) == expected


def test_format_datetime_is_utc_and_zero_padded():
    assert format_datetime(WHEN, "en") == "16 November 2026, 14:05 UTC"
    local = datetime(2026, 11, 17, 0, 7, tzinfo=timezone(timedelta(hours=2)))
    assert format_datetime(local, "en") == "16 November 2026, 22:07 UTC"
    assert format_datetime(datetime(2026, 3, 1, 9, 3), "cs") == "1. března 2026, 09:03 UTC"
    assert format_datetime(WHEN, "xx") == format_datetime(WHEN, "en")
