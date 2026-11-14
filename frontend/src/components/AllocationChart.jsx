import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { CATEGORICAL, TOOLTIP_STYLE, LEGEND_TEXT_STYLE } from "../lib/chartTheme";
import { withSliceCorners } from "../lib/pieCorners";
import { currencyParts, displayLocale } from "../lib/format";
import { convertFromUsd } from "../lib/displayCurrency";
import { PieTouchScrub } from "../hooks/usePieTouchScrub";

export default function AllocationChart({ holdings, currency = "USD", rate = null }) {
  const convert = (n) => convertFromUsd(n, currency, rate);

  const fmtVal = (v) => {
    const converted = convert(v);
    const str = converted.toLocaleString(displayLocale(currency), { maximumFractionDigits: 0 });
    const { prefix = "", suffix = "" } = currencyParts(currency);
    return `${prefix}${str}${suffix}`;
  };

  const data = holdings
    .filter((h) => h.market_value > 0)
    .map((h) => ({ name: h.ticker, value: h.market_value, weight: h.weight }));

  if (!data.length) return <div className="text-muted text-sm">No holdings yet.</div>;

  const slices = withSliceCorners(data, { valueKey: "value", inner: 70, outer: 110, corner: 7 });

  return (
    <PieTouchScrub>
      {(tooltipProps) => (
    <ResponsiveContainer width="100%" height={280}>
      <PieChart>
        <Pie
          data={slices}
          cx="50%"
          cy="50%"
          innerRadius={70}
          outerRadius={110}
          paddingAngle={3}
          cornerRadius={7}
          dataKey="value"
        >
          {data.map((_, i) => (
            <Cell key={i} fill={CATEGORICAL[i % CATEGORICAL.length]} stroke="transparent" />
          ))}
        </Pie>
        <Tooltip
          {...tooltipProps}
          contentStyle={TOOLTIP_STYLE}
          formatter={(v, _name, props) => [
            `${fmtVal(v)}  (${props.payload.weight}%)`,
            props.payload.name,
          ]}
        />
        <Legend
          formatter={(v) => <span style={LEGEND_TEXT_STYLE}>{v}</span>}
          iconType="circle"
          iconSize={8}
        />
      </PieChart>
    </ResponsiveContainer>
      )}
    </PieTouchScrub>
  );
}
