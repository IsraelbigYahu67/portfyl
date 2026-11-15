import pytest
from emails.catalog import ENGLISH, EmailKind, LANGUAGES, normalize_language
from emails.render import TemplateError, render

URL = "https://app.portfyl.com/auth/action?mode=verifyEmail&oobCode=abc123&lang=en"

def test_verify_email_english_copy():
    mail = render(EmailKind.VERIFY_EMAIL, "en", params={"email": "jana@example.com"}, action_url=URL)
    assert mail.subject == "Confirm your e-mail for Portfyl"
    assert "<b>jana@example.com</b>" in mail.html
    assert "Confirm e-mail" in mail.html
    assert "One click and your account is ready." in mail.html  # preheader
    assert 'lang="en"' in mail.html

def test_password_reset_english_copy():
    mail = render(EmailKind.PASSWORD_RESET, "en", params={"email": "jana@example.com"}, action_url=URL)
    assert mail.subject == "Reset your Portfyl password"
    assert "Choose a new password" in mail.html
    assert "Your password stays the same." in mail.html

def test_html_hides_the_url_and_text_shows_it():
    mail = render(EmailKind.VERIFY_EMAIL, "en", params={"email": "j@x.cz"}, action_url=URL)
    assert mail.html.count("oobCode=abc123") == 1          # only inside href
    assert 'href="https://app.portfyl.com/auth/action?mode=verifyEmail&amp;oobCode=abc123&amp;lang=en"' in mail.html
    assert URL in mail.text
    assert "<" not in mail.text

@pytest.mark.parametrize("address", ['a<b>"c@x.cz', "jana+test@příklad.cz"])
def test_values_are_escaped(address):
    mail = render(EmailKind.VERIFY_EMAIL, "en", params={"email": address}, action_url=URL)
    assert 'a<b>' not in mail.html
    assert address in mail.text

def test_missing_placeholder_raises():
    with pytest.raises(TemplateError):
        render(EmailKind.VERIFY_EMAIL, "en", params={}, action_url=URL)

def test_button_without_url_raises():
    with pytest.raises(TemplateError):
        render(EmailKind.VERIFY_EMAIL, "en", params={"email": "j@x.cz"})

def test_html_is_small_and_reads_without_images():
    mail = render(EmailKind.PASSWORD_RESET, "en", params={"email": "j@x.cz"}, action_url=URL)
    assert len(mail.html.encode()) < 20_000
    assert 'alt="Portfyl"' in mail.html and 'width="44"' in mail.html
    assert "support@portfyl.com" in mail.html

@pytest.mark.parametrize("raw,expected", [
    ("cs", "cs"), ("CS", "cs"), ("cs-CZ", "cs"), ("xx", "en"), ("", "en"), (None, "en"), ("c" * 500, "en"), (7, "en"),
])
def test_normalize_language(raw, expected):
    assert normalize_language(raw) == expected

def test_english_has_both_kinds():
    assert set(ENGLISH.messages) == set(EmailKind)
    assert "en" in LANGUAGES and len(LANGUAGES) == 9
