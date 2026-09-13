// Composition rows for the Allocation page. One helper maps the selected
// category to its source (active holdings or an API breakdown dimension), and
// one bounds a chart to seven named segments plus Other while the full list
// always keeps every row.

const DIMENSIONS = {
  sector: "sectors",
  asset_type: "asset_types",
  currency: "currencies",
  account: "accounts",
};

const round2 = (n) => Math.round(n * 100) / 100;

export function allocationRows({ category, holdings = [], breakdown = {} } = {}) {
  if (category === "position") {
    const active = (holdings || []).filter((h) => h && !h.closed && h.market_value > 0);
    return [...active]
      .sort((a, b) => b.weight - a.weight)
      .map((h) => ({ name: h.ticker, value: h.market_value, weight: h.weight }));
  }

  const key = DIMENSIONS[category];
  const rows = (key && breakdown?.[key]) || [];
  return [...rows]
    .sort((a, b) => b.weight - a.weight)
    .map((r) => ({
      name: r.name,
      value: r.value,
      weight: r.weight,
      ...(r.items ? { items: r.items } : {}),
    }));
}

export function boundedAllocationRows(rows, maxNamed = 7) {
  const sorted = [...(rows || [])].sort((a, b) => b.weight - a.weight);
  if (sorted.length <= maxNamed) return sorted;

  const major = sorted.slice(0, maxNamed);
  const rest = sorted.slice(maxNamed);
  return [
    ...major,
    {
      name: "Other",
      value: round2(rest.reduce((sum, r) => sum + r.value, 0)),
      weight: round2(rest.reduce((sum, r) => sum + r.weight, 0)),
      items: rest,
    },
  ];
}
