# Portfyl sends its own e-mails through Brevo — design (2026-11-15)

**Status:** wave 1 (verification, password reset) is implemented on `main`. Wave 2 (account notices) is implemented on the integration branch `feat/own-emails-w2` (plan `docs/superpowers/plans/2026-11-16-portfyl-own-emails-wave2.md`), not yet merged to `main` or deployed; its first-real-send check (section 11 and `deploy/cloudrun.md`) is still open. Wave 3 is design only.
**Input:** part B of `docs/superpowers/plans/2026-11-15-branded-auth-emails-handoff.md`.
**Visual preview of every e-mail (Czech and English):**
https://claude.ai/artifact/Pwh4j9VRmpfhcFPNWCj3iV (private to the founder).

## 1. Intent

Today Firebase Authentication writes and sends Portfyl's verification and
password-reset e-mails. Firebase refuses any change to their subject or text
(`EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED`), so they show a long raw link, come in
one language and do not look like Portfyl. They are the first thing a new
user sees after registering.

Portfyl will write and send these e-mails itself: a branded message with one
button, in the user's app language, sent through Brevo. The same sender then
carries every other account e-mail Portfyl needs (security notices, trial,
plan, broker sync), which the backend cannot send at all today.

## 2. Goals, non-goals, anti-goals

**Goals**

- Verification and password-reset e-mails are Portfyl's own: branded HTML, a
  button instead of a raw URL, one of the 9 app languages.
- One sending path (`backend/emails/`) that later e-mails reuse without new
  infrastructure decisions.
- Every e-mail Portfyl will send has a defined structure and copy now
  (section 8), so later waves only wire triggers.
- Registration and password reset keep working when the new path is missing,
  misconfigured or broken (no key, bad key, old backend, backend error):
  Firebase's built-in sending stays as the fallback. A full Brevo outage is
  not covered by any fallback, because Firebase's own e-mails also go out
  through Brevo.

**Non-goals**

- Marketing e-mails, newsletters, digests. Portfyl sends account messages only.
- Receipts, invoices, failed-payment notices: Stripe Managed Payments (Link)
  is the merchant of record and sends those.
- Price-alert e-mails. Alerts stay on Discord.
- Changing how codes work. Firebase still issues and checks the one-time
  codes (`oobCode`); `/auth/action` still applies them.
- An e-mail-change flow. Portfyl has no "change my e-mail" feature, so the
  `email_change` e-mail is reserved, not designed (the Python Admin SDK has no
  `generate_verify_and_change_email_link`; it would need a direct REST call).

**Anti-goals** (these would make it a failure even if e-mails arrive)

- The forgot-password endpoint reveals whether an account exists.
- An unauthenticated caller can make Portfyl send mail to arbitrary addresses
  without a tight limit.
- An e-mail address, a link or a one-time code ends up in logs or audit rows.
- A deploy of this feature can break login for existing users.

## 3. Facts this design rests on

Verified on 2026-11-15 unless marked otherwise.

- `mail.portfyl.com` is authenticated in Brevo: TXT `brevo-code:…`, DKIM
  `brevo1._domainkey` / `brevo2._domainkey` CNAMEs to Brevo, DMARC
  `v=DMARC1; p=none` on `_dmarc.mail.portfyl.com`. Sender
  `noreply@mail.portfyl.com` is already in use (Firebase → Brevo SMTP).
- The backend has no mailer. `backend/notifications.py` defines a
  `NotificationTransport` protocol and `deliver_notification_outbox`, backed by
  the `notification_outbox` table; nothing implements the transport and no job
  calls the delivery function.
- `firebase-admin` and `httpx` are already dependencies. The runtime service
  account has `roles/firebaseauth.admin` (it already calls `delete_user`).
- Admin SDK `generate_email_verification_link(email, settings)` and
  `generate_password_reset_link(email, settings)` call
  `accounts:sendOobCode` with `returnOobLink: true` and return the link
  without sending anything. A missing user raises `UserNotFoundError` /
  `EmailNotFoundError` (both `firebase_admin.exceptions.NotFoundError`).
  Rate-limit errors are `ResourceExhaustedError` subclasses. Daily quota
  without billing: 10,000 verification links, 1,500 reset links.
- Brevo transactional API: `POST https://api.brevo.com/v3/smtp/email`, header
  `api-key`, JSON body `sender`, `to`, `replyTo`, `subject`, `htmlContent`,
  `textContent`, `tags`, `headers`; success is `201 {"messageId": …}`. The API
  key is a different credential from the SMTP key Firebase uses, and it has no
  scopes (treat it as full access to the Brevo account).
- There is no usable "app origin" setting to reuse. `PORTFYL_APP_URL` exists
  but belongs to billing (`backend/billing_config.py`, Stripe return URLs),
  defaults to `http://localhost:5173`, may be unset while billing is off, and
  the billing runbook sets it to the apex `https://portfyl.com`, where `/api`
  fails closed. E-mail links therefore get their own setting,
  `PORTFYL_EMAIL_APP_URL`.
- Cloud Run runs in project `portfyl-prod-f6shqb`; Firebase Auth lives in
  `portfyl-cloud-fstxby`. Link generation uses the same Admin SDK credential
  path as the existing `delete_user` call, so it should work, but it is on the
  first-send checklist.
- Rate limiting (`backend/rate_limit.py`) is cloud-only, fixed-window, stored
  in `rate_limit_buckets` under an HMAC of the identity. **Every rule's two env
  vars are required at import time in the cloud edition**; a missing one stops
  the service from starting.
- `AuditLog.actor_user_id` is `NOT NULL` and references `users`. A person who
  has registered in Firebase but not yet verified has no Portfyl `User` row.
- The app language is device-level (`localStorage` `portfyl_language`); the
  backend stores no language.
- Czech UI copy uses formal address (vykání).

**Not verified, must be checked on the first real send (section 11):**
whether Brevo rewrites links for click tracking on this account, whether
Brevo adds its own `List-Unsubscribe` header, the free-plan daily cap
(reported as 300 e-mails), and the code lifetimes (widely reported as 1 hour
for password reset and 3 days for verification, not in Firebase's docs).

## 4. Approaches considered

1. **Firebase keeps sending through Brevo SMTP (today).** Zero work. Cannot
   change text, button or language. This is the problem being solved.
2. **Templates stored in Brevo, backend sends `templateId` + params.** Copy
   lives in Brevo's web editor: 12 e-mails × 9 languages edited by hand,
   outside git, with no tests, and the design is tied to one provider.
3. **Fully own tokens: Portfyl issues and checks its own verification and
   reset codes.** Removes Firebase's codes entirely, but re-implements
   security-critical flows that Firebase already does correctly, and needs new
   tables. Too much risk for what is a presentation problem.
4. **Chosen: backend generates the Firebase link with the Admin SDK, renders
   its own template from code, sends through the Brevo HTTP API.** Copy is in
   git and tested, the security of the codes stays with Firebase, and the
   provider is one small class.

Two smaller choices inside approach 4:

- **Brevo HTTP API, not the SMTP relay.** `httpx` is already there, the API
  returns a message id and structured errors, uses port 443 and supports tags.
  SMTP would need `smtplib` plumbing and gives less back.
- **Auth e-mails are sent inside the request, not through the outbox.** The
  user is waiting for the e-mail, a resend button already exists, and the
  outbox needs a `workspace_id` and `user_id` that an unverified person does
  not have. Lifecycle e-mails (wave 3) do use the outbox.

## 5. Design of wave 1 (verification and password reset)

### 5.1 Flow

```
Register / Resend            ForgotPassword
      │ id_token, lang             │ email, lang
      ▼                            ▼
POST /api/auth/email/verification  POST /api/auth/email/password-reset
      │                            │
      ├─ rate limit (IP, then uid / e-mail)
      ├─ Admin SDK: generate link → take oobCode
      ├─ build Portfyl URL  {PORTFYL_EMAIL_APP_URL}/auth/action#mode=…&oobCode=…&lang=…
      ├─ render (kind, lang) → subject, html, text
      └─ Brevo API send
```

If the backend answers "unavailable", the frontend falls back to today's
Firebase client call, so the user still gets an e-mail (the old plain one).

### 5.2 The link

The backend does not use the link Firebase returns as-is. It parses
`oobCode` out of it and builds its own URL from `PORTFYL_EMAIL_APP_URL`:

`{PORTFYL_EMAIL_APP_URL}/auth/action#mode=verifyEmail&oobCode=<code>&lang=<lang>`
(`mode=resetPassword` for the reset). For verification it also adds
`continueUrl={PORTFYL_EMAIL_APP_URL}/login?verified=1`, which `AuthAction.jsx`
already accepts as same-origin.

The parameters are in the URL **fragment** (`#…`), not the query (changed by
the 2026-11-16 review fixes; wave 1 first shipped `?…`). A browser never sends
the fragment to a server, so the one-time code does not reach Cloud Run or
Cloudflare request logs. `AuthAction.jsx` reads the fragment first (when it
holds a `mode` or an `oobCode`) and the query second, so links already sent
and Firebase's own fallback e-mails, which keep the code in the query, still
open. Residual: those fallback e-mails still put the code in request logs
until the fallback is removed (5.10 step 5). If a mail client or Brevo's click
tracking turns out to drop the fragment, revert the one commit that builds
fragment links; the page keeps reading both forms.

Consequences:

- The link no longer depends on the Firebase project's single action URL.
  Dev e-mails point at `http://localhost:5173`, production ones at
  `https://app.portfyl.com` (handoff open question 4 is solved).
- `apiKey` is not needed in the link: `AuthAction.jsx` calls the Firebase SDK
  with the app's own configured key.
- No short links (handoff open question 5): the URL is hidden behind a button,
  and a redirect service would be one more thing that can fail.

`ActionCodeSettings(url=…)` passed to the Admin SDK must use a domain on
Firebase's authorized-domains list (`app.portfyl.com` and `localhost` are).

### 5.3 Endpoints

Both live in the auth router (`/api/auth/...`, no CSRF dependency, like
`/auth/session`: they use no session cookie). Both are plain `def`.

**`POST /api/auth/email/verification`** — body `{ "id_token": str, "lang": str }`

| Case | Response |
|---|---|
| Mailer not configured | `503 {"code":"email_unavailable"}` |
| ID token rejected (invalid, or Firebase could not be reached to check it; the verifier does not tell these apart) | `401 {"code":"authentication_required"}` |
| Address already verified | `200 {"status":"already_verified"}` |
| Per-IP or per-uid limit hit | `429 rate_limit_exceeded` + `Retry-After` |
| Firebase or Brevo call fails | `503 {"code":"email_send_failed"}` |
| Sent | `202 {"status":"sent"}` |

The caller proves who they are with a Firebase ID token (an unverified user
cannot have a Portfyl session). The e-mail address is taken from the token,
never from the body, so nobody can send verification mail to an address they
have not registered. Reuse `FirebaseIdentityVerifier.verify_id_token`.

**`POST /api/auth/email/password-reset`** — body `{ "email": str, "lang": str }`

| Case | Response |
|---|---|
| Mailer not configured (checked before looking at the address) | `503 {"code":"email_unavailable"}` |
| Per-IP limit hit | `429 rate_limit_exceeded` + `Retry-After` |
| Anything else: unknown address, disabled account, a missing / non-string / over-long / implausible `email`, per-address limit hit, Firebase or Brevo error, sent | `202 {"status":"accepted"}` |

Anti-enumeration rules:

- The response body and status are identical whether or not the account
  exists. A send failure is logged, not returned.
- The per-address limit is counted before the lookup and, when exceeded,
  silently skips the send.
- The e-mail is sent inside the request, not after the response. Cloud Run
  throttles CPU once a response is returned, so work after the response is
  not reliable (the reason scheduled work runs as external jobs).
- The handler does not return before a fixed minimum time (1.5 s, measured
  from the start of the request) so the slower "account exists" path is not
  visible in the response time. The real work is normally well under that
  (one Firebase call, one Brevo call). Above the floor the answer is rounded
  up to the next 0.5 s step (work of 1.6 s answers at 2.0 s). Residual: a
  difference smaller than one step can still cross a step boundary; accepted,
  because registration already tells a caller that an address is taken.
- `lang` and the address are validated the same way on both paths (malformed
  input gets the same `202`). `email` is accepted as any JSON value: a
  missing, non-string or over-long (more than 320 characters after trimming)
  value is an invalid address, answered `202` with no limiter call, no
  Firebase call and no send. Residual: a body that is not a JSON object at all
  still gets FastAPI's `422`; that cannot depend on an account.
- **Every reset makes exactly one Brevo call.** A path that does not send
  (invalid address, per-address limit hit or limiter down, unknown account,
  Firebase error, an unexpected error before the send) makes one health probe
  instead (`GET /v3/account`, same timeouts, sends nothing). So both kinds of
  address cost one Firebase call and one Brevo call, and the health flag below
  moves the same way for every address (see "Health flag").

When a send fails (Firebase or Brevo error) the user is told nothing, so the
failure must be visible to the operator and must not last:

- Every failed send is logged at ERROR (kind and error type only), which
  reaches Sentry when `SENTRY_DSN` is set.
- **Health flag.** After a Brevo authentication failure (`401`/`403`) or
  three outage-type failures in a row (timeout, network error, `429`, `5xx`),
  the mailer reports itself unavailable for 5 minutes (per instance, in
  memory). A message Brevo itself rejects (any other `4xx`, for example an
  address it will not accept) is not counted: otherwise anyone able to cause
  such a rejection could switch e-mail off for everyone. During that time both endpoints answer
  `503 email_unavailable` before looking at the request, and the frontend
  falls back to Firebase. A revoked or wrong key therefore degrades to the old
  e-mails within a few requests instead of silently losing every reset.
- **The flag moves the same for every address.** If only real sends moved the
  flag, then while Brevo is failing only a reset for an *existing* account
  would move it, and `202` turning into `503 email_unavailable` would reveal
  the account. The probe of a non-sending reset is therefore counted exactly
  like a failed send (`401`/`403` at once; timeout, network error, `429`,
  `5xx` toward the three). A successful probe changes nothing: only a real
  send proves that sending works, so it neither resets the failure count nor
  switches the mailer back on. The verification endpoint never probes.
  Residual: if Brevo's send endpoint fails while its account endpoint works (a
  partial outage), the probe succeeds and the difference remains for that
  period; a wrong or revoked key and a full outage, the realistic cases, are
  closed. Rejected alternative: reset sends do not move the flag at all (no
  probe needed, but a revoked key would silently lose every reset until a
  verification e-mail happened to fail).

Behaviour kept from Firebase: an account that signs in with Google only still
gets a reset link (it lets the person set a password).

### 5.4 Rate limits

Two new rules in `rate_limit._RULE_ENV_VARS`:

| Rule | Identity | Default |
|---|---|---|
| `auth_email` | client IP | 10 per 600 s |
| `auth_email_target` | `verify:<uid>` or `reset:<normalized e-mail>` | 3 per 900 s |

The per-address limit cannot lock a person out of resetting: when it is hit,
that address has already received three valid links in the last 15 minutes.
It only stops an inbox from being flooded.

`auth_email` uses the existing `rate_limit("auth_email", by="ip")` dependency.
`auth_email_target` is consumed inside the handler with
`rate_limit.consume_rate_limit(...)` (the bucket key is an HMAC, so no address
is stored). Normalize the address with `beta_access.normalize_email`.
Non-cloud editions skip both, as the existing dependency does.

**Deploy ordering:** the four new env vars
(`RATE_LIMIT_AUTH_EMAIL_LIMIT`, `RATE_LIMIT_AUTH_EMAIL_WINDOW_SECONDS`,
`RATE_LIMIT_AUTH_EMAIL_TARGET_LIMIT`,
`RATE_LIMIT_AUTH_EMAIL_TARGET_WINDOW_SECONDS`) must be set in the same
`gcloud run deploy` that ships the code, or the new revision will not start.
Every test that lists the rule env vars or patches `RATE_LIMIT_RULES` needs
the new names: at least `test_csrf_coverage`, `test_rate_limit_config` (it
asserts the exact rule set), `test_main_rate_limit_wiring`,
`test_edition_routes` and `test_cloud_gate`. Grep for `RATE_LIMIT_` rather
than trusting this list.

### 5.5 Language

The frontend sends the app's current language with each request
(`initialLanguage()` order: saved choice → landing choice → browser → English).
The backend accepts exactly the 9 codes in `frontend/src/i18n/languages.js`
(`cs en de fr es it pt pl nl`) and uses English for anything else. This
answers handoff open question 1. No database change in wave 1.

### 5.6 Backend modules

```
backend/emails/
  __init__.py
  catalog.py      EmailKind (str enum), EmailContent, English source copy
  locales/        cs.py de.py fr.py es.py it.py pt.py pl.py nl.py
  render.py       render(kind, lang, params) -> RenderedEmail(subject, html, text)
  transport.py    EmailTransport protocol, BrevoTransport, ConsoleTransport,
                  transport_from_env()
  links.py        Admin SDK link → oobCode → Portfyl action URL
  service.py      send_verification_email(...), send_password_reset(...)
backend/routers/auth_email.py   the two endpoints, mounted with the auth router
```

- `links.py` wraps the Admin SDK behind an injectable client, like
  `FirebaseIdentityVerifier`, so tests never touch Firebase.
- `BrevoTransport.send(to, rendered, tag)` posts with `httpx` (connect 3 s,
  total 5 s, no retry; the user has a resend button) and raises
  `EmailSendError` on any non-201 or network error. It also keeps the health
  flag described in 5.3.
- `ConsoleTransport` prints subject and link to stdout. It is selectable only
  outside the cloud edition (`PORTFYL_EMAIL_TRANSPORT=console`) so a developer
  can click a link without any Brevo key.
- `BrevoTransport` also implements `notifications.NotificationTransport`
  (`send(recipient=, kind=, payload=)`) so wave 3 can pass it to
  `deliver_notification_outbox` unchanged.
- Call `database.release_connection` before the Firebase and Brevo calls if a
  session is open (CLAUDE.md: no slow outbound call while holding a connection).

### 5.7 Configuration and secrets

| Setting | Kind | Value |
|---|---|---|
| `PORTFYL_BREVO_API_KEY` | Secret Manager → `--update-secrets` (same pattern as `PORTFYL_ETORO_APP_KEY`) | Brevo v3 API key |
| `PORTFYL_EMAIL_FROM` | env | `noreply@mail.portfyl.com` |
| `PORTFYL_EMAIL_FROM_NAME` | env | `Portfyl` |
| `PORTFYL_EMAIL_REPLY_TO` | env | `support@portfyl.com` |
| `PORTFYL_EMAIL_APP_URL` | env, new | `https://app.portfyl.com` in production; defaults to `http://localhost:5173` outside the cloud edition |
| `PORTFYL_EMAIL_TRANSPORT` | env, optional | `console` in dev only |

In the cloud edition the mailer counts as configured only when the key is set
**and** `PORTFYL_EMAIL_APP_URL` is an `https` URL. A missing or wrong value
never stops the service from starting (that would break login); it logs an
ERROR at startup and leaves the mailer off.

No key → the mailer is "not configured" → both endpoints answer
`503 email_unavailable` → the frontend uses Firebase. This is the normal
state of the local edition and of any dev machine without a key, and it is
the kill switch in production (remove the secret, redeploy).

Add `xkeysib-…` (Brevo key shape) and `oobCode=<value>` to
`logging_setup._REDACTION_PATTERNS`.

### 5.8 Frontend

New module `frontend/src/auth/authEmail.js` (kept out of `firebase.js`, which
has no static imports on purpose):

- `sendVerificationEmail(user)`: `user.getIdToken()` →
  `POST /auth/email/verification`. `202` and `already_verified` are success.
  `429` surfaces the existing "Too many attempts" message. **Any other
  failure** (`401`, `404` from an old backend during a rolling deploy, `5xx`,
  network error) → `firebase.sendVerificationEmail(user)`. Falling back on
  `401` too is deliberate: the backend cannot tell a bad token from a
  Firebase hiccup, and Firebase's own call makes the final decision.
- `sendPasswordReset(email)`: `POST /auth/email/password-reset`; `202` is
  success, `429` is swallowed like today, any other failure →
  `firebase.sendPasswordReset(email)`.

`Register.jsx`, `VerifyEmail.jsx`, `Login.jsx` and `ForgotPassword.jsx` switch
their import to the new module; nothing else in them changes. `/auth` is
already in `PORTFOLIO_AGNOSTIC_PREFIXES`. No new UI strings are expected.

`AuthAction.jsx` gains one behaviour: it reads `lang` from the link. When the
device has no saved language (`hasSavedLanguage()` is false) and `lang` is one
of the 9 codes, the page is shown in that language for this visit, without
saving it. Someone who opens the e-mail on another device then sees the page
in the same language as the e-mail. A saved choice on the device always wins.

### 5.9 Logging and audit

- One structured log line per attempt: kind, language, outcome, Brevo
  `messageId`. Never the address, the link or the code.
- Audit row `auth.email.sent` (`metadata: {kind, lang}`) only when a Portfyl
  `User` exists for the address (password reset of an existing user), because
  `actor_user_id` is required. Verification e-mails are log-only.
- A password reset is sent to, and shows, the address **as typed** (trimmed
  only): ` Jana@Example.com ` gets its e-mail at `Jana@Example.com`. The
  normalized form (`jana@example.com`) is used only for the per-address limit
  bucket and the `User` lookup of the audit row.
- The handler ends its database transaction before it waits out the minimum
  response time, so no pooled connection is held during the wait.

### 5.10 Rollout

1. Part A of the handoff is live first: `/auth/action` must exist in
   production before any Portfyl-built link is sent.
2. Founder creates the Brevo API key; it goes into Secret Manager.
3. Deploy with the secret and the four rate-limit env vars.
4. Test with a real inbox (section 11). Roll back by removing the secret.
5. The Firebase fallback stays in the frontend until wave 1 has run in
   production for two weeks without a fallback being needed; removing it is a
   separate small change.

The Firebase action-URL switch from part A (step 4 there) is still worth doing
so the fallback e-mails also land on `/auth/action`, but wave 1 does not
depend on it.

## 6. Template model

Every e-mail is the same eight parts. An e-mail's definition is only text;
layout is written once in `render.py`.

```python
@dataclass(frozen=True)
class EmailContent:              # one e-mail in one language
    subject: str
    preheader: str               # inbox preview line, hidden in the body
    heading: str
    paragraphs: tuple[str, ...]  # 1–2
    bullets: tuple[str, ...] = ()
    facts: tuple[tuple[str, str], ...] = ()   # (label, value)
    button: str | None = None    # label; the URL comes from the caller
    note: str = ""               # grey line under the button
    footer_reason: Literal["account", "address"] = "account"
```

- Placeholders are `{name}` (`{email}`, `{date}`, `{plan}`, `{price}`,
  `{broker}`, `{datetime}`). The only markup is `**bold**`. Every value is
  HTML-escaped. Rendering raises on a missing or unknown placeholder.
- English is the source in `catalog.py`. Each `locales/<code>.py` exports the
  same kinds. A test asserts every language has every kind, the same optional
  parts and the same placeholders (the backend twin of
  `frontend/src/i18n/messages.test.js`). Glossary rule from `languages.js`
  applies: plan names, Dashboard, broker names stay in English.
- Dates are formatted per language by a small formatter in the locale file
  (no new dependency). Wave 1 uses no dates.

**Layout (HTML part)**

| # | Part | Rule |
|---|---|---|
| 1 | Preheader | hidden block first in `<body>`, padded so body text does not leak into the preview |
| 2 | Logo | `https://portfyl.com/portfyl-mark.png`, shown 44×44, `alt="Portfyl"`, centred |
| 3 | Heading | 22px / 700, `#3A352C` |
| 4 | Text | 15px / 1.6; the account address in bold |
| 5 | Facts (optional) | label/value rows in a `#ECE0CF` well, 12px radius |
| 6 | Button (optional) | one per e-mail, pill, `#6D7048` background, white 15px / 600 text |
| 7 | Note | 13px, `#6B6353` |
| 8 | Footer | why the e-mail came, `support@portfyl.com`, "Portfyl · portfyl.com" (no operator identification line; founder's decision 2026-11-15) |

- Page background `#F3E8DA`, card `#FDF9F3` with 20px radius, max width 480px.
  These are the `DESIGN.md` §3 values written as literals, because e-mail
  clients do not support CSS variables. `render.py` is the one place they may
  be hardcoded; name them as constants that cite the token.
- Table layout, inline CSS, `role="presentation"`, `bgcolor` attributes next
  to CSS backgrounds, system font stack (web fonts do not load in mail
  clients). Button is a padded `<a>` in a coloured cell; square corners in
  Outlook for Windows are accepted (no VML).
- `<html lang="…">`, `<meta name="color-scheme" content="light">` and
  `supported-color-schemes` light only. The e-mail has one look.
- The HTML never shows a raw URL. The plain-text part carries the full link
  on its own line, plus the same heading, text, facts, note and footer.
- The whole HTML stays under 20 KB and reads correctly with images blocked.

## 7. Waves

| Wave | E-mails | Needs | When | Status |
|---|---|---|---|---|
| 1 | `verify_email`, `password_reset` | sections 5–6; no migration | now, after part A is deployed | implemented |
| 2 | `password_changed`, `account_deletion_scheduled`, `account_deleted` | wave 1 sender; a way to learn about a password change (below) | right after wave 1 | implemented on `feat/own-emails-w2` (migration `0028_password_changed_seen`); not merged or deployed; real-send check open |
| 3 | `beta_invite`, `welcome`, `trial_ending`, `trial_ended`, `plan_activated`, `plan_ended`, `broker_reconnect` | stored user language (`users.language`, additive migration), an outbox delivery job | together with the free-trial plan and payments go-live | not started |

Each wave gets its own implementation plan. Notes that shape those plans:

- **`password_changed`** cannot be triggered by the page that sets the new
  password: a Firebase code can be used directly against Firebase, bypassing
  Portfyl. The reliable signal is on the server: at `/auth/session`, compare
  Firebase's "password last changed" time for the user with the last value
  Portfyl saw; when it moved, send the notice and revoke the user's other
  Portfyl sessions. Today a password reset does **not** end existing Portfyl
  sessions; wave 2 closes that. Needs one nullable column on `users`.
- **`account_deleted`** is sent by the purge job once the purge has committed,
  with the address and language read before the user is deleted (they are gone
  afterwards), directly through the transport, not the outbox. It is not sent
  before the delete because Firebase's `delete_user` runs inside the purge
  transaction: a rollback would leave an account that was already announced as
  deleted. A crash between the commit and the send loses this one notice.
- **`account_deletion_scheduled`** is sent inside
  `schedule_workspace_deletion`'s request, like wave 1.
- **`beta_invite`** is sent by `manage_beta invite --send --lang cs`.
- **Wave 3** writes `NotificationOutbox` rows (deduplicated by
  `deduplication_key`) and adds a job pass that calls
  `deliver_notification_outbox` with `BrevoTransport`. The migration is a
  hotspot: sequence it after the free-trial plan's `0027_free_trial`.
- **`trial_*`** supersede "Trial rules" item 8 ("No e-mails are sent") in
  `docs/superpowers/plans/2026-11-15-portfyl-landing-redesign-free-trial.md`
  once wave 3 exists. Until then the in-app reminder stands.

## 8. E-mail catalogue

`{…}` are placeholders. EN is the source; CS is the reviewed Czech. The other
seven languages are translated during implementation. Footer reason:
*address* = "You got this e-mail because someone entered this address at
Portfyl." / „Tento e-mail jste dostali, protože někdo zadal tuto adresu v
Portfylu."; *account* = "You got this e-mail because it is about your Portfyl
account." / „Tento e-mail jste dostali, protože se týká vašeho účtu Portfyl."
Second footer line: "Need help? support@portfyl.com" / „Potřebujete pomoc?
support@portfyl.com".

### Wave 1

**`verify_email`** — after password registration and on every resend.
Button → `/auth/action#mode=verifyEmail`. Footer: address.

| Part | EN | CS |
|---|---|---|
| Subject | Confirm your e-mail for Portfyl | Potvrďte svůj e-mail pro Portfyl |
| Preheader | One click and your account is ready. | Stačí jedno kliknutí a účet je připravený. |
| Heading | Confirm your e-mail | Potvrďte svůj e-mail |
| Text | Welcome to Portfyl! Confirm **{email}** to finish setting up your account. | Vítejte v Portfylu! Potvrďte adresu **{email}** a dokončete tím založení účtu. |
| Button | Confirm e-mail | Potvrdit e-mail |
| Note | If you didn't create a Portfyl account, you can ignore this e-mail. | Pokud jste si účet v Portfylu nezakládali, tento e-mail můžete ignorovat. |

**`password_reset`** — after the forgot-password form, only if the account
exists. Button → `/auth/action#mode=resetPassword`. Footer: address.

| Part | EN | CS |
|---|---|---|
| Subject | Reset your Portfyl password | Obnovení hesla k Portfylu |
| Preheader | Choose a new password. The link works for 1 hour. | Nastavte si nové heslo. Odkaz platí 1 hodinu. |
| Heading | Reset your password | Obnovte si heslo |
| Text | We got a request to reset the password for **{email}**. Choose a new one with the button below. The link works for 1 hour. | Dostali jsme žádost o obnovení hesla k účtu **{email}**. Nové heslo si nastavíte tlačítkem níže. Odkaz platí 1 hodinu. |
| Button | Choose a new password | Nastavit nové heslo |
| Note | If you didn't ask for this, you can ignore this e-mail. Your password stays the same. | Pokud jste o obnovení nežádali, tento e-mail můžete ignorovat. Vaše heslo zůstává stejné. |

The "1 hour" sentence stays only if the test in section 11 confirms it;
otherwise drop it from both the preheader and the text.

### Wave 2

*Status: implemented on `feat/own-emails-w2`, not yet merged or sent for real. As built, the language comes from the request (`lang` in the `/auth/session` body and the deletion request, English fallback) and the deletion request's language is kept in the workspace deletion state for `account_deleted`; no stored user language, which stays a wave 3 item.*

**`password_changed`** — when Portfyl sees the password changed.
Button → `/forgot-password`. Footer: account.

| Part | EN | CS |
|---|---|---|
| Subject | Your Portfyl password was changed | Heslo k účtu Portfyl bylo změněno |
| Preheader | If that was you, there's nothing more to do. | Pokud jste to byli vy, nemusíte nic dělat. |
| Heading | Your password was changed | Heslo bylo změněno |
| Text | The password for **{email}** was just changed. If that was you, there's nothing more to do. | Heslo k účtu **{email}** bylo právě změněno. Pokud jste to byli vy, nemusíte nic dělat. |
| Facts | When: {datetime} | Kdy: {datetime} |
| Button | That wasn't me | To jsem nebyl/a já |
| Note | The button lets you reset the password right away. If it doesn't work, write to support@portfyl.com. | Tlačítkem si heslo hned obnovíte. Kdyby to nešlo, napište nám na support@portfyl.com. |

**`account_deletion_scheduled`** — when deletion is requested (30-day grace,
`DELETION_GRACE_DAYS`). Button → Settings, cancel deletion. Footer: account.

| Part | EN | CS |
|---|---|---|
| Subject | Your Portfyl account will be deleted on {date} | Váš účet Portfyl bude smazán {date} |
| Preheader | You can change your mind until then. | Do té doby si to můžete rozmyslet. |
| Heading | Account deletion is scheduled | Smazání účtu je naplánováno |
| Text | You asked us to delete your Portfyl account and all its data. You can change your mind until the date below. | Požádali jste o smazání účtu Portfyl včetně všech dat. Do uvedeného data si to můžete rozmyslet. |
| Facts | Account: {email} · We delete it on: {date} | Účet: {email} · Smažeme ho: {date} |
| Button | Keep my account | Ponechat účet |
| Note | If you didn't ask for this, cancel it with the button and change your password. | Pokud jste o smazání nežádali, zrušte ho tlačítkem a změňte si heslo. |

**`account_deleted`** — when the purge job deletes the account. No button.
Footer: account.

| Part | EN | CS |
|---|---|---|
| Subject | Your Portfyl account has been deleted | Váš účet Portfyl byl smazán |
| Preheader | The last e-mail about this account. | Poslední e-mail k tomuto účtu. |
| Heading | Your account is deleted | Účet je smazaný |
| Text 1 | We deleted the account **{email}** and its data, as you asked. This is the last e-mail we send about it. | Účet **{email}** i jeho data jsme na vaši žádost smazali. Je to poslední e-mail, který vám k němu posíláme. |
| Text 2 | You're welcome to come back and start a new one any time. | Kdykoli se můžete vrátit a založit si nový. |
| Note | Questions about this? Write to support@portfyl.com. | Máte k tomu otázku? Napište nám na support@portfyl.com. |

### Wave 3

**`beta_invite`** — `manage_beta invite --send`. Button → `/register`.
Footer: address. The facts row is omitted when the invite has no expiry.

| Part | EN | CS |
|---|---|---|
| Subject | Your invitation to the Portfyl private beta | Pozvánka do uzavřené bety Portfylu |
| Preheader | Your access is ready. | Váš přístup je připravený. |
| Heading | You have access to Portfyl | Máte přístup do Portfylu |
| Text | Portfyl shows your whole portfolio in one place: performance, allocation and dividends. Create your account with **{email}**. The invitation is tied to this address. | Portfyl ukáže celé vaše portfolio na jednom místě: výkonnost, rozložení i dividendy. Účet si založte s adresou **{email}**, pozvánka je vázaná právě na ni. |
| Facts | Invitation valid until: {date} | Pozvánka platí do: {date} |
| Button | Create account | Založit účet |
| Note | If you're not interested in Portfyl, you can ignore this e-mail. | Pokud o Portfyl nestojíte, tento e-mail můžete ignorovat. |

**`welcome`** — once, after the first session of a newly created account
(`account_created` in `exchange_session`). Button → the app. Footer: account.
The facts row appears only when the workspace has an active trial.

| Part | EN | CS |
|---|---|---|
| Subject | Welcome to Portfyl | Vítejte v Portfylu |
| Preheader | Three steps to see your whole portfolio. | Tři kroky k přehledu o celém portfoliu. |
| Heading | Welcome to Portfyl | Vítejte v Portfylu |
| Text | Your account is ready. This is the quickest way to see your whole portfolio in one place: | Účet je připravený. Takhle nejrychleji uvidíte celé portfolio na jednom místě: |
| Bullets | Connect a broker or import a CSV. · Check your allocation and performance. · Follow your dividends month by month. | Připojte brokera nebo nahrajte CSV. · Podívejte se na rozložení a výkonnost. · Sledujte dividendy měsíc po měsíci. |
| Facts | Pro trial until: {date} | Zkušební verze Pro do: {date} |
| Button | Open Portfyl | Otevřít Portfyl |
| Note | (none) | (žádná) |

**`trial_ending`** — 3 days before the trial ends, only without a
subscription. Button → `/pricing`. Footer: account.

| Part | EN | CS |
|---|---|---|
| Subject | Your Portfyl Pro trial ends in 3 days | Zkušební verze Portfyl Pro končí za 3 dny |
| Preheader | Nothing is deleted. Your account moves to Free. | Nic se nemaže, účet přejde na tarif Free. |
| Heading | Your trial ends on {date} | Zkušební verze končí {date} |
| Text | Your Pro trial ends on **{date}**. After that your account moves to the Free plan. Nothing is deleted. Data above the Free limits stays readable but can't be edited. | Vaše zkušební verze tarifu Pro končí **{date}**. Poté účet přejde na tarif Free. Nic se nemaže, data nad limity tarifu Free zůstanou jen ke čtení. |
| Button | See plans | Zobrazit tarify |
| Note | We don't have your card, so nothing is charged on its own. | Nemáme vaši kartu, takže se nic nestrhne samo. |

**`trial_ended`** — the day the trial ends without a subscription.
Button → `/pricing`. Footer: account.

| Part | EN | CS |
|---|---|---|
| Subject | Your Portfyl Pro trial has ended | Zkušební verze Portfyl Pro skončila |
| Preheader | Your data stays. Your account is now on Free. | Vaše data zůstávají, účet je teď na tarifu Free. |
| Heading | You're now on the Free plan | Teď používáte tarif Free |
| Text | Your Pro trial ended today. Your data is safe and you can still view all of it. A paid plan brings back automatic sync and everything above the Free limits. | Zkušební verze tarifu Pro dnes skončila. Vaše data jsou v bezpečí a dál si je můžete prohlížet. Automatickou synchronizaci a vše nad limity tarifu Free vrátí placený tarif. |
| Button | Choose a plan | Vybrat tarif |
| Note | You can stay on Free for as long as you like. | Tarif Free můžete používat, jak dlouho chcete. |

**`plan_activated`** — when `billing_sync` first projects an active
subscription. Button → the app. Footer: account.

| Part | EN | CS |
|---|---|---|
| Subject | Your Portfyl {plan} plan is active | Tarif Portfyl {plan} je aktivní |
| Preheader | Thank you. Everything is unlocked. | Děkujeme, vše je odemčené. |
| Heading | {plan} is active | Tarif {plan} je aktivní |
| Text | Thank you! Your account is now on the **{plan}** plan. | Děkujeme! Váš účet teď běží na tarifu **{plan}**. |
| Facts | Plan: {plan} · Price: {price} a month, VAT included · Renews: every month | Tarif: {plan} · Cena: {price} měsíčně vč. DPH · Obnovuje se: každý měsíc |
| Button | Open Portfyl | Otevřít Portfyl |
| Note | Receipts and payments are handled by Link (Stripe), our payment partner. You manage the subscription in Settings. | Účtenky a platby zajišťuje náš platební partner Link (Stripe). Předplatné spravujete v Nastavení. |

**`plan_ended`** — when a subscription ends and the workspace falls back to
Free. Button → `/pricing`. Footer: account.

| Part | EN | CS |
|---|---|---|
| Subject | Your Portfyl {plan} plan has ended | Tarif Portfyl {plan} skončil |
| Preheader | Your account is now on Free. Nothing is deleted. | Účet je teď na tarifu Free, nic se nemaže. |
| Heading | Your plan has ended | Váš tarif skončil |
| Text | Your **{plan}** plan has ended and your account is now on Free. Nothing is deleted. Data above the Free limits stays readable but can't be edited. | Tarif **{plan}** skončil a účet je teď na tarifu Free. Nic se nemaže, data nad limity tarifu Free zůstanou jen ke čtení. |
| Facts | Ended: {date} | Skončil: {date} |
| Button | See plans | Zobrazit tarify |
| Note | You can come back any time. | Vrátit se můžete kdykoli. |

**`broker_reconnect`** — when a broker connection keeps failing to sync; at
most once per connection per 7 days. Button → Settings, broker connections.
Footer: account.

| Part | EN | CS |
|---|---|---|
| Subject | {broker} stopped syncing with Portfyl | {broker} se přestal synchronizovat s Portfylem |
| Preheader | Reconnecting takes about a minute. | Znovu připojit ho trvá asi minutu. |
| Heading | Reconnect {broker} | Připojte znovu {broker} |
| Text | We can't sync your **{broker}** connection. Your portfolio in Portfyl may be out of date. | Připojení **{broker}** se nám nedaří synchronizovat. Portfolio v Portfylu proto nemusí být aktuální. |
| Facts | Last successful sync: {date} | Poslední úspěšná synchronizace: {date} |
| Button | Reconnect broker | Znovu připojit brokera |
| Note | Most often the API key at the broker expired or was revoked. | Nejčastěji u brokera vypršel nebo byl zrušen API klíč. |

## 9. Tests (wave 1)

Fast suite only; Firebase and Brevo are always faked.

- `render`: every kind × every language renders; values are escaped (an
  address like `a<b>@x.cz`); no raw URL in the HTML; the URL is in the text
  part; missing placeholder raises; HTML under 20 KB.
- Locale parity: every language has every kind, same optional parts, same
  placeholders.
- `links`: `oobCode` is taken from a sample Firebase link; the built URL uses
  `PORTFYL_EMAIL_APP_URL`; a link without a code raises.
- `BrevoTransport`: request shape (header, sender, reply-to, tag), 201 →
  message id, 400/401/429/timeout → `EmailSendError`; the key never appears in
  the exception text.
- Verification endpoint: each row of the table in 5.3; the address comes from
  the token, not the body.
- Password-reset endpoint: identical status and body for existing, unknown and
  disabled accounts and for a Brevo failure; per-address limit skips the send
  silently; the minimum response time is applied on every path (inject the
  clock and the sleep).
- Rate-limit config tests include the two new rules.
- `tests/test_event_loop_not_blocked.py` still passes (both endpoints are
  `def`).
- Health flag: a `401` from Brevo, or three failures in a row, makes both
  endpoints answer `503 email_unavailable` until the 5 minutes pass (inject the
  clock); one success resets the failure count.
- Mailer configuration: key without an `https` `PORTFYL_EMAIL_APP_URL` in the
  cloud edition leaves the mailer off and does not raise at import.
- Frontend: `authEmail.test.js` for success, each fallback trigger, `429`, and
  that `ForgotPassword` shows the same message for every outcome;
  `AuthAction.test.jsx` for `lang` with and without a saved language.

Added by the 2026-11-16 review fixes:

- `BrevoTransport.probe`: request shape; `401` switches the mailer off at
  once; three outage answers switch it off; a successful probe does not heal
  the flag; a rejected (`400`) probe is not counted; never raises; no key in
  the logs.
- Password-reset endpoint: a missing / `null` / non-string / over-long `email`
  is `202` with nothing sent; with Brevo answering `401`, the next request is
  `503` whichever path the first one took (existing, unknown, invalid,
  limited, Firebase error), and likewise after three `503`s of any mix;
  exactly one Brevo call per request; the typed address is the recipient while
  the normalized one keys the limit and the audit lookup; the 0.5 s step; no
  open transaction during the wait.
- `links`: the built URL has no query and its fragment carries the parameters;
  the text part has the full link. `AuthAction.test.jsx`: fragment links,
  fragment over query, fallback to the query, a clean address bar.
- PostgreSQL suite (`tests/postgres/test_auth_email_audit.py`), with the
  handler's session running as `portfyl_runtime`: the `auth.email.sent` row is
  written under forced RLS, is visible to its user and not to another, is not
  written for an address without a Portfyl user, and neither it nor a
  rate-limit bucket key contains the address.

## 10. Risks

| Risk | What we do |
|---|---|
| Brevo rewrites links for click tracking (a per-message off switch is not documented; reported as Enterprise-only) | Check the `href` in the first real e-mail. If rewritten: look for the account-level setting, ask Brevo support to disable tracking for transactional mail, and if neither works decide between accepting it (the code is single-use and short-lived) and swapping the provider (one class). |
| Brevo adds `List-Unsubscribe`; a person who unsubscribes may stop getting transactional mail | Check the headers of the first e-mail. Add to the support runbook: how to remove an address from Brevo's blocked list. A webhook for `unsubscribed` / `hard_bounce` / `blocked` events is a wave 3 item. |
| Free plan cap (reported 300 e-mails a day), shared with the Firebase fallback | Enough for the private beta. Move to a paid Brevo plan before public sign-up opens. |
| The Brevo API key has no scopes | Secret Manager only, never in the repo or logs; redaction pattern added. Rotate if exposed. |
| New required rate-limit env vars stop the service from starting | Same deploy command sets them; runbook updated in the same change. |
| `app.portfyl.com` sits behind Cloudflare Access | Unchanged by this work, but a link opened on a device without an Access session meets the Access login first. Acceptable for the private beta, must be solved before public sign-up (handoff open question 3). |
| Abuse: someone registers Firebase accounts with other people's addresses to send them mail | Already possible today with Firebase's own sender. Now additionally limited per IP and per account. |

## 11. First real send: checklist

1. Register a test account → the e-mail arrives from `Portfyl
   <noreply@mail.portfyl.com>`, in the app's language, button works,
   `/auth/action` shows "Your e-mail is verified". This also proves the
   production service account can generate links in the Firebase project.
2. In the raw message: is the button's `href` Portfyl's URL or a Brevo
   tracking URL? Is there a `List-Unsubscribe` header? Do SPF, DKIM and DMARC
   show `pass`?
3. Forgot password → e-mail → new password → log in.
4. Leave a reset link for 61 minutes, then open it: if it still works, remove
   the "1 hour" sentence.
5. Forgot password for an address with no account: same page message, no
   e-mail.
6. Remove the secret on a test revision: registration still sends Firebase's
   e-mail.
7. Gmail (web and phone), Outlook, Seznam: layout holds, readable with images
   off and in the client's dark mode.
8. The link in the received e-mail has `#` after `/auth/action` and opens the
   page from Gmail web, Gmail on a phone, Outlook and Seznam; the Cloud Run
   request log of that revision shows `/auth/action` without a code.
9. If a mail client or Brevo's click tracking drops the fragment: revert the
   commit that builds fragment links and redeploy (the page still reads query
   links).

## 12. What the founder has to do

All done on 2026-11-15:

1. Brevo API key created and stored as Secret Manager secret
   `portfyl-brevo-api-key` in `portfyl-prod-f6shqb`; `portfyl-runtime` can
   read it. Brevo's "block unknown IP addresses" is switched off (Cloud Run
   has no fixed outbound IP).
2. Replies go to `support@portfyl.com` (confirmed).
3. The footer stays "Portfyl · portfyl.com" with no operator line (confirmed).

## 13. Decisions made here (the author's calls, open to correction)

- Wave 1 is worth doing now: it is about a day of work, the e-mail is the
  first contact with every new user, and wave 3 needs the same sender.
- Language comes from the app, English is the fallback.
- No short links.
- Templates live in code, not in Brevo.
- Firebase stays as the fallback for at least two weeks of production use.
- The e-mail has a light look only.
- Czech uses formal address.
- 12 e-mails in three waves; `email_change` and price alerts are out.
- E-mails are sent inside the request; a failing mailer switches itself off
  for 5 minutes so the Firebase fallback takes over.
- E-mail links use their own `PORTFYL_EMAIL_APP_URL`, not billing's
  `PORTFYL_APP_URL`.
- The action page follows the e-mail's language on a device with no saved
  language.

Found on the way, outside this design: the billing runbook sets
`PORTFYL_APP_URL=https://portfyl.com` (the apex, where `/api` fails closed)
for Stripe return URLs. Check it before payments go live.

## 14. Left to the builder

- Exact HTML of the layout (within section 6) and the plain-text formatting.
- The seven remaining translations.
- Whether `auth_email.py` is its own router file or part of `routers/auth.py`.
- How `ConsoleTransport` prints.
- Where the frontend reads the current language (`initialLanguage()` or the
  provider's state).
- `deploy/cloudrun.md` section "Portfyl e-mails": secret, env vars, rollback,
  the checklist above.
