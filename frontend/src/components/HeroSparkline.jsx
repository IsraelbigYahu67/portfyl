import { AreaChart, Area, ResponsiveContainer, YAxis } from "recharts";
import { LOSS_COLOR } from "../lib/chartTheme";

export default function HeroSparkline({ data = [], positive = true }) {
  if (!Array.isArray(data) || data.length < 2) return null;
  const color = positive ? "var(--brand)" : LOSS_COLOR;
  return (
    <div className="absolute inset-x-0 bottom-0 h-28 pointer-events-none opacity-[0.18] select-none" aria-hidden="true">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="heroFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.9} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Area type="monotone" dataKey="value" stroke={color} strokeWidth={2} fill="url(#heroFill)" isAnimationActive={false} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
