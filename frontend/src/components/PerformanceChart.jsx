import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Customized,
} from "recharts";
import { formatMoney, formatPercent } from "../lib/format";
import { AXIS_TICK_STYLE, LEGEND_TEXT_STYLE, GRID_STROKE, NEUTRAL_COLOR, SERIES_STYLES } from "../lib/chartTheme";
import { buildPercentAxis } from "../lib/chartPercentAxis";
import { splitGrowthLineSegments } from "../lib/growthLineSegments";

// One scrollable row: with a few benchmark indexes the legend used to wrap to a
// second line on a phone and shove the plot down.
const LEGEND_WRAPPER_STYLE = {
  paddingBottom: "20px",
  width: "100%",
  overflowX: "auto",
  whiteSpace: "nowrap",
  scrollbarWidth: "none",
};

const GROWTH_GAIN_STROKE = "#5B8567";
const GROWTH_LOSS_STROKE = "#A7655C";
const benchmarkDash = (i) => SERIES_STYLES[(i % (SERIES_STYLES.length - 1)) + 1].strokeDasharray;

function GrowthLineLayer({ xAxisMap, yAxisMap, series }) {
  const xScale = xAxisMap && Object.values(xAxisMap)[0]?.scale;
  const yScale = yAxisMap && Object.values(yAxisMap)[0]?.scale;
  if (!xScale || !yScale) return null;

  const segments = splitGrowthLineSegments(series.map((point) => ({
    x: xScale(point.date),
    y: yScale(point.pnl_pct),
    value: point.pnl_pct,
  })), yScale(0));

  return (
    <g pointerEvents="none">
      {segments.map((segment, index) => (
        <line
          key={index}
          x1={segment.x1}
          y1={segment.y1}
          x2={segment.x2}
          y2={segment.y2}
          stroke={segment.isGain ? GROWTH_GAIN_STROKE : GROWTH_LOSS_STROKE}
          strokeWidth={2.5}
          strokeLinecap="round"
        />
      ))}
    </g>
  );
}

function CustomTooltip({ active, payload, label, currency, benchmarkMeta, mode }) {
  if (!active || !payload?.length) return null;

  const row = payload[0]?.payload;
  if (!row) return null;

  const pnl = row.pnl;
  const pnlPct = row.pnl_pct;
  const totalPnl = row.total_pnl;
  const totalPnlPct = row.total_pnl_pct;

  const line = (name, val, color) => (
    <div className="flex justify-between gap-6">
      <span className="text-muted">{name}</span>
      <span className={`font-sans tabular-nums font-medium ${color}`}>{val}</span>
    </div>
  );
  const moneyColor = (v) => (v >= 0 ? "text-gain" : "text-loss");

  return (
    <div className="bg-surface-card-elevated border border-hairline rounded-xl shadow-pop px-3 py-2 text-xs">
      <p className="text-muted mb-1.5">{label}</p>
      <div className="space-y-1">
        {mode === "value" && (
          <>
            {line("Value", formatMoney(row.value, currency), "text-ink")}
            {line("Deposited", formatMoney(row.invested, currency), "text-muted")}
          </>
        )}
        {pnl != null && line("Period P&L", formatMoney(pnl, currency), moneyColor(pnl))}
        {pnlPct != null && line("Period % (TWR)", formatPercent(pnlPct), moneyColor(pnlPct))}
        {totalPnl != null && line("Total P&L", formatMoney(totalPnl, currency), moneyColor(totalPnl))}
        {totalPnlPct != null && line("Total % (TWR)", formatPercent(totalPnlPct), moneyColor(totalPnlPct))}
        {benchmarkMeta?.map((b) => {
          const val = row[`bench_${b.key}`];
          if (val == null) return null;
          return (
            <div key={b.key} className="flex justify-between gap-6">
              <span style={{ color: b.color }}>{b.label}</span>
              <span style={{ color: b.color }} className="font-sans tabular-nums font-medium">
                {formatPercent(val)}
              </span>
            </div>
          );
        })}
      </div>
      {(pnlPct != null || totalPnlPct != null) && (
        <p className="financial-meta mt-1.5 pt-1.5 border-t border-hairline">
          % = time-weighted return, excludes deposits/withdrawals
        </p>
      )}
    </div>
  );
}

export default function PerformanceChart({ data, currency = "USD", mode = "value", benchmarks = {}, benchmarkMeta = [] }) {
  if (!data?.length) return <div className="text-muted text-sm">No performance data yet.</div>;

  const merged = data.map((point) => {
    const row = { ...point };
    for (const b of benchmarkMeta) {
      const series = benchmarks[b.key];
      if (series) {
        const match = series.find((s) => s.date === point.date);
        row[`bench_${b.key}`] = match ? match.pct : null;
      }
    }
    return row;
  });

  const sampled = merged.filter((_, i) => i % Math.ceil(merged.length / 120) === 0);
  const shortRange = data.length <= 60;
  const hasBenchmarks = benchmarkMeta.length > 0;
  const isGrowth = mode === "growth";
  const growthValues = merged.flatMap((point) => [
    point.pnl_pct,
    ...benchmarkMeta.map((benchmark) => point[`bench_${benchmark.key}`]),
  ]).filter(Number.isFinite);
  const { domain: growthDomain, ticks: growthTicks } = buildPercentAxis(growthValues);
  const growthZeroOffset = (growthDomain[1] / (growthDomain[1] - growthDomain[0])) * 100;

  const fmtAxis = (v) => {
    if (currency === "CZK") {
      return v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M Kč` : `${(v / 1_000).toFixed(0)}k Kč`;
    }
    return v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(1)}M` : `$${(v / 1_000).toFixed(0)}k`;
  };

  const fmtPctAxis = (v) => `${v > 0 ? "+" : ""}${v}%`;

  return (
    <div className="flex-1 min-h-[300px] mt-6 -mx-2 -mb-2 relative">
      <div className="absolute inset-0">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={sampled} margin={{ top: 4, right: hasBenchmarks && !isGrowth ? 50 : 4, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="var(--brand)" stopOpacity={0.25} />
              <stop offset="95%" stopColor="var(--brand)" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="colorInvested" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={NEUTRAL_COLOR} stopOpacity={0.15} />
              <stop offset="95%" stopColor={NEUTRAL_COLOR} stopOpacity={0} />
            </linearGradient>
            <linearGradient id="colorGrowth" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#638B70" stopOpacity={0.42} />
              <stop offset={`${growthZeroOffset}%`} stopColor="#7C9A7F" stopOpacity={0.04} />
              <stop offset={`${growthZeroOffset}%`} stopColor="#B17C74" stopOpacity={0.04} />
              <stop offset="100%" stopColor="#B17C74" stopOpacity={0.42} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={GRID_STROKE} vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ ...AXIS_TICK_STYLE, fontFamily: "JetBrains Mono Variable" }}
            tickFormatter={(v) => shortRange ? v.slice(5) : v.slice(0, 7)}
            minTickGap={60}
            axisLine={false}
            tickLine={false}
          />
          {isGrowth ? (
            <>
              <YAxis
                yAxisId="pct"
                tick={{ ...AXIS_TICK_STYLE, fontFamily: "JetBrains Mono Variable" }}
                tickFormatter={fmtPctAxis}
                width={55}
                domain={growthDomain}
                ticks={growthTicks}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<CustomTooltip currency={currency} benchmarkMeta={benchmarkMeta} mode={mode} />} />
              <Legend
                verticalAlign="top"
                align="right"
                wrapperStyle={LEGEND_WRAPPER_STYLE}
                formatter={(v) => {
                  if (v === "pnl_pct") return <span style={LEGEND_TEXT_STYLE}>Portfolio Growth</span>;
                  const bm = benchmarkMeta.find((b) => `bench_${b.key}` === v);
                  if (bm) return <span style={{ ...LEGEND_TEXT_STYLE, color: bm.color }}>{bm.label}</span>;
                  return <span style={LEGEND_TEXT_STYLE}>{v}</span>;
                }}
              />
              <Area
                yAxisId="pct"
                type="monotone"
                dataKey="pnl_pct"
                baseValue={0}
                stroke="none"
                fill="url(#colorGrowth)"
                strokeWidth={2.5}
                dot={false}
              />
              <Customized component={(chartProps) => <GrowthLineLayer {...chartProps} series={sampled} />} />
              {benchmarkMeta.map((b, i) => (
                <Line
                  key={b.key}
                  yAxisId="pct"
                  type="monotone"
                  dataKey={`bench_${b.key}`}
                  stroke={b.color}
                  strokeDasharray={benchmarkDash(i)}
                  strokeWidth={1.5}
                  dot={false}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  connectNulls
                />
              ))}
            </>
          ) : (
            <>
              <YAxis
                yAxisId="value"
                tick={{ ...AXIS_TICK_STYLE, fontFamily: "JetBrains Mono Variable" }}
                tickFormatter={fmtAxis}
                width={currency === "CZK" ? 72 : 52}
                domain={['dataMin', 'dataMax']}
                axisLine={false}
                tickLine={false}
              />
              {hasBenchmarks && (
                <YAxis
                  yAxisId="pct"
                  orientation="right"
                  tick={{ ...AXIS_TICK_STYLE, fontFamily: "JetBrains Mono Variable" }}
                  tickFormatter={fmtPctAxis}
                  width={50}
                  axisLine={false}
                  tickLine={false}
                />
              )}
              <Tooltip content={<CustomTooltip currency={currency} benchmarkMeta={benchmarkMeta} mode={mode} />} />
              <Legend
                verticalAlign="top"
                align="right"
                wrapperStyle={LEGEND_WRAPPER_STYLE}
                formatter={(v) => {
                  if (v === "value") return <span style={LEGEND_TEXT_STYLE}>Portfolio Value</span>;
                  if (v === "invested") return <span style={LEGEND_TEXT_STYLE}>Deposited</span>;
                  const bm = benchmarkMeta.find((b) => `bench_${b.key}` === v);
                  if (bm) return <span style={{ ...LEGEND_TEXT_STYLE, color: bm.color }}>{bm.label}</span>;
                  return <span style={LEGEND_TEXT_STYLE}>{v}</span>;
                }}
              />
              <Area yAxisId="value" type="monotone" dataKey="invested" stroke={NEUTRAL_COLOR} fill="url(#colorInvested)" strokeWidth={1.5} dot={false} />
              <Area yAxisId="value" type="monotone" dataKey="value" stroke="var(--brand)" fill="url(#colorValue)" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" dot={false} />
              {benchmarkMeta.map((b, i) => (
                <Line
                  key={b.key}
                  yAxisId="pct"
                  type="monotone"
                  dataKey={`bench_${b.key}`}
                  stroke={b.color}
                  strokeDasharray={benchmarkDash(i)}
                  strokeWidth={1.5}
                  dot={false}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  connectNulls
                />
              ))}
            </>
          )}
        </ComposedChart>
      </ResponsiveContainer>
      </div>
    </div>
  );
}
