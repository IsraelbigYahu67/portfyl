import { buildFinancialAxis, formatFinancialTick, financialAxisWidth } from "./chartFinancialAxis";

const labels = (values, opts) => buildFinancialAxis(values).ticks.map((v) => formatFinancialTick(v, opts));

describe("buildFinancialAxis", () => {
  it("uses round steps and per-label units", () => {
    expect(labels([2e8, 9e8, 1.4e9])).toEqual(["0", "500M", "1B", "1.5B"]);
    expect(labels([2.5e8, 2.8e9])).toEqual(["0", "1B", "2B", "3B"]);
  });

  it("keeps zero on the axis and equal steps across signs", () => {
    const { ticks } = buildFinancialAxis([-219e6, 85e6, -60e6]);
    expect(ticks).toContain(0);
    const steps = ticks.slice(1).map((t, i) => t - ticks[i]);
    expect(new Set(steps).size).toBe(1);
    expect(ticks[0]).toBeLessThanOrEqual(-219e6);
    expect(ticks[ticks.length - 1]).toBeGreaterThanOrEqual(85e6);
    expect(labels([-219e6, 85e6])).toContain("-200M");
  });

  it("covers a value outside the bars (the TTM overlay)", () => {
    const { domain } = buildFinancialAxis([-20e6, -40e6, -810e6]);
    expect(domain[0]).toBeLessThanOrEqual(-810e6);
    expect(domain[1]).toBe(0);
  });

  it("formats small amounts and per-share values", () => {
    expect(labels([20e3, 90e3])).toEqual(["0", "25K", "50K", "75K", "100K"]);
    expect(formatFinancialTick(-4.5, { perShare: true })).toBe("-4.5");
    expect(formatFinancialTick(1.5, { perShare: true })).toBe("1.5");
  });

  it("never repeats a label and caps the tick count", () => {
    for (const vals of [[1, 2, 3], [-1e9, 3.2e9], [7e5, 1.3e6], [-0.64, 3.8]]) {
      const ls = labels(vals, { perShare: true });
      expect(new Set(ls).size).toBe(ls.length);
      expect(ls.length).toBeLessThanOrEqual(6);
    }
  });

  it("handles empty and all-zero series", () => {
    expect(buildFinancialAxis([]).ticks).toEqual([0, 1]);
    expect(buildFinancialAxis([0, 0]).ticks).toEqual([0, 1]);
  });
});

describe("financialAxisWidth", () => {
  it("fits the widest label within 52-72px", () => {
    expect(financialAxisWidth(["0", "500M"])).toBe(52);
    expect(financialAxisWidth(["-500M", "0"])).toBeGreaterThanOrEqual(5 * 7.5);
    expect(financialAxisWidth(["-1.25B"])).toBeLessThanOrEqual(72);
  });
});
