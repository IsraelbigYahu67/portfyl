# Portfyl's Own E-mails, Wave 1 (Verification + Password Reset) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portfyl's backend writes and sends the e-mail-verification and password-reset e-mails itself through Brevo, branded and in the user's app language, with Firebase's built-in sending kept as the fallback.

**Architecture:** A new `backend/emails/` package renders an e-mail from code-owned copy (9 languages) and posts it to Brevo's HTTP API. Two new unauthenticated endpoints under `/api/auth/email/` get a one-time code from the Firebase Admin SDK, build a Portfyl `/auth/action` link from it and send. The frontend calls these endpoints first and falls back to the Firebase client SDK on any failure except `429`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, `firebase-admin`, `httpx` (all already locked; **no new dependency**), React 18, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-11-15-portfyl-own-emails-design.md` — read sections 5, 6, 8 (wave 1), 9 and 10 before starting. Read `CLAUDE.md` too. Section numbers below (§) refer to the spec.

## Global Constraints

- Branch `feat/own-emails`, created from `feat/branded-auth-domain` (it contains `/auth/action`, which the links need). Nobody commits to `main` or to `feat/branded-auth-domain`.
- No migration, no change to `requirements*.txt` / `*.lock` / `package.json`.
- Every endpoint and dependency is a plain `def`, never `async def`.
- No e-mail address, link, one-time code or API key in any log line, exception text or audit metadata.
- The password-reset endpoint answers the same status and body whether or not the account exists (§5.3).
- A missing or wrong e-mail setting must never stop the service from starting.
- Languages are exactly `cs en de fr es it pt pl nl`; English is the source and the fallback.
- Czech copy uses formal address (vykání). Plan names, broker names and "Portfyl" stay untranslated.
- Colors in the e-mail HTML are the literals from §6, defined once as named constants in `backend/emails/render.py`. No other file hardcodes them.
- The e-mail HTML never shows a raw URL; the plain-text part carries the full link.
- Rate-limit defaults: `auth_email` 10 per 600 s per IP; `auth_email_target` 3 per 900 s.
- Timeouts for Brevo: connect 3 s, total 5 s, no retry.
- Health flag: after a Brevo `401`/`403` or 3 failed sends in a row the mailer is unavailable for 300 s.
- Minimum response time of the reset endpoint: 1.5 s.
- Commit messages follow the repo style (`feat(auth): …`, `test(auth): …`, `docs(deploy): …`).

## Review Focus

1. **An address with HTML or unusual characters** (`a<b>"c@x.cz`, `jana+test@příklad.cz`). Expected: shown escaped in the e-mail, sent to the exact address, nothing breaks. Test in Task 1.
2. **Garbage `lang`** (`"xx"`, `""`, `null`, 500 characters, `"CS"`, `"cs-CZ"`). Expected: `CS` and `cs-CZ` give Czech, everything else English, never a `422`. Test in Tasks 1 and 6.
3. **The same address typed differently** (`Jana@Example.com `, `jana@example.com`). Expected: one rate-limit bucket, one account. Test in Task 6.
4. **New frontend, old backend during a rolling deploy** (`404` on the new endpoints). Expected: the Firebase e-mail goes out, the user sees no error. Test in Task 7.
5. **Brevo answers `201` without a `messageId`, or hangs.** Expected: a missing id is still success; a hang ends at 5 s as a failure and counts toward the health flag. Test in Task 3.

## File Structure

| File | Responsibility |
|---|---|
| `backend/emails/__init__.py` | empty package marker |
| `backend/emails/catalog.py` | `EmailKind`, `EmailContent`, language list, English copy, lookup |
| `backend/emails/locales/{cs,de,fr,es,it,pt,pl,nl}.py` | one language's copy each |
| `backend/emails/render.py` | layout: content + params → subject, HTML, text |
| `backend/emails/transport.py` | settings from env, `BrevoTransport` (with health flag), `ConsoleTransport` |
| `backend/emails/links.py` | Firebase Admin link → `oobCode` → Portfyl action URL |
| `backend/routers/auth_email.py` | the two endpoints and their dependencies |
| `backend/rate_limit.py`, `backend/logging_setup.py`, `backend/main.py` | two rules, two redaction patterns, router mount |
| `frontend/src/auth/authEmail.js` | backend-first sending with Firebase fallback |
| `frontend/src/api.js` | two request functions |
| `frontend/src/i18n/I18nProvider.jsx`, `frontend/src/pages/AuthAction.jsx` | action page follows the e-mail's language |
| `deploy/cloudrun.md`, `CLAUDE.md` | runbook section, architecture note |

The spec's `service.py` is folded into the router (two short functions); the spec's "`BrevoTransport` also implements `NotificationTransport`" is left to wave 3, which is the first user of the outbox.

## Execution Waves

- **Wave A (parallel, disjoint files):** Task 1, Task 3, Task 4, Task 5, Task 8.
- **Wave B:** Task 2 (needs Task 1), Task 6 (needs 1, 3, 4, 5), Task 7 (needs only the endpoint contract in Task 6's Interfaces; may run beside Task 6).
- **Wave C:** Task 9.

Tasks in one wave work in separate worktrees off `feat/own-emails` and are merged back before the next wave. `frontend/src/i18n/messages/*.js` is a hotspot; no task in this plan needs to touch it.

---

### Task 1: Template model, English copy, renderer

**Files:**
- Create: `backend/emails/__init__.py`, `backend/emails/catalog.py`, `backend/emails/render.py`
- Test: `backend/tests/test_email_render.py`

**Interfaces:**
- Produces (`emails.catalog`):
  - `LANGUAGES: tuple[str, ...] = ("cs","en","de","fr","es","it","pt","pl","nl")`, `SOURCE_LANGUAGE = "en"`
  - `class EmailKind(str, Enum)`: `VERIFY_EMAIL = "verify_email"`, `PASSWORD_RESET = "password_reset"`
  - `@dataclass(frozen=True) class EmailContent` with the fields of §6 (`subject, preheader, heading, paragraphs, bullets=(), facts=(), button=None, note="", footer_reason="account"`)
  - `@dataclass(frozen=True) class Locale`: `messages: Mapping[EmailKind, EmailContent]`, `footer_reasons: Mapping[str, str]` (keys `"account"`, `"address"`), `footer_help: str`
  - `ENGLISH: Locale`
  - `normalize_language(code: object) -> str` — lower-cases, takes the part before `-`, returns it if in `LANGUAGES`, else `"en"`; never raises
  - `locale_for(lang: str) -> Locale` — imports `emails.locales.<lang>` lazily (`LOCALE` attribute); `"en"` → `ENGLISH`; a missing module → `ENGLISH`
- Produces (`emails.render`):
  - `@dataclass(frozen=True) class RenderedEmail`: `subject: str`, `html: str`, `text: str`
  - `render(kind: EmailKind, lang: str, *, params: Mapping[str, str], action_url: str | None = None) -> RenderedEmail`
  - `class TemplateError(ValueError)` — unknown or missing placeholder, or a button without `action_url`

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_email_render.py`

```python
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
```

- [ ] **Step 2: Run** `cd backend && python -m pytest tests/test_email_render.py -v` — Expected: FAIL, `ModuleNotFoundError: emails`.

- [ ] **Step 3: Write `catalog.py`.** English copy for both kinds is copied verbatim from §8 "Wave 1" (subject, preheader, heading, text, button, note; `footer_reason="address"` for both). Footer strings verbatim from the first paragraph of §8. Keep the "The link works for 1 hour." sentence; Task 9's checklist decides whether it stays.

- [ ] **Step 4: Write `render.py`.** Layout per §6: full HTML document with `<html lang>`, `color-scheme` light metas, hidden padded preheader, table layout with inline CSS and `bgcolor`, logo `https://portfyl.com/portfyl-mark.png` 44×44, 480px card, pill button as a padded `<a>` in a coloured cell, note, footer (reason, help line, `Portfyl · portfyl.com`). Named colour constants citing the `DESIGN.md` token (`BG = "#F3E8DA"  # --bg`, …). Placeholder filling: escape the value with `html.escape`, then turn `**x**` into `<b>x</b>` in the already-escaped template text; in the text part drop the `**`. Unknown `{name}` in a template or a missing key in `params` raises `TemplateError`. The text part: heading, paragraphs, bullets as `- `, facts as `Label: value`, button label followed by the URL on its own line, note, footer.

- [ ] **Step 5: Run** the same command — Expected: all PASS.

- [ ] **Step 6: Commit** `feat(emails): e-mail template model, English copy and renderer`

---

### Task 2: Eight translations and the parity test

**Files:**
- Create: `backend/emails/locales/__init__.py`, `backend/emails/locales/{cs,de,fr,es,it,pt,pl,nl}.py`
- Test: `backend/tests/test_email_locales.py`

**Interfaces:**
- Consumes: `Locale`, `EmailContent`, `EmailKind`, `ENGLISH`, `LANGUAGES`, `locale_for` (Task 1).
- Produces: each module exports `LOCALE: Locale`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run** `python -m pytest tests/test_email_locales.py -v` — Expected: FAIL (locale modules missing, `locale_for` returns `ENGLISH`).

- [ ] **Step 3: Write `cs.py`** with the Czech copy copied verbatim from §8 (both wave-1 tables and the two footer sentences).

- [ ] **Step 4: Write the other seven modules.** Translate from the English source. Match the register of the app's own dictionary `frontend/src/i18n/messages/<code>.js`: look up how it translates "Reset your password" and "Check your inbox (and spam folder)." and use the same form of address and the same spelling of "e-mail"; reuse an existing translation wherever the sentence is the same.

- [ ] **Step 5: Run** the same command — Expected: all PASS.

- [ ] **Step 6: Commit** `feat(emails): translate verification and reset e-mails into 8 languages`

---

### Task 3: Brevo transport, settings, health flag

**Files:**
- Create: `backend/emails/transport.py`
- Test: `backend/tests/test_email_transport.py`

**Interfaces:**
- Consumes: `RenderedEmail` (Task 1; if Task 1 is not merged yet, build against a local dataclass with the same three `str` fields and switch the import at merge).
- Produces (`emails.transport`):
  - `class EmailSendError(RuntimeError)` — message is a short reason code only (`"brevo_http_401"`, `"brevo_timeout"`, `"brevo_network"`)
  - `@dataclass(frozen=True) class MailerSettings`: `api_key: str | None`, `sender_email: str`, `sender_name: str`, `reply_to: str`, `app_url: str`, `console: bool`
  - `load_mailer_settings(env: Mapping[str, str], edition: Edition) -> MailerSettings | None` — `None` means "mailer off"; logs one ERROR when a key is present but the settings are unusable
  - `class EmailTransport(Protocol)`: `available() -> bool`; `send(*, to: str, email: RenderedEmail, tag: str) -> str | None` (Brevo message id)
  - `class BrevoTransport(settings, *, client: httpx.Client | None = None, clock: Callable[[], float] = time.monotonic)`
  - `class ConsoleTransport(*, out: TextIO = sys.stdout)` — `available()` is always `True`
  - `FAILURE_THRESHOLD = 3`, `COOLDOWN_SECONDS = 300`, `BREVO_URL = "https://api.brevo.com/v3/smtp/email"`

Settings rules (§5.7): env names `PORTFYL_BREVO_API_KEY`, `PORTFYL_EMAIL_FROM` (default `noreply@mail.portfyl.com`), `PORTFYL_EMAIL_FROM_NAME` (default `Portfyl`), `PORTFYL_EMAIL_REPLY_TO` (default `support@portfyl.com`), `PORTFYL_EMAIL_APP_URL`, `PORTFYL_EMAIL_TRANSPORT`. Cloud: needs the key and an `https://` app URL, `console` is ignored. Local: app URL defaults to `http://localhost:5173`; `PORTFYL_EMAIL_TRANSPORT=console` gives `console=True` without a key; no key and no console → `None`. The app URL is stored without a trailing slash.

- [ ] **Step 1: Write the failing tests** (use `httpx.MockTransport` for the client)

```python
import httpx, io, json, pytest
from edition import Edition
from emails.transport import (BrevoTransport, ConsoleTransport, EmailSendError,
                              MailerSettings, load_mailer_settings, COOLDOWN_SECONDS)

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

@pytest.mark.parametrize("status", [400, 401, 429, 500])
def test_http_error_raises_without_leaking(status):
    with pytest.raises(EmailSendError) as info:
        _transport(lambda r: httpx.Response(status, json={"message": "xkeysib-secret a@b.cz"})).send(to="a@b.cz", email=Mail, tag="t")
    assert str(info.value) == f"brevo_http_{status}"

def test_timeout_raises():
    def handler(request): raise httpx.ReadTimeout("slow", request=request)
    with pytest.raises(EmailSendError, match="brevo_timeout"):
        _transport(handler).send(to="a@b.cz", email=Mail, tag="t")

def test_auth_failure_switches_off_for_the_cooldown():
    now = [0.0]
    transport = _transport(lambda r: httpx.Response(401), clock=lambda: now[0])
    assert transport.available()
    with pytest.raises(EmailSendError): transport.send(to="a@b.cz", email=Mail, tag="t")
    assert not transport.available()
    now[0] = COOLDOWN_SECONDS + 1
    assert transport.available()

def test_three_failures_in_a_row_switch_off_and_a_success_resets():
    answers = iter([500, 500, 201, 500, 500, 500])
    transport = _transport(lambda r: httpx.Response(next(answers), json={}))
    for expect_ok in (False, False, True, False, False):
        try: transport.send(to="a@b.cz", email=Mail, tag="t")
        except EmailSendError: assert not expect_ok
        assert transport.available()
    with pytest.raises(EmailSendError): transport.send(to="a@b.cz", email=Mail, tag="t")
    assert not transport.available()

def test_console_transport_prints_subject_and_text():
    out = io.StringIO()
    ConsoleTransport(out=out).send(to="a@b.cz", email=Mail, tag="t")
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
    if settings and edition is Edition.CLOUD: assert settings.console is False
```

- [ ] **Step 2: Run** `python -m pytest tests/test_email_transport.py -v` — Expected: FAIL, module missing.
- [ ] **Step 3: Implement `transport.py`.** `httpx.Timeout(5.0, connect=3.0)`. A send that succeeds sets the failure count to 0. The health state is per instance and guarded by a `threading.Lock` (endpoints run in the threadpool).
- [ ] **Step 4: Run** — Expected: all PASS.
- [ ] **Step 5: Commit** `feat(emails): Brevo transport with a health flag and env settings`

---

### Task 4: Action links

**Files:**
- Create: `backend/emails/links.py`
- Test: `backend/tests/test_email_links.py`

**Interfaces:**
- Produces (`emails.links`):
  - `class ActionLinkError(RuntimeError)`; `class AccountNotFound(ActionLinkError)`
  - `class ActionLinkBuilder(*, app_url: str, auth_client: Any = firebase_auth, app: Any = None)`
    - `verification_url(email: str, lang: str) -> str`
    - `password_reset_url(email: str, lang: str) -> str`

Behaviour (§5.2): call `auth_client.generate_email_verification_link(email, action_code_settings=ActionCodeSettings(url=f"{app_url}/login?verified=1"), app=app)` or `generate_password_reset_link(...)` with the same settings; take `oobCode` from the returned link's query; build `f"{app_url}/auth/action?" + urlencode(...)` with `mode`, `oobCode`, `lang`, and for verification also `continueUrl`. `firebase_admin.exceptions.NotFoundError` → `AccountNotFound`; any other exception, or a link with no `oobCode`, → `ActionLinkError` whose message never contains the address or the link. Resolve the default Firebase app the way `firebase_identity._default_firebase_app` does (import and reuse it).

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run** `python -m pytest tests/test_email_links.py -v` — Expected: FAIL, module missing.
- [ ] **Step 3: Implement `links.py`** as described above.
- [ ] **Step 4: Run** — Expected: all PASS.
- [ ] **Step 5: Commit** `feat(emails): build Portfyl action links from Firebase one-time codes`

---

### Task 5: Rate-limit rules and log redaction

**Files:**
- Modify: `backend/rate_limit.py:29-33` (`_RULE_ENV_VARS`), `backend/logging_setup.py:32-46` (`_REDACTION_PATTERNS`)
- Modify tests: every file found by `grep -rln "RATE_LIMIT_" backend/tests` that lists the rule env vars or the rule set — at least `test_rate_limit_config.py`, `test_csrf_coverage.py`, `test_main_rate_limit_wiring.py`, `test_edition_routes.py`, `test_cloud_gate.py`
- Test: `backend/tests/test_rate_limit_config.py`, and the existing redaction test file (find it with `grep -rl "redact" backend/tests`)

**Interfaces:**
- Produces: rules `"auth_email"` (env `RATE_LIMIT_AUTH_EMAIL_LIMIT`, `RATE_LIMIT_AUTH_EMAIL_WINDOW_SECONDS`) and `"auth_email_target"` (env `RATE_LIMIT_AUTH_EMAIL_TARGET_LIMIT`, `RATE_LIMIT_AUTH_EMAIL_TARGET_WINDOW_SECONDS`) in `rate_limit.RATE_LIMIT_RULES`.

- [ ] **Step 1: Write the failing tests**

```python
# test_rate_limit_config.py — extend VALID_CLOUD_ENV with the four new vars ("10","600","3","900") and:
def test_load_rate_limit_rules_returns_all_five_rules_when_valid():
    rules = load_rate_limit_rules(VALID_CLOUD_ENV)
    assert set(rules) == {"global", "auth_session", "broker_sync", "auth_email", "auth_email_target"}
    assert rules["auth_email"] == RateLimitRule(name="auth_email", limit=10, window_seconds=600)
    assert rules["auth_email_target"] == RateLimitRule(name="auth_email_target", limit=3, window_seconds=900)

def test_missing_auth_email_var_fails_closed():
    env = {k: v for k, v in VALID_CLOUD_ENV.items() if k != "RATE_LIMIT_AUTH_EMAIL_TARGET_LIMIT"}
    with pytest.raises(RuntimeError, match="RATE_LIMIT_AUTH_EMAIL_TARGET_LIMIT"):
        load_rate_limit_rules(env)

# redaction test file
def test_redacts_brevo_key_and_one_time_code():
    line = redact("api-key: xkeysib-0123abcd-EFgh link https://app.portfyl.com/auth/action?mode=verifyEmail&oobCode=AbC-12_x&lang=cs")
    assert "xkeysib-0123" not in line and "AbC-12_x" not in line
    assert "mode=verifyEmail" in line and "lang=cs" in line
```

(The old `…returns_all_three_rules…` test is replaced by the five-rule one.)

- [ ] **Step 2: Run** those two test files — Expected: the new tests FAIL.
- [ ] **Step 3: Add the two rules and the two patterns** (`xkeysib-[A-Za-z0-9-]+` → `xkeysib-[REDACTED]`; `(oobCode=)[^&\s"']+` → `\1[REDACTED]`). Fix the `load_rate_limit_rules` docstring's "all four rules … eight env vars" wording.
- [ ] **Step 4: Update the other test fixtures** so the cloud import env contains the four new vars.
- [ ] **Step 5: Run** `python -m pytest tests/ --ignore=tests/postgres -q` — Expected: PASS.
- [ ] **Step 6: Commit** `feat(rate-limit): rules for auth e-mails; redact Brevo keys and one-time codes`

---

### Task 6: The two endpoints

**Files:**
- Create: `backend/routers/auth_email.py`
- Modify: `backend/main.py:41` (import) and `:170` (mount directly after the auth router, same `prefix="/api"`, no CSRF dependency), plus a startup line that builds the mailer once
- Test: `backend/tests/test_auth_email_routes.py`

**Interfaces:**
- Consumes: `render`, `EmailKind`, `normalize_language` (Task 1); `load_mailer_settings`, `BrevoTransport`, `ConsoleTransport`, `EmailTransport`, `EmailSendError` (Task 3); `ActionLinkBuilder`, `AccountNotFound`, `ActionLinkError` (Task 4); rules `auth_email`, `auth_email_target` (Task 5); `routers.auth.get_identity_verifier`, `routers.auth.AuthAPIError`; `beta_access.normalize_email`; `audit.record_audit_event`; `database.set_rls_context`.
- Produces:
  - `router = APIRouter(prefix="/auth/email", tags=["auth"])`
  - `@dataclass(frozen=True) class Mailer`: `transport: EmailTransport`, `links: ActionLinkBuilder`
  - `get_mailer(request: Request) -> Mailer | None` — reads `request.app.state.portfyl_mailer`
  - `build_mailer(env, edition) -> Mailer | None` — called once in `main.py`, result stored on `app.state.portfyl_mailer`
  - `RESET_MIN_SECONDS = 1.5`; module attributes `_now = time.monotonic`, `_sleep = time.sleep` (tests patch them)
  - HTTP contract (frontend relies on it):
    - `POST /api/auth/email/verification` body `{"id_token": str, "lang": str | null}` → `202 {"status":"sent"}` · `200 {"status":"already_verified"}` · `401 {"code":"authentication_required"}` · `429 {"code":"rate_limit_exceeded","rule":…}` · `503 {"code":"email_unavailable"}` · `503 {"code":"email_send_failed"}`
    - `POST /api/auth/email/password-reset` body `{"email": str, "lang": str | null}` → `202 {"status":"accepted"}` · `429` (per IP only) · `503 {"code":"email_unavailable"}`

Order inside each handler (§5.3):

*Verification:* IP rule (dependency) → mailer `None` or `not transport.available()` → `503 email_unavailable` → verify token (failure → 401) → already verified → 200 → target rule `verify:<uid>` (cloud only; exceeded → the normal 429) → link → render → send; `ActionLinkError` or `EmailSendError` → ERROR log + `503 email_send_failed`.

*Reset:* IP rule (dependency) → mailer check → `503` → `start = _now()` → normalize address → target rule `reset:<address>` (cloud only; `RateLimitExceeded` is caught and skips the send) → link (`AccountNotFound` → skip silently; `ActionLinkError` → ERROR log) → render → send (`EmailSendError` → ERROR log) → on success: if a `User` with that e-mail exists, `set_rls_context(db, user_id=user.id, workspace_id=None)`, `record_audit_event(action="auth.email.sent", target_type="user", target_id=str(user.id), metadata={"kind": "password_reset", "lang": lang})`, commit → `_sleep(max(0, RESET_MIN_SECONDS - (_now() - start)))` → `202`. The sleep runs on every path after the mailer check, including the skipped ones. `RateLimitUnavailable` from the target rule is treated like "skip" for reset and propagates for verification. No database session is touched before the outbound calls, so no pooled connection is held while waiting on Firebase or Brevo.

Log lines: `log.info("auth_email kind=%s lang=%s outcome=%s message_id=%s", …)`; failures use `log.error` with `error=<exception class or reason code>`. Logger name `portfyl.auth_email`.

Request bodies: `email: str` and `id_token: str` with `max_length` (320 and 4096); `lang: str | None = None`. No `EmailStr` (no validator dependency); an address that is not an address simply finds no account.

- [ ] **Step 1: Write the failing tests.** Build the mini-app like `tests/test_rate_limit_routes.py::TestAuthSessionRateLimit._app` (same exception handlers, `dependency_overrides` for `get_db`, `get_identity_verifier`, `get_mailer`). Fakes: `FakeTransport` (records sends, optional error, `available` flag), `FakeLinks` (returns `https://app.portfyl.com/auth/action?mode=…&oobCode=C&lang=<lang>`, optional error), `FakeVerifier` (returns a `VerifiedIdentity`). Patch `auth_email._sleep` to record its argument and `auth_email._now` to a controllable clock. Required tests, one assertion group each:

```python
# verification
def test_verification_sends_to_the_token_address_in_the_requested_language()
    # body lang "cs-CZ"; identity email "jana@example.com"; body also carries {"email": "evil@x.cz"} which is ignored
    # → 202 {"status": "sent"}; transport.sent == [("jana@example.com", "verify_email")]; rendered subject is the Czech one
def test_verification_already_verified_sends_nothing()            # 200 {"status": "already_verified"}
def test_verification_bad_token_is_401()                          # {"code": "authentication_required"}
def test_verification_without_mailer_is_503_email_unavailable()   # get_mailer → None
def test_verification_unhealthy_mailer_is_503_email_unavailable() # transport.available() False; verifier never called
def test_verification_send_failure_is_503_email_send_failed()     # EmailSendError and ActionLinkError, parametrized
def test_verification_fourth_request_for_one_uid_is_429()         # cloud app, rule auth_email_target limit=3
def test_verification_unknown_lang_falls_back_to_english()        # lang "xx", None, "c"*500 → 202, English subject

# password reset
def test_reset_sends_for_an_existing_account()                    # 202 {"status": "accepted"}; one send, tag "password_reset"
@pytest.mark.parametrize("case", ["unknown", "link_error", "send_error", "target_limit_hit", "not_an_address"])
def test_reset_answers_the_same_for_every_outcome(case)           # status 202, body exactly {"status": "accepted"}
def test_reset_normalizes_the_address_for_the_limit()             # " Jana@Example.com " then "jana@example.com" ×3 with limit=3 → 3 sends total, all 202
def test_reset_always_waits_for_the_minimum_time()                # clock advances 0.4 s during the handler → _sleep called with ≈1.1; for "unknown" (0.0 s) → 1.5
def test_reset_without_mailer_is_503_before_reading_the_body()    # body {"email": "x"} → 503 email_unavailable
def test_reset_ip_limit_is_429()                                  # cloud app, rule auth_email limit=1
def test_reset_writes_an_audit_row_only_for_a_portfyl_user()      # with test_user's e-mail → one AuditLog action "auth.email.sent", metadata == {"kind": "password_reset", "lang": "en"}; unknown Portfyl user → none
def test_reset_logs_never_contain_the_address_or_code(caplog)     # run success + send_error; "jana@example.com" and "oobCode" absent from caplog.text
def test_limits_are_skipped_in_the_local_edition()                # local app, 10 requests → all 202
```

- [ ] **Step 2: Run** `python -m pytest tests/test_auth_email_routes.py -v` — Expected: FAIL, module missing.
- [ ] **Step 3: Implement `routers/auth_email.py`** in the order above.
- [ ] **Step 4: Wire `main.py`:** `app.state.portfyl_mailer = auth_email.build_mailer(os.environ, PORTFYL_EDITION)` next to the other `app.state` assignments, and `app.include_router(auth_email.router, prefix="/api")` after the auth router. `build_mailer` must not raise for any environment (wrap construction; log ERROR and return `None`).
- [ ] **Step 5: Run** `python -m pytest tests/test_auth_email_routes.py tests/test_csrf_coverage.py tests/test_event_loop_not_blocked.py tests/test_edition_routes.py -v` — Expected: all PASS. If `test_csrf_coverage` flags the two routes, exclude `/api/auth/email/` there the same way `/api/auth/` routes are excluded and say why in the test's docstring (no session cookie is used).
- [ ] **Step 6: Run** the whole fast suite `python -m pytest tests/ --ignore=tests/postgres -q` — Expected: PASS.
- [ ] **Step 7: Commit** `feat(auth): send verification and password-reset e-mails through Brevo`

---

### Task 7: Frontend sends through the backend first

**Files:**
- Create: `frontend/src/auth/authEmail.js`, `frontend/src/auth/authEmail.test.js`
- Modify: `frontend/src/api.js` (next to `exchangeSession`, line ~165), `frontend/src/pages/Register.jsx`, `VerifyEmail.jsx`, `Login.jsx`, `ForgotPassword.jsx` (import lines only), and the mocks in `AuthPages.test.jsx`, `VerifyEmail.test.jsx`, `Register.intent.test.jsx`

**Interfaces:**
- Consumes: the HTTP contract in Task 6; `initialLanguage` from `../i18n/languages`; `sendVerificationEmail`, `sendPasswordReset` from `./firebase` (renamed on import to `firebaseSendVerificationEmail`, `firebaseSendPasswordReset`).
- Produces:
  - `api.js`: `requestVerificationEmail(idToken, lang)` → `POST /auth/email/verification`; `requestPasswordResetEmail(email, lang)` → `POST /auth/email/password-reset`; both resolve to `response.data`
  - `authEmail.js`: `sendVerificationEmail(user): Promise<void>`, `sendPasswordReset(email): Promise<void>`

Rules (§5.8): `202` and `already_verified` resolve. `429` → verification rejects with `Object.assign(new Error("auth/too-many-requests"), { code: "auth/too-many-requests" })` (pages already map that code); reset resolves. Any other failure (no response, `401`, `404`, `5xx`, `user.getIdToken()` rejecting) → call the Firebase function and return its result or rejection.

- [ ] **Step 1: Write the failing tests** (`vi.mock("../api")`, `vi.mock("./firebase")`, `vi.mock("../i18n/languages")` returning `"cs"`)

```js
const httpError = (status, data = {}) => Object.assign(new Error("http"), { response: { status, data } });
const user = { getIdToken: vi.fn(() => Promise.resolve("tok")) };

it("verification goes to the backend with the token and language", async () => {
  api.requestVerificationEmail.mockResolvedValue({ status: "sent" });
  await sendVerificationEmail(user);
  expect(api.requestVerificationEmail).toHaveBeenCalledWith("tok", "cs");
  expect(firebase.sendVerificationEmail).not.toHaveBeenCalled();
});
it("already_verified counts as success", …);
it.each([401, 404, 500, 503])("verification falls back to Firebase on %i", async (status) => {
  api.requestVerificationEmail.mockRejectedValue(httpError(status));
  await sendVerificationEmail(user);
  expect(firebase.sendVerificationEmail).toHaveBeenCalledWith(user);
});
it("verification falls back on a network error and when the token cannot be read", …);   // Error without response; getIdToken rejects
it("verification surfaces 429 as auth/too-many-requests without falling back", async () => {
  api.requestVerificationEmail.mockRejectedValue(httpError(429));
  await expect(sendVerificationEmail(user)).rejects.toMatchObject({ code: "auth/too-many-requests" });
  expect(firebase.sendVerificationEmail).not.toHaveBeenCalled();
});
it("a failing fallback rejects with Firebase's error", …);
it("reset goes to the backend with the address and language", …);                          // ("jana@example.com", "cs")
it.each([404, 500, 503])("reset falls back to Firebase on %i", …);
it("reset swallows 429 without falling back", …);
```

Add to `AuthPages.test.jsx`: `ForgotPassword` shows the same "If an account exists…" message when `authEmail.sendPasswordReset` resolves and when it rejects.

- [ ] **Step 2: Run** `cd frontend && npx vitest run src/auth/authEmail.test.js` — Expected: FAIL, module missing.
- [ ] **Step 3: Implement** the two `api.js` functions and `authEmail.js`.
- [ ] **Step 4: Switch the four pages' imports** of `sendVerificationEmail` / `sendPasswordReset` from `../auth/firebase` to `../auth/authEmail`; update the page tests' mocks to mock `../auth/authEmail` for those two names.
- [ ] **Step 5: Run** `npm test` and `npm run test:cloud` — Expected: PASS.
- [ ] **Step 6: Commit** `feat(auth): request auth e-mails from the backend, Firebase as fallback`

---

### Task 8: The action page follows the e-mail's language

**Files:**
- Modify: `frontend/src/i18n/I18nProvider.jsx` (context value), `frontend/src/pages/AuthAction.jsx:25-32` (`readActionParams`) and its mount effect
- Test: `frontend/src/pages/AuthAction.test.jsx`, `frontend/src/i18n/I18nProvider.test.jsx`

**Interfaces:**
- Produces: the i18n context gains `previewLanguage(code)` — applies a language for this visit without saving (`apply(code, { save: false })`); the default context value has a no-op. Expose it through the same accessor that exposes `setLanguage` today.
- `readActionParams` also returns `lang`.

Rule (§5.8): on mount, if `lang` is an app language (`isAppLanguage`) and `hasSavedLanguage()` is false → `previewLanguage(lang)`. Otherwise nothing.

- [ ] **Step 1: Write the failing tests**

```js
// I18nProvider.test.jsx
it("previewLanguage switches the language without saving it", async () => {
  // render provider with initial "en", call previewLanguage("cs") → t("Confirm") becomes "Potvrdit";
  // localStorage.getItem("portfyl_language") stays null
});

// AuthAction.test.jsx — mock ../i18n/languages hasSavedLanguage
it("uses the link's language on a device with no saved language", …);      // ?lang=cs, hasSavedLanguage false → previewLanguage called with "cs"
it("keeps a saved language", …);                                            // hasSavedLanguage true → not called
it.each(["xx", "", null])("ignores an unknown lang (%s)", …);              // not called
```

- [ ] **Step 2: Run** `npx vitest run src/pages/AuthAction.test.jsx src/i18n/I18nProvider.test.jsx` — Expected: the new tests FAIL.
- [ ] **Step 3: Implement.** Read `lang` in the same single read of the query that already exists (before the address bar is cleaned).
- [ ] **Step 4: Run** `npm test` — Expected: PASS.
- [ ] **Step 5: Commit** `feat(auth): show the e-mail action page in the e-mail's language`

---

### Task 9: Runbook, docs, full verification

**Files:**
- Modify: `deploy/cloudrun.md` (deploy command at line 257 and the note at ~275; new section "Portfyl e-mails" after "E-mail action links"; the sentence at lines 664-668), `CLAUDE.md` ("Login" bullet), `frontend/src/auth/firebase.js:1-8` (header comment: Firebase no longer owns delivery when the mailer is on)

- [ ] **Step 1: `deploy/cloudrun.md`.**
  - Add to the first-deploy command: `--set-secrets` entry `PORTFYL_BREVO_API_KEY=portfyl-brevo-api-key:latest`, and env vars `RATE_LIMIT_AUTH_EMAIL_LIMIT=10,RATE_LIMIT_AUTH_EMAIL_WINDOW_SECONDS=600,RATE_LIMIT_AUTH_EMAIL_TARGET_LIMIT=3,RATE_LIMIT_AUTH_EMAIL_TARGET_WINDOW_SECONDS=900,PORTFYL_EMAIL_APP_URL=https://app.portfyl.com`. Change "eight `RATE_LIMIT_*` values" to twelve.
  - New section "Portfyl e-mails": what it is (one paragraph); the secret (`portfyl-brevo-api-key`, already created and readable by `portfyl-runtime` since 2026-11-15); the one-off update command for the running service:
    `gcloud run services update $SERVICE --region $REGION --update-secrets="PORTFYL_BREVO_API_KEY=portfyl-brevo-api-key:latest" --update-env-vars="RATE_LIMIT_AUTH_EMAIL_LIMIT=10,RATE_LIMIT_AUTH_EMAIL_WINDOW_SECONDS=600,RATE_LIMIT_AUTH_EMAIL_TARGET_LIMIT=3,RATE_LIMIT_AUTH_EMAIL_TARGET_WINDOW_SECONDS=900,PORTFYL_EMAIL_APP_URL=https://app.portfyl.com"`
    with the warning that the four `RATE_LIMIT_AUTH_EMAIL_*` values must be on the service **before or with** the first revision that contains this code; that Brevo's "block unknown IP addresses" must stay off (Cloud Run has no fixed outbound IP); rollback (`--remove-secrets=PORTFYL_BREVO_API_KEY`: the app then sends Firebase's e-mails); the first-send checklist copied from §11; how to unblock an address in Brevo.
- [ ] **Step 2: `CLAUDE.md`.** In "Login": one sentence that verification and reset e-mails are sent by `backend/emails/` through Brevo, with the Firebase client call as fallback, and that copy lives in `backend/emails/catalog.py` + `locales/`. Point to the spec.
- [ ] **Step 3: Run everything.**
  - `cd backend && python -m pytest tests/ --ignore=tests/postgres -q` — PASS
  - `docker compose -f deploy/docker-compose.postgres-test.yml up -d --wait && python -m pytest tests/postgres/ -q` — PASS (no schema change; this proves the rate-limit buckets and the audit row still work under real RLS)
  - `cd frontend && npm test && npm run test:cloud && npm run build && npm run build:cloud` — PASS
- [ ] **Step 4: See a real e-mail locally.** With `PORTFYL_EMAIL_TRANSPORT=console` in the local backend env, start the dev servers (`start.bat`), register a test account at `http://localhost:5173/register` with the app set to Czech: the backend console prints the Czech subject and a `http://localhost:5173/auth/action?...` link; opening it shows "Your e-mail is verified". Then forgot-password → console link → new password → log in. Then write one rendered HTML e-mail to a file (`python -c` calling `render`) and open it in the browser at 375px and 1280px width: no raw URL, button visible, logo loads.
- [ ] **Step 5: Commit** `docs(deploy): runbook for Portfyl's own e-mails`
- [ ] **Step 6: Stop here.** Do not merge, push or deploy. Report: what is on `feat/own-emails`, the test counts, and that production needs (a) part A deployed, (b) the service update command from Step 1, (c) the §11 checklist with a real inbox.
