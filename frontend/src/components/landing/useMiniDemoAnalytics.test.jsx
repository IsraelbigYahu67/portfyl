import { act, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import AnalyticsProvider, { useOptionalAnalytics } from "../../analytics/AnalyticsProvider";
import { createMemoryAdapter } from "../../analytics/analyticsClient";
import { useMiniDemoAnalytics } from "./useMiniDemoAnalytics";

afterEach(() => localStorage.clear());

let reportUse;
let acceptAnalytics;
function Harness({ kind = "dividends", language = "cs" }) {
  ({ reportUse } = useMiniDemoAnalytics(kind, language));
  acceptAnalytics = useOptionalAnalytics()?.acceptAnalytics;
  return null;
}

async function flush() {
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 0)); });
}

function mount({ consent = "accepted", ...props } = {}) {
  const adapter = createMemoryAdapter();
  const adapterFactory = () => adapter;
  render(
    <AnalyticsProvider initialConsent={consent} adapterFactory={adapterFactory}>
      <Harness {...props} />
    </AnalyticsProvider>
  );
  return { adapter };
}

describe("useMiniDemoAnalytics", () => {
  it("sends landing_minidemo_used on the first use after consent, and nothing on the second", async () => {
    const { adapter } = mount();
    await flush();
    act(() => reportUse());
    await flush();
    act(() => reportUse());
    await flush();
    expect(adapter.events).toEqual([["landing_minidemo_used", { minidemo: "dividends", language: "cs" }]]);
  });

  it("each hook instance reports its own demo once", async () => {
    const adapter = createMemoryAdapter();
    const adapterFactory = () => adapter;
    const reporters = {};
    function Probe({ kind }) {
      reporters[kind] = useMiniDemoAnalytics(kind, "en").reportUse;
      return null;
    }
    render(
      <AnalyticsProvider initialConsent="accepted" adapterFactory={adapterFactory}>
        <Probe kind="allocation" />
        <Probe kind="stock" />
      </AnalyticsProvider>
    );
    await flush();
    act(() => { reporters.allocation(); reporters.stock(); reporters.allocation(); reporters.stock(); });
    await flush();
    expect(adapter.events).toEqual([
      ["landing_minidemo_used", { minidemo: "allocation", language: "en" }],
      ["landing_minidemo_used", { minidemo: "stock", language: "en" }],
    ]);
  });

  it.each(["pending", "rejected"])("sends nothing while consent is %s", async (consent) => {
    const { adapter } = mount({ consent });
    await flush();
    act(() => reportUse());
    act(() => reportUse());
    await flush();
    expect(adapter.events).toEqual([]);
  });

  it("counts the first interaction after consent is accepted later", async () => {
    const { adapter } = mount({ consent: "pending" });
    await flush();
    act(() => reportUse());
    await flush();
    expect(adapter.events).toEqual([]);
    act(() => acceptAnalytics());
    await flush();
    act(() => reportUse());
    await flush();
    expect(adapter.events).toEqual([["landing_minidemo_used", { minidemo: "dividends", language: "cs" }]]);
  });

  it("does not use browser storage for the once-per-page mark", async () => {
    const { adapter } = mount();
    await flush();
    act(() => reportUse());
    await flush();
    expect(adapter.events).toHaveLength(1);
    expect(Object.keys(localStorage).filter((key) => key.includes("minidemo"))).toEqual([]);
  });

  it("does not fail without an analytics provider", () => {
    render(<Harness />);
    expect(() => reportUse()).not.toThrow();
  });
});
