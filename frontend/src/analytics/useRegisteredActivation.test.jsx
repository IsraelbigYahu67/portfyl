import { act, renderHook } from "@testing-library/react";
import { describe, it, expect, afterEach, beforeEach, vi } from "vitest";
import AnalyticsProvider from "./AnalyticsProvider";
import { createMemoryAdapter } from "./analyticsClient";
import { useRegisteredActivation } from "./useRegisteredActivation";

const authState = vi.hoisted(() => ({
  user: { id: "u1" },
  currentWorkspace: { id: "w1" },
}));
vi.mock("../auth/AuthProvider", () => ({
  useAuth: () => ({ user: authState.user, currentWorkspace: authState.currentWorkspace }),
}));

beforeEach(() => {
  authState.user = { id: "u1" };
  authState.currentWorkspace = { id: "w1" };
});
afterEach(() => localStorage.clear());

async function flush() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

const names = (adapter) => adapter.events.map(([name]) => name);

function setup({ initialConsent = "accepted" } = {}) {
  const adapter = createMemoryAdapter();
  // Stable reference -- see useDemoAnalytics.test.jsx's note on why an inline
  // arrow here would reset AnalyticsProvider's adapter on every rerender.
  const adapterFactory = () => adapter;
  const hook = renderHook(() => useRegisteredActivation(), {
    wrapper: ({ children }) => (
      <AnalyticsProvider initialConsent={initialConsent} adapterFactory={adapterFactory}>
        {children}
      </AnalyticsProvider>
    ),
  });
  return { ...hook, adapter };
}

describe("useRegisteredActivation", () => {
  it("emits portfolio_created with only creation_path, for every valid creation path", async () => {
    const { result, adapter } = setup();
    await flush();

    act(() => {
      result.current.recordPortfolioCreated("blank");
    });
    await flush();

    expect(adapter.events).toEqual([["portfolio_created", { creation_path: "blank" }]]);
  });

  it("emits dashboard_first_value_rendered then user_activation_reached once an import source and a populated dashboard both exist (import first)", async () => {
    const { result, adapter } = setup();
    await flush();

    act(() => {
      result.current.recordPortfolioDataImported("csv");
    });
    await flush();
    expect(names(adapter)).toEqual(["portfolio_data_imported"]);

    act(() => {
      result.current.recordPopulatedDashboard();
    });
    await flush();

    expect(adapter.events).toEqual([
      ["portfolio_data_imported", { source_type: "csv" }],
      ["dashboard_first_value_rendered", { source_type: "csv" }],
      ["user_activation_reached", { source_type: "csv" }],
    ]);
  });

  it("waits for an import source when the dashboard populates first, then emits both milestones in order", async () => {
    const { result, adapter } = setup();
    await flush();

    act(() => {
      result.current.recordPopulatedDashboard();
    });
    await flush();
    expect(adapter.events).toEqual([]);

    act(() => {
      result.current.recordPortfolioDataImported("broker");
    });
    await flush();

    expect(adapter.events).toEqual([
      ["portfolio_data_imported", { source_type: "broker" }],
      ["dashboard_first_value_rendered", { source_type: "broker" }],
      ["user_activation_reached", { source_type: "broker" }],
    ]);
  });

  it("does not re-emit the activation milestone on a duplicate populated-dashboard call", async () => {
    const { result, adapter } = setup();
    await flush();
    act(() => {
      result.current.recordPortfolioDataImported("csv");
    });
    await flush();
    act(() => {
      result.current.recordPopulatedDashboard();
    });
    await flush();
    const countAfterFirst = adapter.events.length;

    act(() => {
      result.current.recordPopulatedDashboard();
    });
    await flush();

    expect(adapter.events.length).toBe(countAfterFirst);
  });

  it("gives a different workspace its own separate activation lifecycle", async () => {
    const { result, adapter, rerender } = setup();
    await flush();
    act(() => {
      result.current.recordPortfolioDataImported("csv");
    });
    await flush();
    act(() => {
      result.current.recordPopulatedDashboard();
    });
    await flush();
    expect(names(adapter)).toEqual(["portfolio_data_imported", "dashboard_first_value_rendered", "user_activation_reached"]);

    authState.currentWorkspace = { id: "w2" };
    rerender();
    await flush();

    act(() => {
      result.current.recordPopulatedDashboard();
    });
    await flush();
    // w2 has never had an import recorded, so a populated dashboard alone must not activate it.
    expect(names(adapter)).toEqual(["portfolio_data_imported", "dashboard_first_value_rendered", "user_activation_reached"]);

    act(() => {
      result.current.recordPortfolioDataImported("demo");
    });
    await flush();
    expect(names(adapter).slice(3)).toEqual(["portfolio_data_imported", "dashboard_first_value_rendered", "user_activation_reached"]);
    expect(adapter.events[3]).toEqual(["portfolio_data_imported", { source_type: "demo" }]);
  });

  it("never includes a local scope key or any extra property beyond the event contract schema", async () => {
    const { result, adapter } = setup();
    await flush();
    act(() => {
      result.current.recordPortfolioCreated("csv");
    });
    act(() => {
      result.current.recordPortfolioDataImported("csv");
    });
    act(() => {
      result.current.recordPopulatedDashboard();
    });
    await flush();

    expect(names(adapter)).toEqual([
      "portfolio_created",
      "portfolio_data_imported",
      "dashboard_first_value_rendered",
      "user_activation_reached",
    ]);
    for (const [, properties] of adapter.events) {
      const keys = Object.keys(properties);
      expect(keys).not.toContain("scope");
      expect(keys).not.toContain("workspaceId");
      expect(keys).not.toContain("userId");
      expect(keys.length).toBeGreaterThan(0);
    }
  });

  it("safely no-ops and returns false when there is no signed-in user or workspace yet", async () => {
    authState.user = null;
    authState.currentWorkspace = null;
    const { result, adapter } = setup();
    await flush();

    let createdResult, importedResult, dashboardResult;
    act(() => {
      createdResult = result.current.recordPortfolioCreated("blank");
      importedResult = result.current.recordPortfolioDataImported("csv");
      dashboardResult = result.current.recordPopulatedDashboard();
    });
    await flush();

    expect(createdResult).toBe(false);
    expect(importedResult).toBe(false);
    expect(dashboardResult).toBe(false);
    expect(adapter.events).toEqual([]);
  });

  it("keeps activation progress across a hook remount (e.g. Onboarding to Dashboard) when consent is accepted", async () => {
    const adapter = createMemoryAdapter();
    const adapterFactory = () => adapter;
    const wrapper = ({ children }) => (
      <AnalyticsProvider initialConsent="accepted" adapterFactory={adapterFactory}>
        {children}
      </AnalyticsProvider>
    );
    const first = renderHook(() => useRegisteredActivation(), { wrapper });
    await flush();
    act(() => {
      first.result.current.recordPortfolioDataImported("csv");
    });
    await flush();
    first.unmount();

    const second = renderHook(() => useRegisteredActivation(), { wrapper });
    await flush();
    act(() => {
      second.result.current.recordPopulatedDashboard();
    });
    await flush();

    expect(names(adapter)).toEqual(["portfolio_data_imported", "dashboard_first_value_rendered", "user_activation_reached"]);
  });

  it("does not persist to localStorage when consent is rejected", async () => {
    const { result } = setup({ initialConsent: "rejected" });
    await flush();
    act(() => {
      result.current.recordPortfolioDataImported("csv");
    });
    await flush();

    expect(localStorage.getItem("portfyl_activation_v1:u1:w1")).toBeNull();
  });
});
