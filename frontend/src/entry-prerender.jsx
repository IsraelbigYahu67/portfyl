// Server entry for the build-time prerender (scripts/prerender.mjs, cloud
// edition only). It renders the same <Root> the browser hydrates (main.jsx),
// given a fixed location instead of window.location, and waits for every lazy
// chunk (onAllReady) so the HTML is complete and contains no inline scripts.
import { StrictMode } from "react";
import { renderToPipeableStream } from "react-dom/server";
import { Writable } from "node:stream";
import Root from "./Root";

export { PUBLIC_PAGES, headTags, robotsTxt, sitemapXml } from "./seo/publicPages";

export const PRERENDER_HOSTNAME = "portfyl.com";

export function render(pathname) {
  return new Promise((resolve, reject) => {
    let html = "";
    const sink = new Writable({
      write(chunk, _encoding, callback) { html += chunk.toString(); callback(); },
      final(callback) { resolve(html); callback(); },
    });
    const stream = renderToPipeableStream(
      <StrictMode><Root location={{ pathname, hostname: PRERENDER_HOSTNAME }} /></StrictMode>,
      {
        onAllReady() { stream.pipe(sink); },
        onShellError: reject,
        onError: reject,
      },
    );
  });
}
