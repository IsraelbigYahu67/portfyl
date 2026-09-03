import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchTaxReport } from "../editions/localApi";
import { useCurrency } from "../App";
import MetricCard from "../components/MetricCard";
import { FileText, Download, TrendingUp, TrendingDown, ShieldCheck, AlertTriangle, Hourglass } from "lucide-react";
import { TickerLink } from "../components/StockDetail";

// Czech §4 capital gains exemption rules. Kept on the client so the labels can
// be tweaked without touching the API.
const CZ = {
  TIME_TEST_YEARS: 3,
  VALUE_TEST_LIMIT: 100_000,
  TIME_TEST_CAP: 40_000_000,
};

const fmtCzk = (n) => {
  if (n == null) return "—";
  const sign = n < 0 ? "-" : "";
  return sign + Math.abs(n).toLocaleString("cs-CZ", {
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }) + " Kč";
};

function CzechTaxYearCard({ y }) {
  // Cards collapse the per-year summary into actionable rows. Order matters:
  // value test first (because if it passes, the rest are moot), then time test,
  // then the 40M cap, then the bottom-line taxable amount.
  const taxablePositive = y.taxable_total_czk > 0;
  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold flex items-center gap-2">
          <ShieldCheck size={14} className="text-brand" />
          Czech Tax — {y.tax_year}
        </h3>
        <span className="text-[10px] text-muted">§4 ZDP · {y.trades} trade{y.trades === 1 ? "" : "s"}</span>
      </div>

      {y.incomplete_fx && (
        <div className="flex items-start gap-2 text-[11px] text-amber-300 bg-amber-400/5 border border-amber-400/20 rounded p-2">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          <span>
            Some transactions are missing the CZK exchange rate — totals exclude those rows.
            Re-importing or refreshing FX rates will close the gap.
          </span>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="text-muted">Gross sale proceeds</div>
        <div className="text-right tabular-nums">{fmtCzk(y.gross_proceeds_czk)}</div>

        <div className="text-muted">Value test (≤ {CZ.VALUE_TEST_LIMIT.toLocaleString("cs-CZ")} Kč)</div>
        <div className="text-right">
          {y.value_test_passed ? (
            <span className="text-gain font-medium">✓ Passed — fully exempt</span>
          ) : (
            <span className="text-muted">Above threshold</span>
          )}
        </div>

        <div className="text-muted">Time-test exempt (&gt; 3 yrs)</div>
        <div className="text-right tabular-nums text-gain">{fmtCzk(y.time_test_exempt_gain_czk)}</div>

        {y.time_test_cap_active && (
          <>
            <div className="text-muted">40M cap status</div>
            <div className="text-right">
              {y.time_test_cap_excess_czk > 0 ? (
                <span className="text-loss">Exceeded by {fmtCzk(y.time_test_cap_excess_czk)}</span>
              ) : (
                <span className="text-gain">Within cap</span>
              )}
            </div>
          </>
        )}

        <div className="text-muted">Pre-cap taxable gain (&lt; 3 yrs)</div>
        <div className="text-right tabular-nums text-muted">{fmtCzk(y.taxable_gain_czk_pre_cap)}</div>
      </div>

      <div className="border-t border-surface-border pt-3 grid grid-cols-2 gap-2 text-sm">
        <div className="text-muted">Exempt total</div>
        <div className="text-right tabular-nums font-bold text-gain">{fmtCzk(y.exempt_total_czk)}</div>
        <div className="text-muted">Taxable in CZ</div>
        <div className={`text-right tabular-nums font-bold ${taxablePositive ? "text-orange-600" : "text-muted"}`}>
          {fmtCzk(y.taxable_total_czk)}
        </div>
      </div>
    </div>
  );
}

function CzechTaxPanel({ years, year }) {
  if (!years || years.length === 0) return null;
  const visible = year ? years.filter((y) => y.tax_year === year) : years;
  if (!visible.length) return null;

  return (
    <section>
      <h2 className="text-sm font-semibold text-muted mb-3 uppercase tracking-wider flex items-center gap-2">
        <ShieldCheck size={14} className="text-brand" />
        Czech §4 Exemption Analysis
      </h2>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {visible.map((y) => (
          <CzechTaxYearCard key={y.tax_year} y={y} />
        ))}
      </div>
    </section>
  );
}

export default function TaxReport() {
  const { currency, rate } = useCurrency();
  const [year, setYear] = useState(null);
  const [tab, setTab] = useState("realized");

  const convert = (n) => (currency === "CZK" && rate ? n * rate : n);
  const fmt = (n) => {
    if (n == null) return "—";
    const sign = n < 0 ? "-" : "";
    const str = Math.abs(convert(n)).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return currency === "CZK" ? `${sign}${str} Kč` : `${sign}$${str}`;
  };

  // For amounts the backend also provides in CZK at trade-time FX. In CZK mode
  // these are authoritative for Czech filing — use them instead of fmt()'s
  // approximate live-rate conversion of the USD figure.
  const fmtMoney = (usd, czk) =>
    currency === "CZK" ? (czk == null ? "—" : fmtCzk(czk)) : fmt(usd);

  const fmtPct = (n) => (n >= 0 ? "+" : "") + n.toFixed(2) + "%";

  const { data, isLoading } = useQuery({
    queryKey: ["tax-report", year],
    queryFn: () => fetchTaxReport(year),
  });

  const summary = data?.summary || {};
  const gains = data?.gains || [];
  const unrealized = data?.unrealized || [];
  const dividendIncome = data?.dividend_income || [];
  const availableYears = data?.available_years || [];
  const czechTax = data?.czech_tax || [];

  const shortGains = gains.filter((g) => g.term === "short");
  const longGains = gains.filter((g) => g.term === "long");

  const exportCSV = () => {
    if (!gains.length && !dividendIncome.length) return;

    // USD columns are the raw lot figures; the *_czk columns use the FX captured
    // at each trade date (what a Czech filing needs), blank when unavailable.
    const czk = (n) => (n == null ? "" : n);
    let csv = "Section,Ticker,Buy Date,Sell Date,Shares,Cost Basis (USD),Proceeds (USD),Gain/Loss (USD),Cost Basis (CZK),Proceeds (CZK),Gain/Loss (CZK),Gain %,Holding Days,Term\n";
    for (const g of gains) {
      csv += `Realized,${g.ticker},${g.buy_date},${g.sell_date},${g.shares},${g.cost_basis},${g.proceeds},${g.gain},${czk(g.cost_basis_czk)},${czk(g.proceeds_czk)},${czk(g.gain_czk)},${g.gain_pct}%,${g.holding_days},${g.term}\n`;
    }
    if (dividendIncome.length) {
      csv += "\nSection,Ticker,Amount (USD),Amount (CZK)\n";
      for (const d of dividendIncome) {
        csv += `Dividend,${d.ticker},${d.amount},${czk(d.amount_czk)}\n`;
      }
    }
    if (unrealized.length) {
      csv += "\nSection,Ticker,Buy Date,Shares,Cost Basis,Market Value,Unrealized Gain,Gain %,Holding Days,Term\n";
      for (const u of unrealized) {
        csv += `Unrealized,${u.ticker},${u.buy_date},${u.shares},${u.cost_basis},${u.market_value},${u.unrealized_gain},${u.gain_pct}%,${u.holding_days},${u.term}\n`;
      }
    }

    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `tax-report-${year || "all"}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const TABS = [
    { key: "realized", label: "Realized Gains", count: gains.length },
    { key: "unrealized", label: "Unrealized Gains", count: unrealized.length },
    { key: "dividends", label: "Dividend Income", count: dividendIncome.length },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold flex items-center gap-2">
            <FileText size={20} className="text-brand" />
            Tax Report
          </h1>
          <p className="text-xs text-muted mt-0.5">Capital gains, losses, and dividend income (FIFO method)</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={year || ""}
            onChange={(e) => setYear(e.target.value ? parseInt(e.target.value) : null)}
            className="bg-surface border border-surface-border rounded-lg px-3 py-1.5 text-sm text-ink focus:outline-none focus:ring-1 focus:ring-brand"
          >
            <option value="">All Years</option>
            {availableYears.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
          <button
            onClick={exportCSV}
            disabled={!gains.length && !dividendIncome.length}
            className="btn-ghost flex items-center gap-2 text-sm disabled:opacity-30"
          >
            <Download size={14} />
            Export CSV
          </button>
        </div>
      </div>

      {isLoading ? (
        <div className="card animate-pulse h-32 flex items-center justify-center text-muted">
          Generating tax report…
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
            <MetricCard
              label="Total Realized P&L"
              value={fmtMoney(summary.total_realized, summary.total_realized_czk)}
              positive={summary.total_realized >= 0}
              negative={summary.total_realized < 0}
            />
            <MetricCard
              label="Short-Term Gains"
              value={fmtMoney(summary.short_term_gains, summary.short_term_gains_czk)}
              sub={`${summary.short_term_count || 0} trades`}
              positive={summary.short_term_gains >= 0}
              negative={summary.short_term_gains < 0}
            />
            <MetricCard
              label="Long-Term Gains"
              value={fmtMoney(summary.long_term_gains, summary.long_term_gains_czk)}
              sub={`${summary.long_term_count || 0} trades`}
              positive={summary.long_term_gains >= 0}
              negative={summary.long_term_gains < 0}
            />
            <MetricCard
              label="Dividend Income"
              value={fmtMoney(summary.total_dividends, summary.total_dividends_czk)}
              sub={`${dividendIncome.length} stocks`}
            />
          </div>

          <CzechTaxPanel years={czechTax} year={year} />

          <div className="card p-0 overflow-hidden">
            <div className="flex border-b border-surface-border">
              {TABS.map((t) => (
                <button
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={`px-5 py-3 text-sm font-medium transition-colors ${
                    tab === t.key
                      ? "text-brand border-b-2 border-brand"
                      : "text-muted hover:text-ink"
                  }`}
                >
                  {t.label}
                  {t.count > 0 && (
                    <span className="ml-2 text-xs bg-surface-hover px-1.5 py-0.5 rounded-full">{t.count}</span>
                  )}
                </button>
              ))}
            </div>

            {tab === "realized" && (
              <div className="overflow-x-auto">
                {!gains.length ? (
                  <div className="text-muted text-sm text-center py-12">
                    No realized gains or losses{year ? ` in ${year}` : ""}.
                  </div>
                ) : (
                  <table className="w-full">
                    <thead className="border-b border-surface-border">
                      <tr>
                        {["Ticker", "Buy Date", "Sell Date", "Shares", "Cost Basis", "Proceeds", "Gain/Loss", "Gain %", "Days Held", "Term", "CZ Tax"].map((h) => (
                          <th key={h} className="text-left px-4 py-3 text-xs font-medium text-muted uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-border">
                      {gains.map((g, i) => {
                        const up = g.gain >= 0;
                        return (
                          <tr key={i} className="hover:bg-surface-hover transition-colors">
                            <td className="px-4 py-3 font-mono font-bold text-sm">
                              <TickerLink ticker={g.ticker}>{g.ticker}</TickerLink>
                            </td>
                            <td className="px-4 py-3 text-sm text-muted tabular-nums">{g.buy_date}</td>
                            <td className="px-4 py-3 text-sm text-muted tabular-nums">{g.sell_date}</td>
                            <td className="px-4 py-3 text-sm text-right tabular-nums">{g.shares}</td>
                            <td className="px-4 py-3 text-sm text-right tabular-nums">{fmt(g.cost_basis)}</td>
                            <td className="px-4 py-3 text-sm text-right tabular-nums">{fmt(g.proceeds)}</td>
                            <td className={`px-4 py-3 text-sm text-right tabular-nums font-medium ${up ? "text-gain" : "text-loss"}`}>
                              <span className="flex items-center justify-end gap-1">
                                {up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                                {fmt(g.gain)}
                              </span>
                            </td>
                            <td className={`px-4 py-3 text-sm text-right tabular-nums ${up ? "text-gain" : "text-loss"}`}>
                              {fmtPct(g.gain_pct)}
                            </td>
                            <td className="px-4 py-3 text-sm text-right tabular-nums text-muted">{g.holding_days}d</td>
                            <td className="px-4 py-3">
                              <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                                g.term === "long"
                                  ? "bg-blue-400/10 text-blue-400"
                                  : "bg-yellow-400/10 text-yellow-400"
                              }`}>
                                {g.term === "long" ? "LONG" : "SHORT"}
                              </span>
                            </td>
                            <td className="px-4 py-3">
                              {g.cz_exempt_time_test ? (
                                <span
                                  className="text-[10px] font-bold px-2 py-0.5 rounded bg-gain/10 text-gain"
                                  title={`Held >3 years (§4 ZDP) — exempt from CZ income tax. Acquired ${g.buy_date}, exempt from ${g.cz_exempt_date}.`}
                                >
                                  EXEMPT 3Y
                                </span>
                              ) : (
                                <span
                                  className="text-[10px] font-bold px-2 py-0.5 rounded bg-orange-400/10 text-orange-400"
                                  title={`Held <3 years — taxable in CZ unless annual gross proceeds ≤ ${CZ.VALUE_TEST_LIMIT.toLocaleString("cs-CZ")} Kč. Would be exempt from ${g.cz_exempt_date}.`}
                                >
                                  TAXABLE
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                    <tfoot className="border-t-2 border-surface-border bg-surface">
                      <tr>
                        <td className="px-4 py-3 text-sm font-bold" colSpan={5}>Short-Term Total</td>
                        <td className="px-4 py-3 text-sm text-right tabular-nums">{fmt(shortGains.reduce((s, g) => s + g.proceeds, 0))}</td>
                        <td className={`px-4 py-3 text-sm text-right tabular-nums font-bold ${summary.short_term_gains >= 0 ? "text-gain" : "text-loss"}`}>
                          {fmtMoney(summary.short_term_gains, summary.short_term_gains_czk)}
                        </td>
                        <td colSpan={4}></td>
                      </tr>
                      <tr>
                        <td className="px-4 py-3 text-sm font-bold" colSpan={5}>Long-Term Total</td>
                        <td className="px-4 py-3 text-sm text-right tabular-nums">{fmt(longGains.reduce((s, g) => s + g.proceeds, 0))}</td>
                        <td className={`px-4 py-3 text-sm text-right tabular-nums font-bold ${summary.long_term_gains >= 0 ? "text-gain" : "text-loss"}`}>
                          {fmtMoney(summary.long_term_gains, summary.long_term_gains_czk)}
                        </td>
                        <td colSpan={4}></td>
                      </tr>
                    </tfoot>
                  </table>
                )}
              </div>
            )}

            {tab === "unrealized" && (
              <div className="overflow-x-auto">
                {!unrealized.length ? (
                  <div className="text-muted text-sm text-center py-12">No open positions with lot data.</div>
                ) : (
                  <table className="w-full">
                    <thead className="border-b border-surface-border">
                      <tr>
                        {["Ticker", "Buy Date", "Shares", "Cost Basis", "Market Value", "Unrealized G/L", "Gain %", "Days Held", "Term", "Tax-free In"].map((h) => (
                          <th key={h} className="text-left px-4 py-3 text-xs font-medium text-muted uppercase tracking-wider">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-border">
                      {unrealized.map((u, i) => {
                        const up = u.unrealized_gain >= 0;
                        return (
                          <tr key={i} className="hover:bg-surface-hover transition-colors">
                            <td className="px-4 py-3 font-mono font-bold text-sm">
                              <TickerLink ticker={u.ticker}>{u.ticker}</TickerLink>
                            </td>
                            <td className="px-4 py-3 text-sm text-muted tabular-nums">{u.buy_date}</td>
                            <td className="px-4 py-3 text-sm text-right tabular-nums">{u.shares}</td>
                            <td className="px-4 py-3 text-sm text-right tabular-nums">{fmt(u.cost_basis)}</td>
                            <td className="px-4 py-3 text-sm text-right tabular-nums font-medium">{fmt(u.market_value)}</td>
                            <td className={`px-4 py-3 text-sm text-right tabular-nums font-medium ${up ? "text-gain" : "text-loss"}`}>
                              <span className="flex items-center justify-end gap-1">
                                {up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                                {fmt(u.unrealized_gain)}
                              </span>
                            </td>
                            <td className={`px-4 py-3 text-sm text-right tabular-nums ${up ? "text-gain" : "text-loss"}`}>
                              {fmtPct(u.gain_pct)}
                            </td>
                            <td className="px-4 py-3 text-sm text-right tabular-nums text-muted">{u.holding_days}d</td>
                            <td className="px-4 py-3">
                              <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${
                                u.term === "long"
                                  ? "bg-blue-400/10 text-blue-400"
                                  : "bg-yellow-400/10 text-yellow-400"
                              }`}>
                                {u.term === "long" ? "LONG" : "SHORT"}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-sm">
                              {u.cz_exempt_time_test ? (
                                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-gain/10 text-gain" title={`Exempt from ${u.cz_exempt_date} (§4 ZDP)`}>
                                  EXEMPT
                                </span>
                              ) : (
                                <span
                                  className="inline-flex items-center gap-1 text-[11px] tabular-nums text-amber-300"
                                  title={`Tax-free if sold on or after ${u.cz_exempt_date} (§4 ZDP, 3-year time test)`}
                                >
                                  <Hourglass size={10} />
                                  {u.cz_days_to_exemption}d
                                  <span className="text-muted">({u.cz_exempt_date})</span>
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                    <tfoot className="border-t-2 border-surface-border bg-surface">
                      <tr>
                        <td className="px-4 py-3 text-sm font-bold" colSpan={3}>Total Unrealized</td>
                        <td className="px-4 py-3 text-sm text-right tabular-nums font-medium">{fmt(unrealized.reduce((s, u) => s + u.cost_basis, 0))}</td>
                        <td className="px-4 py-3 text-sm text-right tabular-nums font-medium">{fmt(unrealized.reduce((s, u) => s + u.market_value, 0))}</td>
                        <td className={`px-4 py-3 text-sm text-right tabular-nums font-bold ${
                          unrealized.reduce((s, u) => s + u.unrealized_gain, 0) >= 0 ? "text-gain" : "text-loss"
                        }`}>
                          {fmt(unrealized.reduce((s, u) => s + u.unrealized_gain, 0))}
                        </td>
                        <td colSpan={4}></td>
                      </tr>
                    </tfoot>
                  </table>
                )}
              </div>
            )}

            {tab === "dividends" && (
              <div className="overflow-x-auto">
                {!dividendIncome.length ? (
                  <div className="text-muted text-sm text-center py-12">
                    No dividend income{year ? ` in ${year}` : ""}.
                  </div>
                ) : (
                  <table className="w-full">
                    <thead className="border-b border-surface-border">
                      <tr>
                        <th className="text-left px-4 py-3 text-xs font-medium text-muted uppercase tracking-wider">Ticker</th>
                        <th className="text-left px-4 py-3 text-xs font-medium text-muted uppercase tracking-wider">Amount</th>
                        <th className="text-left px-4 py-3 text-xs font-medium text-muted uppercase tracking-wider">% of Total</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-surface-border">
                      {dividendIncome.map((d) => (
                        <tr key={d.ticker} className="hover:bg-surface-hover transition-colors">
                          <td className="px-4 py-3 font-mono font-bold text-sm">
                            <TickerLink ticker={d.ticker}>{d.ticker}</TickerLink>
                          </td>
                          <td className="px-4 py-3 text-sm tabular-nums text-gain font-medium">{fmt(d.amount)}</td>
                          <td className="px-4 py-3 text-sm text-muted">
                            <div className="flex items-center gap-2">
                              <div className="w-24 bg-surface-hover rounded-full h-1.5">
                                <div
                                  className="bg-green-500 rounded-full h-1.5"
                                  style={{ width: `${summary.total_dividends > 0 ? (d.amount / summary.total_dividends * 100) : 0}%` }}
                                />
                              </div>
                              <span className="tabular-nums">
                                {summary.total_dividends > 0 ? (d.amount / summary.total_dividends * 100).toFixed(1) : 0}%
                              </span>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot className="border-t-2 border-surface-border bg-surface">
                      <tr>
                        <td className="px-4 py-3 text-sm font-bold">Total</td>
                        <td className="px-4 py-3 text-sm tabular-nums text-gain font-bold">{fmtMoney(summary.total_dividends, summary.total_dividends_czk)}</td>
                        <td></td>
                      </tr>
                    </tfoot>
                  </table>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
