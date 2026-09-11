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
- Delete the `app.portfyl.com` Access application, DNS CNAME, and Cloud Run
  domain mapping to roll back the hostname. The existing path-scoped Access
  application on `portfyl.com` remains in place as a fallback.
