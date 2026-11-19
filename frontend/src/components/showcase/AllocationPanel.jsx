import { useMemo } from "react";
import AllocationChart from "../AllocationChart";
import AllocationBreakdownList from "../AllocationBreakdownList";
import SegmentedControl from "../ui/SegmentedControl";
import { SectionHeader } from "../ui/SectionHeader";
import { formatMoney, formatPercent } from "../../lib/format";
import { groupHoldings } from "./showcaseMath";

/**
 * Allocation card: a grouping switch, the donut and the full breakdown list,
 * built from the app's own AllocationChart / AllocationBreakdownList.
 *
 * Props only, no data fetching and no translation: every string arrives in
 * `labels`.
 *  - holdings: [{ symbol, sector, country, currency, assetType, marketValue, weight }]
 *    with `marketValue` already in `currency`.
 *  - grouping: holdings | sectors | countries | currencies | assetTypes
 *  - groupings: [{ value, label }] offered by the switch
 *  - labels: { title, groupingAria, tableCaption, columns: { name, value, weight } }
 */
export default function AllocationPanel({ holdings, currency, grouping, groupings, onGroupingChange, labels }) {
  const rows = useMemo(() => groupHoldings(holdings, grouping), [holdings, grouping]);
  const chartRows = useMemo(
    () => rows.map((row) => ({ ticker: row.name, market_value: row.value, weight: row.weight })),
    [rows],
  );

  return (
    <section className="card p-5 max-sm:p-4 min-w-0">
      <SectionHeader
        action={(
          <SegmentedControl
            aria-label={labels.groupingAria}
            value={grouping}
            onChange={onGroupingChange}
            options={groupings}
          />
        )}
      >
        {labels.title}
      </SectionHeader>
      {/* A long legend (one entry per position) would crowd the donut out on a phone; the list below names every row. */}
      <div className={rows.length > 8 ? "max-sm:[&_.recharts-legend-wrapper]:hidden" : undefined}>
        <AllocationChart holdings={chartRows} currency={currency} />
      </div>
      <table className="sr-only">
        <caption>{labels.tableCaption}</caption>
        <thead>
          <tr><th scope="col">{labels.columns.name}</th><th scope="col">{labels.columns.value}</th><th scope="col">{labels.columns.weight}</th></tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.name}>
              <th scope="row">{row.name}</th>
              <td>{formatMoney(row.value, currency)}</td>
              <td>{formatPercent(row.weight, { sign: false })}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-4 min-w-0 overflow-x-auto [&_.financial-data.w-24]:w-auto max-sm:[&_li]:gap-2 max-sm:[&_li>span:first-child]:w-[4.5rem]">
        <AllocationBreakdownList rows={rows} currency={currency} />
      </div>
    </section>
  );
}
