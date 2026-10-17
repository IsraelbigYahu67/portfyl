import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { Sector } from "recharts";
import { describe, it, expect } from "vitest";
import { withSliceCorners } from "./pieCorners";

// Number of arc ("A") commands in the rendered wedge: a sharp wedge has 2
// (outer + inner arc), a rounded one adds 4 corner arcs.
const arcCount = (cornerRadius, endAngle) => {
  const html = renderToStaticMarkup(
    createElement("svg", null, createElement(Sector, { cx: 0, cy: 0, innerRadius: 70, outerRadius: 110, startAngle: 90, endAngle, cornerRadius })),
  );
  return (html.match(/d="([^"]+)"/)[1].match(/A/g) || []).length;
};

const opts = { valueKey: "value", inner: 70, outer: 110, corner: 7 };
const px = (d) => (parseFloat(d.cornerRadius) / 100) * (opts.outer - opts.inner);

describe("withSliceCorners", () => {
  it("keeps the full corner radius on large slices", () => {
    const [big] = withSliceCorners([{ value: 50 }, { value: 50 }], opts);
    expect(px(big)).toBeCloseTo(7);
  });

  it("shrinks the radius on thin slices instead of dropping it", () => {
    const out = withSliceCorners([{ value: 99 }, { value: 1 }], opts);
    expect(px(out[1])).toBeGreaterThan(0.5);
    expect(px(out[1])).toBeLessThan(7);
  });

  it("never exceeds what the inner arc can fit", () => {
    const out = withSliceCorners([{ value: 995 }, { value: 5 }], opts);
    const half = ((5 / 1000) * (360 - 2 * 3) * Math.PI) / 360;
    const theta = Math.asin(px(out[1]) / (opts.inner + px(out[1])));
    expect(theta).toBeLessThan(half);
  });

  it("renders a rounded wedge for a thin slice where a fixed radius would go square", () => {
    const sweep = 360 - 2 * 3;
    const angle = (1 / 100) * sweep; // 1% slice
    const fixed = arcCount(7, 90 - angle);
    const fitted = arcCount(withSliceCorners([{ value: 99 }, { value: 1 }], opts)[1].cornerRadius, 90 - angle);
    expect(fixed).toBe(2);
    expect(fitted).toBe(6);
  });

  it("leaves empty slices and empty data untouched", () => {
    expect(withSliceCorners([{ value: 0 }, { value: 4 }], opts)[0]).toEqual({ value: 0 });
    expect(withSliceCorners([], opts)).toEqual([]);
  });
});
