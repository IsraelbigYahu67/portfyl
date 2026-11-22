---
type: hub
layer: backend
tags: [arch/hub]
generated: false
---
# Emails

Portfyl sends its own transactional e-mails through Brevo: the verification e-mail, the password-reset e-mail, and short account notices. They are branded and written in the user's language (nine languages, English as the source and fallback). Firebase can only send its own fixed-template e-mails, so Portfyl asks Firebase Admin for a one-time code and builds the link itself. If the backend cannot send, the browser falls back to Firebase's own sending, so users are never locked out.

## How it works
- **Copy.** [[emails.catalog]] defines each `EmailKind` (`verify_email`, `password_reset`, `password_changed`, `account_deletion_scheduled`, `account_deleted`), the placeholders and the English text. Other languages are modules in [[emails.locales (folder)]] (cs, de, es, fr, it, nl, pl, pt) with a `LOCALE` attribute. `account_deletion_scheduled` still exists in the catalog but nothing sends it since deletion became immediate.
- **Layout.** [[emails.render]] turns content plus parameters into subject, HTML and plain text. It escapes every value, supports only `**bold**` as markup, and is the one place where DESIGN.md colours are written as literal hex (e-mail clients have no CSS variables).
- **Links.** [[emails.links]] asks Firebase Admin for a verification or reset link, keeps only its `oobCode`, and builds Portfyl's own link `/auth/action#mode=...&oobCode=...` on the configured app URL. The browser page [[pages.AuthAction]] finishes the action using [[auth.firebase]].
- **Transport.** [[emails.transport]] sends through the Brevo HTTP API, with a health flag that turns off sending after repeated failures, or through a console stand-in when `PORTFYL_EMAIL_TRANSPORT=console` (local). Sender, reply-to and app URL come from `PORTFYL_EMAIL_*` settings. If no key is set the mailer is simply off.
- **Endpoints.** [[routers.auth_email]] has three unauthenticated routes under `/api/auth/email`: `/verification`, `/password-reset` and `/password-reset-done`. They have no session, so they are protected by rate limits instead, per IP and per target (`auth_email` and `auth_email_target`, see [[rate_limit]]).
  - The password-reset answer never reveals whether an account exists: same status and body for every case, with a timing floor.
  - `/password-reset-done` is called by the reset page after Firebase accepted a new password, so Portfyl ends the user's other sessions at once (see [[Auth and sessions]]).
- **Notices.** [[emails.notify]] `send_account_notice` renders one e-mail and hands it to Brevo after the user's action is committed. It never raises and never rolls anything back. It is used for `password_changed` ([[routers.auth]]) and `account_deleted` ([[account_deletion]], [[routers.account]]).
- **Privacy rules.** No address, link, one-time code or key may reach a log line, exception text or audit metadata; logs carry a kind, a language and a reason code only. The `oobCode` is also redacted by [[logging_setup]].
- **Browser fallback.** [[auth.authEmail]] tries the backend first. Only a 429 stops the fallback (the backend refused on purpose); any other failure falls back to Firebase's own e-mail.

## Key code
- [[emails.catalog]]: kinds, languages, English copy
- [[emails.locales (folder)]]: translations
- [[emails.render]]: HTML and text layout
- [[emails.links]]: Portfyl action links from Firebase codes
- [[emails.transport]]: Brevo and console transports, mailer settings
- [[emails.notify]]: best-effort account notices
- [[routers.auth_email]]: the three e-mail endpoints
- [[auth.authEmail]]: frontend client with Firebase fallback
- [[pages.AuthAction]]: page that completes verify and reset links
- [[pages.VerifyEmail]], [[pages.ForgotPassword]]: pages that request e-mails

## Related hubs
- [[Auth and sessions]]
- [[Account deletion and data lifecycle]]
- [[Secrets and security]]
- [[Backend]]
- [[Frontend structure]]
- [[Portfyl]]

## Docs
- [[superpowers/specs/2026-11-15-portfyl-own-emails-design]]: the design (read first)
- [[superpowers/plans/2026-11-15-branded-auth-emails-handoff]]: why Firebase templates could not be branded
- [[superpowers/plans/2026-11-16-portfyl-own-emails-wave2]]: password-changed and deletion notices
- [[superpowers/plans/2026-11-17-portfyl-own-emails-session-handoff]]: where the work stood
- [[superpowers/specs/2026-09-05-portfyl-rate-limiting-design]]: the limits that protect these routes
