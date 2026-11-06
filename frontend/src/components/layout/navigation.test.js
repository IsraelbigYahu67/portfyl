import { describe, expect, it } from "vitest";
import {
  BOTTOM_NAV_ITEMS,
  bottomNavChoices,
  buildNavGroups,
  groupsWithoutBottomNav,
  NAV_GROUPS,
  resolveBottomNavItems,
} from "./navigation";
import { TRACKER_HOME } from "../../lib/routes";

describe("bottom bar choices", () => {
  it("offers every page in sidebar order, with the bar's own label for Allocation", () => {
    const choices = bottomNavChoices(NAV_GROUPS);
    expect(choices.map((c) => c.to)).toEqual(NAV_GROUPS.flatMap((g) => g.items.map((i) => i.to)));
    expect(choices.find((c) => c.to === "/allocation").label).toBe("Positions");
    expect(choices.find((c) => c.to === "/cash").label).toBe("Cash");
  });

  it("resolves a stored pick in navigation order and drops unknown pages", () => {
    const items = resolveBottomNavItems(NAV_GROUPS, ["/settings", "/nope", "/cash", TRACKER_HOME]);
    expect(items.map((i) => i.to)).toEqual([TRACKER_HOME, "/cash", "/settings"]);
  });

  it("falls back to the default bar when fewer than two known pages remain", () => {
    const defaults = BOTTOM_NAV_ITEMS.map((i) => i.to);
    expect(resolveBottomNavItems(NAV_GROUPS, ["/cash"]).map((i) => i.to)).toEqual(defaults);
    expect(resolveBottomNavItems(NAV_GROUPS, null).map((i) => i.to)).toEqual(defaults);
    expect(resolveBottomNavItems(NAV_GROUPS, ["/cash"], { min: 1 }).map((i) => i.to)).toEqual(["/cash"]);
  });

  it("More lists everything the bar does not, dropping emptied groups", () => {
    const bar = resolveBottomNavItems(NAV_GROUPS, ["/search", "/watchlists"]);
    const rest = groupsWithoutBottomNav(NAV_GROUPS, bar);
    expect(rest.map((g) => g.id)).toEqual(["portfolio", "insights", "system"]);
    expect(rest.flatMap((g) => g.items.map((i) => i.to))).not.toContain("/search");
    // Default bar: the portfolio group keeps only Cash.
    expect(groupsWithoutBottomNav(NAV_GROUPS)[0].items.map((i) => i.to)).toEqual(["/cash"]);
  });
});

describe("NAV_GROUPS", () => {
  it("has exactly the four named groups in order", () => {
    expect(NAV_GROUPS.map((group) => group.id)).toEqual([
      "portfolio",
      "research",
      "insights",
      "system",
    ]);
  });

  it("does not contain an Overview entry anywhere", () => {
    const allLabels = NAV_GROUPS.flatMap((group) => group.items.map((item) => item.label));
    expect(allLabels).not.toContain("Overview");
  });

  it("portfolio group has Dashboard, Allocation, Transactions, Cash", () => {
    const portfolio = NAV_GROUPS.find((group) => group.id === "portfolio");
    expect(portfolio.items.map((item) => item.to)).toEqual([
      TRACKER_HOME,
      "/allocation",
      "/transactions",
      "/cash",
    ]);
  });
});

describe("buildNavGroups", () => {
  const taxReportEntry = { to: "/tax-report", label: "Tax Report", icon: () => null, capability: "tax_report" };
  const pricingEntry = { to: "/pricing", label: "Plans", icon: () => null, capability: "settings" };

  it("merges Tax Report into Insights when its capability is enabled", () => {
    const groups = buildNavGroups([taxReportEntry], ["tax_report"]);
    const insights = groups.find((group) => group.id === "insights");
    expect(insights.items.some((item) => item.to === "/tax-report")).toBe(true);
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
