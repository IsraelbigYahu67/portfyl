import { useMemo } from "react";
import PerformanceChart from "../PerformanceChart";
import KpiBox from "../ui/KpiBox";
import SegmentedControl from "../ui/SegmentedControl";
import { SectionHeader } from "../ui/SectionHeader";
import { formatMoney, formatPercent, formatShortDate } from "../../lib/format";
import { calculateMetrics } from "./showcaseMath";

const DASH = "—";

// The last point of every month: a text table of all 100+ weekly points would
// bury a screen-reader user.
function monthEnds(performance) {
  const months = new Map();
  for (const point of performance) months.set(point.date.slice(0, 7), point);
  return [...months.values()];
}

/**
 * Performance card: portfolio value or growth in %, against a benchmark.
 *
 *  - performance: weekly points { date, value, invested, ... }
 *  - benchmarks / benchmarkMeta: as PerformanceChart takes them; the first
 *    benchmark feeds the benchmark KPI and the table
 *  - mode: value | growth. In `growth` the chart gets `pnl_pct` series
 *  - modes: [{ value, label }] offered by the switch
 *  - labels: { title, modeAria, totalReturn, benchmarkReturn, tableCaption,
 *    columns: { date, value, benchmark } }
 *  - showKpis (default true): the two return tiles above the chart
 *  - intro: optional node under the title (a page's own description)
 */
export default function PerformancePanel({
  performance,
  benchmarks = {},
  benchmarkMeta = [],
  currency,
  mode,
  onModeChange,
  modes,
  labels,
  showKpis = true,
  intro = null,
}) {
  const metrics = useMemo(() => calculateMetrics(performance), [performance]);
  const chartData = mode === "growth" ? metrics.growth : performance;
  const benchmarkSeries = benchmarks[benchmarkMeta[0]?.key] ?? [];
  const benchmarkFinal = benchmarkSeries.at(-1)?.pct;
  const benchmarkByDate = useMemo(
    () => new Map(benchmarkSeries.map((point) => [point.date, point.pct])),
    [benchmarkSeries],
  );
  const rows = useMemo(() => monthEnds(performance), [performance]);

  return (
    <section className="card p-5 min-w-0">
      <SectionHeader
        action={(
          <SegmentedControl aria-label={labels.modeAria} value={mode} onChange={onModeChange} options={modes} />
        )}
      >
        {labels.title}
      </SectionHeader>
      {intro}
      {showKpis && (
        <div className="grid gap-4 sm:grid-cols-2 mb-4">
          <KpiBox label={labels.totalReturn} value={formatPercent(metrics.totalReturn * 100)} />
          <KpiBox label={labels.benchmarkReturn} value={Number.isFinite(benchmarkFinal) ? formatPercent(benchmarkFinal) : DASH} />
        </div>
      )}
      <PerformanceChart
        data={chartData}
        mode={mode}
        currency={currency}
        benchmarks={benchmarks}
        benchmarkMeta={benchmarkMeta}
      />
      <table className="sr-only">
        <caption>{labels.tableCaption}</caption>
        <thead>
          <tr>
            <th scope="col">{labels.columns.date}</th>
            <th scope="col">{labels.columns.value}</th>
            <th scope="col">{labels.columns.benchmark}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((point) => (
            <tr key={point.date}>
              <th scope="row">{formatShortDate(point.date, { month: "short", year: "numeric" })}</th>
              <td>{formatMoney(point.value, currency)}</td>
              <td>{benchmarkByDate.has(point.date) ? formatPercent(benchmarkByDate.get(point.date)) : DASH}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
