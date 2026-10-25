import { useState } from "react";
import { Link } from "react-router-dom";
import { PieChart as PieIcon, ArrowRight } from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer } from "recharts";
import SegmentedControl from "../ui/SegmentedControl";
import { SectionHeader } from "../ui";
import { CATEGORICAL } from "../../lib/chartTheme";
import { withSliceCorners } from "../../lib/pieCorners";
import { displayLocale, formatCompact, formatMoney } from "../../lib/format";
import { buildCompositionRows } from "../../lib/dashboardSummaries";

const DIMENSIONS = [
  { value: "sectors", label: "Sectors" },
  { value: "countries", label: "Countries" },
  { value: "asset_types", label: "Categories" },
];
// The Countries tab deliberately has no profit column.
const NO_PROFIT = new Set(["countries"]);
const MAX_ROWS = 8;

// Realized + unrealized profit with its sign. A profit that rounds to zero
// reads as neutral, never as a red "-0".
function ProfitCell({ profit, currency }) {
  if (profit == null) return <span className="text-muted">—</span>;
  const rounded = Math.round(profit);
  const tone = rounded > 0 ? "text-gain" : rounded < 0 ? "text-loss" : "text-muted";
  return <span className={tone}>{rounded > 0 ? "+" : ""}{formatMoney(rounded, currency)}</span>;
}

// Splits a formatted amount at its decimal separator so the value column can
// sit in two cells (integer part right-aligned, fraction left-aligned) and the
// separators of every row, and the "Value" heading, share one vertical line.
function splitDecimal(text, currency) {
  const at = text.lastIndexOf(displayLocale(currency) === "cs-CZ" ? "," : ".");
  return at < 0 ? [text, ""] : [text.slice(0, at), text.slice(at)];
}

// Portfolio composition (dashboard variant A): a donut plus a table of the
// same rows, grouped by asset type, sector or country from
// /analytics/sector-breakdown. Columns: weight, value, and total profit
// (realized + unrealized).
export default function CompositionCard({ breakdown, currency }) {
  const [dimension, setDimension] = useState(DIMENSIONS[0].value);
  const showProfit = !NO_PROFIT.has(dimension);
  const rows = buildCompositionRows(breakdown?.[dimension] || []);
  const shown = rows.slice(0, MAX_ROWS);
  const hiddenCount = rows.length - shown.length;
  // Sum the rows instead of using breakdown.total_value: the API folds cash
  // into the rows but leaves it out of total_value.
  const total = rows.reduce((sum, row) => sum + row.value, 0);
  // The donut radii are percentages of its max radius (~140px at full size), so
  // the 9px corner is ~6.5 in the same percent units.
  const pieSlices = withSliceCorners(shown, { valueKey: "value", inner: 62, outer: 92, corner: 6.5 });

  return (
    <div className="flex flex-col h-full">
      <SectionHeader
        icon={PieIcon}
        action={
          <>
            <SegmentedControl aria-label="Group composition by" value={dimension} onChange={setDimension} options={DIMENSIONS} />
            <Link to="/allocation" className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:text-brand-dim">
              Targets <ArrowRight size={12} aria-hidden="true" />
            </Link>
          </>
        }
      >
        Portfolio composition
      </SectionHeader>

      {rows.length === 0 ? (
        <p className="text-sm text-muted py-6 text-center">No holdings to group yet.</p>
      ) : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,280px)_minmax(0,1fr)] items-center">
          <div className="pie-pop relative mx-auto w-full max-w-[280px] aspect-square">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieSlices} dataKey="value" nameKey="name" innerRadius="62%" outerRadius="92%" paddingAngle={3} cornerRadius={9} stroke="none" isAnimationActive={false}>
                  {shown.map((row, i) => <Cell key={row.name} fill={CATEGORICAL[i % CATEGORICAL.length]} />)}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 grid place-content-center text-center">
              <span className="data-label">Total value</span>
              <span className="font-display text-xl font-bold text-ink tabular-nums">{formatCompact(total, currency)}</span>
            </div>
          </div>

          <div className="min-w-0 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-muted">
                  <th scope="col" className="pb-2 font-medium">Name</th>
                  <th scope="col" className="pb-2 pr-3 font-medium text-right">Weight</th>
                  {/* Two header cells like the body: the word is centred on the split, over the decimal separator. */}
                  <th scope="col" className="pb-2 font-medium text-right">
                    <span className="inline-block w-0 overflow-visible">
                      <span className="inline-block translate-x-[calc(-50%+3px)]">Value</span>
                    </span>
                  </th>
                  <th scope="col" className="pb-2 pr-3" aria-hidden="true" />
                  {showProfit && <th scope="col" className="pb-2 font-medium text-right" title="Realized + unrealized profit">Profit</th>}
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
                    <td className="py-2.5 pr-3 text-right tabular-nums font-semibold text-ink">{row.weight.toFixed(1)}%</td>
                    {(([whole, fraction]) => (
                      <>
                        <td className="py-2.5 text-right tabular-nums text-ink whitespace-nowrap">{whole}</td>
                        <td className="py-2.5 pr-3 text-left tabular-nums text-ink whitespace-nowrap">{fraction}</td>
                      </>
                    ))(splitDecimal(formatMoney(row.value, currency), currency))}
                    {showProfit && (
                      <td className="py-2.5 text-right tabular-nums font-medium whitespace-nowrap">
                        <ProfitCell profit={row.profit} currency={currency} />
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            {hiddenCount > 0 && (
              <Link to="/allocation" className="mt-2 inline-block text-xs font-semibold text-brand hover:text-brand-dim">
                +{hiddenCount} more in Allocation
              </Link>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
