import { useState } from "react";
import { Link } from "react-router-dom";
import PortfolioHero from "../../components/PortfolioHero";
import MetricCard from "../../components/MetricCard";
import PerformancePanel from "../../components/showcase/PerformancePanel";
import { buildSummary } from "../../components/showcase/showcaseMath";
import { SectionHeader } from "../../components/ui/SectionHeader";
import { formatMoney, formatPercent } from "../../lib/format";
import { useDemoData } from "../DemoDataContext";

const MODES = [
  { value: "value", label: "Value" },
  { value: "growth", label: "Growth %" },
];

const LABELS = {
  title: "Portfolio performance",
  modeAria: "Chart mode",
  totalReturn: "Total return",
  benchmarkReturn: "S&P 500 return",
  tableCaption: "Portfolio and S&P 500 by month",
  columns: { date: "Month", value: "Portfolio value", benchmark: "S&P 500" },
};

export default function DemoOverview() {
  const data = useDemoData();
  const [mode, setMode] = useState("value");
  const summary = buildSummary(data);

  return (
    <div className="space-y-8">
      <div>
        <p className="eyebrow data-label">Synthetic portfolio</p>
        <h1 className="text-2xl font-display font-bold mt-1">Overview</h1>
      </div>

      <PortfolioHero summary={summary} loading={false} currency="USD" series={data.performance} />

      <PerformancePanel
        performance={data.performance}
        benchmarks={data.benchmarks}
        benchmarkMeta={data.benchmarkMeta}
        currency="USD"
        mode={mode}
        onModeChange={setMode}
        modes={MODES}
        labels={LABELS}
        showKpis={false}
        intro={(
          <div
            role="region"
            aria-label="Portfolio performance summary"
            className="financial-meta text-muted mb-3"
          >
            Synthetic weekly portfolio values since {data.performance[0].date}; final value {formatMoney(summary.net_worth, "USD")}.
          </div>
        )}
      />

      <section aria-labelledby="demo-holdings-heading">
        <SectionHeader><span id="demo-holdings-heading">Holdings</span></SectionHeader>
        <div className="overflow-x-auto card">
          <table className="w-full min-w-[720px] text-left">
            <caption className="sr-only">Synthetic portfolio holdings</caption>
            <thead className="border-b border-hairline text-muted">
              <tr className="data-label">
                <th scope="col" className="px-4 py-3">Symbol</th>
                <th scope="col" className="px-4 py-3">Name</th>
                <th scope="col" className="px-4 py-3">Sector</th>
                <th scope="col" className="px-4 py-3 text-right">Value</th>
                <th scope="col" className="px-4 py-3 text-right">Weight</th>
                <th scope="col" className="px-4 py-3 text-right">P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {data.holdings.map((holding) => {
                const pnl = holding.marketValue - holding.quantity * holding.averageCost;
                const pnlPercent = holding.averageCost === 0 ? 0 : ((holding.currentPrice - holding.averageCost) / holding.averageCost) * 100;
                return (
                  <tr key={holding.symbol} className="border-b border-hairline last:border-0">
                    <td className="px-4 py-3 financial-data font-mono font-bold"><Link to={`/demo/stock/${holding.symbol}`} className="hover:text-brand">{holding.symbol}</Link></td>
                    <td className="px-4 py-3 financial-data"><Link to={`/demo/stock/${holding.symbol}`} className="hover:text-brand">{holding.name}</Link></td>
                    <td className="px-4 py-3 financial-meta">{holding.sector}</td>
                    <td className="px-4 py-3 financial-data text-right">{formatMoney(holding.marketValue, "USD")}</td>
                    <td className="px-4 py-3 financial-data text-right">{formatPercent(holding.weight, { sign: false })}</td>
                    <td className={`px-4 py-3 financial-data text-right ${pnl >= 0 ? "text-gain" : "text-loss"}`}>
                      {formatMoney(pnl, "USD")} ({formatPercent(pnlPercent)})
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className="grid gap-4 sm:grid-cols-3">
        <MetricCard label="Synthetic dividends" value={formatMoney(data.dividendTotal, "USD")} />
        <MetricCard label="Cash" value={formatMoney(data.cash, "USD")} />
        <MetricCard label="Positions" value={String(data.holdings.length)} />
      </div>
    </div>
  );
}
