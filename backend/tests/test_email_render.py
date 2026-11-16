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

def test_english_has_every_kind():
    assert set(ENGLISH.messages) == set(EmailKind)
    assert len(EmailKind) == 5
    assert "en" in LANGUAGES and len(LANGUAGES) == 9

W2 = {"email": "jana@example.com", "date": "16 December 2026", "datetime": "16 November 2026, 14:05 UTC"}

def test_password_changed_english_copy():
    mail = render(EmailKind.PASSWORD_CHANGED, "en", params=W2, action_url="https://app.portfyl.com/forgot-password")
    assert mail.subject == "Your Portfyl password was changed"
    assert "<b>jana@example.com</b>" in mail.html
    assert "When" in mail.html and "16 November 2026, 14:05 UTC" in mail.html
    assert "That wasn&#x27;t me" in mail.html
    assert "You got this e-mail because it is about your Portfyl account." in mail.html
    assert "When: 16 November 2026, 14:05 UTC" in mail.text

def test_deletion_scheduled_english_copy():
    mail = render(EmailKind.ACCOUNT_DELETION_SCHEDULED, "en", params=W2, action_url="https://app.portfyl.com/settings")
    assert mail.subject == "Your Portfyl account will be deleted on 16 December 2026"
    assert "Account: jana@example.com" in mail.text
    assert "We delete it on: 16 December 2026" in mail.text
    assert "Keep my account" in mail.html

def test_account_deleted_has_no_button_and_needs_no_url():
    mail = render(EmailKind.ACCOUNT_DELETED, "en", params={"email": "jana@example.com"})
    assert mail.subject == "Your Portfyl account has been deleted"
    assert "<a href" not in mail.html.replace('<a href="mailto:', "")
    assert "<b>jana@example.com</b>" in mail.html
    assert "come back and start a new one" in mail.text
    assert "http" not in mail.text

@pytest.mark.parametrize("kind", [EmailKind.PASSWORD_CHANGED, EmailKind.ACCOUNT_DELETION_SCHEDULED])
def test_wave2_button_without_url_raises(kind):
    with pytest.raises(TemplateError):
        render(kind, "en", params=W2)

@pytest.mark.parametrize("kind", [EmailKind.PASSWORD_CHANGED, EmailKind.ACCOUNT_DELETION_SCHEDULED, EmailKind.ACCOUNT_DELETED])
def test_wave2_missing_placeholder_raises(kind):
    with pytest.raises(TemplateError):
        render(kind, "en", params={}, action_url="https://app.portfyl.com/x")

@pytest.mark.parametrize("kind", [EmailKind.PASSWORD_CHANGED, EmailKind.ACCOUNT_DELETION_SCHEDULED, EmailKind.ACCOUNT_DELETED])
def test_wave2_values_are_escaped(kind):
    mail = render(kind, "en", params={**W2, "email": 'a<b>"c@x.cz'}, action_url="https://app.portfyl.com/x")
    assert "a<b>" not in mail.html
    assert 'a<b>"c@x.cz' in mail.text

@pytest.mark.parametrize("kind", [EmailKind.PASSWORD_CHANGED, EmailKind.ACCOUNT_DELETION_SCHEDULED, EmailKind.ACCOUNT_DELETED])
def test_wave2_html_is_small(kind):
    mail = render(kind, "en", params=W2, action_url="https://app.portfyl.com/x")
    assert len(mail.html.encode()) < 20_000
