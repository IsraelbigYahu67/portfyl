import { renderHook } from "@testing-library/react";
import { useCountUp } from "./useCountUp";

describe("useCountUp", () => {
  it("returns the target immediately when disabled", () => {
    const { result } = renderHook(() => useCountUp(1000, { enabled: false }));
    expect(result.current).toBe(1000);
  });

  it("returns the target immediately under reduced motion", () => {
    window.matchMedia = (q) => ({
      matches: true, media: q, onchange: null,
      addEventListener() {}, removeEventListener() {},
      addListener() {}, removeListener() {}, dispatchEvent() { return false; },
    });
    const { result } = renderHook(() => useCountUp(500));
    expect(result.current).toBe(500);
  });

  it("passes through a non-finite target unchanged", () => {
    const { result } = renderHook(() => useCountUp(null, { enabled: true }));
    expect(result.current).toBe(null);
  });
});
