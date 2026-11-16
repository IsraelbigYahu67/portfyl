"""The two unauthenticated e-mail endpoints (spec 5.3, plan Task 6).

Firebase and Brevo are always faked: the router is wired to a fake transport,
a fake link builder and a fake token verifier. The tests build a mini-app the
same way tests/test_rate_limit_routes.py does.
"""
from __future__ import annotations

import inspect
import logging

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import rate_limit
from database import get_db
from edition import Edition
from emails.links import AccountNotFound, ActionLinkError
from emails.transport import BrevoTransport, EmailSendError, MailerSettings
from firebase_identity import IdentityVerificationError, VerifiedIdentity
from models import AuditLog, User
from rate_limit import (
    InvalidClientIp,
    RateLimitExceeded,
    RateLimitRule,
    RateLimitUnavailable,
    invalid_client_ip_handler,
    rate_limit_exceeded_handler,
    rate_limit_unavailable_handler,
)
from routers import auth as auth_router
from routers import auth_email

IP_HEADERS = {"CF-Connecting-IP": "203.0.113.9"}
ADDRESS = "jana@example.com"
VERIFY_URL = "/api/auth/email/verification"
RESET_URL = "/api/auth/email/password-reset"


# --- fakes ------------------------------------------------------------------


class FakeTransport:
    def __init__(self, *, available: bool = True, error: Exception | None = None):
        self.is_available = available
        self.error = error
        self.sent: list[tuple[str, str]] = []
        self.emails: list = []
        self.send_calls = 0
        self.probes = 0

    def available(self) -> bool:
        return self.is_available

    def probe(self) -> None:
        self.probes += 1

    def send(self, *, to, email, tag):
        self.send_calls += 1
        if self.error is not None:
            raise self.error
        self.sent.append((to, tag))
        self.emails.append(email)
        return "<message-id>"


class FakeLinks:
    def __init__(self, *, error: Exception | None = None, missing: set[str] | None = None,
                 on_call=None):
        self.error = error
        self.missing = missing or set()
        self.on_call = on_call
        self.calls: list[tuple[str, str, str]] = []

    def _url(self, kind: str, mode: str, email: str, lang: str) -> str:
        self.calls.append((kind, email, lang))
        if self.on_call is not None:
            self.on_call()
        if self.error is not None:
            raise self.error
        if email in self.missing:
            raise AccountNotFound("no account")
        return f"https://app.portfyl.com/auth/action?mode={mode}&oobCode=C&lang={lang}"

    def verification_url(self, email: str, lang: str) -> str:
        return self._url("verify", "verifyEmail", email, lang)

    def password_reset_url(self, email: str, lang: str) -> str:
        return self._url("reset", "resetPassword", email, lang)


def _identity(uid="uid-1", email=ADDRESS, verified=False) -> VerifiedIdentity:
    return VerifiedIdentity(uid=uid, email=email, email_verified=verified, display_name=None)


class FakeVerifier:
    def __init__(self, identities: dict[str, VerifiedIdentity] | None = None):
        self.identities = identities if identities is not None else {"tok": _identity()}
        self.calls = 0

    def verify_id_token(self, token: str) -> VerifiedIdentity:
        self.calls += 1
        if token not in self.identities:
            raise IdentityVerificationError("bad token")
        return self.identities[token]


class Clock:
    def __init__(self):
        self.t = 100.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


# --- harness ----------------------------------------------------------------


def _shared_limiter_session(db_session):
    """consume_rate_limit closes the session it uses; share the test session
    without letting it be closed (see tests/test_rate_limit_routes.py)."""

    class _SharedSession:
        def __getattr__(self, name):
            return getattr(db_session, name)

        def close(self) -> None:
            pass

    return _SharedSession()


@pytest.fixture
def clock(monkeypatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(auth_email, "_now", fake.now)
    monkeypatch.setattr(auth_email, "_sleep", fake.sleep)
    return fake


@pytest.fixture
def rls_calls(monkeypatch) -> list:
    """SQLite has no set_config; record what the router asks for instead."""
    calls: list = []
    monkeypatch.setattr(
        auth_email, "set_rls_context",
        lambda db, user_id, workspace_id: calls.append((user_id, workspace_id)),
    )
    return calls


class Harness:
    def __init__(self, db_session, *, cloud: bool, monkeypatch, ip_limit=1000, target_limit=1000):
        self.transport = FakeTransport()
        self.links = FakeLinks()
        self.verifier = FakeVerifier()
        self.mailer: auth_email.Mailer | None = auth_email.Mailer(self.transport, self.links)

        # Which (kind, language) the router asked the renderer for. The Czech
        # copy lives in emails/locales, which may not be merged yet, so the
        # rendered text alone cannot prove the language was passed on.
        self.render_calls: list[tuple[str, str]] = []
        real_render = auth_email.render

        def spy_render(kind, lang, **kwargs):
            self.render_calls.append((kind.value, lang))
            return real_render(kind, lang, **kwargs)

        monkeypatch.setattr(auth_email, "render", spy_render)

        app = FastAPI()
        app.state.portfyl_edition = Edition.CLOUD if cloud else Edition.LOCAL
        app.add_exception_handler(auth_router.AuthAPIError, auth_router.auth_api_error_handler)
        app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
        app.add_exception_handler(RateLimitUnavailable, rate_limit_unavailable_handler)
        app.add_exception_handler(InvalidClientIp, invalid_client_ip_handler)
        app.include_router(auth_email.router, prefix="/api")
        app.dependency_overrides[get_db] = lambda: db_session
        app.dependency_overrides[auth_router.get_identity_verifier] = lambda: self.verifier
        app.dependency_overrides[auth_email.get_mailer] = lambda: self.mailer
        self.app = app
        self.client = TestClient(app)

        if cloud:
            monkeypatch.setattr(rate_limit, "RATE_LIMIT_RULES", {
                "auth_email": RateLimitRule(name="auth_email", limit=ip_limit, window_seconds=600),
                "auth_email_target": RateLimitRule(
                    name="auth_email_target", limit=target_limit, window_seconds=900),
            })
            monkeypatch.setattr(rate_limit, "KEY_SECRET", b"test-key-secret")
            monkeypatch.setattr(rate_limit, "SessionLocal",
                                lambda: _shared_limiter_session(db_session))

    def verify(self, token="tok", **body):
        return self.client.post(VERIFY_URL, json={"id_token": token, **body}, headers=IP_HEADERS)

    def reset(self, email=ADDRESS, **body):
        return self.client.post(RESET_URL, json={"email": email, **body}, headers=IP_HEADERS)

    def reset_raw(self, body: dict):
        return self.client.post(RESET_URL, json=body, headers=IP_HEADERS)

    def use_brevo(self, status: int) -> list[str]:
        """Swap the fake transport for a real BrevoTransport (real health
        flag) whose every HTTP call answers ``status``. Returns the list the
        HTTP methods of those calls are appended to."""
        calls: list[str] = []

        def handler(request):
            calls.append(request.method)
            return httpx.Response(status, json={})

        settings = MailerSettings(
            api_key="xkeysib-secret", sender_email="noreply@mail.portfyl.com", sender_name="Portfyl",
            reply_to="support@portfyl.com", app_url="https://app.portfyl.com", console=False)
        transport = BrevoTransport(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))
        self.mailer = auth_email.Mailer(transport, self.links)
        return calls

    def limit_target(self, monkeypatch, error: Exception) -> None:
        """Make the per-address limiter raise ``error``; the per-IP one works."""
        real_consume = rate_limit.consume_rate_limit

        def consume(*, rule, identity, now=None):
            if rule.name == "auth_email_target":
                raise error
            return real_consume(rule=rule, identity=identity, now=now)

        monkeypatch.setattr(rate_limit, "consume_rate_limit", consume)


@pytest.fixture
def local(db_session, monkeypatch, clock) -> Harness:
    return Harness(db_session, cloud=False, monkeypatch=monkeypatch)


@pytest.fixture
def make_cloud(db_session, monkeypatch, clock):
    def factory(**limits) -> Harness:
        return Harness(db_session, cloud=True, monkeypatch=monkeypatch, **limits)
    return factory


# --- verification -------------------------------------------------------------


def test_verification_sends_to_the_token_address_in_the_requested_language(local):
    response = local.verify(lang="cs-CZ", email="evil@x.cz")

    assert response.status_code == 202
    assert response.json() == {"status": "sent"}
    assert local.transport.sent == [(ADDRESS, "verify_email")]
    assert local.links.calls == [("verify", ADDRESS, "cs")]
    assert local.render_calls == [("verify_email", "cs")]
    assert "lang=cs" in local.transport.emails[0].text  # the action link carries it too
    assert "evil@x.cz" not in local.transport.emails[0].html + local.transport.emails[0].text


def test_verification_already_verified_sends_nothing(local):
    local.verifier.identities["tok"] = _identity(verified=True)

    response = local.verify()

    assert response.status_code == 200
    assert response.json() == {"status": "already_verified"}
    assert local.transport.sent == []
    assert local.links.calls == []


def test_verification_bad_token_is_401(local):
    response = local.verify(token="not-a-token")

    assert response.status_code == 401
    assert response.json() == {"code": "authentication_required"}
    assert local.transport.sent == []


def test_verification_without_mailer_is_503_email_unavailable(local):
    local.mailer = None

    response = local.verify()

    assert response.status_code == 503
    assert response.json() == {"code": "email_unavailable"}
    assert local.verifier.calls == 0


def test_verification_unhealthy_mailer_is_503_email_unavailable(local):
    local.transport.is_available = False

    response = local.verify()

    assert response.status_code == 503
    assert response.json() == {"code": "email_unavailable"}
    assert local.verifier.calls == 0
    assert local.links.calls == []


@pytest.mark.parametrize("failure", ["send", "link", "unexpected"])
def test_verification_send_failure_is_503_email_send_failed(local, failure):
    if failure == "send":
        local.transport.error = EmailSendError("brevo_http_500")
    elif failure == "link":
        local.links.error = ActionLinkError("boom")
    else:
        local.links.error = RuntimeError("boom")

    response = local.verify()

    assert response.status_code == 503
    assert response.json() == {"code": "email_send_failed"}


def test_verification_fourth_request_for_one_uid_is_429(make_cloud):
    cloud = make_cloud(target_limit=3)
    cloud.verifier.identities["other"] = _identity(uid="uid-2", email="petr@example.com")

    statuses = [cloud.verify().status_code for _ in range(3)]
    fourth = cloud.verify()
    another_user = cloud.verify(token="other")

    assert statuses == [202, 202, 202]
    assert fourth.status_code == 429
    assert fourth.json() == {"code": "rate_limit_exceeded", "rule": "auth_email_target"}
    assert "Retry-After" in fourth.headers
    assert another_user.status_code == 202
    assert len(cloud.transport.sent) == 4


def test_verification_ip_limit_is_429_before_anything_else(make_cloud):
    cloud = make_cloud(ip_limit=1)

    first = cloud.verify()
    second = cloud.verify()

    assert first.status_code == 202
    assert second.status_code == 429
    assert second.json() == {"code": "rate_limit_exceeded", "rule": "auth_email"}
    assert cloud.verifier.calls == 1


@pytest.mark.parametrize("lang", ["xx", None, "", "c" * 500, 7, ["cs"], "CS"])
def test_verification_unknown_lang_never_422(local, lang):
    response = local.verify(lang=lang)

    assert response.status_code == 202
    expected = "cs" if lang == "CS" else "en"
    assert local.render_calls == [("verify_email", expected)]
    assert local.links.calls == [("verify", ADDRESS, expected)]
    if expected == "en":
        assert local.transport.emails[0].subject == "Confirm your e-mail for Portfyl"


def test_verification_without_lang_field_is_english(local):
    response = local.client.post(VERIFY_URL, json={"id_token": "tok"}, headers=IP_HEADERS)

    assert response.status_code == 202
    assert local.render_calls == [("verify_email", "en")]


# --- password reset -------------------------------------------------------------


def test_reset_sends_for_an_existing_account(local, clock):
    response = local.reset()

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert local.transport.sent == [(ADDRESS, "password_reset")]
    assert local.links.calls == [("reset", ADDRESS, "en")]
    assert local.render_calls == [("password_reset", "en")]


@pytest.mark.parametrize("case", [
    "unknown", "link_error", "send_error", "target_limit_hit", "not_an_address", "unexpected",
    "limiter_unavailable", "wrong_type", "too_long",
])
def test_reset_answers_the_same_for_every_outcome(make_cloud, clock, case, monkeypatch):
    cloud = make_cloud(target_limit=1 if case == "target_limit_hit" else 1000)
    email = ADDRESS
    expected_sends = 0
    if case == "limiter_unavailable":
        cloud.limit_target(monkeypatch, RateLimitUnavailable("auth_email_target", "OperationalError"))
    elif case == "wrong_type":
        email = {"address": ADDRESS}
    elif case == "too_long":
        email = "a" * 400 + "@example.com"
    if case == "unknown":
        cloud.links.missing = {ADDRESS}
    elif case == "link_error":
        cloud.links.error = ActionLinkError("boom")
    elif case == "send_error":
        cloud.transport.error = EmailSendError("brevo_http_500")
    elif case == "target_limit_hit":
        assert cloud.reset().status_code == 202  # uses up the single allowed send
        expected_sends = 1
    elif case == "not_an_address":
        email = "not an address"
    elif case == "unexpected":
        cloud.links.error = RuntimeError(f"boom {ADDRESS} oobCode=C")
    clock.sleeps.clear()

    response = cloud.reset(email=email)

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert len(cloud.transport.sent) == expected_sends
    assert clock.sleeps == [pytest.approx(auth_email.RESET_MIN_SECONDS)]


def test_reset_normalizes_the_address_for_the_limit(make_cloud):
    cloud = make_cloud(target_limit=3)

    statuses = [cloud.reset(email=" Jana@Example.com ").status_code]
    statuses += [cloud.reset(email="jana@example.com").status_code for _ in range(3)]

    assert statuses == [202, 202, 202, 202]
    # One bucket for both spellings: the fourth request is over the limit.
    assert [to for to, _tag in cloud.transport.sent] == ["Jana@Example.com", ADDRESS, ADDRESS]
    assert len(cloud.links.calls) == 3


def test_reset_sends_to_the_typed_address_and_limits_and_audits_the_normalized_one(
    make_cloud, db_session, monkeypatch, rls_calls,
):
    cloud = make_cloud()
    user = User(firebase_uid="firebase-jana", email=ADDRESS)
    db_session.add(user)
    db_session.commit()
    identities: list[str] = []
    real_consume = rate_limit.consume_rate_limit

    def consume(*, rule, identity, now=None):
        identities.append(identity)
        return real_consume(rule=rule, identity=identity, now=now)

    monkeypatch.setattr(rate_limit, "consume_rate_limit", consume)

    assert cloud.reset(email=" Jana@Example.com ").status_code == 202

    assert cloud.transport.sent == [("Jana@Example.com", "password_reset")]
    assert cloud.links.calls == [("reset", "Jana@Example.com", "en")]
    email = cloud.transport.emails[0]
    assert "Jana@Example.com" in email.text and "Jana@Example.com" in email.html
    assert ADDRESS not in email.text and ADDRESS not in email.html
    assert "reset:jana@example.com" in identities
    assert not any("Jana" in identity for identity in identities)
    rows = db_session.query(AuditLog).all()
    assert [row.actor_user_id for row in rows] == [user.id]


@pytest.mark.parametrize("body", [
    {},
    {"email": None},
    {"email": 123},
    {"email": ["jana@example.com"]},
    {"email": {"a": 1}},
    {"email": "a" * 400},
    {"email": "j" * 320 + "@example.com"},
    {"email": ""},
    {"email": "   "},
], ids=["missing", "null", "number", "list", "object", "400-chars", "over-long-address", "empty", "blank"])
def test_reset_malformed_email_is_accepted_and_sends_nothing(make_cloud, clock, monkeypatch, body, caplog):
    caplog.set_level(logging.INFO)
    cloud = make_cloud()
    target_calls: list[str] = []
    real_consume = rate_limit.consume_rate_limit

    def consume(*, rule, identity, now=None):
        if rule.name == "auth_email_target":
            target_calls.append(identity)
        return real_consume(rule=rule, identity=identity, now=now)

    monkeypatch.setattr(rate_limit, "consume_rate_limit", consume)

    response = cloud.reset_raw(body)

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert cloud.transport.send_calls == 0
    assert cloud.transport.probes == 1
    assert cloud.links.calls == []  # no Firebase call
    assert clock.sleeps == [pytest.approx(auth_email.RESET_MIN_SECONDS)]
    assert "outcome=invalid_address" in caplog.text
    if not isinstance(body.get("email"), str) or len(body["email"].strip()) > 320:
        assert target_calls == []  # not a string, or over-long: no limiter call either


def test_reset_body_that_is_not_an_object_is_still_422(local):
    # Cannot depend on an account, so FastAPI's own answer stays (plan residual).
    response = local.client.post(RESET_URL, json=["jana@example.com"], headers=IP_HEADERS)

    assert response.status_code == 422


# --- the health flag moves the same for every address (review focus 1) -------

FLAG_CASES = ["existing", "unknown", "invalid", "wrong_type", "target_limited",
              "limiter_unavailable", "link_error", "unexpected"]


def _flag_case(cloud: Harness, monkeypatch, case: str):
    """Arrange ``case`` on the harness and return the request to make."""
    cloud.links.error = None
    cloud.links.missing = set()
    monkeypatch.setattr(rate_limit, "consume_rate_limit", _REAL_CONSUME)
    if case == "unknown":
        cloud.links.missing = {ADDRESS}
    elif case == "invalid":
        return lambda: cloud.reset(email="not an address")
    elif case == "wrong_type":
        return lambda: cloud.reset(email=123)
    elif case == "target_limited":
        cloud.limit_target(monkeypatch, RateLimitExceeded("auth_email_target", 60))
    elif case == "limiter_unavailable":
        cloud.limit_target(monkeypatch, RateLimitUnavailable("auth_email_target", "OperationalError"))
    elif case == "link_error":
        cloud.links.error = ActionLinkError("boom")
    elif case == "unexpected":
        cloud.links.error = RuntimeError("boom")
    return lambda: cloud.reset()


_REAL_CONSUME = rate_limit.consume_rate_limit


@pytest.mark.parametrize("case", FLAG_CASES)
def test_reset_with_a_rejected_key_switches_the_mailer_off_on_every_path(make_cloud, monkeypatch, case):
    cloud = make_cloud()
    calls = cloud.use_brevo(401)

    first = _flag_case(cloud, monkeypatch, case)()
    second = cloud.reset()

    assert first.status_code == 202
    assert first.json() == {"status": "accepted"}
    assert calls == ["POST" if case == "existing" else "GET"]  # exactly one Brevo call
    assert second.status_code == 503
    assert second.json() == {"code": "email_unavailable"}


@pytest.mark.parametrize("order", [
    ["existing", "unknown", "invalid"],
    ["unknown", "target_limited", "existing"],
    ["invalid", "wrong_type", "unknown"],
    ["existing", "existing", "link_error"],
    ["limiter_unavailable", "unexpected", "existing"],
])
def test_reset_three_outage_answers_of_any_mix_switch_the_mailer_off(make_cloud, monkeypatch, order):
    cloud = make_cloud()
    calls = cloud.use_brevo(503)

    statuses = [_flag_case(cloud, monkeypatch, case)().status_code for case in order]
    after = _flag_case(cloud, monkeypatch, "existing")()

    assert statuses == [202, 202, 202]
    assert len(calls) == 3  # one Brevo call per request
    assert after.status_code == 503
    assert after.json() == {"code": "email_unavailable"}


@pytest.mark.parametrize("case", FLAG_CASES)
def test_reset_makes_exactly_one_brevo_call_on_every_path(make_cloud, monkeypatch, case):
    cloud = make_cloud()

    assert _flag_case(cloud, monkeypatch, case)().status_code == 202

    expected = (1, 0) if case == "existing" else (0, 1)
    assert (cloud.transport.send_calls, cloud.transport.probes) == expected


def test_reset_failed_send_is_not_followed_by_a_probe(local):
    local.transport.error = EmailSendError("brevo_http_500")

    assert local.reset().status_code == 202
    assert (local.transport.send_calls, local.transport.probes) == (1, 0)


def test_reset_a_raising_probe_does_not_change_the_answer(local, clock):
    def boom():
        raise RuntimeError(f"probe exploded {ADDRESS}")

    local.transport.probe = boom
    local.links.missing = {ADDRESS}

    response = local.reset()

    assert response.status_code == 202
    assert clock.sleeps == [pytest.approx(1.5)]


def test_verification_never_probes(local):
    local.verify()  # sent
    local.links.error = ActionLinkError("boom")
    local.verify()  # link error
    local.links.error = None
    local.verifier.identities["tok"] = _identity(verified=True)
    local.verify()  # already verified
    local.verify(token="not-a-token")

    assert local.transport.probes == 0


@pytest.mark.parametrize("work,answer_at", [
    (0.2, 1.5), (1.5, 1.5), (1.6, 2.0), (2.0, 2.0), (2.01, 2.5), (4.9, 5.0), (9.0, 9.0),
])
@pytest.mark.parametrize("path", ["existing", "unknown"])
def test_reset_answers_on_a_half_second_grid_above_the_floor(local, clock, work, answer_at, path):
    if path == "unknown":
        local.links.missing = {ADDRESS}
    local.links.on_call = lambda: setattr(clock, "t", clock.t + work)

    assert local.reset().status_code == 202

    assert len(clock.sleeps) == 1
    assert work + clock.sleeps[0] == pytest.approx(answer_at)
    assert clock.sleeps[0] >= 0.0


@pytest.mark.parametrize("case", ["no_portfyl_user", "unknown", "invalid"])
def test_reset_holds_no_transaction_while_it_waits(local, db_session, monkeypatch, case, rls_calls):
    if case == "unknown":
        local.links.missing = {ADDRESS}
    in_transaction: list[bool] = []
    monkeypatch.setattr(auth_email, "_sleep", lambda _s: in_transaction.append(db_session.in_transaction()))
    statements: list[str] = []

    from sqlalchemy import event

    event.listen(db_session.get_bind(), "before_cursor_execute", lambda *args: statements.append(args[2]))

    email = "not an address" if case == "invalid" else ADDRESS
    assert local.reset(email=email).status_code == 202

    assert in_transaction == [False]
    if case == "no_portfyl_user":
        # The lookup did run (Firebase knows the address, Portfyl does not).
        assert any("FROM users" in statement for statement in statements)
        assert local.transport.sent == [(ADDRESS, "password_reset")]


def test_reset_a_failing_release_does_not_change_the_answer(local, clock, monkeypatch):
    def boom(_db):
        raise RuntimeError("database is gone")

    monkeypatch.setattr(auth_email, "release_connection", boom)

    response = local.reset()

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert clock.sleeps == [pytest.approx(1.5)]


def test_reset_always_waits_for_the_minimum_time(local, clock):
    local.links.on_call = lambda: setattr(clock, "t", clock.t + 0.4)

    assert local.reset().status_code == 202
    assert clock.sleeps == [pytest.approx(1.1)]

    clock.sleeps.clear()
    local.links.on_call = None
    local.links.missing = {ADDRESS}
    assert local.reset().status_code == 202
    assert clock.sleeps == [pytest.approx(1.5)]

    # A slow path is never padded below zero.
    clock.sleeps.clear()
    local.links.missing = set()
    local.links.on_call = lambda: setattr(clock, "t", clock.t + 9.0)
    assert local.reset().status_code == 202
    assert clock.sleeps == [0.0]


def test_reset_without_mailer_is_503_before_reading_the_body(local, clock):
    local.mailer = None

    response = local.reset(email="x")

    assert response.status_code == 503
    assert response.json() == {"code": "email_unavailable"}
    assert local.links.calls == []
    assert clock.sleeps == []


def test_reset_unhealthy_mailer_is_503_email_unavailable(local, clock):
    local.transport.is_available = False

    response = local.reset()

    assert response.status_code == 503
    assert response.json() == {"code": "email_unavailable"}
    assert local.links.calls == []
    assert clock.sleeps == []


def test_reset_ip_limit_is_429(make_cloud):
    cloud = make_cloud(ip_limit=1)

    first = cloud.reset()
    second = cloud.reset()

    assert first.status_code == 202
    assert second.status_code == 429
    assert second.json() == {"code": "rate_limit_exceeded", "rule": "auth_email"}
    assert len(cloud.transport.sent) == 1


def test_reset_target_limiter_outage_is_treated_like_a_skip(make_cloud, monkeypatch):
    cloud = make_cloud()
    real_consume = rate_limit.consume_rate_limit

    def consume(*, rule, identity, now=None):
        if rule.name == "auth_email_target":
            raise RateLimitUnavailable(rule.name, "OperationalError")
        return real_consume(rule=rule, identity=identity, now=now)

    monkeypatch.setattr(rate_limit, "consume_rate_limit", consume)

    response = cloud.reset()

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert cloud.transport.sent == []


def test_reset_writes_an_audit_row_only_for_a_portfyl_user(local, db_session, test_user, rls_calls):
    existing = local.reset(email=test_user.email, lang="CS")
    unknown_to_portfyl = local.reset(email="nobody@example.com")

    assert existing.status_code == unknown_to_portfyl.status_code == 202
    assert existing.json() == unknown_to_portfyl.json()
    rows = db_session.query(AuditLog).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.action == "auth.email.sent"
    assert row.actor_user_id == test_user.id
    assert row.target_type == "user" and row.target_id == str(test_user.id)
    assert row.workspace_id is None
    assert row.event_metadata == {"kind": "password_reset", "lang": "cs"}
    assert rls_calls == [(test_user.id, None)]
    assert len(local.transport.sent) == 2


def test_reset_writes_no_audit_row_when_nothing_was_sent(local, db_session, test_user, rls_calls):
    local.transport.error = EmailSendError("brevo_http_500")

    assert local.reset(email=test_user.email).status_code == 202

    assert db_session.query(AuditLog).count() == 0


def test_reset_audit_failure_does_not_change_the_answer(local, clock, test_user, monkeypatch, rls_calls):
    def boom(*_args, **_kwargs):
        raise RuntimeError("database is gone")

    monkeypatch.setattr(auth_email, "record_audit_event", boom)

    response = local.reset(email=test_user.email)

    assert response.status_code == 202
    assert response.json() == {"status": "accepted"}
    assert clock.sleeps == [pytest.approx(1.5)]


def test_reset_does_not_use_the_database_before_the_outbound_calls(make_cloud, db_session, test_user, rls_calls):
    cloud = make_cloud()
    statements: list[str] = []
    seen_at_send: list[list[str]] = []

    from sqlalchemy import event

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", lambda *args: statements.append(args[2]))
    original_send = cloud.transport.send

    def spy_send(**kwargs):
        # Only the rate limiter's own isolated upserts may have run so far.
        seen_at_send.append([s for s in statements if "rate_limit_buckets" not in s])
        return original_send(**kwargs)

    cloud.transport.send = spy_send

    assert cloud.reset(email=test_user.email).status_code == 202
    assert seen_at_send == [[]]
    # ...and the lookup and the audit row did happen afterwards.
    assert any("FROM users" in statement for statement in statements)
    assert db_session.query(AuditLog).count() == 1


@pytest.mark.parametrize("endpoint", ["verification", "reset"])
def test_logs_never_contain_the_address_the_link_or_the_code(
    make_cloud, caplog, endpoint, rls_calls, monkeypatch,
):
    caplog.set_level(logging.DEBUG)
    secret_error = RuntimeError(f"boom {ADDRESS} https://x/auth/action?oobCode=C xkeysib-abc123")
    call = (lambda c: c.verify()) if endpoint == "verification" else (lambda c: c.reset())

    ok = make_cloud()
    call(ok)  # success
    sent = make_cloud()
    sent.transport.error = EmailSendError("brevo_http_500")
    call(sent)  # Brevo error
    unexpected = make_cloud()
    unexpected.links.error = secret_error
    call(unexpected)  # something unforeseen carrying secrets in its text
    unknown = make_cloud()
    unknown.links.missing = {ADDRESS}
    call(unknown)  # unknown account
    if endpoint == "reset":
        malformed = make_cloud()
        malformed.reset(email=[ADDRESS, "https://x/auth/action?oobCode=C"])  # not a string
        malformed.reset(email=f"{ADDRESS} https://x/auth/action?oobCode=C")  # not an address
        malformed.reset(email=ADDRESS + "x" * 400)  # over-long
        limited = make_cloud()
        limited.limit_target(monkeypatch, RateLimitExceeded("auth_email_target", 60))
        call(limited)  # per-address limit hit
        monkeypatch.setattr(rate_limit, "consume_rate_limit", _REAL_CONSUME)
        rejected_key = make_cloud()
        rejected_key.links.missing = {ADDRESS}
        rejected_key.use_brevo(401)
        call(rejected_key)  # the probe switches the mailer off and logs it
        assert "brevo_http_401" in caplog.text
        broken_probe = make_cloud()
        broken_probe.links.missing = {ADDRESS}
        broken_probe.transport.probe = lambda: (_ for _ in ()).throw(secret_error)
        call(broken_probe)  # a probe that raises, carrying secrets in its text
        assert "auth_email probe failed error=RuntimeError" in caplog.text
        assert "outcome=invalid_address" in caplog.text
        assert "outcome=target_limited" in caplog.text
        assert "outcome=no_account" in caplog.text

    assert "auth_email" in caplog.text  # the lines exist, so this is not vacuous
    assert "brevo_http_500" in caplog.text
    # httpx's own client logger prints the URL of the faked Brevo call (Brevo's
    # public endpoint, no key); everything else is checked.
    logged = "\n".join(
        record.getMessage() for record in caplog.records if record.name != "httpx"
    )
    assert "Mailer switched off" in logged or endpoint == "verification"
    for forbidden in (ADDRESS, "jana@", "oobCode", "xkeysib", "https://", "auth/action"):
        assert forbidden not in logged, forbidden


def test_limits_are_skipped_in_the_local_edition(local):
    # No rate-limit rules are loaded outside the cloud edition, so consuming
    # one would raise KeyError: ten 202s prove both rules are skipped.
    assert rate_limit.RATE_LIMIT_RULES == {}
    assert [local.reset().status_code for _ in range(10)] == [202] * 10
    assert [local.verify().status_code for _ in range(10)] == [202] * 10


def test_the_endpoints_are_plain_functions_and_unauthenticated():
    for endpoint in (auth_email.send_verification_email, auth_email.send_password_reset_email,
                     auth_email.get_mailer):
        assert not inspect.iscoroutinefunction(endpoint), endpoint.__name__

    routes = {route.path: route for route in auth_email.router.routes}
    assert set(routes) == {"/auth/email/verification", "/auth/email/password-reset"}


# --- build_mailer ---------------------------------------------------------------


def test_build_mailer_is_off_without_settings():
    assert auth_email.build_mailer({}, Edition.CLOUD) is None
    assert auth_email.build_mailer({}, Edition.LOCAL) is None


def test_build_mailer_cloud_uses_brevo_and_makes_no_network_call(monkeypatch):
    import httpx

    def forbidden(*_args, **_kwargs):
        raise AssertionError("constructing the mailer must not use the network")

    monkeypatch.setattr(httpx.Client, "send", forbidden)
    monkeypatch.setattr(httpx.Client, "request", forbidden)
    env = {"PORTFYL_BREVO_API_KEY": "xkeysib-secret", "PORTFYL_EMAIL_APP_URL": "https://app.portfyl.com/"}

    mailer = auth_email.build_mailer(env, Edition.CLOUD)

    assert mailer is not None
    assert type(mailer.transport).__name__ == "BrevoTransport"
    assert mailer.transport.available() is True


def test_build_mailer_console_transport_in_local():
    mailer = auth_email.build_mailer({"PORTFYL_EMAIL_TRANSPORT": "console"}, Edition.LOCAL)

    assert mailer is not None
    assert type(mailer.transport).__name__ == "ConsoleTransport"


@pytest.mark.parametrize("env", [
    {"PORTFYL_BREVO_API_KEY": "k"},                                         # cloud: no app URL
    {"PORTFYL_BREVO_API_KEY": "k", "PORTFYL_EMAIL_APP_URL": "http://x.y"},  # cloud: not https
    {"PORTFYL_BREVO_API_KEY": "k", "PORTFYL_EMAIL_APP_URL": "https://[bad"},
    {"PORTFYL_BREVO_API_KEY": "k", "PORTFYL_EMAIL_APP_URL": "https://a.b:notaport"},
    {"PORTFYL_BREVO_API_KEY": "\x00\ud800", "PORTFYL_EMAIL_APP_URL": "\x00"},
])
def test_build_mailer_never_raises_for_a_broken_setting(env):
    assert auth_email.build_mailer(env, Edition.CLOUD) is None  # unusable in cloud: mailer off
    auth_email.build_mailer(env, Edition.LOCAL)  # may be on or off, must not raise


def test_build_mailer_never_raises_even_when_the_environment_misbehaves(caplog):
    class Hostile(dict):
        def get(self, *_args, **_kwargs):
            raise RuntimeError("environment exploded with xkeysib-secret")

    assert auth_email.build_mailer(Hostile(), Edition.CLOUD) is None
    assert "xkeysib" not in caplog.text


def test_build_mailer_survives_a_failing_transport_constructor(monkeypatch, caplog):
    def explode(*_args, **_kwargs):
        raise RuntimeError("cannot build client for xkeysib-secret")

    monkeypatch.setattr(auth_email, "BrevoTransport", explode)
    env = {"PORTFYL_BREVO_API_KEY": "xkeysib-secret", "PORTFYL_EMAIL_APP_URL": "https://app.portfyl.com"}

    assert auth_email.build_mailer(env, Edition.CLOUD) is None
    assert "xkeysib" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_get_mailer_reads_the_app_state():
    app = FastAPI()
    app.state.portfyl_mailer = "sentinel"

    class _Request:
        pass

    request = _Request()
    request.app = app
    assert auth_email.get_mailer(request) == "sentinel"

    bare = _Request()
    bare.app = FastAPI()
    assert auth_email.get_mailer(bare) is None
