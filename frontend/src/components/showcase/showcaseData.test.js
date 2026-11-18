import { describe, expect, it } from "vitest";
import {
  SHOWCASE_AS_OF,
  SHOWCASE_PE_HISTORY,
  SHOWCASE_PORTFOLIOS,
  SHOWCASE_RATES_TO_CZK,
  convertAmount,
  portfolioTotals,
  showcaseHoldings,
} from "./showcaseData";

function frozenDeep(value) {
  if (value && typeof value === "object") {
    return Object.isFrozen(value) && Object.values(value).every(frozenDeep);
  }
  return true;
}

function keysDeep(value, found = new Set()) {
  if (Array.isArray(value)) value.forEach((item) => keysDeep(item, found));
  else if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      found.add(key);
      keysDeep(item, found);
    }
  }
  return found;
}

const sum = (rows, pick) => rows.reduce((total, row) => total + pick(row), 0);

describe("showcase portfolios", () => {
  it("has three sample portfolios with the agreed keys and currencies", () => {
    expect(SHOWCASE_PORTFOLIOS.map((portfolio) => [portfolio.key, portfolio.baseCurrency])).toEqual([
      ["long", "EUR"], ["dividend", "USD"], ["growth", "CZK"],
    ]);
  });

  it("versions every id", () => {
    for (const portfolio of SHOWCASE_PORTFOLIOS) {
      expect(portfolio.id.startsWith("portfyl-showcase-v1")).toBe(true);
      for (const item of portfolio.holdings) expect(item.id.startsWith("portfyl-showcase-v1")).toBe(true);
    }
  });

  it("uses a fixed sample exchange rate", () => {
    expect(SHOWCASE_RATES_TO_CZK).toEqual({ CZK: 1, EUR: 25, USD: 23 });
    expect(SHOWCASE_AS_OF).toBe("2026-09-18");
    expect(convertAmount(100, "EUR", "CZK")).toBe(2500);
    expect(convertAmount(2300, "CZK", "USD")).toBe(100);
    expect(convertAmount(12.34, "USD", "USD")).toBe(12.34);
    expect(() => convertAmount(1, "GBP", "CZK")).toThrow();
  });

  it("spreads over several sectors and countries", () => {
    const all = SHOWCASE_PORTFOLIOS.flatMap((portfolio) => portfolio.holdings);
    expect(new Set(all.map((item) => item.sector)).size).toBeGreaterThanOrEqual(3);
    expect(new Set(all.map((item) => item.country)).size).toBeGreaterThanOrEqual(3);
    expect(new Set(all.map((item) => item.symbol)).size).toBe(all.length);
  });

  it("rounds sample values to two decimals", () => {
    for (const portfolio of SHOWCASE_PORTFOLIOS) {
      for (const item of [...portfolio.holdings, portfolio]) {
        const value = item.marketValue ?? item.cash;
        expect(Math.abs(value * 100 - Math.round(value * 100))).toBeLessThan(1e-6);
      }
    }
  });

  it("is deeply frozen and carries no personal fields", () => {
    expect(frozenDeep(SHOWCASE_PORTFOLIOS)).toBe(true);
    expect(frozenDeep(SHOWCASE_PE_HISTORY)).toBe(true);
    const keys = keysDeep([SHOWCASE_PORTFOLIOS, SHOWCASE_PE_HISTORY]);
    for (const forbidden of ["account", "iban", "email", "user"]) expect(keys.has(forbidden)).toBe(false);
  });
});

describe("showcaseHoldings", () => {
  it.each(["CZK", "EUR", "USD"])("weights add up to 100 in %s and keep the same order", (currency) => {
    const rows = showcaseHoldings(currency);
    expect(Math.abs(sum(rows, (row) => row.weight) - 100)).toBeLessThanOrEqual(0.01);
    expect(rows.map((row) => row.symbol)).toEqual(showcaseHoldings("CZK").map((row) => row.symbol));
    expect(rows.every((row) => row.weight > 0)).toBe(true);
  });

  it("keeps the quote currency of every holding", () => {
    expect([...new Set(showcaseHoldings("CZK").map((row) => row.currency))].sort()).toEqual(["CZK", "EUR", "USD"]);
  });

  it("converts at the sample rate", () => {
    const vwceCzk = showcaseHoldings("CZK").find((row) => row.symbol === "VWCE");
    expect(vwceCzk.marketValue).toBe(18400 * 25);
    const cezEur = showcaseHoldings("EUR").find((row) => row.symbol === "CEZ");
    expect(cezEur.marketValue).toBe(5700);
  });
});

describe("portfolioTotals", () => {
  it.each(["CZK", "EUR", "USD"])("adds the cash to the positions in %s", (currency) => {
    const totals = portfolioTotals(currency);
    const cash = sum(SHOWCASE_PORTFOLIOS, (portfolio) => convertAmount(portfolio.cash, portfolio.baseCurrency, currency));
    expect(Math.abs(sum(totals, (row) => row.value) - (sum(showcaseHoldings(currency), (row) => row.marketValue) + cash))).toBeLessThanOrEqual(0.01);
    expect(Math.abs(sum(totals, (row) => row.weight) - 100)).toBeLessThanOrEqual(0.01);
    expect(totals.map((row) => row.key)).toEqual(["long", "dividend", "growth"]);
  });

  it("reports cash in the display currency", () => {
    const totals = portfolioTotals("CZK");
    expect(totals.find((row) => row.key === "long").cash).toBe(1200 * 25);
    expect(totals.find((row) => row.key === "growth").cash).toBe(85000);
  });
});

describe("SHOWCASE_PE_HISTORY", () => {
  it.each(["MSFT", "JNJ", "PG"])("has 20 rising quarterly points for %s", (symbol) => {
    const points = SHOWCASE_PE_HISTORY[symbol];
    expect(points).toHaveLength(20);
    const buckets = points.map((point) => point.bucket);
    expect([...buckets].sort()).toEqual(buckets);
    expect(new Set(buckets).size).toBe(20);
    expect(buckets.at(-1) <= SHOWCASE_AS_OF).toBe(true);
    for (const point of points) {
      expect(Number.isFinite(point.trailing_pe)).toBe(true);
      expect(point.trailing_pe).toBeGreaterThan(0);
    }
  });
});
