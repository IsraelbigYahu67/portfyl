import { describe, it, expect } from "vitest";
import {
  draftErrors,
  draftFromDrift,
  draftTotal,
  fillFromCurrentWeights,
  parseTarget,
  toPayload,
} from "./allocationTargets";

const row = (ticker, target, extra = {}) => ({
  key: ticker, ticker, name: null, group: "", target, currentPct: 0, isNew: false, ...extra,
});

describe("allocation target drafts", () => {
  it("parses targets strictly", () => {
    expect(parseTarget("")).toBeNull();
    expect(parseTarget(" 12,5 ")).toBe(12.5);
    expect(parseTarget("100")).toBe(100);
    expect(parseTarget("33.333")).toBeNaN();
    expect(parseTarget("100.5")).toBeNaN();
    expect(parseTarget("-1")).toBeNaN();
    expect(parseTarget("abc")).toBeNaN();
  });

  it("builds rows from drift, keeping no-target rows empty", () => {
    const rows = draftFromDrift({
      rows: [
        { ticker: "AAPL", name: "Apple", group: "Core", target_pct: 60, current_pct: 70 },
        { ticker: "TSLA", name: "Tesla", group: null, target_pct: null, current_pct: 30 },
      ],
    });
    expect(rows).toEqual([
      { key: "AAPL", ticker: "AAPL", name: "Apple", group: "Core", target: "60", currentPct: 70, isNew: false },
      { key: "TSLA", ticker: "TSLA", name: "Tesla", group: "", target: "", currentPct: 30, isNew: false },
    ]);
  });

  it("totals in hundredths so 0.1 + 0.2 is exactly 0.3", () => {
    expect(draftTotal([row("A", "0.1"), row("B", "0.2"), row("C", "")])).toBe(0.3);
  });

  it("flags duplicates case-insensitively and over-100 totals", () => {
    expect(draftErrors([row("AAPL", "10"), row("aapl", "20", { key: "new-1", isNew: true })]))
      .toContain("AAPL has more than one target.");
    expect(draftErrors([row("A", "60"), row("B", "40.02")]))
      .toContain("Targets add up to 100.02%, more than 100%.");
    expect(draftErrors([row("A", "60"), row("B", "40.01")])).toEqual([]);
  });

  it("flags an invalid number and a target without a ticker", () => {
    expect(draftErrors([row("A", "33.333")]))
      .toContain("The target for A must be a number from 0 to 100 with at most two decimals.");
    expect(draftErrors([row("", "10", { key: "new-1", isNew: true })]))
      .toContain("Every target needs a ticker.");
  });

  it("ignores empty rows and normalizes the payload", () => {
    expect(toPayload([
      row(" msft ", "12,5", { group: " Core " }),
      row("TSLA", ""),
      row("", "", { key: "new-1", isNew: true }),
    ])).toEqual([{ ticker: "MSFT", target_pct: "12.5", group: "Core" }]);
  });

  it("fillFromCurrentWeights totals exactly 100", () => {
    const rows = fillFromCurrentWeights([
      row("A", "", { currentPct: 33.33 }),
      row("B", "", { currentPct: 33.33 }),
      row("C", "", { currentPct: 33.33 }),
      row("D", "50", { currentPct: 0 }),
    ]);
    expect(rows.map((r) => r.target)).toEqual(["33.34", "33.33", "33.33", ""]);
    expect(draftTotal(rows)).toBe(100);
  });
});
