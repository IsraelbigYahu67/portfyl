import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(fileURLToPath(import.meta.url));
const MODE_EDITIONS = Object.freeze({
  "edition-local": "local",
  "edition-cloud": "cloud",
});

export function resolveFrontendEdition(env = process.env, mode = "") {
  const raw = String(env.VITE_PORTFYL_EDITION || MODE_EDITIONS[mode] || "")
    .trim()
    .toLowerCase();
  if (!raw) {
    throw new Error(
      "VITE_PORTFYL_EDITION is required (use mode edition-local or edition-cloud)"
    );
  }
  if (raw !== "local" && raw !== "cloud") {
    throw new Error(
      `Unsupported VITE_PORTFYL_EDITION ${JSON.stringify(raw)}; expected local or cloud`
    );
  }
  return raw;
}

export function editionManifestPath(edition) {
  if (edition !== "local" && edition !== "cloud") {
    throw new Error(`Cannot resolve manifest for unknown edition ${JSON.stringify(edition)}`);
  }
  return path.resolve(ROOT, "src", "editions", `${edition}.jsx`);
}
