import { useMemo } from "react";
import PortfolioHero from "../PortfolioHero";
import AllocationBreakdownList from "../AllocationBreakdownList";
import SegmentedControl from "../ui/SegmentedControl";
import { formatMoney, formatPercent } from "../../lib/format";
import { portfolioTotals } from "./showcaseData";

/**
 * Several portfolios in one currency: the app's PortfolioHero for the sum of
 * all of them and one breakdown row per portfolio.
 *
 *  - portfolios: either the rows of `portfolioTotals(displayCurrency)`
 *    ({ key, value, cash, weight }, already converted) or raw sample
 *    portfolios (SHOWCASE_PORTFOLIOS shape), which are converted here
 *  - displayCurrency / onCurrencyChange / currencies: the currency switch
 *    ([{ value, label }])
 *  - labels: { currencyAria, portfolioNames: { long, dividend, growth },
 *    ratesNote, tableCaption, columns: { name, value, weight } }
 *  - holdingsCount, dividendsTotal: optional figures for the two small chips
 *    of the hero; without them the chips show a dash
 */
export default function PortfoliosPanel({
  portfolios,
  displayCurrency,
  onCurrencyChange,
  currencies,
  labels,
  holdingsCount,
  dividendsTotal,
}) {
  const totals = useMemo(
    () => (portfolios.some((portfolio) => Array.isArray(portfolio.holdings))
      ? portfolioTotals(displayCurrency, portfolios)
      : portfolios),
    [portfolios, displayCurrency],
  );
  const rows = useMemo(
    () => totals.map((row) => ({ name: labels.portfolioNames[row.key] ?? row.key, value: row.value, weight: row.weight })),
    [totals, labels.portfolioNames],
  );
  const netWorth = totals.reduce((sum, row) => sum + row.value, 0);
  const cash = totals.reduce((sum, row) => sum + row.cash, 0);
  const summary = {
    net_worth: netWorth,
    total_value: netWorth - cash,
    cash,
    total_dividends: dividendsTotal,
    holdings_count: holdingsCount,
  };

  return (
    <div className="space-y-4 min-w-0">
      <div className="flex justify-end">
        <SegmentedControl aria-label={labels.currencyAria} value={displayCurrency} onChange={onCurrencyChange} options={currencies} />
      </div>
      <PortfolioHero summary={summary} loading={false} currency={displayCurrency} series={[]} />
      <section className="card p-5 min-w-0">
        <div className="min-w-0 overflow-x-auto">
          <AllocationBreakdownList rows={rows} currency={displayCurrency} />
        </div>
        <p className="financial-meta text-muted mt-4">{labels.ratesNote}</p>
        <table className="sr-only">
          <caption>{labels.tableCaption}</caption>
          <thead>
            <tr><th scope="col">{labels.columns.name}</th><th scope="col">{labels.columns.value}</th><th scope="col">{labels.columns.weight}</th></tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.name}>
                <th scope="row">{row.name}</th>
                <td>{formatMoney(row.value, displayCurrency)}</td>
                <td>{formatPercent(row.weight, { sign: false })}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
