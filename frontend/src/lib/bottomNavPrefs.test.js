import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import {
  BOTTOM_NAV_KEY,
  BOTTOM_NAV_MAX,
  DEFAULT_BOTTOM_NAV_PATHS,
  useBottomNavPaths,
} from "./bottomNavPrefs";
import { TRACKER_HOME } from "./routes";

afterEach(() => localStorage.clear());

describe("useBottomNavPaths", () => {
  it("falls back to the default four pages when nothing is stored", () => {
    const { result } = renderHook(() => useBottomNavPaths());
    expect(result.current.paths).toEqual([TRACKER_HOME, "/allocation", "/transactions", "/dividends"]);
    expect(result.current.paths).toEqual([...DEFAULT_BOTTOM_NAV_PATHS]);
    expect(result.current.isDefault).toBe(true);
  });

  it("reads the stored pick", () => {
    localStorage.setItem(BOTTOM_NAV_KEY, JSON.stringify(["/cash", "/search"]));
    const { result } = renderHook(() => useBottomNavPaths());
    expect(result.current.paths).toEqual(["/cash", "/search"]);
    expect(result.current.isDefault).toBe(false);
  });

  it("ignores garbage in storage", () => {
    for (const raw of ["not json", "{}", "42", "null"]) {
      localStorage.setItem(BOTTOM_NAV_KEY, raw);
      const { result, unmount } = renderHook(() => useBottomNavPaths());
      expect(result.current.paths).toEqual([...DEFAULT_BOTTOM_NAV_PATHS]);
      unmount();
    }
  });

  it("drops non-string entries and never exceeds the maximum", () => {
    const many = ["/", "/allocation", "/transactions", "/cash", "/search", "/watchlists", "/settings"];
    localStorage.setItem(BOTTOM_NAV_KEY, JSON.stringify([7, null, ...many]));
    const { result } = renderHook(() => useBottomNavPaths());
    expect(result.current.paths).toHaveLength(BOTTOM_NAV_MAX);
    expect(result.current.paths.every((path) => typeof path === "string")).toBe(true);
  });

  it("persists a new pick and updates every consumer at once", () => {
    const bar = renderHook(() => useBottomNavPaths());
    const settings = renderHook(() => useBottomNavPaths());

    act(() => settings.result.current.setPaths(["/cash", "/settings", "/search"]));

    expect(JSON.parse(localStorage.getItem(BOTTOM_NAV_KEY))).toEqual(["/cash", "/settings", "/search"]);
    expect(bar.result.current.paths).toEqual(["/cash", "/settings", "/search"]);
    expect(settings.result.current.paths).toEqual(["/cash", "/settings", "/search"]);
  });

  it("reset removes the stored pick and returns to the default", () => {
    localStorage.setItem(BOTTOM_NAV_KEY, JSON.stringify(["/cash", "/search"]));
    const { result } = renderHook(() => useBottomNavPaths());

    act(() => result.current.reset());

    expect(localStorage.getItem(BOTTOM_NAV_KEY)).toBeNull();
    expect(result.current.paths).toEqual([...DEFAULT_BOTTOM_NAV_PATHS]);
    expect(result.current.isDefault).toBe(true);
  });

  it("follows a change made in another tab", () => {
    const { result } = renderHook(() => useBottomNavPaths());
    act(() => {
      localStorage.setItem(BOTTOM_NAV_KEY, JSON.stringify(["/cash", "/search"]));
      window.dispatchEvent(new StorageEvent("storage", { key: BOTTOM_NAV_KEY }));
    });
    expect(result.current.paths).toEqual(["/cash", "/search"]);
  });
});
