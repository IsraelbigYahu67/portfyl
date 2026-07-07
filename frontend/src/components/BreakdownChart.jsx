import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";

const COLORS = [
  "#6366f1", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6",
  "#ec4899", "#06b6d4", "#f97316", "#14b8a6", "#a855f7",
  "#eab308", "#3b82f6", "#e11d48", "#84cc16",
];

// Cash has no sector/country/asset-type of its own — give it a fixed neutral
// slate color instead of whatever the palette-by-index lookup would assign,
// so it visually reads as "not an equity" in every dimension it appears in.
const CASH_COLOR = "#94a3b8";
const colorFor = (item, i) => (item.name === "Cash" ? CASH_COLOR : COLORS[i % COLORS.length]);

export default function BreakdownChart({ title, data, currencyLabel }) {
  const fmt = (n) => {
    if (n == null) return "—";
    const sign = n < 0 ? "-" : "";
    const str = Math.abs(n).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return currencyLabel === "CZK" ? `${sign}${str} Kč` : `${sign}$${str}`;
  };

  if (!data || data.length === 0) return null;

  return (
    <div className="card">
      <h2 className="text-sm font-semibold text-slate-500 mb-4 uppercase tracking-wider">
        {title}
      </h2>
      <div className="flex items-start gap-6">
        <div className="w-48 h-48 shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                dataKey="weight"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={40}
                outerRadius={75}
                paddingAngle={2}
              >
                {data.map((item, i) => (
                  <Cell key={i} fill={colorFor(item, i)} />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  background: "#ffffff",
                  border: "1px solid #e2e8f0",
                  borderRadius: 8,
                  fontSize: 12,
                }}
                formatter={(val, name) => [`${val}%`, name]}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="flex-1 space-y-1.5 min-w-0">
          {data.map((item, i) => (
            <div key={item.name} className="flex items-center gap-2 text-sm">
              <div
                className="w-2.5 h-2.5 rounded-full shrink-0"
                style={{ backgroundColor: colorFor(item, i) }}
              />
              <span className="text-slate-700 truncate flex-1">{item.name}</span>
              <span className="tabular-nums text-slate-500 w-14 text-right">
                {item.weight}%
              </span>
              <span className="tabular-nums text-slate-500 w-24 text-right">
                {fmt(item.value)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
