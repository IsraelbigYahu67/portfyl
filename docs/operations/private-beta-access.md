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

1. Run the database admission job:

   ```powershell
   .\deploy\manage-beta-tester.ps1 -Action invite -Email tester@example.com
   ```

2. In Cloudflare Zero Trust, edit the reusable policy
   `Portfyl private beta testers` and add one exact `Email` Include rule for
   the same normalized address. Preserve every existing exact e-mail.
3. Send `https://app.portfyl.com/register` to the tester. They must use the
   same e-mail for Cloudflare Access and Firebase registration.
4. Verify the Cloudflare Access authentication log and confirm the first
   successful Portfyl login changed the invite from `invited` to `accepted`:

   ```powershell
   .\deploy\manage-beta-tester.ps1 -Action list
   ```

Invitations expire after 30 days by default until first acceptance. Override
that window with `-ExpiresDays`; an accepted tester remains admitted until
explicit revocation.

## Revoke a tester

1. Remove the exact e-mail from the Cloudflare reusable policy first and
   revoke the Access application tokens if immediate termination is required.
2. Run:

   ```powershell
   .\deploy\manage-beta-tester.ps1 -Action revoke -Email tester@example.com
   ```

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
