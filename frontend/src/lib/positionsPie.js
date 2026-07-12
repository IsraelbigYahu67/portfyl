// Build the "Positions" pie data from the holdings list: one slice per open
// position above the weight threshold, everything at/below it combined into
// a single "Other" slice whose `items` the tooltip lists on hover.
//
// Weights are taken straight from the holdings endpoint (% of open-holdings
// market value — cash-free, closed positions are 0) so the pie always agrees
// with the Weight column of the table below it. Cash deliberately gets no
// slice here, unlike the sector/country pies.
export const OTHER_SLICE = "Other";

export function groupPositions(holdings, threshold = 2) {
  const open = (holdings || []).filter((h) => !h.closed && h.market_value > 0);
  const major = [];
  const rest = [];
  for (const h of open) (h.weight > threshold ? major : rest).push(h);

  const byWeight = (a, b) => b.weight - a.weight;
  const slices = major
    .sort(byWeight)
    .map((h) => ({ name: h.ticker, value: h.market_value, weight: h.weight }));

  if (rest.length) {
    const round2 = (n) => Math.round(n * 100) / 100;
    slices.push({
      name: OTHER_SLICE,
      value: round2(rest.reduce((s, h) => s + h.market_value, 0)),
      weight: round2(rest.reduce((s, h) => s + h.weight, 0)),
      items: rest.sort(byWeight).map((h) => ({ name: h.ticker, weight: h.weight })),
    });
  }
  return slices;
}
