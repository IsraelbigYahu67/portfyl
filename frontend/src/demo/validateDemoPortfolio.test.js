import { describe, it, expect } from "vitest";
import { demoPortfolio, HOLDING_SEEDS } from "./demoPortfolio";
import { assertDemoPortfolio } from "./validateDemoPortfolio";

const EXPECTED_SYMBOLS = ["VUAA", "MSFT", "JPM", "JNJ", "XOM", "PG", "AMZN", "CAT", "NEE", "PLD"];

function clone(data) {
  return JSON.parse(JSON.stringify(data));
}

describe("assertDemoPortfolio -- valid fixture", () => {
  it("returns the same object when the fixture is valid", () => {
    expect(assertDemoPortfolio(clone(demoPortfolio))).toEqual(clone(demoPortfolio));
  });

  it("holds exactly the ten approved symbols, in the approved order", () => {
    const data = clone(demoPortfolio);
    expect(data.holdings.map((h) => h.symbol)).toEqual(EXPECTED_SYMBOLS);
    expect(HOLDING_SEEDS.map((h) => h.symbol)).toEqual(EXPECTED_SYMBOLS);
  });

  it("gives every holding a unique sector/role", () => {
    const data = clone(demoPortfolio);
    const sectors = data.holdings.map((h) => h.sector);
    expect(new Set(sectors).size).toBe(10);
  });

  it("sums weights to 100 within 0.01", () => {
    const data = clone(demoPortfolio);
    const total = data.holdings.reduce((sum, h) => sum + h.weight, 0);
    expect(Math.abs(total - 100)).toBeLessThanOrEqual(0.01);
  });

  it("sums position market value to USD 100,000 within one cent", () => {
    const data = clone(demoPortfolio);
    const total = data.holdings.reduce((sum, h) => sum + h.marketValue, 0);
    expect(Math.abs(total - 100000)).toBeLessThanOrEqual(0.01);
  });

  it("carries non-zero cash", () => {
    const data = clone(demoPortfolio);
    expect(data.cash).toBeGreaterThan(0);
  });

  it("covers roughly two years of weekly performance history", () => {
    const data = clone(demoPortfolio);
    expect(data.performance.length).toBe(105);
    expect(data.performance.at(-1).date).toBe(data.asOf);
    expect(data.performance.at(-1).value).toBeCloseTo(105000, 2);
  });

  it("has at least six dividend rows across at least four distinct quarters", () => {
    const data = clone(demoPortfolio);
    expect(data.dividends.length).toBeGreaterThanOrEqual(6);
    const quarters = new Set(
      data.dividends.map((d) => `${d.date.slice(0, 4)}-Q${Math.floor((Number(d.date.slice(5, 7)) - 1) / 3) + 1}`)
    );
    expect(quarters.size).toBeGreaterThanOrEqual(4);
  });

  it("reconciles dividendTotal with the sum of dividend rows", () => {
    const data = clone(demoPortfolio);
    const sum = Math.round(data.dividends.reduce((s, d) => s + d.amount, 0) * 100) / 100;
    expect(Math.abs(sum - data.dividendTotal)).toBeLessThanOrEqual(0.01);
  });

  it("reconciles each holding's quantity with its recorded BUY transactions", () => {
    const data = clone(demoPortfolio);
    for (const holding of data.holdings) {
      const lots = data.transactions.filter((t) => t.symbol === holding.symbol && t.type === "BUY");
      const qty = lots.reduce((s, t) => s + t.quantity, 0);
      expect(Math.abs(qty - holding.quantity)).toBeLessThanOrEqual(0.00001);
    }
  });
});

describe("assertDemoPortfolio -- mutation guards", () => {
  function mutated(mutate) {
    const data = clone(demoPortfolio);
    mutate(data);
    return data;
  }

  it("throws when the holdings count is not ten", () => {
    expect(() => assertDemoPortfolio(mutated((d) => d.holdings.pop()))).toThrow();
  });

  it("throws on a duplicate symbol", () => {
    expect(() => assertDemoPortfolio(mutated((d) => { d.holdings[1].symbol = d.holdings[0].symbol; }))).toThrow();
  });

  it("throws on a duplicate sector", () => {
    expect(() => assertDemoPortfolio(mutated((d) => { d.holdings[1].sector = d.holdings[0].sector; }))).toThrow();
  });

  it("throws on a missing sector", () => {
    expect(() => assertDemoPortfolio(mutated((d) => { d.holdings[0].sector = ""; }))).toThrow();
  });

  it("throws when weights no longer reconcile", () => {
    expect(() => assertDemoPortfolio(mutated((d) => { d.holdings[0].weight += 5; }))).toThrow();
  });

  it("throws on a NaN numeric field", () => {
    expect(() => assertDemoPortfolio(mutated((d) => { d.holdings[0].marketValue = NaN; }))).toThrow();
  });

  it("throws when asOf is missing", () => {
    expect(() => assertDemoPortfolio(mutated((d) => { d.asOf = ""; }))).toThrow();
  });

  it("throws on an invalid date", () => {
    expect(() => assertDemoPortfolio(mutated((d) => { d.performance[0].date = "not-a-date"; }))).toThrow();
  });

  it("throws when performance history is missing", () => {
    expect(() => assertDemoPortfolio(mutated((d) => { d.performance = []; }))).toThrow();
  });

  it("throws when a holding's quantity no longer matches its transactions", () => {
    expect(() => assertDemoPortfolio(mutated((d) => { d.holdings[0].quantity += 1000; }))).toThrow();
  });

  it("throws when dividendTotal no longer reconciles with dividend rows", () => {
    expect(() => assertDemoPortfolio(mutated((d) => { d.dividendTotal += 1000; }))).toThrow();
  });
});
