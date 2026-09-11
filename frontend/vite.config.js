import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { editionManifestPath, resolveFrontendEdition } from "./edition.config.js";

export default defineConfig(({ mode }) => {
  const edition = resolveFrontendEdition(process.env, mode);
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
      proxy: {
        // Keeps the backend same-origin with the SPA in dev (auth cookies,
        // CSRF header). All backend routes -- including /api/auth/* -- live
        // under /api; there is no separate top-level /login or /logout route.
        "/api": {
          target: "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
    test: {
      globals: true,
      environment: "jsdom",
      setupFiles: "./src/test/setup.js",
      css: false,
      passWithNoTests: true,
    },
  };
});
