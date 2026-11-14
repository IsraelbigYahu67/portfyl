const CLOUD_RUN_ORIGIN = "https://portfyl-812512242326.europe-west1.run.app";

// Only the private tracker host may reach the API. The public marketing apex
// (portfyl.com) is served from the same origin but without the edge token, so
// its /api requests keep failing closed with 403 untrusted_edge, exactly as
// they did behind the old Cloud Run domain mapping.
const TRACKER_HOST = "app.portfyl.com";

// Google sign-in: Firebase's popup helper pages live under /__/auth/ on the
// Firebase auth domain. Serving them from app.portfyl.com (authDomain =
// app.portfyl.com) makes Google's account chooser say "continue to
// app.portfyl.com" instead of the raw <project>.firebaseapp.com name. This is
// Firebase's documented "proxy auth requests to firebaseapp.com" setup.
const FIREBASE_AUTH_ORIGIN = "https://portfyl-cloud-fstxby.firebaseapp.com";
const FIREBASE_AUTH_PATH_PREFIX = "/__/auth/";

// The helper pages are static and keep their state in the query string and
// browser storage, so nothing of the visitor's Portfyl or Cloudflare Access
// session is forwarded to Firebase Hosting.
async function proxyFirebaseAuthHelper(request, incoming) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response(null, { status: 405, headers: { Allow: "GET, HEAD" } });
  }
  const target = new URL(FIREBASE_AUTH_ORIGIN);
  target.pathname = incoming.pathname;
  target.search = incoming.search;
  const headers = new Headers();
  for (const name of ["Accept", "Accept-Language", "User-Agent", "If-None-Match", "If-Modified-Since"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  return fetch(target.toString(), { method: request.method, headers, redirect: "manual" });
}

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    if (incoming.hostname === TRACKER_HOST && incoming.pathname.startsWith(FIREBASE_AUTH_PATH_PREFIX)) {
      try {
        return await proxyFirebaseAuthHelper(request, incoming);
      } catch (error) {
        console.error(
          JSON.stringify({
            event: "firebase_auth_fetch_failed",
            path: incoming.pathname,
            error: error instanceof Error ? error.name : "UnknownError",
          }),
        );
        return Response.json({ code: "auth_helper_unavailable" }, { status: 502 });
      }
    }
    const target = new URL(CLOUD_RUN_ORIGIN);
    target.pathname = incoming.pathname;
    target.search = incoming.search;

    const upstream = new Request(target.toString(), request);
    upstream.headers.delete("X-Portfyl-Edge-Token");
    if (incoming.hostname === TRACKER_HOST) {
      upstream.headers.set("X-Portfyl-Edge-Token", env.PORTFYL_EDGE_TOKEN);
    }
    upstream.headers.set("X-Forwarded-Host", incoming.host);

    try {
      return await fetch(upstream, { redirect: "manual" });
    } catch (error) {
      console.error(
        JSON.stringify({
          event: "origin_fetch_failed",
          method: request.method,
          path: incoming.pathname,
          error: error instanceof Error ? error.name : "UnknownError",
        }),
      );
      return Response.json({ code: "origin_unavailable" }, { status: 502 });
    }
  },
};
