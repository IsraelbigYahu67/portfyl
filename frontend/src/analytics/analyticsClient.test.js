import { describe, expect, it, vi } from "vitest";
import {
  createMemoryAdapter,
  createNoopAdapter,
  loadPostHogAdapter,
} from "./analyticsClient";

const acceptedConfig = {
  key: "phc_public_key",
  host: "https://eu.i.posthog.com",
  consent: "accepted",
};

function posthogDouble() {
  return {
    init: vi.fn(),
    capture: vi.fn(),
    identify: vi.fn(),
    reset: vi.fn(),
    shutdown: vi.fn(),
    opt_out_capturing: vi.fn(),
  };
}

describe("analytics adapters", () => {
  it("keeps the no-op adapter non-throwing", async () => {
    const adapter = createNoopAdapter();
    await expect(adapter.init()).resolves.toBe(false);
    await expect(adapter.capture("demo_started", {})).resolves.toBe(false);
    await expect(adapter.identify("opaque-user")).resolves.toBe(false);
    await expect(adapter.reset()).resolves.toBe(false);
    await expect(adapter.shutdown()).resolves.toBe(false);
  });

  it("records ordered events and reset state in the memory adapter", async () => {
    const adapter = createMemoryAdapter();
    await adapter.init();
    await adapter.capture("demo_started", { language: "en", entry_point: "direct" });
    await adapter.identify("opaque-user");
    await adapter.reset();
    expect(adapter.events).toEqual([["demo_started", { language: "en", entry_point: "direct" }]]);
    expect(adapter.identifiedId).toBeNull();
    expect(adapter.resetCount).toBe(1);
    adapter.clear();
    expect(adapter.events).toEqual([]);
    expect(adapter.resetCount).toBe(0);
  });

  it("never imports PostHog while pending or without a project key", async () => {
    const importPostHog = vi.fn();
    const pending = loadPostHogAdapter({ ...acceptedConfig, consent: "pending" }, { importPostHog });
    const missingKey = loadPostHogAdapter({ ...acceptedConfig, key: "" }, { importPostHog });
    await pending.init();
    await missingKey.init();
    expect(importPostHog).not.toHaveBeenCalled();
  });

  it("initializes accepted analytics once with the EU privacy configuration", async () => {
    const posthog = posthogDouble();
    const importPostHog = vi.fn(async () => ({ default: posthog }));
    const adapter = loadPostHogAdapter(acceptedConfig, { importPostHog });
    await expect(adapter.init()).resolves.toBe(true);
    await expect(adapter.init()).resolves.toBe(true);
    expect(importPostHog).toHaveBeenCalledTimes(1);
    expect(posthog.init).toHaveBeenCalledWith("phc_public_key", {
      api_host: "https://eu.i.posthog.com",
      ui_host: "https://eu.posthog.com",
      autocapture: false,
      capture_pageview: false,
      capture_pageleave: false,
      disable_session_recording: true,
      person_profiles: "identified_only",
      cross_subdomain_cookie: true,
      persistence: "localStorage+cookie",
      secure_cookie: true,
    });
    await adapter.capture("demo_started", { language: "en", entry_point: "direct" });
    await adapter.identify("opaque-user");
    await adapter.reset();
    await adapter.shutdown();
    expect(posthog.capture).toHaveBeenCalledWith("demo_started", { language: "en", entry_point: "direct" });
    expect(posthog.identify).toHaveBeenCalledWith("opaque-user");
    expect(posthog.reset).toHaveBeenCalledOnce();
    expect(posthog.shutdown).toHaveBeenCalledOnce();
  });

  it("never imports or initializes PostHog for rejected analytics", async () => {
    const importPostHog = vi.fn(async () => ({ default: posthogDouble() }));
    const adapter = loadPostHogAdapter({ ...acceptedConfig, consent: "rejected" }, { importPostHog });
    await expect(adapter.init()).resolves.toBe(false);
    await expect(adapter.capture("demo_started", {})).resolves.toBe(false);
    await expect(adapter.identify("opaque-user")).resolves.toBe(false);
    expect(importPostHog).not.toHaveBeenCalled();
  });

  it("absorbs import, init, and capture failures", async () => {
    const unavailable = loadPostHogAdapter(acceptedConfig, { importPostHog: async () => { throw new Error("blocked"); } });
    await expect(unavailable.init()).resolves.toBe(false);

    const posthog = posthogDouble();
    posthog.init.mockImplementation(() => { throw new Error("init failed"); });
    const initFailure = loadPostHogAdapter(acceptedConfig, { importPostHog: async () => ({ default: posthog }) });
    await expect(initFailure.init()).resolves.toBe(false);

    const capturePosthog = posthogDouble();
    capturePosthog.capture.mockImplementation(() => { throw new Error("capture failed"); });
    const captureFailure = loadPostHogAdapter(acceptedConfig, { importPostHog: async () => ({ default: capturePosthog }) });
    await captureFailure.init();
    await expect(captureFailure.capture("demo_started", {})).resolves.toBe(false);
  });
});
