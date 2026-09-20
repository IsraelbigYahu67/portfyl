import { useMemo, useState } from "react";
import AllocationChart from "../../components/AllocationChart";
import AllocationBreakdownList from "../../components/AllocationBreakdownList";
import KpiBox from "../../components/ui/KpiBox";
import { SectionHeader } from "../../components/ui/SectionHeader";
import { formatMoney, formatPercent } from "../../lib/format";
import { useDemoData } from "../DemoDataContext";

const BREAKDOWNS = [
  ["holdings", "Holdings"],
  ["sectors", "Sectors"],
  ["countries", "Countries"],
  ["currencies", "Currencies"],
  ["assetTypes", "Asset types"],
];

function groupHoldings(holdings, key) {
  const labelFor = {
    holdings: (holding) => holding.symbol,
    sectors: (holding) => holding.sector,
    countries: (holding) => holding.country,
    currencies: (holding) => holding.currency,
    assetTypes: (holding) => holding.assetType,
  }[key];
  const rows = new Map();
  for (const holding of holdings) {
    const name = labelFor(holding);
    const current = rows.get(name) || { name, value: 0, weight: 0 };
    current.value += holding.marketValue;
    current.weight += holding.weight;
    rows.set(name, current);
  }
  return [...rows.values()].map((row) => ({
    ...row,
    value: Number(row.value.toFixed(2)),
    weight: Number(row.weight.toFixed(2)),
  }));
}

export default function DemoAllocation() {
  const data = useDemoData();
  const [breakdown, setBreakdown] = useState("holdings");
  const positionTotal = data.holdings.reduce((sum, holding) => sum + holding.marketValue, 0);
  const totalWeight = data.holdings.reduce((sum, holding) => sum + holding.weight, 0);
  const rows = useMemo(() => groupHoldings(data.holdings, breakdown), [data.holdings, breakdown]);
  const chartHoldings = data.holdings.map((holding) => ({
    ticker: holding.symbol,
    market_value: holding.marketValue,
    weight: holding.weight,
  }));

  return (
    <div className="space-y-8">
      <div>
        <p className="eyebrow data-label">Synthetic portfolio</p>
        <h1 className="text-2xl font-display font-bold mt-1">Allocation</h1>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <KpiBox label="Positions" value={formatMoney(positionTotal, "USD")} />
        <KpiBox label="Portfolio weight" value={formatPercent(totalWeight, { sign: false })} />
        <KpiBox label="Diversification" value="10 sectors" />
      </div>

      <section className="card p-5" aria-labelledby="allocation-chart-heading">
        <SectionHeader><span id="allocation-chart-heading">Position allocation</span></SectionHeader>
        <AllocationChart holdings={chartHoldings} currency="USD" />
      </section>

      <section aria-labelledby="allocation-details-heading" className="card p-5">
        <SectionHeader
          action={(
            <div className="flex gap-2 overflow-x-auto pb-1" aria-label="Allocation grouping">
              {BREAKDOWNS.map(([key, label]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setBreakdown(key)}
                  aria-pressed={breakdown === key}
                  className={`rounded-lg px-3 py-2 text-sm whitespace-nowrap focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus ${
                    breakdown === key ? "bg-brand/10 text-brand" : "text-muted hover:text-ink"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
        ><span id="allocation-details-heading">Allocation details</span></SectionHeader>
        <table className="sr-only" aria-label="Allocation details">
          <caption>Text equivalent for the allocation chart</caption>
          <thead><tr><th>Name</th><th>Value</th><th>Weight</th></tr></thead>
          <tbody>{rows.map((row) => <tr key={row.name}><td>{row.name}</td><td>{formatMoney(row.value, "USD")}</td><td>{formatPercent(row.weight, { sign: false })}</td></tr>)}</tbody>
        </table>
        <AllocationBreakdownList rows={rows} currency="USD" />
      </section>
    </div>
  );
}
