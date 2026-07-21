import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { CATEGORICAL, TOOLTIP_STYLE } from "../lib/chartTheme";

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

  if (!data.length) return <div className="text-muted text-sm">No holdings yet.</div>;

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
            <Cell key={i} fill={CATEGORICAL[i % CATEGORICAL.length]} stroke="transparent" />
          ))}
        </Pie>
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(v, _name, props) => [
            `${fmtVal(v)}  (${props.payload.weight}%)`,
            props.payload.name,
          ]}
        />
        <Legend
          formatter={(v) => <span className="text-xs text-muted">{v}</span>}
          iconType="circle"
          iconSize={8}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
