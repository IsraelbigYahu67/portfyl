# Portfyl — Sign in with Google

**Date:** 2026-10-12
**Status:** Wave 0 is done by the owner (2026-10-12). Waves 1–2 and T6 are
implemented on branch `feat/google-sign-in`. T7's automated checks pass (§7).
The owner skipped the account-linking spike (T0 step 5). The T7 manual
end-to-end checks with a real Google account are also still open. Do both
before setting the flag in production.
**Goal:** Let a person create a Portfyl account, and log in afterwards, with
their Google account, as an alternative to e-mail/password. This works in both
editions and keeps every existing guarantee: the private-beta invite gate, the
opaque Portfyl session, tenant provisioning, and fresh reauthentication before
account deletion.

## 1. Why this is small

Portfyl already delegates identity to Firebase and only trusts a **verified
Firebase ID token** (`POST /api/auth/session`, `backend/routers/auth.py`). A
Google sign-in through Firebase produces the same kind of ID token: same `uid`,
`email`, `email_verified=true`, and `name`, plus
`firebase.sign_in_provider = "google.com"`. So:

- **No database migration.** `users.firebase_uid` / `email` are
  provider-agnostic. `backend/alembic/versions/`, `EXPECTED_ALEMBIC_HEAD` and
  the Cloud Run migration Job stay untouched.
- **Provisioning is unchanged.** `_provision_identity()` already creates
  `User → Membership(owner) → Workspace` on first exchange. A new Google user
  lands in an empty workspace and gets the existing demo/import/broker
  onboarding.
- **The beta gate is unchanged.** `require_active_invite(db, identity.email)`
  runs before provisioning in the cloud edition, whatever the provider.

The real work is in four places: the browser adapter (popup flow), the login
and register UI, the CSP, and account-deletion reauthentication for users who
have no password.

## 2. Current state (verified 2026-10-12)

| Area | File | Relevant fact |
|---|---|---|
| Firebase browser adapter | `frontend/src/auth/firebase.js` | Lazy SDK import, `inMemoryPersistence`, e-mail/password only. `reauthenticateWithPassword()` is used for deletion. |
| Session exchange | `frontend/src/auth/AuthProvider.jsx` `loginWithIdToken` | Exchanges the ID token, then signs the Firebase client out. The Portfyl cookie is the only durable credential. |
| Login / Register | `frontend/src/pages/Login.jsx`, `Register.jsx` | Password forms only. Register sends a verification mail and then goes to `/verify-email`. |
| Backend verifier | `backend/firebase_identity.py` | Reads `uid`, `email`, `email_verified`, `name`, `auth_time`. Ignores `firebase.sign_in_provider`. |
| Exchange endpoint | `backend/routers/auth.py` | Rejects unverified e-mail (403), applies the beta gate (cloud), provisions, creates the session, audits `auth.session.created`. Returns 409 `identity_conflict` when the e-mail belongs to a different Firebase UID. |
| Display name | `_provision_identity()` | Overwrites `display_name` on every login. A later password login (no `name` claim) would wipe a Google-provided name. |
| Deletion reauth | `frontend/src/components/DataPrivacySettings.jsx`, `backend/account_deletion.py` | Requires a fresh (≤5 min `auth_time`) ID token for the same UID and e-mail. The frontend can only produce one with a password today. |
| CSP | `backend/security_headers.py` | `script-src 'self'`, no `frame-src` (falls back to `default-src 'self'`). Firebase's popup flow needs `https://apis.google.com` scripts and an iframe on the auth domain, so **the current CSP blocks Google sign-in in production builds.** In Vite dev there is no CSP, so dev testing alone cannot catch this. |
| Analytics | `frontend/src/analytics/eventContract.js` | `signup_completed` allows only `source_surface`. |
| Build config | `Dockerfile`, `deploy/cloudrun.md` | `VITE_FIREBASE_*` build args. There is no Google-specific flag. |

## 3. Decisions

- **D1: Use a popup, not a redirect.** `signInWithRedirect` needs auth state
  to survive a full page reload, which conflicts with the deliberate
  `inMemoryPersistence`. It also has third-party-storage problems when the auth
  domain is not same-origin. `signInWithPopup` keeps the current "Firebase
  session lives only for one exchange" model. A blocked popup gets a clear
  error message.
- **D2: Keep the `*.firebaseapp.com` auth domain for the private beta.** The
  Google account chooser will say "continue to `<project>.firebaseapp.com`".
  Before public launch, move `authDomain` to a Portfyl-branded host, either a
  Firebase Hosting custom domain such as `auth.portfyl.com` or a `/__/auth/*`
  proxy on `portfyl.com`. That is a follow-up and outside this plan.
- **D3: Keep Firebase "One account per e-mail address" (the default).** Never
  switch it to "multiple accounts per e-mail". Doing so would mint a new UID
  for the same e-mail and hit `identity_conflict` (409) on every Google
  sign-in by an existing user.
- **D4: Linking UI is out of scope.** Firebase links Google into an existing
  verified password account automatically for `@gmail.com` addresses,
  because Google is a trusted provider for them. For other domains, such as
  Google Workspace accounts, it may return
  `auth/account-exists-with-different-credential`. The MVP shows: "This
  e-mail already has a Portfyl password. Log in with your password." A
  Settings → "Link Google account" flow (`linkWithPopup`) is a later phase.
  Task 0 confirms the exact behavior.
- **D5: Gate the feature at build time.** `VITE_FIREBASE_GOOGLE_SIGN_IN=true`
  shows the button. Code can merge before the Firebase console is configured,
  and the feature can be turned off without a code change. It defaults to
  off.
- **D6: The deletion dialog offers both methods instead of asking which
  provider the user has.** It shows "Confirm with password" and "Confirm with
  Google". This avoids a Firebase Admin `get_user` call in `/auth/me` and
  avoids storing provider state. The backend already verifies UID, e-mail and
  `auth_time`, so either proof is equivalent.
- **D7: Uninvited Google users are rejected the same way as uninvited
  password users** (403 `beta_access_required`). As today, an orphan Firebase
  identity can remain in Firebase. Portfyl creates no records for it.

## 4. Tasks and waves

Parallel-session rules (CLAUDE.md) apply. Each task has its own branch or
worktree, the file sets are disjoint, and no task touches Alembic, lockfiles
or `.env`. The Firebase JS SDK already includes `GoogleAuthProvider`, so no
`package.json` change is needed.

```
Wave 0 (manual, parallel with Wave 1):  T0 Firebase / Google Cloud console
Wave 1 (parallel):                      T1 backend exchange · T2 CSP · T3 firebase.js adapter
Wave 2 (parallel, after T3):            T4 Login/Register UI + analytics · T5 deletion reauth
Wave 3 (sequential):                    T6 build/deploy/docs → T7 end-to-end verification → flag on
```

### T0: Firebase and Google Cloud console setup (owner, manual)

1. Firebase console → Authentication → Sign-in method → enable **Google**.
   Set the project support e-mail.
2. Google Cloud console → OAuth consent screen (Branding): app name
   "Portfyl", logo, support e-mail, privacy policy and terms URLs, authorized
   domain `portfyl.com`. Scopes stay basic (`openid email profile`), so
   sensitive-scope review is not needed. Logo and brand verification is
   needed only for the logo to appear.
3. Firebase Authentication → Settings → Authorized domains: `localhost`,
   `app.portfyl.com` (the tracker host; see §6), plus any Cloud Run or
   preview hostname used for testing.
4. Confirm "User account linking" = **one account per e-mail address** (D3).
5. **Spike**, using a disposable Firebase test project or the dev project:
   record the actual behavior for
   (a) a new Gmail user,
   (b) an existing *verified* password account on a `@gmail.com` address
       signing in with Google (expected: same UID, Google linked),
   (c) the same for a non-Gmail Google Workspace address (expected:
       `auth/account-exists-with-different-credential`),
   (d) an existing *unverified* password account (expected: Firebase drops
       the password and keeps the UID).
   Write the results into §6 of this file. T4's error copy depends on them.

### T1: Backend exchange (provider-aware, otherwise unchanged)

**Files:** `backend/firebase_identity.py`, `backend/routers/auth.py`,
`backend/tests/test_auth.py`, `backend/tests/postgres/test_auth_sessions.py`

1. `VerifiedIdentity` gains `sign_in_provider: str | None`, read from
   `claims.get("firebase", {}).get("sign_in_provider")`. Store it only if it
   is one of a small allowlist (`password`, `google.com`); otherwise `None`.
2. `_provision_identity()` returns `(user, created: bool)`. It overwrites
   `display_name` **only when** `identity.display_name` is not `None`, so a
   password login no longer wipes a Google-provided name.
3. `exchange_session` adds `"account_created": created` to the 201 payload
   (`_account_payload` itself stays the same for `/auth/me`). It adds
   `"provider": identity.sign_in_provider or "unknown"` to the
   `auth.session.created` audit metadata.
4. Keep the `email_verified` check. Google tokens carry `true`. A test with
   provider `google.com` and `email_verified=false` must still produce 403.
5. Tests (fast suite):
   - Google claims map to an identity with the provider.
   - An unknown provider string maps to `None`.
   - Audit metadata contains the provider.
   - `account_created` is true on first exchange and false on the second.
   - A display name is preserved when the second login has no name.
   - Google plus an uninvited e-mail in the cloud edition gives 403
     `beta_access_required` and creates no `users` row.
6. Postgres suite: one case where the same UID first logs in with
   `password` and then with `google.com`. Exactly one user, one membership
   and one workspace must exist, and RLS context must be unaffected.

Event-loop rule: `exchange_session` is already a sync `def`. Keep it that way.

### T2: CSP for the Firebase popup

**Files:** `backend/security_headers.py`, `backend/tests/test_security_headers.py`

1. `script-src 'self' https://apis.google.com`.
2. Add `frame-src https://<auth-domain>`. The auth domain comes from a new
   runtime env `PORTFYL_FIREBASE_AUTH_DOMAIN`. Validate it as a bare hostname
   (no scheme, path or wildcard), and fail closed by omitting `frame-src` when
   it is missing or invalid. Build the policy once at import or startup, not
   per request.
3. `connect-src` already allows `https://*.googleapis.com`, which covers
   `identitytoolkit` and `securetoken`. Do not widen it further unless T7
   finds a violation.
4. Tests: the directive is present with a valid env value and absent when the
   value is missing or malicious (`evil.com; script-src *`). The existing
   assertions still pass.
5. T7 treats the browser console's CSP-violation list on the production build
   as the source of truth. Any additional host, such as `www.gstatic.com`, is
   added explicitly with a test.

### T3: Browser Firebase adapter

**Files:** `frontend/src/auth/firebase.js`, `frontend/src/auth/firebase.test.js`

1. Add `isGoogleSignInEnabled()`, which checks
   `import.meta.env.VITE_FIREBASE_GOOGLE_SIGN_IN === "true"`.
2. Add `signInWithGoogle()`:
   - Call `readyAuth()`.
   - Create `new GoogleAuthProvider()` with
     `setCustomParameters({ prompt: "select_account" })`.
   - Call `signInWithPopup(auth, provider)` and return `credential.user`.
   - Return `null` on `auth/popup-closed-by-user` or
     `auth/cancelled-popup-request`. These are not errors in the UI.
3. Add `reauthenticateWithGoogle(expectedEmail)`, which mirrors
   `reauthenticateWithPassword`. It calls `signInWithPopup` with a
   `login_hint` of the expected e-mail, then `getIdToken(true)`, then
   `signOut` in `finally`. The backend checks that the UID and e-mail match,
   so picking a different Google account produces
   `reauthentication_identity_mismatch`.
4. Extend `ERROR_MESSAGES` with:
   - `auth/popup-blocked`: "Your browser blocked the Google sign-in window.
     Allow pop-ups for this site and try again."
   - `auth/account-exists-with-different-credential`: D4 copy.
   - `auth/unauthorized-domain` and `auth/operation-not-allowed`: generic
     "Google sign-in is not available right now."
   - backend `identity_conflict`: "This e-mail is already linked to a
     different sign-in. Log in with your password."
   Map backend codes the same way as `beta_access_required`.
5. Tests: mock the SDK module, as the existing tests do.
   - The popup is called with the `select_account` parameter.
   - Closing the popup returns `null`.
   - Reauth always signs out, including when it throws.
   - Each new error code maps to the expected message.

### T4: Login and Register UI plus analytics (after T3)

**Files:** new `frontend/src/components/auth/GoogleSignInButton.jsx` (+ test),
`frontend/src/pages/Login.jsx`, `frontend/src/pages/Register.jsx`,
`frontend/src/pages/AuthPages.test.jsx`,
`frontend/src/analytics/eventContract.js`, `eventContract.test.js`

1. `GoogleSignInButton` is a "Continue with Google" button. It follows the
   Google branding guidelines: inline multicolor "G" SVG, neutral surface, and
   correct theming in both dark and light tokens. Behavior:
   - Clicking it calls `signInWithGoogle()`. A `null` result does nothing.
   - Otherwise it gets the ID token, calls `loginWithIdToken`, and navigates
     to `TRACKER_HOME` with `{ replace: true }`.
   - The button has an `aria-busy` loading state and is disabled while
     loading.
   - Errors render through `mapFirebaseAuthError` in a `role="alert"`
     element.
   - If the exchange response has `account_created === true`, it captures
     `SIGNUP_COMPLETED` with `{ source_surface, auth_method: "google" }`.
2. Login and Register render the button above the form, with an "or"
   divider, only when `isGoogleSignInEnabled()` is true. Register passes its
   `sourceSurface`. A Google user skips `/verify-email` entirely.
3. The password Register flow adds `auth_method: "password"` to its existing
   `SIGNUP_COMPLETED` capture.
4. `eventContract.js` adds `auth_method` to the `signup_completed` allowlist
   with an enum of `password` and `google`. Update the contract test,
   including the unknown-value rejection.
5. Tests:
   - The button is hidden when the flag is off.
   - On a successful popup, the exchange runs, then navigation happens.
   - A cancelled popup produces no error.
   - `beta_access_required`, `identity_conflict` and popup-blocked each show
     the right message.
   - The signup event fires only when `account_created` is true.

### T5: Account deletion reauthentication (after T3)

**Files:** `frontend/src/components/DataPrivacySettings.jsx` and its test file

1. The deletion dialog keeps the password field and "Confirm with password",
   and adds a "Confirm with Google" button when the flag is on (D6). Both
   paths produce a `reauth_id_token` and call `scheduleWorkspaceDeletion`
   with the typed confirmation phrase.
2. Change the `recent_reauthentication_required` copy to "Confirm your
   identity again and retry." It no longer says "password".
3. Tests:
   - The Google path sends the token from `reauthenticateWithGoogle`.
   - Cancelling the popup does nothing.
   - The typed confirmation is still required on both paths.
4. No backend change. `account_deletion._validate_reauthentication` is
   already provider-agnostic.

### T6: Build, deploy and docs (after T1–T5 merge)

**Files:** `Dockerfile`, `deploy/cloudrun.md`, `start.bat` (only if it sets
`VITE_*` env), `docs/compliance/data-processing-inventory.md`, `CLAUDE.md`
("Login" bullet)

1. `Dockerfile`: add the build arg and env `VITE_FIREBASE_GOOGLE_SIGN_IN`,
   default `false`.
2. `deploy/cloudrun.md`:
   - Document the build arg.
   - Document the runtime env `PORTFYL_FIREBASE_AUTH_DOMAIN`, which must
     equal `VITE_FIREBASE_AUTH_DOMAIN`.
   - Add the T0 console checklist.
   - Rollback: rebuild with the flag set to `false`. No data change is
     needed.
3. Compliance inventory: the Firebase Authentication row also covers "Google
   sign-in (OAuth): Google returns e-mail, name, and profile identifiers to
   Firebase". No new subprocessor is added, because Google/Firebase is
   already listed. Check whether the public privacy-policy copy names the
   sign-in methods, and update it if so.
4. In `CLAUDE.md`, change "Firebase Authentication (email/password)" to
   "(email/password or Google popup)".

### T7: End-to-end verification and flag on

Run the automated checks first:

- Backend: `python -m pytest tests/ --ignore=tests/postgres -v`.
- Backend: `python -m pytest tests/postgres/ -v` against the per-session test
  container.
- Frontend: `npm test`, `npm run test:cloud`, `npm run build`,
  `npm run build:cloud`.

Then do the manual checks. Run them against a **production-style build served
by FastAPI**, so the CSP is active, on the owner's own port and database. The
owner performs the Google sign-in in the popup; an agent must not type Google
credentials.

1. Brand-new Google account with an invite (cloud):
   - Account is created.
   - Onboarding shows up.
   - The `auth.session.created` audit event has `provider=google.com`.
   - `signup_completed` has `auth_method=google`.
2. Same account logs out and back in: same workspace, and `account_created`
   is false.
3. Uninvited Google e-mail (cloud): you see the beta message, and Portfyl
   creates no rows.
4. Existing verified password account on Gmail signs in with Google: same
   workspace (T0 spike case b). A later password login still works and keeps
   the name.
5. Non-Gmail Workspace account that collides with a password account: the D4
   message appears.
6. Popup blocked, then popup closed: correct message, then no message.
7. Account deletion via "Confirm with Google": it is scheduled. Choosing a
   different Google account in the popup gives an identity-mismatch error.
8. Browser console on a production build: zero CSP violations during the
   whole flow.
9. Local edition (`start.bat`) works the same, minus the beta gate.

When all of these pass, rebuild with `VITE_FIREBASE_GOOGLE_SIGN_IN=true` and
deploy through the normal runbook. The migration Job is a no-op because the
head is unchanged.

## 5. Out of scope and follow-ups

- Settings → "Link / unlink Google" (`linkWithPopup`) and "Add a password" for
  Google-only users.
- Branded auth domain, such as `auth.portfyl.com` (D2). Do this before
  public launch.
- Google One Tap, and Apple or Microsoft sign-in. The T3/T4 structure,
  provider button plus adapter function, is the template for these.
- Cleaning up orphan Firebase identities that were rejected by the beta gate.

## 6. T0 notes and spike results

Console configuration (owner, 2026-10-12):

- The Firebase project is `portfyl-cloud-fstxby`, so the auth domain is
  `portfyl-cloud-fstxby.firebaseapp.com`. Cloud Run runs in a *different*
  GCP project (`portfyl-prod-f6shqb`). The OAuth consent screen belongs to the
  Firebase project.
- The tracker is served from `app.portfyl.com`, not `portfyl.com`. Firebase
  Authorized domains must list `app.portfyl.com` explicitly.
- Consent screen audience: **Testing**, with named test users. Privacy-policy
  and terms URLs are left empty until the public-launch gate in
  `docs/compliance/private-test-legal-status.md`. Every private tester
  therefore needs three entries: Cloudflare Access, `beta_invites`, and
  consent-screen Test users.
- The support e-mail is the owner's Gmail. `support@portfyl.com` is not
  selectable until it is a Google account or Group with project access.
- The console's "Firebase Dynamic Links shutdown" banner does not apply.
  Portfyl uses neither e-mail-link sign-in nor Cordova OAuth.

Implementation notes from Wave 1:

- T3 added `prepareGoogleSignIn()`. **T4 and T5 must call it on mount** (or
  when the deletion dialog opens). Browsers block a popup opened after an
  async gap, so once it has resolved, `signInWithGoogle()` and
  `reauthenticateWithGoogle()` call `signInWithPopup` with no `await` before
  it.
- T2 adds `https://apis.google.com` to `script-src` and adds `frame-src
  https://<auth domain>` only when `PORTFYL_FIREBASE_AUTH_DOMAIN` is a valid
  bare hostname. T6 must set it on Cloud Run to
  `portfyl-cloud-fstxby.firebaseapp.com`.

Spike results (T0 step 5): **not run.** The owner chose to skip it on
2026-10-12. The behavior for an existing password account that signs in with
Google is therefore still unverified (case b: expected same UID, Google
linked). Covering it is part of T7 manual check 4.

## 7. Verification record (2026-10-12)

Automated:

| Check | Result |
|---|---|
| Fast backend suite | 1219 passed |
| PostgreSQL suite (disposable PostgreSQL 16 on its own port) | 423 passed, including the new Google provisioning cases |
| Auth, analytics and privacy-settings frontend tests | 147 passed |
| Full `npm test` / `npm run test:cloud` | Green except 3–4 heavy demo/routing files that time out at 5 s under full-suite load. They pass in isolation (45/45 in both editions) and are unrelated to auth. A separate follow-up task was suggested for them. |
| `npm run build` and `npm run build:cloud` | Pass |

CSP spot check against a production-style build:

- Setup: the local edition built with `VITE_FIREBASE_GOOGLE_SIGN_IN=true` and
  served by FastAPI with
  `PORTFYL_FIREBASE_AUTH_DOMAIN=portfyl-cloud-fstxby.firebaseapp.com`.
- The served CSP contained `script-src 'self' https://apis.google.com` and
  `frame-src https://portfyl-cloud-fstxby.firebaseapp.com`.
- Clicking "Continue with Google" loaded the gapi scripts from
  `apis.google.com` and the `/__/auth/iframe` from the auth domain, with
  **zero** `securitypolicyviolation` events.
- The click was synthetic, so the browser blocked the popup, and the UI showed
  the popup-blocked message. No Google account was signed in.

Manual checks still open: T7 items 1–9, which need a real Google account and,
for the cloud checks, a deployed revision.

Rollout state (2026-10-13):

- The owner's `frontend/.env.local` now contains
  `VITE_FIREBASE_GOOGLE_SIGN_IN=true`. The **next routine redeploy of `main`
  turns the button on in production.**
- The Cloud Run env `PORTFYL_FIREBASE_AUTH_DOMAIN` (cloudrun.md "Google
  sign-in" step 2) is to be set by the owner. Do not redeploy until it is
  set, or the CSP will block the popup.
- Production gcloud access uses the `newgcp` configuration with account
  `support@portfyl.com`. The default configuration (`tom.zoubek@gmail.com`)
  has no access to `portfyl-prod-f6shqb`. On machines where PowerShell
  scripts are disabled, call `gcloud.cmd`.
