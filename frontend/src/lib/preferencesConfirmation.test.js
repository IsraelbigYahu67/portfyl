import { afterEach, describe, expect, it, vi } from "vitest";
import {
  PREFERENCES_CONFIRMED_KEY,
  confirmPreferences,
  preferencesConfirmed,
} from "./preferencesConfirmation";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("preferencesConfirmation", () => {
  it("uses the portfyl_ key", () => {
    expect(PREFERENCES_CONFIRMED_KEY).toBe("portfyl_preferences_confirmed");
  });

  it("is false until confirmed, then true", () => {
    expect(preferencesConfirmed()).toBe(false);
    confirmPreferences();
    expect(preferencesConfirmed()).toBe(true);
    expect(localStorage.getItem(PREFERENCES_CONFIRMED_KEY)).toBe("1");
  });

  it("returns false when storage cannot be read", () => {
    confirmPreferences();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(preferencesConfirmed()).toBe(false);
  });

  it("does not throw when storage cannot be written", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => confirmPreferences()).not.toThrow();
  });
});
