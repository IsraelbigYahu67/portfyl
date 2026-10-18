# Portfyl private beta proxy

This Worker is the origin adapter for the whole-hostname Cloudflare Access
application on `app.portfyl.com`. Access makes the admission decision before
the Worker proxies an allowed request to Cloud Run.

Since 2026-10-16 it also serves the public apex `portfyl.com/*` (marketing
home and demo) from the same Cloud Run service. Only requests for
`app.portfyl.com` get `X-Portfyl-Edge-Token`; apex requests are proxied
without it, so the backend rejects any apex `/api` call with
`403 untrusted_edge`. The path-scoped Access application on `portfyl.com`
still gates the tracker paths there. Roll back the apex by removing the
`portfyl.com/*` route and redeploying.

`PORTFYL_EDGE_TOKEN` is a Wrangler secret. Never add its value to this
directory, the Wrangler configuration, or Git. Set or rotate it separately:

```powershell
Set-Location deploy/cloudflare
npm ci
npx wrangler secret put PORTFYL_EDGE_TOKEN
npm run deploy
```

Run `npm run check` before deploying. The configuration keeps `workers.dev`
and preview URLs disabled so the Worker cannot become a second public entry
point. The production route is fail closed in Cloudflare.
