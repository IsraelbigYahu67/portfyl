import pytest
from html import escape
from urllib.parse import parse_qs, urlsplit
from firebase_admin import exceptions
from emails.catalog import EmailKind
from emails.links import AccountNotFound, ActionLinkBuilder, ActionLinkError
from emails.render import render

FIREBASE_LINK = "https://portfyl-cloud-fstxby.firebaseapp.com/__/auth/action?mode=verifyEmail&oobCode=CODE-1_x&apiKey=k&lang=en"

class FakeAuth:
    def __init__(self, result=FIREBASE_LINK, error=None): self.result, self.error, self.calls = result, error, []
    def _call(self, name, email, action_code_settings, app):
        self.calls.append((name, email, action_code_settings.url))
        if self.error: raise self.error
        return self.result
    def generate_email_verification_link(self, email, action_code_settings=None, app=None):
        return self._call("verify", email, action_code_settings, app)
    def generate_password_reset_link(self, email, action_code_settings=None, app=None):
        return self._call("reset", email, action_code_settings, app)

def _builder(auth): return ActionLinkBuilder(app_url="https://app.portfyl.com", auth_client=auth, app=object())

# The parameters travel in the fragment: a browser never sends it to a server,
# so the one-time code stays out of Cloud Run and Cloudflare request logs.

def test_verification_url():
    auth = FakeAuth()
    url = urlsplit(_builder(auth).verification_url("jana@example.com", "cs"))
    assert (url.scheme, url.netloc, url.path) == ("https", "app.portfyl.com", "/auth/action")
    assert url.query == ""
    assert parse_qs(url.fragment) == {"mode": ["verifyEmail"], "oobCode": ["CODE-1_x"], "lang": ["cs"],
                                      "continueUrl": ["https://app.portfyl.com/login?verified=1"]}
    assert auth.calls == [("verify", "jana@example.com", "https://app.portfyl.com/login?verified=1")]

def test_password_reset_url_has_no_continue_url():
    url = urlsplit(_builder(FakeAuth()).password_reset_url("jana@example.com", "en"))
    assert url.query == ""
    assert parse_qs(url.fragment) == {"mode": ["resetPassword"], "oobCode": ["CODE-1_x"], "lang": ["en"]}

def test_the_parameters_keep_their_order_and_nothing_reaches_the_server_part():
    url = _builder(FakeAuth()).verification_url("jana@example.com", "cs")
    assert url == ("https://app.portfyl.com/auth/action#mode=verifyEmail&oobCode=CODE-1_x&lang=cs"
                   "&continueUrl=https%3A%2F%2Fapp.portfyl.com%2Flogin%3Fverified%3D1")
    server_part = url.split("#", 1)[0]
    assert server_part == "https://app.portfyl.com/auth/action"
    assert "CODE-1_x" not in server_part and "?" not in url

@pytest.mark.parametrize("kind,build", [
    (EmailKind.VERIFY_EMAIL, lambda b: b.verification_url("jana@example.com", "en")),
    (EmailKind.PASSWORD_RESET, lambda b: b.password_reset_url("jana@example.com", "en")),
])
def test_the_e_mail_carries_the_fragment_link(kind, build):
    url = build(_builder(FakeAuth()))
    email = render(kind, "en", params={"email": "jana@example.com"}, action_url=url)
    assert url in email.text  # plain text: the full link, fragment included
    in_html = escape(url, quote=True)
    assert f'href="{in_html}"' in email.html
    assert email.html.count(in_html) == 1  # only as the button's target, never as visible text
    assert "CODE-1_x" not in email.html.replace(in_html, "")

def test_missing_user_is_account_not_found():
    with pytest.raises(AccountNotFound):
        _builder(FakeAuth(error=exceptions.NotFoundError("EMAIL_NOT_FOUND jana@example.com"))).password_reset_url("jana@example.com", "en")

@pytest.mark.parametrize("auth", [FakeAuth(result="https://x.firebaseapp.com/__/auth/action?mode=verifyEmail"),
                                  FakeAuth(error=RuntimeError("boom jana@example.com"))])
def test_other_failures_do_not_leak(auth):
    with pytest.raises(ActionLinkError) as info:
        _builder(auth).verification_url("jana@example.com", "en")
    assert not isinstance(info.value, AccountNotFound)
    assert "jana@example.com" not in str(info.value) and "firebaseapp" not in str(info.value)
