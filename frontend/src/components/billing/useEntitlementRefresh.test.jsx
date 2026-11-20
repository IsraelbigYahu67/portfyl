import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useEntitlementRefresh } from "./useEntitlementRefresh";

let queryClient;
const wrapper = ({ children }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
const denied = () => window.dispatchEvent(
  new CustomEvent("portfyl:entitlement-denied", { detail: { code: "plan_upgrade_required" } }),
);

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-20T12:00:00Z"));
  queryClient = new QueryClient();
});
afterEach(() => vi.useRealTimers());

describe("useEntitlementRefresh", () => {
  it("refetches the billing status and capabilities on a denial, at most once per 30 s", () => {
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    renderHook(() => useEntitlementRefresh(null), { wrapper });

    act(() => { denied(); denied(); });

    expect(invalidate).toHaveBeenCalledTimes(2);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["billing-status"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["plan-capabilities"] });

    act(() => { vi.advanceTimersByTime(31_000); denied(); });
    expect(invalidate).toHaveBeenCalledTimes(4);
  });

  it("refetches once when a trial ending within a day ends", () => {
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const status = { source: "trial", effective_until: new Date(Date.now() + 2 * 3_600_000).toISOString() };
    renderHook(() => useEntitlementRefresh(status), { wrapper });

    act(() => { vi.advanceTimersByTime(2 * 3_600_000 - 1000); });
    expect(invalidate).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(1000); });

    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["billing-status"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["plan-capabilities"] });
  });

  it("sets no timer when the trial ends more than a day away", () => {
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const status = { source: "trial", effective_until: new Date(Date.now() + 3 * 86_400_000).toISOString() };
    renderHook(() => useEntitlementRefresh(status), { wrapper });

    act(() => { vi.advanceTimersByTime(3 * 86_400_000); });
    expect(invalidate).not.toHaveBeenCalled();
  });

  it("removes the listener and the timer on unmount", () => {
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const status = { source: "trial", effective_until: new Date(Date.now() + 3_600_000).toISOString() };
    const { unmount } = renderHook(() => useEntitlementRefresh(status), { wrapper });
    unmount();

    act(() => { denied(); vi.advanceTimersByTime(2 * 3_600_000); });
    expect(invalidate).not.toHaveBeenCalled();
  });
});
