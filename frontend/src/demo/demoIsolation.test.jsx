import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.resetModules();
  vi.doUnmock("../TrackerBootstrap");
  vi.doUnmock("../auth/firebase");
  vi.doUnmock("../api");
});

it.runIf(import.meta.env.VITE_PORTFYL_EDITION === "cloud")("loads the cloud demo without importing tracker, Firebase, or API modules", async () => {
  window.history.replaceState({}, "", "/demo");
  vi.doMock("../TrackerBootstrap", () => { throw new Error("tracker import is forbidden from demo"); });
  vi.doMock("../auth/firebase", () => { throw new Error("Firebase import is forbidden from demo"); });
  vi.doMock("../api", () => { throw new Error("API import is forbidden from demo"); });

  const { default: Root } = await import("../Root");
  render(<Root />);

  expect(await screen.findByRole("heading", { name: "Overview" }, { timeout: 5_000 })).toBeInTheDocument();
});
