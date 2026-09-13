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
  const rows = Array.from({ length: 8 }, (_, i) => ({ name: `R${i}`, value: 8 - i, weight: 20 - i }));

  it("bounds eight rows to seven plus Other while the list retains all eight", () => {
    const bounded = boundedAllocationRows(rows);
    expect(bounded).toHaveLength(8);
    expect(bounded[7].name).toBe("Other");
    expect(bounded[7].items).toHaveLength(1);
  });

  it("returns rows unchanged when there are seven or fewer", () => {
    expect(boundedAllocationRows(rows.slice(0, 7))).toHaveLength(7);
  });
});
