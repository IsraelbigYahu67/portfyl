# Portfyl private beta proxy

This Worker is the origin adapter for the whole-hostname Cloudflare Access
application on `app.portfyl.com`. Access makes the admission decision before
the Worker proxies an allowed request to Cloud Run.

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
