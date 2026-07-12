import { groupPositions, OTHER_SLICE } from "./positionsPie";

const holding = (ticker, weight, market_value, extra = {}) => ({
  ticker, weight, market_value, closed: false, ...extra,
});

describe("groupPositions", () => {
  it("gives each >threshold position a slice, sorted by weight desc", () => {
    const slices = groupPositions([
      holding("MSFT", 30, 3000),
      holding("AAPL", 45, 4500),
      holding("NVDA", 25, 2500),
    ]);
    expect(slices.map((s) => s.name)).toEqual(["AAPL", "MSFT", "NVDA"]);
    expect(slices[0]).toEqual({ name: "AAPL", value: 4500, weight: 45 });
  });

  it("groups positions at or below the threshold into Other with items detail", () => {
    const slices = groupPositions([
      holding("AAPL", 90, 9000),
      holding("PLTR", 2, 200), // exactly 2% is NOT > 2 → grouped
      holding("SOFI", 1.5, 150),
      holding("GME", 6.5, 650),
    ]);
    expect(slices.map((s) => s.name)).toEqual(["AAPL", "GME", OTHER_SLICE]);
    const other = slices[slices.length - 1];
    expect(other.weight).toBe(3.5);
    expect(other.value).toBe(350);
    expect(other.items).toEqual([
      { name: "PLTR", weight: 2 },
      { name: "SOFI", weight: 1.5 },
    ]);
  });

  it("omits the Other slice when nothing falls below the threshold", () => {
    const slices = groupPositions([holding("AAPL", 100, 10000)]);
    expect(slices.map((s) => s.name)).toEqual(["AAPL"]);
    expect(slices[0].items).toBeUndefined();
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
