// Recharts drops corner rounding entirely (draws a sharp wedge) when a donut
// slice is too thin for the requested `cornerRadius`. This gives every slice
// the largest corner radius that still fits its own width, so small slices
// stay rounded instead of snapping square.
//
// Recharts reads a per-datum `cornerRadius` ahead of the <Pie> prop, and a
// percentage string is taken relative to the ring thickness (outer - inner).
// That keeps this unit-agnostic: pass `inner`, `outer` and `corner` in the
// same unit (pixels, or percent of the donut's max radius when the <Pie> uses
// "62%"-style radii).
export function withSliceCorners(data, { valueKey, inner, outer, corner, padding = 3 }) {
  const values = data.map((d) => Math.max(Number(d[valueKey]) || 0, 0));
  const total = values.reduce((s, v) => s + v, 0);
  const visible = values.filter((v) => v > 0).length;
  const thickness = outer - inner;
  if (!total || thickness <= 0) return data;

  const sweep = Math.max(360 - visible * padding, 0);
  return data.map((d, i) => {
    if (values[i] <= 0) return d;
    const half = ((values[i] / total) * sweep * Math.PI) / 360; // half the slice angle, in radians
    const s = Math.sin(half);
    // Widest corner whose tangent points still fit on the inner arc (the
    // narrowest edge). 0.95 keeps a hair of arc so Recharts never bails out.
    const fit = inner > 0 ? ((inner * s) / (1 - s)) * 0.95 : thickness / 2;
    const radius = Math.min(corner, fit, thickness / 2);
    return { ...d, cornerRadius: `${(radius / thickness) * 100}%` };
  });
}
