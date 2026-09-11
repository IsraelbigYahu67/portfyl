# Public landing page — 2026-09-10

## Implemented and deployed

- Cloud `/` renders the Czech marketing preview without loading the tracker,
  authentication provider, or private API data. Local edition keeps its original home.
- Cloud tracker home is `/dashboard`; login, onboarding, platform selection, and
  sidebar navigation use the edition-specific home.
- Every landing-page link is an in-page anchor. There are no login, registration,
  pricing, or tracker links.
- Images are existing design references, explicitly labelled as interface concepts
  with illustrative data (not screenshots of an owner's real portfolio).
- Both edition test suites passed: 30 files / 155 tests each. Both production
  builds passed. Desktop preview and preview switching were checked in Chrome.
- Cloud Run revision: `portfyl-00005-pk7`, serving 100% of traffic.
- Image: `europe-west3-docker.pkg.dev/portfyl-cloud-fstxby/cloud-run-source-deploy/portfyl@sha256:ef9d6fb240af9a0ccd64383054e1f750b0160ee88802cd81745a8389581322f6`.
- This frontend overlay retains the backend from runtime digest
  `sha256:012d8614dc084c05344ff68242e8adc02eae06f42fb93f109646a9b4a153b57a`.
- Pre-deployment migration execution `portfyl-migrate-tlwpw` succeeded.
- Previous runtime revision: `portfyl-00004-64t`.

## Initial public availability blocker (resolved 2026-09-11)

Anonymous visits to `https://portfyl.com/` redirect to Cloudflare Access.
The existing `Portfyl testing` application (`035de1d7-6186-4ba5-b240-4602b54d264d`)
covers the entire `portfyl.com` domain and references the reusable `Only me`
policy (`b6f0c838-536a-4606-aa7c-b7191a0d681f`). No Access changes were made.

Cloudflare application paths inherit to descendants: an apex or `/*` policy
also covers `/`. Therefore a public-home exception must not accidentally become
an unrestricted domain-wide bypass.

Change subsequently authorized by the user's request to publish through Cloudflare:
retain the existing identity provider, policy, and session settings, but scope
the protected application to `/api` and all tracker/auth routes:

`/dashboard`, `/overview`, `/allocation`, `/transactions`, `/cash`, `/import`,
`/dividends`, `/analytics`, `/search`, `/stock`, `/watchlists`, `/assistant`,
`/settings`, `/pricing`, `/login`, `/register`, `/verify-email`, `/forgot-password`.

Also retain protection on operational endpoints `/health`, `/docs`, `/redoc`,
and `/openapi.json`. Public content would be the home and static assets. New
private frontend routes must be added to Access coverage; all API descendants
remain protected by the `/api` destination and the application's own auth.

Before changing coverage, save the complete Access application response for
rollback. After changing, verify anonymous `/` and its images/JS/CSS return 200,
while `/api/auth/me`, `/dashboard`, `/login`, and `/register` still require Access.
Rollback restores the original single destination `portfyl.com` and original
application fields/policy reference.

Reference: https://developers.cloudflare.com/cloudflare-one/access-controls/policies/app-paths/

## Language selection — 2026-09-11

- First-time visitors choose CZ / EN / DE on a dedicated welcome screen.
- All landing-page copy, accessible labels, document title and document language
  follow the selection. The screenshot contents remain English and are labelled.
- The header offers all three languages. The validated choice is remembered in
  `portfyl_landing_language`; blocked storage does not prevent using the page.
- Keyboard focus moves to the landing heading after the initial selection.
- Both edition suites passed (30 files / 162 tests each); both builds passed.
  Chrome checks covered the chooser and German landing layout.
- Deployment image: `portfyl:languages-20260911`, digest
  `sha256:dd6af40bd8f8f57f7e1b574d2113e47a3105782e1ef449266869915bf79725a0`.
  It overlays the preceding landing runtime and preserves the backend.
- Cloudflare Access configuration was not changed in this update.
- Migration execution `portfyl-migrate-gcbpc` succeeded; revision
  `portfyl-00006-fwn` is serving 100% of traffic.

## Public domain activation — 2026-09-11

- The existing Access application now covers the tracker/auth routes and API
  listed above, plus the operational endpoints. Its reusable `Only me` policy,
  identity provider and session settings are preserved. The home and static
  assets are public. Original configuration is saved in
  `portfyl-access-before-public-home.json` for rollback.
- Initial anonymous checks: `/` returns 200; `/api/auth/me`, `/dashboard`,
  `/login` and `/register` redirect to Access (302).
- These checks exposed a prior deployment-target error: the domain maps to
  `portfyl` in **europe-west1**, while prior landing revisions were deployed to
  the separate europe-west3 service. Root HTML still referenced the old bundle
  and `/landing/*.png` fell back to HTML.
- The production domain mapping was verified using the Cloud Run domain-mapping
  API in europe-west1. Do not infer the service region from Artifact Registry's
  europe-west3 location.
- The corrective frontend overlay uses the actual production backend digest
  `sha256:03c097f5080c8da24b4fd162820713a207c31eccbfd91f6c589f441535b7e20e`.
  The previous europe-west1 revision is `portfyl-00007-99q`.

## Follow-up verification — 2026-09-11 06:50 UTC

- Anonymous HTTP requests confirm `/` returns 200 and `/api/auth/me`,
  `/dashboard`, `/login`, `/register` return 302.
- Chrome renders the language chooser and Czech landing page.
- The two landing PNG URLs initially still returned stale HTML. Cache-busting
  queries returned the correct PNGs (302771 and 313368 bytes), establishing
  that the deployed origin contains the assets.
- Purged only `https://portfyl.com/landing/allocation.png` and
  `https://portfyl.com/landing/stock.png` through Cloudflare; API succeeded.
  Subsequent anonymous requests to both original URLs return 200 image/png.
- The existing Chrome profile still showed a broken embedded allocation image
  after reload and a new tab, though navigating to the image directly displayed
  an image document with dimensions 1263x1600. Browser visual acceptance is
  therefore still pending; possible retained browser cache needs confirmation.
- No additional deployment or Access policy change was made in this session.

## Live application screenshots — 2026-09-11

- Replaced the concept images in the hero and gallery with four Chrome captures
  from the open local `Portfyl demo` portfolio: allocation, Microsoft stock
  details, portfolio overview, and performance. Captures exclude the sidebar
  account email. New filenames end in `-live-20260911.png` to avoid stale caches.
- The gallery has four choices; Czech, English and German captions describe
  actual app screenshots with demo portfolio and market data. Images keep their
  intrinsic proportions, including on narrow screens.
- Validation: 11 tests passed in Welcome/Root cloud suites; cloud build passed.
  Chrome verified all four gallery images in the local build and on portfyl.com.
  Anonymous HTTP checks returned 200 image/png for all four images and 200 for
  `/`; `/api/auth/me` and `/dashboard` still redirect to Access (302).
- Preserved production backend using base image digest
  `sha256:1aa636ddeca086a8e0de6a5c26338584fa27e311078afeee69e543a9a048f535`.
- Existing migration job execution `portfyl-migrate-mn9zx` succeeded before deploy.
- Cloud Build `40de0fcc-a803-4312-914c-ba690c2602a4` succeeded; image
  `portfyl:screenshots-20260911`, digest
  `sha256:a931715ba8e3d321aa2be9502a92d5813a5d1066bb2703063ef29323849d4089`.
- Production service: `portfyl`, project `portfyl-cloud-fstxby`, europe-west1.
  Revision `portfyl-00009-pks` serves 100% of traffic; previous revision is
  `portfyl-00008-ccd`. No Access policy changes were made.

## Broker copy and persistent navigation — 2026-09-11

- Removed Interactive Brokers claims from the public broker ribbon and FAQ.
  Added CS/EN/DE equivalents of "More brokers coming soon" in both places.
- Public navigation stays at the top while scrolling, with section anchor
  offsets and all three links visible across responsive layouts.
- Welcome/Root cloud suites: 11 tests passed. Cloud build passed; Chrome
  checked all three translations and sticky positioning at the FAQ section.
- Migration execution `portfyl-migrate-xhjp6` succeeded. Cloud Build
  `71ef1941-bfbe-4f17-b486-3a6f4d179d05` produced image digest
  `sha256:17698f0110624b22f632edb277d7c83605301e662b3780b45ea62a82289aa12a`.
- Revision `portfyl-00010-crq` serves 100% in europe-west1. The frontend-only
  overlay preserves the previous revision's backend. Production Chrome checks
  confirmed the new broker FAQ and header position after scrolling.

## Private beta hostname and admission — 2026-09-11

- Added a proxied Cloudflare CNAME for `app.portfyl.com` and the fail-closed
  Worker route `app.portfyl.com/*` (`portfyl-beta-proxy`). The Worker forwards
  to Cloud Run with the edge token stored as a Cloudflare secret. Its
  `workers.dev` and preview endpoints are disabled.
- Created the whole-hostname Access application `Portfyl private beta`, using
  the existing reusable exact-email policy, renamed to
  `Portfyl private beta testers`. The original path-scoped Access application
  on `portfyl.com` remains as a fallback.
- Added `app.portfyl.com` to Firebase authorized domains.
- Added the application-owned `beta_invites` admission gate before user and
  workspace provisioning, plus an operator-only Cloud Run Job wrapper for
  invite/list/revoke operations. See `private-beta-access.md`.
- Migration `portfyl-migrate-8kw4c` succeeded and revision
  `portfyl-00011-zjr` serves 100% of production traffic from image digest
  `sha256:1bd071a37dfc9945df6a6308cc12e2bd577e86226ee6bd717220ed8dbe99881d`.
- Final checks returned `200` for the public home, Access redirects for all
  anonymous beta routes, `403` for a direct-origin API request, and the
  expected `401` from the beta API after authenticated Access traversal.
