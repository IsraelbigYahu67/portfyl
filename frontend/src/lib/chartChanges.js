// % change of each fundamentals-chart column vs the previous displayed column
// (YoY in the annual view, QoQ in the quarterly view, estimate-vs-prior for
// forecast bars). Returns one entry per row, null where no change applies.
//
// TTM bars get null and are skipped as a comparison base — the trailing-12M
// window overlaps the fiscal year next to it, so a "change" against either
// neighbour would compare overlapping periods. Null-valued rows are likewise
// skipped as a base: the previous *visible* bar is what the eye compares
// against. Guards mirror the backend's _yoy: a zero previous value or two
// negative values yield null rather than a misleading percentage.
export function columnChanges(rows) {
  let prev = null;
  return (rows || []).map((row) => {
    if (row.isTTM) return null;
    const curr = row.value;
    const base = prev;
    if (curr != null) prev = curr;
    if (curr == null || base == null) return null;
    if (base === 0 || (base < 0 && curr < 0)) return null;
    return ((curr - base) / Math.abs(base)) * 100;
  });
}

// Convert a TTM value into a full SVG bar from the zero baseline. The actual
// fiscal-year bar is drawn above this underlay so both values remain visible.
export function ttmUnderlayRect(yScale, ttmValue) {
  if (typeof yScale !== "function" || ttmValue == null) return null;
  const yZero = yScale(0);
  const yTtm = yScale(ttmValue);
  const y = Math.min(yZero, yTtm);
  const height = Math.abs(yZero - yTtm);
  if (!Number.isFinite(y) || !Number.isFinite(height) || height <= 0) return null;
  return { y, height };
}
