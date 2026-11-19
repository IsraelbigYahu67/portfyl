import { describe, expect, it } from "vitest";
import { COPY } from "../../../pages/welcomeCopy";
import {
  allocationGroupings,
  allocationLabels,
  dividendsLabels,
  dividendsViews,
  performanceLabels,
  performanceModes,
  portfoliosLabels,
  stockLabels,
  stockPickAria,
} from "./miniDemoLabels";

const LANGUAGES = ["cs", "en", "de"];

// Every leaf is a non-empty string.
function leaves(value, path = "") {
  if (value && typeof value === "object") {
    return Object.entries(value).flatMap(([key, child]) => leaves(child, `${path}.${key}`));
  }
  return [[path, value]];
}

function shape(value) {
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, child]) => [key, shape(child)]));
  }
  return typeof value;
}

describe.each(LANGUAGES)("miniDemoLabels (%s)", (language) => {
  const copy = COPY[language].miniDemo;

  it("maps the allocation copy onto the panel labels", () => {
    expect(shape(allocationLabels(copy))).toEqual({
      title: "string", groupingAria: "string", tableCaption: "string",
      columns: { name: "string", value: "string", weight: "string" },
    });
    expect(allocationLabels(copy).title).toBe(copy.allocation.title);
    expect(allocationGroupings(copy)).toEqual([
      { value: "holdings", label: copy.allocation.groupings.holdings },
      { value: "sectors", label: copy.allocation.groupings.sectors },
      { value: "currencies", label: copy.allocation.groupings.currencies },
    ]);
  });

  it("maps the stock copy onto the panel labels", () => {
    expect(shape(stockLabels(copy))).toEqual({
      pe: "string", fivePe: "string", forwardPe: "string", vsAverage: "string",
      historyTitle: "string", tableCaption: "string", disclaimer: "string",
    });
    expect(stockPickAria(copy)).toBe(copy.stock.pickAria);
  });

  it("maps the performance copy onto the panel labels", () => {
    expect(shape(performanceLabels(copy))).toEqual({
      title: "string", modeAria: "string", totalReturn: "string", benchmarkReturn: "string", tableCaption: "string",
      columns: { date: "string", value: "string", benchmark: "string" },
    });
    expect(performanceModes(copy)).toEqual([
      { value: "value", label: copy.performance.modes.value },
      { value: "growth", label: copy.performance.modes.growth },
    ]);
  });

  it("maps the dividends copy onto the panel labels", () => {
    expect(shape(dividendsLabels(copy))).toEqual({
      received: "string", upcoming: "string", receivedTotal: "string", upcomingTotal: "string",
      viewAria: "string", tableCaption: "string", columns: { month: "string", amount: "string" },
    });
    expect(dividendsViews(copy)).toEqual([
      { value: "received", label: copy.dividends.received },
      { value: "upcoming", label: copy.dividends.upcoming },
    ]);
  });

  it("maps the portfolios copy onto the panel labels", () => {
    expect(shape(portfoliosLabels(copy))).toEqual({
      currencyAria: "string", ratesNote: "string", tableCaption: "string",
      portfolioNames: { long: "string", dividend: "string", growth: "string" },
      columns: { name: "string", value: "string", weight: "string" },
    });
  });

  it("never hands a panel an empty or missing text", () => {
    const all = [
      allocationLabels(copy), allocationGroupings(copy), stockLabels(copy), stockPickAria(copy),
      performanceLabels(copy), performanceModes(copy), dividendsLabels(copy), dividendsViews(copy), portfoliosLabels(copy),
    ];
    for (const part of all) {
      for (const [path, leaf] of leaves(part)) {
        // `value` of an option is a key, the rest are texts: both must be set.
        expect(typeof leaf, path).toBe("string");
        expect(leaf.trim().length, path).toBeGreaterThan(0);
      }
    }
  });
});
