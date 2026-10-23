// Derive the strongest pairwise correlations from a full correlation matrix.
// The matrix is symmetric with a 1.0 diagonal, so we walk only the upper
// triangle (i < j) to avoid reporting each pair twice and never report a
// ticker against itself. Sorting is by absolute value: a strong negative
// correlation (-0.9) matters as much as a strong positive one for
// diversification, so both surface at the top.
export function topAbsoluteCorrelationPairs(tickers, matrix, n = 10) {
  if (!tickers || tickers.length < 2 || !matrix) return [];
  const pairs = [];
  for (let i = 0; i < tickers.length; i++) {
    for (let j = i + 1; j < tickers.length; j++) {
      pairs.push({ a: tickers[i], b: tickers[j], value: matrix[i][j] });
    }
  }
  return pairs.sort((p, q) => Math.abs(q.value) - Math.abs(p.value)).slice(0, n);
}

// Heatmap cell tint: copper (--chart-2) for positive correlation, the cool
// chart hue (--chart-4) for negative, deeper with |v|. The caller paints the
// diagonal (self-correlation) with --bg-subtle instead.
export function correlationColor(v) {
  const hue = v >= 0 ? "var(--chart-2)" : "var(--chart-4)";
  const percent = Math.round(15 + 55 * Math.min(1, Math.abs(v)));
  return `color-mix(in srgb, ${hue} ${percent}%, var(--surface-card))`;
}
