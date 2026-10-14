import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const IS_CLOUD = import.meta.env.VITE_PORTFYL_EDITION === "cloud";

// Forbid the private modules first, then load the whole demo chain during
// collection (untimed) instead of inside the test's 5 s budget -- under a full
// parallel run the cold graph took ~20 s. The guard still holds: if anything
// in the chain imports a forbidden module, its factory throws here and the
// file fails.
if (IS_CLOUD) {
  vi.doMock("../TrackerBootstrap", () => { throw new Error("tracker import is forbidden from demo"); });
  vi.doMock("../auth/firebase", () => { throw new Error("Firebase import is forbidden from demo"); });
  vi.doMock("../api", () => { throw new Error("API import is forbidden from demo"); });
  await import("../Root");
  await import("./DemoBootstrap");
  await import("./pages/DemoOverview");
}

afterEach(() => {
  cleanup();
  vi.resetModules();
  vi.doUnmock("../TrackerBootstrap");
  vi.doUnmock("../auth/firebase");
  vi.doUnmock("../api");
});

it.runIf(IS_CLOUD)("loads the cloud demo without importing tracker, Firebase, or API modules", async () => {
  window.history.replaceState({}, "", "/demo");

  const { default: Root } = await import("../Root");
  render(<Root />);

  expect(await screen.findByRole("heading", { name: "Overview" }, { timeout: 5_000 })).toBeInTheDocument();
});
