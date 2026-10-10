import { readFile } from "node:fs/promises";
import { sourcePath } from "../test/sourcePath";
import {
  AXIS_TICK_STYLE,
  LEGEND_TEXT_STYLE,
  GRID_STROKE,
  SERIES_STYLES,
} from "./chartTheme";

describe("chartTheme constants", () => {
  it("AXIS_TICK_STYLE and LEGEND_TEXT_STYLE use at least a 12px font size", () => {
    expect(AXIS_TICK_STYLE.fontSize).toBeGreaterThanOrEqual(12);
    expect(LEGEND_TEXT_STYLE.fontSize).toBeGreaterThanOrEqual(12);
  });

  it("GRID_STROKE declares a real, non-empty stroke value", () => {
    expect(typeof GRID_STROKE).toBe("string");
    expect(GRID_STROKE.length).toBeGreaterThan(0);
  });

  it("every adjacent SERIES_STYLES entry differs by more than color", () => {
    expect(SERIES_STYLES.length).toBeGreaterThanOrEqual(3);
    for (let i = 1; i < SERIES_STYLES.length; i++) {
      expect(SERIES_STYLES[i].strokeDasharray).not.toBe(SERIES_STYLES[i - 1].strokeDasharray);
    }
  });
});

// See test/sourcePath.js for how the asset URL becomes a filesystem path.
async function readSource(relativePath) {
  const assetUrl = new URL(relativePath, import.meta.url);
  const pathname = sourcePath(assetUrl);
  return readFile(pathname, "utf-8");
}

const CHART_FILES = [
  "../components/PerformanceChart.jsx",
  "../components/AllocationChart.jsx",
  "../components/BreakdownChart.jsx",
  "../components/CashBalanceChart.jsx",
  "../components/Heatmap.jsx",
  "../components/HeroSparkline.jsx",
];

describe("chart source hygiene", () => {
  it.each(CHART_FILES)("%s imports a shared chart theme constant and avoids fontSize 10/11", async (relativePath) => {
    const src = await readSource(relativePath);
    expect(src).toMatch(/from ["']\.\.\/lib\/chartTheme["']/);
    expect(src).not.toMatch(/fontSize:\s*1[01]\b/);
  });
});
