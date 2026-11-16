import re
import pytest
from emails.catalog import ENGLISH, EmailKind, LANGUAGES, locale_for
from emails.render import render

PLACEHOLDER = re.compile(r"\{(\w+)\}")

def _shape(content):
    texts = [content.subject, content.preheader, content.heading, *content.paragraphs,
             *content.bullets, *(v for _, v in content.facts), content.note]
    return (len(content.paragraphs), len(content.bullets), len(content.facts),
            content.button is None, content.footer_reason,
            sorted(set(PLACEHOLDER.findall(" ".join(texts)))),
            sum(t.count("**") for t in texts))

@pytest.mark.parametrize("lang", [code for code in LANGUAGES if code != "en"])
def test_locale_matches_english(lang):
    locale = locale_for(lang)
    assert locale is not ENGLISH
    assert set(locale.messages) == set(EmailKind)
    assert set(locale.footer_reasons) == {"account", "address"}
    for kind in EmailKind:
        assert _shape(locale.messages[kind]) == _shape(ENGLISH.messages[kind])
        assert locale.messages[kind].subject != ENGLISH.messages[kind].subject

PARAMS = {"email": "jana@example.com", "date": "16 Dec 2026", "datetime": "16 Nov 2026, 14:05 UTC"}

@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize("kind", list(EmailKind))
def test_every_language_renders(lang, kind):
    mail = render(kind, lang, params=PARAMS, action_url="https://app.portfyl.com/auth/action?x=1")
    assert f'lang="{lang}"' in mail.html and "Portfyl" in mail.subject
    assert "{" not in mail.html and "{" not in mail.text and "**" not in mail.text
    assert "support@portfyl.com" in mail.text

@pytest.mark.parametrize("lang", LANGUAGES)
def test_wave2_values_are_filled_in(lang):
    changed = render(EmailKind.PASSWORD_CHANGED, lang, params=PARAMS, action_url="https://x.test/forgot")
    assert "jana@example.com" in changed.text and PARAMS["datetime"] in changed.text
    scheduled = render(EmailKind.ACCOUNT_DELETION_SCHEDULED, lang, params=PARAMS, action_url="https://x.test/s")
    assert PARAMS["date"] in scheduled.subject and PARAMS["date"] in scheduled.text
    assert "jana@example.com" in scheduled.text
    deleted = render(EmailKind.ACCOUNT_DELETED, lang, params=PARAMS)
    assert "jana@example.com" in deleted.text

@pytest.mark.parametrize("lang", LANGUAGES)
def test_wave2_buttons_and_footer(lang):
    messages = locale_for(lang).messages
    assert messages[EmailKind.PASSWORD_CHANGED].button
    assert messages[EmailKind.ACCOUNT_DELETION_SCHEDULED].button
    assert messages[EmailKind.ACCOUNT_DELETED].button is None
    for kind in (EmailKind.PASSWORD_CHANGED, EmailKind.ACCOUNT_DELETION_SCHEDULED, EmailKind.ACCOUNT_DELETED):
        assert messages[kind].footer_reason == "account"

@pytest.mark.parametrize("lang", [code for code in LANGUAGES if code != "en"])
def test_date_settings_are_complete(lang):
    locale = locale_for(lang)
    assert len(locale.months) == 12 and len(set(locale.months)) == 12
    assert locale.months != ENGLISH.months
    assert {"{day}", "{month}", "{year}"} <= {m for m in re.findall(r"\{\w+\}", locale.date_pattern)}
    assert "{date}" in locale.datetime_pattern and "{time}" in locale.datetime_pattern

def test_czech_wave2_copy_is_the_reviewed_one():
    cs = locale_for("cs").messages
    assert cs[EmailKind.PASSWORD_CHANGED].button == "To jsem nebyl/a já"
    assert cs[EmailKind.ACCOUNT_DELETION_SCHEDULED].subject == "Váš účet Portfyl bude smazán {date}"
    assert cs[EmailKind.ACCOUNT_DELETION_SCHEDULED].facts == (("Účet", "{email}"), ("Smažeme ho", "{date}"))
    assert cs[EmailKind.ACCOUNT_DELETED].paragraphs[1] == "Kdykoli se můžete vrátit a založit si nový."

def test_czech_copy_is_the_reviewed_one():
    cs = locale_for("cs").messages
    assert cs[EmailKind.VERIFY_EMAIL].subject == "Potvrďte svůj e-mail pro Portfyl"
    assert cs[EmailKind.PASSWORD_RESET].button == "Nastavit nové heslo"
