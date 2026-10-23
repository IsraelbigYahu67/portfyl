import { squarify, tileLabels } from "./Heatmap";
import { legacyColorClassesIn } from "../test/legacyClasses";

describe("tileLabels", () => {
  it("tileLabels hides labels that cannot fit at 12px", () => {
    expect(tileLabels(30, 18)).toEqual({ ticker: false, change: false, weight: false });
    expect(tileLabels(40, 24)).toEqual({ ticker: true, change: false, weight: false });
    expect(tileLabels(60, 40)).toEqual({ ticker: true, change: true, weight: false });
    expect(tileLabels(80, 56)).toEqual({ ticker: true, change: true, weight: true });
  });
});

describe("squarify", () => {
  it("squarify keeps every tile inside the box", () => {
    const weights = [8, 8, 7, 6, 6, 5, 5, 4, 4, 4, 4, 4, 4, 3, 3, 3, 3, 3, 2, 2, 2, 1.9];
    const items = weights.map((weight, i) => ({ ticker: `T${i}`, weight, change_pct: 0 }));
    const tiles = squarify(items, 600, 400);
    expect(tiles).toHaveLength(items.length);
    for (const t of tiles) {
      expect(t.x).toBeGreaterThanOrEqual(0);
      expect(t.y).toBeGreaterThanOrEqual(0);
      expect(t.x + t.w).toBeLessThanOrEqual(600.5);
      expect(t.y + t.h).toBeLessThanOrEqual(400.5);
    }
  });
});

it("uses no legacy color classes", async () => {
  expect(await legacyColorClassesIn(new URL("./Heatmap.jsx", import.meta.url))).toEqual([]);
});
