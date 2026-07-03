import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";

const COLORS = [
  "#22c55e", "#3b82f6", "#f59e0b", "#ec4899", "#8b5cf6",
  "#06b6d4", "#ef4444", "#84cc16", "#f97316", "#a855f7",
];

export default function AllocationChart({ holdings, currency = "USD", rate = null }) {
  const convert = (n) => (currency === "CZK" && rate ? n * rate : n);

  const fmtVal = (v) => {
    const converted = convert(v);
    const str = converted.toLocaleString("en-US", { maximumFractionDigits: 0 });
    return currency === "CZK" ? `${str} Kč` : `$${str}`;
  };

  const data = holdings
    .filter((h) => h.market_value > 0)
    .map((h) => ({ name: h.ticker, value: h.market_value, weight: h.weight }));

  if (!data.length) return <div className="text-slate-500 text-sm">No holdings yet.</div>;

  return (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie
          data={data}
          cx="50%"
          cy="50%"
          innerRadius={70}
          outerRadius={110}
          paddingAngle={2}
          dataKey="value"
        >
          {data.map((_, i) => (
            <Cell key={i} fill={COLORS[i % COLORS.length]} stroke="transparent" />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{ background: "#FFFFFF", border: "1px solid #E2E8F0", borderRadius: 8 }}
          formatter={(v, _name, props) => [
            `${fmtVal(v)}  (${props.payload.weight}%)`,
            props.payload.name,
          ]}
        />
        <Legend
          formatter={(v) => <span className="text-xs text-slate-600">{v}</span>}
          iconType="circle"
          iconSize={8}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
