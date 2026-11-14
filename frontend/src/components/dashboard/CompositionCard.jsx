import { useState } from "react";
import { Link } from "react-router-dom";
import { PieChart as PieIcon, ArrowRight } from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer } from "recharts";
import { PieTouchScrub } from "../../hooks/usePieTouchScrub";
import SegmentedControl from "../ui/SegmentedControl";
import { SectionHeader } from "../ui";
import { CATEGORICAL } from "../../lib/chartTheme";
import { withSliceCorners } from "../../lib/pieCorners";
import { formatCompact, formatMoney } from "../../lib/format";
import { buildCompositionRows } from "../../lib/dashboardSummaries";
import { useIsPhone } from "../../hooks/useMediaQuery";
import { msg, useT } from "../../i18n/I18nProvider";

const DIMENSIONS = [
  { value: "sectors", label: msg("Sectors") },
  { value: "countries", label: msg("Countries") },
  { value: "asset_types", label: msg("Categories") },
];
// The Categories tab deliberately has no profit column.
const NO_PROFIT = new Set(["asset_types"]);
const MAX_ROWS = 8;

// Realized + unrealized profit with its sign. A profit that rounds to zero
// reads as neutral, never as a red "-0".
function ProfitCell({ profit, currency }) {
  if (profit == null) return <span className="text-muted">—</span>;
  const rounded = Math.round(profit);
  const tone = rounded > 0 ? "text-gain" : rounded < 0 ? "text-loss" : "text-muted";
  return <span className={tone}>{rounded > 0 ? "+" : ""}{formatMoney(rounded, currency)}</span>;
}

// An amount whose digits are tabular (so rows line up) but whose punctuation
// keeps its natural width: tabular-nums widens the decimal comma into a visible
// gap after the last whole digit. Every row has the same two decimals, so the
// separators still share one vertical line when the cell is right-aligned.
function Money({ value, currency }) {
  return formatMoney(value, currency).split(/(\d+)/).map((part, i) =>
    i % 2 ? <span key={i} className="tabular-nums">{part}</span> : part
  );
}

// Portfolio composition (dashboard variant A): a donut plus a table of the
// same rows, grouped by asset type, sector or country from
// /analytics/sector-breakdown. Columns: weight, value, and total profit
// (realized + unrealized).
export default function CompositionCard({ breakdown, currency }) {
  const t = useT();
  const [dimension, setDimension] = useState(DIMENSIONS[0].value);
  const [activeIndex, setActiveIndex] = useState(null);
  const isPhone = useIsPhone();
  const showProfit = !NO_PROFIT.has(dimension);
  const rows = buildCompositionRows(breakdown?.[dimension] || []);
  const shown = rows.slice(0, MAX_ROWS);
  const hiddenCount = rows.length - shown.length;
  // Sum the rows instead of using breakdown.total_value: the API folds cash
  // into the rows but leaves it out of total_value.
  const total = rows.reduce((sum, row) => sum + row.value, 0);
  // The donut radii are percentages of its max radius (~140px at full size), so
  // the 9px corner is ~6.5 in the same percent units.
  const activeRow = activeIndex == null ? null : shown[activeIndex] ?? null;
  const pieSlices = withSliceCorners(shown, { valueKey: "value", inner: 62, outer: 92, corner: 6.5 });

  return (
    <div className="flex flex-col h-full">
      <SectionHeader
        icon={PieIcon}
        action={
          <>
            <SegmentedControl
              aria-label={t("Group composition by")}
              value={dimension}
              onChange={(next) => { setDimension(next); setActiveIndex(null); }}
              options={DIMENSIONS.map((option) => ({ ...option, label: t(option.label) }))}
            />
            <Link to="/allocation" className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:text-brand-dim">
              {t("Targets")} <ArrowRight size={12} aria-hidden="true" />
            </Link>
          </>
        }
      >
        {t("Portfolio composition")}
      </SectionHeader>

      {rows.length === 0 ? (
        <p className="text-sm text-muted py-6 text-center">{t("No holdings to group yet.")}</p>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,280px)_minmax(0,1fr)] items-center">
          <PieTouchScrub className="pie-pop relative mx-auto w-full max-w-[280px] aspect-square">
            {() => (
              <>
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={pieSlices} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="92%" paddingAngle={3} cornerRadius={9} stroke="none" isAnimationActive={false} onMouseEnter={(_, i) => setActiveIndex(i)} onMouseLeave={() => setActiveIndex(null)}>
                      {shown.map((row, i) => <Cell key={row.name} fill={CATEGORICAL[i % CATEGORICAL.length]} />)}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="pointer-events-none absolute inset-0 grid place-content-center text-center">
                  <span className="data-label">{t("Total value")}</span>
                  <span className="font-display text-xl font-bold text-ink tabular-nums">{formatCompact(total, currency)}</span>
                </div>
                {/* The slice's name and weight sit in the hole just below the total,
                    so the bubble never covers the total (and the finger on the ring
                    never covers the bubble). z-10 keeps it above the donut. */}
                {activeRow && (
                  <div
                    role="status"
                    className="pointer-events-none absolute left-1/2 z-10 flex max-w-[92%] -translate-x-1/2 items-center gap-1.5 whitespace-nowrap rounded-lg border border-hairline bg-surface-card-elevated px-3 py-1.5 text-xs font-semibold text-ink shadow-lg"
                    style={{ top: "calc(50% + 34px)" }}
                  >
                    <span aria-hidden="true" className="h-2 w-2 shrink-0 rounded-full" style={{ background: CATEGORICAL[activeIndex % CATEGORICAL.length] }} />
                    <span className="truncate">{activeRow.name} · {activeRow.weight.toFixed(1)}%</span>
                  </div>
                )}
              </>
            )}
          </PieTouchScrub>

          <div className="min-w-0 overflow-x-auto">
            {isPhone ? (
              // A phone shows each row as a card line (name + profit left, value + weight right):
              // the 5-column table cut off its Value and Profit columns.
              <ul className="divide-y divide-hairline" aria-label={t("Composition")}>
                {shown.map((row, i) => (
                  <li key={row.name} className="flex items-center gap-3 py-2.5">
                    <span aria-hidden="true" className="h-9 w-1.5 shrink-0 rounded-full" style={{ background: CATEGORICAL[i % CATEGORICAL.length] }} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-semibold text-ink">{row.name}</div>
                      {showProfit && (
                        <div className="text-xs tabular-nums"><ProfitCell profit={row.profit} currency={currency} /></div>
                      )}
                    </div>
                    <div className="shrink-0 text-right tabular-nums">
                      <div className="font-semibold text-ink"><Money value={row.value} currency={currency} /></div>
                      <div className="text-xs text-muted">{row.weight.toFixed(1)}%</div>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-muted">
                  <th scope="col" className="w-full pb-2 font-medium">{t("Name")}</th>
                  <th scope="col" className="pb-2 pr-8 font-medium text-right whitespace-nowrap">{t("Weight")}</th>
                  <th scope="col" className={`pb-2 font-medium text-right whitespace-nowrap ${showProfit ? "pr-8" : ""}`}>{t("Value")}</th>
                  {showProfit && <th scope="col" className="pb-2 font-medium text-right whitespace-nowrap" title={t("Realized + unrealized profit")}>{t("Profit")}</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-hairline">
                {shown.map((row, i) => (
                  <tr key={row.name}>
                    <td className="py-2.5 pr-3">
                      <span className="flex items-center gap-2.5 min-w-0">
                        <span aria-hidden="true" className="w-1.5 h-7 rounded-full shrink-0" style={{ background: CATEGORICAL[i % CATEGORICAL.length] }} />
                        <span className="font-semibold text-ink truncate">{row.name}</span>
                      </span>
                    </td>
                    <td className="py-2.5 pr-8 text-right tabular-nums font-semibold text-ink whitespace-nowrap">{row.weight.toFixed(1)}%</td>
                    <td className={`py-2.5 text-right text-ink whitespace-nowrap ${showProfit ? "pr-8" : ""}`}>
                      <Money value={row.value} currency={currency} />
                    </td>
                    {showProfit && (
                      <td className="py-2.5 text-right tabular-nums font-medium whitespace-nowrap">
                        <ProfitCell profit={row.profit} currency={currency} />
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            )}
            {hiddenCount > 0 && (
              <Link to="/allocation" className="mt-2 inline-block text-xs font-semibold text-brand hover:text-brand-dim">
                {t("+{count} more in Allocation", { count: hiddenCount })}
              </Link>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
