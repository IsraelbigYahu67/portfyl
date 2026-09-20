import { describe, it, expect } from "vitest";
import { allocationRows, boundedAllocationRows } from "./allocationBreakdown";

describe("allocationRows", () => {
  it.each([
    ["sector", "sectors"],
    ["asset_type", "asset_types"],
    ["currency", "currencies"],
  ])("maps %s to its API dimension", (category, key) => {
    const breakdown = { [key]: [{ name: "One", value: 70, weight: 70 }, { name: "Two", value: 30, weight: 30 }] };
    expect(allocationRows({ category, holdings: [], breakdown })).toEqual(breakdown[key]);
  });

  it("maps active positions to ticker/value/weight and excludes closed ones", () => {
    const holdings = [
      { ticker: "AAPL", market_value: 100, weight: 60, closed: false },
      { ticker: "MSFT", market_value: 50, weight: 30, closed: false },
      { ticker: "OLD", market_value: 20, weight: 10, closed: true },
    ];
    expect(allocationRows({ category: "position", holdings })).toEqual([
      { name: "AAPL", value: 100, weight: 60 },
      { name: "MSFT", value: 50, weight: 30 },
    ]);
  });

  it("returns undefined dimension rows as an empty array", () => {
    expect(allocationRows({ category: "account", breakdown: {} })).toEqual([]);
  });
});

describe("boundedAllocationRows", () => {
  it("keeps every row above 2% weight and groups the rest into Other", () => {
    const rows = [
      { name: "A", value: 60, weight: 60 },
      { name: "B", value: 20, weight: 20 },
      { name: "C", value: 3, weight: 3 },
      { name: "D", value: 1.5, weight: 1.5 },
      { name: "E", value: 1, weight: 1 },
    ];
    const bounded = boundedAllocationRows(rows);
    expect(bounded.map((r) => r.name)).toEqual(["A", "B", "C", "Other"]);
    expect(bounded[3].weight).toBe(2.5);
    expect(bounded[3].value).toBe(2.5);
    expect(bounded[3].items).toHaveLength(2);
  });

  it("returns rows unchanged when none fall at or below the threshold", () => {
    const rows = [
      { name: "A", value: 60, weight: 60 },
      { name: "B", value: 40, weight: 40 },
    ];
    expect(boundedAllocationRows(rows)).toEqual(rows);
  });

  it("supports a custom minimum weight threshold", () => {
    const rows = [
      { name: "A", value: 90, weight: 90 },
      { name: "B", value: 6, weight: 6 },
      { name: "C", value: 4, weight: 4 },
    ];
    const bounded = boundedAllocationRows(rows, 5);
    expect(bounded.map((r) => r.name)).toEqual(["A", "B", "Other"]);
  });
});
