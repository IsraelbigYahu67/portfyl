import { useState } from "react";
import PerformancePanel from "../../components/showcase/PerformancePanel";
import KpiBox from "../../components/ui/KpiBox";
import { SectionHeader } from "../../components/ui/SectionHeader";
import { formatPercent } from "../../lib/format";
import { calculateMetrics } from "../../components/showcase/showcaseMath";
import { useDemoData } from "../DemoDataContext";

const MODES = [
  { value: "value", label: "Value" },
  { value: "growth", label: "Growth %" },
];

const LABELS = {
  title: "Portfolio vs S&P 500",
  modeAria: "Chart mode",
  totalReturn: "Total return",
  benchmarkReturn: "S&P 500 return",
  tableCaption: "Portfolio and S&P 500 by month",
  columns: { date: "Month", value: "Portfolio value", benchmark: "S&P 500" },
};

export default function DemoAnalytics() {
  const data = useDemoData();
  const [mode, setMode] = useState("growth");
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
        intro={<p className="financial-meta text-muted mb-3">Synthetic portfolio and benchmark values, shown for demonstration only.</p>}
      />
    </div>
  );
}
