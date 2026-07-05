import { formatMoney, formatPercent, formatCompact, formatNumber } from "./format";

describe("formatMoney", () => {
  it("formats USD with symbol and 2dp", () => {
    expect(formatMoney(1234.5, "USD")).toBe("$1,234.50");
  });
  it("formats CZK with suffix", () => {
    expect(formatMoney(1234.5, "CZK")).toBe("1,234.50 Kč");
  });
  it("puts the sign before the symbol for negatives", () => {
    expect(formatMoney(-12, "USD")).toBe("-$12.00");
    expect(formatMoney(-12, "CZK")).toBe("-12.00 Kč");
  });
  it("returns an em dash for null/undefined", () => {
    expect(formatMoney(null)).toBe("—");
    expect(formatMoney(undefined)).toBe("—");
  });
});

describe("formatPercent", () => {
  it("adds a + for positives by default", () => {
    expect(formatPercent(2.4)).toBe("+2.40%");
  });
  it("omits the + when sign:false", () => {
    expect(formatPercent(2.4, { sign: false })).toBe("2.40%");
  });
  it("keeps the - for negatives", () => {
    expect(formatPercent(-1.2)).toBe("-1.20%");
  });
  it("returns an em dash for null", () => {
    expect(formatPercent(null)).toBe("—");
  });
});

describe("formatCompact", () => {
  it("compacts thousands with currency symbol", () => {
    expect(formatCompact(190000, "USD")).toBe("$190K");
  });
  it("returns an em dash for null", () => {
    expect(formatCompact(null)).toBe("—");
  });
});

describe("formatNumber", () => {
  it("groups with no decimals by default", () => {
    expect(formatNumber(12345)).toBe("12,345");
  });
});
