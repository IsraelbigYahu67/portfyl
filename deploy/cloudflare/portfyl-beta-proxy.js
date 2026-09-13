const CLOUD_RUN_ORIGIN = "https://portfyl-741407058560.europe-west1.run.app";

export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    const target = new URL(CLOUD_RUN_ORIGIN);
    target.pathname = incoming.pathname;
    target.search = incoming.search;

    const upstream = new Request(target.toString(), request);
    upstream.headers.set("X-Portfyl-Edge-Token", env.PORTFYL_EDGE_TOKEN);
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
