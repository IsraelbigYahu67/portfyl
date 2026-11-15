# Branded auth e-mails — handoff of open work (2026-11-15)

**Status:** input for a plan, not a plan. Everything below is unfinished or
undecided work from the 2026-11-15 session. Read it whole before planning; the
"Facts" section is verified, the "Open questions" are not decided.

## What the founder asked for

Firebase's verification e-mail shows a long raw link
(`https://portfyl-cloud-fstxby.firebaseapp.com/__/auth/action?mode=verifyEmail&oobCode=…&apiKey=…&continueUrl=…&lang=en`),
and clicking it opens Firebase's generic white "Verify Email Address" page.
The founder wants:

1. a link that looks clean — ideally hidden behind text such as
   "Ověř svůj e-mail" / "Confirm e-mail", still pointing to the same action;
2. a Portfyl-branded page after the click, with a clean address bar.

## What is done

- **Commit `1107717` on branch `feat/branded-auth-domain`** (one commit ahead
  of local `main`, not merged, not pushed, not deployed):
  - `frontend/src/pages/AuthAction.jsx` — Portfyl's own action handler at
    `/auth/action`: `verifyEmail` (applyActionCode), `resetPassword`
    (verifyPasswordResetCode → new-password form → confirmPasswordReset, min 8
    chars like Register), `recoverEmail` (checkActionCode + applyActionCode).
    It reads the query once, then `navigate("/auth/action", {replace})` so
    the address bar is clean. "Continue" follows `continueUrl` only when it is
    same-origin or `http://localhost|127.0.0.1` (`safeContinueTarget`),
    otherwise `/login?verified=1`.
  - `frontend/src/App.jsx` `AuthGate` renders it **before** the auth checks,
    so it works signed in or out, without waiting for `/auth/me`.
  - `frontend/src/api.js` `PUBLIC_AUTH_PATHS` gained `/auth/action` (no 401
    bounce to /login).
  - `frontend/src/auth/firebase.js`: `applyEmailActionCode`,
    `checkEmailActionCode`, `verifyResetCode`, `confirmNewPassword`; error
    copy for `auth/expired-action-code` and `auth/invalid-action-code`.
  - 17 new strings translated into all 8 dictionaries.
  - `frontend/src/pages/AuthAction.test.jsx` (9 tests). Full `npm test`,
    `npm run test:cloud`, `npm run build`, `npm run build:cloud` were green.
  - Checked by hand against the real Firebase project on localhost:5173: an
    invalid code shows the translated error page, address bar becomes
    `/auth/action`. A **successful** verify and a real password reset were
    not clicked through end-to-end (needs a fresh e-mail link).
  - `deploy/cloudrun.md` → new section "E-mail action links" (switch steps
    and rollback).
- **Firebase config change already live** (project `portfyl-cloud-fstxby`):
  `senderDisplayName = "Portfyl"` on `verifyEmailTemplate` and
  `resetPasswordTemplate`. Nothing else in the Firebase config was changed.

## Facts found (verified)

- Firebase Auth sends mail through **custom SMTP: Brevo**
  (`smtp-relay.brevo.com:587`, sender `noreply@mail.portfyl.com`). Portfyl's
  backend has **no mailer of its own** (no SMTP/Brevo/Resend code in
  `backend/`).
- The project's action URL (`notification.sendEmail.callbackUri`) is still
  `https://portfyl-cloud-fstxby.firebaseapp.com/__/auth/action`. It is **one
  value for the whole project**, so dev (localhost) e-mails use it too.
- **Firebase refuses edits to template subject and body**: the Identity
  Toolkit `PATCH …/config` returns `400 EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED`
  for `subject` and `body`; only `senderDisplayName` was accepted. So point 1
  of the request (link hidden behind a button, custom text) **cannot be done
  with Firebase-sent e-mails**. A one-language template is all Firebase would
  have allowed anyway (no per-user language).
- The current stored template bodies contain mojibake (`didnâ€™t`); it
  rendered fine in Gmail but is a sign the template text is not ours to fix.
- **`app.portfyl.com` is behind Cloudflare Access** (unauthenticated requests
  get `302` to `portfyl.cloudflareaccess.com`). An action link opened on a
  device/browser without an Access session will hit the Access login before
  `/auth/action`.
- `https://portfyl.com/portfyl-mark.png` is public (200, PNG) — usable as the
  logo in e-mails (Gmail does not show SVG).
- Local `main` is **21 commits ahead of `origin/main`** (not pushed). Whether
  production currently runs that code is unknown — check before deploying.
- A backup of the full Firebase Auth config taken before any change exists
  only in a temporary scratchpad (may be gone). The only value that matters
  for rollback is the callbackUri above.
- A ready e-mail design exists (warm palette `#F3E8DA` background, `#FDF9F3`
  card, `#6D7048` pill button, logo, short copy, no raw URL). It was rendered
  and approved visually by me, not yet by the founder. Copy used:
  - Verify — subject "Confirm your e-mail for Portfyl", heading "Confirm your
    e-mail", text "Welcome to Portfyl! Confirm **%EMAIL%** to finish setting up
    your account.", button "Confirm e-mail", note "If you didn't create a
    Portfyl account, you can ignore this e-mail."
  - Reset — subject "Reset your Portfyl password", heading "Reset your
    password", text "We got a request to reset the password for **%EMAIL%**.
    Choose a new one with the button below.", button "Choose a new password",
    note "If you didn't ask for this, you can ignore this e-mail. Your
    password stays the same."

## Open work

### A. Ship the action page (small, ordered, outward-facing)

1. Decide how `feat/branded-auth-domain` reaches `main` and whether the 21
   unpushed `main` commits go out in the same deploy (they include onboarding
   broker connect and Google popup sign-in — see the memory/plan files for
   those).
2. Deploy (routine redeploy in `deploy/cloudrun.md`).
3. [x] Check `https://app.portfyl.com/auth/action?mode=verifyEmail&oobCode=x`
   shows Portfyl's "This link didn't work" page. Done 2026-11-15, anonymously
   (fresh browser context, no Access session).
4. [ ] **OPEN: owner must do this in the console.** The API refused
   (`PATCH …/config?updateMask=notification.sendEmail.callbackUri` returned
   `400 EMAIL_TEMPLATE_UPDATE_NOT_ALLOWED` on 2026-11-15; config unchanged,
   still `https://portfyl-cloud-fstxby.firebaseapp.com/__/auth/action`).
   Console: Authentication → Templates → pencil → Customize action URL.
   **Only then** switch the action URL to `https://app.portfyl.com/auth/action`
   (console: Authentication → Templates → Customize action URL; or API field
   `notification.sendEmail.callbackUri`). Switching first breaks every link.
5. [ ] End-to-end (owner, real mailbox): register a test account → click link → "Your e-mail is
   verified"; the original tab (VerifyEmail polling) should continue on its
   own. Then forgot-password → link → set new password → log in.
6. [x] Cloudflare Access in front of `/auth/action`: decided and done
   2026-11-15 as a path-scoped Bypass application `Portfyl public auth action`
   (`c8492312-38ef-45b2-a015-2ac6a9672db3`) for `/auth/action`, `/assets/*`,
   `/theme-init.js`, `/portfyl-mark.svg`, `/logo.png` only; `/`, `/login`,
   `/register` and `/api/*` stay behind Access (open question 3 resolved for
   the action page only). See `docs/operations/private-beta-access.md`.

### B. Portfyl sends its own auth e-mails (the real fix for point 1)

> **Designed on 2026-11-15:** see
> `docs/superpowers/specs/2026-11-15-portfyl-own-emails-design.md` (approach,
> endpoints, all 12 e-mail structures in three waves). It answers open
> questions 1, 2, 4 and 5 below. The sketch that follows is the original input.

Goal: branded HTML e-mail, a button instead of a raw URL, in the user's app
language, sent by Portfyl through Brevo. Sketch to evaluate, not decided:

- Backend generates the link with the Firebase Admin SDK
  (`auth.generate_email_verification_link(email, ActionCodeSettings(url=…))`,
  `generate_password_reset_link`) — this already uses the project action URL,
  so it lands on `/auth/action`. Optionally rewrite to a shorter Portfyl URL.
- Sends via Brevo (transactional API or the same SMTP relay). Needs its own
  credential stored like the other secrets (KMS/Fernet / Secret Manager —
  see Workstream D, `deploy/cloudrun.md` "Store secrets").
- New endpoints (sync `def`, never DB work on the event loop — CLAUDE.md):
  - send verification: the caller is not a Portfyl session yet (unverified
    users can't get one), so authenticate with a fresh Firebase ID token;
    rate-limit per uid/e-mail.
  - send password reset: unauthenticated; must stay **anti-enumeration**
    (same response whether or not the account exists — see
    `ForgotPassword.jsx`) and rate-limited per IP and e-mail.
- Frontend call sites that would switch from the Firebase client SDK:
  `firebase.js` `sendVerificationEmail` (used by `Register.jsx`,
  `VerifyEmail.jsx` resend, `Login.jsx` resend) and `sendPasswordReset`
  (`ForgotPassword.jsx`).
- Templates in 9 languages; the language must reach the backend (request
  body or stored user preference).
- Audit-log the sends (existing audit log), redact e-mails in logs.
- Tests: unit (link generation mocked, Brevo mocked), anti-enumeration,
  rate limit; fits the fast suite. No migration needed unless rate limiting
  is stored in the DB (then it is a hotspot — see "Parallel session safety").
- Deliverability: confirm SPF/DKIM/DMARC for `mail.portfyl.com` in Brevo and
  Cloudflare DNS before switching.
- Keep Firebase's built-in sending as fallback until the new path is proven.

## Open questions for the plan

1. **E-mail language**: founder chose English for now (Firebase allows one
   template). With B, send in the user's app language? Which language for
   someone who never picked one (browser guess)?
2. **Is B worth doing now** vs. after payments go-live? It is roughly a day
   of backend + frontend work plus secrets and DNS checks.
3. **Cloudflare Access**: should `/auth/action` (and `/login`, `/register`)
   bypass Access, or is Access on the whole host intended for the private
   beta? A beta user opening the e-mail on their phone will see the Access
   login first.
4. **Dev vs prod action URL**: after the switch, dev e-mails also open the
   prod page. The page then offers "Continue" back to localhost, which works,
   but a code is applied on prod's page. Acceptable, or use a separate
   Firebase project for dev?
5. Short links (`portfyl.com/v/abc`) — wanted at all once the URL is hidden
   behind a button?

## Pointers

- Code: `frontend/src/pages/AuthAction.jsx`, `frontend/src/auth/firebase.js`,
  `frontend/src/App.jsx` (`AuthGate`), `frontend/src/api.js`.
- Runbook: `deploy/cloudrun.md` → "E-mail action links", "Google sign-in",
  "Store secrets", "Routine redeploy".
- Read API config: `GET https://identitytoolkit.googleapis.com/admin/v2/projects/portfyl-cloud-fstxby/config`
  with `gcloud auth print-access-token` and header
  `X-Goog-User-Project: portfyl-cloud-fstxby` (gcloud account
  `support@portfyl.com`).
- Design rules for the e-mail and page: `DESIGN.md` (palette §3, components §8).
