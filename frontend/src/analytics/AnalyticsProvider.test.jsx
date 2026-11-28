import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { createMemoryAdapter } from "./analyticsClient";
import AnalyticsProvider, { useAnalytics } from "./AnalyticsProvider";

function Probe() {
  const analytics = useAnalytics();
  return <>
    <div data-testid="state">{analytics.consent}:{String(analytics.ready)}</div>
    <button type="button" onClick={() => analytics.capture("landing_viewed", { language: "en", referrer_class: "direct", utm_source: "none", utm_medium: "none", utm_campaign: "none" })}>Capture</button>
    <button type="button" onClick={() => analytics.captureOnce("scope-a", "landing_viewed", { language: "en", referrer_class: "direct", utm_source: "none", utm_medium: "none", utm_campaign: "none" })}>CaptureOnceA</button>
    <button type="button" onClick={() => analytics.captureOnce("scope-b", "landing_viewed", { language: "en", referrer_class: "direct", utm_source: "none", utm_medium: "none", utm_campaign: "none" })}>CaptureOnceB</button>
    <button type="button" onClick={() => analytics.identify("user-42")}>Identify</button>
    <button type="button" onClick={() => analytics.reset()}>Reset</button>
    <button type="button" onClick={() => analytics.acceptAnalytics()}>Accept</button>
    <button type="button" onClick={() => analytics.rejectAnalytics()}>Reject</button>
  </>;
}

function mount({ initialConsent, adapterFactory } = {}) {
  return render(
    <AnalyticsProvider initialConsent={initialConsent} adapterFactory={adapterFactory}>
      <Probe />
    </AnalyticsProvider>
  );
}

describe("AnalyticsProvider", () => {
  it("drops pending captures without initializing an adapter", async () => {
    const adapterFactory = vi.fn(() => createMemoryAdapter());
    mount({ initialConsent: "pending", adapterFactory });
    await act(() => screen.getByRole("button", { name: "Capture" }).click());
    expect(screen.getByTestId("state")).toHaveTextContent("pending:false");
    expect(adapterFactory).not.toHaveBeenCalled();
  });

  it("initializes one adapter and captures after accepted consent", async () => {
    const adapter = createMemoryAdapter();
    const adapterFactory = vi.fn(() => adapter);
    mount({ initialConsent: "accepted", adapterFactory });
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("accepted:true"));
    await act(() => screen.getByRole("button", { name: "Capture" }).click());
    expect(adapterFactory).toHaveBeenCalledTimes(1);
    expect(adapter.events).toEqual([["landing_viewed", { language: "en", referrer_class: "direct", utm_source: "none", utm_medium: "none", utm_campaign: "none" }]]);
  });

  it("sends nothing after rejected consent", async () => {
    const adapter = createMemoryAdapter();
    mount({ initialConsent: "rejected", adapterFactory: () => adapter });
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("rejected:true"));
    await act(() => screen.getByRole("button", { name: "Capture" }).click());
    await act(() => screen.getByRole("button", { name: "CaptureOnceA" }).click());
    expect(adapter.events).toEqual([]);
  });

  it("initializes only after an explicit consent decision", async () => {
    const adapter = createMemoryAdapter();
    const adapterFactory = vi.fn(() => adapter);
    mount({ initialConsent: "pending", adapterFactory });
    await act(() => screen.getByRole("button", { name: "Accept" }).click());
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("accepted:true"));
    expect(adapterFactory).toHaveBeenCalledTimes(1);
  });

  it("changes accepted consent to rejected by resetting and replacing the adapter", async () => {
    const accepted = createMemoryAdapter();
    const rejected = createMemoryAdapter();
    const adapterFactory = vi.fn()
      .mockReturnValueOnce(accepted)
      .mockReturnValueOnce(rejected);
    mount({ initialConsent: "accepted", adapterFactory });
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("accepted:true"));
    await act(() => screen.getByRole("button", { name: "Reject" }).click());
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("rejected:true"));
    expect(accepted.resetCount).toBe(1);
    expect(adapterFactory).toHaveBeenCalledTimes(2);
  });

  it("removes the PostHog identity from the browser when accepted consent is withdrawn", async () => {
    const adapter = createMemoryAdapter();
    mount({ initialConsent: "accepted", adapterFactory: () => adapter });
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("accepted:true"));
    // The SDK's own persistence, as written while consent was accepted.
    localStorage.setItem("ph_phc_test_posthog", "{}");
    document.cookie = "ph_phc_test_posthog=abc; path=/";

    await act(() => screen.getByRole("button", { name: "Reject" }).click());
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("rejected:true"));

    expect(localStorage.getItem("ph_phc_test_posthog")).toBeNull();
    expect(document.cookie).not.toContain("ph_phc_test_posthog");
  });

  it("keeps the PostHog identity while consent stays accepted", async () => {
    localStorage.setItem("ph_phc_test_posthog", "{}");
    mount({ initialConsent: "accepted", adapterFactory: () => createMemoryAdapter() });
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("accepted:true"));
    expect(localStorage.getItem("ph_phc_test_posthog")).toBe("{}");
    localStorage.removeItem("ph_phc_test_posthog");
  });

  it("captureOnce deduplicates by scope+event, but a different scope still captures", async () => {
    localStorage.clear();
    const adapter = createMemoryAdapter();
    mount({ initialConsent: "accepted", adapterFactory: () => adapter });
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("accepted:true"));

    await act(() => screen.getByRole("button", { name: "CaptureOnceA" }).click());
    await act(() => screen.getByRole("button", { name: "CaptureOnceA" }).click());
    await act(() => screen.getByRole("button", { name: "CaptureOnceB" }).click());

    expect(adapter.events).toHaveLength(2);
  });

  it("reset() clears only in-memory identity state, not the consent choice", async () => {
    const adapter = createMemoryAdapter();
    mount({ initialConsent: "accepted", adapterFactory: () => adapter });
    await waitFor(() => expect(screen.getByTestId("state")).toHaveTextContent("accepted:true"));

    await act(() => screen.getByRole("button", { name: "Identify" }).click());
    expect(adapter.identifiedId).toBe("user-42");

    await act(() => screen.getByRole("button", { name: "Reset" }).click());
    expect(adapter.identifiedId).toBeNull();
    expect(screen.getByTestId("state")).toHaveTextContent("accepted:true");
  });
});
