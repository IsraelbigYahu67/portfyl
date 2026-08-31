import { columnChanges, ttmUnderlayRect } from "./chartChanges";

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

  it("useAbs compares magnitudes instead of signed values", () => {
    // CapEx-style: -10 -> -15 is growing spend, i.e. a +50% increase in
    // magnitude, not the -50% a signed diff would report.
    expect(columnChanges(rows(-10, -15), { useAbs: true })).toEqual([null, 50]);
    // -15 -> -10 is shrinking spend, a -33.3% decrease in magnitude.
    expect(columnChanges(rows(-15, -10), { useAbs: true })[1]).toBeCloseTo(-33.333, 2);
  });

  it("useAbs guards against a zero base", () => {
    expect(columnChanges(rows(0, -50), { useAbs: true })).toEqual([null, null]);
  });
});

describe("ttmUnderlayRect", () => {
  const yScale = (value) => 100 - value;

  it("draws a positive TTM value from the zero baseline", () => {
    expect(ttmUnderlayRect(yScale, 60)).toEqual({ y: 40, height: 60 });
  });

  it("draws a negative TTM value from the zero baseline", () => {
    expect(ttmUnderlayRect(yScale, -30)).toEqual({ y: 100, height: 30 });
  });

  it("omits an empty underlay at zero", () => {
    expect(ttmUnderlayRect(yScale, 0)).toBeNull();
  });
});
