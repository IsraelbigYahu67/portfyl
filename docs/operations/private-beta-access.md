# Private beta access

The marketing home at `https://portfyl.com/` is public. The tracker lives at
`https://app.portfyl.com/` and the whole hostname is protected by the
Cloudflare Access application `Portfyl private beta`
(`055dcd50-75d9-46c7-b9cb-b8a16e7386f2`). It uses the reusable exact-email
policy `Portfyl private beta testers`
(`b6f0c838-536a-4606-aa7c-b7191a0d681f`). Never replace the exact-email rules
with `Everyone`, `Login Methods`, or an e-mail-domain-wide rule.

Cloudflare is the outer admission gate. The application-owned source of truth
is PostgreSQL `beta_invites`. In the cloud edition, `/api/auth/session` checks
the verified Firebase e-mail before it may create a `User`, `Workspace`,
`Membership`, or `AuthSession`. Existing users were inserted as accepted by
Alembic migration `0013_private_beta_invites`.

Requests for the beta hostname run through the Cloudflare Worker
`portfyl-beta-proxy` on route `app.portfyl.com/*`. The Worker proxies to the
Cloud Run service URL and supplies `PORTFYL_EDGE_TOKEN` from an encrypted
Worker secret. Its `workers.dev` and preview URLs are disabled, and the route
is configured to fail closed. This avoids exposing a second public origin or
depending on a separate Google-managed certificate for the beta hostname.
The versioned Worker source and deployment configuration live in
`deploy/cloudflare/`.

## Invite a tester

`deploy/manage-beta-tester.ps1` writes both systems from one invocation when
`CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` (an Access-policy-edit
scoped API token) are set in the environment: it admits the e-mail in
`beta_invites` via the Cloud Run job, then adds the same normalized address as
an exact `Email` Include rule on the reusable policy `Portfyl private beta
testers`, preserving every other rule untouched. Without those two variables
set, the script only updates `beta_invites` and prints a warning that the
Cloudflare side still needs the manual step below — this was the only
behavior before 2026-09-11 and remains the fallback.

1. Run:

   ```powershell
   $env:CLOUDFLARE_ACCOUNT_ID = "<account id>"
   $env:CLOUDFLARE_API_TOKEN = "<Access: Apps and Policies Edit token>"
   .\deploy\manage-beta-tester.ps1 -Action invite -Email tester@example.com
   ```

   Add `-WhatIf` to preview the Cloudflare policy change without applying it.
   If the two environment variables are absent, manually add one exact
   `Email` Include rule for the same normalized address in Cloudflare Zero
   Trust instead, preserving every existing exact e-mail.
2. Send `https://app.portfyl.com/register` to the tester. They must use the
   same e-mail for Cloudflare Access and Firebase registration.
3. Verify the Cloudflare Access authentication log and confirm the first
   successful Portfyl login changed the invite from `invited` to `accepted`:

   ```powershell
   .\deploy\manage-beta-tester.ps1 -Action list -CheckCloudflare
   ```

   `-CheckCloudflare` additionally fetches the live policy's e-mail list so
   the two systems can be compared by eye; it needs the same two Cloudflare
   environment variables and makes no changes.

Invitations expire after 30 days by default until first acceptance. Override
that window with `-ExpiresDays`; an accepted tester remains admitted until
explicit revocation.

## Revoke a tester

Run:

```powershell
.\deploy\manage-beta-tester.ps1 -Action revoke -Email tester@example.com
```

With the two Cloudflare environment variables set, this also removes the
e-mail from the reusable policy's Include rules. Revoke the Access
application's own tokens separately if immediate session termination (not
just future admission) is required. Without the environment variables set,
remove the exact e-mail from the Cloudflare reusable policy by hand first, as
before 2026-09-11.

The command marks the invite revoked, disables the Portfyl user, revokes all
Portfyl sessions, and revokes Firebase refresh tokens when a Firebase UID is
present.

## Validation and rollback

- Anonymous `https://portfyl.com/` must return `200`.
- Anonymous `https://app.portfyl.com/`, `/register`, and `/api/auth/me` must
  redirect to Cloudflare Access.
- An e-mail absent from `beta_invites` must receive
  `403 {"code":"beta_access_required"}` from the session exchange without
  creating application records.
- Delete the `app.portfyl.com` Access application, Worker route, Worker, and
  DNS CNAME to roll back the hostname. The existing path-scoped Access
  application on `portfyl.com` remains in place as a fallback.

## Production deployment 2026-09-11

- Git commit: `830054d` on `origin/main`.
- Migration execution: `portfyl-migrate-8kw4c`.
- Cloud Run revision: `portfyl-00011-zjr`, serving 100% of traffic.
- Container image digest: `sha256:1bd071a37dfc9945df6a6308cc12e2bd577e86226ee6bd717220ed8dbe99881d`.
- Worker: `portfyl-beta-proxy`; route ID
  `588a1044481c45d0b25af98fa07cffad`.
- Anonymous checks: public home `200`; beta root, registration, and API `302`
  to Access; direct Cloud Run API `403`.
- Authenticated edge check: beta root `200`; beta `/api/auth/me` reached the
  backend and returned the expected `401` without a Portfyl session. The
  temporary verification credential and policy were removed afterward.
