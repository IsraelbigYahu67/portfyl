import PerformanceChart from "../../components/PerformanceChart";
import KpiBox from "../../components/ui/KpiBox";
import { SectionHeader } from "../../components/ui/SectionHeader";
import { formatPercent } from "../../lib/format";
import { useDemoData } from "../DemoDataContext";

const PERIODS_PER_YEAR = 52;

function finite(value) {
  return Number.isFinite(value) ? value : 0;
}

function calculateMetrics(performance) {
  const values = performance.map((point) => point.value);
  const weeklyReturns = values.slice(1).map((value, index) => finite(value / values[index] - 1));
  const totalReturn = finite(values.at(-1) / values[0] - 1);
  const annualizedReturn = finite((1 + totalReturn) ** (PERIODS_PER_YEAR / weeklyReturns.length) - 1);
  const mean = weeklyReturns.reduce((sum, value) => sum + value, 0) / weeklyReturns.length;
  const variance = weeklyReturns.length > 1
    ? weeklyReturns.reduce((sum, value) => sum + (value - mean) ** 2, 0) / (weeklyReturns.length - 1)
    : 0;
  const volatility = finite(Math.sqrt(variance) * Math.sqrt(PERIODS_PER_YEAR));
  const sharpe = volatility === 0 ? 0 : finite(annualizedReturn / volatility);

  let peak = values[0];
  let maximumDrawdown = 0;
  for (const value of values) {
    peak = Math.max(peak, value);
    maximumDrawdown = Math.min(maximumDrawdown, finite(value / peak - 1));
  }

  const months = new Map();
  for (const point of performance) {
    const key = point.date.slice(0, 7);
    const period = months.get(key) || { key, first: point.value, last: point.value };
    period.last = point.value;
    months.set(key, period);
  }
  const monthReturns = [...months.values()].map((month) => ({
    ...month,
    pct: finite(month.last / month.first - 1),
  }));
  const bestMonth = monthReturns.reduce((best, month) => month.pct > best.pct ? month : best, monthReturns[0]);
  const worstMonth = monthReturns.reduce((worst, month) => month.pct < worst.pct ? month : worst, monthReturns[0]);

  return {
    totalReturn, annualizedReturn, volatility, sharpe, maximumDrawdown, bestMonth, worstMonth,
    growth: performance.map((point) => ({
      ...point,
      pnl_pct: finite(point.value / values[0] - 1) * 100,
    })),
  };
}

export default function DemoAnalytics() {
  const data = useDemoData();
  const metrics = calculateMetrics(data.performance);
  const benchmarkFinal = data.benchmarks.sp500.at(-1)?.pct ?? 0;

  return (
    <div className="space-y-8">
      <div>
        <p className="eyebrow data-label">Synthetic portfolio</p>
        <h1 className="text-2xl font-display font-bold mt-1">Analytics</h1>
      </div>

      <section aria-labelledby="demo-analytics-metrics">
        <SectionHeader><span id="demo-analytics-metrics">Synthetic performance metrics</span></SectionHeader>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <KpiBox label="Total return" value={formatPercent(metrics.totalReturn * 100)} />
          <KpiBox label="Annualized return" value={formatPercent(metrics.annualizedReturn * 100)} />
          <KpiBox label="Volatility" value={formatPercent(metrics.volatility * 100, { sign: false })} />
          <KpiBox label="Sharpe ratio" value={metrics.sharpe.toFixed(2)} />
          <KpiBox label="Maximum drawdown" value={formatPercent(metrics.maximumDrawdown * 100, { sign: false })} />
          <KpiBox label="Best month" value={formatPercent(metrics.bestMonth.pct * 100)} sub={metrics.bestMonth.key} subTone="gain" />
          <KpiBox label="Worst month" value={formatPercent(metrics.worstMonth.pct * 100)} sub={metrics.worstMonth.key} subTone="loss" />
          <KpiBox label="Portfolio vs S&P 500" value={`${formatPercent(metrics.totalReturn * 100)} / ${formatPercent(benchmarkFinal)}`} />
        </div>
      </section>

      <section className="card p-5" aria-labelledby="demo-comparison-heading">
        <SectionHeader><span id="demo-comparison-heading">Portfolio vs S&amp;P 500</span></SectionHeader>
        <p className="financial-meta text-muted">Synthetic portfolio and benchmark values, shown for demonstration only.</p>
        <PerformanceChart
          data={metrics.growth}
          mode="growth"
          currency="USD"
          benchmarks={data.benchmarks}
          benchmarkMeta={data.benchmarkMeta}
        />
      </section>
    </div>
  );
}
