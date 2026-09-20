import { render } from "@testing-library/react";
import { describe, expect, it, afterEach } from "vitest";
import AnalyticsProvider from "./AnalyticsProvider";
import { createMemoryAdapter } from "./analyticsClient";
import { useDemoAnalytics } from "./useDemoAnalytics";

afterEach(() => localStorage.clear());

function Harness({ page, symbol, language = "en" }) {
  useDemoAnalytics({ page, symbol, language });
  return null;
}

function mount(initialProps) {
  const adapter = createMemoryAdapter();
  // adapterFactory must keep the same reference across rerenders -- an
  // inline arrow recreated per render would make AnalyticsProvider's effect
  // (deps: [consent, adapterFactory]) treat every rerender as a factory
  // change and reset+reinit the adapter each time.
  const adapterFactory = () => adapter;
  const { rerender } = render(
    <AnalyticsProvider initialConsent="accepted" adapterFactory={adapterFactory}>
      <Harness {...initialProps} />
    </AnalyticsProvider>
  );
  return {
    adapter,
    setProps: (props) =>
      rerender(
        <AnalyticsProvider initialConsent="accepted" adapterFactory={adapterFactory}>
          <Harness {...props} />
        </AnalyticsProvider>
      ),
  };
}

async function flush() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

const names = (adapter) => adapter.events.map(([name]) => name);

describe("useDemoAnalytics", () => {
  it("fires demo_started once, then demo_page_viewed once per distinct route (duplicates do not re-fire)", async () => {
    const { adapter, setProps } = mount({ page: "overview" });
    await flush();
    setProps({ page: "overview" }); // duplicate
    await flush();
    setProps({ page: "allocation" });
    await flush();

    expect(names(adapter)).toEqual(["demo_started", "demo_page_viewed", "demo_page_viewed"]);
    expect(adapter.events[1]).toEqual(["demo_page_viewed", { demo_page: "overview", language: "en" }]);
    expect(adapter.events[2]).toEqual(["demo_page_viewed", { demo_page: "allocation", language: "en" }]);
  });

  it("emits demo_activation_reached with three_pages after three distinct analysis pages", async () => {
    const { adapter, setProps } = mount({ page: "overview" });
    await flush();
    setProps({ page: "allocation" });
    await flush();
    setProps({ page: "analytics" });
    await flush();

    const activation = adapter.events.find(([name]) => name === "demo_activation_reached");
    expect(activation).toEqual(["demo_activation_reached", { activation_path: "three_pages", distinct_demo_pages: 3 }]);
  });

  it("emits demo_activation_reached with stock_after_page after overview then a stock", async () => {
    const { adapter, setProps } = mount({ page: "overview" });
    await flush();
    setProps({ page: "stock", symbol: "MSFT" });
    await flush();

    expect(names(adapter)).toContain("demo_stock_viewed");
    const activation = adapter.events.find(([name]) => name === "demo_activation_reached");
    expect(activation).toEqual(["demo_activation_reached", { activation_path: "stock_after_page", distinct_demo_pages: 2 }]);
  });

  it("does not activate when a stock is viewed first, with no prior demo page", async () => {
    const { adapter } = mount({ page: "stock", symbol: "MSFT" });
    await flush();
    expect(names(adapter)).not.toContain("demo_activation_reached");
  });

  it("emits nothing for an invalid demo stock symbol", async () => {
    const { adapter } = mount({ page: "stock", symbol: "GOOGL" });
    await flush();
    expect(adapter.events).toEqual([["demo_started", { language: "en", entry_point: "direct" }]]);
  });

  it("emits demo_activation_reached at most once per session even across many route changes", async () => {
    const { adapter, setProps } = mount({ page: "overview" });
    await flush();
    for (const page of ["allocation", "analytics", "dividends", "overview"]) {
      setProps({ page });
      await flush();
    }
    expect(names(adapter).filter((n) => n === "demo_activation_reached")).toHaveLength(1);
  });
});
