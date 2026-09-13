import { describe, expect, it } from "vitest";
import { buildNavGroups, NAV_GROUPS } from "./navigation";
import { TRACKER_HOME } from "../../lib/routes";

describe("NAV_GROUPS", () => {
  it("has exactly the five named groups in order", () => {
    expect(NAV_GROUPS.map((group) => group.id)).toEqual([
      "portfolio",
      "research",
      "insights",
      "assistant",
      "system",
    ]);
  });

  it("does not contain an Overview entry anywhere", () => {
    const allLabels = NAV_GROUPS.flatMap((group) => group.items.map((item) => item.label));
    expect(allLabels).not.toContain("Overview");
  });

  it("portfolio group has Dashboard, Allocation, Transactions", () => {
    const portfolio = NAV_GROUPS.find((group) => group.id === "portfolio");
    expect(portfolio.items.map((item) => item.to)).toEqual([
      TRACKER_HOME,
      "/allocation",
      "/transactions",
    ]);
  });
});

describe("buildNavGroups", () => {
  const taxReportEntry = { to: "/tax-report", label: "Tax Report", icon: () => null, capability: "tax_report" };
  const screenerEntry = { to: "/screener", label: "Screener", icon: () => null, capability: "screener" };
  const pricingEntry = { to: "/pricing", label: "Plans", icon: () => null, capability: "settings" };

  it("merges Tax Report into Insights and Screener into Research when capabilities enable them", () => {
    const groups = buildNavGroups(
      [taxReportEntry, screenerEntry],
      ["tax_report", "screener"],
    );
    const insights = groups.find((group) => group.id === "insights");
    const research = groups.find((group) => group.id === "research");
    expect(insights.items.some((item) => item.to === "/tax-report")).toBe(true);
    expect(research.items.some((item) => item.to === "/screener")).toBe(true);
  });

  it("omits an edition entry whose capability is not enabled", () => {
    const groups = buildNavGroups([taxReportEntry], []);
    const insights = groups.find((group) => group.id === "insights");
    expect(insights.items.some((item) => item.to === "/tax-report")).toBe(false);
  });

  it("falls back unmapped edition entries to the System group", () => {
    const groups = buildNavGroups([pricingEntry], ["settings"]);
    const system = groups.find((group) => group.id === "system");
    expect(system.items.some((item) => item.to === "/pricing")).toBe(true);
  });

  it("never mutates the base NAV_GROUPS array", () => {
    const before = NAV_GROUPS.map((group) => group.items.map((item) => item.to));
    buildNavGroups([taxReportEntry], ["tax_report"]);
    const after = NAV_GROUPS.map((group) => group.items.map((item) => item.to));
    expect(after).toEqual(before);
  });
});
