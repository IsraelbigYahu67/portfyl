import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from "recharts";
import { CATEGORICAL, NEUTRAL_COLOR } from "../lib/chartTheme";

// Cash has no sector/country/asset-type of its own — give it a fixed neutral
// slate color instead of whatever the palette-by-index lookup would assign,
// so it visually reads as "not an equity" in every dimension it appears in.
// "Other" (the grouped small-positions slice) is a catch-all the same way.
const colorFor = (item, i) =>
  item.name === "Cash" || item.name === "Other" ? NEUTRAL_COLOR : CATEGORICAL[i % CATEGORICAL.length];

// legendColumns=2 flows the legend into two newspaper-style columns (read
// down, then across) — used by the wide Positions card to halve its height.
export default function BreakdownChart({ title, data, currencyLabel, legendColumns = 1 }) {
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
      <h2 className="text-sm font-semibold text-muted mb-4 uppercase tracking-wider">
        {title}
      </h2>
      <div className="flex flex-col items-stretch gap-6 sm:flex-row sm:items-start">
        <div className="w-48 h-48 shrink-0 self-center sm:self-auto">
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
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const item = payload[0].payload;
                  return (
                    <div className="bg-surface-card-elevated border border-hairline rounded-lg px-3 py-2 text-xs shadow-lg">
                      <div className="font-semibold text-ink">
                        {item.name} · {item.weight}%
                      </div>
                      {/* Grouped slices (e.g. "Other" positions) carry their
                          members in `items` — list them on hover. */}
                      {item.items?.length > 0 && (
                        <div className="flex flex-wrap gap-x-2 mt-1 max-w-[240px] text-muted">
                          {item.items.map((sub) => (
                            <span key={sub.name} className="whitespace-nowrap">
                              {sub.name} {sub.weight}%
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div
          className={`flex-1 min-w-0 space-y-1.5 ${
            legendColumns === 2 ? "sm:columns-2 sm:gap-x-10" : ""
          }`}
        >
          {data.map((item, i) => (
            <div key={item.name} className="flex items-center gap-2 text-sm break-inside-avoid">
              <div
                className="w-2.5 h-2.5 rounded-full shrink-0"
                style={{ backgroundColor: colorFor(item, i) }}
              />
              <span className="text-ink truncate flex-1">{item.name}</span>
              <span className="tabular-nums text-muted w-14 text-right shrink-0">
                {item.weight}%
              </span>
              <span className="tabular-nums text-muted w-24 text-right shrink-0">
                {fmt(item.value)}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
