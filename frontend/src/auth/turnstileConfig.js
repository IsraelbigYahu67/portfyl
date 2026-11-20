// The public Cloudflare Turnstile site key, baked in at build time
// (VITE_TURNSTILE_SITE_KEY, see "Sign-up bot check" in deploy/cloudrun.md).
// Empty when the build has none: the challenge dialog then says the check is
// not available instead of loading Cloudflare.
export function turnstileSiteKey() {
  return (import.meta.env.VITE_TURNSTILE_SITE_KEY || "").trim();
}
