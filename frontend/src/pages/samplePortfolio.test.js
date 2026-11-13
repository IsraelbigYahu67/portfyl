import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import sample from "../assets/sample_portfolio.csv?raw";

// The downloadable sample on the Import page: 30 companies, every sector,
// in the native CSV format the backend accepts without errors.
// Vitest runs from frontend/, so the repo root is one level up.
const rootSample = readFileSync(resolve(process.cwd(), "../sample_portfolio.csv"), "utf8");
const [header, ...lines] = sample.trim().split(/\r?\n/);
const rows = lines.map((line) => {
  const [date, ticker, type, shares, price, currency] = line.split(",");
  return { date, ticker, type, shares: Number(shares), price: Number(price), currency };
});

describe("sample_portfolio.csv", () => {
  it("matches the repo-root sample_portfolio.csv", () => {
    const normalize = (text) => text.replace(/\r\n/g, "\n").trim();
    expect(normalize(sample)).toBe(normalize(rootSample));
  });

  it("uses the native import header", () => {
    expect(header).toBe("date,ticker,type,shares,price,currency");
  });

  it("holds 30 companies with buys, sells and dividends", () => {
    expect(new Set(rows.map((r) => r.ticker)).size).toBe(30);
    expect(new Set(rows.map((r) => r.type))).toEqual(new Set(["buy", "sell", "dividend"]));
  });

  it("has only valid rows", () => {
    for (const r of rows) {
      expect(r.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(r.shares).toBeGreaterThan(0);
      expect(r.price).toBeGreaterThan(0);
      expect(r.currency).toMatch(/^[A-Z]{3}$/);
    }
  });
});
