// @vitest-environment node

import { createConfig } from "./vite.config.js";

it("defaults API proxy to port 8000", () => {
  expect(createConfig({
    mode: "development",
    env: { VITE_PORTFYL_EDITION: "local" },
  }).server.proxy["/api"].target)
    .toBe("http://localhost:8000");
});

it("uses VITE_API_PROXY_TARGET for a worktree server", () => {
  expect(createConfig({
    mode: "development",
    env: {
      VITE_PORTFYL_EDITION: "local",
      VITE_API_PROXY_TARGET: "http://localhost:8001",
    },
  }).server.proxy["/api"].target).toBe("http://localhost:8001");
});
