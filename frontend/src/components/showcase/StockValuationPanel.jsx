import { useMemo } from "react";
import { StockHeader } from "../stock/StockHeader";
import ValuationHistoryCharts from "../stock/ValuationHistoryCharts";
import KpiBox from "../ui/KpiBox";
import { formatPercent, formatShortDate } from "../../lib/format";
import { fiveYearAveragePe, stockHeaderData } from "./showcaseMath";

const DASH = "—";

function multiple(value) {
  return Number.isFinite(value) ? value.toFixed(1) : DASH;
}

/**
 * Stock detail teaser: the stock header, the P/E against its five-year
 * average (Portfyl values a stock against the average, not today's P/E) and
 * the P/E valuation history.
 *
 *  - holding: a holding of demoPortfolio.js (needs `fundamentals`)
 *  - peHistory: [{ bucket, trailing_pe }]; empty or missing = no history, the
 *    average and the difference show a dash
 *  - labels: { pe, fivePe, forwardPe, vsAverage, historyTitle, tableCaption, disclaimer }
 *
 * `currency` is accepted for symmetry with the other panels; the header prints
 * the holding's own quote currency and the multiples are plain numbers.
 */
export default function StockValuationPanel({ holding, peHistory, labels }) {
  const points = useMemo(() => peHistory ?? [], [peHistory]);
  const average = useMemo(() => fiveYearAveragePe(points), [points]);
  const pe = holding.fundamentals.pe;
  const forwardPe = holding.fundamentals.forwardPe;
  const versusAverage = Number.isFinite(pe) && Number.isFinite(average) && average !== 0
    ? (pe / average - 1) * 100
    : null;
  const peRows = points.filter((point) => Number.isFinite(point.trailing_pe));

  return (
    <div className="space-y-4 min-w-0">
      <div className="rounded-xl border border-hairline bg-surface-card overflow-hidden">
        <StockHeader data={stockHeaderData(holding)} />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiBox label={labels.pe} value={multiple(pe)} />
        <KpiBox label={labels.fivePe} value={multiple(average)} />
        <KpiBox label={labels.forwardPe} value={multiple(forwardPe)} />
        <KpiBox label={labels.vsAverage} value={versusAverage == null ? DASH : formatPercent(versusAverage)} />
      </div>

      {peRows.length > 0 && (
        <section className="min-w-0">
          <h3 className="section-title mb-3">{labels.historyTitle}</h3>
          <ValuationHistoryCharts key={holding.symbol} points={points} />
          <table className="sr-only">
            <caption>{labels.tableCaption}</caption>
            <thead>
              <tr><th scope="col">{labels.historyTitle}</th><th scope="col">{labels.pe}</th></tr>
            </thead>
            <tbody>
              {peRows.map((point) => (
                <tr key={point.bucket}>
                  <th scope="row">{formatShortDate(point.bucket, { month: "short", year: "numeric" })}</th>
                  <td>{multiple(point.trailing_pe)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      <p className="financial-meta text-muted">{labels.disclaimer}</p>
    </div>
  );
}
