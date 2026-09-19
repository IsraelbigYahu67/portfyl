import { Link } from "react-router-dom";
import PortfolioHero from "../../components/PortfolioHero";
import PerformanceChart from "../../components/PerformanceChart";
import MetricCard from "../../components/MetricCard";
import { SectionHeader } from "../../components/ui/SectionHeader";
import { formatMoney, formatPercent } from "../../lib/format";
import { useDemoData } from "../DemoDataContext";

function buildSummary(data) {
  const lastPoint = data.performance.at(-1);
  const previousPoint = data.performance.at(-2) || lastPoint;
  const totalValue = data.holdings.reduce((sum, holding) => sum + holding.marketValue, 0);
  const totalInvested = lastPoint.invested;
  const totalPnl = totalValue - data.transactions.reduce((sum, transaction) => sum + transaction.amount, 0);
  const dayChange = lastPoint.value - previousPoint.value;
  const dayChangePercent = previousPoint.value === 0 ? 0 : (dayChange / previousPoint.value) * 100;

  return {
    net_worth: totalValue + data.cash,
    total_value: totalValue,
    cash: data.cash,
    total_invested: totalInvested,
    total_pnl: totalPnl,
    total_dividends: data.dividendTotal,
    holdings_count: data.holdings.length,
    day_change: dayChange,
    day_change_percent: dayChangePercent,
  };
}

export default function DemoOverview() {
  const data = useDemoData();
  const summary = buildSummary(data);

  return (
    <div className="space-y-8">
      <div>
        <p className="eyebrow data-label">Synthetic portfolio</p>
        <h1 className="text-2xl font-display font-bold mt-1">Overview</h1>
      </div>

      <PortfolioHero summary={summary} loading={false} currency="USD" series={data.performance} />

      <section aria-labelledby="demo-performance-heading" className="card p-5">
        <SectionHeader><span id="demo-performance-heading">Portfolio performance</span></SectionHeader>
        <div
          role="region"
          aria-label="Portfolio performance summary"
          className="financial-meta text-muted"
        >
          Synthetic weekly portfolio values since {data.performance[0].date}; final value {formatMoney(summary.net_worth, "USD")}.
        </div>
        <PerformanceChart
          data={data.performance}
          currency="USD"
          benchmarks={data.benchmarks}
          benchmarkMeta={data.benchmarkMeta}
        />
      </section>

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
