import { useState } from "react";
import { Coins } from "lucide-react";
import { SectionHeader } from "../ui";
import { formatCompact, formatMoney } from "../../lib/format";

const TONES = {
  brand: { bar: "linear-gradient(180deg, var(--chart-1), var(--brand))" },
  accent: { bar: "linear-gradient(180deg, var(--chart-2), var(--chart-6))" },
};

// Some themes use a translucent --surface-card; flatten it onto the opaque page
// background so the tooltip never lets the bars underneath show through.
const OPAQUE_CARD = "linear-gradient(var(--surface-card), var(--surface-card)), var(--bg)";

const MAX_TOOLTIP_ROWS = 8;
const STATUS_LABEL = { paid: "Received", confirmed: "Confirmed", forecasted: "Forecasted" };

// Pin the tooltip to the hovered column, but keep it inside the card: columns
// near either edge anchor the tooltip to that edge instead of centring it.
function tooltipPlacement(index, count) {
  const center = ((index + 0.5) / count) * 100;
  if (index < count / 4) return { left: `${center}%`, transform: "translateX(-15%)" };
  if (index >= (count * 3) / 4) return { left: `${center}%`, transform: "translateX(-85%)" };
  return { left: `${center}%`, transform: "translateX(-50%)" };
}

function MonthTooltip({ month, index, count, currency }) {
  const title = month.year ? `${month.month} ${month.year}` : month.month;
  const shown = (month.entries || []).slice(0, MAX_TOOLTIP_ROWS);
  const hidden = (month.entries || []).length - shown.length;
  return (
    <div
      role="tooltip"
      data-testid="dividend-tooltip"
      className="absolute bottom-full mb-2 z-20 w-60 rounded-xl border border-line bg-surface-card px-3 py-2.5 shadow-lg pointer-events-none"
      style={{ ...tooltipPlacement(index, count), background: OPAQUE_CARD }}
    >
      <div className="flex items-baseline justify-between gap-3 mb-1.5">
        <span className="text-xs font-semibold text-ink">{title}</span>
        <span className="text-xs font-semibold tabular-nums text-ink">{formatMoney(month.amount, currency)}</span>
      </div>
      {shown.length === 0 ? (
        <p className="text-xs text-muted">No payments</p>
      ) : (
        <ul className="space-y-1">
          {shown.map((e) => (
            <li key={`${e.ticker}-${e.status}`} className="flex items-center gap-2 text-xs">
              <span className="font-mono font-semibold text-ink">{e.ticker}</span>
              {e.status && (
                <span className={`rounded px-1 text-xs uppercase tracking-wide ${e.status === "forecasted" ? "bg-surface-hover text-muted" : "bg-surface-hover text-gain"}`}>
                  {STATUS_LABEL[e.status] ?? e.status}
                </span>
              )}
              <span className="ml-auto tabular-nums text-ink">{formatMoney(e.amount, currency)}</span>
            </li>
          ))}
        </ul>
      )}
      {hidden > 0 && <p className="financial-meta mt-1.5">+{hidden} more</p>}
    </div>
  );
}

// Monthly dividend bars (dashboard variant A). `half` comes from
// splitDividendForecast: { months: [{ month, amount, confirmed?, forecasted?,
// entries? }], total, monthlyAverage } already in the display currency. Months
// that carry a confirmed / forecasted split are stacked (forecasted lighter),
// and hovering or focusing a column lists what each company pays.
// `leadStat` / `trailStat` ({ label, amount }) add an extra tile before the
// total or after the average; a null amount hides the tile.
export default function DividendBarsCard({ title, half, totalLabel, avgLabel = "Monthly average", currency, tone = "brand", emptyHint = "No dividends in this period.", leadStat = null, trailStat = null }) {
  const [active, setActive] = useState(null);
  const max = Math.max(0, ...half.months.map((m) => m.amount));
  const label = `${title} by month: ${half.months.map((m) => `${m.month} ${formatCompact(m.amount, currency)}`).join(", ")}`;
  const stacked = half.months.some((m) => m.confirmed !== undefined || m.forecasted !== undefined);
  const barBackground = TONES[tone].bar;
  const stats = [
    leadStat,
    { label: totalLabel, amount: half.total },
    { label: avgLabel, amount: half.monthlyAverage },
    trailStat,
  ].filter((s) => s && Number.isFinite(s.amount));

  return (
    <div className="flex flex-col h-full">
      <SectionHeader icon={Coins}>{title}</SectionHeader>
      {!(half.total > 0) ? (
        <p className="text-sm text-muted py-6 text-center">{emptyHint}</p>
      ) : (
        <>
          <div className={`grid ${stats.length > 2 ? "grid-cols-2 sm:grid-cols-3" : "grid-cols-2"} gap-3 mb-5`}>
            {stats.map((s) => (
              <div key={s.label} className="min-w-0 rounded-xl bg-surface-hover px-3.5 py-2.5">
                <span className="block data-label truncate">{s.label}</span>
                <span className="block truncate font-display text-lg font-bold tabular-nums text-ink">{formatMoney(s.amount, currency)}</span>
              </div>
            ))}
          </div>
          {stacked && (
            <div className="flex gap-4 mb-2 text-xs text-muted" data-testid="dividend-legend">
              <span className="inline-flex items-center gap-1.5">
                <i className="block h-2.5 w-2.5 rounded-sm" style={{ background: barBackground }} /> Confirmed
              </span>
              <span className="inline-flex items-center gap-1.5">
                <i className="block h-2.5 w-2.5 rounded-sm" style={{ background: barBackground, opacity: 0.4 }} /> Forecasted
              </span>
            </div>
          )}
          <div role="img" aria-label={label} className="mt-auto relative" onMouseLeave={() => setActive(null)}>
            {active !== null && half.months[active] && (
              <MonthTooltip month={half.months[active]} index={active} count={half.months.length} currency={currency} />
            )}
            <div className="flex items-end gap-1.5 h-40">
              {half.months.map((m, i) => {
                const height = max > 0 ? Math.round((m.amount / max) * 10000) / 100 : 0;
                const confirmedShare = stacked && m.amount > 0 ? ((m.confirmed || 0) / m.amount) * 100 : 100;
                return (
                  <div
                    key={`${m.year ?? ""}${m.month}`}
                    data-testid={`column-${m.month}`}
                    tabIndex={0}
                    className="bar-pop flex-1 min-w-0 h-full flex flex-col items-center justify-end gap-1 cursor-default rounded-md outline-none focus-visible:ring-2 focus-visible:ring-brand"
                    onMouseEnter={() => setActive(i)}
                    onFocus={() => setActive(i)}
                    onBlur={() => setActive(null)}
                  >
                    {m.amount > 0 && (
                      // 12 columns on a phone are ~29px wide, so neighbouring value
                      // labels collide: show every second one there. The hover/focus
                      // tooltip still lists every month.
                      <span className={`text-xs font-semibold text-muted tabular-nums whitespace-nowrap ${half.months.length > 6 && i % 2 === 1 ? "hidden sm:inline" : ""}`}>
                        {formatCompact(m.amount, currency)}
                      </span>
                    )}
                    <div
                      data-testid={`bar-${m.month}`}
                      className="bar-pop-bar flex flex-col w-3/4 max-w-[26px] overflow-hidden rounded-t-xl rounded-b-lg"
                      style={{ height: `${height}%`, minHeight: m.amount > 0 ? 4 : 0 }}
                    >
                      {stacked && confirmedShare < 100 && (
                        <i data-testid={`forecast-${m.month}`} className="block" style={{ height: `${100 - confirmedShare}%`, background: barBackground, opacity: 0.4 }} />
                      )}
                      {confirmedShare > 0 && (
                        confirmedShare < 100 ? (
                          // Overlap the forecast segment by one corner radius so the
                          // confirmed part's top corners are rounded over the lighter one.
                          <i className="block relative shrink-0 rounded-t-lg" style={{ height: `calc(${confirmedShare}% + 8px)`, marginTop: -8, background: barBackground }} />
                        ) : (
                          <i className="block" style={{ height: "100%", background: barBackground }} />
                        )
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="flex gap-1.5 mt-2" aria-hidden="true">
              {half.months.map((m) => (
                <span key={`${m.year ?? ""}${m.month}`} className="flex-1 min-w-0 text-center text-xs text-muted">{m.month}</span>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
