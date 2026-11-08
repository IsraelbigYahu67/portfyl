// Build the "Positions" pie data from the holdings list: the 7 largest open
// positions by weight each get their own slice, everything else combines
// into a single "Other" slice whose `items` the tooltip lists on hover.
// Bounded per spec: a portfolio with many small positions must not render
// an unreadable many-slice donut. The full sorted breakdown lives in
// AllocationBarList, not in this chart.
//
// Weights are taken straight from the holdings endpoint (% of open-holdings
// market value — cash-free, closed positions are 0) so the pie always agrees
// with the Weight column of the table below it. Cash deliberately gets no
// slice here, unlike the sector/country pies.
export const OTHER_SLICE = "Other";

export function groupPositions(holdings, maxSlices = 7) {
  const open = (holdings || []).filter((h) => !h.closed && h.market_value > 0);
  const byWeight = (a, b) => b.weight - a.weight;
  const sorted = [...open].sort(byWeight);
  // A lone leftover position keeps its own slice; "Other" must stand for at
  // least two positions.
  const cut = sorted.length === maxSlices + 1 ? sorted.length : maxSlices;
  const major = sorted.slice(0, cut);
  const rest = sorted.slice(cut);

  const slices = major.map((h) => ({ name: h.ticker, value: h.market_value, weight: h.weight }));

  if (rest.length) {
    const round2 = (n) => Math.round(n * 100) / 100;
    slices.push({
      name: OTHER_SLICE,
      value: round2(rest.reduce((s, h) => s + h.market_value, 0)),
      weight: round2(rest.reduce((s, h) => s + h.weight, 0)),
      items: rest.map((h) => ({ name: h.ticker, weight: h.weight })),
    });
  }
  return slices;
}
