import { Coins } from "lucide-react";
import { SectionHeader } from "../ui";
import { formatCompact, formatMoney } from "../../lib/format";

const TONES = {
  brand: { bar: "linear-gradient(180deg, var(--chart-1), var(--brand))" },
  accent: { bar: "linear-gradient(180deg, var(--chart-2), var(--chart-6))" },
};

// Monthly dividend bars (dashboard variant A). `half` comes from
// splitDividendForecast: { months: [{ month, amount }], total, monthlyAverage }
// already in the display currency.
export default function DividendBarsCard({ title, half, totalLabel, avgLabel = "Monthly average", currency, tone = "brand", emptyHint = "No dividends in this period." }) {
  const max = Math.max(0, ...half.months.map((m) => m.amount));
  const label = `${title} by month: ${half.months.map((m) => `${m.month} ${formatCompact(m.amount, currency)}`).join(", ")}`;

  return (
    <div className="flex flex-col h-full">
      <SectionHeader icon={Coins}>{title}</SectionHeader>
      {!(half.total > 0) ? (
        <p className="text-sm text-muted py-6 text-center">{emptyHint}</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 mb-5">
            <div className="rounded-xl bg-surface-hover px-3.5 py-2.5">
              <span className="block data-label">{totalLabel}</span>
              <span className="font-display text-lg font-bold tabular-nums text-ink">{formatMoney(half.total, currency)}</span>
            </div>
            <div className="rounded-xl bg-surface-hover px-3.5 py-2.5">
              <span className="block data-label">{avgLabel}</span>
              <span className="font-display text-lg font-bold tabular-nums text-ink">{formatMoney(half.monthlyAverage, currency)}</span>
            </div>
          </div>
          <div role="img" aria-label={label} className="mt-auto">
            <div className="flex items-end gap-1.5 h-40">
              {half.months.map((m) => {
                const height = max > 0 ? Math.round((m.amount / max) * 10000) / 100 : 0;
                return (
                  <div key={m.month} className="flex-1 min-w-0 h-full flex flex-col items-center justify-end gap-1">
                    {m.amount > 0 && <span className="text-xs font-semibold text-muted tabular-nums whitespace-nowrap">{formatCompact(m.amount, currency)}</span>}
                    <i
                      data-testid={`bar-${m.month}`}
                      className="block w-3/4 max-w-[26px] rounded-t-lg rounded-b-md"
                      style={{ height: `${height}%`, minHeight: m.amount > 0 ? 4 : 0, background: TONES[tone].bar }}
                    />
                  </div>
                );
              })}
            </div>
            <div className="flex gap-1.5 mt-2" aria-hidden="true">
              {half.months.map((m) => (
                <span key={m.month} className="flex-1 min-w-0 text-center text-xs text-muted">{m.month}</span>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
