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

@pytest.mark.parametrize("lang", LANGUAGES)
@pytest.mark.parametrize("kind", list(EmailKind))
def test_every_language_renders(lang, kind):
    mail = render(kind, lang, params={"email": "jana@example.com"}, action_url="https://app.portfyl.com/auth/action?x=1")
    assert f'lang="{lang}"' in mail.html and "Portfyl" in mail.subject

def test_czech_copy_is_the_reviewed_one():
    cs = locale_for("cs").messages
    assert cs[EmailKind.VERIFY_EMAIL].subject == "Potvrďte svůj e-mail pro Portfyl"
    assert cs[EmailKind.PASSWORD_RESET].button == "Nastavit nové heslo"
