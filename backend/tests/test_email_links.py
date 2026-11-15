import pytest
from urllib.parse import parse_qs, urlparse
from firebase_admin import exceptions
from emails.links import AccountNotFound, ActionLinkBuilder, ActionLinkError

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

def test_verification_url():
    auth = FakeAuth()
    url = urlparse(_builder(auth).verification_url("jana@example.com", "cs"))
    assert (url.scheme, url.netloc, url.path) == ("https", "app.portfyl.com", "/auth/action")
    assert parse_qs(url.query) == {"mode": ["verifyEmail"], "oobCode": ["CODE-1_x"], "lang": ["cs"],
                                   "continueUrl": ["https://app.portfyl.com/login?verified=1"]}
    assert auth.calls == [("verify", "jana@example.com", "https://app.portfyl.com/login?verified=1")]

def test_password_reset_url_has_no_continue_url():
    query = parse_qs(urlparse(_builder(FakeAuth()).password_reset_url("jana@example.com", "en")).query)
    assert query == {"mode": ["resetPassword"], "oobCode": ["CODE-1_x"], "lang": ["en"]}

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
