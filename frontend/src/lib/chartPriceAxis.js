export function buildPriceAxis(prices) {
  const values = (prices || []).filter((value) => Number.isFinite(value) && value >= 0);
  if (!values.length) return [0, 1, 2, 3, 4];

  const min = Math.min(...values);
  const max = Math.max(...values);
  const requiredStep = Math.max(1, (max - min) / 4);
  let magnitude = 10 ** Math.max(0, Math.floor(Math.log10(requiredStep)));

  // Five labels give exactly three interior prices. Prefer whole-unit steps,
  // then 10/25/50, 100/250/500, etc., growing until the rounded bounds fit.
  for (;;) {
    const multiples = magnitude === 1 ? [1, 2, 5] : [1, 2.5, 5];
    for (const multiple of multiples) {
      const step = magnitude * multiple;
      if (step < requiredStep) continue;
      const firstMin = Math.max(0, Math.ceil(max / step) - 4);
      const firstMax = Math.floor(min / step);
      if (firstMin > firstMax) continue;
      const centeredFirst = Math.round((min / step + max / step) / 2 - 2);
      const first = Math.min(firstMax, Math.max(firstMin, centeredFirst));
      return Array.from({ length: 5 }, (_, index) => (first + index) * step);
    }
    magnitude *= 10;
  }
}
