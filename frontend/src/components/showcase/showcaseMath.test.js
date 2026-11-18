import { afterEach, describe, expect, it, vi } from "vitest";
import { demoPortfolio } from "../../demo/demoPortfolio";
import { splitDividendForecast } from "../../lib/dashboardSummaries";
import { SHOWCASE_PE_HISTORY, showcaseHoldings } from "./showcaseData";
import {
  buildDividendForecast,
  buildSummary,
  calculateMetrics,
  fiveYearAveragePe,
  groupHoldings,
  quarterKey,
  stockHeaderData,
  sumBy,
} from "./showcaseMath";

afterEach(() => vi.useRealTimers());

const weightSum = (rows) => rows.reduce((sum, row) => sum + row.weight, 0);

describe("groupHoldings", () => {
  it("groups the demo portfolio by position and by sector", () => {
    const positions = groupHoldings(demoPortfolio.holdings, "holdings");
    expect(positions).toHaveLength(10);
    expect(Math.abs(weightSum(positions) - 100)).toBeLessThanOrEqual(0.01);
    const sectors = groupHoldings(demoPortfolio.holdings, "sectors");
    expect(sectors).toHaveLength(10);
    expect(Math.abs(weightSum(sectors) - 100)).toBeLessThanOrEqual(0.01);
    expect(groupHoldings(demoPortfolio.holdings, "countries").map((row) => row.name).sort()).toEqual(["Ireland", "United States"]);
    expect(groupHoldings(demoPortfolio.holdings, "assetTypes").map((row) => [row.name, row.weight])).toEqual([["ETF", 18], ["Stock", 82]]);
  });

  it("shows the three sample currencies when the holdings are quoted in different ones", () => {
    const rows = groupHoldings(showcaseHoldings("CZK"), "currencies");
    expect(rows.map((row) => row.name).sort()).toEqual(["CZK", "EUR", "USD"]);
    expect(Math.abs(weightSum(rows) - 100)).toBeLessThanOrEqual(0.01);
  });

  it("rejects an unknown grouping", () => {
    expect(() => groupHoldings([], "colours")).toThrow();
  });
});

describe("moved page maths (unchanged results)", () => {
  it("calculateMetrics matches what /demo/analytics showed", () => {
    const metrics = calculateMetrics(demoPortfolio.performance);
    expect(metrics.totalReturn).toBeCloseTo(0.44630410072667837, 12);
    expect(metrics.annualizedReturn).toBeCloseTo(0.20262384007913226, 12);
    expect(metrics.volatility).toBeCloseTo(0.00799216003070636, 12);
    expect(metrics.sharpe).toBeCloseTo(25.352825681748023, 9);
    expect(metrics.maximumDrawdown).toBe(0);
    expect(metrics.bestMonth.key).toBe("2025-08");
    expect(metrics.bestMonth.pct).toBeCloseTo(0.020556965648610426, 12);
    expect(metrics.worstMonth.key).toBe("2026-09");
    expect(metrics.growth).toHaveLength(demoPortfolio.performance.length);
    expect(metrics.growth.at(-1).pnl_pct).toBeCloseTo(44.630410072667836, 9);
  });

  it("buildSummary matches what /demo showed", () => {
    expect(buildSummary(demoPortfolio)).toEqual({
      net_worth: 105000,
      total_value: 100000,
      cash: 5000,
      total_invested: 90000,
      total_pnl: 10000,
      total_dividends: 2840,
      holdings_count: 10,
      day_change: 198,
      day_change_percent: 0.18892769221961414,
    });
  });

  it("quarterKey and sumBy match what /demo/dividends showed", () => {
    expect(quarterKey("2025-02-03")).toBe("2025 Q1");
    expect(quarterKey("2025-12-31")).toBe("2025 Q4");
    const quarters = sumBy(demoPortfolio.dividends, (row) => quarterKey(row.date));
    expect(quarters).toHaveLength(8);
    expect(quarters[0]).toEqual({ key: "2026 Q3", amount: 355 });
    expect(quarters.at(-1)).toEqual({ key: "2024 Q4", amount: 355 });
  });

  it("stockHeaderData maps a holding to the header shape", () => {
    expect(stockHeaderData(demoPortfolio.holdings[1])).toEqual({
      ticker: "MSFT", name: "Microsoft", currency: "USD", price: 480, change: 5.76, change_percent: 1.2,
      sector: "Information Technology", country: "United States", market_cap: 3560000000000,
      ratios: { pe: 34.2, forward_pe: 30.1, div_yield: 0.7 },
      fifty_two_week_low: 390.5, fifty_two_week_high: 495.2,
    });
  });
});

describe("fiveYearAveragePe", () => {
  it("averages the trailing P/E of the five years up to the last point", () => {
    // 20 quarterly points: (31.8 + ... + 34.2) / 20, summed by hand = 649.9.
    expect(fiveYearAveragePe(SHOWCASE_PE_HISTORY.MSFT)).toBeCloseTo(32.495, 10);
    expect(fiveYearAveragePe(SHOWCASE_PE_HISTORY.JNJ)).toBeCloseTo(15.955, 10);
  });

  it("ignores points older than five years before the last point", () => {
    const points = [
      { bucket: "2019-01-01", trailing_pe: 100 },
      { bucket: "2021-06-30", trailing_pe: 10 },
      { bucket: "2026-06-30", trailing_pe: 20 },
    ];
    expect(fiveYearAveragePe(points)).toBe(15);
  });

  it("ignores points without a P/E and returns null without data", () => {
    expect(fiveYearAveragePe([])).toBeNull();
    expect(fiveYearAveragePe(null)).toBeNull();
    expect(fiveYearAveragePe([{ bucket: "2026-01-01", trailing_pe: null }])).toBeNull();
    expect(fiveYearAveragePe([
      { bucket: "2025-01-01", trailing_pe: null },
      { bucket: "2026-01-01", trailing_pe: 12 },
    ])).toBe(12);
  });
});

describe("buildDividendForecast", () => {
  const { dividends, asOf } = demoPortfolio;
  const forecast = buildDividendForecast(dividends, asOf);

  it("has the 12 months of the as-of year with nothing paid after the as-of date", () => {
    expect(forecast.year).toBe(2026);
    expect(forecast.months.map((month) => month.month)).toEqual(
      ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    );
    for (const month of forecast.months.slice(9)) expect(month.paid).toBe(0);
    const paidInYear = forecast.months.reduce((sum, month) => sum + month.paid, 0);
    const expected = dividends
      .filter((row) => row.date.startsWith("2026") && row.date <= asOf)
      .reduce((sum, row) => sum + row.amount, 0);
    expect(paidInYear).toBe(expected);
    expect(forecast.total_paid_all_time).toBe(demoPortfolio.dividendTotal);
  });

  it("repeats last year's months as the outlook, starting with the as-of month", () => {
    expect(forecast.outlook.months).toHaveLength(12);
    expect(forecast.outlook.months[0]).toMatchObject({ month: "Sep", year: 2026 });
    expect(forecast.outlook.months.at(-1)).toMatchObject({ month: "Aug", year: 2027 });
    const december = forecast.outlook.months.find((month) => month.month === "Dec");
    expect(december).toMatchObject({ year: 2026, confirmed: 0, forecasted: 355 });
    // September already paid on the 15th, so nothing is left to forecast.
    expect(forecast.outlook.months[0].forecasted).toBe(0);
  });

  it("feeds splitDividendForecast with money received and money to come", () => {
    const { received, upcoming } = splitDividendForecast(forecast, { monthIndex: 8 });
    expect(received.total).toBe(1065);
    expect(received.months).toHaveLength(9);
    expect(upcoming.total).toBe(1065);
    expect(upcoming.months).toHaveLength(12);
    expect(received.allTime).toBe(2840);
  });

  it("does not depend on the clock", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2031-01-01T00:00:00Z"));
    const later = buildDividendForecast(dividends, asOf);
    vi.setSystemTime(new Date("2020-05-05T00:00:00Z"));
    expect(buildDividendForecast(dividends, asOf)).toEqual(later);
    expect(later).toEqual(forecast);
  });
});
