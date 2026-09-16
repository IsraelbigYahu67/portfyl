import { renderHook } from "@testing-library/react";
import useStockReportConfig, { migrateHiddenSectionsToTabs } from "./useStockReportConfig";

beforeEach(() => localStorage.clear());

it("migrates a tab only when every meaningful legacy section was hidden", () => {
  const hidden = migrateHiddenSectionsToTabs({
    hidden: ["financials", "dividendGrowth", "earningsRecap", "ownership"],
  });
  expect(hidden).toEqual(["financials"]);
  expect(JSON.parse(localStorage.getItem("sb_stock_report_tabs"))).toEqual({
    version: 1,
    hidden: ["financials"],
  });
});

it("preserves the legacy storage key and ignores its custom order for tab order", () => {
  localStorage.setItem("sb_stock_report_sections", JSON.stringify({ order: ["ownership"], hidden: [] }));
  const { result } = renderHook(() => useStockReportConfig());
  expect(result.current.config.order[0]).toBe("ownership");
  expect(localStorage.getItem("sb_stock_report_sections")).not.toBeNull();
  expect(Object.keys(result.current.config.hiddenTabs ? { overview: 1, financials: 1, valuation: 1, ownership: 1, filings: 1 } : {}))
    .toEqual(["overview", "financials", "valuation", "ownership", "filings"]);
});
