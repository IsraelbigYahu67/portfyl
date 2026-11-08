import { groupPositions, OTHER_SLICE } from "./positionsPie";

const holding = (ticker, weight, market_value, extra = {}) => ({
  ticker, weight, market_value, closed: false, ...extra,
});

const makeHoldings = (n) =>
  Array.from({ length: n }, (_, i) => holding(`T${i}`, 10 - i * 0.1, 100 - i));

describe("groupPositions — top-7-plus-Other bounding", () => {
  it("returns every slice unbounded when there are 7 or fewer positions", () => {
    const slices = groupPositions(makeHoldings(7));
    expect(slices).toHaveLength(7);
    expect(slices.find((s) => s.name === OTHER_SLICE)).toBeUndefined();
  });

  it("caps the chart at 7 named slices plus one Other slice for more than 7 positions", () => {
    const slices = groupPositions(makeHoldings(10));
    const named = slices.filter((s) => s.name !== OTHER_SLICE);
    expect(named).toHaveLength(7);
    expect(slices.find((s) => s.name === OTHER_SLICE)).toBeDefined();
  });

  it("shows a single leftover position under its own name instead of Other", () => {
    const slices = groupPositions(makeHoldings(8));
    expect(slices).toHaveLength(8);
    expect(slices.find((s) => s.name === OTHER_SLICE)).toBeUndefined();
    expect(slices[7].name).toBe("T7");
  });

  it("puts the 7 largest-by-weight positions in named slices, not the first 7 in input order", () => {
    const holdings = [holding("SMALL", 0.1, 1), holding("TINY", 0.05, 1), ...makeHoldings(7)];
    const slices = groupPositions(holdings);
    expect(slices.map((s) => s.name)).not.toContain("SMALL");
  });

  it("Other slice sums the value and weight of every excluded position", () => {
    const slices = groupPositions(makeHoldings(9));
    const other = slices.find((s) => s.name === OTHER_SLICE);
    const excluded = makeHoldings(9).slice(7);
    expect(other.value).toBeCloseTo(excluded.reduce((s, h) => s + h.market_value, 0), 2);
  });

  it("gives each named position a slice sorted by weight descending", () => {
    const slices = groupPositions([
      holding("MSFT", 30, 3000),
      holding("AAPL", 45, 4500),
      holding("NVDA", 25, 2500),
    ]);
    expect(slices.map((s) => s.name)).toEqual(["AAPL", "MSFT", "NVDA"]);
    expect(slices[0]).toEqual({ name: "AAPL", value: 4500, weight: 45 });
  });

  it("excludes closed and zero-value positions", () => {
    const slices = groupPositions([
      holding("AAPL", 100, 10000),
      holding("SOLD", 0, 0, { closed: true }),
      holding("GHOST", 0, 0),
    ]);
    expect(slices.map((s) => s.name)).toEqual(["AAPL"]);
  });

  it("returns [] for empty or missing holdings", () => {
    expect(groupPositions([])).toEqual([]);
    expect(groupPositions(undefined)).toEqual([]);
  });
});
