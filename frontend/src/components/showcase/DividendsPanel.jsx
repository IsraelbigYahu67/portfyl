import { useMemo } from "react";
import DividendBarsCard from "../dashboard/DividendBarsCard";
import SegmentedControl from "../ui/SegmentedControl";
import { formatMoney } from "../../lib/format";
import { useT } from "../../i18n/I18nProvider";
import { splitDividendForecast } from "../../lib/dashboardSummaries";
import { buildDividendForecast } from "./showcaseMath";

/**
 * Dividends card: money received this year, or the next 12 months (the same
 * months of the previous year, as an estimate), in the app's own monthly bars.
 *
 *  - dividends: sample events { date, symbol, amount } already in `currency`
 *  - asOf: "now" as YYYY-MM-DD; the panel never reads the clock
 *  - view: received | upcoming
 *  - views: [{ value, label }] offered by the switch
 *  - labels: { received, upcoming, receivedTotal, upcomingTotal, viewAria,
 *    tableCaption, columns: { month, amount } }
 */
export default function DividendsPanel({ dividends, asOf, currency, view, onViewChange, views, labels }) {
  const t = useT();
  const { received, upcoming } = useMemo(() => {
    const monthIndex = Number(asOf.slice(5, 7)) - 1;
    return splitDividendForecast(buildDividendForecast(dividends, asOf), { monthIndex });
  }, [dividends, asOf]);
  const isUpcoming = view === "upcoming";
  const half = isUpcoming ? upcoming : received;

  return (
    <section className="card p-5 max-sm:p-4 min-w-0">
      <div className="flex justify-end mb-4">
        <SegmentedControl aria-label={labels.viewAria} value={view} onChange={onViewChange} options={views} />
      </div>
      <DividendBarsCard
        title={isUpcoming ? labels.upcoming : labels.received}
        half={half}
        totalLabel={isUpcoming ? labels.upcomingTotal : labels.receivedTotal}
        currency={currency}
        tone={isUpcoming ? "brand" : "accent"}
      />
      <table className="sr-only">
        <caption>{labels.tableCaption}</caption>
        <thead>
          <tr><th scope="col">{labels.columns.month}</th><th scope="col">{labels.columns.amount}</th></tr>
        </thead>
        <tbody>
          {half.months.map((month) => (
            <tr key={`${month.year ?? ""}${month.month}`}>
              <th scope="row">{month.year ? `${t(month.month)} ${month.year}` : t(month.month)}</th>
              <td>{formatMoney(month.amount, currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
