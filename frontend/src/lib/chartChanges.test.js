import { columnChanges } from "./chartChanges";

const rows = (...values) => values.map((value) => ({ value }));

describe("columnChanges", () => {
  it("returns vs-previous-column % change, null for the first column", () => {
    const out = columnChanges(rows(100, 110, 99));
    expect(out[0]).toBeNull();
    expect(out[1]).toBeCloseTo(10, 10);
    expect(out[2]).toBeCloseTo(-10, 10);
  });

  it("handles empty / missing input", () => {
    expect(columnChanges([])).toEqual([]);
    expect(columnChanges(null)).toEqual([]);
  });

  it("skips TTM rows and bridges the comparison across them", () => {
    const input = [{ value: 100 }, { value: 120 }, { value: 130, isTTM: true }, { value: 150 }];
    // 150 compares against 120 (last non-TTM), not the TTM bar.
    expect(columnChanges(input)).toEqual([null, 20, null, 25]);
  });

  it("skips null-valued rows as a comparison base", () => {
    const input = rows(100, null, 150);
    // The gap bar isn't drawn, so 150 compares against 100.
    expect(columnChanges(input)).toEqual([null, null, 50]);
  });

  it("guards against a zero base", () => {
    expect(columnChanges(rows(0, 50))).toEqual([null, null]);
  });

  it("guards against negative-to-negative changes", () => {
    expect(columnChanges(rows(-10, -5))).toEqual([null, null]);
  });

  it("uses abs(base) when crossing from negative to positive", () => {
    // -10 -> 5 is a +150% swing relative to |−10|.
    expect(columnChanges(rows(-10, 5))).toEqual([null, 150]);
  });
});
