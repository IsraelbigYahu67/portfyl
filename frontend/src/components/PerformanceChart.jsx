import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";

function CustomTooltip({ active, payload, label, currency, benchmarkMeta, mode }) {
  if (!active || !payload?.length) return null;

  const row = payload[0]?.payload;
  if (!row) return null;

  const fmtMoney = (v) =>
    currency === "CZK"
      ? `${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} Kč`
      : `$${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const pnl = row.pnl;
  const pnlPct = row.pnl_pct;
  const totalPnl = row.total_pnl;
  const totalPnlPct = row.total_pnl_pct;

  const line = (name, val, color) => (
    <div className="flex justify-between gap-6">
      <span className="text-slate-600">{name}</span>
      <span className={`font-medium ${color}`}>{val}</span>
    </div>
  );
  const moneyColor = (v) => (v >= 0 ? "text-emerald-600" : "text-red-600");
  const fmtSignedMoney = (v) => `${v >= 0 ? "+" : ""}${fmtMoney(v)}`;
  const fmtSignedPct = (v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;

  return (
    <div className="bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs shadow-lg">
      <p className="text-slate-500 mb-1.5">{label}</p>
      <div className="space-y-1">
        {mode === "value" && (
          <>
            {line("Value", fmtMoney(row.value), "text-slate-800")}
            {line("Invested", fmtMoney(row.invested), "text-blue-400")}
          </>
        )}
        {pnl != null && line("Period P&L", fmtSignedMoney(pnl), moneyColor(pnl))}
        {pnlPct != null && line("Period %", fmtSignedPct(pnlPct), moneyColor(pnlPct))}
        {totalPnl != null && line("Total P&L", fmtSignedMoney(totalPnl), moneyColor(totalPnl))}
        {totalPnlPct != null && line("Total %", fmtSignedPct(totalPnlPct), moneyColor(totalPnlPct))}
        {benchmarkMeta?.map((b) => {
          const val = row[`bench_${b.key}`];
          if (val == null) return null;
          return (
            <div key={b.key} className="flex justify-between gap-6">
              <span style={{ color: b.color }}>{b.label}</span>
              <span style={{ color: b.color }} className="font-medium">
                {val >= 0 ? "+" : ""}{val.toFixed(2)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function PerformanceChart({ data, currency = "USD", mode = "value", benchmarks = {}, benchmarkMeta = [] }) {
  if (!data?.length) return <div className="text-slate-500 text-sm">No performance data yet.</div>;

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

  const fmtAxis = (v) => {
    if (currency === "CZK") {
      return v >= 1_000_000 ? `${(v / 1_000_000).toFixed(1)}M Kč` : `${(v / 1_000).toFixed(0)}k Kč`;
    }
    return v >= 1_000_000 ? `$${(v / 1_000_000).toFixed(1)}M` : `$${(v / 1_000).toFixed(0)}k`;
  };

  const fmtPctAxis = (v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;

  return (
    <ResponsiveContainer width="100%" height={320}>
      <ComposedChart data={sampled} margin={{ top: 4, right: hasBenchmarks && !isGrowth ? 50 : 4, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="gValue" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#22c55e" stopOpacity={0.25} />
            <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="gInvested" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.15} />
            <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="gGrowth" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
            <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
        <XAxis
          dataKey="date"
          tick={{ fill: "#64748B", fontSize: 11 }}
          tickFormatter={(v) => shortRange ? v.slice(5) : v.slice(0, 7)}
          minTickGap={60}
        />
        {isGrowth ? (
          <>
            <YAxis
              yAxisId="pct"
              tick={{ fill: "#64748B", fontSize: 11 }}
              tickFormatter={fmtPctAxis}
              width={55}
              domain={['dataMin', 'dataMax']}
            />
            <Tooltip content={<CustomTooltip currency={currency} benchmarkMeta={benchmarkMeta} mode={mode} />} />
            <Legend
              formatter={(v) => {
                if (v === "pnl_pct") return <span className="text-xs text-slate-600">Portfolio Growth</span>;
                const bm = benchmarkMeta.find((b) => `bench_${b.key}` === v);
                if (bm) return <span className="text-xs" style={{ color: bm.color }}>{bm.label}</span>;
                return <span className="text-xs text-slate-600">{v}</span>;
              }}
            />
            <Area
              yAxisId="pct"
              type="monotone"
              dataKey="pnl_pct"
              stroke="#22c55e"
              fill="url(#gGrowth)"
              strokeWidth={2}
              dot={false}
            />
            {benchmarkMeta.map((b) => (
              <Line
                key={b.key}
                yAxisId="pct"
                type="monotone"
                dataKey={`bench_${b.key}`}
                stroke={b.color}
                strokeWidth={1.5}
                dot={false}
                connectNulls
              />
            ))}
          </>
        ) : (
          <>
            <YAxis
              yAxisId="value"
              tick={{ fill: "#64748B", fontSize: 11 }}
              tickFormatter={fmtAxis}
              width={currency === "CZK" ? 72 : 52}
              domain={['dataMin', 'dataMax']}
            />
            {hasBenchmarks && (
              <YAxis
                yAxisId="pct"
                orientation="right"
                tick={{ fill: "#64748B", fontSize: 11 }}
                tickFormatter={fmtPctAxis}
                width={50}
              />
            )}
            <Tooltip content={<CustomTooltip currency={currency} benchmarkMeta={benchmarkMeta} mode={mode} />} />
            <Legend
              formatter={(v) => {
                if (v === "value") return <span className="text-xs text-slate-600">Portfolio Value</span>;
                if (v === "invested") return <span className="text-xs text-slate-600">Invested</span>;
                const bm = benchmarkMeta.find((b) => `bench_${b.key}` === v);
                if (bm) return <span className="text-xs" style={{ color: bm.color }}>{bm.label}</span>;
                return <span className="text-xs text-slate-600">{v}</span>;
              }}
            />
            <Area yAxisId="value" type="monotone" dataKey="invested" stroke="#3b82f6" fill="url(#gInvested)" strokeWidth={1.5} dot={false} />
            <Area yAxisId="value" type="monotone" dataKey="value" stroke="#22c55e" fill="url(#gValue)" strokeWidth={2} dot={false} />
            {benchmarkMeta.map((b) => (
              <Line
                key={b.key}
                yAxisId="pct"
                type="monotone"
                dataKey={`bench_${b.key}`}
                stroke={b.color}
                strokeWidth={1.5}
                dot={false}
                connectNulls
              />
            ))}
          </>
        )}
      </ComposedChart>
    </ResponsiveContainer>
  );
}
