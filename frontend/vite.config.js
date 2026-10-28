import { fileURLToPath } from "node:url";
import { searchForWorkspaceRoot } from "vite";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { editionManifestPath, resolveFrontendEdition } from "./edition.config.js";

export function createConfig({ mode, env = process.env }) {
  const edition = resolveFrontendEdition(env, mode);
  return {
    define: { "import.meta.env.VITE_PORTFYL_EDITION": JSON.stringify(edition) },
    plugins: [react()],
    resolve: {
      alias: {
        "@edition-manifest": editionManifestPath(edition),
      },
    },
    server: {
      port: 5173,
      // Lets a quick public tunnel (serveo.net or `cloudflared tunnel --url`)
      // reach the dev server for quick public sharing/testing.
      allowedHosts: [".serveousercontent.com", ".trycloudflare.com"],
      // pages/Legal.jsx imports the legal texts from ../docs/legal, outside
      // the frontend root; the build reads them anyway, dev and Vitest need
      // the folder allow-listed next to the default workspace root.
      fs: { allow: [searchForWorkspaceRoot(process.cwd()), fileURLToPath(new URL("../docs/legal", import.meta.url))] },
      proxy: {
        // Keeps the backend same-origin with the SPA in dev (auth cookies,
        // CSRF header). All backend routes -- including /api/auth/* -- live
        // under /api; there is no separate top-level /login or /logout route.
        "/api": {
          target: env.VITE_API_PROXY_TARGET || "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
    test: {
      include: ["src/**/*.test.{js,jsx}"],
      globals: true,
      environment: "jsdom",
      setupFiles: "./src/test/setup.js",
      css: false,
      passWithNoTests: true,
    },
  };
}

export default defineConfig(({ mode }) => createConfig({ mode, env: process.env }));
