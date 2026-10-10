import path from "node:path";
import { fileURLToPath } from "node:url";

// Filesystem path for `new URL(relative, import.meta.url)` in a test.
// Vite sometimes rewrites such a URL to a root-relative pathname
// ("/src/index.css") and sometimes leaves a real file: URL (Linux CI), so the
// two cases are resolved differently: a file: URL already holds the absolute
// path, a root-relative pathname is resolved against the Vitest cwd (frontend/).
export function sourcePath(assetUrl) {
  if (assetUrl.protocol === "file:") return fileURLToPath(assetUrl);
  return path.resolve(decodeURIComponent(assetUrl.pathname).replace(/^\//, ""));
}
