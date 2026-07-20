import { AreaChart, Area, ResponsiveContainer, XAxis, YAxis, CartesianGrid, Tooltip } from "recharts";
import { formatMoney, formatShortDate } from "../lib/format";
import { AXIS_TICK, GRID_STROKE } from "../lib/chartTheme";

// Cash holds flat between events and jumps on each deposit/withdrawal/trade, so
// a step curve is the honest shape — not a smoothed interpolation.

const compact = (n) => {
  const a = Math.abs(n);
  if (a >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (a >= 1_000) return Math.round(n / 1_000) + "k";
  return String(Math.round(n));
};

function CashTooltip({ active, payload, currency }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="bg-surface-card-elevated border border-hairline rounded-xl shadow-pop px-3 py-2 text-xs">
      <div className="text-muted">{p.date}</div>
      <div className="font-sans tabular-nums font-semibold text-ink">{formatMoney(p.balance, currency)}</div>
    </div>
  );
}

export default function CashBalanceChart({ data = [], currency = "USD" }) {
  if (!Array.isArray(data) || data.length < 2) return null;
  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="cashFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--brand)" stopOpacity={0.2} />
              <stop offset="100%" stopColor="var(--brand)" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid vertical={false} stroke={GRID_STROKE} />
          <XAxis
            dataKey="date"
            tickFormatter={(iso) => formatShortDate(iso)}
            axisLine={false}
            tickLine={false}
            minTickGap={32}
            tick={{ ...AXIS_TICK, fontFamily: "JetBrains Mono Variable" }}
          />
          <YAxis
            tickFormatter={compact}
            axisLine={false}
            tickLine={false}
            width={44}
            tick={{ ...AXIS_TICK, fontFamily: "JetBrains Mono Variable" }}
          />
          <Tooltip content={<CashTooltip currency={currency} />} />
          <Area
            type="stepAfter"
            dataKey="balance"
            stroke="var(--brand)"
            strokeWidth={2.5}
            fill="url(#cashFill)"
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
