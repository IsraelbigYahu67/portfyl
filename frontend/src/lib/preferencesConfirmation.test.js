import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// The module keeps an in-memory fallback, so load a fresh copy per test.
let mod;

beforeEach(async () => {
  vi.resetModules();
  mod = await import("./preferencesConfirmation");
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("preferencesConfirmation", () => {
  it("uses the portfyl_ key", () => {
    expect(mod.PREFERENCES_CONFIRMED_KEY).toBe("portfyl_preferences_confirmed");
  });

  it("is false until confirmed, then true", () => {
    expect(mod.preferencesConfirmed()).toBe(false);
    mod.confirmPreferences();
    expect(mod.preferencesConfirmed()).toBe(true);
    expect(localStorage.getItem(mod.PREFERENCES_CONFIRMED_KEY)).toBe("1");
  });

  it("returns false when storage cannot be read", () => {
    mod.confirmPreferences();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(mod.preferencesConfirmed()).toBe(false);
  });

  it("remembers the confirmation for this visit when storage cannot be written", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => mod.confirmPreferences()).not.toThrow();
    expect(mod.preferencesConfirmed()).toBe(true);
  });

  it("remembers the confirmation when storage can be neither written nor read", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    mod.confirmPreferences();
    expect(mod.preferencesConfirmed()).toBe(true);
  });
});
