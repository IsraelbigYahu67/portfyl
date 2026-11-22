---
type: hub
layer: cross
tags: [arch/hub]
generated: false
---
# Auth and sessions

Portfyl does not keep passwords. Firebase Authentication proves who a person is (by e-mail and password, or by a Google popup), and then Portfyl hands the browser its own opaque, revocable session. Every later request uses that session, not Firebase. This split lets Portfyl end a session at any time (logout, password change) and keeps the identity provider behind one narrow door. In the cloud edition a new account also has to pass the private-beta invite check and, for new identities, a Cloudflare Turnstile bot check.

## How it works
- **Login in the browser.** [[auth.firebase]] signs in with e-mail and password, or with Google. Google uses Google Identity Services plus `signInWithCredential`, never a redirect and never Firebase's own `signInWithPopup`. Firebase state is `inMemoryPersistence`, so nothing survives a reload and Portfyl's session cookie is the only thing that keeps you logged in.
- **ID token to session.** The page posts the Firebase ID token to `POST /api/auth/session` in [[routers.auth]]. [[firebase_identity]] verifies it (`check_revoked=True`) and returns a `VerifiedIdentity`. An unverified e-mail gives `email_verification_required`.
- **Admission.** In the cloud edition [[beta_access]] (`require_active_invite`) runs before any user or workspace row is created. Operators manage invites with [[manage_beta]] and [[deploy.manage-beta-tester (ps1)]].
- **Bot check on demand.** Only an exchange that would create a new user needs a Turnstile token. [[turnstile]] does the server-side `siteverify` call and fails closed at startup in the cloud edition. The frontend side is [[auth.TurnstileWidget]], [[auth.BotCheckDialog]] and [[auth.turnstileConfig]].
- **Provisioning.** A first sign-in creates the `User`, a personal `Workspace` and an owner `Membership` in one transaction (see [[Tenancy and RLS]]), and in cloud grants the free trial (see [[Free trial]]).
- **The session.** [[auth]] creates a random 32-byte token, stores only its SHA-256 digest in [[auth_sessions (table)]] and sets the HttpOnly cookie `__Host-portfyl_session` (plain `portfyl_session` under `PORTFYL_TESTING`). Sessions last at most 30 days and are `SameSite=Lax`.
- **CSRF.** The CSRF token is derived (HMAC-SHA256) from the session token, so every tab gets the same value and nothing is stored or rotated. `csrf_guard` and `require_csrf` in [[tenancy]] check the `X-CSRF-Token` header on every state-changing `/api` call. A legacy random-token branch still exists for old sessions.
- **Password change.** At sign-in (and in `/auth/email/password-reset-done`) Portfyl reads Firebase's "password last changed" time. If it moved forward, `record_password_change` revokes all the user's other sessions, writes an `auth.password_changed` audit row and sends a best-effort notice (see [[Emails]]). A compare-and-set on `users.password_changed_seen_at` makes this fire once per change; the first sighting never e-mails anyone ([[0028_password_changed_seen]]).
- **Logout.** `/auth/logout` revokes one session; `/auth/logout-all` revokes all of them and the Firebase refresh tokens.
- **Frontend state.** [[auth.AuthProvider]] holds the account, the current workspace and the CSRF token, and feeds them to [[src.api]].

## Key code
- [[routers.auth]]: session exchange, `/me`, logout, password-change detection
- [[auth]]: session create/resolve/revoke, cookie policy, derived CSRF
- [[firebase_identity]]: the only Firebase Admin boundary (verify, user lookup, revoke, delete)
- [[tenancy]]: resolves the cookie to a `RequestContext`, CSRF dependencies
- [[beta_access]]: invite-only admission
- [[turnstile]]: bot check config and verification
- [[routers.auth_email]]: verification and password-reset e-mails
- [[auth.firebase]]: browser adapter for Firebase and the Google popup
- [[auth.AuthProvider]]: React context for the session
- [[auth.authEmail]]: Portfyl-first e-mail sending with Firebase fallback
- [[pages.Login]], [[pages.Register]], [[pages.ForgotPassword]], [[pages.VerifyEmail]], [[pages.AuthAction]]: the auth screens
- [[components.auth (folder)]]: Google button and divider

## Data
- [[users (table)]], [[auth_sessions (table)]], [[beta_invites (table)]]
- [[0013_private_beta_invites]], [[0028_password_changed_seen]]

## Related hubs
- [[Tenancy and RLS]]
- [[Emails]]
- [[Secrets and security]]
- [[Account deletion and data lifecycle]]
- [[Free trial]]
- [[Backend]]
- [[Frontend structure]]
- [[Portfyl]]

## Docs
- [[superpowers/plans/2026-10-12-portfyl-google-sign-in]]: why the Google popup is Google's own
- [[superpowers/specs/2026-09-01-portfyl-multiuser-foundation-design]]: identity and tenancy design
- [[superpowers/specs/2026-11-15-portfyl-own-emails-design]]: auth e-mails and password-change handling
- [[operations/private-beta-access]]: how invites are handed out
- [[security/tenant-isolation-matrix]]: what each session may reach
