import KpiBox from "../../components/ui/KpiBox";
import { SectionHeader } from "../../components/ui/SectionHeader";
import { formatMoney, formatPercent, formatShortDate } from "../../lib/format";
import { useDemoData } from "../DemoDataContext";

function quarterKey(date) {
  const year = date.slice(0, 4);
  const quarter = Math.floor((Number(date.slice(5, 7)) - 1) / 3) + 1;
  return `${year} Q${quarter}`;
}

function sumBy(rows, keyFor) {
  const groups = new Map();
  for (const row of rows) {
    const key = keyFor(row);
    groups.set(key, (groups.get(key) || 0) + row.amount);
  }
  return [...groups.entries()].map(([key, amount]) => ({ key, amount })).sort((a, b) => b.key.localeCompare(a.key));
}

export default function DemoDividends() {
  const data = useDemoData();
  const dividends = [...data.dividends].sort((a, b) => b.date.localeCompare(a.date) || a.symbol.localeCompare(b.symbol));
  const quarters = sumBy(dividends, (row) => quarterKey(row.date));
  const byPayer = sumBy(dividends, (row) => row.symbol).sort((a, b) => b.amount - a.amount);
  const years = sumBy(dividends, (row) => row.date.slice(0, 4)).sort((a, b) => a.key.localeCompare(b.key));

  return (
    <div className="space-y-8">
      <div>
        <p className="eyebrow data-label">Synthetic portfolio</p>
        <h1 className="text-2xl font-display font-bold mt-1">Dividends</h1>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <KpiBox label="Total dividend income" value={formatMoney(data.dividendTotal, "USD")} />
        <KpiBox label="Dividend events" value={String(dividends.length)} />
        <KpiBox label="Dividend payers" value={String(byPayer.length)} />
      </div>

      <section className="card p-5" aria-labelledby="quarterly-dividends-heading">
        <SectionHeader><span id="quarterly-dividends-heading">Quarterly synthetic income</span></SectionHeader>
        <p className="financial-meta text-muted">These dividend events are synthetic examples, not a forecast.</p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 mt-4">
          {quarters.map((quarter) => (
            <div key={quarter.key} className="rounded-lg bg-surface-hover p-3">
              <div className="data-label">{quarter.key}</div>
              <div className="financial-data mt-1">{formatMoney(quarter.amount, "USD")}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-2">
        <div className="card p-5">
          <SectionHeader>Income by payer</SectionHeader>
          <ul className="space-y-2" aria-label="Synthetic dividend income by payer">
            {byPayer.map((payer) => (
              <li key={payer.key} className="flex justify-between gap-4 financial-data"><span>{payer.key}</span><span>{formatMoney(payer.amount, "USD")}</span></li>
            ))}
          </ul>
        </div>
        <div className="card p-5">
          <SectionHeader>Year over year</SectionHeader>
          <ul className="space-y-2" aria-label="Synthetic dividend year-over-year direction">
            {years.map((year, index) => {
              const previous = years[index - 1]?.amount;
              const change = previous ? ((year.amount - previous) / previous) * 100 : null;
              const direction = change == null ? "—" : change >= 0 ? "↑" : "↓";
              return (
                <li key={year.key} className="flex justify-between gap-4 financial-data">
                  <span>{year.key}</span>
                  <span>{formatMoney(year.amount, "USD")} {change == null ? "" : `${direction} ${formatPercent(change)}`}</span>
                </li>
              );
            })}
          </ul>
        </div>
      </section>

      <section className="card p-5" aria-labelledby="dividend-payments-heading">
        <SectionHeader><span id="dividend-payments-heading">Dividend payments</span></SectionHeader>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[460px] text-left" aria-label="Synthetic dividend payments">
            <thead className="border-b border-hairline"><tr className="data-label"><th className="px-3 py-2">Date</th><th className="px-3 py-2">Payer</th><th className="px-3 py-2">Quarter</th><th className="px-3 py-2 text-right">Income</th></tr></thead>
            <tbody>{dividends.map((dividend) => <tr key={dividend.id} className="border-b border-hairline last:border-0"><td className="px-3 py-2 financial-meta">{formatShortDate(dividend.date)}</td><td className="px-3 py-2 financial-data">{dividend.symbol}</td><td className="px-3 py-2 financial-meta">{quarterKey(dividend.date)}</td><td className="px-3 py-2 financial-data text-right">{formatMoney(dividend.amount, dividend.currency)}</td></tr>)}</tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
